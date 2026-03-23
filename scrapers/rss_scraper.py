"""
RSS Feed Scraper
Pulls articles from all configured RSS feeds using feedparser.
Only includes articles published within the last 48 hours.
"""

import re
import feedparser
from html import unescape
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

MAX_AGE_HOURS = 48


def _parse_date(date_str: str) -> datetime | None:
    """Try to parse an RSS date string into a timezone-aware datetime."""
    if not date_str:
        return None
    try:
        return parsedate_to_datetime(date_str)
    except Exception:
        pass
    # Try common ISO formats
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(date_str, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    return None


def scrape_rss_feeds(feeds: list[dict]) -> list[dict]:
    """Fetch recent articles from each RSS feed in the config.

    Args:
        feeds: List of dicts with 'name' and 'url' keys.

    Returns:
        List of article dicts published within the last MAX_AGE_HOURS.
    """
    articles = []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=MAX_AGE_HOURS)
    skipped_old = 0

    for feed_cfg in feeds:
        name = feed_cfg["name"]
        url = feed_cfg["url"]

        try:
            parsed = feedparser.parse(url)
        except Exception as e:
            print(f"  [RSS] Error fetching {name}: {e}")
            continue

        if parsed.bozo and not parsed.entries:
            print(f"  [RSS] Warning: {name} returned no entries (bozo={parsed.bozo})")
            continue

        for entry in parsed.entries:
            # Get published date
            date_str = ""
            if hasattr(entry, "published"):
                date_str = entry.published
            elif hasattr(entry, "updated"):
                date_str = entry.updated

            # Filter out old articles
            pub_date = _parse_date(date_str)
            if pub_date and pub_date < cutoff:
                skipped_old += 1
                continue

            summary = ""
            if hasattr(entry, "summary"):
                summary = entry.summary
            elif hasattr(entry, "description"):
                summary = entry.description

            # Strip HTML tags from summary
            if summary:
                summary = unescape(re.sub(r"<[^>]+>", "", summary)).strip()

            # Extract author if available in feed
            author = ""
            if hasattr(entry, "author"):
                author = entry.author
            elif hasattr(entry, "authors") and entry.authors:
                author = entry.authors[0].get("name", "")

            # For Google News feeds, the <source> tag has the real article URL
            # and publisher name (e.g. source.href = "https://apnews.com/...",
            # source.title = "AP News")
            article_url = entry.get("link", "")
            site_name = ""
            source_entry = entry.get("source", {})
            if source_entry:
                real_url = source_entry.get("href", "")
                if real_url:
                    article_url = real_url
                publisher = source_entry.get("title", "")
                if publisher:
                    site_name = publisher

            articles.append({
                "title": entry.get("title", "(no title)"),
                "url": article_url,
                "source": name,
                "site_name": site_name,
                "summary": summary[:500] if summary else "",
                "published": pub_date.strftime("%b %d, %I:%M %p") if pub_date else "",
                "author": author,
            })

    print(f"  [RSS] Collected {len(articles)} recent articles from {len(feeds)} feeds ({skipped_old} older than {MAX_AGE_HOURS}h skipped)")
    return articles
