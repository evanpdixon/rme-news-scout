"""
Web Scraper
Fetches and parses curated web pages (ARRL News, Downdetector).
"""

import httpx
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "RMENewsScout/1.0 (news digest bot)",
}


def scrape_web_sources(sources: list[dict]) -> list[dict]:
    """Scrape configured web sources for article links.

    Args:
        sources: List of dicts with 'name' and 'url' keys.

    Returns:
        List of article dicts.
    """
    articles = []

    for source in sources:
        name = source["name"]
        url = source["url"]

        try:
            timeout = 60 if "fcc.gov" in url else 20
            resp = httpx.get(url, headers=HEADERS, timeout=timeout, follow_redirects=True)
            resp.raise_for_status()
        except Exception as e:
            print(f"  [Web] Error fetching {name}: {e}")
            continue

        soup = BeautifulSoup(resp.text, "html.parser")

        if "arrl.org" in url:
            articles.extend(_parse_arrl(soup, name))
        elif "downdetector" in url:
            articles.extend(_parse_downdetector(soup, name))
        elif "fcc.gov" in url and "enforcement" in url:
            articles.extend(_parse_fcc_enforcement(soup, name))
        else:
            print(f"  [Web] No parser defined for {name}, skipping")

    print(f"  [Web] Collected {len(articles)} items from {len(sources)} web sources")
    return articles


def _parse_arrl(soup: BeautifulSoup, source_name: str) -> list[dict]:
    """Extract news article links from the ARRL news page."""
    articles = []

    for link in soup.select("a[href*='/news/view/']"):
        title = link.get_text(strip=True)
        href = link.get("href", "")
        if not title or not href:
            continue

        if not href.startswith("http"):
            href = f"https://www.arrl.org{href}"

        articles.append({
            "title": title,
            "url": href,
            "source": source_name,
            "summary": "",
            "published": "",
        })

    return articles


def _parse_fcc_enforcement(soup: BeautifulSoup, source_name: str) -> list[dict]:
    """Extract enforcement actions from the FCC enforcement bureau page."""
    articles = []

    # FCC enforcement pages use various structures — try multiple selectors
    # Look for links containing enforcement-related paths
    selectors = [
        "a[href*='/document/']",
        "a[href*='/enforcement/']",
        ".views-row a",
        ".view-content a",
        "td a[href]",
    ]

    seen_hrefs = set()
    for selector in selectors:
        for link in soup.select(selector):
            title = link.get_text(strip=True)
            href = link.get("href", "")

            if not title or not href or len(title) < 10:
                continue
            if href in seen_hrefs:
                continue
            seen_hrefs.add(href)

            if not href.startswith("http"):
                href = f"https://www.fcc.gov{href}"

            # Skip navigation/menu links
            if any(skip in href.lower() for skip in [
                "/about", "/consumers", "/login", "/search", "#",
                "javascript:", "/rss", "/tags/"
            ]):
                continue

            articles.append({
                "title": title,
                "url": href,
                "source": source_name,
                "summary": "FCC Enforcement Bureau action",
                "published": "",
            })

    return articles


def _parse_downdetector(soup: BeautifulSoup, source_name: str) -> list[dict]:
    """Extract trending outage entries from Downdetector."""
    articles = []

    for item in soup.select("a.text-link"):
        title = item.get_text(strip=True)
        href = item.get("href", "")
        if not title or not href:
            continue

        if not href.startswith("http"):
            href = f"https://downdetector.com{href}"

        articles.append({
            "title": f"Outage: {title}",
            "url": href,
            "source": source_name,
            "summary": "Trending outage report on Downdetector",
            "published": "",
        })

    return articles
