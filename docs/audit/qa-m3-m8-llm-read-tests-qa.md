# QA record: M3/M8 `LLMReader.read()` tests, 2026-10-11

Branch `qa-m3-m8-llm-read-tests` from `ab4279e`; spec `docs/specs/qa-m3-m8-llm-read-tests.md`.
New file `tests/test_llm.py` (17 tests). Production code unchanged.

## Mutation check
Scratch copy: `git archive HEAD` plus `tests/test_llm.py` and the nested `sonar/macro`,
`sonar/playmaker`, under the session scratchpad. Each mutation was planted in `sonar/llm.py`
alone, then `pytest tests/test_llm.py` was run, and the original was restored before the next.
After the run, `cmp` showed the scratch `llm.py` was byte-identical to the worktree's.
Before any mutation: `17 passed`.

| Mutation in `read()` | Result | Killed by |
|---|---|---|
| M8: `if False and resp.stop_reason == "refusal"` | 2 failed | both refusal tests |
| M3: `if False and resp.stop_reason == "max_tokens"` | 2 failed | truncated[parses], truncated[cut-mid-object] |
| `except RateLimitError` clause removed (429 falls to APIStatusError) | 1 failed | failure_message[429] |
| `except APIConnectionError` clause removed | 1 failed | failure_message[connection] |
| catch-all `except Exception` removed | 1 failed | failure_message[anything-else] |
| status code dropped from the API-error message | 2 failed | failure_message[529], [401] |
| `except StopIteration` only (ValueError escapes) | 1 failed | unparseable[prose-not-json] |
| `except ValueError` only (StopIteration escapes) | 2 failed | unparseable[no-text-block], [empty-content] |
| `resp.content[0].text` instead of the first text block | 3 failed | thinking-block test, unparseable[no-text-block], [empty-content] |
| conviction clamp removed | 1 failed | clamp/cap test |
| catalysts cap removed | 1 failed | clamp/cap test |
| refusal category ignored (`'unspecified'` always) | 1 failed | refusal (cyber) |
| `'unspecified'` fallback dropped | 1 failed | refusal without a category |
| `output_config.format` (schema binding) removed | 1 failed | schema-bound request test |
| `if not ok: return _err(...)` removed | 1 failed | no call when a read cannot run |

**15 of 15 killed**, including the two survivors from the closing review (M3, M8).

## Full suite (worktree, repo venv, `-p no:cacheprovider`)
| Mode | Result |
|---|---|
| native `./run-tests.sh -q` | `1 failed, 1778 passed, 1 skipped, 30 deselected in 40.69s` |
| offscreen `QT_QPA_PLATFORM=offscreen ./run-tests.sh -q` | `1 failed, 1778 passed, 1 skipped, 30 deselected in 39.31s` |

The one failure in both modes is the doc-count guard:
`test_testplan_page.py::test_the_documented_suite_size_is_the_collected_one`, which reports
`pytest collected 1,780 tests, but the documents say ... 1763`. The owner deferred the count bump
until the QA-11/QA-13 work commits. Before the new file, the suite at `ab4279e` was green:
`1762 passed, 1 skipped`.

## Not verified
- The real `anthropic` SDK is not installed, so the tests run against a stand-in. Its fidelity is
  the reviewer's question 2 (`qa-m3-m8-llm-read-tests-code-reviewer.md`).
- `complete()` is still untested (out of scope).
