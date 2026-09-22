"""Fault scenarios: real breakages of the demo system, each with an exact undo.

All calls are synchronous Kubernetes operations (run them via asyncio.to_thread).
Adding a scenario = subclass Scenario and append it to SCENARIOS.
"""

from abc import ABC, abstractmethod

from app.core import k8s

POSTGRES_AUTO_CONF = "/var/lib/postgresql/data/pgdata/postgresql.auto.conf"


class Scenario(ABC):
    name: str
    title: str
    description: str

    @abstractmethod
    def inject(self) -> None: ...

    @abstractmethod
    def reset(self) -> None: ...

    @abstractmethod
    def is_active(self) -> bool: ...


class PortMismatch(Scenario):
    name = "port_mismatch"
    title = "Database port mismatch"
    description = (
        "Moves the postgres Service to port 5433, then restarts both services (as a deploy "
        "would) while they still connect to 5432. Recreates the real outage from 11 Sep: "
        "every new connection times out."
    )

    def _set_port(self, port: int) -> None:
        # JSON patch: replace the port in place (a merge patch would add a second port entry).
        k8s.core().patch_namespaced_service(
            "postgres", k8s.namespace(),
            [{"op": "replace", "path": "/spec/ports/0/port", "value": port}],
        )

    def inject(self) -> None:
        self._set_port(5433)
        # Established pool connections survive a Service port change, so nothing breaks
        # until the services reconnect. On 11 Sep that was a restart; do the same here.
        for deployment in ("order-service", "payment-service"):
            k8s.rollout_restart(deployment)

    def reset(self) -> None:
        self._set_port(5432)

    def is_active(self) -> bool:
        svc = k8s.core().read_namespaced_service("postgres", k8s.namespace())
        return svc.spec.ports[0].port != 5432


class PoolExhaustion(Scenario):
    name = "pool_exhaustion"
    title = "Database connection limit too low"
    description = (
        "Restarts Postgres with max_connections=5 while the services' pools want up to 32. "
        "Queries queue for connections and fail with 'too many clients'."
    )

    # Edits the config file directly rather than via SQL, so reset works even when
    # every connection slot is taken.
    def _restart_with(self, shell: str) -> None:
        k8s.exec_in_pod(k8s.running_pod("postgres"), ["sh", "-c", shell])
        k8s.rollout_restart("postgres")

    LIMIT = 5

    def inject(self) -> None:
        self._restart_with(
            f"sed -i '/^max_connections/d' {POSTGRES_AUTO_CONF} && "
            f"echo \"max_connections = '{self.LIMIT}'\" >> {POSTGRES_AUTO_CONF}"
        )

    def reset(self) -> None:
        self._restart_with(f"sed -i '/^max_connections/d' {POSTGRES_AUTO_CONF}")

    def is_active(self) -> bool:
        # Look for the injected value specifically: a healthy override (e.g. '100', left by
        # older tooling) must not count as broken.
        pattern = f"^max_connections = '{self.LIMIT}'"
        out = k8s.exec_in_pod(
            k8s.running_pod("postgres"),
            ["sh", "-c", f'grep -c "{pattern}" {POSTGRES_AUTO_CONF} || true'],
        )
        return out.strip() not in ("", "0")


SCENARIOS: dict[str, Scenario] = {s.name: s for s in (PortMismatch(), PoolExhaustion())}
