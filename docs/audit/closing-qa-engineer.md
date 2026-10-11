# Closing QA review: SONAR at HEAD 001e0e4 (v2.180), 2026-10-11

Role: qa-engineer (read-only). Playbook `docs/playbooks/qa-engineer.md` is `status: baseline`
(last-reviewed 2026-10-10, one day old): it carries no current practice beyond AGENTS.md, so
this review rests on AGENTS.md, app-context.md and the specs.

Method. Everything ran in scratch copies under
`/private/tmp/claude-501/-Users-as-Documents-lab-active-sonar/6575dd04-d4d4-4ae1-a064-bc7c34a4fae8/scratchpad/`,
never in the worktree (another session has uncommitted edits to `engine.py`, `scoring.py`,
`calibration.py`, `backtest.py`, `ui/app.py`, README/TESTING/TESTPLAN and four test files; none of
that was tested here). Two copies of committed HEAD:
- `head/`: `git archive HEAD | tar -x` (no `.git`).
- `clone/`: `git clone --local` (has `.git`), with the gitignored nested repos `sonar/macro`
  and `sonar/playmaker` copied in (HEAD does not track them; CI checks them out at pinned SHAs).
Python was the repo's `.venv` (`PYTHON=.../.venv/bin/python`, `-p no:cacheprovider`).

## Verdict (short)
**FAIL for "clean 30-day run" readiness; PASS for the specs' own success measures.**
HEAD is red by one test (README says 1,811 tests, the committed suite collects 1,763). All five
initial survivors M3, M4, M5, M7, M8 still survive; none of the T0/T1 work touched them. The T0/T1
success measures themselves are pinned: 7 fresh mutations across the t0/t1 areas, 6 died.

## 1. Suite at HEAD
| Copy / mode | Command | Result |
|---|---|---|
| clone, native | `./run-tests.sh -q -p no:cacheprovider` | `1 failed, 1761 passed, 1 skipped, 30 deselected in 42.72s` |
| clone, offscreen | `QT_QPA_PLATFORM=offscreen ./run-tests.sh -q -p no:cacheprovider` | `1 failed, 1761 passed, 1 skipped, 30 deselected in 42.64s` |
| head (no .git), native | same | `3 failed, 1757 passed, 3 skipped, 30 deselected in 36.50s` |
| head (no .git), offscreen | same | `3 failed, 1757 passed, 3 skipped, 30 deselected in 39.32s` |

The one real failure, both modes:
`tests/test_testplan_page.py::test_the_documented_suite_size_is_the_collected_one` ->
`pytest collected 1,763 tests, but the documents say {'TESTPLAN.md': 1763, 'TESTING.md': 1763, 'README.md': 1811}`.
`git show HEAD:README.md` line 266 says `1,811`; commit 001e0e4 wrote the count of the other
session's dirty tree. Committing the dirty tree (whose TESTING/TESTPLAN say 1,811) likely closes
it; **not verified** because I did not run the dirty tree.
The two extra failures in `head/` are export artefacts (no `.git`):
`test_version.py::TestFormat::test_version_reads_as_a_version` (`'v2.???'`) and
`...::test_a_bundle_finds_the_checkout_its_stamp_points_at`; both pass in `clone/`.

Flakiness (two-run rule). Native and offscreen each ran twice-plus (the 13 mutant runs below are
full offscreen runs of the unmodified tests; all showed the same fixed baseline failures). One
flake did appear, in the coverage run (59.6s, slower): `tests/test_follow.py::test_whether_a_read_can_run_is_the_holders_answer`
-> `'the engine at 127.0.0.1:56977 runs the read, and has not said yet whether it can'`.
Reproduced once in 15 isolated runs with 8 busy-loop processes competing for CPU, 0 of 12 on an idle machine.
Cause: the `following` fixture (`tests/test_follow.py:146-159`) waits for `snapshot["following"]`
and `positions["open"]`, but `Live._holder_llm` is set later, from `/api/config`
(`sonar/core.py:1088`). The test reads it with no wait.
Teardown noise persists: 3 x `RuntimeError: libshiboken: Internal C++ object (MainWindow) already deleted`
per run, from `ui/app.py:3854` / `3813` (`lambda: self._confirm_hidden(...)` -> `self.isVisible()` at `ui/app.py:3869`).
Same defect as qa.md reported at old line 3569; not fixed.

