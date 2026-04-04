# RME News Scout

Automated ham radio news aggregation system. Scrapes RSS feeds, deduplicates URLs, scores articles using Claude AI for relevance, filters by threshold, enriches with metadata, generates HTML/Markdown digests, and sends push notifications via ntfy.sh.

## Tech Stack
- Python 3, PyYAML, feedparser, BeautifulSoup4, httpx
- Jinja2 (templates), Anthropic API (scoring)
- ntfy.sh (push notifications)

## Structure
- `main.py` — Orchestrator (scrape > dedup > score > filter > generate > notify)
- `scrapers/` — Source-specific scrapers
- `dedup.py` — URL deduplication with seen tracking
- `scorer.py` — Claude-powered relevance scoring (1-5 scale)
- `digest.py` — HTML/Markdown report generation
- `metadata.py` — Article enrichment (OG image, author extraction)
- `config.yaml` — Source list, scoring rules, output paths
- `seen_urls.json` — Persistent dedup tracking

## Key Patterns
- Stateful pipeline with tracking files
- CI-aware config switching (config.ci.yaml vs config.yaml)
- Score-based filtering with configurable thresholds
- Chronological workflow with clear logging at each stage

## Running
```bash
python main.py
```
