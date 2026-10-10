# Spec: T0-3 — the warm-up stays out of the bankroll

- Status: built (branch `fix/t0-3-warmup-pnl`, stacked on `fix/t0-2-book-locking`)
- Owner approval: 2026-10-10, "Correct the record" (asked in chat).
- Source: `docs/audit/code-review.md` P1-1 (reproduced).
- Review: `docs/audit/t0-3-warmup-pnl-code-reviewer.md` — no P0/P1; P2-1, P2-2, P3-3…5 fixed.

## Problem
`Engine.seed_backtest` booked 36 synthetic fair-odds warm-up bets into `self.bankroll`, so the
headline P&L, the return and every Kelly stake carried bets nobody took. The owner's real book:
bankroll 68,430.43 = 10,000 + 58,715.85 (283 live bets) − 285.42 (warm-up).

## Success measure
- A fresh warm-up leaves the bankroll, P&L and return untouched; its curve ends at the bankroll
  and is continuous from the first point.
- An old state file is corrected once on load (real book copy: 68,430.43 → 68,715.85), in memory
  only; the next save keeps `state.json.before-warmup-fix` first and never overwrites it.
- A corrected book saved by an older build (the installed app shares the book) is not corrected
  again; a warm-up netting near zero is not mistaken for a carried one.
- 8 planted mutations, 8 caught.

## Architecture
- `seed_backtest` no longer adds to the bankroll; `_redraw_warmup(end_at)` draws the warm-up
  points (and the start point) so the curve shows its variance and ends at `end_at`.
- `_take_the_warmup_out_of_the_bankroll()` runs on every load and decides from the numbers:
  `carried = bankroll − (start + Σ live P&L)`; it corrects only when `carried` is non-trivial
  and equals the warm-up's sum (±0.05). It subtracts the sum from the bankroll and from every
  `live` equity point and redraws the warm-up. No flag: an older build would drop it.
- `Engine.save` keeps the pre-fix file once, atomically; a failed copy is logged, not fatal.
- Total P&L tooltip in `static/index.html` now says live trades only.

## Residual risk
The equity curve still plots by index, not time (pre-existing).

## Verification
Full suite 1,603 passed natively and under `QT_QPA_PLATFORM=offscreen`.

## CHANGELOG draft
**The warm-up no longer counts as money.** The 36 fair-odds bets that draw the chart's first
hours were booked into the bankroll, so the headline P&L and every stake carried bets nobody
took. They are now chart history only; an existing book is corrected once (the file as it was is
kept beside it as `state.json.before-warmup-fix`).
