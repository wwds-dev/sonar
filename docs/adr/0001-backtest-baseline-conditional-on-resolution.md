# 0001. The backtest's `predicted` is conditional on resolving within the hold window

- Status: accepted (owner, 2026-10-11)
- Date: 2026-10-11

## Context

`backtest.run_symbol` drops trials that touch neither barrier within `4 × horizon` bars
(TIMEOUT), and it then compares the resolved hit rate with `plan.p_profit = k_s/(k_t+k_s)`. That
figure is the probability with no time limit. The dropped trials are mostly ones that a far
target had not yet reached. As a result, a market with nothing in it reads below its own
baseline, and the gap grows with the ratio. On driftless walks at h = 5 (40 × 1,500 bars) the
resolved rate reads:

| ratio | resolved | baseline | gap | |
|---|---|---|---|---|
| 1.5:1 | 39.35% | 40% | −0.65 pt | 1.3 se |
| 2:1 | 30.6% | 33.3% | −2.7 pt | 5.1 se |
| 3:1 | 16.3% | 25% | −8.7 pt | 17.8 se |

The Lab's verdict, its momentum and attention buckets, and CONFIDENCE.md's "39.58% vs 39.99%" all
inherit that baseline. The model-validator's P1-3 bias (−0.3 to −0.9 pt, "always ≤ 0") turns out
to be mostly this effect, not the tie-as-STOP rule.

## Decision

Each resolved trial's `predicted` becomes
**P(target first | the trial resolves within its own window)** for a driftless Brownian motion.
This uses units in which the barriers sit at +k_t and −k_s and the window lasts T = W/h
horizons. W is the bars actually available, so a trial cut short by the end of the data gets
its true, shorter T — but only if W covers at least 2 horizons (`MIN_WINDOW_HORIZONS`). A setup
with less data after it is not compared at all; it is counted (`n_short_window`) and shown as "too
near the end of the data" *(amended 2026-10-12; see Amendments)*.

The probability is computed from the closed-form image series for two-sided first passage. It
lives in `scoring.barrier_probabilities_within` / `resolved_hit_probability`, is cached by
`(k_t, k_s, W, h)`, and needs at most about 6 terms at 1e−15. It agrees with the eigenfunction
series to 2.5e−11.

The rest of the output follows from that:
- Timeouts stay out of n. They are counted (`n_timeout`, `n_timeout_data_end`) and shown.
  `timeout_share_expected`, the share a driftless walk would leave, is an output field only: it is
  not shown on screen and it is not a diagnostic *(amended 2026-10-12)*.
- `baseline_untimed` keeps 1/(1+R:R) on screen.
- `implied_edge_sigma` inverts the same time-aware probability.
- `expectancy_r` uses each trial's own rr, and `expectancy_vs_null_r` is 0 in expectation with
  no edge.

The P(profit) shown on rows is **not** affected; it stays 1/(1+R:R), as T1-1 decided.

## Alternatives considered

- **Count timeouts as losses.** This makes the bias worse unless the baseline also changes to
  "target first within the window". It mixes two questions in one rate.
- **A three-way split** (target / stop / timeout) against predicted shares. This is honest, but
  it changes the metric, the verdict and every bucket. It is more surface than the defect
  needs.
- **Mark timeouts to market at the window end.** That changes the measure from hit rate to
  expectancy, which is a different study.
- **A Monte-Carlo baseline per run.** It could also absorb the daily-bar and tie bias, but it is
  slow and seed-dependent, and the measured residual (about ±0.6 pt at h = 5) is below the
  test's error bar.
- **The eigenfunction series.** It is equally exact in theory, but it cancels catastrophically
  at small T and returned negative probabilities at T = 0.004, which a Lab horizon of 250 with a
  1-bar truncated window reaches.
- **Drop every decision point whose full window does not fit in the data.** This is simpler, but
  it changes the realised hit rate and throws away resolved trials.

## Consequences

