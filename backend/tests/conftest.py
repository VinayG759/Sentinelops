"""Shared test setup: unit tests never reach real third-party services.

`.env` holds real keys for the running app. Without this, a test that exercises the phone
alert would call Sarvam / ElevenLabs for real (network, credits, flakiness). Tests that
want a voice provider opt in by setting the key themselves.
"""

import pytest

from app.core.config import get_settings


@pytest.fixture(autouse=True)
def no_real_voice_providers(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "sarvam_api_key", "")
    monkeypatch.setattr(s, "elevenlabs_api_key", "")
