"""Text-to-Speech via ElevenLabs API (shared with rme-daily-briefing)."""

import os
import httpx


def generate_audio(text: str, output_path: str) -> str:
    voice_id = os.environ.get("ELEVENLABS_VOICE_ID", "")
    api_key = os.environ.get("ELEVENLABS_API_KEY", "")
    if not voice_id or not api_key:
        raise RuntimeError("ELEVENLABS_VOICE_ID and ELEVENLABS_API_KEY must be set")

    resp = httpx.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
        headers={"xi-api-key": api_key, "Content-Type": "application/json", "Accept": "audio/mpeg"},
        params={"output_format": "mp3_22050_32"},
        json={"text": text, "model_id": "eleven_flash_v2_5", "voice_settings": {"stability": 0.5, "similarity_boost": 0.75, "speed": 1.2}},
        timeout=60,
    )
    resp.raise_for_status()
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(resp.content)
    print(f"  [TTS] Generated {os.path.getsize(output_path) / 1024:.0f} KB audio -> {output_path}")
    return output_path
