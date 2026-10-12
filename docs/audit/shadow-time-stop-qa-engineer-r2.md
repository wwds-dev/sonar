# QA report, round 2: time-stop shadow readout (Verify, qa-engineer, 2026-10-12)

Checked at HEAD `52a715e` (fix loop 1 `564515c`, `1c34432`, `5546cc5`, plus the master merge); whole change
`git diff 82125df HEAD`. Saved by the orchestrator. Resumed once after a usage-limit cut-off.

**Verdict: PASS, with 2 new P2 and 5 new P3 test gaps, none blocking.** Pre-release success measures 1, 3
and 4 are demonstrably met (1 at the owner-accepted ~6% size); measure 2 is live and waits for ~2026-11-06
(TESTPLAN 11.21 ⚠).

**Scope and hygiene.** Mutants only in a private copy (`/private/tmp/claude-501/qa-shadow-mutants-r2`);
property, copy and coverage runs in a second clean copy (`/private/tmp/claude-501/qa-shadow-clean-r2`).
Nothing edited in the shared worktree; the copy's `git status --porcelain` empty after every mutant and
after the cut-off. `log_activity.py` not run (the orchestrator logs Verify). Playbook
`docs/playbooks/qa-engineer.md` `status: baseline` (stale). Synthetic books only.

## 1. Mutation table
Harness `/private/tmp/claude-501/qa-harness/mutate_r2.py` (round 1's with `ROOT` at the r2 copy, three
mutants adapted, 25 new, multi-site support); each mutant alone, targeted tests (`-x`, offscreen):
`test_calibration`, `test_shadow_engine`, `test_follow`, `test_server`, `test_shadow_ui` (baseline
`300 passed, 22 deselected`). Results `results_r2.json`, `mutate_r2.log`.

**Totals: 61 mutants, 55 killed, 3 survived, 3 equivalent.** Round 1's 36: 35 killed, 1 equivalent (U07);
all 11 round-1 survivors now killed. New 25: 20 killed, 3 survived, 2 equivalent.

### Round-1 mutants re-run
| ID | Mutant | Result |
|---|---|---|
| M01 | `<` → `<=` at the cut | Killed (`test_v3_…`) |
| M02 | T bar = next bar | Killed (`test_v2_…`) |
| M03 | Direction sign dropped | Killed (`test_v4_…`) |
| M04 | R over the target distance | Killed (`test_v1_…`) |
| M05 | Cohort = first N to resolve | Killed (`test_v13_…`) |
| M06 | Boundary 1.96 per look | Killed |
| M07 | Rank IC as the gate | Killed |
| M08 | A crossing does not close the design | Killed |
| M09 | Look z over non-members | Killed |
| M10 | No-price grace 0 days | Killed |
| M11 | Gap check leaves out the T bar | **Killed** (`test_qa_m11_the_t_bars_own_close_is_gap_checked`), was a survivor |
| M12 | Rule 2 before rule 1 | **Killed** (`test_qa_m12_…`), was a survivor |
| M13 | Hand close before T counted only from T | **Killed** (`test_qa_m13_…`), was a survivor |
| M14 | `shadow_needs_bars` ignores closes after T | **Killed** (`test_qa_m14_…`), was a survivor |
| M15 | Coverage check dropped | Killed |
| M16 | HC2 instead of HC3 | Killed |
| M17 | Look evaluated before every member final | Killed |
| M18 | Waiting counted as excluded | Killed |
| M19 | Non-final T bar used | Killed |
| C01 | Fetch under `book.lock` (adapted) | Killed |
| C02 | Follower computes or fetches | Killed |
| C03 | `read_only` guard dropped | **Killed** (`test_qa_c03_a_waiting_window_never_computes`), was a survivor |
| C04 | Missing key read as loading | Killed |
| C05 | Failed fetch not cached (adapted) | Killed |
| C06 | 7-day range slack dropped | **Killed** (`test_the_range_reaches_back…[85-6mo]`), was a survivor |
| C07 | Compute under `self.lock` (adapted) | Killed |
| C08 | Positions by reference | Killed |
| U01 | (c) chosen before (f) | **Killed** (`test_qa_u01_…`), was a survivor |
| U02 | Crossed UP/DOWN flipped | Killed |
| U03 | Unavailable and loading swapped | Killed |
| U04 | 10% warning only on evaluated looks | **Killed** (`test_qa_u04_…`), was a survivor |
| U05 | (a2) shown while entries wait for a price | **Killed** (`test_qa_u05_…`), was a survivor |
| U06 | Stale threshold 48 h | Killed |
| U07 | UI decides "crossed" from rounded z | Equivalent (as in round 1) |
| U08 | `SH_FINAL_NONE` after 2 looks | **Killed** (`test_qa_u08_two_looks_are_not_three`), was a survivor |
| U09 | Past-look row repeats the named look | **Killed** (`test_qa_u09_…`), was a survivor |

