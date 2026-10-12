# QA round 5: QA-11 / QA-13 loop 4 (uncommitted), qa-engineer, 2026-10-12

- Saved by the orchestrator (QA is read-only).

**Verdict: PASS on every loop-4 check. No P0 or P1 against the loop-4 scope.** One new P2 model-risk finding needs an owner decision: the attribution and "ranks backwards" significance tests are not date-clustered. Release still waits on Document.

**Playbook:** `docs/playbooks/qa-engineer.md` is `status: baseline` (last-reviewed 2026-10-10), so it is unverified and has no practices yet.

**Read-only.** I edited nothing in the repo. All mutants ran in my own copy, `scratchpad/qa5/repo`, and the harness confirmed with `cmp` after every run that the edited files match the repo again. My QA-11/QA-13 files in `sonar/`, `ui/` and `tests/` are byte-identical to my start snapshot.

**Another session is editing the same worktree.** The book-broker-truth work changed `sonar/alpaca.py` at 04:34, added `tests/test_broker_docs_truth.py` at 04:33, and is editing CHANGELOG, TODO, `static/docs.html`, README, TESTING and TESTPLAN. This happened after my four suite runs (04:09–04:20).

## 1. Suites, twice each: PASS
| run | exit | result |
|---|---|---|
| native 1 | 0 | 1871 passed, 30 deselected, 47.0 s |
| offscreen 1 | 0 | 1871 passed, 46.2 s |
| native 2 | 0 | 1871 passed, 52.3 s |
| offscreen 2 | 0 | 1871 passed, 87.5 s (machine busy) |

- Each run prints 3 teardown tracebacks after the last test: `RuntimeError: libshiboken: Internal C++ object (MainWindow) already deleted` from `_confirm_hidden`. They are in older code, outside this change.
- A later coverage run, after the other session's edits, gave 1 failed, 1906 passed. The failure is `test_testplan_page.py::test_the_documented_suite_size_is_the_collected_one` ("collected 1,908 … documents say 1907"). That is the other session's unfinished count update, not QA-11/QA-13. **Re-run both suites before any commit.**

## 2. Clustered-coin acceptance test: PASS
- 5 runs of `tests/test_backtest.py::test_a_correlated_coin_rarely_gets_a_verdict`: all exit 0, call time 2.55 / 3.10 / 2.53 / 2.67 / 2.56 s (wall 3.0–3.5 s), under load averages of 48–114.
- Removing the DK floor makes it fail: `AssertionError: 9 of 60 runs gave a verdict on a coin / assert 9 <= 7`. Mutants D1 and D5 are also caught by this test, D10 and D11 by it and others.
- The test's own 60 runs: 5 false verdicts and z² 1.351 with the floor; 9 and 2.322 without it.
- **Test quality:** it is seeded and has no time or network dependence, so it is not flaky. But the bound only clears the method on the chosen seed set. On worlds 5–9 the floored method scores 7 false verdicts with z² 1.562 (over the 1.5 bound); on 10–14, 4 and 1.225; on 15–19, 7 and 1.525 (over). So it guards against regressions; it does not show the ≤5% target is met (see P2-2).

## 3. Loop-4 behaviour: PASS
- **Headline se uses the DK floor.**
  - My own brute-force double-sum DK matches `_dk_se` to 2.4e-15 relative on 40 random clustered samples, including calendar gaps, rows without an entry time, and L from 0 to 9.
  - On days whose 40 setups win or lose together: `std_error == se_dk` = 0.0688, against a binomial bar of 0.0100.
  - On independent rows the binomial bar is the wider one (0.0247 vs 0.0240).
  - `se_dk` and `dk_lag_days` are present in every summary with n > 0.
  - Lag rule: 1→2, 3→5, 5→8, 20→29, 60→87 days.
- **Attention buckets.**
  - Each bucket's bar is max(binomial, DK), and buckets are compared with the run's Δ: on a run 15 points above the prediction everywhere, `vs_run` sits between −1.6 and +1.1 points and nothing is significant.
  - BH at `ATTENTION_FDR_Q = 0.05`. The spike bucket at z 2.25 or 2.40 (p 0.0163 > 0.0125) is refused; at 2.55, 2.70, 2.85 and 3.00 it is kept.
  - The withheld gate holds for all four reasons (horizon, single_class, too_few, span): no bucket is significant and the news verdict reads "No reading on attention either".
