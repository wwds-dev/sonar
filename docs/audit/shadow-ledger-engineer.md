# Engineer report: the write-once look ledger (spec `shadow-ledger.md`, ADR 0002 Amendment 1)

- **Role:** engineer, Build phase, 2026-10-12. Branch `claude/sleepy-haslett-7b11c2`, worktree
  `cool-leavitt-1b6b6d`. Spec approved by the owner (G1 yes, G2 (a), G3 manual).
- **Playbook:** `docs/playbooks/engineer.md` is `status: baseline` (last-reviewed 2026-10-10). By
  the AGENTS.md rule it is stale, and it added nothing beyond AGENTS.md.
- **Pre-registration:** synthetic books and a scratch `SONAR_DATA` only. Nothing under
  `~/Library/Application Support/SONAR`, no `data/portfolio.json` and no copy of the real book was
  read. No real time-stop outcome was computed or printed.
- **Choices the spec left open:** see "Build notes (shadow ledger)" at the end of the spec.

## What changed

### `sonar/calibration.py` (pure)
- Constants (:273-288): `SHADOW_PRICE_GRACE_DAYS` 7 → 28, plus `SHADOW_PRICE_TRIES = 3`,
  `SHADOW_TRY_AFTER_DAYS = 7`, `SHADOW_VERTEX_K_MAX = 12`, `SHADOW_RULES = 1`. `SHADOW_EXCLUDED`
  gains `no_risk`. New: `SHADOW_FILLED` (`left`, `no_price`), `SHADOW_FINAL` and `SHADOW_SOURCES`
  (:309-318).
- `_shadow_risk` (:354) gives the signed stop distance d·(entry − stop). `shadow_needs_bars` (:341)
  skips `no_risk`.
- `_hc3_z_at` (:395) is `hc3_z` with the x-only parts worked out once. It uses the same sums in
  the same order, so the results are bit-identical; a test pins this.
- `extreme_z` (:426): all 2^k vertices for k ≤ 12, else the two slope-extreme fills. Each member
  uses its own `r_stop` / `r_target`. Unknown barriers or an undefined vertex give no extremes,
  so the crossing is not robust.
- `_shadow_from_bars` (:482) also returns the source (`book` / `hand` / `gap` / `bar`), `t_bar`
  and `t_cut`.
- `_shadow_entry` (:550):
  - `no_risk` at once on signed distance ≤ 0, source `fill`.
  - Per-member `r_stop` / `r_target`.
  - The 28-day plus 3-day grace, with today's try counted when the symbol was fetched today.
  - Returns `(entry, tries)`.
- `shadow_decided` (:538) now covers `SHADOW_FINAL`.
- `shadow_looks(entries, recorded)` (:621):
  - Honours recorded looks; a recorded crossing closes the design first.
  - Applies the robust rule.
  - Adds `n_filled`, `past_line`, `price_until`, `recorded` and `recorded_at`, and `members`
    only on an evaluated look that is not yet recorded.
- `shadow_time_stop(…, decided, ledger, tries, fetched)` (:719):
  - Ledger entries join `decided` and win over it.
  - Adds `n_no_risk` and `price_tries` to the readout.
  - Ends in `shadow_with_ledger` (:846), which adds `looks`, `mismatches`, `errata` and
    `ledger`.
- The ledger (:861-1130):
  - `LedgerFormatError` and `LedgerIdError`, `ledger_constants` and `ledger_new`.
  - `ledger_parse`: strict, so any error is a whole-file error; NaN and Infinity are refused.
  - `ledger_marker_parse`.
  - `ledger_merge`: write-once; only `price_tries` changes.
  - `ledger_check`: `constants` / `members` / `z`, not a re-grade.
  - `ledger_errata`: read-only.

### `sonar/core.py` (engine)
- `SHADOW_LEDGER_FILE`, `SHADOW_LEDGER_RETRY_S = 600`, `SHADOW_LEDGER_MAX_BYTES` (:143-150).
  Ledger state on `Live` (:252-262), reset in `_take_the_book` (:1319-1325).
- `_shadow_pass` (:572), in this order:
  1. Opens the ledger.
  2. Fetches only for ids that are in neither the memo nor the ledger.
  3. Passes `fetched` (the symbols asked for this UTC day) and the tries (memo ∪ ledger).
  4. Computes, then merges and writes.
  5. Publishes only after the write. Followers and read-only engines return before any of this.
- `_shadow_ledger_open` (:639):
  - Loads once per tenure; while the error lasts, re-reads on `read` / `missing`, never writing.
  - Starts the ledger marker first (`_shadow_ledger_mark`, :701, under `book.lock`).
  - Applies the 10-minute rule.
  - Adopts a file that has no marker.
  - A wrong id is `LedgerIdError`.
- `_shadow_ledger_record` (:716):
  - Merges. Then `daily_backup`, then `write_atomically` (JSON, `indent=1`, `allow_nan=False`).
  - On success, the looks are worked out again against the new record.
  - On failure, `ledger.error = "write"` and the readout's looks stay unrecorded.

### `sonar/portfolio.py`
- `Portfolio.shadow_ledger` (:207). Loaded as it is (:223) and saved only when present
  (:235-236). Older files load with `None`, and a save without a marker adds no key.

