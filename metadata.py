"""
Metadata Enrichment
Follows article URLs to extract the real source name, favicon, og:image,
author, and description. Then uses Claude to generate article abstracts
for story card generation.
Only runs on filtered articles to minimize HTTP requests and API calls.
"""

import httpx
import json
import re
from html import unescape as html_unescape
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed

from bs4 import BeautifulSoup


def _extract_meta(html: str, properties: list[str]) -> str:
    """Extract content from a meta tag matching any of the given property/name values."""
    for prop in properties:
        patterns = [
            rf'<meta[^>]+(?:property|name)="{re.escape(prop)}"[^>]+content="([^"]*)"',
            rf'<meta[^>]+content="([^"]*)"[^>]+(?:property|name)="{re.escape(prop)}"',
            rf"<meta[^>]+(?:property|name)='{re.escape(prop)}'[^>]+content='([^']*)'",
            rf"<meta[^>]+content='([^']*)'[^>]+(?:property|name)='{re.escape(prop)}'",
        ]
        for pattern in patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                return html_unescape(match.group(1).strip())
    return ""


def _extract_article_text(html: str) -> str:
    """Extract the main article body text from HTML, stripping nav/ads/etc."""
    soup = BeautifulSoup(html, "html.parser")

    # Remove non-content elements
    for tag in soup.find_all(["nav", "header", "footer", "aside", "script",
                              "style", "noscript", "iframe", "form"]):
        tag.decompose()

    # Try to find the article body via common selectors
    article = (
        soup.find("article")
        or soup.find(class_=re.compile(r"article.?body|post.?content|entry.?content|story.?body", re.I))
        or soup.find(attrs={"itemprop": "articleBody"})
    )

    if article:
        text = article.get_text(separator=" ", strip=True)
    else:
        # Fallback: grab all paragraph text
        paragraphs = soup.find_all("p")
        text = " ".join(p.get_text(strip=True) for p in paragraphs)

    # Clean up whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text[:3000]  # Cap at 3000 chars for LLM context


def _extract_favicon(html: str, base_url: str) -> str:
    """Extract the best favicon/icon URL from the page HTML."""
    icon_patterns = [
        r'<link[^>]+rel="apple-touch-icon"[^>]+href="([^"]*)"',
        r"<link[^>]+rel='apple-touch-icon'[^>]+href='([^']*)'",
        r'<link[^>]+rel="icon"[^>]+href="([^"]*)"',
        r"<link[^>]+rel='icon'[^>]+href='([^']*)'",
        r'<link[^>]+rel="shortcut icon"[^>]+href="([^"]*)"',
        r'<link[^>]+href="([^"]*)"[^>]+rel="apple-touch-icon"',
        r'<link[^>]+href="([^"]*)"[^>]+rel="icon"',
    ]
    for pattern in icon_patterns:
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            href = match.group(1).strip()
            if href.startswith("//"):
                return "https:" + href
            if href.startswith("/"):
                parsed = urlparse(base_url)
                return f"{parsed.scheme}://{parsed.netloc}{href}"
            if href.startswith("http"):
                return href
            parsed = urlparse(base_url)
            return f"{parsed.scheme}://{parsed.netloc}/{href}"

    parsed = urlparse(base_url)
    return f"{parsed.scheme}://{parsed.netloc}/favicon.ico"


