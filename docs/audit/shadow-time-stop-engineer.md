# Build report: the time-stop shadow of the score grade

- Phase: Build (engineer), 2026-10-12, branch `claude/zealous-mclaren-8985d0`.
- Spec: [`docs/specs/shadow-time-stop.md`](../specs/shadow-time-stop.md). ADR: [0002](../adr/0002-shadow-time-stop-grade.md).
- Commits: `1c22be7` (pure function and its tests), `3849700` (engine and payload), `9b4752e` (UI,
  TESTPLAN and suite count), `c27d812` (one more `hc3_z` case; suite count 2,045). This report, the
  spec's Build notes and the backlog are in the last commit.
- Playbook: `docs/playbooks/engineer.md` is `status: baseline` (seeded 2026-10-10, never
  radar-verified), so treat it as stale. It added nothing beyond `AGENTS.md`.
- Pre-registration: built and tested on synthetic books only. No time-stop outcome was computed for
  the real book or any copy of it. No test or command pointed at the live data directory: conftest
  patches `paths.user_data_base` to a tmp dir for every test, at both session and function scope.
  The app was not run, and the launchd agent was not touched.
- Phases skipped: none. Review, Verify, Secure, Document and Release come next. No version bump
  and no CHANGELOG entry, as instructed.

## What was built

