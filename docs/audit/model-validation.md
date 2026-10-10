# SONAR model validation — 2026-10-10

Produced by the `quant-validator` role (read-only; scratch scripts in the session scratchpad).
Reproduced numbers from repo data and live Yahoo/Binance pulls. The test suite was not run.

## Bottom line
Apparatus mostly sound and honest: barrier math correct, look-ahead hygiene in panel/features
good, BH-FDR/controls/block tests implemented properly, "no directional edge" plausible. Four
things do not hold up:
1. The shipped hourly-σ estimator is not the one that was measured.
2. A ≥20-trade paper book silently becomes a "measured edge" that rewrites P(profit) on every row.
3. Several "no edge" statements are really "underpowered, and the harness has its own bias".
4. Several numeric/wording claims are wrong (bps label, "measured" costs, "6 of 6" blocks,
   "thin statistical edge").

## Reproductions
| Claim | Result | Status |
|---|---|---|
| Model vs market Brier (README/TODO 0.1696/0.1657 at n=139) | n=256 (09-21→10-08): model 0.1686, market 0.1639; diff +0.0048, SE 0.0056, t=0.84, bootstrap 95% CI [−0.0071, +0.0154] | Reproduced; model not better than market, within noise |
| EWMA×diurnal +7.5% QLIKE, 16,078 h, 6/6 blocks | Fresh pull: n=16,078, +7.57%, 6/6. Others: ewma +3.71% (5/6), garch +6.08% (6/6), trailing72_diurnal +3.73% (5/6); "every candidate 6/6" docstring does not replicate | Reproduced for winner |
| Daily vol study | 5d GARCH vs trailing-20 +17.6% (claimed +17.8%); 3d +14.7% (claimed +11.6%); 20d claimed +5.6% undefined baseline | 5d ok; 20d unverifiable |
| Catalyst "first KEEP" | 29 equities, H=5, n=10,517: IC +0.032, HAC p=0.0003, quintile spread +4.7 pts; event 45.1% vs 38.6% (+6.5, week-cluster CI [2.9,10.1]) | Effect robust (see P1-2, P2-4) |
| Backtest hit ≈ 40% | H=5 40.09% (HAC SE 0.55); H=20 40.54% (SE 0.86) | Consistent, but null isn't 40% (P1-3) |
| Sign test 5/6 p=0.22 | two-sided 0.2188 | Correct |
| 116,563 rows | 75,669+38,320=113,989 + 2,574 embargo | Consistent, not reproducible (bars not cached) |
| Regime study "0 of 48" | n_tests=48, floor 1.72, best |t| 1.81 | Matches |

## Verdict per claim
| Claim | Verdict |
|---|---|
| Barrier math P=1/(1+R:R), EV=0 for driftless walk (`scoring.py:85-113`) | Supported |
| Backtest reproduces 1/(1+R:R) at 1.5:1 | Partly: biased low 0.3–0.9 pts (P1-3) |
| "Five pre-registered studies" | Unverifiable — features/signs committed in same commit as results (`af16fea`); catalyst study came after the five nulls |
| "No directional edge in momentum, news, 52w-high, regimes" | Only as "none detectable at this power"; MDE 0.04–0.07 IC (P1-4) |
| "Neither momentum nor news carries a usable edge" (README:232, `ui/app.py:1607`) | Overstated (spike +0.8 ± 3.1; +3.9 pts not excluded) |
| Catalyst KEEP (pooled) | Supported |
| Catalyst "6 of 6 blocks" (README ~330, docs.html:844) | Unsupported on fresh data: 5 of 6 (P1-2) |
| Hourly σ "+7.5% QLIKE" justifies shipped estimator | Unsupported for shipped code (P1-1) |
| "Better vol forecast improves the stated probability" (`volatility.py:12-13`, CONFIDENCE.md:297) | Unsupported — P(profit) depends only on k_target/k_stop |
| "Thin statistical edge" from realised vs implied vol (README:91-93, `model.py:24-28`) | Unsupported — own Brier shows model slightly worse than market; log-loss 0.512 vs 0.497 |
| Calibration "moves P(profit) only when a real edge has been measured" (`ui/app.py:589-593`) | Unsupported (P1-1b) |
| Costs "measured … 5.2% / €1.05 / 50.0 bps per side" | Label wrong; "measured" circular (P2-1) |
| Hourly model calibration | Overconfident in upper tail (P2-6) |

## P0
None. No leakage found in panel, features or replay (`Session` hides the future structurally).

