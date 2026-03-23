"""
Metadata Enrichment
Fetches og:image and author metadata from article URLs for story card generation.
Only runs on filtered articles to minimize HTTP requests.
"""

import httpx
import re
from concurrent.futures import ThreadPoolExecutor, as_completed


def _extract_meta(html: str, properties: list[str]) -> str:
    """Extract content from a meta tag matching any of the given property/name values."""
    for prop in properties:
        # Match both property= and name= attributes, in either order
        patterns = [
            rf'<meta[^>]+(?:property|name)="{re.escape(prop)}"[^>]+content="([^"]*)"',
            rf'<meta[^>]+content="([^"]*)"[^>]+(?:property|name)="{re.escape(prop)}"',
            # Single-quote variants
            rf"<meta[^>]+(?:property|name)='{re.escape(prop)}'[^>]+content='([^']*)'",
            rf"<meta[^>]+content='([^']*)'[^>]+(?:property|name)='{re.escape(prop)}'",
        ]
        for pattern in patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                return match.group(1).strip()
    return ""


def _fetch_metadata(article: dict) -> dict:
    """Fetch og:image and author from an article's URL."""
    url = article.get("url", "")
    if not url:
        return article

    try:
        resp = httpx.get(
            url,
            timeout=8,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; RMENewsScout/1.0)"},
        )
        resp.raise_for_status()
        html = resp.text[:50000]  # Only parse first 50KB for meta tags

        # Extract featured image
        if not article.get("image_url"):
            image = _extract_meta(html, [
                "og:image",
                "twitter:image",
                "twitter:image:src",
            ])
            if image:
                article["image_url"] = image

        # Extract author
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

        # Extract description as fallback for empty summaries
        if not article.get("summary"):
            desc = _extract_meta(html, [
                "og:description",
                "description",
                "twitter:description",
            ])
            if desc:
                article["summary"] = desc[:500]

    except Exception:
        pass  # Graceful failure — metadata is optional

    return article


def enrich_articles(articles: list[dict], max_workers: int = 6) -> list[dict]:
    """Enrich a list of articles with og:image and author metadata.

    Uses thread pool for parallel fetching. Only call on filtered articles
    to minimize request count.

    Args:
        articles: List of article dicts (mutated in place).
        max_workers: Number of concurrent fetch threads.

    Returns:
        The same list with image_url and author fields populated where available.
    """
    if not articles:
        return articles

    print(f"  [Meta] Fetching metadata for {len(articles)} articles...")
    enriched_count = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_fetch_metadata, art): art for art in articles}
        for future in as_completed(futures):
            art = future.result()
            if art.get("image_url") or art.get("author"):
                enriched_count += 1

    print(f"  [Meta] Enriched {enriched_count}/{len(articles)} articles with metadata")
    return articles
