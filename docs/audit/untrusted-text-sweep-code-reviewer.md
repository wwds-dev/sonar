# Code review: untrusted-text-sweep, 2026-10-12

Reviewer: code-reviewer agent (read-only; saved by the orchestrator). Uncommitted diff on
`untrusted-text-sweep` vs `docs/specs/untrusted-text-sweep.md`. Playbook `status: baseline`: stale.

**Verdict: no P0-P2; four P3.** No regression for ordinary text: every caller of the six now-plain
labels passes plain text (`ui/app.py` 1537, 3565-3568, 3639-3657, 3718-3750, 4293-4296; bt_result
3583-3630; lab_status 2750-2770; sm_result 2622-2645); no `&entity;` or tags in those strings or in
`sonar/core.py` messages; `\n` still breaks lines; nothing double-escaped (`B&M` shows as `B&M`).
The 160-char cap applies only to the exception part; realistic URLError/HTTPError/timeout/JSON
errors fit; exact-text tests (`test_refused_action_message.py:247`, `test_health.py:86,234`) pass.
No missed sibling sink of this class in `ui/`.

Evidence (offscreen): test_untrusted_text 28 passed; test_health, test_follow,
test_refused_action_message, test_refresh, test_lab_tab, test_playmaker, test_sports,
test_backtest 288 passed. Native and ruff not run.

## Findings
- **P3-1** `sonar/core.py:907` poll snapshot `detail` (`llm._clean(exc, 160)`) not pinned: reverting
  to `str(exc)` left 142 tests green; not covered by the spec's "pinned through `_exc_line`" line.
- **P3-2** `ui/app.py:2999` escapes `c['component']` in the "why" line while the spec says
  component names are not escaped (table cells at 2951 are not); unpinned.
- **P3-3** `ui/worker.py:94` ConfigThread errors now carry the exception type ("Setting not
  applied: OSError: …"); not in the spec or CHANGELOG.
- **P3-4** `ui/app.py:2864`, `3310` added lines over 100 chars (E501 not selected; no CI failure).
- Mutations (scratch): plain-text loop narrowed to the toast only: killed; follow-failure call
  reverted to raw: survived (pinned only via `_exc_line`, as the spec says).

Outside the diff: `ui/app.py:3244` `pm_devig.consensus(quotes)` outside the parse `try`: books
with different outcome counts (`A -110 -110` / `B -110 -110 +300`) raise ValueError in the slot
and draw nothing (reproduced with `devig` directly).

## Dispositions (orchestrator)
- P3-1: fixed, `test_a_poll_failure_snapshot_detail_is_clean` (revert to `str(exc)` dies).
- P3-2: escape kept (harmless, consistent with the line's other field); spec corrected.
- P3-3: kept, matching the other workers; spec and CHANGELOG say so.
- P3-4: both lines split.
- Consensus crash: fixed (moved inside the `try`, same escaped message);
  `test_books_that_disagree_on_outcomes_are_a_message_not_a_crash`.