### New mutants on the fix-loop code
| ID | Mutant | Result |
|---|---|---|
| N01 | Keep-previous-series dropped (`b or None`) | Killed (`test_a_failed_request_keeps_the_series_already_held`) |
| N02 | Memo ignored by the pure function | Killed (`test_a_decided_outcome_is_kept_not_recomputed`) |
| N03 | Memo never stored by the engine | Killed (`test_one_request_per_symbol…[bars]`) |
| N04 | `no_price` memoised | Killed |
| N05 | `left` not memoised | Killed |
| N06 | Decided entries still fetched | Killed |
| N07 | Memo consulted before the protocol check | **Equivalent** (`Position.protocol` set only at open, `portfolio.py:280`; ids `uuid4`, `portfolio.py:271`) |
| N08 | Newest bar used (no `[:-1]`) | Killed (`test_v6_a_newest_bar_stamped_mid_session_decides_nothing`) |
| N09 | Future stamps kept | Killed (`test_a_bar_stamped_after_now_is_ignored`) |
| N10 | `t <= now` → `t < now` | Killed (`test_v6_the_fx_sunday_entry_waits_for_mondays_close`) |
| N11 | `SHADOW_SPLIT_GUARD` 2.0 → 3.0 | Killed |
| N12 | Guard 2.0 → 8.0 | Killed |
| N13 | Guard 2.0 → 1.0 | Killed |
| **N14** | Guard comparison `>` → `>=` | **Survived** (no case at exactly 2 stop distances; the test uses 1.5 and 2.05) |
| N15 | Guard reads the series' first close, not the last at/before entry | Killed |
| N16 | Guard scaled by the target distance | Killed |
| **N17** | One malformed row drops the rest of the series (`continue` → `break`) | **Survived** (the test appends bad rows after every good row) |
| N18 | Zero close kept | Killed |
| N19 | UI timestamp clamp removed | Killed |
| **N20** | Clamp lower bound (`0 <=`) dropped | **Survived** (no negative-timestamp case) |
| N21 | `SHADOW_TS_MAX` 4e10 → 1e17 | Killed |
| N22 | My trades renders the shadow before the existing grade | Killed |
| N23 | Landing renders the shadow before the existing grade | Killed |
| N24 | `render` no longer catches `OSError` | **Equivalent** today (the clamp keeps values in range; defence in depth) |
| N25 | Failure drops the last readout | Killed |

## 2. Property, copy and D6 checks (clean copy)
- `invariants.py` (round 1): `books checked: 1500, failures: 0`.
- `invariants_r2.py` (new): memo idempotent and holds only final states; with the memo, a failed day or a
  2:1 rescale moves no decided entry and no evaluated look; without the memo a rescaled series grades
  nothing from bars; future stamps and malformed rows (shuffled in: `None`, short tuples, `10**400`, NaN,
  ≤ 0) leave the readout byte-identical; changing the newest bar's close changes nothing; a later pass
  with more bars moves no decided entry; neither memo nor positions mutated. **`books: 1500; decided
  entries checked: 123074; evaluated looks checked: 1357; failures: 0`.** It kills N17 (297/300 books),
  N09 (203/300), N02 (298/300); not N08 or N14 (the suite kills N08).
- `copycheck.py`: `texts checked: 6344 hits: 0` (both modes, every string, every state, 300 computed
  readouts).
- `d6diff.py` against the updated D6 table: every key matches both ways; `SH_LOOK_CROSSED_DOWN` plain =
  UP with "higher R" → "lower R".
- Branch coverage of changed lines (shadow tests, diff vs `82125df`): `sonar/calibration.py` **100%** (172
  statements, 74 branches); `sonar/core.py` **98.8%** (missed 353→355, stop set just before the pass);
  `ui/app.py` **98.8%** (missed 764→766, 873→881 damaged-payload only, 914→919 running row with `ic` None,
  2824→2827 My trades with no stats).

## 3. Suite runs (HEAD 52a715e)
| Run | Result | Exit |
|---|---|---|
| Native (QA, `TEST_BUDGET_S=900`) | `2336 passed, 3 skipped, 52 deselected in 118.36s` | 0 |
| Offscreen (QA) | `2336 passed, 3 skipped, 52 deselected in 205.31s` | 0 |
| Slow (QA, `--durations=25`) | `22 passed, 2369 deselected in 236.46s` | 0 |
| Orchestrator native / offscreen / slow | 2336 + 3 skipped / same in 199.65 s / 22 passed in 178 s | 0 |

