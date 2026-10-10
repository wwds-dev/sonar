# Spec: T0-5 — a position the risk filter hides is still priced

- Status: built (branch `fix/t0-5-hidden-prices`, stacked on `fix/t0-4-stale-candle`)
- Owner approval: delegated in chat 2026-10-10 (work through Tier 0, pause for decisions).
- Source: `docs/audit/code-review.md` P1-4 (reproduced).
- Review: `docs/audit/t0-5-hidden-prices-code-reviewer.md` — no P0–P2; P3-1…3 fixed.

## Problem
The risk profile hides volatile instruments from the board, and the book priced held positions
from the board alone. Holding DOGE through a 30% fall and switching to Conservative (which
hides it), a close booked exit = entry, P&L 0; the position's barriers stopped being watched and
its equity was marked at entry.

## Success measure
- A hidden position closes at its last price; with no price at all the close is refused, never
  booked at entry.
- A hidden position's stop is watched, also when the filter empties the board entirely.
- Its card keeps its price and history; a takeover prices it too.
- The scanner records prices of rows it hides.
- 6 planted mutations, 6 caught.

## Architecture
- `AssetScanner.last_prices` / `last_sparks`: every fetched instrument's last price and recent
  closes, recorded before the risk filter.
- `Live._book_prices(board)` / `_book_sparks(rows)`: the board's values over those; used by
  `_mark_book` (merged before its empty-board return), `close_position`, `_take_the_book`.
- `close_position` refuses with "no price for X yet — try again after the next scan".

## Residual risk
`last_prices` carries no age of its own (nor do visible rows on the position cards; pre-existing).
After a takeover it is empty until the first scan, so hidden positions show at entry until then.

## Verification
Full suite 1,613 passed natively and under `QT_QPA_PLATFORM=offscreen`.

## CHANGELOG draft
**Hiding an instrument no longer hides its position's losses.** A position whose instrument the
risk profile hides from the board was closed at its entry price and stopped being watched. It is
now priced, watched and closed at its own last price.
