---
role: model-validator
last-reviewed: 2026-11-11
status: current
---

# Playbook: model-validator

Canonical copy lives in the Foundry repo; apps receive it via `install.sh --update`.
Changes come from `radar/reports/` and need owner approval.

## Scope
Models, backtests, calibration, leakage, multiple testing (optional role)

## Current practices
Sources and dates are in `radar/reports/2026-11-11-rest.md`; the rules in `AGENTS.md` and the agent prompt still apply.

- Every study records how many variants, parameters and windows were tried (including abandoned
  ones) before it is run. A result picked from more than one variant reports a multiple-testing
  correction (Benjamini-Hochberg across hypotheses) and, for a strategy metric, the Deflated
  Sharpe Ratio given that trial count or PBO by CSCV. A study that cannot say how many trials it
  took is not evidence.
- Probabilities are judged with a strictly proper scoring rule (Brier or log score for binary
  outcomes, RPS for ordered outcomes) on held-out data, reported as skill against the base rate
  with the sample size. A calibration claim shows a reliability diagram built by isotonic
  regression (CORP/PAV), not hand-picked bins, with its miscalibration component. No probability
  sizes anything until it has beaten the base rate out of sample (SONAR's `calibrated_estimate()`
  is the pattern).
- Every external data source a model or figure depends on is listed in the app's
  `app-context.md` Stack section with its endpoint and whether it is official, unofficial or
  scraped. An unofficial source is never the only input to a published figure without a stated
  fallback.

## Watch list
overfitting and calibration literature, data-provider changes

## Change log
- 2026-10-10: seeded (baseline).
- 2026-11-11: first radar review (current), from `radar/reports/2026-11-11-rest.md`, owner-accepted rows M1, M2, M5. P3 rows (M3, M4, M6) not applied.
