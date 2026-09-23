# How SentinelOps runs, and how it sees failure

The system SentinelOps watches is a real Kubernetes cluster with real services, a real
database and real metrics. Nothing in the detection or investigation path is mocked: the
simulator breaks the cluster for real, and the agent only ever sees symptoms.

This page explains the whole stack from the bottom up, and what happens when each part fails.

---

## 1. The layers

```
Laptop (Windows)
└── Docker Desktop ............ runs Linux containers
    └── Kubernetes ............ keeps the right things running, gives them a network
        ├── order-service   × 2 pods   Node.js, queries the database twice a second
        ├── payment-service × 2 pods   same, independently
        ├── postgres        × 1 pod    the database they share
        └── prometheus      × 1 pod    collects numbers from every pod every 5s

SentinelOps itself runs beside the cluster, not inside it:
    backend (FastAPI)   → reads Prometheus + the Kubernetes API, acts through a restricted identity
    frontend (React)    → the operator's screen
    Supabase (cloud)    → SentinelOps' own database: incidents, events, proposals, audit chain
```

**Terms, once:** a *container* is a program plus everything it needs, sealed in a box. *Docker*
builds and runs those boxes. *Kubernetes* is the manager above Docker: you declare what you
want ("2 copies of order-service") and it makes reality match, restarting anything that dies.
A *pod* is one running copy. *kubectl* is the remote control.

**Why SentinelOps runs outside the cluster:** a tool that diagnoses an outage must not be part
of the outage. Its own database (Supabase) is deliberately separate from the database it watches.

---

## 2. What is declared, and where

| File | Declares |
|---|---|
| `services/order-service/server.js` | The program: queries Postgres every 500 ms, counts requests, errors, latency, pool usage; serves `/metrics` |
| `services/k8s/order-service.yaml` | 2 pods of `order-service:v2`, its settings, memory limits, and the `order-service` network name |
| `services/k8s/payment-service.yaml` | The same for payments |
| `services/k8s/postgres.yaml` | The database, its 1 GB persistent volume, and the `postgres` network name on port 5432. `Recreate` strategy so two Postgres processes never share one data directory |
| `services/k8s/prometheus.yaml`, `prometheus-config.yaml` | The metrics collector, and the rule "scrape every pod that asks to be scraped, every 5 s" |
| `services/k8s/sentinelops-rbac.yaml` | SentinelOps' own cluster identity and exactly what it may do |

Apply everything with `kubectl apply -f services/k8s/`.

> Docker Desktop's Kubernetes keeps its **own image store**, so a locally built image must be
> loaded into it:
> `docker save order-service:v2 | docker exec -i desktop-control-plane ctr -n k8s.io images import --all-platforms -`

---

## 3. How services find each other

Pods get new IP addresses whenever they restart, so nothing connects to an IP. Kubernetes gives
each service a **stable name**: `order-service` connects to host `postgres`, port `5432`, and
Kubernetes routes that to whichever pod is alive.

That indirection is what the first demo fault attacks: the simulator moves the `postgres` name
to port **5433** while the services keep dialling **5432**. Every new connection times out.
It is a real outage, not a flag we flip in software — and it is the same mistake that took this
system down for real on 11 September 2026.

---

## 4. How numbers leave the services

1. Each service keeps counters in memory — `order_requests_total`, `order_errors_total`,
   a latency histogram, and connection-pool gauges (`db_pool_total`, `db_pool_idle`,
   `db_pool_waiting`, `db_pool_max`).
2. It publishes them as plain text at `http://<pod>:4002/metrics`.
3. Each pod carries annotations (`prometheus.io/scrape: "true"`, `port`, `path`), and Prometheus
   discovers and **scrapes every such pod every 5 seconds**, storing values with timestamps.

The pool gauges matter: they are what lets an investigation *prove* connection exhaustion
(requests waiting for a connection) instead of guessing.

---

## 5. How SentinelOps sees failure

Three independent senses, all **pull-based** — nothing pushes to SentinelOps.

**The detector — the alarm.** Every 15 seconds the backend asks Prometheus one question per
service: what share of requests failed in the last 30 seconds?

```promql
sum(rate(order_errors_total[30s])) / sum(rate(order_requests_total[30s]))
```

Above 5% on **two consecutive checks** opens an incident. One blip does not. No traffic at all
does not (0 errors out of 0 requests is not an outage). At most one open incident per service
and signal. Code: `backend/app/features/incidents/detector.py`, rules in `rules.py`.

