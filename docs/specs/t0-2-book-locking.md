# Spec: T0-2 — the paper book and the engine are written whole, from any thread

- Status: built (branch `fix/t0-2-book-locking`, stacked on `fix/t0-1-lock-takeover`)
- Review: `docs/audit/t0-2-book-locking-code-reviewer.md` — no P0/P1; P2-1 and P3-1…6 fixed.
- Owner approval: delegated in chat 2026-10-10 ("do next").
- Source: `docs/audit/code-review.md` P1-3 (reproduced), `docs/audit/architecture.md` P1-2.

## Problem
`Portfolio` and `Engine` are mutated from the engine thread (`_poll`, `_rescan`, `_mark_book`,
`_protocol_scan`), the window's thread and HTTP handler threads (`trade`, `close_position`,
`configure`, `read`), and a settings change's `ConfigThread` (which rescans). Nothing was locked.
Reproduced in the audit: a manual close racing a barrier hit credited cash twice (7,763.93 →
12,536.07) and raised `ValueError: list.remove(x)`; two saves of one file shared `<name>.tmp`
and raised 8,657 `FileNotFoundError`s in 2 s.

## Success measure
- A close racing a barrier pass credits once, closes once, raises nothing
  (`test_a_close_racing_a_barrier_hit_credits_once`).
- A manual close that loses the race to a barrier says "no such open position" instead of
  crashing (`test_a_manual_close_after_a_barrier_closed_it_says_so`).
- Concurrent atomic writes of one file all land, leave no temp file
  (`test_two_saves_of_one_file_at_once_both_land`); the engine saves from two threads cleanly.
- Rescans never overlap (`test_rescans_run_one_at_a_time`).
- An older mark pass never hides a newer trade (`test_an_older_mark_pass_never_hides_a_newer_trade`).
- Orphaned temp files older than 10 minutes are swept on load; younger ones are left.
- Each test fails when its part of the fix is removed (7 of 7 planted mutations caught).

## Non-goals
Moving `_rescan`/macro fetches off the poll thread (T1-7); last-known prices for hidden symbols
(T0-5); the stale-lock reclaim race.

## Architecture
- `Portfolio.lock` / `Engine.lock`: `threading.RLock`; a `_locked` decorator wraps every public
  method that mutates or iterates shared state (Portfolio: save, position_for, enter, close,
  poll_fills, settle_fills, mark, equity, stats, open_rows, log_equity, history_wanted,
  seed_equity_log; Engine: set_risk, attach_llm_read, save, tick, finalize, seed_backtest, stats,
  model_vs_market, buyability, run_health, llm_calibration). Re-entrant, so methods compose.
- `Live`: `_mark_book`, `trade`, `close_position` (find and close in one step) and
  `_protocol_scan` (count the cap and fill it in one step) run under `book.lock`; `_mark_book`
  publishes `positions`/`calibration` while still holding it.
  `_rescan` is serialised by `_rescan_lock`.
- **Lock order:** `_rescan_lock` → `book.lock` → `Live.lock`; `Live.lock` → `engine.lock` (the
  poll's tick and snapshot). Nothing takes `book.lock` while holding `Live.lock`.
- `paths.write_atomically` uses a per-writer temp name (`<name>.<pid>.<thread>.tmp`) and removes
  it on failure; `Engine.save` and `Portfolio.save` now use it.

## Residual risk
- The Engine lock has no race test of its own: the engine is mutated mostly on the poll thread,
  and the cross-thread cases (`set_risk` from configure, `attach_llm_read` from a read) are short.
- No dedicated tests for the protocol cap racing a manual trade, `attach_llm_read` racing `tick`,
  or a ConfigThread rescan queued behind the engine's (which can push back `shutdown()`'s wait).
- A network broker's `execute`/`settlements` would now run under the book lock. Only the
  internal paper broker is wired (Alpaca is dormant), so nothing waits on the network today.

## Verification
Full suite 1,597 passed natively and under `QT_QPA_PLATFORM=offscreen`; 7 new tests.