def _fetch_metadata(article: dict) -> dict:
    """Follow article URL to get real source info, image, author, and body text."""
    url = article.get("url", "")
    if not url or "news.google.com/rss/articles/" in url:
        return article

    try:
        resp = httpx.get(
            url,
            timeout=10,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            },
        )
        resp.raise_for_status()
        final_url = str(resp.url)
        html = resp.text[:80000]

        article["resolved_url"] = final_url

        # Real source name
        site_name = _extract_meta(html, ["og:site_name", "application-name"])
        if site_name:
            article["site_name"] = site_name

        # Real article title
        og_title = _extract_meta(html, ["og:title", "twitter:title"])
        if og_title:
            article["og_title"] = og_title

        # Featured image
        if not article.get("image_url"):
            image = _extract_meta(html, [
                "og:image", "twitter:image", "twitter:image:src",
            ])
            if image:
                if image.startswith("//"):
                    image = "https:" + image
                elif image.startswith("/"):
                    parsed = urlparse(final_url)
                    image = f"{parsed.scheme}://{parsed.netloc}{image}"
                article["image_url"] = image

        # Author
        if not article.get("author"):
            author = _extract_meta(html, [
                "author", "article:author", "og:article:author",
                "twitter:creator", "dc.creator",
            ])
            if author:
                article["author"] = author

        # og:description — only use if article-specific (>80 chars)
        desc = _extract_meta(html, [
            "og:description", "description", "twitter:description",
        ])
        if desc and len(desc) > 80:
            article["og_description"] = desc[:600]
        if not article.get("summary") and desc:
            article["summary"] = desc[:500]

        # Extract article body text for Claude abstract generation
        body_text = _extract_article_text(html)
        if body_text and len(body_text) > 100:
            article["_body_text"] = body_text

        # Favicon
        favicon = _extract_favicon(html, final_url)
        if favicon:
            article["favicon_url"] = favicon

    except Exception:
        pass

    return article


def _generate_abstracts(articles: list[dict]) -> None:
    """Use Claude to generate 2-3 sentence abstracts for articles.

    Processes articles in a single batch call to minimize API usage.
    Only generates abstracts for articles that have body text extracted.
    """
    from scorer import _call_llm

    # Filter to articles that need abstracts and have body text
    needs_abstract = [
        (i, art) for i, art in enumerate(articles)
        if art.get("_body_text") and not art.get("abstract")
    ]

    if not needs_abstract:
        print("  [Meta] No articles need abstract generation")
        return

    # Build batch prompt
    article_blocks = []
    for batch_idx, (orig_idx, art) in enumerate(needs_abstract):
        title = art.get("og_title") or art.get("title", "")
        source = art.get("site_name") or art.get("source", "")
        body = art.get("_body_text", "")[:2000]
        article_blocks.append(
            f"[{batch_idx}] Title: {title}\n"
            f"    Source: {source}\n"
            f"    Text: {body}"
        )

    prompt = (
        "Generate a concise 2-3 sentence abstract for each article below. "
        "The abstract should summarize the key facts — who, what, where, when, why. "
        "Write in a neutral news style. Do NOT include the article title in the abstract.\n\n"
        "Respond with ONLY a JSON array. No markdown fences.\n"
        'Each element: {"index": <0-based>, "abstract": "<2-3 sentences>"}\n\n'
        "Articles:\n\n" + "\n\n".join(article_blocks)
    )

    try:
        raw = _call_llm(prompt)
        # Strip markdown fences if present
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

        results = json.loads(raw)
        applied = 0
        for item in results:
            batch_idx = item.get("index", -1)
            abstract = item.get("abstract", "").strip()
            if 0 <= batch_idx < len(needs_abstract) and abstract:
                orig_idx = needs_abstract[batch_idx][0]
                articles[orig_idx]["abstract"] = abstract
                applied += 1

        print(f"  [Meta] Generated abstracts for {applied}/{len(needs_abstract)} articles")

    except Exception as e:
        print(f"  [Meta] Abstract generation failed: {e}")


def enrich_articles(articles: list[dict], max_workers: int = 6) -> list[dict]:
    """Enrich articles with metadata and Claude-generated abstracts.

    Step 1: Parallel HTTP fetches for og:image, site_name, body text, etc.
    Step 2: Single Claude API call to generate abstracts from extracted text.

    Args:
        articles: List of article dicts (mutated in place).
        max_workers: Number of concurrent fetch threads.

    Returns:
        The same list with enriched metadata and abstract fields.
    """
    if not articles:
        return articles

    # Step 1: Fetch metadata in parallel
    print(f"  [Meta] Fetching metadata for {len(articles)} articles...")
    enriched_count = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_fetch_metadata, art): art for art in articles}
        for future in as_completed(futures):
            art = future.result()
            if art.get("image_url") or art.get("site_name"):
                enriched_count += 1

    print(f"  [Meta] Enriched {enriched_count}/{len(articles)} articles with metadata")

    # Step 2: Generate abstracts using Claude
    _generate_abstracts(articles)

    # Clean up temporary body text (not needed in output)
    for art in articles:
        art.pop("_body_text", None)

    return articles
