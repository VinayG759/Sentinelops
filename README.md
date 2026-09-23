# SentinelOps AI

**Autonomous incident response that is allowed to act on production — safely.**

SentinelOps watches a Kubernetes system, detects incidents, investigates them with an AI
agent that must cite evidence, and proposes fixes from a fixed catalog of safe actions.
A human approves (in SentinelOps or through Freshservice change management), the fix runs,
recovery is verified, failed fixes roll back automatically, and every step lands in a
tamper-evident audit log.

> Status: in development for the Freshworks hackathon (Bangalore, 25–26 Sep 2026).
> **[docs/how-it-runs.md](docs/how-it-runs.md)** explains the stack and what happens when each
> part fails. [docs/implementation-plan.md](docs/implementation-plan.md) has the full plan.

## The loop

```
break → detect → investigate → propose → approve → execute → verify → (rollback) → audit
```

## Repository layout

| Path | What |
|---|---|
| `backend/` | FastAPI service: detector, agent, policy, executor, integrations |
| `frontend/` | React + TypeScript app |
| `services/` | The *monitored* demo system: order-service, payment-service, Postgres, Prometheus |
| `supabase/migrations/` | SentinelOps' own database schema |
| `docs/` | Plans, business case, demo script |

## Running locally

Prerequisites: Docker Desktop with Kubernetes enabled, Node 20+, [uv](https://docs.astral.sh/uv/).

```bash
cp .env.example .env            # then fill in the values

# 1. Demo system
docker build -t order-service:v2 services/order-service
docker build -t payment-service:v2 services/payment-service
kubectl apply -f services/k8s/

# 2. SentinelOps' least-privilege cluster identity + database schema
cd backend
uv run python scripts/make_agent_kubeconfig.py
uv run python scripts/migrate.py

# 3. Backend (http://localhost:8000/api/health)
uv run python run.py

# 4. Frontend (http://localhost:5173)
cd ../frontend && npm install && npm run dev
```

## What was built when

Judging weighs work done during the hackathon, so this is tracked honestly.

| Built before the event (tag `v0-pre-event`) | Built at the event |
|---|---|
| _filled in at the freeze_ | _filled in during the event_ |

The monitored demo services in `services/` were first written for an earlier prototype
and adapted here; they are the system being watched, not the product.
