"""ElevenLabs text-to-speech for the on-call phone alert.

Audio is generated when the call is answered (the script is live data) and cached by
content, so 'press 2 to repeat' and repeated phrases cost nothing extra. Any failure or a
slow response returns None, and the caller falls back to the telephony provider's voice:
a nicer voice must never cost us the call.
"""

import hashlib
import logging

import httpx

from app.core.config import get_settings

log = logging.getLogger(__name__)

TIMEOUT_SECONDS = 4  # Vobiz waits 10s for the answer XML; leave room for the rest
MAX_CACHED = 64
_cache: dict[str, bytes] = {}


def configured() -> bool:
    return bool(get_settings().elevenlabs_api_key)


def cached(key: str) -> bytes | None:
    return _cache.get(key)


async def synthesize(text: str) -> str | None:
    """Speak `text`; returns a cache key for the MP3, or None to fall back."""
    if not configured():
        return None
    s = get_settings()
    key = hashlib.sha256(f"{s.elevenlabs_voice_id}|{s.elevenlabs_model}|{text}".encode())
    key = key.hexdigest()[:32]
    if key in _cache:
        return key
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as http:
            resp = await http.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{s.elevenlabs_voice_id}",
                params={"output_format": "mp3_22050_32"},
                headers={"xi-api-key": s.elevenlabs_api_key},
                json={"text": text, "model_id": s.elevenlabs_model},
            )
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        log.warning("elevenlabs failed, falling back", extra={"error": str(exc)[:200]})
        return None
    if len(_cache) >= MAX_CACHED:
        _cache.pop(next(iter(_cache)))
    _cache[key] = resp.content
    return key