## 2. Re-planted initial mutations (scratch copies of HEAD, full suite offscreen each)
Baseline failures subtracted (3 in `head/`). "Survived" means no new failure.
| # | Mutation (HEAD line) | Result |
|---|---|---|
| M3 | `llm.py:266` `if resp.stop_reason == "max_tokens":` -> `if False and ...` | **SURVIVED** (`3 failed, 1757 passed`) |
| M8 | `llm.py:263` `"refusal"` check disabled | **SURVIVED** |
| M4 | `engine.py:606` `BUYABILITY_PRICE_BAND (0.02, 0.98)` -> `(0.0, 1.0)` | **SURVIVED** |
| M5 | `scoring.py:177` `grade()` `ev > 0.05` -> `> 0.5` | **SURVIVED** (but see P3 below: unreachable in production) |
| M7 | `engine.py:385` `_score_hour` `close >= p["open"]` -> `>` | **SURVIVED** |

Result: **0 of 5 now die.** `grep -ln stop_reason tests/*.py` returns nothing; there is no
`tests/test_llm.py`. `git diff --stat af128c8 HEAD -- tests` shows 25 files touched, none for
`llm.py`, the buyability band, `grade()` or the score-log outcome. The dirty tree's added test
names (grep of `git diff -U0`) also cover none of M3/M4/M7/M8; not run, so not verified.

## 3. Fresh mutations on the T0/T1 success measures
| # | Mutation | Spec | Result |
|---|---|---|---|
| X1 | `engine.py` stale-candle guard `if False and ...candle.open_time < current_hour` | t0-4 | killed: `test_engine.py::test_a_candle_from_an_earlier_hour_does_not_void_the_open_position` |
| X2 | `calibration.py` `Z_CLAIM 3.0 -> 1.96` | t1-1 | killed: `test_calibration.py::test_beating_the_odds_is_claimed_only_beyond_three_standard_errors` |
| X3 | `server.py` foreign-Origin check disabled | t0-7 | killed: `test_server.py::test_a_write_from_a_foreign_origin_is_refused` |
| X4 | `server.py` chunked-body 411 disabled | t0-7 | killed: `test_a_chunked_body_is_refused_rather_than_read_as_empty` |
| X5 | `feeds.py` slug `h < 12 -> h <= 12` (12pm reads 12am) | t1-5 | killed: 2 tests (`test_the_hour_slug_uses_a_twelve_hour_clock`, `test_the_slug_hour_edges[12-12pm]`) |
| X7 | `server.py` Host check disabled | t0-7 | killed: 4 tests incl. `test_a_rebinding_host_is_refused_for_reads_and_writes[...]` |
| X8 | `calibration.py` `GRADED` adds `"MANUAL"` | t1-1 | killed: `test_a_manual_close_in_profit_is_not_a_target_hit` |
| X6 | `engine.py:233` `if not keep.exists():` -> `if True:` (kept pre-warm-up copy overwritten) | t0-3 | **SURVIVED** |

7 of 8 died. X6 is the t0-3 success measure "`state.json.before-warmup-fix` ... never overwrites it".
The test meant to pin it, `tests/test_engine.py:581-586`, reloads a file that has already been
corrected, so `_warmup_correction` is 0 and the guarded branch never runs
(coverage: `engine.py` `234->240` partial, `237-238` uncovered). It passes for a reason other
than the one in its failure message ("the kept copy was overwritten"): the assertion cannot fail.
Reachable in production: an older installed build rewrites the uncorrected book, the new code
corrects it again and saves, replacing the owner's original record.

## 4. Coverage (clone, offscreen, `coverage run --branch --source=sonar,ui`)
TOTAL 83% (includes nested `sonar/macro`, `sonar/playmaker`; the 80% bar is met either way).
Changed/important modules: `engine.py` 97% (missing `234->240, 237-238, 331->333, 368->370, 384, 590, 646, 722, 733`),
`calibration.py` 98% (222), `server.py` 94%, `enginelock.py` 92%, `execution.py` 95%, `feeds.py` 85%
(359-383, 424-427), `core.py` 83%, `alpaca.py` 65%, `scoring.py` 76% (93, 101-112, 174-181),
`ui/worker.py` 51%, **`llm.py` 50%** (was 30%; missing 131, 135, 145-150, 165, 180, 205-210, 221-276, 299-315,
i.e. all of `read()` after the SDK import). `TESTING.md` still says `engine.py` is 100%; it is 97%.
(That coverage run had the flake above, so figures come from a run with 2 failures; they are
line-execution counts and unaffected.)