### `ui/app.py`
- New `SHADOW_WORDS` keys: `SH_LOOK_WAITING_UNTIL`, `SH_LOOK_NOT_ROBUST`, `SH_LOOK_UNRECORDED`,
  `SH_EXTREMES`, `SH_ROW_PAST_LOOK_NOT_ROBUST`, `SH_RECORD`, `SH_MISMATCH`, `SH_WHY_MEMBERS`,
  `SH_WHY_Z`, `SH_MISMATCH_CONSTANTS`, `SH_LEDGER_READ`, `SH_LEDGER_MISSING`, `SH_LEDGER_WRITE`
  and `SH_ERRATUM` (:521-659).
- Changed `SHADOW_WORDS` keys: the three result lines carry "recorded {date}" first, and
  `SH_ROW_LEFT_OUT` gains a `no_risk` part.
- `_sh_shown` (:844) gates every result on `recorded is True`, and not while the ledger is
  `read` or `missing`.
- `_sh_ledger_lines` (:945) prints errors, mismatches and errata through `_clean(…, 80)`.
- `_sh_look_status` (:976) handles the unrecorded and not-robust lines and the "until" date.
- `_sh_rows` (:1068) adds the extremes row and the not-robust past-look row.
- The record line goes at the end of the note.

### Tests
- **New** `tests/test_shadow_ledger.py` (L-1 to L-13 and L-15 to L-18, plus parse, marker,
  backup and UI-line tests; 84 tests).
- **New** L-14 in `tests/test_calibration.py` (:1299-1381): 8 slow chunks and a slow mean test.
- **`tests/conftest.py`:** `LIVE_DATA`, `refuse_live_data`, `use_scratch_data`, the
  `scratch_data` fixture, and `isolated_state` refusing a `tmp_path` under the live directory.
- **Existing tests updated to the approved spec** (none weakened; each now asserts the new rule):

  | Test | Old behaviour asserted | Now asserts |
  |---|---|---|
  | `test_calibration.py`: `test_a_rescaled_history_…`, `test_qa_r3_m20_…`, `test_qa_r4_m21_m22_…` | `no_price` at t_T + 8 days | `no_price` once 28 days and 3 tried days have both passed (`PAST_GRACE`, `TRIED`; `one()` takes `tries`) |
  | `test_calibration.py`: `test_v10_…` (renamed `…waits_out_the_grace…`) | `no_price` at t_T + 8 days | still waiting at t_T + 8 days; `no_price` once both limits have passed |
  | `test_calibration.py`: `test_a_plan_with_no_stop_distance_has_no_r` | `no_price` | `no_risk` |
  | `test_calibration.py`: `test_v14_…` | grace pinned at 7 | grace pinned at 28 |
  | `test_shadow_engine.py`: `test_one_request_per_symbol_…` | `no_price` 12 days past T | `wait_price`, with 2 tried days counted |
  | `test_shadow_engine.py`: `test_the_memo_lives_in_memory_…` | no `shadow*` file in the data directory | the only one is `shadow_ledger.json` |
  | `test_shadow_engine.py`: `test_r2_a_pass_writes_nothing_at_all` (renamed `…writes_the_ledger_and_its_marker_and_nothing_else`) | no file touched | only the ledger and the marker are written, the book's other contents are unchanged, and a second pass with nothing new writes nothing at all |
  | `test_shadow_engine.py`: `test_the_pass_reads_copies_and_writes_nothing` | spy accepted 5 arguments | spy passes the new positional arguments through (no assertion changed) |
  | `test_shadow_ui.py`: the `look()` / `readout()` fixtures | evaluated looks were results | evaluated looks in the fixtures are recorded (`recorded_at`) and the readout carries `ledger`; `test_u4` expects "Look 1 of 3, recorded {date}, …" |

- **Suite size** in `TESTPLAN.md`, `TESTING.md` and `README.md`: 2,399 → 2,483. Kept equal to
  the collected suite, which `test_the_documented_suite_size_is_the_collected_one` enforces.

## Results

All runs used `PYTHON=$PWD/.venv/bin/python ./run-tests.sh …`, output to the session scratchpad
(`build/*.txt`). The machine load average was 110–140 throughout.

| Run | Tree | Exit | Result |
|---|---|---|---|
| Baseline, native | HEAD `bdd8a2b` before any change | 0 | 2,396 passed, 3 skipped, 52 deselected |
| Native, final | `eae1ecf` | **0** | 2,480 passed, 3 skipped, 61 deselected (2:01) |
| Offscreen (`QT_QPA_PLATFORM=offscreen`), final | `eae1ecf` | **0** | 2,480 passed, 3 skipped, 61 deselected (4:44) |
| Slow (`-m slow`): `test_calibration`, `test_shadow_ledger`, `test_shadow_engine`, `test_shadow_ui` | `eae1ecf` | 0 | 31 passed (V-12 slow, end-to-end slow, L-14), 4:06 |

Along the way:
- **The first offscreen run was killed by the watchdog at the default 300 s budget** (exit 137, at
  about 92%; load about 140). Every later run used `TEST_BUDGET_S=900`, as the brief allows.
