# SentinelOps AI

**An AI SRE agent that is allowed to fix production — because every fix goes through your own change-management process first.**

> The Great Agent Hackathon · Freshworks, Bengaluru · 25–26 September 2026
> Track 3 — AI-native Enterprise · Team **SentinelOps AI** (Vinay G, Chethan)

![Overview](docs/screenshots/overview.png)

---

## What it is

SentinelOps is an autonomous incident-response agent for teams running services on Kubernetes.

It watches a live system, detects incidents from real metrics, investigates them with Claude,
and proposes a fix. The fix becomes a **change request in Freshservice**. A human approves it
there, the way they approve every other production change — and only then does SentinelOps act,
verify that recovery actually happened, and roll itself back if it didn't.

Every step is written to an append-only, hash-chained event log, so the record of what the AI
did cannot be altered without it showing.

The distinction that matters: most AI ops tools stop at diagnosis. The ones that go further are
usually trusted with arbitrary access to production. SentinelOps acts, but only from a fixed
catalog of four validated actions, through a cluster identity that cannot delete or create
anything, after a human says yes. **The engineering is in the word "allowed".**

## What it does (business objective)

**Remove the human steps between knowing what is wrong and having it fixed — without removing
the human decision.**

| | |
|---|---|
| **Cuts time to recovery** | The outage ends at the approval click, not after an engineer works out the fix, applies it and checks it. Hours become minutes on failures the catalog covers. |
| **Returns engineer hours** | Investigation and the change paperwork both happen without anyone typing. The agent cites its evidence, so review is reading, not re-deriving. |
| **Makes AI action auditable** | Every action is a Freshservice change record plus a tamper-evident event. Compliance teams get a defensible trail instead of a log file. |
| **Keeps the existing process** | Approvals stay in Freshservice, with the organisation's own approvers and rules. Nothing new to certify. |
| **Reduces 2 a.m. pages** | When a fix does need a human, SentinelOps phones the on-call engineer rather than hoping someone notices a ticket. |

## What it doesn't do (out of scope)

Being explicit about the boundary is part of the safety argument.

- **It does not act without approval.** There is no autonomous-execution mode and no flag to
  enable one. The executor starts only from an approval event.
- **It does not write or run commands.** The agent selects one of four typed actions
  (`restart_service`, `scale_service`, `set_service_port`, `set_database_max_connections`) with
  validated parameters. Free-form shell, `kubectl` and SQL are not reachable from the model.
- **It does not collect telemetry.** It reads an existing Prometheus. It is not a monitoring
  product and does not replace one.
- **It does not support stacks other than Prometheus + Kubernetes** yet. Those are the only two
  interfaces it couples to; other stacks need adapters that do not exist.
- **It does not group or correlate alerts at scale.** Two services with one threshold is easy;
  two hundred services means an incident storm. Alert correlation is planned, not built.
- **It does not set your approval policy.** Risk level and required approvals are decided by a
  plain-code policy, and the approval itself belongs to Freshservice.
- **It does not do capacity planning, cost optimisation or security scanning**, and it is not a
  chatbot. It does one loop, end to end.

---

## Product Integrations

| Product | Used for |
|---|---|
| **Freshworks — Freshservice (REST API v2)** | The system of record and the approval gate. An incident opens a **ticket**; the agent's findings are posted as a **note** with its evidence; a proposed fix becomes a **change request** carrying the diff, blast radius, verification condition and rollback plan. SentinelOps then polls `GET /api/v2/changes/{id}/approvals` every 15 s and acts on the decision made *inside* Freshservice. Execution, verification and rollback are posted back as notes, and the change is closed out. |
| **Freshworks — Freshservice MCP server** | The hosted Model Context Protocol endpoint (`https://<domain>.freshservice.com/mcp`) for ticket operations and solution-article search, exposed to the agent as tools. Change management is not available over MCP, which is why the REST API carries that half. |
| **Anthropic — Claude Sonnet 5** | The investigation agent. Runs a tool-use loop over nine read-only tools (metrics, pod logs, pod status, deployment config, Kubernetes Service definition, rollout history, Postgres settings, dependencies, and a live TCP probe from inside a pod). Its conclusion is rejected unless it cites the tool results that support it. Bounded to 14 tool calls and 120 s, about $0.05 per investigation. |
| **Vobiz** | Outbound voice telephony. Phones the on-call engineer when a fix is waiting for approval — at most one call per 5 minutes, summarising everything currently open. Press 1 acknowledges, 2 repeats. Approval itself stays in Freshservice, where the approver is authenticated. |
| **Sarvam AI (bulbul)** | Indian-English text-to-speech for that phone call. Tried first, generated live while the phone rings. |
| **ElevenLabs** | Text-to-speech fallback if Sarvam fails or is slow. If both fail, the call still happens in the telephony provider's own voice — a nicer voice must never cost us the alert. |
| **Supabase** | SentinelOps' own Postgres, Auth (ES256 JWT) and Realtime. Deliberately separate from the database it monitors, so the tool survives the outage it is diagnosing. Hosts the hash-chained `events` table and its verification function. |
| **Prometheus** | The metrics source. Pull-based PromQL over HTTP; the detector asks every 15 s. |
| **Kubernetes** | The system under management. Accessed through a dedicated least-privilege ServiceAccount. |

