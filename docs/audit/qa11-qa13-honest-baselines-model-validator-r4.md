# Model validation, round 4 (final acceptance): loop 3 on the uncommitted code, live bars

- Validator: `model-validator` (read-only), 2026-10-12. Saved by the orchestrator. Today's Yahoo bars (129/129, 1y/2y/5y/10y).
- Scratch `scratchpad/r4/`: `sweep.py` → `main.jsonl` (step 3; 4 ranges × 41 horizons 1…250 × 6 universes × momentum + 20 coins; 20,664 runs; universe passed as the Lab passes it); `step1.jsonl` (whole watchlist, h = 1, 2, 5, 20, 40, 60, 90, 120, all ranges); `corr.py`; `synth.py` (engineer's correlated walks, shipped se vs Driscoll–Kraay); `ccoin.py`, `ccoin2.py` (clustered coin); `momdet.py`; `e2e.py`, `newsnoise.py`; `analyze.py`, `detail.py`. Reference DK: `dk_se` in `r4/sweep.py`.

**Overall: not fit as it stands for the claim "beats … more than two standard errors".** The loop-3 gates are fit (class universes withheld, span rule works, withheld runs gate attention/attribution; per-decision coin false "beats" 0.25% vs nominal 2.3%). The error bar ignores correlation across instruments on the same dates: on real bars the shipped se is 1.1–2.3× too small for a coin and ~3.5× for momentum; every real-momentum "beats" the app now gives (incl. the Terminal's 60-day profile) falls to |z| ≤ 1.5 with a date-clustered se. Minimal next step (then fit with caveats): se = max(shipped, Driscoll–Kraay entry-date-clustered), and a clustered-coin acceptance test.

## Reproduced (independent code + `backtest.run`)
2y h=5 whole: n 18,958, 7,523 wins, 39.68% vs 39.44%, Δ +0.24, se 0.42 → "within". 10y h=60 whole momentum: n 94,218, 39,365 wins, Δ +2.36, se 0.51 (NW; binomial 0.16), z +4.6 → "beats". 2y h=60 whole momentum (Terminal "quarter", `sonar/horizon.py:123`): n 13,656, Δ +3.19, se 1.33, z +2.40 → "beats".

## Coin runs, whole watchlist, h ≤ 120 (step 3, 20 seeds) — "beats / below / verdict runs"
| Range | h 1–2 | 3–29 | 30–59 | 60–89 | 90–120 | "beats" | "below" |
|---|---|---|---|---|---|---|---|
| 1y | 0/0/40 | 0/7/140 | 0/11/40 (80 span) | — (180 span) | — (160 too few, 80 span) | 0/220 | 18/220 (8.2%) |
| 2y | 0/6/40 | 0/12/140 | 1/0/120 | 0/0/80 (100 span) | — (240 span) | 1/380 | 18/380 (4.7%) |
| 5y | 1/2/40 | 0/27/140 | 0/48/120 | 0/146/180 | 0/113/240 | 1/720 | 336/720 (46.7%) |
| 10y | 0/0/40 | 0/7/140 | 1/0/120 | 2/0/180 | 0/0/240 | 3/720 | 7/720 (1.0%) |

All ranges step 3: "beats" 5/2,040 = 0.25% [Wilson 0.10–0.57]; "below" 379/2,040 = 18.6% [16.9–20.3] (intervals too narrow — seeds share one path). Step 1: "beats" 1/520 (0.19%); "below" 122/520 (23.5%; 5y h=60, 90 20/20; 10y h=1 15/20). 5y "below" source: coin mean Δ −0.5 to −1.1 pt for h 20–110, z to −4.4 — the daily-bar/tie residual named in the ADR, against a se that is too tight. The low "beats" rate is partly luck of sign (negative residual pushes away from "beats"); it does not show validity.

Settings that still give any verdict (step 3, 41-horizon grid): 102 of 984 — whole watchlist only: 1y h ≤ 35 (11/41), 2y h ≤ 71 (19/41), 5y and 10y h ≤ 120 (36/41 each). Boundaries exact: 1y h=36 span (4.89 horizons); 2y h=72 span (4.92). Class universes: 0 verdicts in 16,800 runs (all `single_class`, `horizon` or no trials).

## Real cross-instrument correlation (`corr.py`)
Engineer's factor model: within = ρ_g + ρ_c, between = ρ_g; "moderate" 0.25/0.05, "heavy" 0.6/0.1.

| Live bars | Within class (pair mean) | Between classes | Global |
|---|---|---|---|
| 2y daily | 0.21 (mean \|ρ\| 0.26) | 0.06 | 0.10 |
| 2y weekly | 0.22 | 0.08 | 0.12 |
| 10y daily | 0.31 (mean \|ρ\| 0.34) | 0.10 | 0.15 |
| 10y weekly | 0.32 | 0.12 | 0.16 |

By class (10y daily): Crypto 0.54–0.61 (heavy); Index 0.36 (0.49 weekly); Equity 0.17 (2y) to 0.32 (10y); Commodity 0.14; Forex signed 0.03 but mean |ρ| 0.27–0.29 (quote conventions cancel signs). Volatility co-movement (corr of |r|): real within 0.22–0.29, between 0.08–0.11, global 0.11–0.16; Gaussian-implied moderate 0.055/0.002, heavy 0.33/0.009 (~0.09 global). Signed: real ≈ moderate within (crypto heavy), heavy between; on common volatility beyond heavy. Measured design effect (DK/se) on real whole-watchlist coin runs: 1.1 at h=1, ~1.5 at h=30, 1.9–2.3 at h=60–120 (matches synthetic "real-like" sd/se 1.2–1.95).

## Findings
**P1-D (new) — the 2-se verdict ignores cross-instrument correlation; "more than two standard errors" is false for momentum on real bars.** se at `sonar/backtest.py:537-553` (binomial/AC + NW over the per-symbol trial list), verdict `:570`, copy `:689`. An independent coin decorrelates directions across instruments; momentum aligns them (a whole class goes LONG together). Clustered-coin placebo (`ccoin.py`; one random direction per (class, ~h-day block), uninformative but correlated like momentum), 2y/5y/10y h 5–120: "beats" 77/320 (24% [19.7–29.0]), "below" 111/320, some false verdict 58.8% [53–64]; seed spread of Δ 2.5–3.9× the shipped se (a lower bound). Real momentum with DK: DK/se ≈ 3.5 (2y h=60 DK se 4.6 pt vs 1.33); every significant whole-watchlist momentum verdict (39 "beats", 2 "below") becomes non-significant (2y h=37–71 z 2.1–2.7 → zDK 0.6–0.9; 10y h=5–120 z 2.2–5.1 → zDK 0.8–1.5). Terminal 60-day profile (`ui/app.py:3447-3449`) today: "beats … by 3.2 points, more than two standard errors (1.3) … a reason to look closer"; zDK 0.69. Terminal 1-day: "below" (Δ −0.85, z −2.4; zDK −1.2). Drift aggravates it: per-asset detrending (diagnostic, full-sample drift) flips whole-watchlist momentum — 10y h=60 +2.36 → −0.98; 2y h=60 +3.19 → −6.57; 10y h=60 Equity +4.76 → −0.63, Index +2.29 → −2.53. Momentum "beats" is the realised drift of today's survivor watchlist.

Minimal next step: se = max(current, Driscoll–Kraay) — residuals (win − predicted − Δ) summed per entry calendar day across instruments, Bartlett kernel over L = ceil(avg_bars_held·365/252) days; pure Python, ~O(days·L).

| Placebo | False verdicts, shipped se | With DK floor |
|---|---|---|
| Clustered coin | 58.8% ("beats" 24.1%) | 11.2% [8.2–15.2] ("beats" 3.75%) |
| Independent coin, step 3 | "beats" 5, "below" 379 of 2,040 | "beats" 0, "below" 39 of 2,040 (1.9%) |
| Independent coin, step 1 | "below" 122/520 | 36/520 (6.9%; 10y h=1 is 13) |

Cost: under DK no real momentum setting gets a verdict. Residual: DK is biased down with few long-horizon blocks; widening L to 2× or 4h didn't help (10.9%, 13.4%) — the DK floor leaves the clustered coin at ~2× nominal. Recommended: adopt the DK floor; make the clustered coin the acceptance test (target ≤ 5% two-sided); if still above, per-run sign-randomisation p-value by (class, block) (forced LONG/SHORT pairs make it cheap). Keep the verdict copy off "two standard errors" until then.

**P1-E (pre-existing, judged path, outside loop 3) — the news verdict finds attention effects in pure noise.** Attention buckets use plain binomial se, no overlap/cross-section correction, no multiplicity across 4 buckets (`sonar/backtest.py:803-807`); each bucket vs the prediction rather than vs the others; `_news_verdict` (`:811-834`) turns any significant bucket into "Some attention levels / A news spike shifts the odds". `newsnoise.py` (random attention independent of prices, judged whole-watchlist runs): "shifts the odds" 0/7 at 2y h=5, 5/7 at 2y h=20, 4/7 at 5y h=20; 10y h=60 (`e2e.py`) all 4 noise buckets "significant" (inherit the run's +2.4). User-visible with "include attention" (`ui/app.py:2785-2786`). Fix: same clustered se; buckets vs each other (or vs the run's Δ); BH across buckets.

**P2-E (carried, worse at step 1)** — "did worse than a coin flip" common: 18.6% step 3 (5y 46.7%), 23.5% step 1; DK floor → 1.9% / 6.9%.

**P2-F (narrowed)** — attribution on judged runs uses NW over pooled trials only: 10y h=60 momentum "KEEP", volatility "INVERTED" (same drift/cross-section artefact). Withheld runs fully gated (confirmed end to end for single class, span, h > 120).

**P3** — universe defaults fail open (`sonar/backtest.py:700`, `ui/worker.py:62`; current callers pass it, `ui/app.py:2663`, `:3449`); withheld-horizon copy "even a coin-flip direction reads above" (`:671-672`) → "can read"; ADR 0001 timeout-monitor wording (`:83-84`).

## Verdict per claim
| Claim | Verdict |
|---|---|
| No verdict on single-class universes; universe explicit | Supported (0/16,800; `ui/app.py:2663`, `:3449`) |
| Entry span ≥ 5 horizons | Supported (1y h=35 judged / 36 withheld at 4.89; 2y 71 / 72 at 4.92) |
| Withheld runs gate attention/attribution | Supported (end to end) |
| Cap 120, n ≥ 100, 20 dates, AC floor | Supported |
| Whole-watchlist per-decision coin rarely "beats" | Supported (0.25% step 3, 0.19% step 1) |
| "Beats/below … more than two standard errors" is a valid 2-se test | **Unsupported** (se 1.1–2.3× too small for a coin, ~3.5× momentum; clustered coin false 59%) |
| Real momentum "beats" (2y h 37–71, Terminal 60-day; 10y h 5–120) | **Unsupported** (zDK ≤ 1.5; sign flips detrended) |
| "Did worse than a coin flip" for the coin | Unsupported at 5y and step 1 (47%, 23%) |
| News verdict "attention shifts the odds" on judged runs | **Unsupported** (fires on noise in 9/21) |
| Lab default "no edge", Δ +0.24 | Supported (reproduced) |
| Real data moderate or heavy | Within classes moderate (crypto heavy); between heavy; volatility co-movement beyond heavy; design effect 1.1–2.3 for a coin |
