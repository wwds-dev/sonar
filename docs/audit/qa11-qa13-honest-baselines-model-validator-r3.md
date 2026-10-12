# Model re-validation, round 3: the P1-A cap and P1-B guards (uncommitted)

- Validator: `model-validator` (read-only), 2026-10-11. Saved by the orchestrator.
- Scripts/outputs in the session scratchpad `r3/`: `sweep.py` → `main.jsonl` (`analyze.py`, `matrix.py`); `sweep2.py` → `detrend10y.jsonl`, `step1.jsonl`, `step10.jsonl`; `cluster.py`, `paired.py`, `attr.py`; `synth.py`, `synth2.py` → `synth_all.jsonl`; `kurt.py`, `tails.py`; `indep3.py` (independent reproduction, no `sonar` imports).
- Code: current `summarise`/`run_symbol` (cap, n ≥ 100 and dates ≥ 20, Agresti–Coull floor, negative-close guard). Bars: Yahoo today, 129 symbols, 1y/2y/5y/10y (10y incl. CL=F). Grid: 6 universes × 4 ranges × 41 horizons (1,2,3,5,7,10,15…120, every 3 days 60–120, plus 121,130,150,200,250), step 3; real momentum + 20 coin seeds per setting (forced-LONG/forced-SHORT passes): 20,664 runs. Plus step 1/10 spot checks, per-asset detrending, date-clustered se, a paired both-directions baseline, synthetic walks (Gaussian, t3 per sub-step, t3 per day; 16 walk-sets × 20 coins), end-to-end `backtest.run` on 10y Commodity.

**Verdict: not fit as it stands.** At 1.5:1 and h ≤ 120 a coin still gets "Hit rate beats the prediction … a reason to look closer" at many Lab settings — all in single-class universes; the Whole-watchlist choice is clean for edge-suggestive verdicts on every range. **Fit with caveats** with one small change: no verdict on single-class universes (numbers only) — the Lab then judges only the whole watchlist (clean), and the Terminal uses only the whole watchlist.

## Reproduced exactly (independent code)
Lab default (2y, h=5, all): n 18,974, 7,531 wins, 39.69% vs 39.44%, Δ +0.25, se 0.42 → "within". 2y h=60 all momentum: n 13,677, Δ +3.15, z +2.37 → "beats". 10y Equity h=100 momentum: Δ +5.66, z +5.13 (always-LONG +18.56, always-SHORT −17.33 → coin ≈ +0.6). 2y Index h=120 momentum: Δ +22.73, z +4.35. 2y Commodity h=73 momentum: Δ +8.93, z +2.16.

## Coin runs that got a verdict, h ≤ 120 — "beats" / verdict runs, bands [1–2] [3–29] [30–59] [60–89] [90–120]
| Range | Whole watchlist | Problem classes |
|---|---|---|
| 1y | 1/40, 0/140, 0/120, 0/180, 0/80 | Forex 3/40, 12/140 |
| 2y | 0/40, 1/140, 0/120, 0/180, 0/240 | Equity 90–120: 53/240; Index 90–120: 37/240 (3–59: 12/260); Commodity 60–89: 82/180, 90–120: 92/240; Forex h 1–2: 10/40 |
| 5y | 0/40, 1/140, 0/120, 0/180, 0/240 | Forex h 1–2: 20/40; Index 3/40, 4/140 |
| 10y | 0/40, 0/140, 2/120, 4/180, 0/240 | Equity 30–59: 21/120, 60–89: 86/180, 90–120: 41/240; Crypto 3–29: 11/140, 30–59: 18/120; Commodity 60–89: 19/180, 90–120: 8/240; Forex h 1–2: 26/40 |

Overall 607 of 15,540 coin verdict runs read "beats" (3.9%) and 2,374 "below" (15.3%) vs ~2.3% each for a valid 2-se test. Market-level coin z (mean of 20 seeds): Whole watchlist never above +1.5 in 136 settings (mean −0.91; 23 below −2); Equity 21 settings above +1.5; Commodity 17; Index 4; Forex 4; Crypto 2 (and 62 below −2).

"Did worse than a coin flip" (conservative false verdict): Whole watchlist 1y 154/560 (27%), 2y 20/720 (3%), 5y 350/720 (49%; h=55–110 14–20/20 seeds, Δ −0.7 to −1.2), 10y 25/720 (3.5%). Crypto h ≥ 60: 2y 118/180 and 238/240; 5y 173/180 and 239/240; 10y h ≥ 83 15–20/20 (Δ −2 to −7). 5y Index h 30–89: 111/300; 1y Index h 60–76: 59/120.

