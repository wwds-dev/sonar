# Security review: `LLMReader.read()` hardening, 2026-10-12

Reviewer: security-engineer agent (read-only; did not run tests). Playbook `status: baseline`.
Scope: the `sonar/llm.py` diff on branch `llm-read-hardening`.

## How an error reaches the screen
1. `LLMRead.error` is returned by `as_dict()` (`sonar/core.py:680`).
2. `ReadPanel.show_read` passes it to `self.body.setText(r["error"])` (`ui/app.py:1054`).
3. `label()` (`ui/app.py:343`) never calls `setTextFormat`, so Qt's AutoText applies: a string that
   looks like markup is drawn as rich text.

`static/` never shows `llm_read`, and `server.py` passes it through as JSON.

## Answers
- Model and server text now reach the error string only through `_clean`, which strips `<` and `>`.
  The raw `exc.message` (the server's error body) is gone.
- No secrets: the messages are fixed text plus the status code, the cleaned model name and the
  timeout.
- The change opens no injection path and closes two:
  - the raw server body;
  - the `int("...")` exception, which escaped `read()` and was shown uncleaned by
    `ui/worker.py:44`.

## Findings
| # | Pri | Where | Finding | Disposition |
|---|---|---|---|---|
| S1 | P2 | `ui/app.py:1070` (existing) | A successful read's `summary`, `catalysts` and `risks` go into the same AutoText label uncleaned. A reply steered by a headline could start with `<a href=…>` or `<img src=…>` and be drawn as rich text. Fix: `setTextFormat(Qt.PlainText)` on `body` (and `subject`), as `ui/app.py:751/809` already do. | **Open.** `ui/app.py` has uncommitted QA-11/QA-13 edits by another session; to do once those commit. |
| S2 | P3 | `sonar/llm.py` catch-all `except Exception` (existing) | `str(exc)` is shown uncleaned. It also wraps `_get_client()`, so a credential-profile failure could show a file path (not verified). | **Fixed** in this change: `_clean(exc, 160)`, pinned by `test_an_unexpected_exception_is_shown_cleaned_and_capped` (mutation killed). |
| S3 | P3 | `ui/worker.py:44` (existing) | Also shows `str(exc)` uncleaned. After this change it is much harder to reach. | Open; low. |

No P0 or P1.