| Part | Where |
|---|---|
| Constants: T in horizons (4), looks (45, 101, 201), boundary 2.315, 7-day price grace | `sonar/calibration.py:261-272` |
| `shadow_t_days`, `shadow_due`, `shadow_reference_horizons`, `shadow_needs_bars` | `sonar/calibration.py:275-304` |
| `hc3_z`, the gate statistic (the sims' sum; None, never NaN or inf) | `sonar/calibration.py:307` |
| Rules 1-3 from the bars (`_shadow_from_bars`) and per entry (`_shadow_entry`) | `sonar/calibration.py:335`, `:364` |
| `shadow_looks`: cohorts by entry order, evaluated once, the first crossing closes the design | `sonar/calibration.py:403` |
| `shadow_time_stop(open, closed, bars, now)`: every D4 field, plus per-entry outcomes | `sonar/calibration.py:462` |
| `SHADOW_UNAVAILABLE`, `SHADOW_RANGES`, `Live.shadow` (None = loading), the in-memory bar cache | `sonar/core.py:87-91`, `:181` |
| The pass after `_mark_book` and the seed in the scan | `sonar/core.py:296` |
| `_shadow_pass`: copy under `book.lock`, compute outside every lock, assign under `self.lock`, keep the last good readout on error | `sonar/core.py:490` |
| `_shadow_fetch` (once per symbol per UTC day, failures included) and `_shadow_range` | `sonar/core.py:518`, `:548` |
| Takeover resets to loading; the follower mirrors the readout or marks it unavailable | `sonar/core.py:1068`, `:1205` |
| `/api/book` carries `shadow` | `sonar/server.py:180` |
| `SHADOW_WORDS` (D6), formats, `shadow_texts` (D3 states), rows, warnings | `ui/app.py:471`, `:698-878` |
| `ShadowGrade(QFrame)`, `_hline` | `ui/app.py:880`, `:336` |
| Placed after every existing widget: My trades `:2364`, landing `:2513`; rendered in `_refresh_book` `:2386` and `_refresh_portfolio` `:2694` | `ui/app.py` |
| `slow` marker, registered and deselected by default | `pyproject.toml` |
| TESTPLAN 0.9 and 11.14-11.21; suite size 2,045 in TESTPLAN, TESTING, README and `static/testplan.html` | docs |

## Decisions
All of them are in the spec, under Architecture → **Build notes** (items 1-15). In short:
1. An entry is graded only from its t_T on, even when the book settled it earlier. This keeps the
   running figures from leaning on quick resolvers.
2. The gap check reads bars stamped after `opened_at`, up to the T bar. Every decision that needs
   bars waits until the T bar is final.
3. The series must reach back to `opened_at`. The fetch range is the shortest of 3mo, 6mo, 1y, 2y
   and 5y that covers the oldest entry needing bars, plus 7 days.
4. A hand close before the cut is excluded before the gap check. A hand close after the cut is
   graded like an open position.
5. R uses the formula, with exits at the barrier. That gives +R:R and −1 whenever the fill was at
   the planned entry.
6. `n_no_price` is not sticky: it depends on which bars exist when the readout is computed. Nothing
   is persisted, so it cannot be frozen. Flagged for review.
7-13. Look fields, `ic_closed` on the same entries, reference horizons (4 weekday, 5.6 crypto), how
   mixed T is handled, `hc3_z` returning None, the engine's sentinels, and UI state precedence and
   z formatting.
14. The TESTPLAN case the spec calls 11.9b is numbered **11.14**, because the generator accepts
   only `N.N` ids.
15. How V-12 is built, and its numbers (below).

String changes, recorded in the spec's D6 table:
- `SH_ROW_SPLIT` now reads "valued at the close after {T}". It used to read "the {T} close".
- `SH_LOOK_WAITING_PRICE` used `{k}` twice; the count is now `{w}`.

## V and U tests → test names

| # | Test(s) |
|---|---|
| V-1 | `test_calibration.py::test_v1_a_barrier_hit_before_t_keeps_its_outcome`, `test_v1_a_barrier_hit_before_t_needs_no_price` |
| V-2 | `test_v2_a_barrier_hit_after_the_cut_is_graded_at_t` |
| V-3 | `test_v3_the_cut_is_the_next_bars_stamp_exclusive` |
| V-4 | `test_v4_the_direction_signs_r` |
| V-5 | `test_v5_r_is_in_units_of_the_stop_distance` |
| V-6 | `test_v6_a_t_bar_still_trading_is_not_a_result` |
| V-7 | `test_v7_a_holiday_takes_the_session_before_never_the_one_after` |
| V-8 | `test_v8_a_daily_close_through_the_stop_is_a_stop_the_polls_missed`, `test_v8_the_entry_days_own_close_is_not_a_gap`, `test_v8_the_first_barrier_crossed_is_the_one_graded` |
| V-9 | `test_v9_manual_entries_and_hand_closes_are_left_out_and_counted`, `test_v9_a_hand_close_after_the_cut_is_graded_at_t`, `test_v9_a_hand_close_between_t_and_the_cut_is_left_out` |
| V-10 | `test_v10_no_price_waits_a_week_then_is_left_out_never_zero`, `test_a_series_that_does_not_reach_back_to_the_entry_cannot_decide` |
| V-11 | `test_v11_the_shadow_reads_and_changes_nothing`, `test_v11_every_verdict_is_the_same_with_the_shadow_computed` (6 verdict branches); engine: `test_shadow_engine.py::test_the_pass_reads_copies_and_writes_nothing` |
| V-12 | always on: `test_v12_the_fast_walk_library_is_the_sims_walk`, `test_v12_quick_the_design_holds_its_size`, `test_v12_quick_the_design_has_its_planned_power`, `test_the_gate_is_the_hc3_slope_of_the_evidence_script`; slow: `test_v12_the_design_holds_its_size_where_the_closed_only_grade_does_not`, `test_v12_slow_the_design_size_to_a_fifth_of_a_point`, `test_v12_slow_the_design_power_to_two_points` |
| V-13 | `test_v13_a_cohort_is_the_first_n_by_entry_and_is_fixed_once_evaluated`, `test_v13_a_look_waits_for_every_member`, `test_looks_cross_at_the_boundary_inclusive_and_the_first_crossing_closes`, `test_a_look_counts_its_exclusions` |
| V-14 | `test_v14_t_the_looks_and_the_line_are_pre_registered` |
| V-15 | `test_shadow_engine.py`: `test_the_fetch_happens_outside_both_locks`, `test_the_engine_never_holds_the_engine_lock_while_computing`, `test_a_follower_never_fetches_or_computes`, `test_the_follower_mirrors_the_holders_shadow[older holder: no key]` (and 2 more ids), `test_a_mirrored_shadow_that_is_not_a_dict_is_ignored`, `test_one_request_per_symbol_per_utc_day_failures_included`, `test_the_range_reaches_back_past_the_oldest_entry`, `test_a_failure_keeps_the_last_readout_and_says_why`, `test_before_the_first_pass_the_readout_is_loading`, `test_the_scan_works_it_out_after_marking_the_book`, `test_taking_the_book_forgets_the_holders_shadow`, `test_the_readout_is_served_with_the_book`; `test_follow.py::test_the_follower_shows_the_holders_shadow_and_never_fetches` (two real HTTP endpoints); `test_server.py::test_the_book_is_served_with_its_grading_and_switch` (now expects `shadow`) |
| V-16 | `test_v16_the_reference_is_the_timed_no_edge_split_per_entry` |
| U-1 | `test_shadow_ui.py::test_u1_no_forecast_edge_or_profit_words_anywhere[plain/expert]` |
| U-2 | `test_u2_the_existing_grade_reads_the_same_with_the_shadow_present`, `test_u2_the_block_comes_after_every_existing_widget` |
| U-3 | `test_u3_landing_and_my_trades_say_the_same_sentence` |
| U-4 | `test_u4_each_state_says_its_own_sentence`, `test_u4_not_a_test_yet_until_a_look_is_evaluated`, `test_u4_the_running_row_always_says_not_a_test`, `test_u4_running_figures_wait_for_twenty_results`, `test_u4_past_looks_are_listed_under_the_sentence` |
| U-5 | `test_u5_every_exclusion_is_shown[4 params]`, `test_u5_a_look_with_over_a_tenth_left_out_says_so[5-True / 4-False]` |
| U-6 | `test_u6_no_reference_means_no_reference_line_and_no_dash`, `test_u6_the_reference_and_the_bands_when_present` |
| U-7 | `test_u7_z_near_the_line_never_contradicts_the_verdict`, `test_u7_the_sentence_follows_the_unrounded_decision`, `test_u7_the_shown_z_is_clamped_to_the_verdicts_side` |
| U-8 | `test_u8_the_block_does_not_widen_either_page` |
| Untrusted payload | `test_payload_text_is_never_markup`, `test_a_damaged_readout_is_never_a_crash[4]`, `test_a_readout_this_build_cannot_read_is_said_not_half_shown` |
| Other | degenerate JSON, running figures, `ic_closed`, pending orders, graded only from t_T, NaN bars, zero stop distance, T in words, dates, both wordings keep the same rows, accessible name and heading link |

The default suite has 129 new tests (1,916 → 2,045). Three slow tests are deselected by default.

## Mutation check
Each mutant was planted on its own, the named tests were run (`pytest -x`, offscreen), and the
original was restored. The script and its output are in the session scratchpad, not the repo. The
working tree was checked clean of mutants afterwards: `git status` and `git diff` showed only the
intended changes, and the full suite was green on the final tree.

| Mutant | Result: first failing test |
|---|---|
| V-1 barrier close graded as TIME | killed: `test_v1_a_barrier_hit_before_t_keeps_its_outcome` |
| V-2 closed_at ignored against T | killed: `test_v2_…` |
| V-3 `<` → `<=` at the cut | killed: `test_v3_…` |
| V-4 direction sign dropped | killed: `test_v4_…` |
| V-5 R over the target distance | killed: `test_v1_…` (and V-5) |
| V-6 non-final T bar used | killed: `test_v6_…` |
| V-7 next bar instead of the T bar | killed: `test_v2_…` |
| V-8 gap check skipped | killed: `test_v8_a_daily_close_through_the_stop…` |
| V-8b entry day's own close counted as a gap | killed: `test_v8_the_entry_days_own_close_is_not_a_gap` |
| V-9 MANUAL graded by P&L sign | killed: `test_v9_manual_entries…` |
| V-10 missing price as R = 0 | killed: `test_v10_…` |
| V-11 writes `pos.exit` | killed: `test_v11_the_shadow_reads_and_changes_nothing` |
| V-12 boundary 1.96 per look (in the comparison only, so V-14 cannot see it) | killed: `test_v12_quick_the_design_holds_its_size` |
| V-12 rank IC as the gate | killed: `test_v13_…` (and the HC3 identity test) |
| V-12 HC0 instead of HC3 (no leverage correction) | killed: `test_the_gate_is_the_hc3_slope_of_the_evidence_script` |
| V-13 cohort = first N to resolve | killed: `test_v13_a_cohort_is_the_first_n_by_entry…` |
| V-13 a look evaluated after the design closed | killed: `test_looks_cross_at_the_boundary…` |
| Boundary exclusive (`>` for `>=`) | killed: `test_looks_cross_at_the_boundary…` |
| V-14 T, a look, the boundary changed (3 mutants) | all killed |
| V-16 untimed reference; crypto at 4 horizons | both killed: `test_v16_…` |
| Early barrier graded before T | killed: `test_an_entry_is_graded_only_from_its_fixed_date` |
| V-15 fetch under `book.lock` | killed: `test_the_fetch_happens_outside_both_locks` |
| V-15 compute under `self.lock` | killed: `test_the_engine_never_holds_the_engine_lock_while_computing` |
| V-15 follower computes | killed: `test_a_follower_never_fetches_or_computes` |
| V-15 no key read as loading | killed: `test_the_follower_mirrors_the_holders_shadow[older holder: no key]` |
| Positions passed by reference | killed: `test_the_pass_reads_copies_and_writes_nothing` |
| A request every scan; a failed fetch retried at once | both killed: `test_one_request_per_symbol_per_utc_day…` |
| Range ignores the oldest entry | killed: `test_the_range_reaches_back…[100-6mo]` |
| Error drops the last readout | killed: `test_a_failure_keeps_the_last_readout_and_says_why` |
| Takeover keeps the holder's shadow | killed: `test_taking_the_book_forgets_the_holders_shadow` |
| The scan does not run the pass | killed: `test_the_scan_works_it_out_after_marking_the_book` |
| U-5 warning at ≥ 8%; a non-zero exclusion dropped | both killed |
| U-6 dash for a missing reference | killed |
| U-7 z rounded, not cut | killed |
| Payload rendered as markup | killed: `test_payload_text_is_never_markup` |
| Running line from 10 results | killed |
| U-4 state (f) skipped | killed |
| U-2 shadow written into the existing grade | killed: `test_u2_the_existing_grade_reads_the_same…` |
| U-8 status / rows label unwrapped | **survived at first**: the test measured the page's `minimumSizeHint`, which Qt caches on a window that is never shown. The test was rewritten to measure the block itself and to require every label to wrap. Both mutants are now killed. |

The first U-2 mutant I tried also survived. It wrote into `grade_next` before `_refresh_grade`, which
then overwrote it, so it is an equivalent mutant. I reformulated it as a write after
`_refresh_grade`, and that mutant is killed. Totals: 46 distinct mutants. One is equivalent (the
first U-2). The other 45 are all killed by the final tests; the two U-8 mutants are killed only
after the test was rewritten.

## Suite runs (final tree)
```
PYTHON=/Users/as/Documents/lab/active/sonar/.venv/bin/python ./run-tests.sh tests/ -q -p no:cacheprovider
2042 passed, 3 skipped, 33 deselected in 57.64s              exit 0
QT_QPA_PLATFORM=offscreen PYTHON=… ./run-tests.sh tests/ -q -p no:cacheprovider
2042 passed, 3 skipped, 33 deselected in 76.16s              exit 0
python -m pytest tests/test_calibration.py -m slow
3 passed, 58 deselected in 49.67s
```
The deselected 33 are the 30 network tests and the 3 slow tests. Each run printed the usual three
"MainWindow already deleted" tracebacks. Neither run showed a test_follow timing flake.

Coverage, offscreen, whole suite: 85% total branch coverage (the floor is 83%).
`sonar/calibration.py` is at 97%, and the new code in `core.py` is fully covered. That run left 7
lines of the new `ui/app.py` code and 4 of the shadow section of `calibration.py` uncovered. I added
tests for each, and a re-run of the UI and calibration tests under coverage then showed no uncovered
line in the new `ui/app.py` code. I did not re-run the whole suite under coverage after that. Lint (`uvx ruff check`, the
repo's `ruff.toml`) finds nothing new: 0 findings in the new or changed code, and the 5
pre-existing findings in `core.py` and `ui/app.py` are unchanged.

## V-12: measured size and power
Model: the sims' driftless walk, 20 marks per horizon, 4 horizons, target +1.5 and stop −1, exact
fills. Realised vol / σ̂ falls from 1.3 to 0.5 with score, and there is no edge. The design runs
through the production `shadow_looks` and `hc3_z`.

| Run | Books | Seeds (library; books) | Result |
|---|---|---|---|
| Quick null (default suite) | 1,000 | 20,000 paths, seed 11; 20261012 | design size 6.5% (band 2.5-8%) |
| Quick power (default suite) | 500 | 11; 20261013 | 0.718 (0.73 ± 0.060) |
| Spec null (slow) | 2,000 | 50,000 paths, seed 12; 20261012 | **design 5.35%**; closed-only rank IC at 2σ on the same books **13.6%** at n ≈ 194 closed |
| Spec power (slow) | 2,000 | 12; 20261013 | **0.7405** |
| Precision null (slow) | 20,000 (10 × 2,000) | libraries 100-109 at 20,000 paths; books 2000-2009 | **6.19%**, Monte-Carlo SE 0.17 pt (chunks 5.4-6.75%) |
| Precision power (slow) | 10,000 (5 × 2,000) | libraries 200-204; books 3000-3004 | **0.739** |
| Prototype, 50,000-path libraries | 20,000 | 500-509; 1000-1009 | 5.94% (flat vol: 5.93%; mild gradient: 6.25% at 10,000) |
| Prototype, fresh walks (no library) | 6,000 | 1000-1002 | 5.78% |

Per look, at 20,000 books: 2.7%, 1.9% and 1.4%. Pocock's nominal rate is about 2.06% at each look.
At 2,000 books the Monte-Carlo SE is 0.53 pt, so single 2,000-book chunks vary a lot. With
50,000-path libraries they ranged from 4.95% to 7.1%, with one of ten above 6.5%. With 20,000-path
libraries they ranged from 5.4% to 6.75%, with two of ten above 6.5%.

## Left for the owner
1. **The design's real false-positive rate is about 6%, not 5%** (5.8-6.2% across three methods).
   That is inside the spec's 5 ± 1.5 band, so I did not treat it as a blocker. But it sits about
   1 pt above nominal, and the margin to the band's top edge is about 2 Monte-Carlo SE at 2,000
   books. The excess comes from look 1 (n = 45), where the HC3 z has heavier tails than normal. The
   boundary is pre-registered and I left it unchanged. The question goes to the model-validator and
   the owner before the first look (about 2026-11-06). Options are to accept about 6%, or to amend
   ADR 0002 (for example, a small-sample correction at look 1) before any look is evaluated.
2. **`n_no_price` is not sticky** (Build note 6). If closes arrive more than a week after an
   entry's T, an evaluated look can change. This needs a week-long outage, and with nothing
   persisted it cannot be frozen. For the reviewer.
3. **Run `./run-tests.sh tests/ -m slow` at release.** It takes about a minute. The precision test
   took 33 s on its own, within the 60 s per-test faulthandler limit, but a loaded machine could
   bring it close to that limit.
4. **Branch base.** This branch is based on an older master. `git diff master..HEAD` shows master
   ahead in `ui/app.py` and in other files (for example `tests/test_refused_action_message.py`).
   The merge at Release will need care in `ui/app.py`.
5. Intermediate commits `1c22be7` and `3849700` each fail one test, the documented-suite-size check,
   because the counts are updated in `9b4752e`. The final tree is green.
6. `docs/company/activity.jsonl` was already modified by other sessions when this build began. I
   appended `build start` / `build done` to it but did not commit it.

## Not verified
- Behaviour against real Yahoo bars, timestamps and ranges. Every fetch here is a stub. ADR §5's
  live check is from 2026-10-12, made by the architect, not by this build.
- The window on a real display (only offscreen and native test windows were built, never shown),
  and VoiceOver reading the accessible name.
- A real holder-follower pair across two processes with the new key. `test_follow` uses one real
  HTTP server and a fake holder; `test_two_processes.py` was not extended.
- The live success measure (TESTPLAN 11.21). It is due on or after the first look.

## Fix loop 1 (2026-10-12, on top of `cca9428`)
Inputs: `shadow-time-stop-code-reviewer.md`, `-domain-finance.md`, `-security-engineer.md`,
`-qa-engineer.md` and `-model-validator.md`, plus owner decisions relayed by the coordinator.
Synthetic books only; nothing ran against the real book or the live data directory. Commits:
`564515c` (calibration and engine), `1c34432` (UI, copy, suite counts), and a last docs commit
(spec, TODO, this section).

### What changed
| Finding | Fix | Where |
|---|---|---|
| Code review P1-1 / validator P1-1: one failed fetch rewrote evaluated looks | A failed request keeps the series already held. The engine memoises decided outcomes (target, stop, time, left) by position id, hands them back, and stops fetching for them. Not persisted. Build note 6 is rewritten: one failed request was enough, not a week-long outage. | `core.py` `_shadow_pass`, `_shadow_fetch`; `calibration.shadow_decided`, the `decided=` argument |
| Code review P1-2 / validator B1–B3: the newest bar is stamped at fetch time | The newest bar never picks the T bar or the cut. Bars stamped after `now` are ignored. Validator s1 B1/B2/B3 all wait, then grade at day 28's close. | `_shadow_from_bars`; the cleaning loop in `shadow_time_stop` |
| Security P2-2 / P3-3 and code review P2-1: wrong closes and splits | Closes ≤ 0 are dropped, and rows are validated one at a time. `SHADOW_SPLIT_GUARD = 2.0` (stop distances between the last close at or before entry and `p.entry`) marks a rescaled series unusable, so the entry waits and then counts as no price. It is σ-based rather than a [0.5, 2] ratio, which would pass 3:2 and even an exact 2:1 split. Build note 19. | `calibration.py` |
| Domain P1-1 | Crossed wording: "On these paper entries, higher scores went with higher R on average". The caveat says: past paper entries, before costs, fees and slippage, exact fills, one test that can cross by chance, not a trading edge. The `SH_NOTE` last sentence no longer says "the direction was random". No false-alarm rate appears anywhere. | `SHADOW_WORDS`, spec D6 |
| Domain P1-2 | `SH_ROW_REF` and the band tail are conditional on the volatility estimate. Both modes keep "what no edge would give", and U-6 still holds. | same |
| Security P2-1 / code review P2-2 | Payload timestamps outside 0..4e10 show n/a, `render` catches `OSError`, and both pages render the shadow after the existing grade. | `ui/app.py` `_sh_ts`, `_refresh_book`, `_refresh_portfolio` |
| Validator P2-4 | "no link strong enough to cross the line yet"; "on average". `SH_FINAL_NONE` is unchanged (ADR-fixed, the owner's call). | `SHADOW_WORDS` |
| Owner decision on the size | The boundary comment now reads "nominal 5% (Pocock); measured ~6% … accepted by the owner 2026-10-12". Build note 15 records the decision, and the TODO item is closed. ADR untouched. | `calibration.py:263` |
| QA P1-1 and code review P2-3 | The precision run is 10 chunk tests plus a mean check, with the bar tightened to 5.7–6.7%. The 2,000-book test keeps 5 ± 1.5. TESTPLAN 0.9 states that the measured size is about 6%, accepted by the owner. | `test_calibration.py` |
| Validator P3-1 | A slow end-to-end null through `shadow_time_stop`: 8 chunks × 500 books, each about 7 s. | `test_v12_slow_e2e_*` |
| Validator P3-5 | **Not done**, for the reasons in Build note 23: it would contradict ADR rule 1 and expose final outcomes to `no_price`. Looks are unaffected. | |

Left for the owner, with TODO items:
- A persisted ledger of decided outcomes and evaluated looks (needs ADR §7).
- Validator P2-2: exclusions select slow resolvers.
- Validator P3-4, P3-6 and P3-7.
- Security P3-1, P3-2 and P3-4 are not built. P3-4 is eased for free, because decided entries are no
  longer fetched.
- The residual: one plausible but wrong close mid-series still grades a gap.

### Mutation checks (fix loop)
Each mutant was planted alone, the named tests were run, and the original restored. All are killed:

| Mutant | Killed by |
|---|---|
| Drop keep-previous-series | `test_a_failed_request_keeps_the_series_already_held` |
| Drop the memo (not handed back / not stored / ignored by the pure function / dropped with a split) | `test_a_failed_day_after_a_good_one_changes_nothing`, `test_one_request_per_symbol…[bars]`, `test_a_decided_outcome_is_kept_not_recomputed`, `test_rewritten_closes_do_not_regrade_a_decided_entry` |
| Memo and kept series both dropped | `test_mv_s1a_failed_fetches_leave_look_1_as_evaluated[all]` |
| `no_price` memoised | `test_a_decided_outcome_is_kept_not_recomputed` |
| Use the newest bar | `test_v6_a_newest_bar_stamped_mid_session_decides_nothing`, `test_mv_b3_…` |
| Future stamps kept | `test_a_bar_stamped_after_now_is_ignored` (survived at first, because the one future bar was also the newest; now two) |
| Split guard removed; replaced by a [0.5, 2] ratio | `test_a_rescaled_history_is_not_this_entrys_price[2:1 split]` |
| Closes ≤ 0 kept; per-row validation removed | `test_a_close_at_or_below_zero…[0.0]`, `test_one_malformed_bar_drops_that_bar_not_the_readout` |
| Timestamp clamp removed | `test_an_impossible_date_reads_as_n_a_not_as_a_failure` (survived at first behind the `OSError` catch, which showed "unreadable"; the test now requires a normal render) |
| Render before the existing grade | `test_the_existing_grade_is_refreshed_before_the_shadow` |
| Caveat without costs | `test_domain_p1_the_crossing_says_what_it_does_not_show[before costs…]` |
| QA M11, M12, M13, M14, C03, C06, U01, U04, U05, U08, U09 | `test_qa_m11_…` … `test_qa_u09_…`, and the `[85-6mo]` range case. None was equivalent. |
| Validator: naive OLS SE | `test_the_gate_is_the_hc3_slope_of_the_evidence_script`. It survives V-12, as the validator found, but this test kills it. |

### Runs (final tree before the docs commit)
```
./run-tests.sh tests/ -q -p no:cacheprovider                          exit 0
2291 passed, 3 skipped, 52 deselected in 111.76s
QT_QPA_PLATFORM=offscreen ./run-tests.sh tests/ -q -p no:cacheprovider exit 0
2291 passed, 3 skipped, 52 deselected in 94.53s
TEST_BUDGET_S=600 ./run-tests.sh tests/ -m slow -q                    exit 0
22 passed, 2324 deselected in 86.58s (longest test 8.7 s)
```
- The suite collects 2,294 tests: 2,291 passed plus 3 skipped. That count is in TESTPLAN, TESTING,
  README and `testplan.html`.
- The 52 deselected tests are 30 network and 22 slow.
- Lint: nothing new in the changed files. The remaining findings were already there at HEAD (5 in
  `ui/app.py`, 2 in `core.py`).

V-12 numbers in this loop:
- **Precision null:** 6.19% over 20,000 books, inside the new 5.7–6.7% bar.
- **End to end through `shadow_time_stop`:** 6.095% over 40,000 books (seeds 9000–9039, SE 0.12 pt,
  every look evaluated). The test's own 4,000 books (seeds 9100–9107) gave 5.43%, within its ±3 SE
  bar of 4.96–7.23%.
- The validator's `mv/s1_instability.py` on this tree:
  - Part A (the pure function with no bars and no memo) still shows the drop. That is expected: the
    protection is in the engine, and the s1-A engine test passes.
  - B1, B2 and B3 now all give `wait_price`.
  - Part C now ends in `wait_price` (the split guard), so the script's `r` format crashes on None.

### Not verified
Live Yahoo stamps for US equities during the session, Yahoo's split adjustment itself, and a restart
during an outage. The memo is per process, so a restart still decides again.
