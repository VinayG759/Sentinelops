"""Running commands inside pods must be safe to do in parallel.

The Kubernetes client's `stream()` swaps the request method on the ApiClient it is given for
the duration of the call. When that client is shared across threads, overlapping calls read
the swapped method and fail with "'NoneType' object has no attribute 'decode'", and can leave
the shared client stuck in exec mode. The investigation agent probes in parallel, so this
must hold.

    uv run pytest -m cluster
"""

import types
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.core import k8s

pytestmark = pytest.mark.cluster


def _probe(deployment: str) -> str:
    pod = k8s.running_pod(deployment)  # a plain REST read, interleaved with the exec
    return k8s.exec_in_pod(pod, ["node", "-e", "console.log('ok')"]).strip()


def test_parallel_execs_all_succeed_and_leave_the_shared_client_intact():
    deployments = ["order-service", "payment-service"] * 6
    with ThreadPoolExecutor(max_workers=len(deployments)) as pool:
        futures = [pool.submit(_probe, d) for d in deployments]
        outcomes = []
        for future in futures:
            try:
                outcomes.append(future.result())
            except Exception as exc:  # collect every failure, not just the first
                outcomes.append(f"{type(exc).__name__}: {exc}")

    assert outcomes == ["ok"] * len(deployments)
    # The shared client must still make ordinary REST calls, not websocket ones.
    assert isinstance(k8s._api_client().request, types.MethodType)
    k8s.apps().read_namespaced_deployment("order-service", k8s.namespace())