## System Interaction Diagram

```
                    ┌──────────────────── Laptop ─────────────────────────┐
                    │  Kubernetes (Docker Desktop)                         │
                    │    order-service ─┐                                  │
                    │    payment-service┼──► postgres     MONITORED SYSTEM │
                    │    prometheus ◄───┘   scrapes /metrics every 5s      │
                    │         ▲                    ▲                       │
                    │  PromQL │ (pull)   k8s API   │ (read + limited patch)│
                    │    ┌────┴────────────────────┴─────┐                 │
   ┌────────────────┼───►│  SentinelOps backend (FastAPI) │                 │
   │                │    │  detector · agent · policy ·   │                 │
   │  approvals     │    │  executor · verifier · audit   │                 │
   │  polled 15s    │    └────┬───────────────────────┬───┘                 │
   │                │         │                       │                     │
   │                │    ┌────▼─────────────┐         │                     │
   │                │    │ Frontend (React) │         │                     │
   │                │    └──────────────────┘         │                     │
   └────────────────┼─────────────────────────────────┼─────────────────────┘
                    │                                 │
   ┌────────────────▼──────┐   ┌──────────────────┐   │   ┌──────────────────┐
   │  FRESHWORKS           │   │  ANTHROPIC       │◄──┘   │  SUPABASE        │
   │  Freshservice         │   │  Claude Sonnet 5 │       │  Postgres · Auth │
   │  · tickets (MCP)      │   │  tool-use loop,  │       │  · Realtime      │
   │  · solution articles  │   │  9 read-only     │       │  SentinelOps'    │
   │  · changes (REST v2)  │   │  tools           │       │  OWN database    │
   │  · approvals ────────►│   └──────────────────┘       └──────────────────┘
   │  · problems           │
   └───────────────────────┘
                    ▲
                    │  "a fix is waiting for approval"
   ┌────────────────┴──────┐   ┌──────────────────┐   ┌──────────────────┐
   │  VOBIZ                │◄──┤  SARVAM (bulbul) │   │  ELEVENLABS      │
   │  outbound voice call  │   │  Indian-English  │   │  TTS fallback    │
   │  to the on-call       │   │  TTS, tried 1st  │   │                  │
   └───────────────────────┘   └──────────────────┘   └──────────────────┘
```

---

## The loop

```
break → detect → investigate → propose → approve → execute → verify → (rollback) → audit
```

1. **Detect.** Every 15 s the detector asks Prometheus for each service's error ratio. Above
   5 % on two consecutive checks opens an incident, deduplicated so one problem is one incident.
2. **Investigate.** Claude investigates with read-only tools. Its conclusion must cite the tool
   results it relied on; a claim without evidence is rejected.
3. **Propose.** One action from the catalog, validated against the allow-list and the policy,
   shown as a live before/after diff from the cluster.
4. **Approve.** A change request in Freshservice — or the approval card in SentinelOps, which
   reads like a pull request: what changes, why, the evidence, who is affected, how success is
   judged, how to undo it.
5. **Execute → verify → roll back.** The executor re-checks the kill switch and the proposal
   before acting, records the "before" state, applies the change, then verifies recovery for
   two minutes or rolls back automatically.
6. **Audit.** Every step is an append-only event whose hash covers the previous event's hash.
   The audit page recomputes the whole chain on demand.

![Incident detail](docs/screenshots/incident-detail.png)
![Approval card](docs/screenshots/approvals.png)

## Why it is safe to let it act

The fences do not depend on the AI behaving well.

