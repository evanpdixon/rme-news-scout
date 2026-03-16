"""
Scrapers package — aggregates all source scrapers.
"""

from scrapers.rss_scraper import scrape_rss_feeds
from scrapers.web_scraper import scrape_web_sources


def run_all_scrapers(config: dict) -> list[dict]:
    """Run every configured scraper and return a combined article list."""
    articles = []

    # RSS feeds
    rss_feeds = config.get("rss_feeds", [])
    if rss_feeds:
        articles.extend(scrape_rss_feeds(rss_feeds))

    # Web sources
    web_sources = config.get("web_sources", [])
    if web_sources:
        articles.extend(scrape_web_sources(web_sources))

    print(f"\n  Total articles collected: {len(articles)}")
    return articles