- **Blend "ranks backwards" sentence.**
  - Strong case (t −9.26): shown.
  - Same data, withheld: not shown.
  - Noise case (t −2.56): not shown.
  - Across 200 noise seeds the flag is always exactly (IC < 0 and t ≤ −3.0).
  - In the UI it needs both `blend_ranks_backwards` and a run that is not withheld.
- **Old summaries.** `_lab_html` renders without error for a current summary, an r4-era one (no `se_dk`, `dk_lag_days`, `vs_run`, `p`, `blend_ranks_backwards` or `blend_ic_t`), and a minimal pre-QA-13 one. The sentence never appears on the old ones.
- **Changed-line branch coverage (loop 3 to loop 4):**
  - `sonar/backtest.py`: 57/57 statements, 12/12 branches.
  - `ui/app.py`: 2/2 statements.
  - Total coverage 84%, over the 80% bar.

## 4. Live Yahoo, fetched 2026-10-12 (129/129 instruments on both 2y and 5y; last bar 2026-10-12)
**Lab default (2y, h=5, step 3, whole watchlist). These are the figures for the docs:**
- n **18,973** compared setups across 129 instruments (Equity 50, Crypto 21, Forex 20, Index 20, Commodity 18).
- Realised hit rate **39.55%**; predicted **39.44%** (40% with unlimited time); Δ **+0.11 pt**.
- **se 0.88 pt** (it was 0.42 without the floor); **se_dk 0.88**; **dk_lag_days 11** (not 5: the real average hold is about 7 bars). z +0.12.
- Verdict: "Realised hit rate is within 1.8 points of the barrier model's prediction — no edge detected."
- 2,574 timed out (11.95%; 84 at data end); 373 too near the end of the data.
- Expectancy beyond a no-edge market +0.0027 R; raw −0.0112 R; implied drift +0.0018σ.
- 572 entry dates, 2024-11-11 to 2026-09-29.
- Attribution: momentum WEAK, volatility DROP; blend IC −0.0165, t −1.58, so no "backwards" sentence.

**Terminal profiles (whole watchlist):**
| profile | n | hit / pred | Δ | se (before floor) | z (before) | verdict |
|---|---|---|---|---|---|---|
| h=1, 2y | 18,658 | 38.46 / 39.45 | −0.99 | 0.70 (0.36) | −1.41 (−2.75) | within 1.4: no edge (was "below … worse than a coin flip") |
| h=5, 2y | 18,973 | 39.55 / 39.44 | +0.11 | 0.88 (0.42) | +0.12 | within 1.8: no edge |
| h=20, 2y | 17,912 | 40.25 / 39.39 | +0.86 | 1.52 (0.70) | +0.57 (+1.23) | within 3.0: no edge |
| h=60, 2y | 13,655 | 42.23 / 39.18 | +3.05 | 4.65 (1.33) | +0.66 (+2.29) | within 9.3: no edge (was "beats by 3.0"); span 549 d = 6.32 horizons |
| h=250, 5y | 22,412 | 45.22 / 38.72 | +6.50 | 6.08 (1.95) | +1.07 | withheld: horizon |

## 5. Mutation: 31 mutants, 28 killed, 3 survived
- **Killed:**
  - DK: D1 floor removed; D2 floor instead of ceil; D3 no 365/252; D4 Bartlett 1−l/L; D5 cross terms not doubled; D6 residual not centred; D7 last lag dropped; D8 undated rows dropped; D9 calendar gaps closed; D10 cluster by hour; D11 lag 0; D12 `se_dk` reports the headline se; D13 `dk_lag_days` off by one.
  - Attention: A1 compared with the prediction; A2 run gap over attention rows only; A3 q = 0.10; A4 BH dropped; A5 bucket bar binomial only; A6 bucket lag 0; A7 withheld gate dropped; A8 sentence quotes `delta`; A11 BH thresholds loosened.
  - Blend: K1 t test dropped; K2 t at 2; K3 withheld gate dropped.
  - UI: U1 keyed to the sign; U2 withheld check dropped; U3 KeyError on an old summary.
