# SentinelOps AI — The Plan in Plain Words

> The easy-to-read version of [implementation-plan.md](implementation-plan.md).
> Same plan, simpler words. If the two ever disagree, the technical one wins.
> Update both together.

---

## What we're building, in one breath

A small pretend company runs on your laptop: an **order service**, a **payment service**,
and a **database** they share. SentinelOps watches it. When something breaks, SentinelOps:

1. **notices** (detect),
2. **figures out why**, and shows its proof (investigate),
3. **suggests a fix** from a fixed menu of safe fixes (propose),
4. **waits for a human to say yes** (approve),
5. **applies the fix** (execute),
6. **checks that it actually worked**, and undoes it if not (verify / rollback),
7. **writes everything in a record book nobody can secretly edit** (audit).

And now, because the hackathon requires it: **all of this shows up in Freshservice**, the
tool IT teams already use to track problems and approve changes.

**What makes us different:** competitors mostly stop at step 2. We go to step 7, safely,
and through the customer's own approval process.

---

## What the organisers told us, and what it means

| They said | So we… |
|---|---|
| The handbook says Freshworks integration is required for Tracks 1 and 2, **not** for Track 3 — and we're Track 3. The spoken briefing said it was required for everyone. | **We're doing it anyway** (decided 23 Sep). "The AI works through the approval process you already use" is a strong story, and it covers us if the briefing is right |
| Judges mostly score **what's built at the event** | Build the engine now; build the Freshservice part, the record book and the polish at the event. The README says honestly what was built when |
| Need a **public GitHub repo + demo link** by **26 Sep, 10:45** | Write the README from day one; make a public link with a free tunnel (see below) |
| Need a short **business case** (1–2 hours, no more) | Your friends can own this; you review it |
| Anthropic credits provided | Use Claude as the AI |
| Voice, AWS and Indian-language tracks are optional | Ignore them unless everything else is done |

---

## Why Freshservice fits perfectly

Freshservice already has the things SentinelOps needs. We plug into them instead of
reinventing them:

| When SentinelOps… | In Freshservice… |
|---|---|
| detects a problem | an **Incident ticket** appears |
| finishes investigating | a **note** with the AI's findings is added to the ticket |
| proposes a fix | a **Change request** is created (the standard way companies approve changes to live systems) |
| gets approval | ideally the approval happens **inside Freshservice**, and SentinelOps notices it |
| applies and checks the fix | notes are added and the change is updated |
| resolves the incident | the ticket closes, and a **Problem** record holds the "what happened" report |
| needs a how-to guide | it searches Freshservice's **knowledge articles** |

**One thing we don't know yet:** whether a program can *read approvals* out of Freshservice.
If it can, the approver never opens SentinelOps — they approve in Freshservice, and our system
notices and runs the fix. If it can't, the approval happens in SentinelOps and we copy the
decision into the Freshservice record so the paperwork is still complete. The Freshworks
cookbook lists approvals in its API, so the first version is likely. We'll confirm with one
test call, not by asking anyone.

**Your mentors** (from the assignment sheet): Himanshu Singhal (product,
himanshu.singhal@freshworks.com) and Mohideen Ibrahim (engineering,
mohideen.ibrahim@freshworks.com).

---

## The "demo link" problem

Judges want a link. But our system runs on your laptop, next to the Kubernetes cluster.

**Solution:** a free tool called **Cloudflare Tunnel** gives your laptop a public web
address (like `https://something.trycloudflare.com`) for as long as it's running. Anyone
with the link sees the app. **Ask a mentor** whether the link must keep working after the
event. If it must, we'll need a different approach.

---

## A real bug is already waiting for us

Both services are currently failing **every request**. We traced exactly why: on
11 September, a change in the old project moved the database's "front door" to number
**5433**, but the services are hard-wired to knock on **5432**.

In the new build, we first **fix it** so the pretend company is healthy. Then we turn this
same mistake into a **"break it" button**, so SentinelOps can find and fix it live on stage.

---

## The rules we build by

1. **Each feature lives in its own folder** and never reaches into another's.
2. **Features talk by leaving notes** in one shared list (the **events**). If one feature
   breaks, the others keep working. That list is also the record book and the timeline.
3. **Freshservice is a plug-in that listens to the notes.** If Freshservice is down,
   SentinelOps keeps working and retries later.
4. **The AI never writes its own commands.** It picks from a menu and fills in blanks.
5. **When in doubt, don't act.**
6. **Nothing fake pretending to be real.** The old project showed hardcoded "SOC2 PASSED"
   checks and invented services. In the new build, anything illustrative is clearly labelled.
   One sharp judge's question shouldn't be able to break the story.

