# Code review r3: shadow ledger fix loop 2 (diff 244095d..aa3de64)
Reviewer: code-reviewer, read-only, 2026-10-13. Saved by the orchestrator from the agent's report,
condensed. Playbook `status: baseline` (stale). Synthetic data and scratch `SONAR_DATA` only. HEAD
moved to f8b5289 during the review (docs only). Evidence: scratchpad `cr3/` (`probe/test_walk_cr3.py`,
`walk.txt`, `walk_w4b.txt`, `native.txt`, `native2.txt`, `offscreen.txt`, `twoproc{1,2,3}.txt`).

## Summary
1. No P0, P1 or P2. Every code review r2 item and QA item is fixed or pinned by a test.
2. The README steps work as written when followed by hand (walks W1, W2-look, W3), with two naming
   edge cases (P3-1, P3-2).
3. New code holds: per-look copies, retire attribution by the id inside each backup,
   `LedgerRetiredError`, anchors counting looks only, the file's own constants, the anchor retry, the
   `price_tries` cap. Six P3s.
4. ruff: 7 findings on changed files, the same as before.
5. Suite: native exit 1 on the first run (one timing failure in `test_two_processes`, pre-existing,
   P3-6), exit 0 on rerun; offscreen exit 0.

## Prior findings
| Finding | Status | Evidence |
|---|---|---|
| CR2 P2-N1 newest backup "behind" | Fixed | anchors count looks only (calibration.py:939-941); behind check core.py:809; look copy core.py:973-982 via `paths.snapshot` (paths.py:107); walk W2-look restores. Residual P3-1 |
| CR2 P2-N2 reset cannot start a new record | Fixed | `_shadow_retired` (core.py:851); retired anchors dropped (:751-753); backups attributed by id (:831-848); walks W1, W3. Residual P3-2 |
| CR2 P3-N1 constants mismatch | Fixed | `_file_boundary`, `_file_looks` (calibration.py:1006-1019) in parse (:1097) and merge (:1185) |
| CR2 P3-N2 anchor retry | Fixed | `_ledger_needs_anchor` core.py:817, :983, :739-740, :1575 |
| CR2 P3-N3 copy nits | Fixed | ui/app.py:1055-1061 |
| QA P2-1 `price_tries` growth | Fixed | calibration.py:1228; `test_qa_p2_1_*` (450 days) |
| QA P2-2, P2-3 | Pinned | `test_qa_p2_2_q57_*`, `_q61_q65_*`, `test_qa_p2_3_q45_*` |
| QA P2-4 "same side" | Correct, no change | calibration.py:682-685 = :1053-1055; `test_qa_p2_4_q21_*` |
| QA P3 (1)-(6) | Pinned | `test_qa_p3_*`; `_today` pins `paths._dt` |
| QA P3 (8) StubLive noise | Pre-existing | |

## New findings
**P3-1. On a look's day two files carry the latest date, and only the `.look` copy restores.**
README.md:274-275; `SH_LEDGER_BEHIND`, `SH_LEDGER_RESTORE` (ui/app.py:694-713); naming paths.py:84,
:120. Walk W2: restoring `…bak.<D>` gives `LedgerBehindError`; only `…bak.<D>.look1.<id8>` works.
Fix: "the last one by name (on a look's day, the `.look<k>` copy)"; spec shadow-ledger.md:257 "always"
→ "unless the copy failed".

**P3-2. On a reset day the newest name can be the retired record's copy, and the new record may have
no copy.** core.py:981, paths.py:85-86, README.md:274-276. Walk W4b: if B (new) has no look, only A's
copies exist; restoring gives `LedgerRetiredError`, B stays missing until a person writes its id by
hand. If B's id sorts below A's, A's copy is last by name. Fix: snapshot right after a new record's first
write (`start.<id8>`); README: "the newest copy whose name ends in the first 8 characters of
`shadow_ledger.id`".

**P3-3. A file lost under a running holder is worded "this folder's" for one pass.** core.py:916, :922
set `("missing", None)`; ui/app.py:1050. Walk W5. Fix: set "marker" when `book.shadow_ledger` names
the id; test.

**P3-4. "Decided again from the same closes" is not guaranteed.** Spec Build note 17
(shadow-ledger.md:419-423), calibration.py:899-902. Fix wording: "decided again from the closes then
available; not part of any recorded look".

**P3-5. Expert erratum says "looks 1 and 2 and 3".** ui/app.py:1080. Fix: "looks 1, 2 and 3".

**P3-6. Pre-existing race in `test_the_window_drives_once_the_agent_process_is_gone[agent stopped]`.**
tests/test_two_processes.py:181-182 asserts `read_only is False` as soon as the lock is held;
`_take_the_book` clears it last (core.py:1577). Failed once under load. Fix: `_wait(lambda: not
live.read_only)`.

## Suite (TEST_BUDGET_S=900, load 43-114)
| Run | Code | Exit | Result |
|---|---|---|---|
| Native | aa3de64 | 1 | 1 failed (P3-6), 2554 passed, 3 skipped |
| Offscreen | aa3de64 | 0 | 2555 passed, 3 skipped |
| Native rerun | f8b5289 (same code) | 0 | 2555 passed, 3 skipped |
| `test_two_processes.py` ×3 | same | 0, 0, 0 | 4 passed each |
Not run: slow.
