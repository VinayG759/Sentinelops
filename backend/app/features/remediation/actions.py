"""The action catalog: the only changes SentinelOps can make to the cluster.

The agent never writes commands. It picks an action by name and fills in typed
parameters, which are validated here before anything else happens. Each action knows:

  preview()      what would change (shown on the approval card)
  execute()      do it, returning the `before` state needed to undo it
  rollback()     put `before` back
  verify_query() PromQL that must come true for the fix to count as working

Adding an action = one class + an entry in CATALOG. Nothing else changes.
"""

from abc import ABC, abstractmethod
from typing import Literal

from pydantic import BaseModel, Field

from app.core import k8s

# Outer fence. The agent's RBAC role is the other one; both must allow an action.
ALLOWED_SERVICES = {"order-service", "payment-service"}
ALLOWED_NETWORK_SERVICES = {"postgres"}
Risk = Literal["low", "medium", "high"]


class Action(ABC):
    name: str
    title: str
    description: str
    Params: type[BaseModel]

    @abstractmethod
    def risk(self, params: BaseModel) -> Risk: ...

    @abstractmethod
    def affected_services(self, params: BaseModel) -> list[str]: ...

    @abstractmethod
    def preview(self, params: BaseModel) -> dict: ...

    @abstractmethod
    def execute(self, params: BaseModel) -> dict: ...

    @abstractmethod
    def rollback(self, params: BaseModel, before: dict) -> dict: ...

    @abstractmethod
    def verify_query(self, params: BaseModel) -> str: ...

    def rollback_plan(self, params: BaseModel) -> str:
        return "Restore the previous value recorded before execution."


def _error_ratio_below(services: list[str], threshold: float = 0.02) -> str:
    """PromQL that is true (returns 1) when every listed service is healthy again."""
    prefixes = {"order-service": "order", "payment-service": "payment"}
    parts = [
        f"(sum(rate({prefixes[s]}_errors_total[1m])) / sum(rate({prefixes[s]}_requests_total[1m])) "
        f"< bool {threshold})"
        for s in services
        if s in prefixes
    ]
    return " * ".join(parts) if parts else "vector(1)"


class RestartServiceParams(BaseModel):
    service: str = Field(description="Service to restart, e.g. 'order-service'")


class RestartService(Action):
    name = "restart_service"
    title = "Rolling restart"
    description = "Restart a service's pods one at a time. No downtime, no config change."
    Params = RestartServiceParams

    def risk(self, params) -> Risk:
        return "low"

    def affected_services(self, params) -> list[str]:
        return [params.service]

    def preview(self, params) -> dict:
        pods = k8s.core().list_namespaced_pod(
            k8s.namespace(), label_selector=f"app={params.service}"
        ).items
        return {
            "summary": f"Rolling restart of {params.service} ({len(pods)} pods)",
            "changes": [
                {"field": "pods", "from": f"{len(pods)} running", "to": "replaced one by one"}
            ],
        }

    def execute(self, params) -> dict:
        k8s.rollout_restart(params.service)
        return {"restarted": params.service}

    def rollback(self, params, before: dict) -> dict:
        return {"note": "a restart has nothing to undo; pods are already replaced"}

    def rollback_plan(self, params) -> str:
        return "Nothing to undo — a restart replaces pods with the same configuration."

    def verify_query(self, params) -> str:
        return _error_ratio_below([params.service])


class ScaleServiceParams(BaseModel):
    service: str
    replicas: int = Field(ge=1, le=5, description="Desired pod count, 1-5")


class ScaleService(Action):
    name = "scale_service"
    title = "Scale replicas"
    description = "Change how many pods a service runs (1-5)."
    Params = ScaleServiceParams

    def risk(self, params) -> Risk:
        return "low"

    def affected_services(self, params) -> list[str]:
        return [params.service]

    def _current(self, service: str) -> int:
        return k8s.apps().read_namespaced_deployment(service, k8s.namespace()).spec.replicas

    def preview(self, params) -> dict:
        current = self._current(params.service)
        return {
            "summary": f"Scale {params.service} from {current} to {params.replicas} pods",
            "changes": [{"field": "spec.replicas", "from": current, "to": params.replicas}],
        }

    def execute(self, params) -> dict:
        before = self._current(params.service)
        k8s.apps().patch_namespaced_deployment(
            params.service,
            k8s.namespace(),
            {"spec": {"replicas": params.replicas}},
            field_manager=k8s.FIELD_MANAGER,
        )
        return {"replicas": before}

    def rollback(self, params, before: dict) -> dict:
        k8s.apps().patch_namespaced_deployment(
            params.service,
            k8s.namespace(),
            {"spec": {"replicas": before["replicas"]}},
            field_manager=k8s.FIELD_MANAGER,
        )
        return {"replicas": before["replicas"]}

    def rollback_plan(self, params) -> str:
        return f"Scale {params.service} back to its previous replica count."

    def verify_query(self, params) -> str:
        return _error_ratio_below([params.service])