---

## Your timeline

| When | What |
|---|---|
| **Tonight (Mon 22)** | Phase 0: set up, fix the pretend company, test Freshservice |
| **Tue 23, day** | Phases 1–2: notice problems live, and the AI detective |
| **Tue 23, night → Wed 24, midday** | Phase 3: the safety system, then **draft the README** and test the demo link. **Freeze here** |
| **Wed 24, afternoon** | Review the business case, **practise the presentation** |
| **Thu 25, 12:45–20:00 (event)** | Phase F: Freshservice. Then Phase 4: the record book. Lunch and mentor hours sit inside this, so it's about 5 real hours |
| **Thu 20:00 → Fri 08:00** | **Venue closes — it's not an overnight hackathon.** Everyone leaves |
| **Fri 26, 08:00–10:45** | Finish the record book, add the Freshservice part to the README, **submission closes at 10:45 sharp** |
| **Fri 26, 10:45 onwards** | Judging, shortlist, finals on the main stage, closing at 16:20 |

---

## The phases

For each one: **what we build**, **what you'll see**, and **how we check it**.

### Phase 0 — Set up  *(tonight, ~4 hours)*

- A fresh project and a public GitHub repo. **Commit often.** The history is your proof of
  what was built when.
- Copy the pretend company's setup from the old project, **fix the port bug**, and add
  three new numbers the services report: how many database connections they have, how many
  are free, and **how many requests are waiting**. Without that third number, the AI can't
  *prove* a "too many connections" problem.
- A **restricted key** for SentinelOps on Kubernetes: it can look at and adjust our
  services, but can't delete anything or touch the system core.
- The Supabase database, login/sign-up, and an empty app.
- **The Freshservice test:** a small script that creates a ticket, adds a note, creates a
  change and reads it back. That answers "can we do approvals?" before we build on it.

**You'll see:** both services healthy (0% errors), login working, and a test ticket in Freshservice.

### Phase 1 — Break it and see it  *(Tue, ~4 hours)*

- The events list with tamper-proofing: each note carries a fingerprint of the one before,
  like a wax seal.
- The **detector:** every 15 seconds it asks Prometheus "what share of requests are failing?"
  More than 5%, twice in a row → incident.
- The **simulator:** "Break it" / "Fix it" buttons for two scenarios: the port bug, and
  "too many connections" (the database only allows 5).
- The **incident list**, updating live.

**You'll see:** press "Break it", and within 45 seconds an incident appears by itself.

### Phase 2 — The detective  *(Tue, ~5 hours)*

- **Look-only tools** for the AI: read metrics, logs, pods, recent changes, dependencies,
  connection-pool numbers, and "can service X reach door Y?"
- Claude investigates (at most 10 tool uses, within 2 minutes) and must finish with: what's
  wrong, how sure it is, **the proof**, and what it ruled out. No proof, no answer.
- The **incident page:** timeline of every step, plus charts that line up in time.

**You'll see:** "Order service can't reach the database on 5432; 5433 is open", with the
proof clickable.

**We check it by:** exam papers. We save each scenario's tool results and run the AI 5
times. It should be right at least 4 times.

### Phase 3 — The safety system  *(Tue night → Wed midday, ~8 hours)*

- The AI **proposes** a fix from the menu; the system checks it's allowed.
- **Risk rules** (plain rules, not AI) decide how risky it is and who must approve.
- The **approval card**, like a GitHub pull request: what changes, why, who's affected, how
  we'll know it worked, and how to undo it.
- **Approval is enforced.** Only an approver can approve, a double-click can't run it twice,
  and **nothing runs without approval**. (The old project had a hole here: the fix could run
  without anyone approving it.)
- **Fix → check for 2 minutes → auto-undo if it didn't work.**
- **Pause button** that stops all automatic fixes.

**You'll see:** Approve → the real cluster changes → errors drop to zero → the incident closes itself.

> **Freeze on Wednesday midday.** Mark this point in git (`v0-pre-event`). Everything
> after it counts as built at the hackathon.

### Phase F — Freshservice  *(event day, ~4 hours, required)*

Everything in the "Why Freshservice fits" table above, made real. If Freshservice goes
down mid-demo, SentinelOps still finishes the job and shows that it will retry.

**You'll see:** break it → a ticket appears in Freshservice → the AI's findings as a note →
a change request → approval → the ticket closes → a Problem record with the report.

