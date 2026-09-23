"""Kubernetes access as the least-privilege `sentinelops-agent` identity.

The official client is synchronous; call these helpers via `asyncio.to_thread`.
"""

from datetime import UTC, datetime
from functools import lru_cache

from kubernetes import client
from kubernetes import config as k8s_config
from kubernetes.stream import stream

from app.core.config import get_settings

# Kubernetes records the name of whichever client last wrote each field, in
# `metadata.managedFields`. Naming ourselves means `kubectl get svc postgres -o yaml`
# shows, in the cluster's own words, that SentinelOps made the change — independent
# evidence that does not come from our database.
FIELD_MANAGER = "sentinelops-agent"
SIMULATOR_FIELD_MANAGER = "sentinelops-simulator"


@lru_cache
def _api_client() -> client.ApiClient:
    return k8s_config.new_client_from_config(config_file=str(get_settings().kubeconfig_file))


def core() -> client.CoreV1Api:
    return client.CoreV1Api(_api_client())


def apps() -> client.AppsV1Api:
    return client.AppsV1Api(_api_client())


def namespace() -> str:
    return get_settings().k8s_namespace


def running_pod(app_label: str) -> str:
    """Name of a running, non-terminating pod for `app=<label>`."""
    pods = core().list_namespaced_pod(namespace(), label_selector=f"app={app_label}").items
    for pod in pods:
        if pod.status.phase == "Running" and pod.metadata.deletion_timestamp is None:
            return pod.metadata.name
    raise RuntimeError(f"No running pod for app={app_label}")


def exec_in_pod(pod: str, command: list[str]) -> str:
    """Run a command in a pod's first container and return its combined output.

    Uses its own throwaway ApiClient: `stream()` swaps the client's request method for the
    duration of the call, which corrupts a client shared across threads (overlapping calls
    fail, and the shared client can be left stuck in exec mode).
    """
    private = k8s_config.new_client_from_config(config_file=str(get_settings().kubeconfig_file))
    return stream(
        client.CoreV1Api(private).connect_get_namespaced_pod_exec,
        pod,
        namespace(),
        command=command,
        stderr=True,
        stdin=False,
        stdout=True,
        tty=False,
        _request_timeout=30,
    )


def rollout_restart(deployment: str) -> None:
    """Same as `kubectl rollout restart`: bump a template annotation."""
    stamp = datetime.now(UTC).isoformat()
    apps().patch_namespaced_deployment(
        deployment,
        namespace(),
        {"spec": {"template": {"metadata": {"annotations": {
            "kubectl.kubernetes.io/restartedAt": stamp
        }}}}},
        field_manager=FIELD_MANAGER,
    )
