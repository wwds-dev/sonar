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
