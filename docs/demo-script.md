# The 5-minute pitch

The loop takes 2–3.5 minutes to run and you cannot speed it up. So the script is built
around one rule:

> **Press Break before you say your first word.** Then talk while it detects.

Everything else is choreography around that.

---

## Before you start

**Three windows, arranged in advance.**

| Window | Showing |
|---|---|
| **Browser (main, full screen)** | SentinelOps on `/simulator`, logged in as an **approver** |
| **Terminal (small, visible)** | `kubectl` ready, nothing typed |
| **Browser tab 2** | Prometheus at `localhost:9090` with the detector's query already typed |

**Checklist, five minutes before:**

- All six pods `Running` (`kubectl get pods`)
- `/api/health` — database, prometheus, kubernetes green
- No open incidents; both services at 0% errors
- Simulator shows `port_mismatch` as **Healthy**
- Backup video open in a tab you can reach in one click

---

## The script

### 0:00 — Press Break. Then start talking.

Click **Break it** on *Database port mismatch*, then look up at the room. Don't wait for it.

> "Every ops team now has an AI that reads their logs and tells them what's wrong. That part's
> solved.
>
> What nobody has is an AI they'll let **touch** production. Because the failure mode isn't a
> bad answer — it's taking down the business at 3am.
>
> I just broke something. While it notices, let me tell you what it's watching."

### 0:20 — What it's watching (fill the detection gap)

Switch to the terminal. Type it live:

```bash
kubectl get pods
```

> "This is a real Kubernetes cluster. Two services talking to a real Postgres database, and
> Prometheus collecting metrics from all of them every five seconds. Nothing here is mocked.
>
> What I broke is the database's network port — I moved it from 5432 to 5433 while both
> services still dial 5432. That's not a flag in my software. It's a real change to the
> cluster, and it's the same mistake that took this system down for real two weeks ago.
> I made it myself."

Switch to the Prometheus tab, hit Enter on the query:

> "This is Prometheus — not my app. Error rate, live."

The line should be climbing.

### 0:50 — The incident opens

Back to SentinelOps. The incident should be there.

> "Detection is one rule: more than five percent of requests failing, on two consecutive
> checks, fifteen seconds apart. Two checks, so one blip doesn't wake anyone. And zero traffic
> isn't an outage — nothing out of nothing is fine."

Click the incident title.

### 1:10 — The investigation, live

The timeline is filling. **This is the part to slow down for.**

> "Now an agent investigates. It has nine tools — pod logs, pod status, deployment config, the
> Service definition, rollout history, the database's own settings, and a live network probe
> from inside a pod. Every one of them is **read-only**. It can look. It cannot touch.
>
> And it has a rule: it is not allowed to conclude anything it can't prove. Watch."

When the root cause lands, click an **evidence chip**:

> "It says the Service is on 5433 while the client dials 5432 — and here's the raw tool output
> it's citing. Every claim on this page links to the data underneath it.
>
> That matters because of what happens next. The person approving isn't trusting the AI.
> They're reading its working."

### 2:10 — The proposal

> "Here's the fix it wants. And this is the part I'd argue is the actual product.
>
> The AI did not write a command. It picked one of **four** actions I allow — restart, scale,
> change a Service port, change a database connection limit — and filled in parameters that get
> validated and checked against an allow-list before anything happens.
>
> It tells you the exact change, the blast radius, how it'll be verified, and how it gets undone."

### 2:40 — Approval

> "And it stops. Nothing has touched the cluster."

*(If Freshservice is connected: switch to it.)*
> "This is the same fix as a **change request in Freshservice**. The approval happens in the
> company's real change-management process — their rules, their approvers, their audit
> requirements. Their process is what gives the AI permission. Not a button I built."

Click **Approve**.

### 3:00 — Execution and proof

Switch to the terminal:

```bash
kubectl get svc postgres -o jsonpath='{.spec.ports[0].port}'
```

> "5432. Fixed. And Kubernetes records who did it —"

```bash
kubectl get svc postgres -o jsonpath='{range .metadata.managedFields[*]}{.manager}{" "}{.time}{"\n"}{end}'
```

> "`sentinelops-simulator` broke it. `sentinelops-agent` fixed it. That's the cluster's own
> record, not my database.
>
> It's now verifying recovery for two minutes. If the error rate doesn't come down, it undoes
> the change automatically and hands it back to a human."

Prometheus tab — the line should be falling.

> "There's the recovery, in a tool that has no idea SentinelOps exists."

### 3:50 — The audit page

Go to `/audit`.

> "Every step of that is here. Append-only — the database physically refuses updates and
> deletes. And each event's fingerprint covers the one before it, so changing anything breaks
> everything after it."

Click **Verify chain** → green.

> "That recomputed all of it just now. **Tamper-evident doesn't mean nobody can change the
> record. It means nobody can change it without it showing.**"

### 4:20 — Close

> "Two independent fences make this safe. Its cluster identity **cannot delete or create
> anything** — I can prove that in one command. And it can't express a dangerous action in the
> first place, because it picks from four. Either one alone would stop a disaster.
>
> Gartner made AI SRE a category in January. Resolve AI raised $125 million in February. But
> the market's own summary is that autonomous *investigation* works and autonomous
> *remediation* is still supervised — because nobody's solved trust.
>
> I'm not claiming better AI. The AI is Claude, same as everyone's. What I built is the
> permission structure that makes it safe to say yes."

Stop. Don't add anything.

---

## When things run late

**The loop is slower than the slot.** Verification takes up to two minutes and will often still
be running at 5:00. That's fine — say *"it's verifying now"* and move to the audit page. Never
stand in silence waiting for a green tick.

**If the incident hasn't opened by 0:50:** keep going with the cluster tour. Check back at 1:20.
The detector needs two ticks; sometimes it's three.

**If the investigation stalls:** open a **previous** incident — *"here's one from earlier that
completed"* — and carry on. Have one resolved incident in the list before you start.

**If nothing works:** the backup video. Say it plainly: *"the laptop's not cooperating, here's
the recorded run"* — and keep the same narration. Judges forgive hardware. They don't forgive
panic.

---

## Things not to do

- **Don't name the stack.** React, FastAPI, Tailwind — costs eight seconds, tells them nothing.
- **Don't say "autonomous" unqualified.** It invites *"so it acts without asking?"*, which is the
  opposite of the point. Say **governed autonomy**, or just describe it.
- **Don't read the timeline aloud.** Point at two things, not ten.
- **Don't apologise for anything unfinished.** If they ask, answer straight and move on.
- **Don't fill silence with detail.** The pauses after "That part's solved" and after
  "without it showing" are doing work.

---

## The three questions that always come

**"What stops it doing something destructive?"**
> "Two independent fences. Its cluster identity physically cannot delete or create anything —
> one command proves it. And it can't express a dangerous action in the first place: four
> actions, validated parameters, an allow-list of targets. Then verification and automatic
> rollback afterwards."

**"What if the diagnosis is wrong?"**
> "A finding is rejected unless it cites the tool output proving it, and every claim links to
> that raw output. If a fix is approved and doesn't work, it's undone automatically within two
> minutes and a human gets it back."

**"Is this a real cluster or a mock?"**
> "Real Kubernetes, four real workloads, a real database, real Prometheus. The simulator changes
> the cluster itself — the agent can't see how it was broken, only the symptoms. And I can show
> you any layer of it live."