- **The first native run failed one test**, `test_the_documented_suite_size_is_the_collected_one`,
  because the new tests changed the suite size. The documents and `static/testplan.html`
  (`scripts/build_testplan.py`) were updated.
- **The second native run failed `test_two_processes.py::…[agent killed]` once** (a follower
  still `read_only` under load). It passed in the same round's offscreen run, twice on its own
  (25 passed ×2), and in the final run. It is load flakiness under the TESTING.md two-run rule,
  not this change.
- **Self-review fix (`eae1ecf`):** `math.isfinite` raises `OverflowError` on an integer too large
  for a float. A hand-edited ledger or marker holding one would have failed the pass instead of
  reading as "read". `_is_num` now refuses it, and two parse cases pin this.
- **ruff** on every changed file: no new findings (see below).

## Mutation check (new logic)
One mutant at a time was applied to the source and the matching tests were run; the file was
restored after each (`cmp` against a saved copy). Script and log are in the session scratchpad
(`build/mut/run.py`, `result.txt`). All 22 mutants were killed:

| Mutant | Killed by |
|---|---|
| ledger not read (ledger entries and tries ignored) | L-1, L-3 |
| recomputing over the record (records ignored) | L-2, L-5, L-17 |
| entries not persisted | L-3 |
| overwrite on merge: entries / looks | L-4 / L-4 |
| overwrite of a bad file (a fresh ledger on a parse error) | L-6 |
| unrecorded result shown (UI ignores `recorded`) | L-6, L-7, L-15 |
| publish blocked on a failed write | L-7 |
| a follower writes (guard removed) | L-8 |
| grace left at 7 / attempts ignored / tries not kept | L-9 / L-9, L-10 / L-10 |
| corners at −1 / +rr; one corner only | L-11 |
| the rule changes the no-exclusion case | L-12 |
| `abs()` risk; the old `no_price` filing | L-13 |
| robust rule dropped (slow) | L-14 (size 117 > 115 on the same books) |
| silent fresh start on a missing file | L-15 |
| erratum rewrites `crossed` | L-16 |
| `no_price` written as final (cross-look leak) | L-17 |
| live-directory guard dropped | L-18 |

The first L-18 mutant removed only the textual check and survived, because the resolved-path
check still refused. The whole-guard mutant was killed.

## Not done, and not verified
- No CHANGELOG or VERSION change; that belongs to the Document and Release phases.
  `static/docs.html` (the manual) does not describe the ledger yet.
- No app build, install or `launchctl`. The holder was not run against a live agent, and no
  screenshot of the new lines was taken: the UI was checked through `shadow_texts` and the
  existing window tests only.
- No ux-designer review of the new strings. Expert wording uses "record", not the spec's "ledger"
  (Build note 1).
- The Secure phase is required: a new file write under `SONAR_DATA`, a new key in
  `portfolio.json`, and parsing of a hand-editable file.
- The validator's optional SHA-256 of each look in CHANGELOG is left to the Document phase of
  each look, as the spec says.
- Coverage was not measured for this change (`coverage run …` was not run).
- `ruff` is not installed in `.venv`. It was run from uv's offline cache (`uvx --offline ruff`
  0.17.0): no new findings in the changed files. The 2 findings in `core.py`, 1 in `portfolio.py`
  and 5 in `ui/app.py` are older, at the same count as HEAD.

## Fix loop 1 (2026-10-13)
Round-1 findings: `shadow-ledger-code-reviewer.md` (CR), `shadow-ledger-security-engineer.md` (SEC),
`shadow-ledger-domain-finance-r2.md` (domain r2). Code and tests are in commit `49e6da4`; docs
come in the commit after it. All tests named below are in `tests/test_shadow_ledger.py` unless
another file is given.

