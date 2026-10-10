# Spec: T1-1 — calibration is a report, never an input

- Status: built (branch `fix/t1-1-calibration-gate`)
- Owner approval: 2026-10-10 — "Report only" (asked in chat after the model validation).
- Source: `docs/audit/model-validation.md` P1-1b, `docs/audit/code-review.md` P1-5, P2-12.
- Review: `docs/audit/t1-1-calibration-gate-model-validator.md`.

## Problem
At 20 closed positions `calibration.report()` declared the book "calibrated", bisected a drift
from the pooled hit rate with no interval, and `core.py` pushed it into every row's P(profit) and
grade. It graded wins by P&L sign, so hand closes in profit counted as target hits. The real book
(22 closed: 10 TARGET, 11 STOP, 1 MANUAL) was already moving all 129 rows by +0.09σ.

The validation then showed the pooled hit rate cannot measure a drift at all: protocol entries take
a coin-flip direction, a driftless walk watched at discrete marks already lands at 40.6–41.3%, fat
tails push it higher, and a gate re-checked after every close trips on a book with no edge 23–37% of
the time at 95%.

## Decision
Calibration reports; it never moves P(profit), which stays at 1/(1+R:R).

## Success measure
- A book of 40 straight target hits leaves every row's P(profit) at 0.40.
- Only TARGET/STOP are graded; hand closes are counted (`n_manual`) and shown, not graded.
- The 95% range is shown; "beats its odds" and the rank-IC verdicts need three standard errors.
- The report carries no drift (`implied_edge_sigma`, `calibrated` removed).
- Real book: 21 graded, 48%, range 28–68%, "within noise".

## Architecture
`calibration.report`: `graded()`, `wilson()`, `enough`, `hit_rate_ci`, `beyond_noise` at
`Z_CLAIM = 3.0`, `n_manual`. `core.py` no longer writes the scanner; `AssetScanner` lost
`edge_sigma`/`calibrated`. `implied_edge` stays for the backtest readout. Window tooltip, the
"Is the score right?" rows and the manual (§3, §10) say the grade never moves the number.

## Residual risk
- Hand closes are dropped from the grade; if they become frequent they can bias it (validator P2-1).
  The count is on screen.
- Delayed broker fills could make a stored p_profit drift from its position's real baseline
  (latent; only the synchronous paper broker is wired).

## Verification
Full suite 1,659 passed natively and under `QT_QPA_PLATFORM=offscreen`; planted mutations caught
(no gate, P&L-sign grading, wrong Wilson, two-sigma claims, a drift fed to the plans); one
equivalent mutant (counting wins by P&L sign among graded positions).

## CHANGELOG draft
**Your track record no longer changes the odds shown.** After twenty closed positions the app used
to turn a better-than-promised hit rate into a higher P(profit) on every row. A closed book cannot
measure that — the effect was noise and price-gap geometry — so the grade is now a report only, it
counts only target and stop hits, and it claims nothing inside three standard errors.
