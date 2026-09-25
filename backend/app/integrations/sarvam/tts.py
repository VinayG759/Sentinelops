"""Sarvam text-to-speech (bulbul): Indian English voice for the on-call phone alert.

Same contract as the ElevenLabs module: synthesize() returns a cache key for an MP3, or
None on any failure or slow response, and the caller falls back to the next voice.
"""

import base64
import hashlib
import logging

import httpx

from app.core.config import get_settings

log = logging.getLogger(__name__)

URL = "https://api.sarvam.ai/text-to-speech"
TIMEOUT_SECONDS = 6  # measured ~2s; Vobiz waits 10s for the answer XML
MAX_CACHED = 64
_cache: dict[str, bytes] = {}


def configured() -> bool:
    return bool(get_settings().sarvam_api_key.strip())


def cached(key: str) -> bytes | None:
    return _cache.get(key)


async def synthesize(text: str) -> str | None:
    if not configured():
        return None
    s = get_settings()
    speaker = s.sarvam_speaker.strip() or "priya"
    key = hashlib.sha256(f"sarvam|{speaker}|{text}".encode()).hexdigest()[:32]
    if key in _cache:
        return key
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as http:
            resp = await http.post(
                URL,
                headers={"api-subscription-key": s.sarvam_api_key.strip()},
                json={"text": text, "language_code": "en-IN", "model": "bulbul:v3",
                      "speaker": speaker, "output_audio_codec": "mp3",
                      "speech_sample_rate": 22050},
            )
        resp.raise_for_status()
        audio = base64.b64decode(resp.json()["audios"][0])
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
        log.warning("sarvam failed, falling back", extra={"error": str(exc)[:200]})
        return None
    if len(_cache) >= MAX_CACHED:
        _cache.pop(next(iter(_cache)))
    _cache[key] = audio
    return key