| # | Finding | Fix (file:line at `49e6da4`) | Test |
|---|---|---|---|
| 1 | CR P1-1: a foreign ledger with no marker is adopted | With no marker in the book, the file is taken only if `calibration.ledger_belongs` (:1112) holds; otherwise `("read", "LedgerIdError")`, and nothing is written (`core.py:774`). The read line adds `SH_LEDGER_FOREIGN` (`ui/app.py:680`) | `test_cr_p1_1_another_books_ledger_is_never_adopted[kept,removed]`, `test_cr_p1_1_a_marker_less_ledger_of_this_book_is_adopted` |
| 2 | CR P2-1, SEC P2-2: a dropped marker means a fresh start | Anchor = marker, or the sidecar `shadow_ledger.id` (`core.py:155`, `:792`, `:812`), or any local or off-site backup (`:804`). Any anchor with no file is `missing`. `Portfolio` keeps unknown top-level keys (`portfolio.py:188`, `:232`, `:240`) | `test_cr_p2_1_an_older_build_drops_the_marker_then_the_file_goes_missing`, `…a_backup_alone_is_an_anchor`, `…an_off_site_backup_is_an_anchor`, `test_sec_p2_2_an_unknown_top_level_key_survives_a_save` |
| 3 | SEC P2-1: an erratum added mid-tenure is overwritten | `_shadow_ledger_refresh` (`core.py:841`) compares inode, size and mtime_ns before each pass and each write. With the same id it re-reads and takes over the errata; otherwise `read` or `missing`, with no write | `test_sec_p2_1_an_erratum_added_while_the_holder_runs_survives_its_next_write`, `test_sec_p2_1_a_file_replaced_under_the_holder_is_never_written_over[another id,unreadable,deleted]` |
| 4 | SEC P2-3, CR P3-3: the writer writes what the reader refuses | `ledger_merge(…, refused)` (`calibration.py:1121`) checks each new record and leaves out and counts failures (`ledger.refused`, `SH_LEDGER_REFUSED`). `_shadow_ledger_write` (`core.py:871`) parses the text back before `write_atomically` | `test_sec_p2_3_…[65-character symbol, lowercase direction, NaN rr]`, `test_cr_p3_3_what_is_written_is_first_read_back` |
| 5 | CR P3-1: writes after stop or a lock handover | `_may_write_shadow` (`core.py:689`) is checked before the anchors, before the file and before publishing | `test_cr_p3_1_…[stop, lock lost]` |
| 6 | CR P3-2: crash window between marker and file | The empty file is written right after the anchors in `_shadow_ledger_open` (`core.py:700`). The 10-minute rule stays, now only for an anchor that counts nothing | `test_cr_p3_2_the_empty_file_is_written_with_the_anchors`, `test_l15_a_young_marker_…[±1 s]`, `test_l15_a_young_marker_that_counts_records_is_missing_not_remade` |
| 7 | CR P3-4: a constants key change makes the file unreadable | `_check_constants` (`calibration.py:1038`) type-checks a mapping; a key change shows as a `constants` mismatch | `test_cr_p3_4_…[added, removed]` |
| 8 | CR P3-5: the warning line shows for an unrecorded look | `_sh_warnings` uses `_sh_shown` (`ui/app.py:1205`) | `test_cr_p3_5_no_left_out_warning_for_a_look_that_is_not_a_result` |
| 9 | CR P3-6, SEC P3-5: environment leaks into tests | `isolated_state` clears `SONAR_BACKUP_DIR` and `SONAR_DATA` (`tests/conftest.py:205-209`) | `test_cr_p3_6_isolated_state_clears_the_data_and_backup_variables` |
| 10 | SEC P3-1: errata cost and screen size unbounded | Errata indexed once (`calibration.py:1213`) and capped at 1,000 (`:882`). Members are sized by the look. The window shows 5 errata plus a count, and at most 3 mismatches and looks | `test_sec_p3_1_errata_and_members_are_bounded` |
| 11 | SEC P3-2: the read follows symlinks and special files | `_read_regular` (`core.py:158`): `O_NOFOLLOW \| O_NONBLOCK`, `S_ISREG` only, at most limit + 1 bytes read | `test_sec_p3_2_…[symlink, fifo, directory]` |
| 12 | SEC P3-3: a restored backup drops recorded looks | Marker and sidecar carry `looks` / `entries` counts (`calibration.ledger_anchor`, :926), updated after each write. A file with fewer is `LedgerBehindError` (:898), with the line `SH_LEDGER_BEHIND` | `test_sec_p3_3_a_restored_copy_behind_the_anchors_is_refused` |
| 13 | SEC P3-4: the guard is case-sensitive | `_folded` (NFD + casefold) in `refuse_live_data` (`tests/conftest.py:53-80`) | `test_l18_sec_p3_4_any_letter_case_…` (2 cases) |
| 14 | SEC P3-7: a recorded verdict is trusted as written | `_check_look` (`calibration.py:996`) enforces n = `SHADOW_LOOKS[k-1]`, crossed ⇒ \|z\| ≥ boundary and robust when filled, `design_closed` false. `_check_looks_order` (:1029) allows no look after a crossing. The UI requires `crossed is True` (`ui/app.py:1057`) | `test_sec_p3_7_a_recorded_verdict_must_follow_from_its_figures` (7 cases), `test_sec_p3_7_only_a_crossed_that_is_true_is_a_crossing` |
| 15 | Domain r2 P2-1, P2-2, P3-1, P3-2, P3-3 | `SH_EXTREMES` (:566), `SH_ERRATUM` with look(s) and corrected R (:702), `SH_LOOK_BLOCKED` (:562), `SH_CAVEAT_NOT_ROBUST` (:549), `SH_LOOK_NOT_ROBUST_NA` and `SH_ROW_PAST_LOOK_NA` (:541). Domain P3-4 not taken, as instructed | `test_the_not_robust_look_line_and_the_extremes`, `test_l16_…` (exact erratum text), `test_l6_…` (blocked line), `test_domain_r2_p3_3_…` |
| 16 | CR P3-7: Build note 14 is wrong | Corrected in the spec; fix loop 1 is recorded as Build note 16 | — |
| — | SEC P3-6: no fsync before rename | Deferred to `TODO.md` (P3 security), as instructed | — |

**Probes:**
- The code reviewer's probes, rerun against the fix:
  - The foreign ledger is now `read` / `LedgerIdError`.
  - "Marker dropped, then file lost" is now `missing`.
  - The blocked line says "not shown as a result while the record cannot be used", and no
    left-out warning appears.
  - The "stop" probe still finds a marker and a file. They are made when the record is opened,
    before the fetch it interrupts (CR P3-2). Nothing after the stop is written or published
    (`test_cr_p3_1`).
