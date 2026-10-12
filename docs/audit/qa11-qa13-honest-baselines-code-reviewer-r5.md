# Code review, round 5: QA-11 / QA-13 honest baselines, loop 4 (uncommitted)

- Reviewer: `code-reviewer`, read-only, 2026-10-12. Saved by the orchestrator. Probes are in the session scratchpad only: `/private/tmp/claude-501/-Users-as-Documents-lab-active-sonar/a26ec703-42e8-43e7-ab51-f430c0bd1c34/scratchpad/cr5/` (`probe1.py` to `probe4.py`, using QA's cached bars `../live/bars_{2y,5y}.pkl`).
- The playbook `docs/playbooks/code-reviewer.md` is `status: baseline` (last-reviewed 2026-10-10), so it counts as stale under AGENTS.md.

**Verdict: the loop-4 code does what the owner decided. No P0 and no P1.**
- The Driscoll–Kraay estimator is correct.
- BH is correct, and ties are handled.
- The withheld gate and the blend-IC guard are correct.
- The acceptance test is deterministic and tests what it claims.

One new P2 is structural: attention buckets are compared against the gap of the whole run, but only 25 of 129 symbols can carry attention. Two items stay open from the engineer's own list: the "two standard errors" copy (P2) and the docs (P2, carried). Release stays blocked by Document.

## Evidence
- Targeted suites offscreen (`test_backtest`, `test_lab_tab`, `test_scoring`, `test_engine`, `test_follow`): 269 passed in 17.4 s. `test_backtest.py`: 58 passed in 5.0 s. The acceptance test takes 2.24 s.
- `py_compile` passes. ruff and pyflakes are not installed, so static checks are not verified.
- `_dk_se` (`sonar/backtest.py:463-498`) checked against the textbook DK estimator:
  - **Centring:** on the run's mean gap, as the spec requires.
  - **Clustering:** by UTC day, `int(t // 86400)`, which matches `summarise`'s `utcfromtimestamp(...).date()`.
  - **Day grid:** dense calendar-day grid with empty days as 0, and Bartlett weights `1 − l/(L+1)`.
  - **Scaling:** to the se of the mean, `sqrt(var)/n`.
  - **Undated trials:** each adds `r²` with no cross terms, so it is its own cluster. With all trials undated the result equals the plain centred se exactly (0.04899 = 0.04899).
  - **Lag beyond the grid:** it is truncated at `len(x)−1`, and the omitted terms are zero anyway.
  - **Non-negative variance:** Bartlett on the full grid is PSD, so the `max(var, 0)` guard only absorbs float noise. With one day the result is 1e-16, and the binomial or Newey–West bar takes over.
  - **Cost:** about 157k trials over 10 years took 43 / 68 / 91 ms at L = 5 / 250 / 500.
- `_dk_lag_days` has a float issue: `ceil(k·252/365 · 365/252)` returns k+1 for 37 of 399 exact multiples. This is harmless (one extra lag day widens the bar slightly), and a mean of integer holds almost never lands exactly there. Discarded.
- The acceptance test's forced side takes effect: within a pair the directions are {LONG}/{SHORT}, and outcomes differ in 131 of 158 rows. It seeds `random.Random`/`crc32` with no clock, so it is deterministic.
- `_ic_t` extraction keeps component p-values byte-identical: the same expression, now with `strict=True` on equal-length lists.
- The UI guard `ui/app.py:2867` (`blend_ranks_backwards and not withheld`) is correct. Older dicts without the key render the number only.

## Findings

**P2-1 — attention buckets read against the whole run's gap, while only the covered symbols carry attention** (`sonar/backtest.py:869-870`, `885`; pinned by `tests/test_backtest.py:1243-1268`, whose docstring calls "the run's gap taken over the attention rows only" a mutant).
- **Coverage:** in production `run()` passes no `articles`, so only `WIKI_ARTICLE` symbols get attention: 25 of 129 (10 Crypto, 7 Equity, 3 Index, 3 Forex, 2 Commodity). Rows before 30 days of pageview history also have none.
- **The bias:** any gap difference between that crypto-heavy subset and the run is added to every bucket's `vs_run`. That is the same common-offset failure mode P1-E was meant to remove.
- **Synthetic repro** (`probe1.py`): 25 covered symbols at +3 pt, 104 uncovered at 0, attention pure noise, independent trials. Result: three buckets "significant" after BH, and the verdict reads "Some attention levels shift the odds: below normal +2.5 … normal +3.2 … elevated +3.3 pts against the run as a whole".
- **Real bars** (`probe4.py`, noise attention on the 25 covered symbols only):
  - covered-minus-run offset: 2y h=60 −4.3 pt; 5y h=20 +1.9 pt; 2y h=20 +1.6 pt;
  - false firing: 2y 0/40, 0/40, 0/40, 2/40 at h=5/20/40/60; 5y 0, 2, 0, 0 of 40 at h=5/20/60/90.
  - So the wide DK bars mostly absorb it today, but the bias is systematic and grows as samples grow.
- The engineer's "0/24 judged runs" figure appears to put attention on every trial, so it would not see this.
- **Fix:** take `run_gap` over `rows` (the setups that have attention), or compare each bucket against the other buckets. This equals "the run's own Δ" when coverage is full. It needs a one-line owner or validator confirmation of the reading, plus a change to the pinning test.

**P2-2 — verdict copy still says "more than two standard errors" / "beyond two standard errors"** (`sonar/backtest.py:752-759`; also the Lab line `ui/app.py:2748` "±… at 2 s.e.").
- The figure is literally true for the floored se. But a reader takes "two standard errors" to mean about 95%, and the measured false-verdict rate on an uninformative clustered coin is:
  - 7.5% [5.8–9.7] on synthetic runs;
  - 9.7% [7.1–13.2] on real bars (10.9% of judged runs);
  - against about 4.6% if the bar were right.
- The test's own bound accepts up to 11.7%. The validator (r4 P1-D) asked to "keep the verdict copy off 'two standard errors' until then".
- **Fix (owner/UX wording):** e.g. "more than twice its error bar (±x, setups entered on the same day counted together)", plus a placebo caveat ("a direction with nothing in it gets this about one run in ten"), until the sign-randomisation test lands.

**P2-3 — docs not updated (carried from r4 P2-2 and r3 P2-3; blocks release under D4):**
- `CONFIDENCE.md:587` still says "39.58% against a 39.99% prediction".
- `TODO.md:251` still says "leave-one-out — one whale …".
- None of CONFIDENCE.md, the ADR, `static/docs.html`, README or TODO mentions the date-clustered bar, `se_dk`, BH for attention, or `vs_run`.

**P3-1 — the Lab attention table's "vs baseline" column shows `delta` while significance and the sentence use `vs_run`** (`ui/app.py:2767-2781`).
- If every setup beats the prediction by 3 points, every row reads "+3.0 vs baseline" directly above "Attention makes no difference".
- **Fix:** for attention buckets, show `vs_run` under "vs the run as a whole", or both columns. Momentum buckets keep "vs baseline".

**P3-2 — the acceptance test does not encode the owner's target or cover the long horizons where DK is weakest** (`tests/test_backtest.py:1191-1217`).
- It checks only h=5 and h=20 over a 2y world, with a bound of 7/60 (11.7%) and mean z² ≤ 1.5. The validator's target was ≤ 5%, and DK's documented downward bias is at h=60–120, where there are few lag blocks.
- It cannot pass for the wrong reason: the sides are forced, `se_dk > 1.2×` binomial is asserted, and the no-floor mutant reads 9/60. But it is a regression guard, not acceptance.
- **Fix:** say so in the docstring and TESTPLAN, and add one h=60 world (the cost is roughly the same) or a slow-marked sweep.

**P3-3 — small-cluster DK uses normal p-values** (`sonar/backtest.py:880-886`).
- Buckets have no date floor (only n ≥ 30), and the headline has none beyond 20 dates. DK with few effective clusters is biased low, and the binomial floor ignores within-day correlation.
- `probe3b.py`: noise attention with day-level outcome correlation 0.5 or 0.8 gives any bucket significant in 7.1% and 7.8% of runs, against ≤ 5% under the global null (2.0% at correlation 0).
- **Fix (validator's call):** a minimum distinct-date count per bucket (e.g. `MIN_VERDICT_DATES`), or t(G−1) critical values.

**P3-4 — "ranks backwards" uses a Newey–West t that ignores the cross-section** (`sonar/backtest.py:1045-1046`, `_ic_t` `:1070-1077`).
- The NW default lag is about 13 over a symbol-then-time ordered list, so same-day co-movement across instruments, the P1-D design effect of 1.5–3.5×, is not in the t. Momentum-heavy blends could still clear −3 on judged real runs from correlated noise.
- This matches the owner's decision ("significant", using the components' test) and the component INVERTED verdicts (validator P2-F, narrowed). Recorded so it is not mistaken for clustered.
- **Fix with P2-F later:** a DK t on the centred products.

**P3-5 — Lab colour is computed from rounded fields** (`ui/app.py:2712`: `within = abs(delta) <= 2*se` on 4-dp values).
- `summarise` decides on unrounded values, so at the boundary the colour can disagree with `significant`. Pre-existing; this loop makes the boundary sit on DK.
- **Fix:** `within = not r.get("significant") and not withheld`.

## Status of r4 findings
| r4 | Status |
|---|---|
| P2-1 blend "ranks backwards" on withheld/noise | **Resolved**: `backtest.py:1040-1050`, `ui/app.py:2862-2871`. Tests `test_backtest.py:1367-1396` (strong / withheld / noise t −2.56) and `test_lab_tab.py:383`. Residual P3-4. |
| P2-2 docs | Unresolved (P2-3) |
| P3-1 "Horizons up to 120 days get one" | Unresolved (`backtest.py:731`) |
| P3-2 single-class gate ignores `compared_by_class` | Unresolved (`backtest.py:622`) |
| P3-3 universe defaults fail open | Unresolved (`backtest.py` `run(... universe=WHOLE_WATCHLIST)`, `ui/worker.py:62` `"all"`) |
| P3-4 momentum top edge `(0.10, 1.0)` | Unresolved (`backtest.py:1216`) |
| P3-5 follow docstrings / redundant −1 bump | Unresolved (`core.py:1088`) |
| P3-6 left-out items | Unresolved (owner left out) |
| MV P1-D DK floor | Implemented as decided; residual false rate about 2× nominal (P2-2, P3-2, P3-3) |
| MV P1-E attention DK + vs run + BH | Implemented as worded; composition bias (P2-1) |

## Recommendation
The code is correct for what was decided. Before release:
1. Owner/validator decide P2-1 (the gap over the attention rows): a one-line change plus the test.
2. Owner/UX decide the verdict wording (P2-2).
3. Document (P2-3).

P3-1 (the attention table column) is cheap enough to take with (2).
