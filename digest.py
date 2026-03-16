"""
Digest Generator
Produces a markdown file and a standalone HTML report from scored articles.
Articles are sorted by score (highest first) with topic category tags.
"""

import os
from datetime import date

from jinja2 import Environment, FileSystemLoader


def generate_markdown(articles: list[dict], output_dir: str) -> str:
    """Write a daily markdown digest sorted by score with topic tags.

    Returns:
        Path to the written file.
    """
    today = date.today()
    filename = f"{today.isoformat()}_digest.md"
    filepath = os.path.join(output_dir, filename)

    sorted_articles = sorted(articles, key=lambda a: a.get("score", 0), reverse=True)

    lines = [
        f"# RME News Scout -- {today.strftime('%B %d, %Y')}",
        "",
        f"**{len(articles)} articles** passed the relevance filter today.",
        "",
    ]

    for art in sorted_articles:
        score = art.get("score", "?")
        topic = art.get("topic", "Other")
        rationale = art.get("rationale", "")
        lines.append(f"- **[{art['title']}]({art['url']})** [{topic}] (score: {score}/5)")
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

    sorted_articles = sorted(articles, key=lambda a: a.get("score", 0), reverse=True)

    html = template.render(
        date=date.today().strftime("%B %d, %Y"),
        total=len(articles),
        articles=sorted_articles,
    )

    today = date.today()
    filename = f"{today.isoformat()}_digest.html"
    filepath = os.path.join(output_dir, filename)

    os.makedirs(output_dir, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"  [Digest] HTML report saved to {filepath}")
    return filepath
