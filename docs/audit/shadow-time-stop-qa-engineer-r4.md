# QA engineer, Verify round 4: time-stop shadow, fix loop 3 (`a23556e..fa8d05c`, tested at HEAD `725f879`)

**Verdict: PASS for `725f879`.** No P0 or P1; two new P2 test gaps and four P3 items. All three suite modes
green; the collected count matches the documented 2,393. Saved by the orchestrator, 2026-10-12.

Playbook `docs/playbooks/qa-engineer.md` stale (`status: baseline`, 2026-10-10). Setup: three private
full-history clones at `725f879` with `sonar/macro` and `sonar/playmaker` rsynced in
(`/private/tmp/claude-501/qa-shadow-{clean,mutants,prop}-r4`); the shared worktree not edited; every clone's
`git status` clean after every mutant; synthetic books only; load average 60–150 throughout.

## 1. Mutation results (`mutate_r4.py`, `results_r4.json`)
35 mutants: 28 killed by the suite, 7 survived (the property harness kills one, U02).

| ID | Mutant | Result |
|---|---|---|
| P01 | Pattern check `% 3600` instead of `% DAY` | Killed (`test_r3_a_dst_shift_costs_a_day_and_nothing_else`) |
| P02 | Pattern check `% 60` | Killed (`test_v6_a_newest_bar_stamped_mid_session_decides_nothing`) |
| P03 / P04 | Equality loosened to 1 s / 15 min | Killed (`test_r3_…session_pattern[1-wait_price]`) |
| **P05** | Newest bar compared with the oldest bar, not the previous | **Survived** (no test has a shift long before the newest bar; one extra day of waiting after a DST change). P3-2 |
| P06 / P07 | 2nd vs 3rd newest / always true | Killed |
| **P08** | `len(series) >= 2` guard dropped | **Survived** (a 1-bar series raises IndexError → the whole readout errors). P3-3 |
| D01 / D02 | Newest bar dropped always / never | Killed |
| U01 | Newest close used as the TIME exit | Killed (`test_v2_a_barrier_hit_after_the_cut_is_graded_at_t`) |
| **U02** | Gap scan to `i + 2` (reads the newest bar's close) | **Survived the suite**; killed by the property harness (42 differences). **P2-A** |
| U03 / U04 | Later-bar check dropped / two later bars required | Killed |
| M20 | `stamps[i] <= p.opened_at` check dropped | **Killed** (`test_qa_r3_m20_…`; r3 P2-B closed) |
| **M21 / M22** | M20 check `<`, or `<= opened_at − 1 day` | **Survived** (entry-day-own-bar case not pinned). P3-1 |
| M01 | Cut `<` → `<=` | Killed (`test_v3_…`) |
| W02 (r3 survivor) | `_sh_num` instead of `_sh_ts` | **Killed** (`test_qa_r3_w02_…`; r3 P3-4 closed) |
| W09–W13 | Damaged date blanks both ends; `n` counts good dates / every row; always NONE wording; span over all rows | All killed |
| S04 / S05 | Helper skips / passes on a partial chunk set | Killed (`test_r3_a_mean_test_skips_with_no_chunks_and_fails_with_some`) |
| S01 (r3 survivor) | One precision chunk dropped (`-m slow`) | **Killed** (`1 failed, 9 passed`; r3 P3-1 closed) |
| S02 (r3 survivor) | One e2e chunk dropped (`-m slow`) | **Killed** (`1 failed, 7 passed`) |
| F09a / b / d | Engine drops the newest bar / floors stamps to the UTC day / reverses the series | Killed (`test_a_failed_request_keeps_the_series_already_held`) |
| F09c | Engine rounds stamps to the hour | Survived (low plausibility; information only) |
| C05 / C09 | Failed fetch drops yesterday's series / not counted for the day | Killed |
| **C08** | `cache[s] = (day, old or b)` (yesterday preferred over today) | **Survived**. **P2-B** |

r3 survivors no longer applicable (code removed): F07, F09 (old form), B06, B08. D04, D05, U07, N24 unchanged
(already equivalent).

Changed-line coverage (`covchanged_r4.py`; calibration, shadow_engine, shadow_ui, follow, server tests; 354
passed): 100% of changed lines and branches (calibration.py 13 statements / 8 branches; core.py 4
statements; ui/app.py 4 statements / 2 branches).

## 2. Property and copy checks
- `invariants_r3_head.py` (r3's harness without `fetched_at`), 400 books: 8,700 decided entries, 689,186
  entry-days, **0 failures**; 0 entries went back to undecided (r3 had 61).
- `invariants_r4.py` adds: newest finished bar stamped at session end, at fetch time, or end − 60 s; a data
  hole or halt of 5–40 days; a one-hour DST-like shift of the US session start. 400 books: 8,920 decided,
  731,621 entry-days, **2 failures**, both crypto (seed 29 p7 stop → target; seed 252 p2 target where the
  truth is "left"), root cause P3-4. With the crypto end stamp at 23:59:59 (`invariants_r4b.py`): 400 and
  2,000 books, **0 failures**.
- Property-level mutants (`prop_mut_r4.py`): clear signal for P02 (1,488 changed / 79 differ from truth),
  P04, P06, D02 (5,775 / 312), U01 (133), U02 (42), U03 (1,752); P01, P03, P05, P08, M20, M21, M01 same as
  baseline; D01, U04 conservative (0 failures; the suite kills both).
- `copycheck_r3.py`: 6,348 texts, 0 hits. `d6diff.py`: spec and code match (`SH_ROW_WINDOW`,
  `SH_ROW_WINDOW_NONE` exact).

## 3. Suite results (in `qa-shadow-clean-r4`)
| Mode | Result | Exit | Wall | Load |
|---|---|---|---|---|
| Native (`TEST_BUDGET_S=2400`) | `2390 passed, 3 skipped, 52 deselected in 130.43s` | **0** | 141 s | 73 → 61 |
| Offscreen | `2390 passed, 3 skipped, 52 deselected in 288.86s` | **0** | 328 s | 79 → 119 |
| Slow (`-m slow`, offscreen, `TEST_BUDGET_S=3600`) | `22 passed, 2423 deselected in 237.49s`, no skips (both means computed) | **0** | 239 s | 116 → 150 |

`2393/2445 tests collected (52 deselected)` = the 2,393 in TESTPLAN.md:20, TESTING.md:13, README.md:271,
static/testplan.html:110. No flakes. Logs: `/private/tmp/claude-501/qa-harness/suite_{native,offscreen,slow}_r4.txt`.

## 4. New findings
- **P2-A (U02).** "The newest bar's close is never used" is pinned only for the TIME exit, not the gap scan:
  extending the scan to `i + 2` passes all 354 targeted tests. Fix: a test where the bar after the T bar (the
  newest, on the pattern) closes beyond a barrier → TIME at the T bar's close, `gap` False.
- **P2-B (C08).** Nothing tests that a successful fetch replaces yesterday's series (`sonar/core.py:625`);
  inverting the `or` freezes the first series forever, so waiting entries become "no price" after 7 days.
  Fix: an engine test — day 1 good but not decisive, day 2 good and decisive → the day-2 series is used and
  the entry is graded.
- **P3-1 (M21, M22).** `test_qa_r3_m20_…` covers only a gap of at least one day; the case where the last bar
  ≤ t_T is the entry day's own bar (stamped before the entry), followed by a halt, is not pinned.
- **P3-2 (P05).** No test has a DST shift long before the newest bar; comparing with the wrong earlier bar
  would add a day of latency for half the year unnoticed. Fix: extend the DST test a few days past the shift.
- **P3-3 (P08).** The 1-bar-series guard is not pinned; without it an IndexError takes down the whole readout.
- **P3-4 (property, information).** On a 24-hour market a bar stamped at its session **end** lands on the
  00:00 pattern (end = next start). If the newest finished crypto row is restamped at exactly 00:00:00 UTC
  and the next row is missing (provider lag around midnight), the stamp is taken as the cut one day late and
  a booked close inside that day keeps its booked outcome; the memo freezes it. Needs an exact-second stamp
  (23:59:59 gives 0 failures over 2,000 books). Recommend recording in the spec's known limits, not a code change.

r3 findings: P2-A (F09) closed (code removed; F09a/b/d killed); P2-B (M20), P3-1 (S01/S02), P3-4 (W02)
closed; P3-2/P3-3 (B08, F07, B06) no longer apply.

## 5. Pre-release success measures (at 725f879)
1. **Met** (slow suite green, both means computed). 2. **Pending** (first look ~2026-11-06). 3. **Met**
(read-only; memo/cache mutants C05, C09, D-series killed; purity holds). 4. **Met** (`DAY_S` pinned by
P01–P04; guard by the r3 set; the finality constant no longer exists).

Nothing blocks release from the QA side; the two P2 gaps are test-only fixes. Harness:
`/private/tmp/claude-501/qa-harness/` (`mutate_r4.py`, `results_r4.json`, `invariants_r4.py`,
`invariants_r4b.py`, `prop_mut_r4.py`, `covchanged_r4.py`).
