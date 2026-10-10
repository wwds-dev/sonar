# Spec: T0-4 — a past hour's candle never voids a live position

- Status: built (branch `fix/t0-4-stale-candle`, stacked on `fix/t0-3-warmup-pnl`)
- Owner approval: delegated in chat 2026-10-10 (work through Tier 0, pause for decisions).
- Source: `docs/audit/code-review.md` P1-2 (reproduced).
- Review: `docs/audit/t0-4-stale-candle-code-reviewer.md` — no P0–P2; P3-1 fixed.

## Problem
`Engine.tick` treated any candle whose hour differed from `current_hour` as a rollover — also a
candle from an *earlier* hour, which the Coinbase fallback served whenever Binance dropped out
(`parse_coinbase_candles` fell back to the newest row, and the fallback skipped the staleness
test). The rollover looked up the current hour's close (not closed yet), voided the open
position and dropped the hour's score snapshot.

## Success measure
- An earlier-hour candle leaves the open position, `n_voided`, `current_hour` and the pending
  score untouched, and the hour still settles (`test_a_candle_from_an_earlier_hour_does_not_void_the_open_position`).
- Coinbase without the hour in progress is no candle; a stale Coinbase candle is no candle.
- An earlier-hour candle never reaches the screen (spark line, snapshot) (`tests/test_poll.py`).
- 4 planted mutations, 4 caught.

## Architecture
- `Engine.tick`: return `last_signal` for `candle.open_time < current_hour`.
- `feeds.parse_coinbase_candles`: the hour in progress or `None` (no newest-row fallback).
- `feeds.hourly_candle`: `is_stale` applies to the Coinbase result too (a backstop; the strict
  parser already makes it unreachable with real data).
- `Live._poll`: drops an earlier-hour candle before the spark line and the snapshot.
- `tests/conftest.py`: a `real_poll` fixture exposes `Live._poll` as written, which every test
  otherwise gets as a no-op.

## Verification
Full suite 1,606 passed natively and under `QT_QPA_PLATFORM=offscreen`.

## CHANGELOG draft
**A lagging backup feed can no longer delete a trade.** When Binance dropped out and Coinbase
still showed the previous hour, the engine read it as a new hour and voided the open position.
A past hour's candle is now ignored, by the engine and by the screen.