### Phase 4 — The record book  *(event day, ~2 hours)*

An audit page listing everything, and a **Verify** badge. Secretly edit one old record, and
the badge turns **red** and points at it.

### Phase 5 — Extras  *(event morning, only if there's spare time)*

A service map showing what's broken and what's affected; deploy markers on the charts;
maybe a voice call to the approver (partner prize track). All optional.

### Submission  *(mostly before the freeze, ~1 hour; a short finish on Friday)*

**Before the freeze:** README, project description, business case link, and the demo link
tested from a phone on mobile data. Writing about the project isn't building it, so doing it
early doesn't take anything away from what counts as built at the event.

**Friday morning (~30 min):** add the Freshservice and record-book parts, re-test the link,
final push **before 10:45**.

---

## If time runs short

The event gives about **7.5 real hours** (5 on Thursday, 2.5 on Friday). Freshservice (4) +
record book (2) + finishing the submission (0.5) = 6.5, so there's about **1 hour spare**,
and only because the README is written beforehand.

- **Before the event:** the safety system (Phase 3) must work. If needed, make "undo" a
  button instead of automatic. Then the README draft, because that's what creates the spare hour.
- **At the event:** Freshservice first (it's required), then the record book. Extras only
  if the spare hour is still there on Friday.
- **If Freshservice takes too long:** skip the "search how-to articles" part first. If it's
  still slow, approve in SentinelOps and copy the decision into Freshservice rather than
  reading approvals back. Ticket, note, change request, and closing with a Problem record
  are the parts the demo needs.
- **Thursday 18:30 check:** if Freshservice isn't finished, the record book shrinks to just
  the Verify badge and the tamper demo.
- **Never** cut the final submission push.

---

## What your friends can do (no coding needed)

- Write the **business case** (problem, customer, competitors, solution, value, pricing,
  go-to-market, costs, success measures, risks). Keep it short.
- Build the **pitch deck**.
- Set up the **Freshservice trial** and write 3–4 short how-to articles in it, so the AI has
  something to search.
- Play **"tough judge"** during rehearsals and ask the hardest questions.

---

## Testing and debugging, in short

**Testing:** small automatic tests for the safety rules, the tamper-proofing, the detector
and the Freshservice messages, run before every commit. Real break-and-fix runs on the
cluster at the end of each phase. The AI's exam papers after any AI change. And the full
demo, run by hand, at the end of each phase and **3 times before judging**.

**Debugging:** make it happen again → find **which layer** is wrong → make **one** guess →
test it → fix it → add a test. The events list tells you what happened, in order, and who
did it. The Freshservice page shows the last 20 messages sent and whether they worked.

---

## The 4-minute demo

1. Dashboard green, Freshservice open beside it.
2. "Break it." Errors spike; the incident appears, and **so does a Freshservice ticket**.
3. The AI investigates with proof.
4. The approval card and the matching **Freshservice change request**. "The AI picked from
   a menu. Approval goes through your existing process."
5. Approve → fixed → checked → the ticket closes, with a Problem report.
6. Audit: green; tamper → red.
7. Pause button: fix refused.
8. One line of business case, then what's next.

---

## Questions to ask mentors (first thing on day 1, or earlier by email)

1. Does the **demo link** have to work after the event, or only during judging?
2. Can a program **request and read change approvals** through the Freshservice API on the trial?
3. What are the Freshservice trial's **API limits** (how many calls per minute)?
4. Is it fine that the **pretend company** being monitored was set up before the event, since
   it's the thing being watched, not the product?

---

## Words used in this plan

- **Freshservice:** Freshworks' tool where IT teams track incidents and approve changes.
- **Ticket / Change / Problem:** Freshservice's records for "something's broken", "we want to
  change something", and "why did it happen and how do we prevent it".
- **Kubernetes:** software that runs our services. **Pod:** one running copy of a service.
- **Prometheus:** collects numbers (requests, errors, speed) from our services every 5 seconds.
- **Event:** one short note saying something happened. Only ever added, never edited.
- **Hash / chain:** a fingerprint of data. Each note holds the previous note's fingerprint, so edits show.
- **Action catalog:** the fixed menu of fixes the AI may choose from.
- **Policy:** written rules deciding how risky a fix is and who must approve it.
- **Rollback:** undoing a fix. **Kill switch:** pause button for all fixes.
- **Tunnel:** a secure public web address that leads to your laptop.
- **Least privilege:** giving a program only the permissions it actually needs.
- **Commit / tag:** a saved snapshot in git / a named bookmark on one snapshot.
