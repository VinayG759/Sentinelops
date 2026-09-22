"""GET /api/health — each dependency reported separately, so a red light says *which* layer."""

import asyncio
import time

import httpx
from fastapi import APIRouter
from kubernetes import client as k8s
from kubernetes import config as k8s_config

from app.core.config import get_settings
from app.core.db import get_pool

router = APIRouter()


async def _timed(check) -> dict:
    start = time.perf_counter()
    try:
        detail = await asyncio.wait_for(check(), timeout=5)
        status = "skipped" if detail == "not configured" else "ok"
        return {"status": status, "detail": detail, "ms": _ms(start)}
    except Exception as exc:  # health must report failures, never raise them
        return {"status": "error", "detail": f"{type(exc).__name__}: {exc}", "ms": _ms(start)}


def _ms(start: float) -> int:
    return round((time.perf_counter() - start) * 1000)


async def _check_database() -> str:
    if not get_settings().supabase_db_url:
        return "not configured"
    async with get_pool().connection() as conn:
        await conn.execute("select 1")
    return "connected"


async def _check_prometheus() -> str:
    async with httpx.AsyncClient(timeout=4) as http:
        resp = await http.get(f"{get_settings().prometheus_url}/-/ready")
        resp.raise_for_status()
    return "ready"


async def _check_kubernetes() -> str:
    settings = get_settings()
    if not settings.kubeconfig_file.exists():
        return "not configured"

    def list_pods() -> int:
        api = k8s_config.new_client_from_config(config_file=str(settings.kubeconfig_file))
        pods = k8s.CoreV1Api(api).list_namespaced_pod(settings.k8s_namespace, _request_timeout=4)
        return len(pods.items)

    count = await asyncio.to_thread(list_pods)
    return f"{count} pods visible in '{settings.k8s_namespace}'"


async def _check_freshservice() -> str:
    settings = get_settings()
    if not (settings.freshservice_domain and settings.freshservice_api_key):
        return "not configured"
    async with httpx.AsyncClient(timeout=4) as http:
        resp = await http.get(
            f"https://{settings.freshservice_domain}/api/v2/agents/me",
            auth=(settings.freshservice_api_key, "X"),
        )
        resp.raise_for_status()
    return "authenticated"


@router.get("/api/health")
async def health() -> dict:
    names = ["database", "prometheus", "kubernetes", "freshservice"]
    results = await asyncio.gather(
        _timed(_check_database),
        _timed(_check_prometheus),
        _timed(_check_kubernetes),
        _timed(_check_freshservice),
    )
    checks = dict(zip(names, results, strict=True))
    overall = "ok" if all(c["status"] != "error" for c in checks.values()) else "degraded"
    return {"status": overall, "checks": checks}
