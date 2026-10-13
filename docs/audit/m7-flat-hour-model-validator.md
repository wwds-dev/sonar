# Model validation: the outcome of a flat hour (M7), 2026-10-12

Reviewer: model-validator agent (read-only; read from `master` at `d5f7a04`). It completes the
M7 item from `docs/audit/closing-qa-engineer.md`. The test was pinned in `b654ae6`
(`docs/specs/closing-qa-fixes.md`, row M7), but no model-validator review was recorded then.

## Verdict: consistent
An hour that closes at its open (close == open) counts as **UP** everywhere, and that is correct.

## Evidence (line numbers at `d5f7a04`)
1. **How the market resolves a tie.** `README.md:80` says "will the BTC/USDT 1-hour candle close
   **at or above** its open?". The resolution source is Binance BTCUSDT (`sonar/feeds.py:5-7`,
   `README.md:66`). Polymarket's own rules text is not in the repo, so the README's statement is
   **not verified** against it.
2. **What the model predicts.** `sonar/model.py:66-67` defines `prob_up` as "P(candle closes >=
   open)". Under the continuous model a tie has zero probability. The lattice counts the
   at-barrier bin as a tie (`model.py:121-124`).
3. **Every settlement path agrees:**
   - `engine.py:437` (`_score_hour`, `>=`)
   - `engine.py:506` (`finalize`, `>=`)
   - `engine.py:545` (warm-up rows)
   - `feeds.py:74` (`is_up`)

   Both settlement calls receive the same `close` from `_settle_rollover` (`engine.py:374-379`).
   Tests pin both: `tests/test_engine.py:363` and the M7 test from `b654ae6`.
4. **How often ties happen.**
   - Binance history: 10,000 BTCUSDT hours (2025-08-20 to 2026-10-10) contain 2 exact ties at
     $0.01, about 0.02% (Poisson 95% CI 0.002%-0.07%).
   - Live `state.json` scorelog: 1 tie in 245 hours, 2026-10-10 21:00 UTC, open = close =
     83040.00. Binance klines confirm it.
   - Effect on the Brier log: the mean model-minus-market Brier difference is 0.00870
     (SE 0.00589) with the tie scored UP, and 0.00903 if it were scored DOWN. The shift of 0.0003
     is about 0.06 SE, so not material.
   - The same hour settled one live DOWN paper trade as a loss of $4,416.29, which is correct
     under the stated rule.

## Related finding
| # | Pri | Where | Finding |
|---|---|---|---|
| V1 | P3 | `engine.py:374` | The previous hour's close is taken as the next candle's **open**. On Binance the two differ in 4,747 of 10,000 hours: for example, 20:00 closed at 83040.01 but was logged as 83040.00. That flipped the outcome in 0 of 10,000 hours, because it can only matter at the barrier. Using the kline's own close (field [4]) would remove the approximation. When the feed falls back to Coinbase BTC-USD, a different series is settled, and a tie there is not a tie on Binance (not quantified). Not a bug today; for the owner to schedule. |

## Inputs
- Binance `/api/v3/klines` (public, read-only).
- `~/Library/Application Support/SONAR/state.json` (read only).
- Nothing was written to the app or the repo by the reviewer.
