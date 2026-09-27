"""Read-only tools the investigation agent may call.

The agent can look, never touch: no tool here writes anything to the cluster.
Remediation comes later, and only through the approved action catalog.

Each tool is a plain async function returning JSON-serialisable data, plus a
schema in TOOL_SCHEMAS describing it to the model.
"""

import asyncio
import json
import re

from app.core import k8s, prometheus
from app.core.db import get_pool

ALLOWED_PROBE_PORTS = {5432, 5433, 4001, 4002, 9090}
MAX_LOG_LINES = 50

# Settings whose values the agent must never see. Their names stay visible, so it can still
# tell a password is configured; the value would be sent to the model and kept on the timeline.
_SENSITIVE_ENV = re.compile(r"PASSWORD|PASSWD|SECRET|TOKEN|KEY|CREDENTIAL", re.IGNORECASE)


def redact_env(env: dict[str, str | None]) -> dict[str, str | None]:
    return {k: "[hidden]" if v and _SENSITIVE_ENV.search(k) else v for k, v in env.items()}


async def _service_row(name: str) -> dict:
    async with get_pool().connection() as conn:
        cur = await conn.execute(
            "select name, kind, deployment, namespace, metric_prefix, depends_on "
            "from public.services where name = %s",
            (name,),
        )
        row = await cur.fetchone()
    if row is None:
        raise ValueError(f"Unknown service '{name}'")
    return row


async def get_service_metrics(service: str, window: str = "2m") -> dict:
    """Error ratio, request rate, p95 latency and connection-pool gauges."""
    row = await _service_row(service)
    prefix = row["metric_prefix"]
    if not prefix:
        return {"service": service, "note": "no application metrics for this component"}

    app_filter = f'{{app="{service}"}}'
    ratio, rate, p95, pool_total, pool_idle, pool_waiting, pool_max = await asyncio.gather(
        prometheus.query_scalar(
            f"sum(rate({prefix}_errors_total[{window}])) / "
            f"sum(rate({prefix}_requests_total[{window}]))"
        ),
        prometheus.query_scalar(f"sum(rate({prefix}_requests_total[{window}]))"),
        prometheus.query_scalar(
            f"histogram_quantile(0.95, sum(rate({prefix}_request_duration_ms_bucket[{window}]))"
            " by (le))"
        ),
        prometheus.query_scalar(f"sum(db_pool_total{app_filter})"),
        prometheus.query_scalar(f"sum(db_pool_idle{app_filter})"),
        prometheus.query_scalar(f"sum(db_pool_waiting{app_filter})"),
        prometheus.query_scalar(f"max(db_pool_max{app_filter})"),
    )
    return {
        "service": service,
        "window": window,
        "error_ratio": ratio,
        "requests_per_second": rate,
        "p95_latency_ms": p95,
        "db_pool": {
            "open_connections": pool_total,
            "idle": pool_idle,
            "waiting_queries": pool_waiting,
            "max_per_pod": pool_max,
        },
    }


async def get_logs(service: str, lines: int = 20) -> dict:
    """Recent log lines from one pod of the service. Each line starts with its UTC timestamp,
    so errors from before the incident opened can be told apart from current ones."""
    row = await _service_row(service)
    lines = min(lines, MAX_LOG_LINES)
    pod, text = await asyncio.to_thread(k8s.pod_logs, row["deployment"], lines)
    return {"service": service, "pod": pod, "lines": text.strip().splitlines()}


async def get_pods(service: str) -> dict:
    """Pod status, restart counts and image for the service."""
    row = await _service_row(service)

    def read() -> list[dict]:
        pods = k8s.core().list_namespaced_pod(
            k8s.namespace(), label_selector=f"app={row['deployment']}"
        )
        return [
            {
                "name": p.metadata.name,
                "phase": p.status.phase,
                "ready": all(c.ready for c in (p.status.container_statuses or [])),
                "restarts": sum(c.restart_count for c in (p.status.container_statuses or [])),
                "image": p.spec.containers[0].image,
                "started_at": str(p.status.start_time),
            }
            for p in pods.items
        ]

    return {"service": service, "pods": await asyncio.to_thread(read)}


async def get_deployment_config(service: str) -> dict:
    """Environment variables, image, replica counts and container ports."""
    row = await _service_row(service)

    def read() -> dict:
        dep = k8s.apps().read_namespaced_deployment(row["deployment"], k8s.namespace())
        container = dep.spec.template.spec.containers[0]
        return {
            "deployment": dep.metadata.name,
            "image": container.image,
            "env": redact_env({e.name: e.value for e in (container.env or [])}),
            "ports": [p.container_port for p in (container.ports or [])],
            "replicas": {"desired": dep.spec.replicas, "ready": dep.status.ready_replicas},
        }

    return await asyncio.to_thread(read)


async def get_network_service(name: str) -> dict:
    """The Kubernetes Service other pods connect to by name: its ports, type and selector."""

    def read() -> dict:
        svc = k8s.core().read_namespaced_service(name, k8s.namespace())
        return {
            "name": name,
            "type": svc.spec.type,
            "cluster_ip": svc.spec.cluster_ip,
            "selector": svc.spec.selector,
            "ports": [
                {"port": p.port, "target_port": str(p.target_port)} for p in svc.spec.ports
            ],
        }

    return await asyncio.to_thread(read)


