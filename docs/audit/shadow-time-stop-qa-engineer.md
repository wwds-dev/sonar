# QA report: time-stop shadow readout (Verify, qa-engineer, 2026-10-12)

Saved by the orchestrator from the qa-engineer's report. Checked at HEAD `cca9428`.

**Verdict:** for what can be checked before release, success measures 1, 3 and 4 are met at `cca9428`,
measure 1 only to the letter. 11 of 36 mutants survived, so test gaps remain.
- **Measure 1 (null size):** the spec's 2,000-book test gives 5.35% against a closed-only 13.6%. At
  higher precision the design's real false-positive rate is about **6.1%, not 5%**; the test's
  tolerance hides it. *(Orchestrator note: the owner accepted ~6% and chose not to amend ADR 0002 on
  2026-10-12.)*
- **Measure 2** (live) cannot be checked yet; TESTPLAN 11.21 (⚠) covers it, with 11.16 for the counts.

**Scope.** Mutants were planted only in a private copy, `/private/tmp/claude-501/qa-shadow-mutants`
(rsync of HEAD with its own throwaway git); the shared worktree was never edited. Between 12:31 and
12:36 the engineer's fix loop 1 modified `sonar/calibration.py`, `sonar/core.py`, `ui/app.py`, three test
files and docs (uncommitted then): a `decided` cache, dropping the newest bar, filtering bars with
`t <= now`, a comment on the owner's ~6% acceptance. **Nothing here covers those edits.** Re-run
`/private/tmp/claude-501/qa-harness/mutate.py` (with `ROOT` at a fresh copy) and both suite modes on the
new tree before calling Verify done for it.

**Playbook:** `docs/playbooks/qa-engineer.md` is `status: baseline` (2026-10-10): stale; added nothing
beyond AGENTS.md. **Activity log:** `verify start` / `verify done` appended to
`docs/company/activity.jsonl` (the only write to the worktree).

## 1. Test map (V-1..V-16, U-1..U-8)