class SetServicePortParams(BaseModel):
    network_service: str = Field(description="Kubernetes Service name, e.g. 'postgres'")
    port: int = Field(ge=1, le=65535, description="Port the Service should expose")


class SetServicePort(Action):
    name = "set_service_port"
    title = "Change a Service port"
    description = (
        "Change the port a Kubernetes Service exposes, so clients using the standard port "
        "can reach it again."
    )
    Params = SetServicePortParams

    def risk(self, params) -> Risk:
        return "medium"  # touches shared networking used by every dependent service

    def affected_services(self, params) -> list[str]:
        return sorted(ALLOWED_SERVICES)

    def _current(self, name: str) -> int:
        return k8s.core().read_namespaced_service(name, k8s.namespace()).spec.ports[0].port

    def preview(self, params) -> dict:
        current = self._current(params.network_service)
        name = params.network_service
        return {
            "summary": f"Move Service {name} from port {current} to {params.port}",
            "changes": [{"field": "spec.ports[0].port", "from": current, "to": params.port}],
        }

    def _set(self, name: str, port: int) -> None:
        k8s.core().patch_namespaced_service(
            name,
            k8s.namespace(),
            [{"op": "replace", "path": "/spec/ports/0/port", "value": port}],
            field_manager=k8s.FIELD_MANAGER,
        )

    def execute(self, params) -> dict:
        before = self._current(params.network_service)
        self._set(params.network_service, params.port)
        return {"port": before}

    def rollback(self, params, before: dict) -> dict:
        self._set(params.network_service, before["port"])
        return {"port": before["port"]}

    def rollback_plan(self, params) -> str:
        return f"Put {params.network_service} back on the port it had before."

    def verify_query(self, params) -> str:
        return _error_ratio_below(sorted(ALLOWED_SERVICES))


class SetDatabaseMaxConnectionsParams(BaseModel):
    value: int = Field(ge=20, le=200, description="New max_connections for Postgres (20-200)")


class SetDatabaseMaxConnections(Action):
    name = "set_database_max_connections"
    title = "Raise the database connection limit"
    description = (
        "Set Postgres max_connections and restart it. Brief downtime while the database "
        "restarts; clients reconnect automatically."
    )
    Params = SetDatabaseMaxConnectionsParams
    CONF = "/var/lib/postgresql/data/pgdata/postgresql.auto.conf"

    def risk(self, params) -> Risk:
        return "high"  # restarts the shared database

    def affected_services(self, params) -> list[str]:
        return sorted(ALLOWED_SERVICES | {"postgres"})

    def _read_current(self) -> int | None:
        out = k8s.exec_in_pod(
            k8s.running_pod("postgres"),
            ["sh", "-c", f"grep '^max_connections' {self.CONF} | tail -1 || true"],
        ).strip()
        digits = "".join(c for c in out if c.isdigit())
        return int(digits) if digits else None

    def preview(self, params) -> dict:
        current = self._read_current()
        return {
            "summary": f"Set Postgres max_connections to {params.value} and restart it",
            "changes": [
                {"field": "max_connections", "from": current or "default (100)", "to": params.value}
            ],
        }

    def _apply(self, value: int | None) -> None:
        line = f" && echo \"max_connections = '{value}'\" >> {self.CONF}" if value else ""
        k8s.exec_in_pod(
            k8s.running_pod("postgres"),
            ["sh", "-c", f"sed -i '/^max_connections/d' {self.CONF}{line}"],
        )
        k8s.rollout_restart("postgres")

    def execute(self, params) -> dict:
        before = self._read_current()
        self._apply(params.value)
        return {"max_connections": before}

    def rollback(self, params, before: dict) -> dict:
        self._apply(before.get("max_connections"))
        return {"max_connections": before.get("max_connections") or "default"}

    def rollback_plan(self, params) -> str:
        return "Restore the previous max_connections value and restart Postgres again."

    def verify_query(self, params) -> str:
        return _error_ratio_below(sorted(ALLOWED_SERVICES))


CATALOG: dict[str, Action] = {
    a.name: a
    for a in (RestartService(), ScaleService(), SetServicePort(), SetDatabaseMaxConnections())
}


class NotAllowed(ValueError):
    """The action or its target is outside the allow-list."""


def validate(action_name: str, raw_params: dict) -> tuple[Action, BaseModel]:
    """Look up the action, validate its parameters, and enforce the allow-list. Fails closed."""
    action = CATALOG.get(action_name)
    if action is None:
        raise NotAllowed(f"Unknown action '{action_name}'. Allowed: {sorted(CATALOG)}")
    params = action.Params(**raw_params)  # pydantic raises on bad types/ranges

    service = getattr(params, "service", None)
    if service is not None and service not in ALLOWED_SERVICES:
        raise NotAllowed(f"Service '{service}' is not in the allow-list {sorted(ALLOWED_SERVICES)}")

    network_service = getattr(params, "network_service", None)
    if network_service is not None and network_service not in ALLOWED_NETWORK_SERVICES:
        raise NotAllowed(
            f"Service '{network_service}' is not in {sorted(ALLOWED_NETWORK_SERVICES)}"
        )
    return action, params
