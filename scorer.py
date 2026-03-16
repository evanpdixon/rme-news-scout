"""
Relevance Scorer
Sends articles to Claude CLI in batches and gets 1–5 relevance scores
for a ham radio / emergency-preparedness audience.
Uses `claude -p` (Claude Code CLI) — works with Claude Max, no API key needed.
"""

import json
import os
import subprocess
import shutil

BATCH_SIZE = 10

SCORING_PROMPT = """\
You are a relevance scorer for Radio Made Easy (RME), a company focused on
ham radio, GMRS, emergency communications, off-grid preparedness, and
infrastructure resilience.

For each article below, rate its relevance from 1 to 5:
  5 = Directly about ham radio, GMRS, emergency comms, or RME's core audience
  4 = Strongly related (power grid failures, major outages, FCC policy, preparedness)
  3 = Moderately related (natural disasters, infrastructure news, survival gear)
  2 = Loosely related (general tech, tangentially relevant)
  1 = Not relevant to RME's audience

Also assign each article to ONE topic category:
  - Ham Radio
  - GMRS
  - Emergency Comms
  - Outages & Infrastructure
  - Preparedness & Off-Grid
  - FCC & Policy
  - Other

Respond with ONLY a JSON array. No markdown fences, no explanation.
Each element must be: {{"index": <0-based>, "score": <1-5>, "topic": "<category>", "rationale": "<one sentence>"}}

Articles to score:

{articles}"""


def _call_claude(prompt: str) -> str:
    """Call the Claude CLI with a prompt and return the response text."""
    claude_path = shutil.which("claude")
    if not claude_path:
        raise RuntimeError(
            "Claude CLI not found on PATH. "
            "Install it or add it to PATH: https://docs.anthropic.com/en/docs/claude-code"
        )

    # Unset CLAUDECODE env var to allow running from within a Claude Code session
    env = {**os.environ}
    env.pop("CLAUDECODE", None)

    result = subprocess.run(
        [claude_path, "-p", prompt],
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )

    if result.returncode != 0:
        raise RuntimeError(f"Claude CLI error: {result.stderr.strip()}")

    return result.stdout.strip()


def score_articles(articles: list[dict], config: dict) -> list[dict]:
    """Score each article for relevance using Claude CLI.

    Args:
        articles: List of article dicts (must have 'title' and 'summary').
        config: Config dict (unused with CLI mode, kept for interface compat).

    Returns:
        The same articles, each annotated with 'score' and 'rationale'.
    """
    if not articles:
        return articles

    scored = []

    for batch_start in range(0, len(articles), BATCH_SIZE):
        batch = articles[batch_start : batch_start + BATCH_SIZE]

        articles_text = ""
        for i, art in enumerate(batch):
            articles_text += (
                f"[{i}] {art['title']}\n"
                f"    Source: {art['source']}\n"
                f"    Summary: {art.get('summary', '(none)')[:300]}\n\n"
            )

        prompt = SCORING_PROMPT.format(articles=articles_text)

        try:
            text = _call_claude(prompt)

            # Extract JSON if wrapped in markdown code blocks
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

            scores = json.loads(text)
            score_map = {s["index"]: s for s in scores}

            for i, art in enumerate(batch):
                info = score_map.get(i, {"score": 3, "topic": "Other", "rationale": "No score returned"})
                art["score"] = info["score"]
                art["topic"] = info.get("topic", "Other")
                art["rationale"] = info.get("rationale", "")
                scored.append(art)

        except Exception as e:
            print(f"  [Scorer] Error scoring batch starting at {batch_start}: {e}")
            # Default unscored articles to 3 so they aren't silently dropped
            for art in batch:
                art["score"] = 3
                art["topic"] = "Other"
                art["rationale"] = f"Scoring failed: {e}"
                scored.append(art)

    print(f"  [Scorer] Scored {len(scored)} articles")
    return scored


def filter_by_score(articles: list[dict], min_score: int) -> list[dict]:
    """Keep only articles at or above the minimum relevance score."""
    kept = [a for a in articles if a.get("score", 0) >= min_score]
    dropped = len(articles) - len(kept)
    print(f"  [Scorer] Kept {len(kept)} articles (dropped {dropped} below score {min_score})")
    return kept
