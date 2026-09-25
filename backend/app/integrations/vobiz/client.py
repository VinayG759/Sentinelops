"""Vobiz voice API: place an outbound call whose script is fetched from our answer URL."""

import logging

import httpx

from app.core.config import get_settings

log = logging.getLogger(__name__)
BASE = "https://api.vobiz.ai/api/v1"


class VobizError(Exception):
    pass


def configured() -> bool:
    s = get_settings()
    return all((s.vobiz_auth_id, s.vobiz_auth_token, s.vobiz_from_number, s.oncall_phone,
                s.vobiz_webhook_secret, s.public_api_url))


def webhook_base() -> str:
    s = get_settings()
    return f"{s.public_api_url.rstrip('/')}/api/vobiz/{s.vobiz_webhook_secret}"


async def place_call(to: str, answer_url: str, hangup_url: str) -> str:
    """Start a call; Vobiz fetches `answer_url` for the script once it is answered."""
    s = get_settings()
    async with httpx.AsyncClient(timeout=15) as http:
        resp = await http.post(
            f"{BASE}/Account/{s.vobiz_auth_id}/Call/",
            headers={"X-Auth-ID": s.vobiz_auth_id, "X-Auth-Token": s.vobiz_auth_token},
            json={"from": s.vobiz_from_number, "to": to, "answer_url": answer_url,
                  "answer_method": "POST", "hangup_url": hangup_url, "time_limit": 180},
        )
    log.info("vobiz call", extra={"status": resp.status_code})
    if resp.status_code >= 400:
        raise VobizError(f"HTTP {resp.status_code}: {resp.text[:200]}")
    return resp.json().get("request_uuid", "")
