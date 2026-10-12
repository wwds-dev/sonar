# Code review: closing-qa-fixes (uncommitted diff on branch `closing-qa-fixes`), 2026-10-12

Reviewer: code-reviewer agent (read-only; saved by the orchestrator). Playbook
`docs/playbooks/code-reviewer.md` is `status: baseline` (last-reviewed 2026-10-10): stale.
Inputs: `docs/specs/closing-qa-fixes.md`, `docs/audit/closing-qa-engineer.md` (§3 X6; §6 items 2,
4, 5, 6, 10), `docs/audit/llm-read-hardening-security.md` (S1), `docs/company/app-context.md`.

**Verdict: no P0, P1 or P2. Six P3.** Each new test fails when its bug is put back.

## What was run
- Targeted, offscreen: test_engine + test_scoring + test_untrusted_text `171 passed in 1.67s`;
  test_follow `34 passed in 2.78s`. `git diff --check` clean.
- Not verified: ruff (not in `.venv`), full suite, native mode.

| Mutant (scratch copy) | Result |
|---|---|
| `_score_hour` `close >= open` -> `>` | killed |
| band (0.02, 1), (0, 0.98), (0.02, 0.99), (0.015, 0.98) | each killed |
| band (0.016, 0.98) | **survived** (P3-4) |
| band check `n_bad_book += 1` -> `pass` | killed |
| X6 `if not keep.exists():` -> `if True:` | killed |
| grade `ev > 0.3`, `ev < -0.03` | killed |
| grade `ev >= 0.25`, `ev >= 0.05` | **survived** (P3-3) |
| ReadPanel loop without `body` / without `badge` | killed / killed |

## Per fix
1. M7 (`tests/test_engine.py:702`): OK. The scoring close is the next candle's open
   (`sonar/engine.py:373`), so `close == open` is really reached. Deterministic.
2. M4 (`tests/test_engine.py:936`): OK. Cheap row fills at 0.015, dear row capped at 0.99; both pass
   the `0 < bid <= ask < 1` check (`engine.py:716`), so the band excludes them. `n_priced == 5`
   catches the dear rows (their edge 0.009 is below the 0.04 gate).
3. X6 (`tests/test_engine.py:584`): OK, can no longer pass for the wrong reason: the correction is
   asserted to fire again, and the kept file is compared to the original byte for byte.
4. Follow fixture (`tests/test_follow.py:155-159`): hides no product bug. `_holder_llm` is set only
   at `sonar/core.py:1133`, after `_mirror_book`; "has not said yet" (`core.py:661-662`) is designed
   behaviour. The settle check (`_mirror_mark` / `_settled_since`) is not bypassed by waiting. The
   read test already gained its own 5 s wait in 231540b; the fixture change mainly lengthens the
   budget, which the 6 s-delay demonstration shows.
5. M5 grade (`tests/test_scoring.py:101`): OK for the spec's mutants; strictness not pinned (P3-3).
6. S1 ReadPanel (`ui/app.py:1034-1037`): complete for the LLM read path. `subject` also gets the
   untrusted subject via `show_pending` (`ui/app.py:1044`); success/error paths (callers 3552,
   3555, 3568) write only to badge/subject/body plus app-written `caveat`. Other model output: the
   playmaker narrative is `html.escape`d (`ui/app.py:3270-3288`); the sports `summary`
   (`ui/app.py:2540`) is local. No regression for ordinary text (`·`, `•`, `\n`, curly quotes);
   not checked visually.

## Findings
- **P3-1** `tests/test_follow.py:589-594` `test_a_holder_that_can_read_lets_a_follower_without_the_sdk_ask`
  waits 5 s for the *next* slow round; the fixture wait does not help. Same flake class (QA item 4,
  "likely its sibling"). Fix: 15 s there too / a shared constant.
- **P3-2** `sonar/core.py:661-662` "has not said yet" now has no test (the fixture always waits past
  it). Also `_holder_llm` is never cleared when following stops or the holder changes (only set at
  `core.py:137`, `1133`): a previous holder's answer could show until the new config arrives (not
  reproduced). Fix: unit test with `following` set and `_holder_llm = None`; optionally reset it.
- **P3-3** grade strictness: `ev >= 0.25` / `>= 0.05` survive. rr=1.5 gives ev exactly 0.25:
  add `(1.5, "slight edge")`. 0.05 is not exactly reachable at p=0.5.
- **P3-4** price-band low edge pinned only to (0.015, 0.02]. Optional: a row filled at ~0.019.
- **P3-5** (outside S1) `ui/app.py:3260` `playmaker_status.setText(error)` on an AutoText label
  (`ui/app.py:3005`); `error` from `sonar/llm.py:359-360` (`f"{type(exc).__name__}: {exc}"`, not
  `_clean`ed) or `ui/worker.py:139`. Reachability not verified. Fix: PlainText + `_clean(exc, 160)`
  in `llm.complete`.
- **P3-6** (nit) `tests/test_engine.py:581` duplicates line 603's test; message "corrected twice"
  reads backwards.

## Dispositions (orchestrator)
- P3-1, P3-3, P3-4, P3-6: fixed on this branch (see the commit).
- P3-2: the test is added; clearing `_holder_llm` on a holder change is a production change outside
  this task list: open.
- P3-5: open, outside this task list (same class as S3).
