# Model re-validation, round 2: P1-1 under MIN_WINDOW_HORIZONS = 2.0 (uncommitted)

- Validator: `model-validator` (read-only), 2026-10-11. Saved by the orchestrator.
- Scratch: session scratchpad `r2/` — `v9_floor.py` (placebo grid), `compact.py`, `v10_sweep.py`, `sweepshow.py`, `v11_detrend.py`, `v12_onset.py`, `v13_tiny.py` (`v13.json`), `indep.py` (independent reproduction, no `sonar` imports), bars `bars_1y.pkl`, `bars_5y.pkl`, `bars_10y.pkl`, `../bars.pkl` (2y).
- Live Yahoo bars, all 129 symbols, 1y/2y/5y/10y (10y excludes CL=F — the app crashes on it, P2-D). Real momentum, 4 coin seeds, always-LONG, always-SHORT; h = 5/20/60/120/250 at 1.5:1 and 2:1 plus fine sweeps near the floor's edge; per-asset detrend; universe × horizon small-sample search (456 runs). Model tests pass (66).

## Verdict: not fit as it stands
The floor removes the data-end truncation mechanism, but the acceptance test fails: at the shipped 1.5:1 a significant, edge-suggestive coin placebo remains at user-selectable settings (5y, h ≥ ~210), from drift convexity, which the floor cannot fix. The floor also creates tiny single-period samples that still get a "beyond two standard errors" verdict, including se = 0. **Fit with caveats** with: (1) cap the Lab horizon or suppress the verdict above h = 120 (at h ≤ 200 no coin seed read "beats" on any range; at h ≤ 120 the margin is wide); (2) a minimum-sample guard before any verdict (P1-B).

## Findings
**P1-A — P1-1 not closed at long horizons on 5y; the bias moved from truncation to drift convexity.** Coin placebo, 1.5:1, 5y (4 seeds): h=200 +0.3 to +1.1 pt, 0/4 "beats"; h=210 +0.7 to +1.7 (z ≤ +3.0), 3/4; h=230 +1.8 to +2.1 (z +3.1 to +3.6), 4/4; h=250 +2.94/+2.15/+1.98/+2.39 (z +4.7/+3.5/+3.1/+4.0), 4/4. 10y h=250: +0.55 to +0.96 (z +1.6 to +2.7), one seed formally "beats" (borderline). Real momentum 5y h=250 reads "+6.6 points … a reason to look closer"; ~2.4 pt is placebo bias. Mechanism: detrending each asset's own drift takes 5y h=250 from +2.37 to −0.37 (no seed significant); closed form (q(m)+q(−m))/2 − q(0) at 1.5:1 is +2.4 to +3.4 pt at |m| = 0.5 for T = 2–4; at h=250 m ≈ the asset's annual Sharpe, so the effect grows with √h. The old code on the same trials read −0.45 to −1.13 (conservative); the new reads +2 to +3 — the original P1-1 pattern. What closed: the removed trials were exactly the biased ones (short-window coin +5.7 pt at 2y h=250, +28.5 pt at 1y h=250). Fixes in order of effort: cap the horizon / suppress the verdict at h > 120; or compare against a deterministic both-directions placebo (absorbs drift convexity and fat tails empirically).

**P1-B — the floor creates tiny single-period samples that still get a 2-se verdict.** Near the edge compared trials come from a few days/weeks of entries (1y h=120: n=15 from 9 symbols, all entered 2026-02; 2y h=238: entries span 12 days). 1y h=114–120: momentum n=15–65, every trial a STOP → `sonar/backtest.py:411` se = 0.00, `:429` significant = True → "Hit rate is 36.8 points below the prediction, beyond two standard errors", "±0.00 at 2 s.e.". Positive direction reachable by universe choice: Index universe 2y h=168, n=10 from 5 symbols, "beats the prediction by +53.2 points, more than two standard errors (9.5)"; h=150–165 +42 to +50 pt, n=46–272. 41 of 456 searched runs read "beats"; 38 gave a verdict on n < 100. Effective sample ≈ one market move; se ignores cross-symbol correlation (known P1-3), which the floor makes bite. Fix: minimum compared n and minimum distinct entry dates / entry span before any verdict; Wilson/continuity floor on se; later, se clustered by entry date.

