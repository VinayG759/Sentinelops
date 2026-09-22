"""Write a kubeconfig that authenticates as the least-privilege `sentinelops-agent`.

Usage (from backend/):  uv run python scripts/make_agent_kubeconfig.py
Needs kubectl on PATH, pointed at the demo cluster, and services/k8s/sentinelops-rbac.yaml applied.
The token lasts 30 days; rerun to refresh. Output is gitignored (*.kubeconfig).
"""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.config import get_settings

SERVICE_ACCOUNT = "sentinelops-agent"


def kubectl(*args: str) -> str:
    return subprocess.run(["kubectl", *args], check=True, capture_output=True, text=True).stdout


def main() -> None:
    settings = get_settings()
    current = json.loads(kubectl("config", "view", "--raw", "--minify", "-o", "json"))
    context = current["contexts"][0]["name"]
    cluster = current["clusters"][0]["cluster"]
    print(f"Source context: {context}  ({cluster['server']})")

    token = kubectl(
        "create", "token", SERVICE_ACCOUNT, "-n", settings.k8s_namespace, "--duration=720h"
    ).strip()

    kubeconfig = {
        "apiVersion": "v1",
        "kind": "Config",
        "clusters": [{"name": "demo", "cluster": cluster}],
        "users": [{"name": SERVICE_ACCOUNT, "user": {"token": token}}],
        "contexts": [
            {
                "name": SERVICE_ACCOUNT,
                "context": {
                    "cluster": "demo",
                    "user": SERVICE_ACCOUNT,
                    "namespace": settings.k8s_namespace,
                },
            }
        ],
        "current-context": SERVICE_ACCOUNT,
    }
    out = settings.kubeconfig_file
    out.write_text(json.dumps(kubeconfig, indent=2), encoding="utf-8")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
