# Spec: a holder's read answer stays with it (P3-2); exception text is never markup (P3-5, S3)

- Status: built (branch `holder-llm-playmaker-plaintext`, from `3a7e572`)
- Owner approval: asked for in chat 2026-10-12 ("fix P3-2 and P3-5 next").
- Source: `docs/audit/closing-qa-fixes-code-reviewer.md` P3-2, P3-5;
  `docs/audit/llm-read-hardening-security.md` S3 (same defect class, same file as P3-5's worker
  half, fixed with it).
- Phases: small fixes to existing behaviour, no visible change for ordinary text. Define/Design/
  Architect skipped (no state, concurrency or module-boundary change: one attribute reset on the
  follow thread, which alone writes `following`). Secure required (untrusted input).

## Problem
1. P3-2: `Live._holder_llm` (whether the engine holder can run an LLM read) was set from the
   holder's `/api/config` and never cleared. After the follower stopped following, or the lock
   passed to another holder, the old holder's answer was shown for the new one until its config
   arrived.
2. P3-5: `playmaker_status` was an AutoText label showing exception text, and `llm.complete()`
   returned `f"{type(exc).__name__}: {exc}"` raw. Text that looks like markup (`<a>`, `<img>`)
   would be drawn as rich text.
3. S3: `ui/worker.py` `ReadThread` and `PropThread` emitted raw `str(exc)` too.

## Change
- `sonar/core.py`: `Live._follow(url, pid)` sets `following` and clears `_holder_llm` when the
  holder changes (another URL, a new pid at the same URL, or none); the follow loop uses it.
  `_holder_llm` is `(url asked, ok, detail)`, and `llm_available()` reads `following` and the answer
  once and ignores an answer given for another URL (review P3-1/P3-3, security S-A).
- `sonar/llm.py` `complete()`: the catch-all error goes through `_clean(…, 160)`, as `read()`'s does.
- `ui/worker.py`: both catch-alls use `llm._clean(…, 160)`.
- `ui/app.py`: `playmaker_status.setTextFormat(Qt.PlainText)`.

## Success measure
New tests, each failing under the listed mutation (engineer run, file restored after each):

| Test | Mutation | Result |
|---|---|---|
| `test_follow.py::test_a_new_holder_has_not_answered_for_the_old_one` | reset removed; reset only on `None`; pid ignored | killed (each) |
| `test_follow.py::test_an_answer_from_the_last_holder_is_not_shown_for_the_next` | URL key removed from `llm_available` | killed |
| `test_follow.py::test_the_follow_loop_resets_the_answer_when_the_holder_changes` | loop writes `following` directly; loop passes no pid | killed; killed |
| `test_llm.py::test_a_plain_completion_shows_an_exception_cleaned_and_capped` | `complete()` raw error | killed |
| `test_untrusted_text.py::test_the_playmaker_status_line_is_text_not_markup` | `setTextFormat` removed | killed |
| `test_untrusted_text.py::test_a_worker_error_is_cleaned` | `ReadThread` raw error | killed |
| `test_untrusted_text.py::test_a_completion_worker_error_is_cleaned` | `PropThread` raw error | killed |

## Non-goals
- `ui/app.py:3225` `_playmaker_price`: `f"<b>Could not read the prices.</b><br>{exc}"` puts the
  parser's message (from the owner's own pasted prices) into rich text. Not in this task; noted.
- QA P2-7 (`libshiboken` teardown traceback).

## Review
- Code review `docs/audit/holder-llm-playmaker-plaintext-code-reviewer.md`: no P0-P2; P3-1..P3-3
  fixed; P3-4 open.
- Security `docs/audit/holder-llm-playmaker-plaintext-security.md`: no P0-P2; S-A fixed; S-B, S-C,
  S-D (playmaker/lab HTML panes, AutoText status labels) open as one follow-up sweep.
