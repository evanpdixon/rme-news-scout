"""
YouTube Search Scraper
Searches YouTube for specific terms and extracts video metadata
from the embedded ytInitialData JSON in the HTML response.
"""

import json
import re
import httpx
from datetime import datetime, timedelta, timezone

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

MAX_AGE_HOURS = 48


def scrape_youtube_searches(searches: list[dict]) -> list[dict]:
    """Search YouTube for configured queries and return recent videos.

    Args:
        searches: List of dicts with 'query' key.

    Returns:
        List of article dicts for videos found.
    """
    articles = []
    seen_ids = set()

    for search in searches:
        query = search["query"]
        try:
            results = _search_youtube(query)
            for video in results:
                vid = video.get("video_id", "")
                if vid and vid not in seen_ids:
                    seen_ids.add(vid)
                    articles.append(video)
        except Exception as e:
            print(f"  [YouTube] Error searching '{query}': {e}")

    print(f"  [YouTube] Collected {len(articles)} videos from {len(searches)} searches")
    return articles


def _search_youtube(query: str) -> list[dict]:
    """Fetch YouTube search results and parse ytInitialData."""
    url = f"https://www.youtube.com/results?search_query={_url_encode(query)}&sp=CAISBAgCEAE%253D"
    # sp parameter filters by upload date (last week)

    resp = httpx.get(url, headers=HEADERS, timeout=30, follow_redirects=True)
    resp.raise_for_status()

    # Extract ytInitialData from the HTML
    match = re.search(r"var ytInitialData\s*=\s*({.*?});\s*</script>", resp.text)
    if not match:
        return []

    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError:
        return []

    return _extract_videos(data)


def _extract_videos(data: dict) -> list[dict]:
    """Walk the ytInitialData structure to find video renderers."""
    videos = []

    try:
        contents = (
            data["contents"]["twoColumnSearchResultsRenderer"]
            ["primaryContents"]["sectionListRenderer"]["contents"]
        )
    except (KeyError, TypeError):
        return []

    for section in contents:
        items = (
            section.get("itemSectionRenderer", {})
            .get("contents", [])
        )
        for item in items:
            renderer = item.get("videoRenderer")
            if not renderer:
                continue

            video_id = renderer.get("videoId", "")
            title_runs = renderer.get("title", {}).get("runs", [])
            title = "".join(r.get("text", "") for r in title_runs)

            channel_runs = (
                renderer.get("ownerText", {}).get("runs", [])
            )
            channel = "".join(r.get("text", "") for r in channel_runs)

            # Published time text like "2 days ago", "1 week ago"
            published_text = (
                renderer.get("publishedTimeText", {}).get("simpleText", "")
            )

            # Skip if older than our threshold
            if published_text and not _is_recent(published_text):
                continue

            snippet_runs = (
                renderer.get("detailedMetadataSnippets", [{}])[0]
                .get("snippetText", {}).get("runs", [])
            ) if renderer.get("detailedMetadataSnippets") else []
            snippet = "".join(r.get("text", "") for r in snippet_runs)

            if not video_id or not title:
                continue

            videos.append({
                "title": title,
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "source": f"YouTube - {channel}" if channel else "YouTube",
                "summary": snippet[:500] if snippet else f"YouTube video by {channel}",
                "published": published_text,
            })

    return videos


def _is_recent(text: str) -> bool:
    """Check if a YouTube relative time string is within MAX_AGE_HOURS."""
    text = text.lower().strip()

    # "streamed X ago" -> "X ago"
    text = text.replace("streamed ", "")

    if "just now" in text or "moment" in text:
        return True

    match = re.match(r"(\d+)\s+(second|minute|hour|day|week|month|year)", text)
    if not match:
        return True  # Can't parse, include it

    num = int(match.group(1))
    unit = match.group(2)

    hours_map = {
        "second": 1 / 3600,
        "minute": 1 / 60,
        "hour": 1,
        "day": 24,
        "week": 168,
        "month": 720,
        "year": 8760,
    }

    age_hours = num * hours_map.get(unit, 0)
    return age_hours <= MAX_AGE_HOURS


def _url_encode(query: str) -> str:
    """Simple URL encoding for search query."""
    return query.replace(" ", "+").replace('"', "%22")
