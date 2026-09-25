"""Freshservice API v2 client: Basic auth with the agent API key, retries, one log per call.

Only this module talks to Freshservice. Everything is async; failures raise
FreshserviceError after the retries are spent, and callers decide what that means.
"""

import asyncio
import logging

import httpx

from app.core.config import get_settings

log = logging.getLogger(__name__)

ATTEMPTS = 3
TIMEOUT_SECONDS = 15
MAX_RETRY_AFTER_SECONDS = 10


class FreshserviceError(Exception):
    """A Freshservice call failed after retries (or was refused outright)."""


def configured() -> bool:
    s = get_settings()
    return bool(s.freshservice_domain and s.freshservice_api_key)


def ticket_url(ticket_id: int) -> str:
    return f"https://{get_settings().freshservice_domain}/a/tickets/{ticket_id}"


async def request(method: str, path: str, json: dict | None = None) -> dict:
    """One API call. Retries rate limits (429, honouring Retry-After) and server errors."""
    s = get_settings()
    url = f"https://{s.freshservice_domain}/api/v2{path}"
    last = "no attempt made"
    for attempt in range(1, ATTEMPTS + 1):
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as http:
                resp = await http.request(method, url, json=json,
                                          auth=(s.freshservice_api_key, "X"))
        except httpx.HTTPError as exc:
            last = f"{type(exc).__name__}: {exc}"
            log.warning("freshservice call failed", extra={"method": method, "path": path,
                                                          "attempt": attempt, "error": last})
            await asyncio.sleep(attempt)
            continue
        log.info("freshservice call", extra={"method": method, "path": path,
                                             "status": resp.status_code, "attempt": attempt})
        if resp.status_code < 400:
            return resp.json() if resp.content else {}
        last = f"HTTP {resp.status_code}: {resp.text[:300]}"
        if resp.status_code == 429:
            wait = min(float(resp.headers.get("Retry-After", attempt)), MAX_RETRY_AFTER_SECONDS)
            await asyncio.sleep(wait)
        elif resp.status_code >= 500:
            await asyncio.sleep(attempt)
        else:
            break  # 4xx other than 429: retrying won't help
    raise FreshserviceError(f"{method} {path} failed: {last}")


_requester_email: str | None = None
_workspace_id: int | None = None


async def _load_identity() -> None:
    global _requester_email, _workspace_id
    agent = (await request("GET", "/agents/me"))["agent"]
    _requester_email = agent["email"]
    own = (agent.get("workspace_ids") or [None])[0]
    _workspace_id = get_settings().freshservice_workspace_id or own


async def requester_email() -> str:
    """Tickets need a requester; SentinelOps files them as the agent who owns the API key."""
    if _requester_email is None:
        await _load_identity()
    return _requester_email


async def workspace_id() -> int | None:
    """Where records are filed: the configured workspace, else the key owner's own."""
    if _requester_email is None:
        await _load_identity()
    return _workspace_id


SOURCE_ALERTS = 14  # Freshservice ticket source for monitoring-raised tickets


async def create_ticket(subject: str, description_html: str, priority: int) -> int:
    """Open a ticket (status Open, source Alerts). Returns its id.

    Some workspaces run a rule on new tickets that resets priority (the w19 sandbox sets
    every new ticket to Low), so if the stored priority differs, set it again.
    """
    body = {
        "subject": subject,
        "description": description_html,
        "email": await requester_email(),
        "priority": priority,
        "status": 2,  # Open
        "source": SOURCE_ALERTS,
    }
    if (ws := await workspace_id()) is not None:
        body["workspace_id"] = ws
    ticket = (await request("POST", "/tickets", body))["ticket"]
    if ticket.get("priority") != priority:
        await request("PUT", f"/tickets/{ticket['id']}", {"priority": priority})
    return ticket["id"]
