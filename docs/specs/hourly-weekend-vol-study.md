# Spec: Weekend / hour-of-week term in the hourly BTC volatility forecast (study only)

- Status: draft (revision 2, after `docs/audit/hourly-weekend-vol-study-domain-finance.md`)
- Owner approval: pending (GATE: new work). **Approval freezes every number below.**
- Priority: P2 (research; nothing user-visible, nothing live depends on it)
- Source: `docs/research/2026-10-industry-techniques-shortlist.md`, item 1
- Playbook: `docs/playbooks/product-manager.md` is `status: baseline` (never radar-verified); unverified guidance.

## Problem
The Terminal's sigma is `forecast()` in `sonar/research/hourlyvol.py`: EWMA (lambda 0.94) on
deseasonalised r^2 times an hour-of-day factor (24 cells, 1440 h). `sonar/model.py` feeds it into
`prob_up = Phi(ln(c/o)/(sigma*sqrt(tau)))`. Sigma is the input SONAR estimates itself rather than
reads from the market price. The profile has no day-of-week or weekend term. Whether that costs
accuracy is a **hypothesis, not a known defect**; nobody has measured it in SONAR.

Evidence and limits: one unreviewed GitHub repo *reports* a weekend dummy cutting QLIKE ~15% and
per-weekday dummies ~22% (DM p < 0.001) on BTC **daily** variance from 5-minute data, with no EWMA
comparator (the shortlist's [V] means three agents confirmed the repo states this, not that it was
reproduced). That could be a daily-aggregation artefact; at one hour, EWMA (half-life ~11 h) may
already absorb it. A 2025 equities paper is [S], unread, and is not cited as evidence.

## User and goal
User: the owner (SONAR is owner-only today). The result note must not enter `static/docs.html` or
`ui/words.py` without Define/Design and a domain review.

Goal: one pre-registered verdict on whether a weekend factor, or a 168-bucket hour-of-week profile,
lowers out-of-sample hourly **forecast loss** (QLIKE) versus the current estimator. A DROP is a
successful outcome. **This is forecast accuracy, not profit; no trading, costs or slippage are
involved (not applicable).** A better sigma is a better-scaled forecast, not a trading advantage.

## Pre-registration (FINAL; frozen by owner approval)
**Freeze mechanism.** On approval the owner records the approving commit hash here and in the
result block. The runner embeds the SHA-256 of this file as approved, prints it, and **refuses to
run if the file differs**. Any later change to a number below is a new study with a new family.
**Data cut-off:** one pull of 730 days ending at the last closed hour at run time; record endpoint,
symbol, first/last bar, bar count and a hash of the series. The runner asserts every step is exactly
3600 s (a gap aborts). The sample is **already seen** (B0 was scored on this history), so the
result is exploratory confirmation, not a clean holdout, and must say so.

**Estimators** (all causal: factors read before the hour is pushed; weekday = `((t//86400)+3)%7`,
0 = Monday, using the open time of the *scored* hour, i.e. `times[1:]` like `hods_from_times(times)[1:]`;
weekend = Sat/Sun UTC, so Sun 23:00 is weekend and Mon 00:00 is not). Clamp = `PROFILE_CLAMP`
(0.25, 4.0), applied to **each factor separately**; products are not re-clamped.
- **B0** = shipped `ewma_diurnal` (24 cells, raw r^2, 1440 h).
- **B0L** = B0 with a 4368 h window (isolates window length from profile shape).
- **V1** = B0 plus a weekend factor. f_h exactly as B0. For every hour in the 1440 h window store
  rd2 = r^2 / f_h(as of before that hour). g_weekend = mean(rd2 over weekend hours) / mean(rd2 over
  all hours); g_weekday likewise; each clamped; g = 1 if a class has < 100 hours. EWMA runs on
  r^2/(f_h*g_c) (c = class of the hour, factors as of before it); forecast = EWMA * f_h*g_c of the target hour.
- **V2** = 168 cells (weekday x hour), raw r^2, window **4368 h (26 weeks, ~26 per cell)**, same
  clamp; EWMA on r^2/f, forecast = EWMA * f. Windows are fixed by arithmetic (the existing
  `DIURNAL_WINDOW` argument), not tuned on data.
- Scoring: all five models on the same hours, starting after 4368 h of warm-up (~13,150 scored
  hours), 6 contiguous blocks of n//6 (remainder dropped, ~2,190 h each).

