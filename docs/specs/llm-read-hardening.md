# Spec: `LLMReader.read()` says plainly what went wrong, and never raises on a bad reply

- Status: built (branch `llm-read-hardening`, on top of `qa-m3-m8-llm-read-tests` / `4466131`)
- Owner approval: "yes fix and commit" in chat 2026-10-12, for review findings R1-R4.
  Define/Design gates not held separately: the change is limited to the error text of an
  existing panel. Architect skipped: no state, concurrency or module boundary is touched.
- Source: `docs/audit/qa-m3-m8-llm-read-tests-code-reviewer.md` R1-R4.

## Problem
- **R1 (P2).** A reply that parses but has the wrong shape raised out of `read()`: a JSON array,
  a `conviction` that is a word, null or infinite, or a `catalysts` that is not a list.
  `sonar/core.py` has no guard, so the request failed with no read and no error.
- **R2 (P2).** API status errors showed the SDK's raw message, e.g.
  `API error 401: Error code: 401 - {'type': 'error', ...}`.
- **R3 (P3).** A timeout read "could not reach the API (network)".
- **R4 (P3).** The `model_context_window_exceeded` stop reason fell through to parsing, so a
  cut-off reply that happened to parse would have been shown as a whole read.

## Behaviour
| Case | Message shown |
|---|---|
| 402 | `the API account has a billing problem — check its credit balance (HTTP 402)` |
| 400 mentioning "credit balance" | `the API account's credit balance is too low (HTTP 400)` |
| 400 / 401 / 403 / 413 / 529 | a fixed line per status, ending `(HTTP n)` |
| 404 | `model <name> was not found (HTTP 404)` |
| other 5xx | `the API had a server error (HTTP n)` |
| other 4xx | `the API returned an error (HTTP n)` |
| 429 | unchanged: `rate limited — try again shortly` |
| timeout | `the API did not answer within <timeout> s` |
| context window exceeded | `response cut off — the request filled the model's context window` |
| wrong-shape JSON (not an object, list field not a list, bad conviction, deep nesting) | `unparseable response: <ExceptionType>: <message, cleaned and capped at 160 chars>` |
| any other exception | `<ExceptionType>: <message, cleaned and capped at 160 chars>` |

A bug while building the `LLMRead` from parsed values raises; it is not reported as a bad reply.

No message carries the raw error body. Exception text that can quote the model's own reply goes
through `_clean()`: angle brackets and control characters are removed and the length is capped.

## Success measure
- 22 new tests in `tests/test_llm.py` (39 in the file), all green.
- Each of 28 planted mutations of `read()` fails at least one test
  (`docs/audit/llm-read-hardening-qa.md`).
- The full suite passes natively and offscreen, apart from the deferred doc-count guard.

## Non-goals
- `complete()` (the Playmaker path) keeps its `TypeName: message` errors.
- The `pause_turn` stop reason: it occurs only with server tools, which `read()` does not use.
- The doc test-count bump: deferred until the QA-11/QA-13 work commits.