| Fence | How it is enforced |
|---|---|
| **A fixed menu of actions** | The agent picks from a catalog with typed, validated parameters. It cannot write commands. |
| **An allow-list** | Only named deployments and services in one namespace, and only permitted values. Anything else is refused server-side. |
| **Plain-code policy** | A table-driven function, not the AI, decides risk and how many approvals a fix needs. |
| **Enforced human approval** | Only the `approver` role may approve, and the approve is an atomic database transition, so a double-click cannot run a fix twice. Approving in Freshservice and in SentinelOps cannot double-execute either. |
| **Verify, then roll back** | After executing, SentinelOps watches the error rate. No recovery → the change is undone automatically and a human gets it back. |
| **Kill switch** | One switch pauses all execution, re-checked at execution time rather than only at approval time. |
| **Least-privilege identity** | A dedicated Kubernetes ServiceAccount that can patch allowed objects and cannot delete anything, create anything, read secrets, or see other namespaces. Provable with `kubectl auth can-i`. |
| **Tamper-evident record** | Append-only events, hash-chained. The database rejects updates and deletes on the table, and the audit page proves the chain on screen. |

## Stack

| Layer | Stack |
|---|---|
| Frontend | React 19, TypeScript, Vite, Tailwind, shadcn/ui, Recharts, TanStack Query |
| Backend | Python 3.12+, FastAPI, Pydantic v2, uv |
| Database, auth, live updates | Supabase (Postgres, Auth, Realtime) |
| Telemetry | Prometheus (PromQL over HTTP) |
| Cluster access | Kubernetes Python client, least-privilege ServiceAccount |
| AI | Claude Sonnet 5 via tool use (Anthropic Python SDK) |
| ITSM | Freshservice REST API v2 + hosted MCP server |
| Voice | Vobiz telephony, Sarvam and ElevenLabs TTS |

## Repository layout

| Path | What |
|---|---|
| `backend/app/core/` | Config, database, auth, event bus + hash chain, health |
| `backend/app/features/` | One folder per feature: `incidents`, `investigation`, `remediation`, `audit`, `simulator`, `topology` |
| `backend/app/integrations/` | `freshservice`, `vobiz`, `sarvam`, `elevenlabs` |
| `backend/tests/` | Unit tests (safety rules, detection, agent, executor, audit) and database tests |
| `frontend/src/` | App shell, feature pages, shared UI |
| `services/` | The *monitored* demo system: order-service, payment-service, Postgres, Prometheus |
| `supabase/migrations/` | SentinelOps' own database schema |
| `docs/` | [how-it-runs](docs/how-it-runs.md) · [glossary](docs/glossary.md) · [demo script](docs/demo-script.md) · [plan](docs/implementation-plan.md) · [test checklist](docs/manual-test-checklist.md) |

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
uv run python run.py            # not plain uvicorn: psycopg needs a SelectorEventLoop on Windows

# 4. Frontend (http://localhost:5173)
cd ../frontend && npm install && npm run dev
```

Then sign in, open **Simulator**, and press **Break it** on *Database port mismatch*. An
incident appears within about 35 s, and the investigation, proposal and approval card follow.

Only Supabase, Anthropic and the cluster are required. Freshservice, Vobiz, Sarvam and
ElevenLabs each degrade to "not configured" and the core loop still completes.

**Tests:** `cd backend && uv run pytest -q` (unit), `uv run pytest -q -m db` (database guarantees).

## What was built when

Judging weighs work done during the hackathon, so this is tracked honestly. The
**`v0-pre-event`** tag is the boundary, and `git log v0-pre-event..HEAD` is the full list.

| Built before the event (up to `v0-pre-event`) | Built at the event (after `v0-pre-event`) |
|---|---|
| Demo system baseline, least-privilege cluster identity, Supabase schema, auth | **Freshservice integration**: tickets, evidence notes, change requests, approvals read back from Freshservice, execution/verification notes, change closed out |
| Event bus with hash chain; detector; live incident list; failure simulator | **Audit page**: chain verification endpoint, filterable event table, on-screen verify badge, JSON-lines export |
| Investigation agent with evidence-backed findings | **Blast-radius map**: topology graph coloured by live error ratio, showing what a fix touches |
| Safety core: action catalog, policy, enforced approval, executor, verification, rollback, kill switch | **Voice escalation**: Vobiz call to the on-call engineer, Sarvam and ElevenLabs voices with fallback |
| Dark "command centre" UI: overview, incidents, incident detail, approvals, simulator, ⌘K palette | Audit-chain concurrency fix, and disclosure of its one historical fault |
| Observability views: global time range, per-service charts with incident markers, outcome tiles, filterable incidents table, service side panel | Glossary, demo script, submission deck |

The monitored demo services in `services/` were first written for an earlier prototype and
adapted here; they are the system being watched, not the product.
