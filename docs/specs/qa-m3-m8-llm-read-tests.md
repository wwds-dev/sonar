# Spec: QA M3/M8 — `LLMReader.read()` failure mapping is tested

- Status: built (branch `qa-m3-m8-llm-read-tests`, from `ab4279e`)
- Owner approval: asked for in chat 2026-10-11 (task list from `docs/audit/closing-qa-engineer.md`).
  Test-only change: Define/Design/Architect/Secure/Release skipped (AGENTS.md: test-only changes);
  no production code changed.
- Source: `docs/audit/closing-qa-engineer.md` §2 (M3, M8 survived), §6 P1-3.

## Problem
`sonar/llm.py` `read()` decides what the user sees when the model refuses, runs out of tokens,
returns text that is not the schema's JSON, or the call fails (429, other status, network, anything
else). None of it ran in the suite (`llm.py` 50% covered, 221-276 missing); the existing LLM tests
patch `available()` only. Disabling the refusal or the `max_tokens` check left the suite green, so a
half-answer could reach the panel looking like a whole one.

## Success measure
- `tests/test_llm.py` drives `LLMReader.read` through a stand-in `anthropic` module (the SDK is
  optional and not installed in CI; no network). The stand-in keeps the SDK's class shape:
  `RateLimitError` subclasses `APIStatusError`, so the `except` order is under test.
- Every error path returns an `LLMRead` with the exact user-facing message and no direction,
  conviction or prose: refusal (with and without a category), `max_tokens` (both a body that parses
  and one cut mid-object), prose instead of JSON, no text block, empty content, 429, 529, 401,
  connection error, any other exception, and `available()` false (no client built, no call made).
- The clean path is pinned too: parsed fields, conviction clamped to 0..100, lists capped at 6,
  a thinking block before the text skipped, the request bound to `_SCHEMA` with headlines inside
  `<HEADLINES>`.
- 15 planted mutations of `read()`, including M3 and M8, each fail at least one new test
  (record: `docs/audit/qa-m3-m8-llm-read-tests-qa.md`).

## Non-goals
- `complete()` (Playmaker's plain-text path) — not in M3/M8; still untested.
- Hardening `read()` against JSON that parses but breaks the schema (a list, or a non-integer
  `conviction`): today that raises out of `read()`. Structured outputs make it unlikely; logged as a
  finding, not fixed here.
- The test-count bump (README/TESTING/TESTPLAN): deferred by the owner until the QA-11/QA-13 work
  commits; until then `test_testplan_page.py::test_the_documented_suite_size_is_the_collected_one`
  fails on this branch (1,780 collected vs 1,763 documented).
