# Model validation, round 6: loop 5 on the uncommitted code

- Validator: `model-validator` (read-only), 2026-10-12. Saved by the orchestrator.

**Overall: fit with caveats.** I'm downgrading P1-A to P2: the placebo now gets KEEP or INVERTED about 5–7% of the time, down from 24%. The refactor left the headline unchanged: 0 of 6,724 sweep runs moved. Nothing is P0 or P1. Before release, the Learn-tab docs still contradict the new copy (P2-B).

- **Code state.** `sonar/backtest.py` sha `a3b5cdb…` was the same at the start and at the end of every run.
- **Bars.** I reused the r5 live bars (fetched 04:10 today).
- **Scratch.** Everything is in `/private/tmp/claude-501/-Users-as-Documents-lab-active-sonar/a26ec703-42e8-43e7-ab51-f430c0bd1c34/scratchpad/r6/`:
  - `sweep6.py` → `main.jsonl`
  - `attr6.py` → `attr6.jsonl`, analysed by `an6.py`
  - `e2e6.py` → `e2e6.jsonl`
  - `news6.py` → `news6.jsonl`, analysed by `an_news6.py`
- **Repo.** I wrote nothing to it (`PYTHONDONTWRITEBYTECODE`).
- **Concurrent session.** Another session's `mutate6.py` is running, but on a scratch copy (`qa6/repo`), not on the repo.
- **Playbook.** `model-validator.md` is `status: baseline`, so it counts as stale.

## (a) Attribution placebo on the new code

Setup: real momentum trials, with `c_news` replaced by noise. 20 seeds per (setting, design).
- "Orig6" means the r5 settings with the same seeds.
- "All 12" adds 1y h5, 1y h20, 2y h40, 5y h5, 10y h20 and 10y h120. All 12 settings are judged.
- Intervals are Wilson; CB is a cluster bootstrap over settings.

| Design | KEEP/INV r5 (orig6) | KEEP/INV now (orig6) | KEEP/INV now, all 12 (n=240) | Survives FDR, all 12 | IC t² / spread z² |
|---|---|---|---|---|---|
| iid per trial | 1/120 | 1/120 (0.8%) | 0.4% [0.1–2.3] | 2.5% [1.2–5.3] | 1.08 / 0.93 |
| Per (class, block) | 29/120 (24%) | **6/120 (5.0%) [2.3–10.5]** | **7.1% [4.5–11.0], CB [4.6–10.0]** | 10.0% [6.8–14.4] | 1.52 / 1.55 |
| Per symbol, persistent | 14/120 (12%) | 10/120 (8.3%) [4.6–14.7] | **4.6% [2.6–8.0], CB [1.7–7.9]** | 6.2% [3.8–10.1] | 1.38 / 1.64 |

- I reproduced the engineer's 5.0% and 8.3% exactly.
- **P1-A is resolved to "fit with caveats".**
  - The clustered designs still grade about 10–18 times as often as iid (roughly 1 run in 14–20).
  - The IC test runs at about 1.4–1.5 times its nominal variance.

## (b) The DK port for IC products and the quintile spread

I checked it against my own sparse-loop DK reference on the same rows and lag.

| Check | Result |
|---|---|
| IC DK se, relative difference | ≤ 1.7e-15 |
| IC t, absolute difference | ≤ 2.9e-15 |
| Spread DK se, absolute difference | ≤ 5e-5 (the shipped value is rounded to 4 dp) |
| Lag | identical in all 24 component checks |

- On real components DK sets the bar for the IC in 24 of 24 cases. It is 1.3–2.8 times the Newey–West se.
- The spread's DK se is 1.9–9.0 times the binomial one.

## (c) Real-bar attribution on 12 judged settings

**Momentum**
- WEAK or UNCLEAR everywhere; never KEEP.
- 10y h60 is UNCLEAR, p 0.29.

**"Ranks backwards"**
- False everywhere.
- The largest |blend t| is 2.34 at 5y h5, below Z_CLAIM 3. 2y h1 reads −1.93.

**Volatility**
- DROP on 10 of 12 settings.
- INVERTED on 2 of 12: 1y h5 (p 0.0096) and 5y h5 (p 0.0048).

Credibility: **weak.**
- Volatility is a persistent per-symbol reading. That is exactly the regime where the date-clustered bar is still too narrow: persistent placebo IC t² is 1.6 on orig6.
- At a ~5% false rate, two or more grades in 12 happens about 12% of the time.
- 1y lies inside 5y, so the two INVERTED results are not independent.
- The sign is negative on all 12 settings, but the settings share bars. That is suggestive, not a finding.

## (d) Headline numbers did not move

**Sweep (step 3, 6,724 runs)**
- Identical in n, Δ, se, se_dk, lag, withheld and class on every run.
- Only the verdict text changed (839 runs: 63 beats, 202 below, 574 withheld), as intended.
- Shipped `_dk_se` matches my reference to ≤ 1.1e-16.

**Headline figures, recomputed from raw trials and identical to r5**

| Setting | n | wins | Δ | se | z | Verdict |
|---|---|---|---|---|---|---|
| Lab default, 2y h5 | 18,973 | 7,504 | +0.11 | 0.88 | 0.12 | "within 1.8 points" |
| 10y h60 | 94,213 | 39,361 | +2.36 | 1.86 | 1.27 | – |

- Terminal profiles: z = −1.41 (1-day), 0.57 (20-day), 0.66 (60-day); 250-day is withheld for "horizon".
- Clustered coin: 11.37% [10.1–12.8]; beats 3.04%, below 8.33%.
- Independent coin: 1.62%.
- Momentum: 0 of 102 judged runs got a verdict.