- `predicted` changes meaning. At the shipped 1.5:1 and the Lab default (2y, h = 5) it moves from
  40.00% to 39.44%, re-measured on live bars to 2026-10-12 (n 18,973, 129 instruments; hit rate
  39.55%, Δ +0.11 pt, error bar ±1.8; `docs/audit/qa11-qa13-honest-baselines-qa-engineer-r6.md`
  §4). The realised hit rate is unchanged.
- **Restated (2026-10-12):** CONFIDENCE.md "What the backtest found"; TESTPLAN 7.5; the Learn tab
  (`static/docs.html` §8); the `tests/test_backtest.py` identity test, now a four-ratio driftless
  test against the time-aware baseline.
- **Nothing to migrate.** No persisted file stores `predicted` (`research_results/*.json`
  checked), and summaries are transient.
- **Easier:** an R:R control in the Lab no longer reads a no-edge market as "actively harmful".
  The bucket and attribution comparisons inherit an honest baseline.
- **Harder:**
  - "Predicted" now needs a qualifier on screen ("for setups that resolved in time");
  - the baseline depends on the driftless-BM model of σ̂-scaled barriers, so fat tails or a
    biased σ̂ move it. The check on that is the coin-flip (direction) placebo run on real bars, not
    `timeout_share` against `timeout_share_expected`: real prices time out about twice as often as
    the driftless share (11.95% against 5.31% on the Lab default) while the baseline holds there,
    so the gap does not diagnose anything *(amended 2026-10-12)*.
- **Residual, stated rather than modelled:** the daily-bar and tie-as-STOP bias, the gap
  between lognormal and arithmetic barriers, and σ̂ noise. Together they come to about ±0.6 pt at
  h = 5, and possibly −1 to −2 pt at h = 20, which cannot be separated from overlap noise at the
  tested sample.
- **Reversal:** go back to `plan.p_profit` in `run_symbol`. It is cheap in code, but published
  figures would have to be restated again.

## Amendments

**2026-10-12** (owner decisions recorded in `docs/specs/qa11-qa13-honest-baselines.md`, Review and
Verify rounds 1–6). The decision above stands; what is compared, and when a run is judged, changed:
- **Window floor (P1-1).** Only setups with at least 2 horizons of data after entry are compared.
  Over a shorter window the driftless baseline's thin tail calls a far target nearly unreachable,
  and real prices reach it far more often: a coin-flip direction at h = 250 on 2y read +5.7 pt, z
  +4.1. Shorter-window setups are counted (`n_short_window`), never compared.
- **When a run gets a verdict (P1-A, P1-B, P1-C).** No verdict above a 120-day horizon
  (`MAX_VERDICT_HORIZON`); none on a single asset class, only on the whole watchlist
  (`WHOLE_WATCHLIST`); none under 100 compared setups (`MIN_VERDICT_TRIALS`) or 20 distinct entry
  dates (`MIN_VERDICT_DATES`); none unless the entries span at least 5 horizons
  (`MIN_VERDICT_SPAN_HORIZONS`, read at 365/252 calendar days per trading day). The numbers are
  always returned and shown with the reason (`withheld`). A run without a verdict makes no
  attention finding and grades no component.
- **Error bar floor (P1-D).** The headline se is the widest of the binomial (never below the
  Agresti–Coull se), Newey–West, and a Driscoll–Kraay se clustered by UTC entry date across
  instruments with a Bartlett kernel over L = ceil(average hold × 365/252) calendar days. The same
  date-clustered bar now sets the attention buckets (each read against the gap of the setups that
  carry attention, Benjamini–Hochberg across the buckets) and attribution (component IC,
  quintile spread, blend t). It is not a calibrated 5% test: a direction picked at random per class
  and block still got a verdict on 11.4% of judged real-bar runs. The ≤ 5% target is open and needs a
  sign-randomisation test.
- **`timeout_share_expected` is an output field, not a monitor.** It is not on screen and is not
  diagnostic (validator round 1, P2-3: 12.9% realised against 6.1% expected with the baseline fine
  there; at 3:1, where the baseline is off, the gap was small). The coin-flip/direction placebo is
  the real check on the baseline.
