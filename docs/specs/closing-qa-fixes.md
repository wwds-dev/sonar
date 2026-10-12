# Spec: closing-QA test gaps (M7, M4, X6, follow flake, grade P3) and read-panel S1

- Status: built (branch `closing-qa-fixes`, from `8270878` + merge of `llm-read-hardening`, `cc30d56`)
- Owner approval: task list given in chat 2026-10-12 (tasks 1, 3, 4, 5, 6 of
  `docs/audit/closing-qa-engineer.md` §6, plus `docs/audit/llm-read-hardening-security.md` S1).
- Phases: fixes 1-5 are test-only (AGENTS.md: Define/Design/Architect/Secure/Release skipped).
  Fix 6 changes `ui/app.py` (three `setTextFormat` calls); it is the security reviewer's own
  recommended fix, so Secure is covered by that report; Define/Design skipped (no visible change
  for ordinary text).

## Fixes and success measures

| # | Source | Change | Success measure |
|---|---|---|---|
| 1 | QA P1-2, M7 | `test_engine.py::test_an_hour_that_closes_at_its_open_is_scored_up` | `_score_hour` `close >= open` -> `>` fails it. (`finalize()` at a tie is already pinned by the existing `close_price=100.0 ... == "UP"` test.) |
| 2 | QA P2-5, M4 | `test_engine.py::test_a_fill_outside_the_price_band_is_a_resolution_state_not_a_trade` | `BUYABILITY_PRICE_BAND` -> `(0, 1)`, `(0, 0.98)` and `(0.02, 1)` each fail it: both band edges pinned, excluded rows counted in `n_bad_book`. |
| 3 | QA P2-6, X6 | `test_a_second_correction_never_overwrites_the_kept_record` replaces the tail of `test_an_old_state_file_has_the_warm_up_taken_out_once`, which could not fail | `if not keep.exists():` -> `if True:` fails it. The test rewrites an old-style book (marked so it differs from the original) over the corrected one, asserts the correction fires again, saves, and compares the kept copy to the original text. |
| 4 | QA P1-4, follow flake | `following` fixture also waits for `live._holder_llm` (the holder's config, mirrored after the book), timeout 15 s | With `_mirror_config` delayed 6 s, the old fixture fails `test_whether_a_read_can_run_is_the_holders_answer`; the new one passes. Not reproduced without the delay: 0/20 loaded runs (8 busy loops) of either version. |
| 5 | QA P3-10, M5 | `test_scoring.py::test_a_calibrated_grade_follows_the_expected_value` (8 cases either side of each threshold) | `ev > 0.05` -> `> 0.5` (M5), `> 0.25` -> `> 0.3`, `< -0.05` -> `< -0.03`, `> 0.05` -> `>= 0`, and dropping the `calibrated` gate each fail it. The branch stays (pinned, not deleted): no caller passes `calibrated=True` today, so it is not a live risk. |
| 6 | Security S1 | `ReadPanel` `badge`, `subject`, `body` set to `Qt.PlainText`; `test_untrusted_text.py::test_the_read_panel_draws_a_reply_as_text[read|error]` | Leaving `body` on AutoText fails both cases. |

Engineer's mutation runs were planted in the worktree file and restored with `git checkout`
after each; the targeted test file was run per mutant.

## Non-goals
- QA P1-1 (doc count) is the count bump at the end of this branch, not a separate fix.
- QA P1-3 (M3/M8) landed with `llm-read-hardening`.
- QA P2-7 (`libshiboken` teardown traceback), P2-8/9 (coverage) and S3 (`ui/worker.py` `str(exc)`):
  not in this task list.

## Review and verification
- Code review: `docs/audit/closing-qa-fixes-code-reviewer.md`: no P0-P2; P3-1, P3-3, P3-4, P3-6
  fixed, P3-2 test added (clearing `_holder_llm` on a holder change open), P3-5 open.
- QA: `docs/audit/closing-qa-fixes-qa-engineer.md`: PASS, 20 of 22 mutants killed; both
  survivors (band and grade strictness) now pinned and die.