## 5. Test quality
- Assertions that cannot fail: `tests/test_engine.py:581-586` (above). Rationale text is untrue
  of the branch it claims to cover; the same lesson TESTING.md records for `_mark_book`.
- Time dependence: the `test_follow.py` race above; `tests/test_shutdown.py` fixed 0.2-0.3 s sleeps
  (from qa.md; not re-measured).
- Over-mocking: LLM tests patch `available()` only; the code that decides what a user sees when
  the model refuses or truncates is never driven.
- Network: conftest closes the network; only opt-in `test_live_sources.py` (`-m network`, 30 deselected, not run) touches it.
- The doc-count guard works as designed and is what caught the HEAD inconsistency.

## 6. Ranked gaps for the 30-day clean run
**P0** none. No gap found that bears on money paths: the live-key guard, flatten, and settle
idempotency were pinned in qa.md; T0 specs' mutations die (X1, X3, X4, X7).

**P1**
1. HEAD is red: README `1,811` vs 1,763 collected (`test_testplan_page.py`). CI is red on any
   push of HEAD as it stands. Resolve by committing the matching tree; re-run both modes after.
2. M7 survives: `_score_hour`'s `>=` vs `>` at close == open feeds the model-vs-market Brier log
   that the dry-run readiness gates and the 30-day run read. Add a test with `close == open`
   expecting outcome 1.0 (and one for `finalize()` at `engine.py:454`, not mutated here).
3. M3/M8 survive: `llm.py` `read()` refusal/truncation/unparseable/rate-limit mapping is untested
   (`llm.py` 221-276). A silent regression shows a user a half-answer from the model, in a
   product whose honesty is the point. Drive `LLMReader.read` with a fake client.
4. Flaky `test_follow.py::test_whether_a_read_can_run_is_the_holders_answer` (and likely its sibling
   asserting the same `_holder_llm` hand-off): add `_wait(lambda: live._holder_llm is not None)` to the
   fixture. A 30-day clean run that depends on CI staying green will meet this.

**P2**
5. M4 survives: nothing exercises a book at `ask` < ~0.02 or > ~0.98 in `buyability` (`engine.py:606,
   642-662`). It is not equivalent: a row with `ask = 0.015` is kept under (0, 1) and dropped under the real band.
6. X6: replace `tests/test_engine.py:581-586` with a test that makes the correction fire a second time
   (rewrite the old-style file over the corrected one, load, save) and asserts the kept copy is unchanged.
7. `libshiboken ... already deleted` teardown traceback (`ui/app.py:3813, 3854, 3869`): ships in production
   code and hides real tracebacks; guard the lambda (`shiboken6.isValid`).
8. TESTING.md claims `engine.py` 100%; measured 97%. `enginelock.py` 40-41, 52-53, 148-160, 191, 208-209 uncovered (lock edge paths of t0-1).
9. `core.py` 83%, `alpaca.py` 65% (`_request` and the `AlpacaUnavailable` mapping), `ui/worker.py` 51%,
   `execution.py` 561-623 error paths (unchanged from qa.md; not re-listed in detail).

**P3**
10. M5 is unreachable in production: `assets.py:466` calls `build_plan` without `calibrated`, so `grade()`
    always returns "unproven" (`scoring.py:172`) since t1-1 made calibration a report. Lines 174-181 are dead;
    either delete them or pin them, and note that the survivor is not a live risk.
11. Research apparatus, `ui/app.py`/`ui/tabs.py` handlers: unchanged from qa.md; not re-measured here.

## Not verified
- The dirty worktree (the other session's QA-11/QA-13 work) was not run or mutated.
- `-m network` live-source checks were not run (30 deselected).
- `finalize()` boundary (`engine.py:454`) was not separately mutated.
- Real-machine release smoke test and the headless agent's health: out of scope here (see sre-release).

## State of the repo
Scratch only; no repo file touched except this report. `git status` is the other session's changes
plus this file (checked at the end).
