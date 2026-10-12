# Code review, round 6: QA-11 / QA-13 honest baselines, loop 5 (uncommitted)

- Saved by the orchestrator (reviewer is read-only).

Reviewer: `code-reviewer`, read-only, 2026-10-12. My test files and outputs are in `/private/tmp/claude-501/-Users-as-Documents-lab-active-sonar/a26ec703-42e8-43e7-ab51-f430c0bd1c34/scratchpad/cr6/`. I compared against the loop-4 baseline QA used in r5, `scratchpad/qa5/repo/sonar/backtest.py`. The playbook `docs/playbooks/code-reviewer.md` is still marked `status: baseline` (last-reviewed 2026-10-10), so under AGENTS.md it counts as stale.

**Verdict: no P0 and no P1.** Loop 5 does what the owner decided, and the headline result is unchanged to the bit. The one thing still blocking release is the user-visible docs (P2-1).

## Evidence
- **Suite, offscreen, run once.** Command: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/ -q`. Result: 1916 passed, 30 deselected, in 142.7 s, exit code 0 (saved to `cr6/suite_off_exit.txt`). The machine was heavily loaded (load average 57). The `libshiboken … MainWindow already deleted` teardown traceback appears, as in earlier runs.
- **Targeted tests.** `test_backtest.py` and `test_lab_tab.py`: 98 passed, exit code 0.
- **The `_dk_se` refactor changes no numbers** (`cr6/p1.py`).
  - Across 3,000 random trial sets (5% undated, lags 0–40), the old and new `_dk_se` gave the same result to the bit every time.
  - Across 300 synthetic runs, `summarise` gave the same `std_error`, `delta`, `significant` and `withheld` every time.
  - The reason is that the arithmetic order is preserved: `(w−pred)−gap` with `gap = Σ(w−pred)/n`.
- **The date-clustered (Driscoll–Kraay) bar is applied correctly to attribution.**
  - Component t (`backtest.py:1137-1143`): the centred products are re-centred on their own mean inside `_dk_mean_se`, so the residuals are the right ones for a test of their mean. It uses the same `t//86400` day key as the headline, the lag is `_dk_lag_of(have)`, and it takes the larger of this bar and Newey–West.
  - Quintile spread (`:995-1005`): each setup contributes ±(w − h_side)/n_side, summed per day, so this is the correct influence function for a difference of two means. Without entry times it reduces exactly to the binomial bar.
  - Blend t (`:1081-1082`): `blend[2]` lines up with `xs` and `ys`.
  - **A null test confirms the bars are sized right** (`cr6/p2.py`, 400 runs: 120 day-clusters of 15 setups, outcomes shared within a day, a component unrelated to the outcome). The spread had mean z² 0.99 and rejected 5.2% at 2 se. The IC had mean t² 0.98 and rejected 6.5% at 1.96.
- **Attention.** `run_gap` is now taken over `rows`, the setups that have attention (`:907-908`). The new test `test_backtest.py:1448` would fail on the old behaviour: the whole-run reference gives 3 significant buckets, the new one gives 0.
- **Copy matches the approved strings.**
  - `_verdict` "beats" and "below" (`:775-793`) match the validator r5 strings character for character.
  - The Lab line (`ui/app.py:2754-2755`) matches.
  - The null attention copy matches.
  - "can read above" appears at `:37` and `:761`.
  - Searching `sonar/` and `ui/` finds no user-visible backtest "two standard errors", "2 s.e." or "worse than a coin flip" wording other than the negated form at `:792`. The `engine.py:640` hit is the buyability verdict, which is outside this scope.
- **The copy-guard change in the tests is legitimate** (`test_backtest.py:490-506`). "not a guarantee" is allowed only as that exact phrase and only as a denial, the same way "no edge detected" already was. A bare "guarantee" still fails, and "standard error" is now banned outright. The only gap is cosmetic: "not a guaranteed …" would also be stripped, but that phrase is still a denial. Nothing is weakened.
- **The Lab fixes would catch a regression.**
  - The colour test puts delta exactly on 2·se (0.01 ≤ 0.01), so the old rule (colour worked out from the rounded figures) would show grey where the test expects amber.
  - The attention-column test would catch the column going back to `delta`.
  - Old summaries are handled: without `significant`, the colour falls back to the figures; without `vs_run`, the column shows `delta` under "vs baseline"; the UI does not read the new spread `se_dk` field.