Load average ~165 during QA's runs (budget raised to 900 s; nothing came near it). `test_follow`: no
flake. Test count 2,339 matches TESTPLAN.md:20, TESTING.md:13, README.md:271, static/testplan.html:110.
Slow durations (loaded): longest 21.75 s (`test_v12_slow_the_design_power_to_two_points`); e2e chunks
13.2–20.4 s (~7 s unloaded); size chunks 4.1–8.3 s; spec test 13.6 s. Noise: three `SONAR: watchdog step
failed (AttributeError: 'StubLive' object has no attribute '_stop')` lines from `tests/test_server.py`
(untouched; present in round 1).

## 4. Status of round-1 findings
| Finding | Status |
|---|---|
| P1-1 size ~6.1% vs 5% (owner decision) | **Closed.** `tests/test_calibration.py:1012-1014` asserts the 20,000-book mean at 0.057–0.067 in 10 chunks; the 2,000-book spec test keeps 5 ± 1.5; a new e2e test holds 4,000 books at 6.095% ± 3 SE; TESTPLAN.md:48 (0.9) states ~6%, owner-accepted 2026-10-12; boundary comment `calibration.py:263-265` (wording nit P3-5) |
| P2-1 (M14), P2-2 (M11), P2-3 (U08) | **Closed** (killed) |
| P2-4 (stale verification) | **Closed by this report** |
| P3 survivors M12, M13, C03, C06, U01, U04, U05, U09 | **All killed**; U07 still equivalent |
| P3 precision test at 39 s of 60 s | **Closed for the normal run** (chunks, longest 8.3 s); new gap when run alone (P2-A) |
| P3 offscreen teardown wedge | Not seen this round |

## 5. New findings
**P0 / P1: none.**
- **P2-A. The two slow "mean" tests cannot run alone** (`test_v12_slow_e2e_the_whole_pipeline_holds_the_measured_size`,
  `test_v12_slow_the_design_size_to_a_fifth_of_a_point`): they read a module-level cache (`_e2e_hits`,
  `_v12_rates`) the chunk tests fill; alone they recompute every chunk. Measured: run alone →
  `Timeout (0:01:00)!`, faulthandler abort, exit 1 (load ~70–90). Unloaded the chunks total ~56 s and
  ~40–60 s: no margin. Collides with TESTING.md's two-run rule (rerun alone), `-k`, random-order or xdist.
  Fix: compute the means only when all chunks ran (skip otherwise), or give the mean tests their own
  smaller budget.
- **P2-B. N17: per-row bar validation only half-tested** (malformed rows only at the end). In production
  that bug would push every entry on the symbol into `wait_price` then `no_price`, inflating exclusions.
  Add a bad row mid-series.
- **P3-1. N14:** the split guard's `>` vs `>=` not pinned at exactly the bound.
- **P3-2. N20:** the UI clamp's lower bound untested (a negative timestamp shows a pre-1970 date, not n/a).
- **P3-3. N24 equivalent today:** `render`'s `OSError` catch unreachable behind the clamp; nothing would
  notice if it became load-bearing.
- **P3-4. Two engine behaviours untested:** the memo surviving `_take_the_book` (benign by reading);
  `test_the_memo_lives_in_memory…` only checks no file starting "shadow" exists (weak proof of "nothing
  persisted").
- **P3-5. Docs wording:** Build note 15 says "The V-12 test keeps its 5% ± 1.5 pt bar" while note 24 and
  TESTPLAN 0.9 give 5.7–6.7% for the 20,000-book bar; name the 2,000-book test in note 15.
- **P3-6 (information).** On the intraday preset one stop distance ≈ one daily σ, so the guard is ≈ 2
  daily σ; roughly 1% of intraday entries would be excluded spuriously (more with fat tails). Uses
  pre-entry information only, so no E[R] bias; counted.

## 6. Pre-release success measures
| Measure | Evidence | Met? |
|---|---|---|
| 1. No censoring by construction | spec 2,000-book 5.35% vs closed-only 13.6%; 20,000-book mean 6.19% in 5.7–6.7%; e2e 4,000 books within ±3 SE of 6.095%; ~6% owner-accepted | **Yes**, at ~6% |
| 2. Live, first look | due ~2026-11-06; TESTPLAN 11.21 ⚠ | Not verifiable yet |
| 3. Read-only | V-11 pass; C08 killed; `invariants_r2` purity with the memo, 0 failures | **Yes** |
| 4. Pre-registered | V-14 pins T, the looks and 2.315; M06 killed | **Yes** |

**Verdict:** Verify passes for `52a715e`; P2-A and P2-B are test-quality fixes, not release blockers.
Harness: `/private/tmp/claude-501/qa-harness/` (`mutate_r2.py`, `results_r2.json`, `invariants_r2.py`,
`copycheck.py`, `d6diff.py`, `covchanged_r2.py`).
