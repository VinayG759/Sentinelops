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

## Phase 4 — audit ⬜

- ⬜ Audit page lists every event with actor and time
- ⬜ "Verify chain" badge is green
- ⬜ After I tamper with a row in the database, the badge turns red and names the row

## Cross-cutting, before the event ⬜

- ⬜ Full demo run from a cold start, 3 times, on the laptop you'll use
- ⬜ Demo on a phone hotspot (venue Wi-Fi will be bad)
- ⬜ Backup demo video recorded
- ⬜ Decide: services at 2 replicas or 1 (RAM on the demo laptop)
