"""
Relevance Scorer
Scores articles for relevance using the Anthropic API (Haiku) when available,
falling back to Claude CLI for local runs.
"""

import json
import os
import subprocess
import shutil

BATCH_SIZE = 10

SCORING_PROMPT = """\
You are a relevance scorer for Radio Made Easy (RME), a company focused on
ham radio, GMRS, emergency communications, off-grid preparedness, and
infrastructure resilience. RME's website is radiomadeeasy.com.

For each article below, rate its relevance from 1 to 5:
  5 = Directly mentions Radio Made Easy / RadioMadeEasy / radiomadeeasy.com,
      OR is directly about ham radio, GMRS, emergency comms, or RME's core audience
  4 = Strongly related (power grid failures, major outages, FCC enforcement actions,
      FCC policy changes, preparedness)
  3 = Moderately related (natural disasters, infrastructure news, survival gear)
  2 = Loosely related (general tech, tangentially relevant)
  1 = Not relevant to RME's audience

IMPORTANT: Any article that mentions "Radio Made Easy" or "RadioMadeEasy" by name
should ALWAYS score 5, regardless of other content.

Also assign each article to ONE topic category:
  - RME Mention (any direct mention of Radio Made Easy / RadioMadeEasy)
  - Ham Radio
  - GMRS
  - Emergency Comms
  - Outages & Infrastructure
  - Preparedness & Off-Grid
  - FCC & Policy
  - FCC Enforcement
  - Other

Respond with ONLY a JSON array. No markdown fences, no explanation.
Each element must be: {{"index": <0-based>, "score": <1-5>, "topic": "<category>", "rationale": "<one sentence>"}}

Articles to score:

{articles}"""


def _has_api_key() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def _call_api(prompt: str) -> str:
    """Call the Anthropic API directly using the anthropic SDK."""
    import anthropic

    client = anthropic.Anthropic()
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text.strip()


def _call_claude_cli(prompt: str) -> str:
    """Call the Claude CLI with a prompt and return the response text."""
    claude_path = shutil.which("claude")
    if not claude_path:
        raise RuntimeError(
            "Claude CLI not found on PATH. "
            "Install it or add it to PATH: https://docs.anthropic.com/en/docs/claude-code"
        )

    env = {**os.environ}
    env.pop("CLAUDECODE", None)

    # Use "-" to read prompt from stdin (avoids CLI argument truncation on Windows)
    # Normalize Unicode to ASCII-safe text to avoid Windows cp1252 encoding errors
    prompt_safe = prompt.encode("ascii", errors="replace").decode("ascii")
    result = subprocess.run(
        [claude_path, "-p", "-", "--model", "haiku", "--tools", ""],
        input=prompt_safe,
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )

    if result.returncode != 0:
        raise RuntimeError(f"Claude CLI error (rc={result.returncode}): stderr={result.stderr.strip()!r} stdout={result.stdout[:200]!r}")

    output = result.stdout.strip()
    if not output:
        raise RuntimeError(f"Claude CLI returned empty output. stderr={result.stderr[:200]!r}")
    return output


def _call_llm(prompt: str) -> str:
    """Use API if ANTHROPIC_API_KEY is set, otherwise fall back to Claude CLI."""
    if _has_api_key():
        return _call_api(prompt)
    return _call_claude_cli(prompt)


def score_articles(articles: list[dict], config: dict) -> list[dict]:
    """Score each article for relevance.

    Uses the Anthropic API (Haiku) when ANTHROPIC_API_KEY is set,
    otherwise falls back to Claude CLI.
    """
    if not articles:
        return articles

    mode = "API (Haiku)" if _has_api_key() else "CLI"
    print(f"  [Scorer] Using {mode}")

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
            text = _call_llm(prompt)

            # Extract JSON array from response (handles markdown fences, surrounding text, etc.)
            import re
            # Try to find a JSON array in the response
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            # Find the first [ ... ] block in the text
            match = re.search(r"\[.*\]", text, re.DOTALL)
            if match:
                text = match.group(0)

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