- The security probes were not rerun as written: they need the repo's conftest fixtures. Each
  scenario is a test above instead.

**Existing tests changed in this loop:**
- L-1 and L-15: the readout's `ledger` now carries `refused: 0`.
- L-6: the blocked line's wording (domain r2 P3-1).
- L-15 young marker: rebuilt as a crash after the anchors, ±1 s around 600 s. The old version
  deleted a file holding records, and that is `missing` under SEC P3-3.
- `test_a_ledger_with_no_marker_is_taken_as_this_books`: the marker now includes the counts.
- Backup test: the day's copy is the empty file written at creation.
- L-16: the exact erratum wording.
- Marker parse: the counts default to 0.
- `test_the_not_robust_look_line_and_the_extremes`: the new extremes and caveat wording.
- L-4: random looks now have the size their key says, as the reader requires.
- L-17: also asserts that merging records nothing for the `no_price` member and refuses nothing.
- `test_shadow_engine.py`: the sidecar and the day's backup are now among the shadow files.

**Mutation check (fix loop 1):**
- 18 new mutants, all killed (scratchpad `build/mut/run2.py`, `result2.txt`).
- "Sidecar ignored" first survived: a backup also anchored that case. The test now removes the
  backups, so the sidecar alone has to anchor the record, and the mutant is killed.
- The 22 original mutants were rerun after updating 4 patterns for the new code. All are killed.
- The original L-17 mutant (`no_price` written as final) is also stopped by the merge's own
  check, which refuses it. L-17 now asserts that nothing is refused, so the mutant is killed.

**Results on `49e6da4`.** Every run used `TEST_BUDGET_S=900`; output is in the session
scratchpad as `build/fl1-*.txt`. The load average was about 150.

| Run | Exit | Result |
|---|---|---|
| Native | **0** | 2,520 passed, 3 skipped, 61 deselected (2:38) |
| Offscreen (`QT_QPA_PLATFORM=offscreen`) | **0** | 2,520 passed, 3 skipped, 61 deselected (4:01) |
| Slow (`-m slow`) over `test_calibration`, `test_shadow_ledger`, `test_shadow_engine` and `test_shadow_ui` | 0 | 31 passed (V-12 slow, end-to-end slow, L-14), 4:12 |

The suite size is 2,523 (`TESTPLAN.md`, `TESTING.md`, `README.md`, `static/testplan.html`).
ruff found nothing new in the changed files: `core.py` has 2 findings, `portfolio.py` 1 and
`ui/app.py` 5, the same counts as before the loop.

## Fix loop 2 (2026-10-13)
Inputs: `shadow-ledger-code-reviewer-r2.md` (CR2) and `shadow-ledger-qa-engineer.md` (QA), both on
HEAD `4ada4d1`. Branch `shadow-ledger-fl2` from `4ada4d1`, in an isolated worktree. Code and tests
are in `c09819f`, `e76df3d` and `b4b6484`; docs in the commit after them. Choices are in spec Build note 17.
All tests named below are in `tests/test_shadow_ledger.py` unless another file is given. Playbook
still `status: baseline` (stale). Synthetic books and pytest scratch directories only.

