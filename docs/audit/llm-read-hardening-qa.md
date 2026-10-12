# QA record: `LLMReader.read()` hardening (R1-R4 + review round), 2026-10-12

Branch `llm-read-hardening`; spec `docs/specs/llm-read-hardening.md`.

## Tests first
Each round of fixes was preceded by tests that failed against the code at that point.
- **Round 1 (R1-R4):** `16 failed, 15 passed` before the fix.
- **Round 2 (code-review and security findings):** `6 failed, 33 passed` before the fix. The 6
  covered a string or object list field, deep nesting, a programming error, and the 400-credit and
  402 cases.
  - The first draft of the programming-error test passed against the unfixed code for the wrong
    reason: `_err()` builds an `LLMRead` too, so the patched class raised again from inside the
    `except`. The stub was narrowed to break only the success path, and the test then failed
    correctly.

Final: `tests/test_llm.py` has 39 tests, all passing.

## Mutation check (final code)
Fresh copy `scratchpad/author-mut-final` (`git archive HEAD` + nested repos + the final `llm.py`
and `tests/test_llm.py`). One mutation at a time, `pytest tests/test_llm.py`, restore. `cmp`
afterwards: identical. (An earlier shared copy `scratchpad/m` was altered by a reviewer's
concurrent runs. Nothing below comes from it.)

| Mutation | Failed |
|---|---|
| M8 refusal check off | 2 |
| M3 max_tokens check off | 2 |
| R4 context-window check off | 1 |
| `except RateLimitError` removed | 1 |
| R3 `except APITimeoutError` removed | 1 |
| `except APIConnectionError` removed | 1 |
| R2 raw `API error {code}: {message}` restored | 11 |
| 5xx boundary `>=` → `>` | 1 |
| 404 branch off | 1 |
| 401 label removed | 1 |
| 529 label removed | 1 |
| 402 billing branch off | 1 |
| 400 credit-balance branch off | 1 |
| raw message not passed to the status mapper | 1 |
| "reply is an object" check removed | 1 |
| list-field check removed | 2 |
| `TypeError` dropped from the parse catch | 5 |
| `OverflowError` dropped | 1 |
| `RecursionError` dropped | 1 |
| `StopIteration` dropped | 2 |
| `ValueError` dropped | 3 |
| `LLMRead` construction moved back inside the parse `try` | 1 |
| parse-error text not cleaned | 1 |
| catch-all text not cleaned | 1 |
| conviction clamp removed | 1 |
| list cap removed | 1 |
| first block taken instead of the first text block | 3 |
| `available()` result ignored | 1 |

**28 of 28 killed.** The reviewer independently killed 6 more in its own copy
(`llm-read-hardening-code-reviewer.md`).

## Full suite (worktree, repo venv, `-p no:cacheprovider`)
| Mode | Result |
|---|---|
| native `./run-tests.sh -q` | `1 failed, 1800 passed, 1 skipped, 30 deselected in 55.42s` |
| offscreen | `1 failed, 1800 passed, 1 skipped, 30 deselected in 96.43s` |

The only failure in both modes is the doc-count guard: 1,802 collected vs 1,763 documented. The
owner deferred the count bump until the QA-11/QA-13 work commits.

## Not verified
- The real `anthropic` SDK: the tests use a stand-in. Class names were checked against a 1.13.0
  copy. Whether they all exist in 0.40 (the floor in `requirements.txt`) is not verified.
- That an empty credit balance arrives as HTTP 400 with "credit balance" in the message: taken
  from the reviewer's knowledge of the API, not checked against a live response.
- The panel in the running app: not launched.