## P1
**P1-1 Shipped hourly σ ≠ validated estimator.** `hourlyvol.py:316-343` (`forecast`, used at
`core.py:800-808`) runs EWMA on raw r² then multiplies by the target hour's diurnal factor; the
study's `ewma_diurnal` (`hourlyvol.py:239-241, 248-258`) runs EWMA on deseasonalised r²/fac.
No test links them. Same origins (every 3rd hour, 62-day window, n=5,360): shipped QLIKE 1.830,
study 1.787, trailing72 1.961. Shipped−study +0.043, block-bootstrap 95% [0.020, 0.065] —
significantly worse; still beats trailing72 by 6.7%. Study's +7.5% has 95% CI ≈ +4.9% to +13%.
Fix: ship the studied formula or re-run the study on `forecast()`.

**P1-1b 20-trade book silently becomes a "measured edge".** `calibration.py:37, 122-124`
(`calibrated=True` at n≥20); `:72-94, 143` (`implied_edge` bisected from overall hit rate, no CI or
significance gate); `core.py:306-309` → `assets.py:456-460` (`build_plan`, all 129 rows) →
`scoring.grade` (`scoring.py:166-181`). Current book: 19 closed, 6 wins (31.6%, Wilson
[15.4, 54.0]); the next close flips the switch. Under null p=0.40, P(≥10/20)=24.5% already earns
"favourable"; half-width at n=20 is ±21.5 pts; detecting 44% vs 40% needs ~940 trades. Also
`calibration.py:103` counts `pnl>0`, so MANUAL exits count as barrier wins (`portfolio.py:88,272`);
protocol direction is a coin flip (`core.py:274`), so >40% can only come from jump/fat-tail
effects, not "drift in σ" applied to a LONG plan.
Fix: gate on a CI excluding baseline; count TARGET/STOP only; don't label jump effects "drift".

**P1-2 Catalyst "6 of 6" does not replicate; bar applied asymmetrically.** Fresh block ICs:
−0.019 (2021-11→2022-09, event 37.1% < non-event 40.3%), +0.042, +0.046, +0.033, +0.044, +0.049
= 5/6. README (~296, docs.html:698) calls 5/6 at p=0.22 "not a finding"; `validate.py:82`
`consistent` needs sign_p<0.05 (6/6). Pooled effect survives cluster bootstrap. Date the claim and
state the standard evenly.

**P1-3 Backtest null isn't 40%; SEs too small.** `backtest.py:267-268` drops TIMEOUT trials,
`:222` scores a both-barrier bar as STOP, `:303-318` max of binomial and within-sequence HAC SE.
Exact-bridge OHLC simulation of a driftless walk (300 paths × 1,500 d, σ=0.02): H=5 39.68%
(−0.32, ~1.9 SE); H=20 39.13% (−0.87, ~2.7 SE); bias depends on granularity, always ≤0. A real
+1 pt edge would read as "matches the barrier maths". README:232 "39.58% vs 39.99% — barrier maths
is right" is consistent with the bias. `tests/test_backtest.py:172-190` admits 2:1 reads 30.7% vs
33.3%, 3:1 14.4% vs 25%; tolerance ±3 SE (~±4 pts) can't see 0.5–1 pt. `static/docs.html:714`
tells users to change R:R and re-run — the UI has no R:R control. Reported SE vs truth: empirical
SD of hit-rate delta 1.38 pts vs reported mean SE 0.99; cross-sectional dependence ignored (`run`
stacks symbols); `_attention_buckets` (`backtest.py:421-426`) uses plain binomial SE, so "±3.1" is
unadjusted.

**P1-4 "No edge" stated stronger than power supports.** 116,563 "asset-days" are overlapping
20-day windows (~77 independent per cross-section); SE of mean IC 0.014–0.024, 80%-power MDE
≈0.04–0.07 IC vs realistic anomaly ICs 0.02–0.05; discovery CIs ±0.03–0.05 (`mom_20` [−0.030,
0.043]). Holdout isn't null-like: `dist_52w_high` t=+3.39, `attention_z` +2.44, `mom_250_ex1m`
+2.39, `reversal_1` +2.42 (wrong sign); BH on holdout p-values keeps 4 of 16; the
discovery-then-holdout filter (`study.py:79-93`) discards them by design. Say "not detected;
≥~3 pts not excluded".

## P2
- **P2-1 Costs:** `costs.py:97-100` divides round-trip cost by one leg's notional → 50 bps = 2× per
  side; stated inputs (0.2% + 5 bp per side) are 25 bps/side. `SimBroker` `fee_rate=0`
  (`execution.py:259-265`); fee/slippage in `tests/test_costs.py:160` are hard-coded, so "measured,
  not assumed" is arithmetic on assumptions. 5.2%-of-risk is crypto at a ~9.5% stop only. Backtest,
  replay and Practice are gross of costs. Only genuine observation: Polymarket median spread 1¢.