## Findings
**P1-C (new) — the 120-day cap does not close P1-A on single-class universes** (universe list `ui/app.py:2339-2341`, horizon 1–250 `:2349`, step 1–30 `:2352`). Mechanisms: (1) drift convexity from survivorship drift (10y Equity h 30–118: up to 14/20 coins "beats"; h=60 coin +0.79, z ≤ +3.9; detrending h=60 +0.79 → −0.43, h=100 +0.67 → −0.65; date-clustered se reduces but doesn't remove — 5/20 still significant with hold-block clusters); (2) one-episode samples with cross-sectional correlation (2y classes h ≳ 63–120: entries span 1.2–2 horizons, e.g. 2y Equity h=120 entries 2025-04-04 → 2025-10-22 = 2 hold-blocks; coin Equity +3.5, Index +4.8, Commodity +4 to +5 pt; step 1 worse — 2y Commodity h=73 20/20, 2y Equity h=120 16/20); (3) daily-bar/jump artefact at h=1–2 on Forex (5y/10y: h=1 coin +1.1 to +1.4 pt, 14 and 17/20 "beats"; fades by h=3); 10y Crypto h=25–30 (+0.8, 11–12/20) survives detrending but not date clustering — partly chance. Real momentum in the same cells is inflated by the same effects yet gets "reason to look closer" (2y Index h=120 +22.7; 10y Equity +4.8 to +5.7 for every h 40–120).

**P1-B — partly closed.** Works: no verdict with n < 100 or < 20 dates (0 of 16,317 verdict runs); minimum se 0.16 pt; 735 runs withheld too few. Does not: 20 distinct dates ≠ independent moves — 1y Whole watchlist h=100: 230 trials, 22 dates over 63 days (0.4 horizons), all crypto, momentum "16.6 points below … beyond two standard errors"; 2y Index h=120: 795 trials over 1.2 horizons → "beats by 22.7". Coin "beats" rate by entry span: < 2 horizons 9.1%; 2–5 6.1%; 5–10 0.9%; 10–20 0.7%. Fix: entries must span at least ~5 horizons.

**P2-E — the conservative false verdict is common** (rates above); for a literal coin "did worse than a coin flip" is false. ADR's ±0.6 wrong at h ≥ 20 on 5y and on crypto.

**P2-F — attribution is outside the cap and guards.** `summary["attribution"]` (`sonar/backtest.py:691`) still gives KEEP/DROP/INVERTED at h > 120 and on one-episode samples; a coin produced momentum "KEEP" (IC +0.024, "survives FDR") on 10y Equity h=60 in 1/3 seeds; 10y Commodity h=121 (no verdict) still shows "volatility DROP".

**P3** — withheld copy (`:597`) "even a coin-flip direction reads above the prediction" is not general (10y Whole watchlist h=130–200 coin −0.2 to −0.4; crypto far below): say "can read". Docs stale: ADR 0001:83 timeout monitor; ADR silent on cap and guards; `CONFIDENCE.md:587`. Expected-timeout comment: still 12% realised vs 5% expected.

**Closed:** P2-D (CL=F guarded `sonar/backtest.py:252`, `:350`; 10y Commodity and Whole watchlist run end to end at h=5, 60, 121); P2-A/P2-C (instruments by class, "(of N fetched)", entry span); cap boundary 120/121.

## The Student-t(3) synthetic finding
Real bars, 2y h=120, Whole watchlist: clean (0/20 "beats", coin +0.20, z −1.1 to +1.4; h 90–120 0/240); 2y classes are not (P1-C). Tails:

| Returns | Daily excess kurtosis (median/asset) | Pooled σ̂-standardised kurtosis | P(\|z\|>5) per 1,000 |
|---|---|---|---|
| Real 2y | 5.4 | 21.5 | 3.5 |
| Real 10y | 10.3 | 16.9 | 3.5 |
| t3 per sub-step | 1.3 | 11.6 | 1.3 (lighter than real) |
| t3 per day | 9.1 | 128 | 6.5 (~2× real) |

Placebo on synthetic walks shaped like the 2y whole watchlist, h=120, 16 walk-sets × 20 coins: Gaussian −0.31 ± 0.20 pt, "beats" 0.3%; t3 sub-step +0.12 ± 0.19, 3.4%; t3 per day +0.31 ± 0.26, 14.7% (between-set spread 1.02 pt vs reported se 0.87). The engineer's +2.4 pt (1/4 seeds) is a draw from the between-set spread (set means reach +1.87), not a stable mean bias; heavy tails understate se and fatten the false "beats" tail; real tails sit between the two constructions; real whole-watchlist bars are clean.

## Lowest safe cap
Whole watchlist: 120 is enough for edge-suggestive verdicts (9 of 2,720 seed runs, 0.3%). Single-class universes: no cap is safe — failures start at h=1–2 (Forex), h=25 (10y Crypto), h≈45 (10y Equity), h=63 (2y Commodity); the lowest uniform cap clearing every class and range for h ≥ 3 is 20 days (Forex h=1–2 still fails). Recommendations: (1) no verdict on single-class universes; or (2) a paired both-directions placebo, (LONG + SHORT)/2 per decision, with a sign-randomisation se (coin false "beats" 0.5–4% in all 11 cells tested, incl. the worst), plus a minimum entry span of ~5 horizons for the one-episode problem.

## Verdict per claim
| Claim | Verdict |
|---|---|
| P1-A closed at every user-selectable setting | Unsupported for class universes (P1-C); supported for Whole watchlist, all ranges |
| No verdict above 120 days | Supported for the headline; attribution not covered (P2-F) |
| P1-B: no verdict under 100 trials or 20 dates | Supported |
| P1-B: error bar never 0 | Supported (Agresti–Coull, `sonar/backtest.py:493`) |
| P1-B: tiny/one-move samples get no verdict | Unsupported (spans 0.4–1.2 horizons still judged) |
| Negative-close guard | Supported |
| Instruments compared / entry span disclosed | Supported |
| Withheld copy "even a coin-flip … reads above" | Unsupported as general (P3) |
| Lab default "no edge" at Δ +0.25 | Supported (reproduced) |
| t3 synthetic bias in real bars | Not on Whole watchlist; a different, larger problem on class universes |
