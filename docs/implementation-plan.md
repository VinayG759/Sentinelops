# SentinelOps AI — Implementation Plan

> Autonomous enterprise observability with safety-gated remediation, integrated with Freshservice.
> Track: AI-native Enterprise (Open) · Freshworks hackathon, Bangalore, 25–26 Sep 2026.
> Plain-language companion: [implementation-plan-simple.md](implementation-plan-simple.md)

| | |
|---|---|
| Status | v2, 2026-09-22. Rewritten after the organisers' briefing |
| Builder | Vinay (solo build; teammates on business case and pitch) |
| Repo | This folder, new public GitHub repo. The earlier `SentinalOps` project is **reference only**, and no code is carried over except demo infrastructure manifests, which are copied and fixed in Phase 0 |
| Scope | Working prototype against a real local Kubernetes cluster, with Freshservice as the system of record for incidents, changes and approvals |

---

## 0. Constraints from the organisers

| Constraint | Consequence for this plan |
|---|---|
| Freshworks integration is **mandatory for Tracks 1 and 2, not for Track 3** (participant handbook, §3). The pre-event briefing said mandatory for all; the handbook is the written rule. **We are Track 3 and are doing it anyway** — decided 23 Sep — because "the AI works through your existing change process" is a differentiator, and it covers us if the briefing wins | Freshservice (ITSM) is the natural fit. Its own phase (Phase F), with a de-risking spike in Phase 0 |
| Judging mainly weighs **what is built during the hackathon** | Pre-event: platform and core loop. At the event: Freshservice integration, audit, blast radius, polish. The README states what was built where, and the git history shows it |
| **Public GitHub repo + demo URL** due **26 Sep, 10:45** | Clear README from day one; demo URL approach in §2.3 |
| Working prototype + **business case / elevator pitch** (1–2 h max) | Separate deliverable `docs/business-case.md`, owned by teammates, reviewed by Vinay |
| Mentors available for Freshworks integration | Take Freshservice API questions to mentors early (§12) |
| Anthropic credits provided | LLM = Claude via tool use |
| Partner tracks (AWS, Sarvam, ElevenLabs, Wabby's AI) optional | Out of scope unless the core is finished; one stretch item (§7) |

### Timeline

| Window | Date | Hours (approx.) | Target |
|---|---|---|---|
| W1 | Mon 22 Sep, night | 4 | Phase 0 |
| W2 | Tue 23 Sep, day | 9 | Phases 1–2 |
| W3 | Tue 23 Sep, night | 4 | Phase 3 (first half) |
| W4 | Wed 24 Sep, until midday | 4 | Phase 3 done; freeze pre-event scope |
| — | Wed 24 Sep, afternoon | — | Business case review, **presentation practice** |
| E1 | Thu 25 Sep, 12:45–20:00 | ~5 net (lunch 13:15–14:15, mentor hours 15:40–16:15 sit inside this) | Phase F (Freshservice), Phase 4 (audit) |
| — | Thu 20:00 → Fri 08:00 | — | **Venue closes. Not an overnight hackathon** — everyone leaves at 20:00 |
| E2 | Fri 26 Sep, 08:00–10:45 | ~2.5 | Finish, README, **submission closes 10:45 sharp** |
| — | Fri 26 Sep, 10:45–15:00 | — | Judging round 1, shortlisting, finals on the main stage; closing 16:20 |

**Pre-event cut line:** Phase 3 working end to end by midday 24 Sep. If behind, drop Phase 3's
auto-rollback to "manual rollback button" rather than slipping into presentation practice.

---

## 1. Open questions (take to mentors / organisers)

| # | Question | Default until answered |
|---|---|---|
| Q1 | What counts as a "demo URL": a link judges open during judging, or one that works after the event? | Cloudflare quick tunnel from the laptop during judging (§2.3) |
| Q2 | Can Freshservice change **approvals** be requested and read through the API on the trial plan? The cookbook lists `approvals`, `changes` and `problems` under Freshservice REST v2, so probably yes — confirm with one call in the Phase 0 spike | If readable: approve inside Freshservice, SentinelOps polls and executes. If not: approve in SentinelOps and mirror the decision onto the change record (§6, Phase F) |
| Q3 | Freshservice API rate limit on the trial account | Poll no faster than every 15s; cache reads |
| Q4 | Is pre-built demo infrastructure (the monitored services) acceptable, given judging weighs event-built work? | Yes. It's the test subject, not the product. Disclose it in the README |

**Mentors assigned to SentinelOps AI:** Himanshu Singhal (PM, himanshu.singhal@freshworks.com),
Mohideen Ibrahim (Engineering, mohideen.ibrahim@freshworks.com).

**Other rules from the handbook:** build the same idea that was shortlisted (no pivoting);
judging puts majority weight on work done during the hackathon; Anthropic credits are $100
per participant valid 7 days from grant. Partner names: **Vobiz** (voice telephony),
**Wispr Flow** (voice prompting).

**Known live state (verified 2026-09-22):** both demo services fail 100% of requests. The
cause is confirmed: the old commit `43bbe24` (11 Sep) changed the `postgres` Service port to 5433
for laptop access, while `server.js` in both services hardcodes `port: 5432`. Phase 0
restores a healthy baseline; the same fault becomes simulator scenario `port_mismatch`.

---

## 2. Architecture

### 2.1 Components

```
 ┌──────────────── Laptop ─────────────────────────────────────────────┐
 │  Kubernetes (docker-desktop)                                         │
 │   order-service ─┐                                                   │
 │   payment-service┼──► postgres   (the MONITORED system)              │
 │   prometheus ◄───┘  scrapes /metrics every 5s                        │
 │        ▲                    ▲                                        │
 │        │ PromQL (pull)      │ k8s API (read + limited patch)          │
 │  ┌─────┴────────────────────┴────────┐                               │
 │  │ SentinelOps backend (FastAPI)      │── Claude API (agent)         │
 │  │ detector · agent · executor ·      │── Freshservice API v2 (poll) │
 │  │ freshservice sync                  │                              │
 │  └─────┬──────────────────────────────┘                              │
 │        │                     ┌──────────────────────┐                │
 │        │                     │ Frontend (React/Vite)│                │
 │        │                     └──────────┬───────────┘                │
 │        │           cloudflared tunnel ──┘ → public demo URL          │
 └────────┼────────────────────────────────────────────────────────────┘
          │ SQL + Realtime + Auth
   ┌──────▼──────────────┐
   │ Supabase             │  SentinelOps' OWN database
   └──────────────────────┘
```

**Hard rule:** the monitored Postgres (in-cluster) and SentinelOps' own database (Supabase)
are separate. SentinelOps must stay up while the system it watches is down.

### 2.2 Stack

| Layer | Choice | Notes |
|---|---|---|
| Frontend | React 19 + TypeScript, Vite, Tailwind, shadcn/ui, React Flow, Recharts, TanStack Query | Built fresh; old frontend not reused |
| Backend | Python 3.12, FastAPI, Pydantic v2, `uv`, httpx | Long-running process (continuous detection loop) |
| DB / Auth / Realtime | Supabase | Auth with roles; Realtime drives the live timeline |
| Telemetry | Existing Prometheus via HTTP API (PromQL) | Pull, no ingestion pipeline |
| Cluster access | `kubernetes` Python client, dedicated least-privilege ServiceAccount | |
| ITSM | **Freshservice API v2** (httpx, API-key basic auth) | Incidents, changes, notes, problems, solution articles |
| LLM | Claude Sonnet 5 (`claude-sonnet-5`) via tool use, Anthropic Python SDK | Hackathon credits |
| Tests | pytest, pytest-asyncio, respx (HTTP mocking); Vitest | Playwright dropped for time |
| Lint / types | ruff; `tsc --noEmit` | mypy and CI optional (time) |

Not used: Lambda/Amplify (a continuous loop and long agent runs don't fit; the cloud can't
reach the laptop cluster), Redis, Clerk (a second identity system), Firebase, DynamoDB, S3,
and our own vector knowledge base (replaced by Freshservice solution articles).

### 2.3 Demo URL (pending Q1)

- **Default:** everything runs on the laptop. `cloudflared tunnel --url http://localhost:5173`
  (a free "quick tunnel", no account needed) gives a public `https://…trycloudflare.com` link
  while the laptop is on. The frontend proxies `/api` to the backend, so one URL covers both.
- **If a permanent link is required:** frontend on Vercel pointing at a named Cloudflare
  tunnel for the backend. This only works while the laptop runs; a fully cloud-hosted variant
  would need a cloud cluster, which is out of scope.

---

## 3. Engineering principles

1. **Feature modules.** Each feature owns its router, service, schemas and DB access. No
   feature imports another's internals. Shared code lives only in `core/` or `shared/`.
2. **Events are the only cross-feature channel.** Features append to `events` and subscribe
   to event types. The same table is the audit log and the incident timeline.
3. **Integrations are adapters that subscribe to events.** Freshservice sync listens to
   events and mirrors them outward. If Freshservice is down, SentinelOps still works;
   failures emit `integration.failed` and are retried.
4. **The agent never produces commands.** It chooses from the action catalog with typed,
   validated parameters.
5. **Fail closed.** If policy, approval, kill switch or allow-list can't be confirmed, don't execute.
6. **Contracts first.** Pydantic schemas are the source of truth; frontend types are generated.
7. **Every phase is end to end,** and **no fake data presented as real.** Anything
   illustrative is labelled as such in the UI. (This is the main lesson from the old project.)

---

## 4. Repository structure

```
sentinalops-hackathon/
├── README.md                     # what it is, how to run, what was built when
├── docs/                         # plans, business case, demo script
├── services/                     # the MONITORED demo system (copied from old repo, fixed)
│   ├── order-service/  payment-service/
│   └── k8s/                      # deployments, services, prometheus, sentinelops RBAC
├── backend/
│   ├── pyproject.toml
│   ├── app/
│   │   ├── main.py               # create app, mount routers, start background loops
│   │   ├── core/                 # config, db, auth, events (bus + hash chain), logging
│   │   ├── integrations/
│   │   │   └── freshservice/     # client.py (API), sync.py (event subscribers + poller)
│   │   └── features/
│   │       ├── incidents/  detection/  investigation/  remediation/
│   │       ├── approvals/  execution/  topology/  audit/  simulator/
│   │       └── <feature>/        # router.py service.py schemas.py
│   └── tests/
├── frontend/
│   └── src/
│       ├── app/                  # router, layout, auth guard
│       ├── shared/               # ui/, api/ (client + generated types), lib/
│       └── features/<feature>/   # api.ts pages/ components/
└── supabase/migrations/
```

Adding a feature or integration: new folder → mount router / register subscribers → add
frontend route. Nothing else changes.

---

## 5. Contracts

### 5.1 Data model (Supabase)

| Table | Purpose | Key columns |
|---|---|---|
| `profiles` | Role | `id`, `role` ∈ viewer, responder, approver, admin |
| `services` | Service registry | `name`, `deployment`, `namespace`, `metric_prefix`, `depends_on text[]` |
| `incidents` | Incident state | `id`, `service`, `signal`, `severity`, `status`, `fingerprint`, `fs_ticket_id`, `opened_at`, `resolved_at` |
| `events` | **Append-only** log = audit = timeline | `id`, `incident_id`, `type`, `actor`, `payload jsonb`, `created_at`, `prev_hash`, `hash` |
| `proposals` | Remediation proposals | `id`, `incident_id`, `action`, `params`, `risk`, `approvals_required`, `status`, `fs_change_id` |
| `approvals` | Decisions | `proposal_id`, `user_id` or `source='freshservice'`, `decision`, `reason` |
| `executions` | Action runs | `id`, `proposal_id`, `status`, `before jsonb`, `result jsonb` |
| `settings` | Switches | `autonomy_paused` |

A partial unique index on `incidents(fingerprint) WHERE status <> 'resolved'` means at most one
open incident per problem. A trigger rejects UPDATE/DELETE on `events`.

### 5.2 Event types

`incident.opened` · `incident.acknowledged` · `investigation.started|step|completed|failed` ·
`remediation.proposed|approved|rejected|expired` · `execution.started|succeeded|failed` ·
`verification.passed|failed` · `rollback.started|succeeded|failed` · `incident.resolved` ·
`autonomy.paused|resumed` · `handler.failed` · `integration.synced|failed`

### 5.3 Action catalog (v1)

| Action | Params | Risk | Approvals | Rollback |
|---|---|---|---|---|
| `restart_service` | `service` | low | 1 | none needed |
| `scale_service` | `service`, `replicas` (1–5) | low | 1 | previous replica count |
| `update_config` | `service`, `key` ∈ allow-list, `value` | medium | 1 | previous value |
| `rollback_deploy` | `service` | medium | 1 | roll forward |
| `set_service_port` | `service` (k8s Service), `port` ∈ {5432} | medium | 1 | previous port |

Each action is one file implementing `Params`, `risk()`, `preview()`, `execute()`,
`rollback(before)` and `verify_query()`. Allow-list: namespace `default`; deployments
`order-service`, `payment-service`; Service `postgres` (port changes only).

### 5.4 API surface

```
GET  /api/health
GET  /api/incidents  ·  GET /api/incidents/{id}  ·  POST /api/incidents/{id}/acknowledge
POST /api/incidents/{id}/investigate  ·  GET /api/incidents/{id}/events
GET  /api/incidents/{id}/metrics  ·  GET /api/incidents/{id}/blast-radius
GET  /api/approvals?status=pending  ·  POST /api/approvals/{id}/approve|reject
GET  /api/topology  ·  GET /api/audit  ·  GET /api/audit/verify
POST /api/simulator/scenarios/{name}/inject|reset
POST /api/settings/autonomy
GET  /api/integrations/freshservice/status
```

Frontend routes: `/incidents`, `/incidents/:id` (overview · timeline · metrics · blast radius),
`/approvals`, `/topology`, `/audit`, `/simulator`, `/login`.

---

## 6. Phases

Each phase lists: **goal**, **build** (with explanation), **acceptance**, **tests**, **debugging**.
A phase is done only when its acceptance criteria pass end to end on the laptop.

---

### Phase 0 — Foundation, healthy baseline, Freshservice spike  *(W1, ~4 h)*

**Build:**
1. **Repo.** `git init`, `.gitignore`, README skeleton, public GitHub repo. Stage explicit
   paths only; commit often (the history shows when things were built).
2. **Demo system.** Copy `demo-infra` manifests and service code from the old repo into
   `services/`. Fix the baseline: the `postgres` Service becomes ClusterIP on **5432** (the
   backend doesn't need direct DB access). Keep Prometheus exposed on 9090. **Add pool
   metrics** to both services: `db_pool_total`, `db_pool_idle` and `db_pool_waiting` gauges from
   the `pg` Pool. Without them, pool exhaustion can't be diagnosed with evidence.
   Rebuild the images and redeploy. Confirm the error rate is ~0%.
3. **Least-privilege identity.** ServiceAccount `sentinelops-agent` with a Role in `default`:
   `get/list/watch` on pods, pods/log, deployments, replicasets and services; `patch` on
   deployments and services; `create` on pods/exec (for the connectivity probe). Generate a
   kubeconfig for it. The backend never uses the admin context.
4. **Supabase.** One dev project; migrations for §5.1; Realtime on `events` and `incidents`.
5. **Backend skeleton.** FastAPI, settings from `.env`, structured JSON logging, and
   `/api/health` reporting Supabase, Prometheus, k8s and Freshservice separately.
6. **Frontend skeleton.** Vite + TS + Tailwind + shadcn, app shell, router, Supabase auth
   (login/signup, `profiles` row created by trigger), route guard.
7. **Freshservice spike (de-risk).** Trial account + API key. From a script: create an
   Incident ticket, add a note, create a Change, read it back and inspect its approval-related
   fields. Record the answers to Q2 and Q3 in `docs/freshservice-notes.md`.

**Acceptance:** health is green on all four; login works; the agent kubeconfig can patch
deployments but can't delete them or read `kube-system`; the spike script creates and reads a
ticket and a change.

**Tests:** JWT verification; `events` rejects UPDATE/DELETE.

**Debugging:** if a service is still failing after the baseline fix, run
`kubectl logs deploy/order-service` and the in-pod TCP probe to 5432.

---

### Phase 1 — Walking skeleton: fault → detection → live incident  *(W2, ~4 h)*

**Build:**
1. **Event bus + hash chain (`core/events.py`).** `emit()` inserts (serialised by an
   advisory lock; `hash = sha256(prev_hash ‖ canonical_json(row))`), then runs subscribers,
   each isolated in try/except → `handler.failed`.
2. **Service registry seed:** order, payment and postgres with metric prefixes and dependencies.
   Only real services. No illustrative extras.
3. **Detector loop** (every 15s): per-service error ratio
   `sum(rate({p}_errors_total[1m])) / sum(rate({p}_requests_total[1m]))`; open an incident when
   it's > 5% for 2 consecutive ticks; no traffic (NaN) is not an incident; dedup by fingerprint.
4. **Simulator:** scenario interface `inject()`/`reset()`. Scenarios: `port_mismatch`
   (Service → 5433) and `pool_exhaustion` (`max_connections` → 5, as in the old scripts,
   reimplemented through the k8s client rather than shell scripts). Admin only.
5. **UI:** incident list with triage tabs (Triggered / Acknowledged / Resolved), live via
   Realtime; simulator page.

**Acceptance:** Inject `port_mismatch` → a Triggered incident appears within 45s without
refresh; Reset → healthy.

**Tests:** detection rule fixtures (below, above ×1, above ×2, NaN); dedup; hash chain
(valid, tampered); subscriber failure isolation.

**Debugging (layer by layer):** PromQL in the Prometheus UI → `detector.tick` logs →
`incidents` table → Realtime websocket frames → UI.

---

### Phase 2 — Investigation agent  *(W2, ~5 h)*

**Build:**
1. **Read-only tools:** `get_error_ratio`, `query_metric`, `get_logs`, `get_pods`,
   `get_rollout_history`, `get_dependencies`, `get_service_spec`, `check_connectivity(from,
   host, port)` (TCP probe via pod exec; ports allow-listed), `get_db_pool_stats`.
2. **Agent loop:** triggered by `incident.opened` or a manual re-run. Claude tool use, at most
   10 tool calls, 120s limit. Each call is emitted as `investigation.step` (the reasoning
   trail, and the debugging record).
3. **Structured result:** `{hypothesis, confidence, evidence: [step_event_id], ruled_out}`,
   validated with Pydantic. Claims without evidence are rejected; one retry, then
   `investigation.failed`.
4. **UI:** incident detail with a header (severity, status, service, duration), a timeline of
   all events with expandable evidence, and a metrics tab (stacked charts, shared time axis,
   synced crosshair).

**Acceptance:** `port_mismatch` → the hypothesis names the port mismatch and cites the timeout
logs plus the connectivity probe (5432 closed, 5433 open). `pool_exhaustion` → it cites pool
waiting > 0 and `max_connections=5`. Both appear within 90s.

**Tests:** tools against recorded fixtures; loop limits. **Agent evals** (`-m eval`, on demand):
recorded scenario outputs, assert on structured fields, ≥ 4/5 correct per scenario.

**Debugging:** read the `investigation.step` events in order; find the first misleading or
missing tool result. Improve the tool before the prompt.

---

### Phase 3 — Safety core  *(W3–W4, ~8 h)*

**Build:**
1. **Proposal:** after diagnosis, the agent may call `propose_action(action, params,
   rationale)`. The server validates the catalog entry, params and allow-list. The agent has
   no write tools.
2. **Policy engine:** a pure, table-driven function → `(risk, approvals_required)`. Unknown →
   reject.
3. **Preview:** a live before/after diff from the k8s spec.
4. **Approval (enforced):** `approver` role required. Atomic transition
   `UPDATE … SET status='approved' WHERE id=$1 AND status='pending'`, where 0 rows → 409.
   Proposals expire after 15 min or when the incident resolves.
5. **Executor:** triggered only by the `remediation.approved` event, never by an HTTP call.
   Re-checks kill switch, allow-list and proposal status; records `before`; runs with the agent
   ServiceAccount.
6. **Verifier:** polls `verify_query` every 10s for up to 2 min. Pass → resolve the incident.
   Fail → `rollback(before)` and back to Triggered.
7. **Kill switch** in the top bar (admin).
8. **UI:** the approval card, "remediation as a pull request": action → target, risk and
   approvals needed, diff, evidence links, blast radius, verify condition, rollback plan,
   Reject / Approve (`A`/`R`).

**Acceptance:** `port_mismatch` → propose `set_service_port(postgres, 5432)` → approve → the
error ratio is < 1% within 2 min → auto-resolved. A forced verification failure → rollback.
With the kill switch on → refused. A concurrent double approve → one execution. **There is no
path to execution without an approved proposal** (the old project's critical flaw).

**Tests (highest value):** policy table; allow-list refusals (`kube-system`, unknown
deployment, disallowed port); param validation; approval race; role check (403 for a
viewer); kill switch; execute → rollback restores the spec (cluster test).

**Debugging:** proposal status → approvals rows → `autonomy_paused` → executor logs →
`executions.result` → `kubectl rollout history`.

> **Pre-event freeze (24 Sep, midday):** Phases 0–3 done. Tag `v0-pre-event`. Everything after
> this tag is hackathon-built and listed as such in the README.

---

### Phase F — Freshservice integration  *(E1, ~4 h — decided 23 Sep, doing it regardless of Track 3 rules)*

**Goal:** Freshservice is the system of record that IT teams already use. SentinelOps works
*through* it, not beside it.

| SentinelOps | Freshservice | Direction |
|---|---|---|
| `incident.opened` | Create **Incident ticket** (priority from severity), store `fs_ticket_id` | → |
| `investigation.completed` | Private **note** on the ticket: hypothesis + evidence summary + link | → |
| `remediation.proposed` | Create a **Change** (type Normal/Emergency by risk), linked to the ticket; description = diff + rollback plan | → |
| Approval | Q2 answered **yes**: poll the change approval status every 15s; an approval there emits `remediation.approved` with `source='freshservice'`. Q2 **no**: approve in SentinelOps, mirror the decision as a change status update + note | ← / → |
| `execution.*`, `verification.*` | Notes on the change + ticket; update change status | → |
| `incident.resolved` | Resolve the ticket; create a **Problem** record with the AI-drafted postmortem | → |
| Runbooks | Agent tool `search_solution_articles(query)` reads Freshservice solution articles | ← |

**Build:** `integrations/freshservice/client.py` (typed httpx client, retries with backoff,
rate-limit aware); `sync.py` (event subscribers plus approval poller); an integration status
page; links from the incident page to the ticket and change.

**Acceptance:** the full loop creates a ticket, a note, a change, an approval (via
Freshservice if Q2 = yes), execution notes, a resolved ticket and a problem, all visible in the
Freshservice UI. With Freshservice unreachable, SentinelOps still completes the loop and shows
`integration.failed` with retries.

**Tests:** client against mocked responses (respx): success, 429 rate-limit, 5xx retry;
subscriber mapping (event → request payload); poller emits approval exactly once.

**Debugging:** every outbound call is logged with the Freshservice ID and status code; the
integration page shows the last 20 calls.

---

### Phase 4 — Audit trail  *(E1, ~2 h)*

`GET /api/audit/verify` walks the chain → `{valid, checked, first_broken_id}`. The audit page
has a filterable table, a **Verify chain** badge, and a JSON-lines export.
**Acceptance:** green badge; a manual DB edit turns it red and names the row.
**Tests:** 0/1/N events; tampered payload; deleted row; reordered rows.

---

### Phase 5 — Depth  *(E2, only if time; each item independent)*

1. **Blast radius** (~1.5 h): graph walk over `depends_on`, coloured by live error ratio (React Flow).
2. **Change markers** (~1 h): rollout history as vertical lines on the charts.
3. **Stretch, partner track:** Wabby's AI voice call to the on-call approver for high-risk
   proposals ("press 1 to open the approval"). Only after everything else is done.

---

### Submission  *(E2, ~1.5 h, non-negotiable)*

README (problem, what it does, architecture diagram, how to run, **built before / built at
the event**, screenshots), updated project description, business case linked, demo URL
tested from a phone on mobile data, final push before **10:45**.

---

## 7. UI system

Patterns borrowed, not visual designs copied:

| Pattern | Reference | Used in |
|---|---|---|
| Keyboard-first, ⌘K palette, dense lists | Linear | App shell |
| Triage states | PagerDuty | Incident list |
| Single timeline plus header metadata | incident.io | Incident detail |
| Shared time axis, synced crosshair | Datadog | Metrics |
| Deploy markers on charts | Grafana / Datadog | Metrics |
| Health-coloured service map | Datadog | Blast radius |
| Monospace logs, status dots | Vercel | Logs, executions |
| **Remediation as a pull request** | GitHub PR review | Approval card (original) |

Rules: neutral greys plus one accent; status colours carry meaning only; Inter/Geist plus
monospace for machine output; 13–14px body; 1px borders; no gradients, glass effects or emoji;
tables over card grids; every empty state says what to do next; **nothing fake**, and anything
illustrative is labelled.

---

## 8. Testing strategy

| Level | Tool | What | When |
|---|---|---|---|
| Unit | pytest, vitest | Policy, allow-list, hash chain, detection rules, Freshservice mapping | Before each commit |
| Integration | pytest + dev Supabase (separate schema) | Approval race, event isolation, API ↔ DB | End of each phase |
| Cluster | pytest `-m cluster` | Inject/reset, execute/rollback | End of Phases 1, 3 |
| Agent evals | pytest `-m eval` | Diagnosis on recorded scenarios | After tool/prompt changes |
| Manual E2E | Demo script (§10) | Full path | End of each phase + 3× before judging |

Rules: safety tests pass before the executor may touch the cluster; bug fixes start with a
failing test; verify the target (Supabase project, kubeconfig) before any destructive action.

---

## 9. Schedule and cut lines

| Phase | Window | Effort | Built |
|---|---|---|---|
| 0 Foundation + Freshservice spike | W1 | 4 h | pre-event |
| 1 Walking skeleton | W2 | 4 h | pre-event |
| 2 Investigation | W2 | 5 h | pre-event |
| 3 Safety core | W3–W4 | 8 h | pre-event |
| F Freshservice integration | E1 | 4 h | **at event** |
| 4 Audit | E1 | 2 h | **at event** |
| 5 Depth | E2 | 1–3 h | at event, optional |
| Submission | E2 | 1.5 h | at event |

**Cut lines:** pre-event, Phase 3 is mandatory (drop auto-rollback to a manual button if
behind). At the event, Phase F is mandatory and comes first; Phase 4 next; Phase 5 only with
time left. Never cut the submission block.

**Teammates (parallel, non-code):** business case (§11), pitch deck, Freshservice trial setup
and seeding a few solution articles, demo rehearsal as "the judge asking hard questions".

---

## 10. Demo script (4 minutes)

1. Green dashboard; the Freshservice tab open beside it. "A real Kubernetes cluster, connected to Freshservice."
2. Inject `port_mismatch`. Errors spike on synced charts; the incident appears live, **and
   a Freshservice ticket appears**.
3. The investigation streams in with evidence (connectivity probe: 5432 closed, 5433 open).
4. The approval card, plus the matching **Freshservice Change**. "The AI chose from a catalog; it
   can't write commands. Approval goes through your existing change process."
5. Approve. Execute → verify → resolved. The ticket resolves, and a Problem record with the postmortem appears.
6. Audit: Verify chain is green; tamper with a row → red.
7. Kill switch: execution refused.
8. Close: business case in one line, then the roadmap (runners inside customer networks, more
   action adapters).

---

## 11. Business case (separate doc, ≤ 2 h)

`docs/business-case.md`, following the organisers' outline: problem · target customer ·
competitive landscape · solution · value proposition · pricing · go-to-market · costs ·
success measures · risks and assumptions. Source material: the earlier conversation on
customers (mid-size engineering orgs and regulated industries; buyer = VP Eng / Head of
Platform) and competitors (PagerDuty, Datadog Bits AI, incident.io, Rootly, Resolve.ai, etc.:
they diagnose; we act safely through the customer's own change process).

---

## 12. Debugging playbook

Method: reproduce → locate the layer → one hypothesis → test → fix → regression test. Record
hypotheses that were ruled out.

| Symptom | First checks |
|---|---|
| No incident after inject | PromQL in the Prometheus UI → detector logs → `incidents` → Realtime frames |
| Duplicate incidents | fingerprint index; overlapping ticks |
| Agent wrong/slow | `investigation.step` events in order; tool output quality; token usage |
| Approved but not executed | proposal status → kill switch → executor logs → `executions.result` |
| Executed but not resolved | verify query in Prometheus; `kubectl rollout status` |
| Freshservice ticket missing | integration page (last calls, status codes); API key; rate limit (429) |
| Freshservice approval not picked up | poller logs; the change's approval field (see spike notes); `fs_change_id` stored? |
| Audit badge red unexpectedly | concurrent inserts without the lock; canonical JSON of timestamps |
| UI stale | Realtime publication; subscription filter; query invalidation |
| Demo URL down | `cloudflared` process running? Vite proxy to `/api`? Test from mobile data |

---

## 13. Workflow and definition of done

- Work on `main`; commit small and often with clear messages; stage explicit paths only.
- Secrets only in `.env` (gitignored); `.env.example` lists the keys.
- **Done** = acceptance passes end to end, tests are green, behaviour is explainable from the
  timeline/logs, and this document is updated if anything changed.

---

## 14. Risks

| Risk | Mitigation |
|---|---|
| Freshservice API can't do approvals | Q2 fallback designed in; ask a mentor on day 1 morning |
| Freshservice rate limits during the demo | 15s polling, caching, only calls driven by events |
| Venue network | Test on a phone hotspot; **record a backup demo video on 24 Sep** and again after Phase F |
| LLM latency on stage | Temperature 0, tool-call cap, evals; backup video |
| Laptop memory (~3.9 GB for Docker) | Resource limits on services; close other apps |
| Scope creep / fatigue (solo) | Cut lines above; sleep on the night of the 25th |
| Judges question pre-built work | README "built before / at event" section; tag `v0-pre-event` |
