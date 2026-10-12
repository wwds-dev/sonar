# Loop 5 build report (engineer), 2026-10-12. Not yet reviewed.

- Scope: the owner's loop-5 decisions in `docs/specs/qa11-qa13-honest-baselines.md`, items 1–4.
- Nothing was committed or staged.
- `docs/playbooks/engineer.md` is `status: baseline` (last-reviewed 2026-10-10), so it counts as stale.
- Scripts and logs are in the session scratchpad under `eng5/` (`placebo_syn*.py`, `placebo_real.py`, `power.py`, `h1.py`, `mut/`, `*.log`).

## Changes
1. **Attribution uses the date-clustered error bar** (`sonar/backtest.py`):
   - New helpers: `_dk_var` :492 (the Driscoll–Kraay variance of summed residuals) and `_dk_mean_se` :481. `_dk_se` :463 is now a thin wrapper over them, with the same arithmetic and order of operations.
   - `_dk_lag_of` :518 applies `_dk_lag_days` to the trials' own average hold.
   - `_ic_t` :1127: t = mean centred product / max(Newey–West se, DK se). Callers are the components at :1070 and the blend at :1082.
   - `_quintile_spread` (~:996–1005): se = max(binomial, DK on each setup's share of top − bottom). It also reports `se_dk`.
   - `_blend_series` now also returns the setups it used (:1173).
   - Benjamini–Hochberg, `IC_KEEP`, the 2-se spread rule and `Z_CLAIM` are unchanged.
2. **Verdict copy** (`sonar/backtest.py` `_verdict` :770–795):
   - "beats" and "below" now use the validator r5 strings exactly. The bar is shown as "(±{2se})" in points.
   - "within" is unchanged.
   - The module docstring (:31–37) and `_withheld_verdict` :761 now say "can read above". The docstring no longer says a "below" result is worse than a coin flip.
   - The Lab difference line (`ui/app.py:2754`) now reads "(error bar ±x; setups entered on the same day counted together)".
   - The Terminal (`ui/app.py` `_backtest_done`) prints `r["verdict"]` and "(± x)", so it is already consistent.
   - The grep of `sonar/` and `ui/` found no other backtest "two standard errors" or "coin flip" verdict text. `engine.py:640` belongs to the model-vs-market calibration verdict, which is outside this scope.
3. **Attention buckets** are now compared with the gap of the setups that carry attention (`run_gap` over `rows`, :908). The docstring is updated.
4. **Small fixes:**
   - Null attention copy (:950): "No attention level stood apart from the run as a whole (the setups with an attention reading), … no effect of a news spike was detected, which is not the same as none."
   - The "shifts the odds" tail now says the run is the setups with an attention reading.
   - The Lab attention table shows `vs_run` under "vs the run as a whole" (`ui/app.py:2776–2784`). Momentum buckets, and older attention buckets without `vs_run`, keep "vs baseline" / `delta`.
   - The Lab colour now comes from `significant`/`withheld` (`ui/app.py:2715`). A summary without the flag falls back to the rounded figures.

## Tests (+8; 1,908 → 1,916)
New tests:
- `tests/test_backtest.py`:
  - :1255, the placebo acceptance test, 4.9 s. Worlds 0–3, 20 instruments a class, h = 20, 6 placebos per world, 24 runs. It requires: at most 3/24 graded KEEP or INVERTED, mean spread z² ≤ 2.2, mean IC z² ≤ 2.0, and a real per-setup component (IC ≈ 0.08) reading KEEP.
  - :1320, the IC t is clustered by date.
  - :1357, the spread is clustered, and a common move on the same day cancels in the difference.
  - :1448, the reviewer's partial-coverage case. With the whole-run reference, Benjamini–Hochberg flags 2–4 buckets on each of 20 seeds; with the attention-row reference it flags none.
  - :647, the exact verdict strings.
- `tests/test_lab_tab.py`: the difference line :582, the colour :592, the attention column :610.

Tests changed to the new spec. None of these is a weakening:
- `test_summary_flags_a_harmful_signal` now checks for "does not show the lean is worse than a coin flip" and that "did worse" is absent.
- `test_no_backtest_verdict_promises_anything` now allows the denial "not a guarantee" (as it already allowed "no edge detected") and newly bans "standard error".
- The attention test's docstring and its run-gap reference are flipped. The reviewer's mutant is now the old behaviour.
- The two `startswith("Attention makes no difference")` checks now match the new null copy.
- The blend-t pin now uses max(Newey–West, DK).

## Numbers
- Placebo graded KEEP or INVERTED: one value per (class, ~h-day block) plus 20% per-setup noise.

| | Before | After |
|---|---|---|
| Real cached bars (validator r5 `bars_*`; 2y h5/20, 5y h20/60, 10y h5/60; 120 runs) | 24.2% [17.4–32.6] | **5.0% [2.3–10.5]** |
| Synthetic, 20/class, h=20, 360 runs | 14.7% [11.4–18.8] | 5.6% [3.6–8.4] |
| Synthetic, 20/class, h=5 and 20, 400 runs | 11.2% | 4.5% |
| Synthetic, 6/class, h=5 and 20, 1,200 runs | 4.8% | 3.2% |

- **Bound justification:** the 6-per-class world barely shows the problem, so the test uses 20 per class.
  - Over 15 disjoint sets of 24, the floored spread z² ranged 0.88–1.89 and the unfloored 2.66–5.71. Graded counts were 0–4 floored and 0–7 unfloored.
  - The test's own set reads 2 / 1.61 / 1.57 floored and 6 / 2.59 / 5.55 unfloored.
  - It is a regression guard fitted to its seeds, like the clustered-coin test.
- **Other placebo designs on real bars:** an independent placebo per setup was 0.8% before and after. A per-symbol persistent placebo was 11.7% → 8.3%. A date-clustered bar does not reach persistence within one instrument that outlasts the lag, so that one stays open.
- **Power:** a real per-setup component was kept as often as before. At IC ≈ 0.035 it was kept 28/30 both before and after; at IC ≥ 0.05 it was kept 30/30.
- **Real components on judged real runs (after the change):**
  - Volatility INVERTED went from 4 of 6 runs to 0.
  - 10y h=60 momentum went from KEEP (p 0.0009) to UNCLEAR (p 0.29).
  - 2y h=1 (QA's live bars): blend t −3.72 → −1.93, so "ranks backwards" is no longer shown. Momentum and volatility went from INVERTED/INVERTED to UNCLEAR/DROP.
  - 2y h=5: volatility p 0.045 → 0.22, still DROP.

## Mutation
16 mutants were planted in a scratch copy, and `cmp` confirmed the copy matched the repo after each. All 16 were killed:
- IC DK floor dropped
- spread DK floor dropped
- component lag 0
- blend t undated
- DK mean not centred
- bottom-fifth sign flipped (survived at first; killed after adding the same-day-cancel case)
- `_dk_lag_of` returns 0
- attention gap over every trial
- old null copy
- "more than two standard errors"
- "did worse than a coin flip"
- "reads above"
- "at 2 s.e."
- colour from rounded fields
- attention column on `delta`
- max → min in `_ic_t`

## Suite runs
Run with `./run-tests.sh tests/ -q`; the script returns pytest's exit code.

| Run | Exit | Result |
|---|---|---|
| native 1 | 0 | 1916 passed, 30 deselected, 56.6 s |
| offscreen 1 | 0 | 1916 passed, 50.9 s |
| native 2 | 0 | 1916 passed, 52.6 s |
| offscreen 2 | 0 | 1916 passed, 52.2 s |

- Every run prints the pre-existing teardown traceback `libshiboken … MainWindow already deleted`, as QA r5 found.
- Suite counts: only the number "1,908 tests" was changed to "1,916 tests" in TESTPLAN.md, TESTING.md and README.md. `static/testplan.html` was regenerated with `scripts/build_testplan.py`, and `--check` passes.

## Not verified / open
- `ruff` and `pyflakes` are not installed. `py_compile` passes, and the new lines are ≤ 100 characters.
- Changed-line coverage was not measured. The `se == 0` branch of `_ic_t` is probably not covered.
- **Docs not touched** (owned by the other session or Document):
  - `static/docs.html` (the error-bar paragraph and the attention and attribution wording)
  - CHANGELOG, TODO and CONFIDENCE
  - the ADR
  - the spec's old copy at :200–203
  - the backlog entry
- Still open:
  - the IC z² is 1.52 at h=20, because a block outlasts the one-hold lag
  - the per-symbol persistent placebo is at 8.3%
  - the clustered-coin ≤ 5% target still needs a sign-randomisation test
- The other session modified `sonar/execution.py` and `sonar/portfolio.py` during this loop. I did not touch them.

## Polish (after round 6)
Scope: the spec's "Orchestrator polish after round 6" bullet (`docs/specs/qa11-qa13-honest-baselines.md:10`). The suite count is still 1,916, because the asserts went into existing test functions. No count strings were changed.

**Code**
- `sonar/backtest.py` `_verdict_for`:
  - INVERTED now reads "…this component would push the wrong instruments up the board. Worth testing with its sign flipped, or dropped. From one replay of past prices: a reason to look closer, not a finding."
  - KEEP now reads "IC … survives FDR and {phrase} — from one replay of past prices".
  - No other place in `sonar/` or `ui/` quoted "Flip its sign".
- `sonar/backtest.py` `_attention_buckets` docstring: the 137-character line is rewrapped. No line in the file is over 100 characters.
- `ui/app.py`: the Lab attention column is now headed "vs setups with attention". Momentum keeps "vs baseline".

**Tests**
- `tests/test_backtest.py`:
  - `test_a_run_without_a_verdict_claims_no_attention_or_attribution_finding`: the judged momentum KEEP sentence is pinned exactly. So is the INVERTED sentence, via `_verdict_for` on the same readings with IC and spread negated. A copy guard covers both and includes "flip its sign or drop".
  - `test_the_news_verdict_says_how_the_buckets_were_judged`: the null attention sentence is pinned in full (QA r6 T2).
  - `test_the_ic_test_counts_setups_entered_on_the_same_day_together`: this test now runs `attribute()` on its own fixture, with `bars_held` 5, which gives a lag of 8 days. The component's p must equal `normal_p(_ic_t(…, 8))`. The fixture tells lag 8 (p 0.6588) apart from lag 4 (p 0.6717) (QA r6 E4).
- `tests/test_lab_tab.py`:
  - The column test checks "vs setups with attention", and checks that "as a whole" is absent.
  - The withheld guard now checks for "push the wrong", because "pushes the wrong" would always be absent and the check would be empty.

**Mutation check** (scratch copy at `…/scratchpad/eng5b/repo`; script `mutate.py`; log `mutants.txt`): 7 of 7 killed.
- M1: INVERTED goes back to "Flip its sign or drop it".
- M2: INVERTED loses its hedge.
- M3: KEEP loses its hedge.
- M4: the column heading is reverted.
- M5 (T2): the null copy loses "which is not the same as none".
- M6 (E4): the component IC lag is halved.
- M7: the component IC lag is set to 0.

**Suite runs** (`.venv/bin/python -m pytest -q`, exit codes from `$?`):

| Run | Exit | Result |
|---|---|---|
| native | 0 | 1916 passed, 30 deselected, 50.0 s |
| offscreen 1 | 1 | 1915 passed, 1 failed |
| offscreen 2 | 1 | 1915 passed, 1 failed (same test) |

- The failing test is `tests/test_docs.py::test_it_states_how_much_data_a_number_needs`. It is not caused by this change. The concurrent tech-writer's `static/docs.html` (modified 05:30, between the native and offscreen runs) changed the 20-trial band from ±21.5 to ±21.9 points. The test still looks for "21.5". This file is not one of mine and I did not touch it. The writer or the owner should reconcile the docs and the test. Do not weaken the test.

**Not verified**
- `ruff` is not installed in `.venv` or on PATH, so lint was not run. A line-length check by `awk` passes.
- Docs that describe the old copy were not touched (they belong to the tech-writer): `static/docs.html`, CONFIDENCE and CHANGELOG.