| # | Test(s) | Tests what the spec says? |
|---|---|---|
| V-1 | `test_v1_a_barrier_hit_before_t_keeps_its_outcome`, `_needs_no_price` | Yes |
| V-2 | `test_v2_a_barrier_hit_after_the_cut_is_graded_at_t` | Yes |
| V-3 | `test_v3_the_cut_is_the_next_bars_stamp_exclusive` (T_CUT−1 and T_CUT) | Yes, both sides |
| V-4 | `test_v4_the_direction_signs_r` | Yes |
| V-5 | `test_v5_r_is_in_units_of_the_stop_distance` (+0.75) | Yes |
| V-6 | `test_v6_a_t_bar_still_trading_is_not_a_result` | Yes |
| V-7 | `test_v7_a_holiday_takes_the_session_before_never_the_one_after` | Yes |
| V-8 | `test_v8_*` (3) | Partly: the T bar's own close beyond a barrier (M11) and rule 1 over rule 2 (M12) not covered |
| V-9 | `test_v9_*` (3) | Partly: a hand close at or before t_T counted as it happens (Build note 4) not tested (M13) |
| V-10 | `test_v10_no_price_waits_a_week_then_is_left_out_never_zero`, series-coverage test | Yes |
| V-11 | `test_v11_the_shadow_reads_and_changes_nothing` (deepcopy), `test_v11_every_verdict_is_the_same_with_the_shadow_computed` (6 branches), `test_the_pass_reads_copies_and_writes_nothing` | Yes; `git diff cf84642 HEAD` shows `portfolio.py`, `scoring.py`, `engine.py` untouched, and the only removed line in `calibration.py` is the import |
| V-12 | Always: library-vs-direct-walk check, quick null (1,000), quick power (500). Slow: 2,000-book spec test with closed-only comparison, 20,000-book size test, 10,000-book power test | Spec run matches; **the precision test uses ±1.5 pt at 20,000 books where 3 SE is ±0.5 pt** (P1-1) |
| V-13 | `test_v13_*` (2), `test_looks_cross_at_the_boundary_inclusive…`, `test_a_look_counts_its_exclusions` | Yes |
| V-14 | `test_v14_t_the_looks_and_the_line_are_pre_registered` | Yes (ADR §1, §3) |
| V-15 | `test_shadow_engine.py`, `test_follow.py::test_the_follower_shows_the_holders_shadow_and_never_fetches` (real HTTP), `test_server.py` | Yes; lock probes valid. **Gap:** fetching for entries the book closed after t_T untested (M14) |
| V-16 | `test_v16_the_reference_is_the_timed_no_edge_split_per_entry` | Yes |
| U-1 | `test_u1_no_forecast_edge_or_profit_words_anywhere[plain/expert]` | Yes (substring match; `"will "` misses a line-end "will."; covered by §5's word-bounded check) |
| U-2 | `test_u2_the_existing_grade_reads_the_same…`, `test_u2_the_block_comes_after_every_existing_widget` | Partly: every shadow state, but the existing grade in one state only |
| U-3 | `test_u3_landing_and_my_trades_say_the_same_sentence` | Yes |
| U-4 | `test_u4_*` (5) | Each D3 row asserted; untested: (f) over (c) precedence (U01), premature `SH_FINAL_NONE` (U08), (a2) with `wait_price` (U05) |
| U-5 | `test_u5_every_exclusion_is_shown[4]`, `test_u5_a_look_with_over_a_tenth_left_out…[5/4]` | Partly: the warning on a due, unevaluated look untested (U04); `>` vs `>=` equivalent for 45/101/201 |
| U-6 | `test_u6_*` (2) | Yes |
| U-7 | `test_u7_*` (3) | Yes |
| U-8 | `test_u8_the_block_does_not_widen_either_page` | A proxy (block min width + every label wraps); the engineer's reason (Qt caches the hint on an unshown window) holds |

**Property check (QA's, not in the repo):** `/private/tmp/claude-501/qa-harness/invariants.py`, 1,500
random synthetic books (pending, manual, MANUAL/TARGET/STOP closes, missing symbols, gapped bars, three
presets, crypto): **0 failures** on the 11.16 count identities, band sums, R at barriers, nothing graded
before t_T, strict JSON (`allow_nan=False`), purity, determinism, each evaluated look's z = HC3 on its
members only.

## 2. Load-bearing checks
- **V-11 / V-15 / U-2:** all pass; mutants C01 (fetch under `book.lock`), C07 (compute under
  `self.lock`), C02 (follower computes), C04 (no key read as loading), C08 (positions by reference) killed.
- **V-12 slow:** `./run-tests.sh tests/ -m slow -q -p no:cacheprovider` → `3 passed, 2278 deselected in
  67.29s`, exit 0; durations 38.90 s (precision), 16.95 s (power), 7.59 s (spec). Precision test at 65%
  of the 60 s per-test timeout.

| Run | Books | Result |
|---|---|---|
| Spec null | 2,000 | design **5.35%**; closed-only rank IC at 2σ **13.60%** (mean closed n 193.6) |
| Spec power | 2,000 | **0.7405** (design 0.73) |
| Precision null | 20,000 | **6.19%**; chunks 6.05, 6.40, 5.75, 6.30, **6.65**, 5.95, **6.75**, 5.40, 6.50, 6.15 |
| Quick null / power | 1,000 / 500 | 6.5% / 0.718 |

Independent simulation (fresh walks, 20 steps per horizon, 4 horizons, production `shadow_looks` and
`hc3_z`; `/private/tmp/claude-501/qa-harness/v12_indep.py`):

| Model | Books (seeds) | Design size | \|z\| ≥ 2.315 at looks 1/2/3 (normal 2.06%) | Constant for 5% overall |
|---|---|---|---|---|
| Steep vol 1.3→0.5 | 40,000 (1,000,000+) | **6.08%**, SE 0.12 pt, +9.0 SE | 2.79 / 2.32 / 2.24% | **2.413** |
| Flat vol | 20,000 (2,000,000+) | 6.16%, +6.8 SE | 3.01 / 2.36 / 2.21% | 2.421 |
| Gaussian R (no barriers) | 20,000 (3,000,000+) | 5.53%, +3.2 SE | 2.44 / 2.08 / 2.20% | 2.365 |

**Assessment: the tolerance hides a real calibration gap.** The excess (~+1.1 pt, ~9 SE) is real; it is
not caused by score-dependent censoring (flat vol gives the same) but by small-sample, t-like tails of
the HC3 z at n = 45 plus barrier-R skew; Pocock's 2.315 is asymptotic. The ±1.5 pt band was Monte-Carlo
error at 2,000 books; at 20,000 books it is ~9 SE wide. The 2,000-book spec test passes on its seed; at
a true ~6.1% about 1 seed in 5 would exceed 6.5% (2 of 10 chunks did). The "no censoring" contrast holds
(13.6% vs 5.35%).

## 3. Mutation table
36 mutants on targeted tests (`-x`, offscreen), each reverted; the copy's `git status` clean after every
mutant. **24 killed, 11 survived, 1 equivalent.** Script `/private/tmp/claude-501/qa-harness/mutate.py`,
results `results.json`.

| ID | Mutant | Result |
|---|---|---|
| M01 | `<` → `<=` at the cut | Killed (`test_v3_…`) |
| M02 | T bar = next bar (`bisect_left`) | Killed (`test_v2_…`) |
| M03 | Direction sign dropped | Killed (`test_v4_…`) |
| M04 | R over the target distance | Killed (`test_v1_…`) |
| M05 | Cohort = first N to resolve | Killed (`test_v13_…`) |
| M06 | Boundary 1.96 per look | Killed |
| M07 | Rank IC × √(n−1) as the gate | Killed |
| M08 | A crossing does not close the design | Killed |
| M09 | Look z over non-members | Killed |
| M10 | `n_no_price` grace 0 days | Killed (`test_v6_…`) |
| **M11** | **Gap check leaves out the T bar's own close** | **Survived** |
| **M12** | **Gap check before the booked barrier (rule 2 before 1)** | **Survived** |
| **M13** | **Hand close before T counted only from T** | **Survived** |
| **M14** | **`shadow_needs_bars` ignores closes after t_T** | **Survived** (225 shadow tests) |
| M15 | Series-coverage check dropped | Killed |
| M16 | HC2 instead of HC3 | Killed |
| M17 | Look evaluated before every member final | Killed |
| M18 | Pending entries counted as excluded | Killed |
| M19 | Non-final T bar used | Killed |
| C01 | Fetch under `book.lock` | Killed |
| C02 | Follower computes and fetches | Killed |
| **C03** | **`read_only` guard dropped** | **Survived** (reachable via a settings-change `_rescan` on a waiting window; not verified) |
| C04 | Missing key read as loading | Killed |
| C05 | Failed fetch not cached | Killed |
| **C06** | **7-day range slack dropped** | **Survived** (no case near a range edge, e.g. age 85 days) |
| C07 | Compute under `self.lock` | Killed |
| C08 | Positions by reference | Killed |
| **U01** | **(c) evaluated chosen before (f) look due, prices missing** | **Survived** |
| U02 | Crossed UP/DOWN sign flipped | Killed |
| U03 | Unavailable and loading swapped | Killed |
| **U04** | **10% warning only on evaluated looks** | **Survived** |
| **U05** | **(a2) "none at T" shown while entries wait for a price** | **Survived** |
| U06 | Stale threshold 48 h | Killed |
| U07 | UI decides "crossed" from z rounded to 2 places | Equivalent |
| **U08** | **`SH_FINAL_NONE` after 2 evaluated looks** | **Survived** |
| **U09** | **Past-look row repeats the look named in the status** | **Survived** |

Branch coverage of changed lines (shadow tests): `calibration.py` 100% (159 statements, 70 branches),
`core.py` 98.7% (missed 301→303), `ui/app.py` 98.4% (5 partial arcs). Coverage alone does not show
strength: four mutants survived at 100%.

## 4. Full suite
| Run | Tree | Result | Exit |
|---|---|---|---|
| Native 1 | HEAD | `2245 passed, 3 skipped, 33 deselected in 121.96s` | 0 |
| Offscreen 1 | HEAD | all tests to `[100%]`, then wedged in Qt teardown; watchdog kill at 300 s | **137** |
| Offscreen 2 | HEAD | `2245 passed, 3 skipped, 33 deselected in 184.73s` | 0 |
| Native 2 | private copy | `2 failed, 2243 passed` — `test_version.py` needs history the copy lacks; not a HEAD defect | 1 |
| Native 3 | worktree with fix-loop-1 edits | `2265 passed, 3 skipped` | 0 |

Test count 2,248 at HEAD matches TESTPLAN.md:20, TESTING.md:13, README.md:271, static/testplan.html:110
(the working tree then collected 2,268). Noise: three `SONAR: watchdog step failed (AttributeError:
'StubLive' object has no attribute '_stop')` lines from `tests/test_server.py:351` (untouched by this
change). `test_follow` did not flake.

## 5. Copy check
`copycheck.py`: 6,344 texts in both modes (every `SHADOW_WORDS` string, every state render, 300 readouts
from synthetic books), word-bounded `will|should|buy|sell|expect*|likely|going to|bullish|bearish|promised|advertised|profit*|certain*|guarantee*|forecast*|predict*`
and "edge" outside the allowed phrases: **0 hits.** `SHADOW_WORDS` matches the spec's D6 table exactly.

## 6. Success measure 2 (live)
Not verifiable before ~2026-11-06. TESTPLAN 11.21 (⚠) covers it; 11.16, 11.19, 11.20 support it.

## Findings
- **P1-1. The design's real size is ~6.1%, not the pre-registered 5%, and the V-12 tolerance hides it.**
  The precision test asserts 3.5–6.5% at 20,000 books (SE 0.17 pt). Either accept ~6% (amend ADR §3 and
  TESTPLAN 0.9) or recalibrate the boundary (~2.41 under the walk model; power cost unmeasured). Either
  way tighten the precision test to the measured value ± 3 SE (e.g. 5.7–6.7%).
  *Orchestrator note: the owner accepted ~6% without amending the ADR (2026-10-12); this becomes a docs
  and test-tightening item.*
- **P2-1. M14:** fetching for entries the book closed after t_T is untested; a break would bring back
  censoring by score. Add a closed-at-target-after-T entry to
  `test_only_entries_past_t_without_an_earlier_barrier_are_fetched`.
- **P2-2. M11:** rule 2 includes the T bar's own close, untested (a T-bar close beyond the stop would be
  TIME with R < −1).
- **P2-3. U08:** a premature "Three looks, no crossing … The test is finished" is untested.
- **P2-4.** Verification is stale for the fix-loop-1 tree: re-run both modes and the mutation harness.
- **P3.** Survivors on spec/Build-note behaviour: M12, M13, C03, C06, U01, U04, U05, U09. U-2 checks the
  existing grade in one state only; U-8 measures the block, not the page. Offscreen wedged at teardown
  in 1 of 2 runs (exit 137) and took 185 s of a 300 s budget under load; the precision slow test takes
  39 s of the 60 s per-test timeout.

Harness files: `/private/tmp/claude-501/qa-harness/` (`mutate.py`, `results.json`, `v12_indep.py`,
`v12_numbers.py`, `invariants.py`, `copycheck.py`, `d6diff.py`).
