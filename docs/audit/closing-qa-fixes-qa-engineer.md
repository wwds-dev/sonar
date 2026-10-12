# QA verification: closing-qa-fixes (spec `docs/specs/closing-qa-fixes.md`)

- Date: 2026-10-12. Role: qa-engineer (read-only). Branch `closing-qa-fixes`, HEAD `cc30d56` + uncommitted diff
  (tests/test_engine.py, test_follow.py, test_scoring.py, test_untrusted_text.py, ui/app.py).
- Playbook `docs/playbooks/qa-engineer.md`: `last-reviewed: 2026-10-10`, **`status: baseline`** (stale by the AGENTS.md rule; no radar run yet).
- Method: everything ran in a scratch copy (`rsync -a --exclude .git --exclude __pycache__`), Python
  `/Users/as/Documents/lab/active/sonar/.venv/bin/python`, `-p no:cacheprovider`. Each mutant was written by a
  script, the target test file run in full (no `-x` for the counts below), and the source restored in a `finally`;
  copy sources were diffed against the worktree afterwards (identical). The worktree was not edited except for this file.
- Not done: `log_activity.py` (would write `docs/company/activity.jsonl`; this file is the only write allowed).

## Verdict: PASS

All spec-listed mutants killed by the new tests; one or more fresh mutants per fix also killed. Two fresh
boundary probes survived (expected, low priority, see gaps). Suite green in both modes apart from the
expected doc-count test and two copy-only artefacts.

## 1. Mutation results

