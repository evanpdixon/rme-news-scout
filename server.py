"""RME News Scout — serves HTML reports via FastAPI."""

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

APP_DIR = Path(__file__).parent
OUTPUT_DIR = APP_DIR / "output"

app = FastAPI()


@app.get("/")
async def index():
    index_path = OUTPUT_DIR / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return {"message": "No reports generated yet. Run main.py first."}


@app.get("/latest")
async def latest():
    """Redirect to the most recent report."""
    html_files = sorted(OUTPUT_DIR.glob("*_digest.html"), reverse=True)
    if html_files:
        return RedirectResponse(f"/reports/{html_files[0].name}")
    return {"message": "No reports found."}


app.mount("/reports", StaticFiles(directory=str(OUTPUT_DIR)), name="reports")


if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8804)