- **P2-2 Survivorship:** `universe.py:97-124` — today's US common stock ≥ $5B, ranked by current
  cap; 26-symbol watchlist (`backtest.WIKI_ARTICLE`) all survivors (SOL, AVAX, LINK, DOGE, XMR,
  NVDA, META…). Biases long/trend tests upward (likely feeds the recent-block 52w-high effect).
  Never mentioned in the repo.
- **P2-3 `random_control` not deterministic:** `features.py:288` uses `hash((symbol, ordinal))`,
  salted per process, so the "seeded" control (README 4/6, t=−1.87, floor 1.72) can't be re-created.
- **P2-4 Fixed-R accounting near jumps:** `backtest.py:332` `expectancy_r = hit·rr − (1−hit)` ignores
  gaps. Event windows: fixed-R +0.128 vs gap-adjusted +0.073R, naive SE 0.057 → [−0.04, +0.18],
  indistinguishable from zero; non-event −0.037. Keep `expectancy_r` out of UI/claims.
- **P2-5 Quintile ties broken by input order:** `backtest.py:464`; `c_volatility = min(1, vol/0.03)`
  saturates for 35–36% of rows, so "top quintile" is arbitrary (LINK/AVAX/DOGE/ADA/XMR in the run);
  effect is mostly crypto vs not. Use unclipped inputs or random tie-breaks.
- **P2-6 Hourly model overconfident in upper tail:** `model_up≥0.9` n=27, 4 misses vs 0.74 expected
  (P=0.005); market ≥0.9: 3 vs 1.01 (P=0.076). Bin 0.3–0.5: predicted 0.41, observed 0.283 (n=46,
  Wilson [0.17, 0.43]). Resolving a 0.002 Brier diff needs ~8,000 hours; at 256 you have ±0.011.
  Snapshots at τ≈0.5; only 31 hours at τ<0.2; coverage 256 of ~410 hours.
- **P2-7 Inference helpers:** `stats.newey_west_t` (`stats.py:68-90`, lags=20 on 20-overlap MA):
  false-positive 9.2% vs 4.6% nominal. `bootstrap_ci` (`:122-145`, block=10 vs 20-overlap): ~78%
  coverage. `regimes.py`: 3/48 |t|≥1.5 vs ~6.4 expected — under-dispersed, low-powered; "nothing
  works even sometimes" (`regimes.py:222`) too strong. `validate.py:111` picks reference sign from
  pooled data before the sign test (anti-conservative).
- **P2-8 Vol forecast doesn't change stated probability:** P(profit)=k_stop/(k_target+k_stop) is
  independent of σ (`scoring.py`); σ only moves price levels and size.
- **P2-9 README misreads wider SEs** (~222-224: "overlap only ever widens an error bar, so the null
  survives…") — wider bars make the null less informative, not more.

## P3
- Docs overstating/contradicting: README:91-93 and `model.py:24-28` "thin statistical edge"; "five
  studies" count (see `docs/audit/docs.md`); `docs.html` figures (e.g. 6,268 setups) not reproducible
  (got 10,517 at step 3).
- `attention_z` (`features.py:265`, `backtest.attention_z`) uses full-UTC-day pageviews incl. 3–4 h
  after the US close — mild look-ahead.
- Calendar features `turn_of_month`/`month_of_year` constant per date → cross-sectional IC undefined
  (`stats.spearman` returns None); study silently tests 16 of 18 non-control features ("20" in JSON
  header).
- FRED regime inputs forward-filled on observation date (VIX/T10Y2Y published after close). Tiny.
- `volatility.forecast` cutoff `CLUSTERING_HORIZON_DAYS=10` and horizon menu chosen post hoc; the
  pre-registered expectation was contradicted; no QLIKE intervals reported.
- 50 bps / 5.2% come from a stub, not fills; the 20-round-trip gate is a "decency threshold"
  (`costs.py:40`), not a power calculation.

## Checked clean
`model.prob_up` and lattice tie-split; panel construction (`panel.py:84-122`); embargo/split
(`study.py:49-58`); Benjamini-Hochberg (`stats.py:98-119`); scorelog snapshot logic
(`engine.py:255-303`); replay `Session`; week/symbol-cluster bootstraps for the catalyst effect; the
EWMA/diurnal study itself (walk-forward, causal).