**Test.** d_t = loss_base - loss_variant (positive = variant better). t from
`stats.newey_west_t(d, lags=168)`; the weekly cycle is where a weekday-structured differential
autocorrelates, and the repo default (~9 lags) would be too short. One-sided
p = 0.5*normal_p(t) if t > 0 else 1 - 0.5*normal_p(t) (`normal_p` is two-sided). Non-gating context
lines: the same at lags 24 and 9, and `stats.bootstrap_ci` on the mean d (moving block, 168).
This supersedes the module note that no HAC is needed: that holds for the score, not for
differentials between nested forecasts. A statistician's check is requested (open question).

**Family = 3 one-sided comparisons:** V1 vs B0, V2 vs B0, V2 vs B0L. alpha = 0.05/3 = **0.0167**
each. B0L vs B0 and other models (garch, trailing72) are reported as attribution only, not
hypotheses. Prior five-model study excluded: same data, other question; its selection of B0 makes
B0 harder to beat, which biases against the variants (conservative).

**Verdict** (I = pooled improvement vs comparator, W = blocks won of 6, p as above), first match wins:
1. NOT RUN: any control below failed.
2. INSUFFICIENT: < 2,000 scored hours.
3. KEEP: I >= **1.0%**, W >= **5**, p < 0.0167. For V2 additionally I > 0 and p < 0.0167 against
   B0L; otherwise label "V2: LONGER WINDOW ONLY" and the words "weekday effect" are not used.
4. WEAK: I >= 1.0%, p < 0.0167, W <= 4.
5. DETECTED, BELOW THRESHOLD: 0 < I < 1.0%, p < 0.0167.
6. DROP: everything else.
The 1.0% is a judgment, not power-derived. The runner also reports it as the mean absolute change in
displayed P(up) at a half-sigma move on the scored hours, so the owner sees it in the user's unit.

**Controls** (offline, seeded, sigma 0.004 where flat, N = 4368 + 8760 hours, series seeds 1..):
- C1 flat volatility, seed 7 (every build): V1, V2 pooled QLIKE >= 0.995 x B0 and neither KEEP. Size check
  (marked slow, not every build): 200 seeds, per-variant rejection rate at alpha 0.0167 must be <= 5% (10/200;
  expected ~3). Failure = apparatus manufactures a pattern; study does not run.
- C2 planted weekend 1.5x: V1 must meet verdict rules 3's I > 0, W >= 5, p < 0.0167 (no hand-derived % gate).
- C3 planted Tuesday-only 13-20h UTC loud (2x): V2 must KEEP including vs B0L.
- C4 equivalence and causality: the study path and a `forecast()`-style path give identical V1/V2 sigma
  (rel 1e-12) at origins across a run; B0 reproduced to 1e-12; boundary test for Sun 23:00/Mon 00:00;
  perturbing the return at hour i leaves forecasts for hours <= i unchanged.
- **Power simulation (reported, non-gating):** weekend sigma 1.05x, 1.1x, 1.2x, 1.3x, 50 seeds each, detection
  rate for V1. This replaces hand arithmetic and states the study's real resolving power.

## Scope
`sonar/research/hourlyvol.py` study path only (new profile classes beside `_Diurnal`, new models,
DM helper, runner) and `tests/test_hourlyvol.py`. Result in a dated block plus a `docs/audit/` note
with period, sample size, "historical, simulated, forecast loss only", and the non-goal sentence above.

## Non-goals
- **No change to the running engine, headless agent, `sonar/model.py` or shipped `forecast()`.** The
  30-day clean agent run (2026-10-10 to 2026-11-09) must not be disturbed. Wiring a winner live is a
  separate later spec, not before 2026-11-09, with Architect gate, `model-validator`, domain review.
- No UI, copy, new dependency (stdlib plus PySide6), new data source, other symbols, daily horizon,
  tuning of lambda, clamps or windows. No claim of edge, profit or certainty.

## Data and environment
Binance is blocked in the cloud sandbox: tests run offline on synthetic data; the real run happens on
the owner's Mac. Until then there is no real-data result. `fetch_hourly` errors on a failed page only; it
does not check contiguity, so the study adds the 3600 s assertion. One venue, UTC bar boundaries.

## Risks
Low power (~104 weekends; a small real effect may miss 1.0%; DROP means "not detected here");
V2 noise (~26 observations per fat-tailed cell); UTC weekend may not match activity shifts (another
boundary is exploratory only); single regime path; sample already seen; HAC/DM validity for nested
rolling-window forecasts and heavy-tailed single-hour loss is unverified.

## Open questions for the owner
1. Approve family of 3 / alpha 0.0167, the 1.0% threshold, W >= 5, lag 168, the windows and UTC weekend (this approval is the freeze).
2. Is 5 of 6 blocks (a weak test: 11% by chance) acceptable, or require 6 of 6?
3. Request a statistician's review of lag 168 and DM validity before the run?
4. Should the real run wait until after 2026-11-09? (Network pull and CPU on the agent's Mac; low risk.)
