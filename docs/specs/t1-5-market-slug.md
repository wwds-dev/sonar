# Spec: T1-5 — the hourly market is found in any locale and on the fall-back night

- Status: built (branch `fix/t1-5-market-slug`)
- Owner approval: delegated in chat 2026-10-10 ("ok go ahead"). Deadline: before 2026-11-01.
- Source: `docs/audit/code-review.md` P2-5 (reproduced), P2-6 (reproduced).
- Review: `docs/audit/t1-5-market-slug-code-reviewer.md` — no P0–P2; P3-1…4 fixed.

## Problem
`_hour_slug` used `strftime("%B")`/`("%-I%p")`, which follow `LC_TIME`; Qt sets it from the
environment, so a window under `LANG=de_DE` looked for `...-oktober-10-2026-7-et`. On the
fall-back night (2026-11-01) 1am ET happens twice with one slug; for the second hour the slug
returned the first, ended market and `current_market` returned None for the whole hour.

## Success measure
- The slug is identical to the C-locale format for every hour of 2026–2027 (reviewer checked) and
  unaffected by a German/French locale; 12am/12pm edges pinned.
- An ended slug market falls through to the series, which skips ended events to the first live one.
- A live slug market never triggers the series query.
- Another hour's market is not shown beside this hour's candle.
- 4 planted mutations, 4 caught.

## Architecture
`feeds.MONTHS` and an explicit 12-hour clock in `_hour_slug`; `current_market` → `_market_from`
(first live event of an answer) → `_live_book` (checks the end time before the midpoint call);
series query `limit=3`. `Live._poll` drops a market whose end is not the candle's hour + 1.

## Residual risk
Last year's fall-back night had no 1am market in the series at all; if that repeats, the second
1am has no market (the next hour's is refused by the engine's alignment check) — no trade, no score,
which is the honest outcome.

## Verification
Full suite 1,655 passed natively and under `QT_QPA_PLATFORM=offscreen`.

## CHANGELOG draft
**The hourly market is found in any language and on the night the clocks go back.**
