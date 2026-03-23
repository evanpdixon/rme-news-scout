"""
Digest Generator
Produces a markdown file and a standalone HTML report from scored articles.
Articles are grouped by topic category and sorted by score within each group.
"""

import glob
import os
import re
from collections import OrderedDict
from datetime import date, datetime

from jinja2 import Environment, FileSystemLoader

# Ordered list of all topic categories — defines section order in reports
TOPIC_ORDER = [
    "RME Mention",
    "Ham Radio",
    "GMRS",
    "Emergency Comms",
    "Outages & Infrastructure",
    "Preparedness & Off-Grid",
    "FCC & Policy",
    "FCC Enforcement",
    "Other",
]


def _group_by_topic(articles: list[dict]) -> OrderedDict:
    """Group articles by topic category, sorted by score within each group."""
    grouped = OrderedDict()
    for topic in TOPIC_ORDER:
        grouped[topic] = []

    for art in articles:
        topic = art.get("topic", "Other")
        if topic not in grouped:
            grouped[topic] = []
        grouped[topic].append(art)

    # Sort each group by score descending
    for topic in grouped:
        grouped[topic].sort(key=lambda a: a.get("score", 0), reverse=True)

    return grouped


def generate_markdown(articles: list[dict], output_dir: str) -> str:
    """Write a daily markdown digest sorted by score with topic tags.

    Returns:
        Path to the written file.
    """
    today = date.today()
    filename = f"{today.isoformat()}_digest.md"
    filepath = os.path.join(output_dir, filename)

    grouped = _group_by_topic(articles)

    lines = [
        f"# RME News Scout -- {today.strftime('%B %d, %Y')}",
        "",
        f"**{len(articles)} articles** passed the relevance filter today.",
        "",
    ]

    for topic, topic_articles in grouped.items():
        lines.append(f"## {topic}")
        lines.append("")
        if not topic_articles:
            lines.append("*No articles found*")
            lines.append("")
            continue
        for art in topic_articles:
            score = art.get("score", "?")
            rationale = art.get("rationale", "")
            lines.append(f"- **[{art['title']}]({art['url']})** (score: {score}/5)")
            if rationale:
                lines.append(f"  > {rationale}")
            if art.get("summary"):
                lines.append(f"  {art['summary'][:200]}")
            lines.append("")

    os.makedirs(output_dir, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"  [Digest] Markdown saved to {filepath}")
    return filepath


def generate_html_report(articles: list[dict], output_dir: str) -> str:
    """Render a standalone HTML report sorted by score with topic tags.

    Returns:
        Path to the written HTML file.
    """
    template_dir = os.path.join(os.path.dirname(__file__), "templates")
    env = Environment(loader=FileSystemLoader(template_dir), autoescape=True)
    template = env.get_template("report.html")

    grouped = _group_by_topic(articles)

    html = template.render(
        date=date.today().strftime("%B %d, %Y"),
        total=len(articles),
        grouped=grouped,
    )

    today = date.today()
    filename = f"{today.isoformat()}_digest.html"
    filepath = os.path.join(output_dir, filename)

    os.makedirs(output_dir, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"  [Digest] HTML report saved to {filepath}")
    return filepath


def generate_index(output_dir: str) -> str:
    """Generate an index.html listing all historical digest reports.

    Scans output_dir for *_digest.html files and renders a linked archive page.

    Returns:
        Path to the written index.html file.
    """
    template_dir = os.path.join(os.path.dirname(__file__), "templates")
    env = Environment(loader=FileSystemLoader(template_dir), autoescape=True)
    template = env.get_template("index.html")

    today_iso = date.today().isoformat()

    # Find all digest HTML files
    pattern = os.path.join(output_dir, "*_digest.html")
    files = glob.glob(pattern)

    reports = []
    for fpath in files:
        fname = os.path.basename(fpath)
        # Extract date from filename like 2026-03-23_digest.html
        match = re.match(r"(\d{4}-\d{2}-\d{2})_digest\.html", fname)
        if match:
            date_str = match.group(1)
            try:
                dt = datetime.strptime(date_str, "%Y-%m-%d")
                display_date = dt.strftime("%B %d, %Y")
            except ValueError:
                display_date = date_str
            reports.append({
                "filename": fname,
                "date_str": date_str,
                "display_date": display_date,
                "is_today": date_str == today_iso,
            })

    # Sort newest first
    reports.sort(key=lambda r: r["date_str"], reverse=True)

    html = template.render(reports=reports)

    filepath = os.path.join(output_dir, "index.html")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"  [Digest] Index page saved to {filepath} ({len(reports)} reports)")
    return filepath