- **Survived (full suite):**
  - A9: the bucket bar loses its binomial floor (DK only).
  - A10: BH threshold q·rank/(n+1).
  - A12: BH changed from step-up to step-down.

  All three make the test stricter or change nothing on the fixtures; the loosening mutant, A11, is killed.

## Defects
- **P0/P1:** none in the loop-4 scope.
- **P2-1 (model risk, new): attribution significance is not date-clustered.** Component verdicts and the blend's "ranks backwards" use `_ic_t`, a Newey–West t in trial order, which misses the same-day clustering across instruments that P1-D fixed for the headline. The same check date-clustered (DK, same lag) roughly halves the t:

  | horizon | what shows now | NW t | date-clustered t |
  |---|---|---|---|
  | 2y h=1 | blend: "ranking the wrong way round" (fires on the Lab at h=1) | −3.72 | −1.93 |
  | 2y h=1 | momentum INVERTED | −2.96 | −1.61 |
  | 2y h=1 | volatility INVERTED | −4.25 | −2.29 |
  | Lab default h=5 | volatility DROP | −2.01 | −1.22 |
  | 2y h=20 | volatility INVERTED | −2.89 | −1.46 |

  Code-review r4 P2-1 is met as written, and this is no worse than HEAD (which printed the sentence on any negative blend). But the "significant" test is the one this loop showed to be anti-conservative. Owner call: extend DK to `_ic_t`, or record it as a follow-up for the model-validator.
- **P2-2 (known, open):** the false-verdict rate with the floor is 7.5% on synthetic data and 9.7% on real bars, against a ≤5% target. The acceptance bound is fitted to one seed set (see §2). The docs must not claim 5%.
- **P2-3:** Document has not landed (D4 ships QA-11 and QA-13 together). Another session is editing the docs now; the figures in §4 are ready.
- **P3:**
  - Mutants A9/A10/A12 are untested. A fixture with mixed same-day outcomes in one bucket would kill A9; the BH step-up/step-down difference is untested in `stats.py`.
  - The Lab attention table's "vs baseline" column shows `delta` while significance is judged against the run (`ui/app.py:2774-2779`).
  - At h=60 the band is ±9.3 points, yet the copy says "This is what no edge is supposed to look like". At that width a sizeable edge would read the same; the copy could say the bar is wide.
  - The bucket bar treats the run gap as fixed. This is conservative (about 1/√0.75 with four equal buckets, so code z 2.40 ≈ 2.77 on the true difference); for information only.
  - Older teardown tracebacks in every run (see §1).
  - The verdict copy still says "more than two standard errors". That stays accurate, because se is the widest of the bars.

## Release recommendation
The loop-4 code is release-ready against its spec, with no P0/P1. Before release:
1. Land Document (P2-3).
2. Get the owner's decision on P2-1, at least recorded; preferably the same DK bar on the attribution and blend tests.
3. Re-run both suites twice once the concurrent book-broker-truth edits settle (its doc-count test is currently red).

## Files
Everything is under `/private/tmp/claude-501/-Users-as-Documents-lab-active-sonar/a26ec703-42e8-43e7-ab51-f430c0bd1c34/scratchpad/qa5/`:
- Suite logs: `native1.log`, `native2.log`, `offscreen1.log`, `offscreen2.log`, `cov_run.log`
- Coverage: `cov.json`
- Mutation results: `mutants.txt`, `mutants2.txt`
- Scripts in `scripts/`: `mutate.py`, `behave.py`, `coin.py`, `live.py`, `blenddk.py`, `oldsum.py`, `chcov.py`, `fetch.py`, `refill.py`
- Bars: `live/bars_2y.pkl`, `live/bars_5y.pkl`
- Lab summary: `live/lab_summary.pkl`

Code checked:
- `/Users/as/Documents/lab/active/sonar/sonar/backtest.py` (`_dk_lag_days` :456, `_dk_se` :463, summarise :531, `_attention_buckets` :845, `attribute`/`_ic_t`)
- `/Users/as/Documents/lab/active/sonar/ui/app.py` (:2862-2871)
- `/Users/as/Documents/lab/active/sonar/tests/test_backtest.py` (:1005-1395)
- `/Users/as/Documents/lab/active/sonar/tests/test_lab_tab.py` (:383)
