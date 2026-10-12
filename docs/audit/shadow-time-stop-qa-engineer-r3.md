# QA report, round 3: time-stop shadow readout (Verify, qa-engineer, 2026-10-12)

Checked HEAD `a23556e` (fix loop 2 `52a715e..c939b53`; the merge on top is docs only); whole change
`git diff 82125df a23556e`. Read-only, synthetic books only; `log_activity.py` not run. Playbook
`docs/playbooks/qa-engineer.md` `status: baseline` (stale). Saved by the orchestrator.

**Verdict: PASS for `a23556e`. No P0/P1, two new P2 test gaps, six P3 items; all r2 findings closed.**

**The shared worktree moved during Verify.** At 17:16 HEAD was `7410465` ("Fix loop 3: domain r3
N-5..N-7, the window names what it covers") with uncommitted edits to `sonar/calibration.py`,
`sonar/core.py` and two test files replacing `SHADOW_FINAL_AFTER_S` and the fetch-time rule with
`_shadow_newest_is_a_session_start` (code review r3 P2-1) — the engineer's fix loop 3, not QA's. **This
report does not verify loop 3**; the F, B and M20 rows exercise code loop 3 replaces. Verify needs a round
4 on the loop-3 tree.

**Hygiene.** Mutants only in `/private/tmp/claude-501/qa-shadow-mutants-r3`; property mutants only in
`/private/tmp/claude-501/qa-shadow-prop-r3`; the suite in `/private/tmp/claude-501/qa-shadow-clean-r3` (a
real-history clone at `a23556e`). `git status --porcelain` empty in each copy after every mutant (asserted
per mutant) and at the end.

## 1. Mutation table
Harness `/private/tmp/claude-501/qa-harness/mutate_r3.py` (r2's set adapted, plus new); results
`results_r3.json`, `r3/mutate.log`; each mutant alone, `-x`, offscreen, against `test_calibration`,
`test_shadow_engine`, `test_follow`, `test_server`, `test_shadow_ui` (baseline `346 passed, 22
deselected`); S mutants with `-m slow`.

**Totals: 103 mutants: 91 killed, 8 survived, 4 equivalent.**

### r2 set re-run (61): 59 killed, 2 equivalent
Killed: M01–M19, C01–C08, U01–U06, U08, U09, N01–N23, N25. Adapted: M01 (`< cut_hi`), M12, M19 (cut = inf),
C01, C05, C07, N01, N03, N07, N08 ("always trusted"). Guard mutants rescaled to 4.5: N11 (6.75), N12 (18),
N13 (2.25), N14, N16. r2 survivors now killed: N14 (`test_qa_n14_the_split_guard_holds_at_exactly_its_bound[109.0-True]`),
N17 (`test_one_malformed_bar_drops_that_bar_not_the_readout`), N20 (`test_qa_n20_a_negative_timestamp_reads_n_a`).
Still equivalent: U07, N24.

### New mutants on loop-2 code (42): 32 killed, 8 survived, 2 equivalent
| ID | Mutant | Result |
|---|---|---|
| F01 | Finality bound 24 h → 12 h | Killed |
| F02 | 24 h → 36 h | Killed |
| F03 | Trust judged against `now` in the pure function | Killed |
| F04 | Engine passes `now` as every fetch time | Killed |
| F05 | Kept series stamped with today's time | Killed |
| F06 | No fetch time → newest bar trusted | Killed |
| **F07** | Trust `>` → `>=` (exactly 24 h) | **Survived** (boundary unpinned) |
| F08 | Fetch time = `time.time()`, not the pass's `now` | Killed |
| **F09** | Engine never hands `fetched` to `shadow_time_stop` | **Survived** (P2-A) |
| B01 | Bounded cut removed | Killed |
| B02 | Bounded cut without its 24 h margin | Killed |
| B03 | Untrusted stamp taken as the exact cut | Killed |
| B04 | Close inside the window treated as before the cut | Killed |
| B05 | Close inside the window treated as after the cut | Killed |
| **B06** | Lower edge `<= cut_lo` → `<` | **Survived** (boundary unpinned) |
| B07 | Upper edge `>= cut_hi` → `>` | Killed |
| **B08** | Window lower edge = stamp − 12 h | **Survived** in the suite; killed by `invariants_r3` (9/400 books) |
| G01 | √momentum_days dropped | Killed |
| G02 / G03 | G 4.5 → 2.0 / → 5.0 | Killed / Killed |
| G04 | Divide by momentum_days, not its root | Killed |
| G05 | Always √5 | Killed |
| D01 | Memo hand-back shallow-copied | Killed |
| D02 | Memo storage not deep-copied | Killed |
| D03 | `booked` refresh dropped | Killed |
| D04 | `booked = p.outcome` without the `closed_at` check | Equivalent (`outcome` None until close, `portfolio.py:90`) |
| D05 | Memo overwritten by later passes | Equivalent (same state, R, exit; `booked` refreshed anyway) |
| T01 / T02 | `_take_the_book` keeps the memo / bar cache | Killed / Killed |
| W01 | Window: graded filter dropped | Killed |
| **W02** | Window: `_sh_num` instead of `_sh_ts` (clamp skipped) | **Survived** (P3-4) |
| W03 | First and last swapped | Killed |
| W04 | Shown with no entries | Killed |
| W05 | Last row, not first | Killed |
| W06 | "Graded" includes left / no_price | Killed |
| W07 | Window only on the plain page | Killed |
| W08 | n/a branch returns "" | Killed |
| E01 | `SH_ERROR` not through `_clean` | Killed |
| **M20** | `stamps[i] <= p.opened_at` check dropped | **Survived**; `invariants_r3` does not reach it (P2-B) |
| **S01** | One precision chunk dropped from the parametrize | **Survived** (`20 passed, 1 skipped`, exit 0; P3-1) |
| **S02** | One e2e chunk dropped | **Survived** (`20 passed, 1 skipped`, exit 0; P3-1) |
| S03 | An e2e chunk raises before recording | Killed (chunk fails; mean skips) |

A *broken* chunk cannot let the mean skip silently (S03); a *missing* chunk can (shrunk parametrize, `-k`,
deselection, reordering, xdist → `len(_v12_rates) < N` → skip, exit 0).

## 2. Property, copy and D6 checks (clean copy of HEAD)
- `invariants.py`: `books checked: 1500, failures: 0`.
- `invariants_r2.py`: `books: 1500; decided entries checked: 123176; evaluated looks checked: 1358; failures: 0`.
- **New `invariants_r3.py` (realistic daily fetches):** in-progress newest bar (moving close; stamp at
  session start or fetch time); 15% failed days keeping the old series and fetch time; US-session equities
  with holidays plus 24 h crypto; week, intraday, month; booked closes concentrated around t_T and the cut
  window. Checks every early decision equals the outcome once all sessions are final, and that a decided
  outcome never changes. **`books: 1000; decided entries: 22026; entry-days checked: 1751155; failures: 0`.**
  Kills F01, F03, B02, B03, B04, B05, B08, N08, M19 (`prop_mut_r3.py`); not F02/B01 (conservative), F07,
  B06, M01 (measure-zero boundaries), M20.
- `copycheck.py` (old ALLOWED list): `texts checked: 6346 hits: 615`, all the new allowed condition "with no
  edge, exact fills and randomly wandering prices". `copycheck_r3.py` with ALLOWED = `EDGE_ALLOWED`
  (`tests/test_shadow_ui.py:39`): **`texts checked: 6346 hits: 0`**, both modes, every state, 300 readouts.
- `d6diff.py`: every key matches both ways.
- Branch coverage of changed lines (`cov_r3.json`): loop-2 lines `calibration.py` 98.0% (missed 397→398, the
  M20 check, 100% in r2), `core.py` 100%, `ui/app.py` 100%; whole change `calibration.py` 99.3%, `core.py`
  98.9% (355→357), `ui/app.py` 98.8% (same four damaged-payload/no-stats branches as r2).

## 3. Suite runs (HEAD a23556e, real-history clone)
| Run | Result | Exit | Load avg |
|---|---|---|---|
| Native (`TEST_BUDGET_S=1200`) | `2382 passed, 3 skipped, 52 deselected in 131.35s` | 0 | 106 → 218 |
| Offscreen | `2382 passed, 3 skipped, 52 deselected in 312.61s` | 0 | 218 → 198 |
| Slow (`-m slow -rs --durations=25`) | `22 passed, 2415 deselected in 190.26s`, 0 skipped | 0 | 167 → 120 |
| `test_v12_slow_the_design_size_to_a_fifth_of_a_point` alone | `1 skipped in 0.43s` (reason printed) | 0 | ~120 |
| `test_v12_slow_e2e_the_whole_pipeline_holds_the_measured_size` alone | `1 skipped in 0.62s` | 0 | ~120 |

Load 80–218 on 8 cores (budgets raised; none approached). Slow durations under load: longest e2e chunk
18.79 s, power 18.58 s, size chunks 3.2–4.7 s. A first native run in a single-commit copy failed 2
`test_version.py` tests (copy history artifact). `test_follow` did not flake; the 3 `StubLive … '_stop'`
noise lines as in r2. Count 2,385 = TESTPLAN.md:20, TESTING.md:13, README.md:271, static/testplan.html:110.

## 4. Status of r2 findings
| Finding | Status |
|---|---|
| P2-A mean tests cannot run alone | **Closed** (each skips alone in < 1 s; full slow run computes both); residual P3-1 |
| P2-B N17 half-tested | **Closed** |
| P3-1 N14, P3-2 N20 | **Closed** |
| P3-3 N24 | Unchanged (equivalent, left as instructed) |
| P3-4 memo across `_take_the_book`; weak "nothing persisted" | **Closed** (T01/T02 killed; `test_r2_a_pass_writes_nothing_at_all` checks every file, size, mtime) |
| P3-5 Build note 15 wording | **Closed** (spec 493–495, 588) |
| P3-6 intraday guard ≈ 2 daily σ | **Closed** by the daily-σ guard |

## 5. New findings
**P0 / P1: none.**
- **P2-A (F09).** No engine test shows the fetch time reaching the grade (`sonar/core.py:587`): without it
  a Mon–Thu T is decided 4.4 d after t_T instead of 2.4; `test_r2_a_kept_series_is_judged_at_its_own_fetch_time`
  covers only the negative case. Needs an engine test where a finished newest bar fetched > 24 h after its
  stamp decides. Re-check on loop 3, which appears to remove the fetch-time rule.
- **P2-B (M20).** The "no bar after the entry up to t_T" check lost coverage in loop 2
  (`calibration.py:397-398`). Without it, an entry with no bar between opening and t_T (halt, delisting,
  data hole ≥ T) is graded TIME at an entry-day or earlier close, possibly before the entry — a wrong R into
  the gate. Needs a test with bars stopping at the entry and resuming after t_T.
- **P3-1 (S01/S02).** A slow mean test skips silently (exit 0) when any chunk did not run. Fix: skip only
  when no chunk ran; fail when 0 < ran < N.
- **P3-2 (B08).** The bounded-cut window's lower edge is pinned only at −25 h and −1 h; add a booked close
  at about −13 h.
- **P3-3 (F07, B06).** Boundaries at exactly 24 h before the fetch and a close exactly at `cut_lo` unpinned.
- **P3-4 (W02).** The window's clamp untested with mixed entries: one damaged `opened_at` among good ones
  blanks an end ("22 Sep to n/a") instead of being ignored.
- **P3-5 (information).** Without the memo, 61 of 22,026 early-decided entries (0.28%) go back to waiting (an
  in-progress bar stamped at fetch time bounds the cut more tightly than the next day's session-start stamp).
  With the memo the outcome stays and is correct (0 truth mismatches); after a restart such an entry waits
  ~1 more day. Never a wrong outcome.
- **P3-6 (harness).** r2 `copycheck.py`'s ALLOWED list predates the narrowed `EDGE_ALLOWED`; `copycheck_r3.py`
  mirrors it.

## 6. Pre-release success measures (at a23556e)
| Measure | Evidence | Met? |
|---|---|---|
| 1. No censoring by construction | slow suite green, both means computed (precision 5.7–6.7%; e2e ±3 SE of 6.095%); 2,000-book spec test in the default run; ~6% owner-accepted | **Yes**, at ~6% |
| 2. Live, first look | due ~2026-11-06 (TESTPLAN 11.21) | Not verifiable yet |
| 3. Read-only | C02, C03, C08 killed; `invariants_r2` purity 0 failures; whole-directory no-write test; T01/T02 killed | **Yes** |
| 4. Pre-registered | M06 killed; T, looks, 2.315, guard and finality constants pinned | **Yes** |

**Verdict:** measures 1, 3, 4 met and 2 pending, for `a23556e` only; loop 3 (`7410465` plus the uncommitted
calibration/core work) is unverified and needs a round 4.

Harness: `/private/tmp/claude-501/qa-harness/` (`mutate_r3.py`, `results_r3.json`, `invariants_r3.py`,
`prop_mut_r3.py`, `copycheck_r3.py`, `cov_r3.json`); logs in `r3/`.
