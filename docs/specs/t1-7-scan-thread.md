# Spec: T1-7 — the price poll never waits on the slow work

- Status: built (branch `fix/t1-7-scan-thread`). Owner approval: delegated in chat ("go on").
- Source: `docs/audit/code-review.md` P2-3, P2-4; architecture P2.
- Review: `docs/audit/t1-7-scan-thread-code-reviewer.md` — no P0/P1; P2 and P3 2–7 fixed.

## Problem
`Live._poll` ran the asset rescan (26+ charts, 24 feeds, calendars, central banks) and the hourly σ
fetch inline: the price poll stalled for seconds to minutes and the engine ticked a stale candle
against a fresh market (10 s stale ≈ ±4¢ of model P(up), the size of the entry threshold).
`_build`, under `Live.lock` (taken by the window every second), called `macro.get()`, which fetches
six FRED series at 25 s timeouts when its cache expires — up to ~150 s of frozen window.

## Success measure
- A poll never runs the scan or the σ fetch; the market is fetched before the candle, which is
  fetched right before the tick; one σ value prices the signal and fills the page.
- A background thread runs what is due (σ hourly, macro snapshot, scan every 90 s) and outlives a
  failing step; a scan queued behind a settings change's scan does not run again at once.
- The snapshot and the LLM read use a cached macro snapshot; the panel says "Loading…" on a long
  horizon until it arrives (warmup fetches it first, usually from the disk cache).
- On quit, the engine lock is released only after the background thread is joined; a scan that
  finishes after quit writes nothing to the book.
- `health()` reports a `scan` problem when the background thread died or the board is 3× overdue;
  the agent's alarm covers it after 10 minutes.
- 12 planted mutations caught; `_book_prices` copies the scanner's dicts atomically (pre-existing race).

## Residual risk
The window's 1.5 s shutdown grace is shorter than the 20 s join: quitting mid-scan hard-exits via
`_exit_now`, as it did before when the scan ran inside the poll; the next launch reclaims the
stale lock. Headless never calls `stop()`.

## Verification
Full suite 1,697 passed natively and under `QT_QPA_PLATFORM=offscreen`.

## CHANGELOG draft
**Prices are never held up by the scan.** The 90-second asset scan, the hourly volatility fetch and
the macro data now run beside the price poll instead of inside it, and the window no longer freezes
while the macro series load.