**The agent's tools — the investigation.** Once an incident opens, Claude investigates with
read-only tools: service metrics, pod logs, pod status and restart counts, deployment
configuration, the Kubernetes Service's ports, rollout history, Postgres's own connection
settings, dependencies, and a live TCP probe from inside a pod. It may look; it may not touch.
Code: `backend/app/features/investigation/tools.py`.

**The health check — is SentinelOps itself blind?** `GET /api/health` tests Supabase,
Prometheus, Kubernetes and Freshservice separately, each with its own timeout. The four dots in
the top bar are this endpoint, so a red dot names the layer that is down.

---

## 6. How SentinelOps acts, and what stops it

Two independent fences:

**Outer fence — the cluster identity.** SentinelOps authenticates as the `sentinelops-agent`
ServiceAccount. It may read pods, logs, deployments and services in the `default` namespace,
patch deployments and services, and exec for connectivity probes. It **cannot** delete anything,
create anything, read secrets, or see other namespaces. Demonstrable live:

```bash
kubectl --kubeconfig sentinelops-agent.kubeconfig auth can-i delete deployments -n default  # no
kubectl --kubeconfig sentinelops-agent.kubeconfig auth can-i get pods -n kube-system        # no
kubectl --kubeconfig sentinelops-agent.kubeconfig auth can-i patch deployments -n default   # yes
```

**Inner fence — the action catalog.** The agent never writes commands. It picks one of four
actions and fills in typed parameters, which are validated and checked against an allow-list
before anything happens: `restart_service`, `scale_service` (1–5), `set_service_port`,
`set_database_max_connections` (20–200). A policy then sets the risk level and how many
approvals are required, a human approves, and only then does the executor act — triggered by
the approval **event**, with no HTTP route into it.

After execution, recovery is verified for 2 minutes against a PromQL condition. If it does not
recover, the change is **rolled back automatically** and the incident goes back to a human.

---

## 7. What happens when each part fails

| What breaks | What SentinelOps does |
|---|---|
| A service starts failing | Incident opens in ~30 s; investigation starts automatically |
| A single pod dies | Kubernetes replaces it. An incident opens only if errors actually spike |
| Postgres goes down | Both services fail → two incidents → one approved fix closes both ("resolved by a fix applied elsewhere") |
| **Prometheus dies** | Detection goes blind: the `prometheus` dot turns red, ticks log the failure and retry. No invented incidents |
| **Docker / Kubernetes stops** | The `kubernetes` dot turns red; panels show "could not load this" with the reason instead of spinning; the rest of the app keeps working |
| The backend restarts between approval and execution | A 30-second sweeper picks up approved-but-unexecuted proposals; the one-time execution claim prevents double runs |
| A proposal is never decided | It expires after 15 minutes, and the incident is investigated again (capped at 3 times) rather than being stranded |
| A fix does not work | Verification fails, the change is undone automatically, the incident reopens for a human |
| **Supabase unreachable** | SentinelOps' own database is gone: the `database` dot turns red and the UI cannot load. This is the one hard dependency |

---

## 8. Showing any layer live

```bash
kubectl get pods                              # what is running
kubectl logs deploy/order-service --tail=20   # what a service is saying
kubectl get svc postgres -o yaml              # the network name and port — where the fault lives
kubectl rollout history deploy/postgres       # what changed recently

# Prometheus UI — run the detector's own query in front of an audience
#   sum(rate(order_errors_total[30s])) / sum(rate(order_requests_total[30s]))
http://localhost:9090

curl http://localhost:8000/api/health         # what SentinelOps can currently reach
```

---

## 9. Questions worth expecting

**"Is this a real cluster or a mock?"** Real Kubernetes, four real workloads, a real database,
real Prometheus. The simulator changes the cluster itself; the agent cannot see how it was
broken, only the symptoms.

**"What stops the AI doing something destructive?"** Four allowed actions with validated
parameters, an allow-list of targets, a policy deciding risk and approvals, a required human
approval, and a cluster identity that cannot delete or create. Then verification and automatic
rollback afterwards.

**"What if the diagnosis is wrong?"** A finding is rejected unless it cites the specific tool
results that prove it, and every claim on the timeline links to the raw output behind it. If a
fix is approved and does not work, it is undone automatically within two minutes.

**"Could it act without a human?"** There is no code path from the agent to the cluster. The
executor starts only from an approval event, re-checks the kill switch and the proposal's
status first, and claims a one-time execution record so two approvals cannot run twice.

**"What if your laptop is slow, or the network dies mid-demo?"** Detection, investigation and
execution are all local to the laptop. The cloud dependencies are Supabase (SentinelOps' own
database) and the Claude API (investigation). Both show as red dots when unreachable, and the
kill switch works regardless.
