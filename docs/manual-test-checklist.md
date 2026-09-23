# Manual test checklist (things only Vinay can check)

Automatic tests cover logic; this file tracks what needs a human at the screen.
Tick items off as you go, and note anything that looks wrong — that feedback shapes the UI.

Legend: ⬜ waiting · ✅ passed · ⚠️ passed with a comment · ❌ failed

---

## Phase 0 — foundation ✅ (22 Sep)

- ✅ Sign up, confirm email, sign in
- ✅ Sidebar shows `role: admin` (proves the backend verified the token and read the role)
- ✅ Health dots: database / prometheus / kubernetes green, freshservice grey

## Phase 1 — break → detect → live incident ✅ (22 Sep)

- ✅ Simulator lists two scenarios, both "Healthy"
- ✅ "Break it" on port mismatch → incidents appear by themselves within ~35s, no refresh
- ✅ Acknowledge moves an incident to the Acknowledged tab
- ✅ Reset → resolve → list is clean

## Phase 2 — the investigation agent ⬜ (ready to test)

Start: everything running, system healthy, Simulator shows both scenarios "Healthy".

- ⬜ **Break it** on *Database port mismatch* → incident appears (~35s)
- ⬜ Click the incident **title** → detail page opens
- ⬜ Timeline fills in by itself: `Investigation started` → several `Tool call` rows → `Root cause found`
- ⬜ The conclusion names the **port mismatch** and reads clearly
- ⬜ **Click a tool call row** → expands to show the raw arguments and result
- ⬜ **Click an evidence chip** (`#123`) → jumps to that tool call and highlights it
- ⬜ "Ruled out" lines are shown and make sense
- ⬜ **Metrics tab**: three charts, same time axis, red "opened" marker, hover shows values
- ⬜ **Re-investigate** button runs a second investigation (costs ~5 cents)
- ⬜ Reset the scenario → Resolve the incidents → list is clean
- ⬜ Repeat with *Database connection limit too low* (slower: Postgres restarts, ~60s)

Watch for: anything ugly, slow, confusing, or wrongly worded. Judges read this page most.

## Phase 3 — safety core ⬜ (being built)

- ⬜ After the diagnosis, a **proposed fix** appears on the incident page and on Approvals
- ⬜ The card shows action, target, risk, the before/after change, evidence, verify condition, rollback plan
- ⬜ **Nothing runs before approval** — confirm the cluster is untouched while it waits
- ⬜ **Approve** → execution runs → errors drop → incident resolves itself
- ⬜ Timeline shows execution and verification steps
- ⬜ **Reject** on a second run → nothing executes, incident stays open
- ⬜ **Kill switch** on → approving is refused with a clear reason
- ⬜ A non-approver account cannot approve (create a second account to check)

## Phase 4 — audit ⬜ (built 23 Sep)

- ⬜ Audit page lists every event with category, actor, incident, time and hash
- ⬜ **Verify chain** badge is green and names the number of events checked
- ⬜ Click a row → payload, full actor, previous hash and this hash
- ⬜ A row's **previous hash** equals the hash of the row below it (the chain, by eye)
- ⬜ Category and actor filters narrow the table; counts look right
- ⬜ **Older events** pages backwards, **Back to newest** returns
- ⬜ **Export chain** downloads `sentinelops-audit.jsonl`
- ⬜ The tamper demo below turns the badge red and names the row

### The tamper demo

The point: the record cannot be edited, and if someone with database access forces it,
the next check says so. Run this in the Supabase SQL editor.

**1. Prove it is append-only.** This fails, which is the first half of the demo:

```sql
update public.events set actor = 'somebody-else' where id = (select max(id) from public.events);
-- ERROR: events are append-only
```

**2. Force it anyway**, as only a database owner could. Note the id you pick:

```sql
select id, payload from public.events order by id desc limit 5;  -- pick one, note its payload

alter table public.events disable trigger events_no_update;
update public.events set payload = '{"tampered": true}' where id = <ID>;
alter table public.events enable trigger events_no_update;
```

**3. Press Verify chain.** The badge turns red, names event `<ID>`, and that row is
highlighted in the table.

**4. Put it back** (the hash is set on insert and is untouched by an update, so restoring
the original payload restores the match):

```sql
alter table public.events disable trigger events_no_update;
update public.events set payload = '<THE ORIGINAL PAYLOAD>'::jsonb where id = <ID>;
alter table public.events enable trigger events_no_update;
```

Press **Verify chain** again — green. Do this run-through once before the event so the
SQL is in your clipboard history and you are not typing it in front of judges.

## Cross-cutting, before the event ⬜

- ⬜ Full demo run from a cold start, 3 times, on the laptop you'll use
- ⬜ Demo on a phone hotspot (venue Wi-Fi will be bad)
- ⬜ Backup demo video recorded
- ⬜ Decide: services at 2 replicas or 1 (RAM on the demo laptop)
