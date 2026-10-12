# Code review: `tests/test_llm.py` (QA M3/M8), 2026-10-11

Reviewer: code-reviewer agent (independent of the author, read-only). Branch
`qa-m3-m8-llm-read-tests`. Playbook `docs/playbooks/code-reviewer.md` is `status: baseline`
(last-reviewed 2026-10-10).
Run: `pytest tests/test_llm.py` gave `17 passed`. The stand-in was checked against the real SDK,
anthropic 1.13.0 (installed in another lab venv): `_exceptions.py`, `_base_client.py:460-471`,
`types/stop_reason.py`, `types/refusal_stop_details.py`, `resources/messages/messages.py:132`.

## Verdict
No P0 or P1. No test can pass for a reason other than the one it states. The refusal and
truncation tests use a body that parses, so only the stop-reason check can catch it. The 429 case
pins the order of the `except` clauses.

Where the stand-in matches the SDK:
- `RateLimitError < APIStatusError < APIError`
- `.status_code` and `.message`
- an optional `stop_details.category`
- content blocks with `.type` and `.text`
- `output_config`, which exists in 1.13

Neither the fake module nor the env var leaks out of a test: `monkeypatch` restores both.

## Findings (all in production code; none fixed in this test-only change)
| # | Pri | Where | Finding | Suggested fix |
|---|---|---|---|---|
| R1 | P2 | `sonar/llm.py:276-283` | JSON that parses but is not a dict (`[]` gives AttributeError), or a non-numeric `conviction` (`"high"` gives ValueError), raises out of `read()`. The call site `sonar/core.py:680` has no guard. "Never take the panel down" covers only the API call. | Build the `LLMRead` inside the same `try` and return `unparseable response`; add one test. |
| R2 | P2 | `sonar/llm.py:256` | The real SDK sets `exc.message` to `"Error code: 401 - {...raw dict...}"`, so the panel shows the status code twice plus raw JSON. The 401/529 tests use tidy messages, so they don't pin what a user actually sees. | Use a short fixed label per status (401 key, 529 overloaded, 5xx server), and give the tests the SDK's real message format. |
| R3 | P3 | `sonar/llm.py:257` | `APITimeoutError` subclasses `APIConnectionError`, so a 120 s timeout reads "could not reach the API (network)". | Catch `APITimeoutError` first, with its own message and a test. |
| R4 | P3 | `sonar/llm.py:266` | The `model_context_window_exceeded` stop reason (and `pause_turn`) falls through to parsing, so it shows "unparseable response" instead of "truncated". The risk is low at this prompt size. | `stop_reason in ("max_tokens", "model_context_window_exceeded")`. |

Not pinned and harmless:
- The `ImportError` branch at `llm.py:239` cannot be reached once `available()` passes.
- `model`, `generated` and `latency_ms` on the clean path are not asserted.

## Disposition (author)
R1-R4 change user-visible behaviour in production code, so they are outside this test-only change.
They are left for the owner to schedule.
