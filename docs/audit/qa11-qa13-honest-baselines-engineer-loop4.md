# Loop 4 build report (engineer), 2026-10-12 — saved by the orchestrator; not yet reviewed

- P1-D: headline se = max(binomial/Agresti–Coull, Newey–West, Driscoll–Kraay by UTC entry date, Bartlett, L = ceil(avg_bars_held·365/252)); `_dk_lag_days` (`sonar/backtest.py:456`), `_dk_se` (`:463`), summary fields `se_dk`, `dk_lag_days`. Cost: 6 ms at the Lab default; 69 ms at 10y h=120 (whole summarise 765 ms).
- P1-E: attention buckets use DK, compared against the run's own Δ (`vs_run`), Benjamini–Hochberg at `ATTENTION_FDR_Q = 0.05` (`:845-930`); random attention on cached real bars → "shifts the odds" 0/24 judged runs (was 9/21).
- Acceptance test (`tests/test_backtest.py:1100-1238`): clustered coin on correlated synthetic walks (within 0.25, between 0.11; vol co-movement 0.18/0.07), 60 runs, bound ≤ 7/60 false verdicts and mean z² ≤ 1.5; 2.5 s.

| Clustered coin | Before | After |
|---|---|---|
| Synthetic, 720 runs | 18.9% [16.2–21.9], z² 2.23 | 7.5% [5.8–9.7], z² 1.30 |
| Test's fixed 60 | 9/60 | 5/60 |
| Real cached bars, 360 runs | 52.2% (58.8% of judged) | 9.7% [7.1–13.2] (10.9% of judged) |

  Still above the ≤ 5% target; closing it needs a sign-randomisation test (validator's next step).
- Code review r4 P2-1: blend "ranks backwards" only when not withheld and t ≤ −Z_CLAIM (`_ic_t` `:1070`, `_blend_series` `:1087`, `ui/app.py:2862-2871`).
- Mutation: 24/24 killed. Suites: native and offscreen 1,871 passed, exit 0, twice each. Counts updated; `static/testplan.html` regenerated.
- Live cached bars (whole watchlist): Lab default se 0.42 → 0.88, "no edge"; Terminal 1-day "below" z −2.36 → −1.23 "no edge"; 20-day z 1.43 → 0.67; 60-day "beats 3.2" z 2.40 → 0.69 "no edge"; 250-day withheld.
- Open: verdict copy still says "more than two standard errors"; Lab attention table "vs baseline" shows `delta` while significance is vs the run; docs/TODO/CHANGELOG/ADR not updated; full momentum sweep and independent-coin "below" rate not re-measured.
