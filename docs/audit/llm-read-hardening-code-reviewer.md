# Code review: `LLMReader.read()` hardening, 2026-10-12

Reviewer: code-reviewer agent (independent of the author, read-only), two rounds. Playbook
`status: baseline`. The SDK was checked against anthropic 1.13.0 (another lab venv). No 0.40 copy
was available.

## Round 1: the R1-R4 diff
No P0 or P1.
- The except order is correct: `APITimeoutError` subclasses `APIConnectionError`
  (`_exceptions.py:100`), and `APIStatusError` is a separate branch.
- The status mapping keys on `status_code`, so it does not depend on newer SDK subclasses.
- No new test passes for the wrong reason. 6 mutations planted, all killed.

| # | Pri | Where | Finding | Disposition |
|---|---|---|---|---|
| C1 | P2 | `ui/app.py:1031` (existing) | The read panel's body label has no `setTextFormat(Qt.PlainText)`, so the model's summary, catalysts and risks can render as rich text. | **Open.** Same as security S1. `ui/app.py` has uncommitted QA-11/QA-13 edits; to do after they commit. |
| C2 | P2 | `llm.py` status map | A fixed 400 label hides an empty credit balance, and 402 is not mapped. | **Fixed:** 402 and "credit balance" 400 have their own lines. The SDK message is searched, never shown. |
| C3 | P3 | `llm.py` parse `try` | A programming error while building `LLMRead` was reported as a bad reply. | **Fixed:** construction moved after the `try`. |
| C4 | P3 | `llm.py` list fields | A string list field became one bullet per character; an object became its keys. | **Fixed:** they must be lists. |
| C5 | P3 | `llm.py` `json.loads` | Deep nesting raised `RecursionError` out of `read()`. | **Fixed:** caught. |
| — | P3 | `llm.py` catch-all | Uncleaned `str(exc)` (also security S2). | **Fixed:** `_clean`. |

## Round 2: the delta fixing C2-C5 and S2
All fixes are correct. No test passes for the wrong reason: the programming-error test breaks only
the success path, so `pytest.raises` is genuine. Nothing new at P0-P2. Six more mutations were
planted in `/private/tmp/claude-501/reviewer-r2`, one per fix, and all were killed. C1 remains open.