| # | Finding | Fix (file:line at `b4b6484`) | Test |
|---|---|---|---|
| 1 | CR2 P2-N1: the newest backup is usually "behind" | Anchors count looks only (`calibration.ledger_anchor` :933; behind check `core.py` :809; marker parse drops a legacy `entries`). After a write that adds a look, `paths.snapshot` (:107) copies the file to `….bak.<date>.look<k>.<id8>` here and off-site, before the anchors move (`core.py` :973-983). `SH_LEDGER_BEHIND` and `SH_LEDGER_RESTORE` say "the newest backup copy … latest date in its name, here or off-site" | `test_cr2_p2_n1_lost_on_a_day_that_added_entries_the_newest_copy_restores`, `test_cr2_p2_n1_lost_after_a_look_the_newest_copy_here_and_off_site_matches` |
| 2 | CR2 P2-N2: a reset cannot start a new record without deleting backups | Retire step: `shadow_ledger.retired.<id>.json` (`core.py` :156-163, `_shadow_retired` :851) retires an id its own JSON holds. Retired marker and sidecar are dropped (:752-754); backups are attributed by their `ledger_id` (`_shadow_ledger_backups` :831, `calibration.ledger_id_of` :1143). A live file with a retired id is `LedgerRetiredError` (:795-798, `SH_LEDGER_RETIRED`). "Missing" carries its anchor as the reason; the UI says "this book" only for `marker` (`ui/app.py` :1045-1053, `SH_LEDGER_MISSING_FOLDER`). Steps named in `SH_LEDGER_FOREIGN`, `SH_LEDGER_RESTORE`, the README reset paragraph and the spec's Failure modes table (rows for sidecar, backups, behind, another book's file, retired) | `test_cr2_p2_n2_a_deliberate_reset_retires_the_old_record_and_starts_a_new_one` (end to end), `…retiring_without_a_reset_…`, `…a_retirement_frees_only_the_id_it_holds[3]`, `…a_copy_of_a_retired_record_left_in_place_is_never_used`, `…missing_says_this_book_only_when_the_book_says_so` |
| 3 | CR2 P3-N1: merge and reader use different constants | `_file_boundary`, `_file_looks` (`calibration.py` :1006-1019) feed `_check_look` in `ledger_parse` and `ledger_merge` | `test_cr2_p3_n1_the_merge_judges_a_look_by_the_files_own_line` (boundary probe), `test_cr2_p3_n1_changed_look_sizes_are_a_constants_mismatch_not_unreadable` (looks probe), `test_cr2_p3_n1_n3_a_holder_on_a_stricter_file_refuses_the_look_and_says_so` |
| 4 | CR2 P3-N2: a failed anchor save is not retried | `_ledger_needs_anchor`, set from every anchor save after a read or write and retried at the start of each pass (`core.py` :738-741, :817, :983; reset in `_take_the_book`) | `test_cr2_p3_n2_a_failed_anchor_save_after_adoption_is_tried_again` |
| 5 | CR2 P3-N3: copy nits | `ledger.refused` (results) and `ledger.refused_looks` (`ledger_merge(…, refused_looks)`); `SH_LEDGER_REFUSED_ONE` / `_REFUSED` / `_REFUSED_LOOK_ONE` / `_REFUSED_LOOKS`; expert `SH_ERRATUM` uses `{where}`: "no look", "look 1", "looks 1 and 2" | `test_cr2_p3_n3_…`; pinned `test_sec_p2_3_…` now expects "1 result could not be recorded" |
| 6 | QA P2-1: `price_tries` grows past the reader's 400 days | `ledger_merge` adds a day only while the entry is `wait_price`, or while fewer than 3 are recorded (`calibration.py` :1222-1237). Build note 5's "days are only added" still holds | `test_qa_p2_1_tried_days_stop_growing_once_no_longer_waiting` (450 days; the QA probe's 402) |
| 7 | QA P2-2: S4 gating unpinned | test only | `test_qa_p2_2_q57_…`, `test_qa_p2_2_q61_q65_…` |
| 8 | QA P2-3: a foreign record with entries only | test only | `test_qa_p2_3_q45_…` |
| 9 | QA P2-4: "same side" | No code change: `shadow_looks` (:683-685) and `_check_look` already use the same rule. A natural cohort (8 fills at ±6 R) gives z 3.92, z_lo −2.66, z_hi 5.24: not crossed, no look closed, and the reader refuses it as crossed | `test_qa_p2_4_q21_…` |
| 10 | QA P3 | tests: Q18, Q26, Q30, Q29, Q08/Q10, Q12 (the check already existed), Q38/Q43, Q37, Q39/Q40 (adapted: fewer looks with every entry is behind; fewer entries with every look is read), Q51, Q48, Q64. `test_shadow_engine.py` `_today(monkeypatch)` pins `paths._dt` to the date of the tests' NOW | `test_qa_p3_*` |

**Existing tests changed in this loop** (each to the new rule, none loosened):
- L-1 and L-15: the readout's `ledger` carries `refused_looks: 0`; L-15's reason is `marker` and
  its line names the restore and retire steps.
- `test_l15_a_young_marker_that_counts_records_…` became `…counts_a_look_…`: entries are no longer
  counted, so the anchor that must not be remade is one that counts a look.
- Marker shape without `entries`: `test_a_ledger_with_no_marker_…`, `test_cr_p1_1_a_marker_less_…`,
  `test_the_marker_is_checked_too`.
- `test_cr_p1_1_another_books_ledger_…`: the foreign line's new wording (the retire step).
- `test_sec_p2_3_…`: "1 result could not be recorded".
- `test_sec_p3_3_…`: picks the day's backup by name (a look copy now sits beside it) and expects
  the new behind wording.
- `test_shadow_engine.py`: the two tests that list the day's backup pin its date.

**Mutation check.** In a scratch copy of HEAD (`git archive` plus the nested repos), never the
worktree; each mutant applied by exact text, the four shadow test files run with `-x`, and every
file restored and checked byte-equal. Scripts and logs: scratchpad `fl2/mut.py`, `mut_log.txt`,
`mut_log2.txt`, `mut_k.py`, `mut_k_log.txt`.
- 22 mutants of this loop's code (F01-F22) and QA's 18 surviving mutants re-applied to today's
  code (Q08, Q10, Q12, Q18, Q21, Q26, Q29, Q30, Q37, Q38, Q43, Q45, Q48, Q51, Q57, Q61, Q64, Q65):
  **40 of 40 killed**, after one fix.
- **F16 (the reader on today's look sizes) first survived.** `_check_look`'s defaults were bound
  when the module loaded, so patching `calibration.SHADOW_LOOKS` in the looks probe changed
  nothing. The defaults are now read at the call (`b4b6484`); F16 is killed by the looks probe and
  F15 still by the boundary probe.
- Where `-x` stopped at an earlier test, the mutant was run again against the test written for it
  alone (`-k`): F01 (anchors count entries) by the "lost on a day that added entries" test, F03 (no
  id in the copy's name) by the end-to-end reset test (A's same-day look copy would be overwritten),
  F14 by the "missing says this book" test, F19 by the P3-N3 test. All killed.
- Q39 and Q40 (each half of "behind") are adapted rather than re-run: the entries half no longer
  exists, so F01 puts it back (killed) and F06 removes the looks half (killed).

**Runs** (`TEST_BUDGET_S=900`; output in scratchpad `fl2/`; load average 150-230):

| Run | Tree | Exit | Result |
|---|---|---|---|
| Native | `e76df3d` (before the `_check_look` fix) | 0 | 2,555 passed, 3 skipped, 61 deselected (2:06) |
| Offscreen (`QT_QPA_PLATFORM=offscreen`) | `b4b6484` | **0** | 2,555 passed, 3 skipped, 61 deselected (4:01) |
| Native | `b4b6484` | **0** | 2,555 passed, 3 skipped, 61 deselected (2:17) |
| Slow (`-m slow`) over `test_shadow_ledger`, `_engine`, `_ui`, `test_calibration` | `b4b6484` | 0 | 31 passed (3:40) |

The suite size is 2,558 (`TESTPLAN.md`, `TESTING.md`, `README.md`, `static/testplan.html`), up
from 2,523. No flake in any run. The offscreen run prints the known `StubLive._stop` watchdog
noise from `test_server.py` (QA P3 (8), pre-existing). ruff (`uvx --offline ruff` 0.17.0) on
every changed code file: `core.py` 2 and `ui/app.py` 5 findings, the same as before; `paths.py`,
`calibration.py` and the two test files none.

**Not done, and not verified.**
- No CHANGELOG, VERSION or manual change (Document phase). No build, install, push or `launchctl`.
- The retire step was tested on scratch directories only; nobody has walked through it by hand.
- The look copy is swallowed on failure, like the daily backup: if it fails, the newest copy is
  "behind" until the next day's backup. Not surfaced on screen.
- After a reset the old record's backups rotate out over the following 7 days locally and 30
  off-site, as every backup does; the retired file is the copy kept. A reset on the same day as
  an old daily backup costs the new record that day's daily backup (the name is taken).
- `docs/company/activity.jsonl` got a `build start` line in this worktree; it is not committed
  (shared log, concurrent sessions).

## Fix loop 3 (2026-10-13)
Inputs: `shadow-ledger-domain-finance-r3.md` (D3) and `shadow-ledger-code-reviewer-r3.md` (CR3), at
`a08e796`. Branch `shadow-ledger-fl3` from `a08e796`, in an isolated worktree. Code and tests are in
`71a5f5e` and `7a34499`; documents in `2401d80` and the commit after this report. Choices are in spec
Build note 18. Playbook still `status: baseline` (stale). Synthetic books and pytest scratch
directories only.

| # | Finding | Fix (file:line at `7a34499`) | Test (`tests/test_shadow_ledger.py` unless named) |
|---|---|---|---|
| 1 | D3 P1-1: retiring re-tests the same book with no trace (G3) | A retirement is not honoured while `portfolio.json`'s marker names the id (`core.py` :759-764); the ten-minute rule never remakes a retired id (:785). `_shadow_retired` (:866) now returns id → `st_ctime`; `ledger.retired` / `retired_first` count the retired records other than the one in use (:1025-1033). `SH_RECORD_RETIRED_ONE` / `SH_RECORD_RETIRED` (`ui/app.py` :665, :1056-1064). `SH_LEDGER_RESTORE_RETIRE` (:733) follows only a non-`marker` "missing" (:1090-1094). README, CHANGELOG, manual §10, spec rows and Known limit 9 | `test_cr3_g3_retiring_without_a_reset_is_not_honoured[a day on, inside ten minutes]`, `test_cr3_domain_p1_1_retired_records_are_always_disclosed`, the end-to-end reset test (disclosure after restart), `test_cr2_p2_n2_a_copy_of_a_retired_record_left_in_place_is_never_used[after a reset, book not reset]`, L-15 (no retire sentence) |
| 2 | D3 P3-1 "counted but not recorded" | "could not be written to the record … It is not in the record, so a look that uses it cannot be fully checked against the record." / "not in record" | `test_sec_p2_3_…`, `test_cr2_p3_n3_…`, `test_cr2_p3_n1_n3_…` (wording) |
| 3 | D3 P3-2 a hidden erratum may matter | Errata touching a recorded look first, then newest (`ui/app.py` :1118-1146); `SH_ERRATA_MORE` "{n} more …; {m} of them touch a recorded look." / "+{n} errata ({m} on looks)" | `test_cr3_errata_on_looks_first_then_newest_and_how_many_are_hidden`, `test_sec_p3_1_…` |
| 4 | D3 P3-3 "corrected R n/a" | `SH_ERRATUM_R` / `SH_ERRATUM_NO_R` "it has no usable R" / "R → none" | same test |
| 5 | CR3 P3-1 two files carry the look's date | Restore and behind lines: "the last one by name … (on a look's day, the one with .look in its name; after a reset, see the README)"; spec row "unless that copy failed" | L-15, `test_sec_p3_3_…` |
| 6 | CR3 P3-2 reset day: no copy of the new record | `_shadow_ledger_copy` (`core.py` :948) after a new record's first successful write, tag `created` (sorts before `look`; the suggested `start` would sort after it). README: the newest copy ending in the id's first 8 characters | `test_cr3_p3_2_after_a_reset_the_new_records_first_copy_restores_it`, `…the_first_copy_waits_for_the_first_write_that_succeeds`, `…the_look_copy_is_the_last_by_name_on_a_day_with_both`; `test_shadow_engine.py` file lists |
| 7 | CR3 P3-3 "this folder's" for one pass | `_shadow_missing_reason` (`core.py` :958) in the refresh | `test_cr3_p3_3_a_file_lost_under_the_holder_is_this_books_at_once` |
| 8 | CR3 P3-4 "same closes" | Docstrings (`calibration.py` LedgerBehindError, `ledger_anchor`), core comment, spec Build note 17 and the "behind" row: "decided again from the closes then available; not part of any recorded look" | — |
| 9 | CR3 P3-5 "looks 1 and 2 and 3" | "1, 2 and 3" (`ui/app.py` :1131-1133) | the errata test |
| 10 | CR3 P3-6 race in `test_two_processes` | `_wait(lambda: not live.read_only)` before the assertion | `tests/test_two_processes.py` |

**Existing tests changed in this loop:**
- `test_cr2_p2_n2_retiring_without_a_reset_starts_a_new_record_for_the_same_book` is replaced by
  `test_cr3_g3_retiring_without_a_reset_is_not_honoured`. It asserted a new record for the same
  book; the orchestrator's fix-loop-3 decision (enforcing G3) refuses that, so the test now pins
  the refusal. This is a spec change, not a weakening: the new test asserts more (error, reason,
  no file, marker unchanged, no retire sentence, and the ten-minute case).
- `test_cr2_p2_n2_a_copy_of_a_retired_record_left_in_place_is_never_used` now runs after a reset
  (no marker), where `LedgerRetiredError` still applies, and adds the "book not reset" case, where
  the retirement is ignored.
- L-15: no retire sentence on the "this book" path; restore wording "the last one by name".
- Backup lists include the `created` copy: `test_the_day_is_backed_up_before_its_first_overwrite`,
  `test_cr2_p2_n1_lost_after_a_look_…`, and the two `test_shadow_engine.py` file-list tests.
- Refused wording: `test_sec_p2_3_…`, `test_cr2_p3_n3_…` (its "no look line" check now looks for
  "look(s) could not", since the result line itself mentions "a look"), `test_cr2_p3_n1_n3_…`.
- `test_sec_p3_1_…`: the hidden-errata line with its look count.

**Mutation check.** Scratch copy of `7a34499` (`git archive` plus the nested repos), never the
worktree; scripts and log in scratchpad `fl3/` (`mut3.py`, `mut_log.txt`). **16 of 16 killed**: G01
retirement honoured with the marker; G02 ten-minute rule remakes a retired id; G03 retired records
not in the payload; G04 the record in use counted as retired; G05 disclosure dropped; G06 plural for
one; G07 retire offered on the marker path; G08 no first copy at open; G09 no first copy after a
failed open write; G10 "this folder's" for a file lost under the holder; G11 errata on looks not
first; G12 not newest first; G13 hidden-on-looks count 0; G14 no R shown as n/a; G15 "1 and 2 and 3";
G16 first copy tagged `start` (sorts after the look's). G09 needed a new test
(`…the_first_copy_waits_for_the_first_write_that_succeeds`), written before the run.

**Runs** (`TEST_BUDGET_S=900`, tree `7a34499`; output in scratchpad `fl3/`):

| Run | Exit | Result |
|---|---|---|
| Native | **0** | 2,563 passed, 3 skipped, 61 deselected (2:11) |
| Offscreen (`QT_QPA_PLATFORM=offscreen`) | **0** | 2,563 passed, 3 skipped, 61 deselected (5:40) |
| Slow (`-m slow`) over `test_shadow_ledger`, `_engine`, `_ui`, `test_calibration` | 0 | 31 passed (5:04) |

Suite size 2,566 (was 2,558) in `TESTPLAN.md`, `TESTING.md`, `README.md`, `static/testplan.html`.
No flake. ruff on the changed code files: the same 7 findings as before (`core.py` 2,
`ui/app.py` 5), none in the tests.

**Not done, and not verified.**
- The retired date is `st_ctime`. A rename or a copy sets it, but a later metadata change (a restore
  of the folder, a permission change) moves it. Not tested on a restored folder.
- Removing the marker by hand, or the retired file, still lets someone start over unseen (Known
  limit 2: not tamper-evident). Spec Known limit 9 says so.
- No ADR 0002 note: under the decision the same-book retirement is refused, so none is needed.
  The owner may still want G3's enforcement recorded there.
- Known limit 8 ("nobody has walked through it by hand") is unchanged. Code review r3 scripted the
  README walks (W1-W5); a hand walk has still not been done.
- No build, install, push or `launchctl`. No screenshot of the new lines.
