"""ElevenLabs voice for the phone alert: plays when available, falls back when not."""

import httpx
import pytest
import respx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.integrations.elevenlabs import tts
from app.integrations.vobiz import calls

URL = "https://api.elevenlabs.io/v1/text-to-speech/voice-1"


@pytest.fixture(autouse=True)
def settings(monkeypatch):
    s = tts.get_settings()
    monkeypatch.setattr(s, "elevenlabs_api_key", "k")
    monkeypatch.setattr(s, "elevenlabs_voice_id", "voice-1")
    monkeypatch.setattr(tts, "_cache", {})


@respx.mock
async def test_synthesize_caches_the_audio_so_repeats_are_free():
    route = respx.post(URL).mock(return_value=httpx.Response(200, content=b"ID3mp3"))
    key = await tts.synthesize("hello")
    assert key and tts.cached(key) == b"ID3mp3"
    assert await tts.synthesize("hello") == key and route.call_count == 1


@respx.mock
async def test_an_empty_voice_line_uses_the_default_voice(monkeypatch):
    monkeypatch.setattr(tts.get_settings(), "elevenlabs_voice_id", "")
    route = respx.post(f"https://api.elevenlabs.io/v1/text-to-speech/{tts.DEFAULT_VOICE_ID}").mock(
        return_value=httpx.Response(200, content=b"ID3"))
    assert await tts.synthesize("hi") and route.called


@respx.mock
async def test_any_failure_returns_none_so_the_call_falls_back():
    respx.post(URL).mock(return_value=httpx.Response(401, json={"detail": "bad key"}))
    assert await tts.synthesize("hello") is None
    respx.post(URL).mock(side_effect=httpx.ReadTimeout("slow"))
    assert await tts.synthesize("hello again") is None


def test_call_plays_elevenlabs_audio_and_serves_it(monkeypatch):
    s = calls.get_settings()
    monkeypatch.setattr(s, "vobiz_webhook_secret", "sec")
    monkeypatch.setattr(s, "public_api_url", "https://t.example")

    async def fake_synth(text):
        tts._cache["abc.mp3"] = b"ID3mp3"
        return "abc.mp3"

    async def script(pid):
        return "SentinelOps alert."

    monkeypatch.setattr(calls.tts, "synthesize", fake_synth)
    monkeypatch.setattr(calls, "script", script)
    app = FastAPI()
    app.include_router(calls.router)
    client = TestClient(app)
    xml = client.post("/api/vobiz/sec/answer/00000000-0000-0000-0000-000000000001").text
    assert "<Gather" in xml and "<Play>https://t.example/api/vobiz/sec/audio/abc.mp3</Play>" in xml
    assert "<Speak" not in xml
    audio = client.get("/api/vobiz/sec/audio/abc.mp3")
    assert audio.status_code == 200 and audio.content == b"ID3mp3"
    assert audio.headers["content-type"] == "audio/mpeg"
    assert client.get("/api/vobiz/wrong/audio/abc.mp3").status_code == 404


@respx.mock
async def test_sarvam_is_tried_first_as_phone_native_wav(monkeypatch):
    import base64

    from app.integrations.sarvam import tts as sarvam

    monkeypatch.setattr(sarvam.get_settings(), "sarvam_api_key", "sk")
    monkeypatch.setattr(sarvam, "_cache", {})
    route = respx.post(sarvam.URL).mock(return_value=httpx.Response(
        200, json={"audios": [base64.b64encode(b"\xff\xf3mp3").decode()]}))
    xml = await calls._voice("SentinelOps alert.")
    assert "<Play>" in xml and route.called
    body = route.calls.last.request.content
    assert b'"language_code":"en-IN"' in body.replace(b" ", b"")
    assert b'"speech_sample_rate":8000' in body.replace(b" ", b"")
    assert b'"output_audio_codec":"wav"' in body.replace(b" ", b"")
    key = xml.split("/audio/")[1].split("</Play>")[0]
    assert key.endswith(".wav") and sarvam.cached(key) == b"\xff\xf3mp3"


@respx.mock
async def test_sarvam_failure_falls_back_to_the_telephony_voice(monkeypatch):
    from app.integrations.sarvam import tts as sarvam

    monkeypatch.setattr(sarvam.get_settings(), "sarvam_api_key", "sk")
    monkeypatch.setattr(sarvam.get_settings(), "elevenlabs_api_key", "")
    monkeypatch.setattr(sarvam, "_cache", {})
    respx.post(sarvam.URL).mock(return_value=httpx.Response(500))
    assert (await calls._voice("hi")).startswith("<Speak")