| ID | Fix | Mutant (source) | Origin | Result | Killing test |
|---|---|---|---|---|---|
| 1a | 1 | engine.py:437 `close >= p["open"]` -> `>` | spec | KILLED | test_engine.py::test_an_hour_that_closes_at_its_open_is_scored_up |
| 1b | 1 | `>= p["open"] + 1e-9` (epsilon tie) | fresh | KILLED | same |
| 2a | 2 | `BUYABILITY_PRICE_BAND = (0, 1)` | spec | KILLED | test_engine.py::test_a_fill_outside_the_price_band_is_a_resolution_state_not_a_trade (only failure in file, 1 failed / 107 passed) |
| 2b | 2 | `(0, 0.98)` | spec | KILLED | same |
| 2c | 2 | `(0.02, 1)` | spec | KILLED | same |
| 2d | 2 | drop `n_bad_book += 1` in the band branch (engine.py:733-734) | fresh | KILLED | same |
| 2e | 2 | fill cap `min(0.99, ...)` -> `min(0.98, ...)` | fresh | KILLED | same |
| 2f | 2 | `lo <= price <= hi` -> `lo < price < hi` | fresh probe | **SURVIVED** | none (band edges' inclusivity unpinned) |
| 3a | 3 | engine.py:286 `if not keep.exists():` -> `if True:` | spec | KILLED | test_engine.py::test_a_second_correction_never_overwrites_the_kept_record |
| 3b | 3 | `if not keep.exists() or self.current_hour:` (refresh copy on later correction) | fresh | KILLED | same |
| 3a vs HEAD | 3 | 3a against the **old** HEAD test_engine.py (`-k "warm_up or kept"`) | spec claim | SURVIVED (12 passed) | confirms the old tail could not fail |
| 5a | 5 | `ev > 0.05` -> `> 0.5` (M5) | spec | KILLED | test_scoring.py::test_a_calibrated_grade_follows_the_expected_value[1.48-slight edge] |
| 5b | 5 | `ev > 0.25` -> `> 0.3` | spec | KILLED | ...[1.52-favourable] |
| 5c | 5 | `ev < -0.05` -> `< -0.03` | spec | KILLED | ...[0.92-even] |
| 5d | 5 | `ev > 0.05` -> `>= 0` | spec | KILLED | ...[1.08-even] |
| 5e | 5 | drop the `calibrated` gate | spec | KILLED | all 8 new cases + existing test_uncalibrated_plans_never_claim_an_edge (9 failed) |
| 5f | 5 | `> 0.05` checked before `> 0.25` (order swap) | fresh | KILLED | ...[2.0-favourable] |
| 5g | 5 | `expected_value(p, 1.0, rr)` (target/stop swapped) | fresh | KILLED | ...[2.0-favourable] |
| 5h | 5 | `ev > 0.25` -> `ev >= 0.25` | fresh probe | **SURVIVED** | none (exact thresholds unpinned; spec says "either side") |
| 6a | 6 | `body` left on AutoText | spec | KILLED | test_untrusted_text.py::test_the_read_panel_draws_a_reply_as_text[read] and [error] (2 failed, as spec says) |
| 6b | 6 | `subject` left on AutoText | fresh | KILLED | ...[read] |
| 6c | 6 | `badge` left on AutoText | fresh | KILLED | ...[read] |
| 6d | 6 | error path calls `body.setTextFormat(Qt.RichText)` after `setText` | fresh | KILLED | ...[error] |

## 2. Fix 4: follow flake, 6 s `_mirror_config` delay

`time.sleep(6)` inserted at the top of `sonar/core.py::_mirror_config` in the copy (restored after), offscreen,
`uptime` load 3.75:

```
== test_follow_old (git show HEAD:tests/test_follow.py) (delay 6s)
FAILED tests/test_follow_old.py::test_whether_a_read_can_run_is_the_holders_answer
1 failed, 33 deselected in 6.21s
== test_follow (new fixture) (delay 6s)
1 passed, 33 deselected in 6.20s
```

Matches the spec's success measure. Not re-run without the delay (spec reports 0/20 loaded runs).

## 3. Full suite, scratch copy

`./run-tests.sh tests/ -q -p no:cacheprovider > out.txt 2>&1; echo $?` with `PYTHON=` the venv above.

| Mode | Load (uptime before) | Exit | Result |
|---|---|---|---|
| native | 3.26 | 1 | 3 failed, 1960 passed, 5 skipped, 30 deselected in 48.10s |
| offscreen | 9.19 | 1 | 3 failed, 1960 passed, 5 skipped, 30 deselected in 46.98s |

Collected: `1968/1998 tests collected (30 deselected)`. Failures, identical in both modes:
- `test_testplan_page.py::test_the_documented_suite_size_is_the_collected_one`: expected (docs say 1916, collected 1968; count bumped after review).
- `test_version.py::TestFormat::test_version_reads_as_a_version` (`'v2.???'`) and
  `test_version.py::TestStalenessIsHonest::test_a_bundle_finds_the_checkout_its_stamp_points_at` ("No checkout to compare against"):
  **copy artefacts** of excluding `.git`. Re-run in the worktree itself (`PYTHONDONTWRITEBYTECODE=1`): `33 passed, 1 skipped`.
- Known noise: 3 "already deleted" tracebacks in each mode. test_follow passed in both modes, including offscreen at load 9.19.

## 4. Branch coverage of the changed/pinned lines

`coverage run --branch --source=sonar,ui` over only the 13 new test cases:
- `sonar/scoring.py` 285-294 (`grade`): every line and every branch covered.
- `sonar/engine.py` 285-288 (keep copy), 437 (tie), 733-735 (band exclusion): covered. 716->717 (crossed book) missed by the new tests; out of scope, a different gate.
- `ui/app.py` 1036-1037 (the new `setTextFormat` loop): covered; straight-line code, no branches.

## 5. Test quality and gaps (ranked)

1. **P3, fix 6:** two assertions in `test_the_read_panel_draws_a_reply_as_text` cannot fail:
   `"<b>BTC</b>" == panel.subject.text()` and `"<a href=" in panel.body.text()`. `QLabel.text()` returns the
   string as set whatever the text format, so they pass with rich text on too. The `textFormat() == Qt.PlainText`
   asserts do all the work (mutants 6a-6d). The test checks configuration, not rendering. Acceptable; the comment
   "kept as characters" overstates what it checks.
2. **P3, fix 2:** band-edge inclusivity unpinned (2f survived). A fill of exactly 0.02 or 0.98 (for example ask 0.975 + 0.005 slippage)
   flips between priced and excluded without any test failing.
3. **P3, fix 5:** exact thresholds unpinned (5h survived). This is by design ("either side"), and float EV at the
   boundaries (for example rr=1.1 gives 0.05000000000000004) makes exact pinning brittle. No caller passes `calibrated=True`.
4. **Note, fix 4:** the fixture now waits on a condition, not a sleep (good), but test_follow still depends on real
   threads, localhost HTTP and wall-clock timeouts. The 15 s ceiling only costs time on failure.
5. **Note, fix 3:** the surviving assertion `eng.Engine(path).bankroll == 10_050.0, "corrected twice"` in
   `test_an_old_state_file_has_the_warm_up_taken_out_once` reads as "not corrected twice". The message wording is misleading; the logic is fine.

No over-mocking found: the engine and scoring tests run real code. The read-panel test builds a real `ReadPanel`.

## Cleanliness

`git status --short` in the worktree after the run: the same entries as before (`activity.jsonl`, the four test
files, `ui/app.py`, the spec), plus this report. No production file in the worktree was touched.

## Dispositions (orchestrator, after this record)
- Read-panel test's two vacuous text asserts: removed; the `textFormat()` asserts carry the test.
- Band edges inclusive at exactly 0.02 / 0.98: pinned by
  `test_a_fill_exactly_at_the_band_edge_is_priced`; `lo <` and `< hi` mutants now die.
- Grade `> 0.25` -> `>= 0.25`: pinned by the `(1.5, "slight edge")` case (code review P3-3); dies.
