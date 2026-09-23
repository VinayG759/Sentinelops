# Next session — pick up here

Written 23 Sep (Wed), when the Claude Code weekly limit was at 90%. Read with
`implementation-plan.md` and `manual-test-checklist.md`.

## Dates (corrected today)
Event is **Fri 25 – Sat 26 Sep**. Freeze + tag `v0-pre-event` at the **end of Thu 24 night**.
Presentation: written Wed 23 evening, practised Thu 24 evening. Submission closes Sat 10:45.

## Done today (all committed on `main`, nothing pushed)
- Plans: event-hours budget, cut lines, weekday fix, README first full draft.
- UI foundation `9fc6abb`: global 15m/1h/6h range + Live toggle; per-service colours
  (violet order-service, green payment-service — validated for colour-blindness).
- Overview `336e34d`: four sections, error-rate + p95 charts for all services, outcome tiles
  (`GET /api/incidents/stats`).
- Incidents `7244478`, `902bfce`: Problems-style table, facet rail, root cause, duration bar.
- **Bug fix `d87ab97`**: in-pod exec corrupted the shared Kubernetes client under concurrency
  (18/48 connectivity probes failed; could also break the executor). Cluster test added
  (`uv run pytest -m cluster`).

## Not yet verified
- **Live break → fix run after `d87ab97`** through the UI: expect zero failed
  `check_connectivity` steps and "Root cause found" on both incidents.

## Waiting on others
- **Freshservice API key**: trial `codexplorers.freshservice.com` (Enterprise, 14 days) shows
  "API key disabled". Asked Freshworks support (ticket open on their portal) and mentor
  Mohideen Ibrahim. When enabled: fill `FRESHSERVICE_API_KEY` in `.env`, then run the spike
  (explain first; it creates a ticket, note and change in the trial).

## Next, in order
1. Freshservice spike as soon as the key arrives.
2. Vinay's manual checklist (Phase 2 + 3 items) and full demo runs.
3. Backup demo video; tunnel test from a phone (`cloudflared tunnel --url http://localhost:5173`).
4. UI step 3 (optional): service side panel — click a service on Overview → slide-over with
   health chips and Metrics / Logs / Incidents tabs (incl. DB pool open/idle/waiting chart).
5. Thu night: tag `v0-pre-event`, fill README "built before" column.

## Known quirks found today
- Prometheus has no persistent storage: every Docker restart wipes chart history.
- Backend doesn't auto-reload; restart `uv run python run.py` after backend changes.
- `browse` daemon can reset between calls: do login → navigate → screenshot in ONE chain;
  a selector matching several elements aborts the chain (use `>> nth=0` or `aside a[...]`).
