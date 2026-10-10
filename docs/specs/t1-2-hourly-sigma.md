# Spec: T1-2 + T1-6 — the hourly σ is the studied estimator, on fresh, whole history

- Status: built (branch `fix/t1-2-hourly-sigma`)
- Owner approval: delegated in chat 2026-10-10 ("ok go ahead").
- Source: `docs/audit/model-validation.md` P1-1, `docs/audit/code-review.md` P2-1, P2-2.
- Review: `docs/audit/t1-2-hourly-sigma-model-validator.md` — no P0/P1; its P2 (= T1-6) fixed here.

## Problem
`hourlyvol.forecast()` (the hourly BTC model's σ, via `Live._sigma`) ran EWMA on raw r² times the
target hour's factor; the study's winner runs EWMA on deseasonalised r². The "+7.5%, 6/6" belonged
to an estimator that was never shipped. And `fetch_hourly` returned whatever pages it had when a
page failed, dropped the last bar unconditionally, and `forecast()` checked neither gaps nor age —
so a failed second page priced the hour off history ending ~20 days ago.

## Success measure
- `forecast()` equals the study's `ewma_diurnal` forecast at many origins (test via `study(trace=)`);
  reviewer: 599/599 bit-identical on real data; not-full fallback = plain EWMA.
- Real data, live-shaped 62-day window, n=16,031: new 1.82682 (+7.50% vs trailing-72, 6/6), old
  1.88352 (+4.63%); difference 0.0567, block-bootstrap 95% [0.041, 0.073].
- A failed page is an error (→ `model.hourly_sigma` fallback); only the in-progress hour is dropped;
  a missing hour or history older than 3 h gives no forecast.
- 5 planted mutations, 5 caught.

## Residual risk
`forecast()` equals the study on the same data; live sees 62 days, the study two years (per-forecast
difference up to 1.9%, pooled QLIKE the same). The T1-6 guards were prescribed by the reviewer and
mutation-tested, not separately reviewed.

## Verification
Full suite 1,664 passed natively and under `QT_QPA_PLATFORM=offscreen`.

## CHANGELOG draft
**The hourly model prices with the volatility estimate that was actually measured** — about 3 points
of QLIKE better than what shipped — and never with a history that stopped short or ended hours ago.