async def get_recent_changes(service: str) -> dict:
    """Rollout history: when the deployment last changed, newest first."""
    row = await _service_row(service)

    def read() -> list[dict]:
        sets = k8s.apps().list_namespaced_replica_set(
            k8s.namespace(), label_selector=f"app={row['deployment']}"
        )
        history = [
            {
                "revision": rs.metadata.annotations.get("deployment.kubernetes.io/revision"),
                "created_at": str(rs.metadata.creation_timestamp),
                "image": rs.spec.template.spec.containers[0].image,
                "desired_replicas": rs.spec.replicas,
                "restarted_at": rs.spec.template.metadata.annotations.get(
                    "kubectl.kubernetes.io/restartedAt"
                ),
            }
            for rs in sets.items
        ]
        return sorted(history, key=lambda h: h["created_at"], reverse=True)[:5]

    return {"service": service, "rollouts": await asyncio.to_thread(read)}


async def get_dependencies(service: str) -> dict:
    """What this service depends on, and what depends on it."""
    async with get_pool().connection() as conn:
        rows = await (
            await conn.execute("select name, depends_on from public.services")
        ).fetchall()
    return {
        "service": service,
        "depends_on": next((r["depends_on"] for r in rows if r["name"] == service), []),
        "depended_on_by": [r["name"] for r in rows if service in (r["depends_on"] or [])],
    }


async def get_database_settings() -> dict:
    """Postgres connection limits and current usage: max_connections vs active connections."""

    def read() -> dict:
        pod = k8s.running_pod("postgres")
        sql = (
            "select current_setting('max_connections'), "
            "current_setting('superuser_reserved_connections'), "
            "(select count(*) from pg_stat_activity)"
        )
        out = k8s.exec_in_pod(
            pod, ["psql", "-U", "sentinel", "-d", "sentinelops", "-Atc", sql]
        ).strip()
        # A refusal here is itself evidence: it means no connection slots are free.
        if "|" not in out:
            return {"error": out or "no output", "note": "could not query Postgres"}
        max_conn, reserved, active = out.splitlines()[0].split("|")
        return {
            "max_connections": int(max_conn),
            "superuser_reserved_connections": int(reserved),
            "active_connections": int(active),
        }

    return await asyncio.to_thread(read)


async def check_connectivity(from_service: str, host: str, port: int) -> dict:
    """Open a TCP connection from inside a service's pod: is host:port reachable?"""
    if port not in ALLOWED_PROBE_PORTS:
        raise ValueError(f"Port {port} is not allowed; pick one of {sorted(ALLOWED_PROBE_PORTS)}")
    row = await _service_row(from_service)
    script = (
        f"const s=require('net').connect({port},'{host}');s.setTimeout(3000);"
        "s.on('connect',()=>{console.log('OPEN');s.end()});"
        "s.on('timeout',()=>{console.log('TIMEOUT');s.destroy()});"
        "s.on('error',e=>console.log(e.code));"
    )

    def probe() -> str:
        pod = k8s.running_pod(row["deployment"])
        return k8s.exec_in_pod(pod, ["node", "-e", script]).strip()

    result = await asyncio.to_thread(probe)
    return {
        "from": from_service,
        "target": f"{host}:{port}",
        "result": result,
        "reachable": result == "OPEN",
    }


TOOLS = {
    fn.__name__: fn
    for fn in (
        get_service_metrics,
        get_logs,
        get_pods,
        get_deployment_config,
        get_network_service,
        get_recent_changes,
        get_dependencies,
        get_database_settings,
        check_connectivity,
    )
}


def _schema(fn, properties: dict, required: list[str]) -> dict:
    return {
        "name": fn.__name__,
        "description": fn.__doc__.strip(),
        "input_schema": {"type": "object", "properties": properties, "required": required},
    }


SERVICE_ARG = {"service": {"type": "string", "description": "Service name, e.g. 'order-service'"}}

TOOL_SCHEMAS = [
    _schema(get_service_metrics, SERVICE_ARG | {
        "window": {"type": "string", "description": "PromQL range, default '2m'"}}, ["service"]),
    _schema(get_logs, SERVICE_ARG | {
        "lines": {"type": "integer", "description": f"Up to {MAX_LOG_LINES}, default 20"}},
        ["service"]),
    _schema(get_pods, SERVICE_ARG, ["service"]),
    _schema(get_deployment_config, SERVICE_ARG, ["service"]),
    _schema(get_network_service, {
        "name": {"type": "string", "description": "Kubernetes Service name, e.g. 'postgres'"}},
        ["name"]),
    _schema(get_recent_changes, SERVICE_ARG, ["service"]),
    _schema(get_dependencies, SERVICE_ARG, ["service"]),
    _schema(get_database_settings, {}, []),
    _schema(check_connectivity, {
        "from_service": {"type": "string", "description": "Service whose pod runs the probe"},
        "host": {"type": "string", "description": "Hostname to reach, e.g. 'postgres'"},
        "port": {"type": "integer", "description": f"One of {sorted(ALLOWED_PROBE_PORTS)}"}},
        ["from_service", "host", "port"]),
]


async def run_tool(name: str, args: dict) -> str:
    """Execute a tool by name and return its result as JSON text for the model."""
    fn = TOOLS.get(name)
    if fn is None:
        raise ValueError(f"Unknown tool '{name}'")
    return json.dumps(await fn(**args), default=str)