## (e) Is "about 1 run in 10" fair?

**Yes, as a pooled figure.**
- Clustered-coin false verdicts by step: 11.4% at step 3, 11.0% at step 1, 7.8% at step 10, 10.6% at step 30.
- By range: 8.2–13.8%.

It understates specific settings:
- 2y h30–59: 18.3% [12.4–26.2]
- 5y h90–120: 17.9% [13.6–23.3]
- At step 3, 23% of (range, h) settings were at or above 20% over 20 seeds. Part of that is 20-seed noise.

It overstates the one-sided rate that matters to someone reading "beats":
- 3.0% overall, up to 8.3% (2y h30–59).

So it is conservative on average for "beats". Optional tightening: "…about 1 run in 10 overall, and up to about 1 in 5 at some range and horizon settings." The "below" copy ("can land this far below too") is supported: random-direction "below" was 8.3%.

## (f) Attention gap over attention rows, partial coverage

Setup: attention noise only on the 25 watchlist symbols that have a pageview article (21–22% of setups). 6 settings × 8 seeds × 3 designs = 144 judged runs.

| Measure | Value |
|---|---|
| "Shifts the odds", new reference | **3/144 = 2.1% [0.7–5.9]** |
| Same, old whole-run reference | 7/144 (4.9%); market-wide spike design 5/48 old vs 2/48 new |
| Bucket z² | 0.55 (conservative) |
| Spike-bucket z² | 0.83 |
| News component graded KEEP on noise | 3/144 |
| Gap of attention rows minus whole run | 0.6–2.8 pts on these bars |

The fix is correct and helps. On real bars it is a small effect.

## Findings

**P2-A (was P1-A): attribution still over-grades clustered and persistent components, and the INVERTED copy is unhedged.**
- The rates are 4.6–7.1% (see a). Real volatility INVERTED at 1y and 5y h5 is in that regime.
- The copy "Flip its sign or drop it" (`sonar/backtest.py:1203`) is an unqualified instruction.
- Fix options:
  - Hedge it like the headline: "…from one replay of past prices: a reason to look closer, not a finding".
  - Add symbol clustering (a two-way cluster bar) for components.

**P2-B (carried from r5 P2-D): docs contradict the new copy.**
- `static/docs.html:627-628` still says "Two standard errors on the difference. This is the number that decides."
- `:637-652` still describes Newey–West only, with the binomial trials-to-band table. 18,973 trials give ±1.8 points, not ±0.7.
- `docs/specs/qa11-qa13-honest-baselines.md:201-206` still has the old "two standard errors" / "worse than a coin flip" strings.
- CHANGELOG, CONFIDENCE and the ADR are not updated.

**P3 items:**
- **DROP has no error bar.** "The weight is buying nothing" (`:1207-1209`) comes from a point estimate of the leave-one-out cost, as small as −0.0018 (2y h5). It is now the main real-run grade (volatility 10/12) and is shown in red. On noise it fires 18–28%. This is pre-existing and out of loop-5 scope.
- **Placebo acceptance test.** It allows 3/24 (12.5%) and IC z² ≤ 2.0 (`tests/test_backtest.py:1255`). Its docstring correctly calls it a regression guard.
- **Carried from r5:**
  - Same-day pageviews include hours after the US close (`:257-277`), a minor look-ahead.
  - `run()` defaults `universe` to the whole watchlist, so it fails open (`:799`).

## Verdict per claim

| Claim | Verdict |
|---|---|
| Refactor leaves the headline se and verdicts unchanged | Supported (0/6,724 differ; 12/12 end-to-end identical) |
| IC and spread use the date-clustered DK bar, port correct | Supported (≤ 1.7e-15; DK binds 24/24) |
| Class-block placebo 24% → 5.0% | Supported (6/120 reproduced; 7.1% [4.5–11.0] over 12 settings) |
| Persistent placebo 11.7% → 8.3% | Supported (10/120; 4.6% [2.6–8.0] over 12) |
| Real: volatility INVERTED 4/6 → 0; 10y h60 KEEP → UNCLEAR; 2y h1 blend t −1.93 | Supported on the r5 settings; INVERTED remains at 1y and 5y h5 (2/12) |
| Real volatility INVERTED is a finding | Unsupported (inside the placebo false rate) |
| Power is unchanged (IC 0.035 kept 28/30) | Unverifiable (not re-run) |
| "About 1 run in 10" | Supported as pooled; per setting up to ~1 in 5 |
| "Can land this far below too" / no "worse than a coin flip" | Supported (8.3%) |
| Attention read against the attention rows' own gap | Supported (2.1% [0.7–5.9] false vs 4.9% old) |
| "No effect detected, which is not the same as none" | Supported (bucket z² 0.55) |
| Clustered coin ≤ 5% | Unsupported (11.4%; open by owner decision) |
| `static/docs.html` error-bar text | Unsupported (still says "two standard errors") |
| Placebo test guards the floor | Supported as a regression guard only |

Relevant files:
- `/Users/as/Documents/lab/active/sonar/sonar/backtest.py` (`:770-795`, `:973-1007`, `:1127-1143`, `:1176-1215`)
- `/Users/as/Documents/lab/active/sonar/static/docs.html`
- `/Users/as/Documents/lab/active/sonar/docs/specs/qa11-qa13-honest-baselines.md`
- `/Users/as/Documents/lab/active/sonar/tests/test_backtest.py`