**P2-A — the floor counts bars, so it selects crypto, and the instrument count is wrong.** Crypto has 365 bars/yr vs ~250. At 1y h ≥ ~86 and 2y h ≥ ~170 the whole-watchlist comparison is 100% crypto (36% vs 24% of decision points at 1y h=60; 31% at 2y h=120). The Lab still says "N across 129 instruments" (`summary["symbols"] = fetched`, `sonar/backtest.py:544`, `ui/app.py:2700`). In the crypto-only zone the coin placebo reads −5 to −14 pt, significant 8/8 at 2y h=166–214 → false "did worse than a coin flip". Fix: show instruments actually compared, ideally by class.

**P2-B — negative-side false verdicts exceed the ADR's ±0.6 at medium/long horizons.** 5y h=60 coin −0.66 to −1.05 pt (z −2.1 to −3.4), 4/4 "below"; 1y h=40–46, 4/8 "below". Drift removed, the underlying model bias at h=150–250 is ~−1.6 to −2.4 pt (partly offset by P1-A at h=250). Conservative, but "worse than a coin flip" is false for a literal coin. ADR residual should name horizons.

**P2-C — the floor selects older entry dates** (disclosure, not look-ahead): median entry all → compared: 2y h=120 2025-12 → 2025-07 (last 2026-02); 5y h=250 2024-09 → 2023-10 (last 2025-05); 10y h=250 2022-06 → 2021-04 (last 2025-05). Fix: show the compared entry span.

**P2-D (pre-existing, blocks 10y)** — a 10y Whole-watchlist or Commodity run crashes: CL=F closed at −37.63 on 2020-04-20; `_vol` (`sonar/backtest.py:222-223`) guards `closes[i-1] > 0` but not `closes[i]` → `ValueError: math domain error`; the worker (`ui/worker.py:74`) shows only that error. AAVE-USD has a low ≤ 0 in 10y but does not crash.

**P3** — docs: ADR 0001:83 still "monitored by `timeout_share` against `timeout_share_expected`"; ADR doesn't describe the floor and its alternatives reject what is now partly adopted; `sonar/backtest.py:443-445` comment still calls the timeout share a visible check (default: 12.1% realised vs 5.3% expected with the baseline fine); `CONFIDENCE.md:587-589` "39.58% vs 39.99%". Momentum readings that are not baseline bias: 2y h=60 (+3.15, z +2.4) and 10y at every horizon (z +2.7 to +4.8) while coin is clean (2y h=60 both-directions +0.14) and LONG-only reads +8.7 — drift/survivorship confound with cross-sectionally understated se; pre-existing.

## Share of decision points the floor removes (momentum, 1.5:1, step 3; resolved removed in brackets)
| range | h=5 | h=20 | h=60 | h=120 | h=250 |
|---|---|---|---|---|---|
| 1y | 3.2% (1.6%) | 15.7% (7.6%) | 56.2% (39.2%) | 99.3% (99.2%), n=15 | 100%, n=0 |
| 2y | 1.6% (0.8%) | 7.5% (3.4%) | 24.7% (13.1%) | 56.8% (42.1%) | 100%, n=0 |
| 5y | 0.6% | 2.9% | 9.1% | 19.3% | 45.2% (29.9%) |
| 10y | 0.3% | 1.5% | 4.7% | 9.6% | 21.2% (11.7%) |

## Lab default under the floor (for docs)
2y, h=5, step 3, 129 symbols, bars 2026-10-11: n = 18,974 (7,531 wins); hit 39.69%; predicted 39.44% (40% untimed); Δ +0.25 pt, se 0.42; timeouts 2,609 (12.09%; 85 at data end), expected 5.32%; too near the end 360 (1.6% of 21,943); implied drift +0.0042σ; expectancy beyond no-edge +0.0063 R; verdict "within 0.8 points … no edge detected". vs pre-floor 39.64% / 39.37%. Reproduced independently (n, wins, hit, predicted, timeouts, short windows exact at h=5; 2y h=60 n=13,677, Δ +3.15; q(T=4)=0.39458, q(T=2)=0.36718).

## Verdict per claim
| Claim | Verdict |
|---|---|
| P1-1 closed at every user-selectable horizon/range at 1.5:1 | **Unsupported** (5y h ≥ ~210; 10y h=250 borderline; P1-B tiny-n) |
| Floor removes the truncation-driven bias | Supported |
| A full window is never affected | Supported |
| Lab default reads "no edge" at Δ +0.25 | Supported |
| 39.46% baseline at 1.5:1, 4-horizon window | Supported |
| ADR residual ±0.6 pt | Supported at h=5; unsupported at h ≥ 60 |
| "N across {symbols} instruments" | Unsupported at long horizons |
| "Beyond two standard errors" at n = 10–65 | Unsupported (se = 0 / single-period) |
