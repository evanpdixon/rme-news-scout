"""
Metadata Enrichment
Follows article URLs to extract the real source name, favicon, og:image,
author, and description for story card generation.
Only runs on filtered articles to minimize HTTP requests.
"""

import httpx
import re
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed


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
                return match.group(1).strip()
    return ""


def _extract_favicon(html: str, base_url: str) -> str:
    """Extract the best favicon/icon URL from the page HTML."""
    # Look for apple-touch-icon first (higher res), then standard icons
    icon_patterns = [
        r'<link[^>]+rel="apple-touch-icon"[^>]+href="([^"]*)"',
        r"<link[^>]+rel='apple-touch-icon'[^>]+href='([^']*)'",
        r'<link[^>]+rel="icon"[^>]+href="([^"]*)"',
        r"<link[^>]+rel='icon'[^>]+href='([^']*)'",
        r'<link[^>]+rel="shortcut icon"[^>]+href="([^"]*)"',
        # href before rel variants
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
            # Relative URL
            parsed = urlparse(base_url)
            return f"{parsed.scheme}://{parsed.netloc}/{href}"

    # Fallback: try /favicon.ico at the domain root
    parsed = urlparse(base_url)
    return f"{parsed.scheme}://{parsed.netloc}/favicon.ico"


def _fetch_metadata(article: dict) -> dict:
    """Follow article URL to get real source info, image, author, summary."""
    url = article.get("url", "")
    if not url or "news.google.com/rss/articles/" in url:
        return article  # Skip Google News redirect URLs (can't resolve without JS)

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
        final_url = str(resp.url)  # After redirects (Google News -> actual article)
        html = resp.text[:80000]

        # Store the resolved URL (after Google News redirect)
        article["resolved_url"] = final_url

        # Real source name from og:site_name
        site_name = _extract_meta(html, [
            "og:site_name",
            "application-name",
        ])
        if site_name:
            article["site_name"] = site_name

        # Real article title from og:title (often cleaner than RSS title)
        og_title = _extract_meta(html, ["og:title", "twitter:title"])
        if og_title:
            article["og_title"] = og_title

        # Featured image
        if not article.get("image_url"):
            image = _extract_meta(html, [
                "og:image",
                "twitter:image",
                "twitter:image:src",
            ])
            if image:
                # Make absolute if relative
                if image.startswith("//"):
                    image = "https:" + image
                elif image.startswith("/"):
                    parsed = urlparse(final_url)
                    image = f"{parsed.scheme}://{parsed.netloc}{image}"
                article["image_url"] = image

        # Author
        if not article.get("author"):
            author = _extract_meta(html, [
                "author",
                "article:author",
                "og:article:author",
                "twitter:creator",
                "dc.creator",
            ])
            if author:
                article["author"] = author

        # Description / summary — always prefer the og:description for story cards
        desc = _extract_meta(html, [
            "og:description",
            "description",
            "twitter:description",
        ])
        if desc:
            article["og_description"] = desc[:600]
            # Also backfill summary if empty
            if not article.get("summary"):
                article["summary"] = desc[:500]

        # Source favicon/logo
        favicon = _extract_favicon(html, final_url)
        if favicon:
            article["favicon_url"] = favicon

    except Exception:
        pass  # Graceful failure — metadata is optional

    return article


def enrich_articles(articles: list[dict], max_workers: int = 6) -> list[dict]:
    """Enrich a list of articles with metadata from their actual URLs.

    Follows redirects (e.g. Google News -> real article), extracts
    og:site_name, og:image, og:description, author, and favicon.

    Args:
        articles: List of article dicts (mutated in place).
        max_workers: Number of concurrent fetch threads.

    Returns:
        The same list with enriched metadata fields.
    """
    if not articles:
        return articles

    print(f"  [Meta] Fetching metadata for {len(articles)} articles...")
    enriched_count = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_fetch_metadata, art): art for art in articles}
        for future in as_completed(futures):
            art = future.result()
            if art.get("image_url") or art.get("site_name"):
                enriched_count += 1

    print(f"  [Meta] Enriched {enriched_count}/{len(articles)} articles with metadata")
    return articles
