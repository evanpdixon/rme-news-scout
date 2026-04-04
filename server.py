"""RME News Scout — serves HTML reports with on-demand audio via FastAPI."""

import os
import re
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn

APP_DIR = Path(__file__).parent
load_dotenv(APP_DIR / ".env")
OUTPUT_DIR = APP_DIR / "output"

app = FastAPI()


@app.get("/")
async def index():
    """Dynamic archive listing all reports, most recent first."""
    html_files = sorted(OUTPUT_DIR.glob("*_digest.html"), reverse=True)
    if not html_files:
        return HTMLResponse("<h1>No reports yet</h1>")

    items = []
    for f in html_files[:60]:
        date_str = f.stem.replace("_digest", "")
        size_kb = round(f.stat().st_size / 1024)
        mp3_exists = (OUTPUT_DIR / f"{date_str}_digest.mp3").exists()
        audio_badge = ' <span style="color:#4ca854;font-size:11px;">&#9654; audio</span>' if mp3_exists else ""
        items.append(f'''<li class="report-item">
          <a href="/reports/{f.name}">
            <div class="report-date">{date_str}{audio_badge}</div>
            <div class="report-meta">{size_kb} KB report</div>
          </a>
        </li>''')

    html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>RME News Scout — All Reports</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: 'Segoe UI', system-ui, sans-serif; background: #0a0a0a; color: #e0e0e0; min-height: 100vh; padding: 32px 20px; }}
  h1 {{ color: #d4a843; font-size: 24px; margin-bottom: 4px; }}
  .subtitle {{ color: #888; font-size: 14px; margin-bottom: 32px; }}
  .reports {{ list-style: none; max-width: 600px; }}
  .report-item {{
    border: 1px solid #262626; border-radius: 12px;
    margin-bottom: 10px; background: #161616;
    transition: border-color 0.15s;
  }}
  .report-item:hover {{ border-color: #d4a843; }}
  .report-item a {{
    display: block; padding: 16px 20px;
    text-decoration: none; color: inherit;
  }}
  .report-date {{ color: #d4a843; font-size: 16px; font-weight: 600; margin-bottom: 4px; }}
  .report-meta {{ color: #555; font-size: 12px; }}
</style></head>
<body>
  <h1>RME News Scout</h1>
  <div class="subtitle">{len(html_files)} report{"s" if len(html_files) != 1 else ""} archived</div>
  <ul class="reports">{"".join(items)}</ul>
</body></html>"""
    return HTMLResponse(html)


@app.get("/latest")
async def latest():
    html_files = sorted(OUTPUT_DIR.glob("*_digest.html"), reverse=True)
    if html_files:
        return RedirectResponse(f"/reports/{html_files[0].name}")
    return {"message": "No reports found."}


# ── On-Demand Audio ──────────────────────────────────────────────────────────

class AudioRequest(BaseModel):
    date: str


def _extract_text_from_html(html_path: Path) -> str:
    """Strip HTML tags to get plain text for summarization."""
    text = html_path.read_text(encoding="utf-8")
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL)
    text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:6000]


def _summarize_for_audio(report_text: str, report_type: str) -> str:
    """Use Haiku to create a spoken summary of a report."""
    client = anthropic.Anthropic()
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=800,
        system=f"""You are Callie on Comms, a concise business briefing voice. Create a spoken audio summary of this {report_type} report.
Rules:
- 200-400 words, conversational tone
- Start with "Here's your {report_type} summary."
- Highlight the top 3-5 most important items
- No markdown, no bullet points — write for speech
- Spell out abbreviations on first use
- End with a brief takeaway""",
        messages=[{"role": "user", "content": report_text}],
    )
    return resp.content[0].text.strip()


@app.post("/api/generate-audio")
async def generate_audio_endpoint(data: AudioRequest):
    from tts import generate_audio

    html_path = OUTPUT_DIR / f"{data.date}_digest.html"
    mp3_path = OUTPUT_DIR / f"{data.date}_digest.mp3"

    if mp3_path.exists():
        return {"status": "exists", "message": "Audio already generated."}
    if not html_path.exists():
        raise HTTPException(status_code=404, detail=f"No report for {data.date}")

    try:
        report_text = _extract_text_from_html(html_path)
        script = _summarize_for_audio(report_text, "news scout")
        generate_audio(script, str(mp3_path))
        return {"status": "ok", "message": "Audio generated."}
    except Exception as e:
        print(f"[audio] Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate audio")


@app.get("/audio/{filename}")
async def serve_audio(filename: str):
    from fastapi.responses import FileResponse
    path = OUTPUT_DIR / filename
    if not path.exists():
        raise HTTPException(status_code=404)
    return FileResponse(str(path), media_type="audio/mpeg")


AUDIO_INJECT_JS = """
<div id="rme-audio-bar" style="position:fixed;bottom:0;left:0;right:0;background:#161616;border-top:1px solid #262626;padding:12px 16px;z-index:999;display:flex;align-items:center;gap:10px;justify-content:center;">
  <div id="rme-audio-container"></div>
</div>
<script>
(function() {
  var m = location.pathname.match(/\\/reports\\/(\\d{4}-\\d{2}-\\d{2})_digest\\.html/);
  if (!m) return;
  var date = m[1];
  var c = document.getElementById('rme-audio-container');
  // Check if audio exists
  fetch('/audio/' + date + '_digest.mp3', {method:'HEAD'}).then(function(r) {
    if (r.ok) {
      c.innerHTML = '<audio controls preload="auto" src="/audio/' + date + '_digest.mp3" style="height:40px;"></audio>';
    } else {
      c.innerHTML = '<button id="genBtn" style="padding:10px 24px;border-radius:10px;border:1px solid #d4a843;background:transparent;color:#d4a843;font-size:13px;font-weight:600;cursor:pointer;font-family:inherit;">Generate Audio Summary</button>';
      document.getElementById('genBtn').onclick = function() {
        this.disabled = true; this.textContent = 'Generating...';
        fetch('/api/generate-audio', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({date:date})})
          .then(function(r){return r.json()}).then(function(d) {
            if (d.status === 'ok' || d.status === 'exists') {
              c.innerHTML = '<audio controls autoplay preload="auto" src="/audio/' + date + '_digest.mp3" style="height:40px;"></audio>';
            } else { document.getElementById('genBtn').textContent = 'Failed'; }
          }).catch(function() { document.getElementById('genBtn').textContent = 'Failed'; });
      };
    }
  });
  document.body.style.paddingBottom = '70px';
})();
</script>
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

class AudioInjectMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/reports/") and request.url.path.endswith("_digest.html"):
            body = b""
            async for chunk in response.body_iterator:
                body += chunk
            html = body.decode("utf-8")
            html = html.replace("</body>", AUDIO_INJECT_JS + "</body>")
            return Response(content=html, status_code=200, media_type="text/html")
        return response

app.add_middleware(AudioInjectMiddleware)
app.mount("/reports", StaticFiles(directory=str(OUTPUT_DIR)), name="reports")

if __name__ == "__main__":
    uvicorn.run("server:app", host="100.77.39.93", port=8804)
