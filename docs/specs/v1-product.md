# Spec: v1.0 — what SONAR is for

- Status: **approved** by the owner, 2026-10-10 (four questions asked in chat).
- Owner approval: audience, core job, side experiments, definition of done.
- Source: `docs/ROADMAP.md` Phase 2; `docs/audit/SUMMARY.md`; `docs/audit/ux.md`.

## Problem
SONAR grew by accretion into eight tabs, three experiments and a research notebook, with no
statement of who it serves or when it is finished. Every audit ran against an implicit target.

## Audience
**The owner now; others later.** Built and judged as a personal tool on one Mac, but kept
shareable: nothing is removed that a later release would need (disclaimers, first-run help,
notarization on the roadmap, honest wording). Not marketed, not supported, not signed for others.

## Core job
**A notability scanner and an honest paper book.** It shows what in 129 instruments is worth a
look, lets you take paper positions on it, and reports truthfully whether the score kept to its odds.
It never says which way anything will go, and never claims an edge.

- **Core path (main rail):** My investments · Screener · News · My trades · Big picture · Learn.
- **Lab (demoted, end of the rail):** Practice (the hourly BTC model vs Polymarket) and Sports
  (Playmaker). Experiments with their own scores; kept, not on the main path.

## Success measure ("v1.0 is done when")
**30 days clean.** From the day the Tier 0/1 fixes are all running on the agent:
- the agent runs the whole period with no silent stop (health check never red for over 10 min
  without an alarm reaching the owner, no restart loop);
- no loss or overwrite of the book (daily and off-disk backups present for every day; one restore
  drill passes);
- the model-vs-market and calibration reports keep updating and say nothing they cannot support;
- no new P0/P1 found.
Then features stop; changes after that are fixes.

## Non-goals
Real money (out of scope until the owner says otherwise in writing); a public launch; Windows or
Linux; new data sources; new tabs; any claim of edge.

## Decided without asking
Tier 2 stays optional and is ordered by what serves the core path first: first-run loading states
(U-2), jargon in plain mode (U-7), the BTC edge cell's emphasis (U-5), then dead code and README.

## What follows
1. Demote Practice and Sports to a "Lab" group at the end of the rail (`ui/tabs.py`, `ui/app.py`).
   Small UX change; owner-approved by this spec.
2. Start the 30-day clock when the owner confirms the agent and app run the latest build
   (agent restarted 2026-10-10 17:30, app v2.168): **day 1 = 2026-10-10**, due **2026-11-09**.
3. A restore drill into a scratch folder from the off-disk copy, once, before day 30.

## Open
- Whether "others later" ever happens is not decided here; the roadmap's Phase 5/6 stay unscheduled.