- **Not verified:** `ruff` and `pyflakes` are not installed. I did not run the native mode or a second run.

## Findings

**P2-1: the user-visible docs still say "two standard errors" and describe only Newey–West.** This carries over r5 P2-3 and blocks release under D4.
- `static/docs.html` is rendered in-app by `ui/learn.py`. It still says:
  - `:627-628`: "Error bar — Two standard errors on the difference. **This is the number that decides.**"
  - `:636`: "the two-standard-error band".
  - `:650-657`: the error bar is described as a Newey–West correction only.
  - `:624-625`: "Predicted rate … `1/(1+R:R)` … **40%**", while the Lab shows 39.46%.
- Other files:
  - `CONFIDENCE.md:578` still has a "±2 s.e." column.
  - `CONFIDENCE.md:587` still says "39.58% against a 39.99% prediction".
  - `TODO.md:251` still says "leave-one-out — one whale …".
- Scenario: a user reads the Lab verdict "outside its error bar … about 1 run in 10", then opens Learn and is told the bar is two standard errors and decides. That is the calibrated-95% reading the owner decided to remove.
- Fix: the Document phase applies the validator's r5 `docs.html:623-624` text, the clustering paragraph, the date-clustered bar for attribution and the "run = setups with attention" wording. The other session currently has uncommitted edits in `docs.html` (the Alpaca section), so that work needs coordinating.

**P3-1: the Lab attention column header says "vs the run as a whole", but the figure is against the setups with attention** (`ui/app.py:2783`).
- The momentum table right above it covers every setup, so a reader takes "the run" to mean all setups. The verdict text says otherwise ("the run being the setups with an attention reading"), so the table and the sentence disagree.
- Fix (UX wording): e.g. "vs all setups with attention", or a one-line caption under the table.

**P3-2: the placebo acceptance test is now the slowest test, close enough to the 60 s kill to watch** (`test_backtest.py:1255`).
- It took 17.6 s under load (load average 57); the engineer measured 4.9 s on a quiet machine.
- `pyproject.toml:32-33` sets `faulthandler_timeout = 60` with exit-on-timeout, so the margin is about 3.4× under load.
- Fix: add a `slow` mark, or use 4 placebos per world instead of 6 (the bounds would need to be refitted).

**P3-3: the small-cluster bias (r5 P3-3) now applies to attribution as well** (`backtest.py:995-1005`, `:1141-1143`).
- The quintile fifths and the components have no minimum number of distinct dates, and the p-values are normal ones from a date-clustered bar. The null test above is fine at 120 clusters; the bias appears when there are few clusters.
- This is the validator's call, together with the sign-randomisation test that is still open.

**P3-4: one line is over the 100-character limit** (`backtest.py:894`, 137 characters). It is a docstring line joined in this loop. Ruff's selected rules exclude E501, so CI is not affected; the engineer's report says all new lines are ≤ 100. Fix: rewrap.

## Status of r5 findings
| r5 | Status |
|---|---|
| P2-1 attention against the whole run's gap | **Resolved**: `:907-908`; test `:1448`; pinned test flipped `:1413-1445` |
| P2-2 "two standard errors" verdict copy | **Resolved in code** (`:775-793`, `ui/app.py:2754`); remains in the docs (P2-1 above) |
| P2-3 docs | **Unresolved** (P2-1 above) |
| P3-1 attention table shows `delta` | **Resolved** (`ui/app.py:2777-2792`); header wording is P3-1 above |
| P3-2 clustered-coin test is a regression guard, no h=60 | Recorded in the spec; that test's docstring is unchanged and there is still no h=60 world. Open |
| P3-3 small-cluster normal p | Open, now wider (P3-3 above) |
| P3-4 blend t ignores the cross-section | **Resolved**: the date-clustered bar now applies (`:1081-1082`); test `:1601-1613` |
| P3-5 Lab colour from rounded fields | **Resolved** (`ui/app.py:2712-2716`); test in `test_lab_tab.py` |
| r4 P3-1/2/3/4/5/6 | Unchanged (owner left them out) |

## Recommendation
The loop-5 code is correct and ready for Verify. Release stays blocked until the docs are updated (P2-1). P3-1 is a one-word UX change that can go in with that work. The rest can be deferred.
