"""
Deduplication
Tracks seen URLs in a JSON file to avoid re-processing articles.
Prunes entries older than 30 days.
"""

import json
import os
from datetime import datetime, timedelta

PRUNE_DAYS = 30


def load_seen_urls(filepath: str) -> dict:
    """Load the seen-URLs dict from disk. Returns empty dict if missing."""
    if not os.path.exists(filepath):
        return {}
    try:
        with open(filepath, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def save_seen_urls(filepath: str, seen: dict) -> None:
    """Write the seen-URLs dict back to disk, pruning old entries first."""
    cutoff = (datetime.now() - timedelta(days=PRUNE_DAYS)).isoformat()
    pruned = {url: date for url, date in seen.items() if date >= cutoff}
    with open(filepath, "w") as f:
        json.dump(pruned, f, indent=2)


def deduplicate(articles: list[dict], seen: dict) -> list[dict]:
    """Remove articles whose URL is already in the seen set.

    Also registers new URLs in the seen dict (caller must save afterward).

    Returns:
        List of new (unseen) articles.
    """
    new_articles = []
    today = datetime.now().isoformat()

    for art in articles:
        url = art.get("url", "")
        if not url or url in seen:
            continue
        seen[url] = today
        new_articles.append(art)

    dupes = len(articles) - len(new_articles)
    print(f"  [Dedup] {len(new_articles)} new articles ({dupes} duplicates skipped)")
    return new_articles
