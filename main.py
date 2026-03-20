"""
RME News Scout -- Main Orchestrator
Scrape -> Deduplicate -> Score -> Filter -> Generate HTML Report -> Notify
"""

import os
import sys
import webbrowser
import yaml
from datetime import datetime

from scrapers import run_all_scrapers
from dedup import load_seen_urls, save_seen_urls, deduplicate
from scorer import score_articles, filter_by_score
from digest import generate_markdown, generate_html_report
from notifier import send_notification


def load_config() -> dict:
    """Load and return the YAML configuration.
    Uses config.ci.yaml in CI, config.yaml locally."""
    path = "config.ci.yaml" if os.environ.get("CI") else "config.yaml"
    if not os.path.exists(path):
        print(f"ERROR: {path} not found.")
        sys.exit(1)
    with open(path, "r") as f:
        return yaml.safe_load(f)


def main():
    # Ensure working directory is the script's directory (critical for Task Scheduler)
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    start = datetime.now()
    print(f"\n{'=' * 50}")
    print(f"  RME News Scout -- {start.strftime('%Y-%m-%d %H:%M')}")
    print(f"{'=' * 50}\n")

    # 1. Load config
    config = load_config()
    settings = config.get("settings", {})
    output_dir = settings.get("output_dir", "output")
    # In CI, always use local output directory
    if os.environ.get("CI"):
        output_dir = "output"
    min_score = settings.get("min_relevance_score", 3)
    seen_file = settings.get("seen_urls_file", "seen_urls.json")

    # 2. Load seen URLs
    seen = load_seen_urls(seen_file)
    print(f"  Loaded {len(seen)} previously seen URLs\n")

    # 3. Scrape all sources
    print("--- Scraping ---")
    raw_articles = run_all_scrapers(config)

    if not raw_articles:
        print("\n  No articles collected from any source. Exiting.")
        return

    # 4. Deduplicate
    print("\n--- Deduplication ---")
    new_articles = deduplicate(raw_articles, seen)

    if not new_articles:
        print("\n  No new articles today. Exiting.")
        save_seen_urls(seen_file, seen)
        return

    # 5. Score with Claude CLI
    print("\n--- Relevance Scoring ---")
    scored = score_articles(new_articles, config)

    # 6. Filter by minimum score
    filtered = filter_by_score(scored, min_score)

    if not filtered:
        print("\n  No articles met the relevance threshold. Exiting.")
        save_seen_urls(seen_file, seen)
        return

    # 7. Generate reports
    print("\n--- Generating Reports ---")
    md_path = generate_markdown(filtered, output_dir)
    html_path = generate_html_report(filtered, output_dir)

    # 8. Save seen URLs
    save_seen_urls(seen_file, seen)
    print(f"\n  Updated {seen_file} ({len(seen)} URLs tracked)")

    # 9. Send push notification via ntfy with link to hosted report
    ntfy_cfg = config.get("ntfy")
    if ntfy_cfg and ntfy_cfg.get("topic"):
        top_articles = sorted(filtered, key=lambda a: a.get("score", 0), reverse=True)[:5]
        body_lines = [f"{len(filtered)} articles in today's digest:\n"]
        for art in top_articles:
            body_lines.append(f"  [{art.get('score', '?')}/5] {art['title']}")
        if len(filtered) > 5:
            body_lines.append(f"  ... and {len(filtered) - 5} more")

        # Build report URL: GitHub Pages in CI, empty locally
        report_url = ""
        pages_base = config.get("settings", {}).get("pages_base_url", "")
        if pages_base and html_path:
            report_url = f"{pages_base}/{os.path.basename(html_path)}"

        send_notification(
            topic=ntfy_cfg["topic"],
            title=f"RME News Scout -- {len(filtered)} articles",
            message="\n".join(body_lines),
            report_url=report_url,
            server=ntfy_cfg.get("server", "https://ntfy.sh"),
        )

    # 10. Open HTML report in browser (when run interactively)
    if sys.stdout.isatty():
        abs_html = os.path.abspath(html_path)
        webbrowser.open(f"file:///{abs_html}")

    # 11. Summary
    elapsed = (datetime.now() - start).total_seconds()
    print(f"\n{'=' * 50}")
    print(f"  Done in {elapsed:.1f}s")
    print(f"  {len(raw_articles)} scraped -> {len(new_articles)} new -> {len(filtered)} in digest")
    print(f"  Markdown : {md_path}")
    print(f"  HTML     : {html_path}")
    print(f"{'=' * 50}\n")


if __name__ == "__main__":
    main()
