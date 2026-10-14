# QA (Verify): hourly weekend / hour-of-week vol study, commit 2d6fee5

Date 2026-10-13. Scope: `sonar/research/hourlyvol_weekend.py`, `tests/test_hourlyvol_weekend.py`
vs `docs/specs/hourly-weekend-vol-study.md`. Playbook `docs/playbooks/qa-engineer.md` is
`status: baseline` (last-reviewed 2026-10-10): not radar-verified, practice unverified.

## Verdict: PASS for the apparatus; the full project suite is NOT VERIFIED (environment)

## Environment limits (honest)
- No `.venv`, no PySide6, and the nested repos `sonar/macro` and `sonar/playmaker` are absent, so
  `tests/conftest.py` fails to import (`cannot import name 'macro' from 'sonar'`). `./run-tests.sh`
  fails at `.venv/bin/python`; with `PYTHON=python3` it fails on the same import.
  `./run-tests.sh` and `QT_QPA_PLATFORM=offscreen ./run-tests.sh`: **not verified**. The study module
  imports only `hourlyvol`/`stats`, so its tests were run with `--noconftest`.
- `coverage` was not installed; installed into the scratchpad (`pip --target`), repo untouched.

## Commands and output
1. `python3 -m pytest tests/test_hourlyvol.py tests/test_hourlyvol_weekend.py -q --noconftest`
   -> `64 passed, 5 deselected in 11.16s` (default addopts deselect `slow`).
2. Size check, all of it (4 chunks of 50 seeds + summary, one process; the summary asserts all
   chunks ran): `pytest tests/test_hourlyvol_weekend.py -m slow -k size_check --noconftest`
   -> `5 passed, 47 deselected in 125.33s`. Nothing skipped; 200 seeds, V1 and V2 each <= 10 rejections.
3. Coverage: `coverage run --branch --source=sonar/research -m pytest tests/test_hourlyvol_weekend.py --noconftest`
   (47 passed, slow deselected) -> `hourlyvol_weekend.py 329 stmts, 98 branches, 91%` (floor 80%: PASS).
   Missing: 162 (`all_mean <= 0`), 174 (`_Est` bad kind), 223 (length mismatch), 525-526 and 528-541 (`main`
   hash print and the network run path), 545. Lines 422-430 (size check) are covered only by the slow tests.
4. Determinism: all RNG is seeded, no network, no clock; the fast set ran three times (64, 47, 47 passed)
   with identical results. No flakiness seen.

## Success measure, line by line (spec "Pre-registration" and controls)
| Line | Result | Evidence |
|---|---|---|
| Frozen numbers copied exactly | PASS | `test_frozen_preregistration_numbers`; see frozen-only note below |
| Weekday/weekend convention, Sun 23:00 weekend, Mon 00:00 not | PASS | boundary test; mutants M1, M2 killed |
| Causal estimators B0/B0L/V1/V2, factors before push, clamp per factor | PASS | naive from-scratch reference at 3 origins x 4 kinds, rel 1e-9 |
| One-sided p formula, lag 168, bootstrap block 168, blocks n//6 remainder dropped | PASS | tests; M6, M9, M10, M18 killed. Bootstrap block size itself is NOT asserted (F4) |
| Verdict rules 1-6 first match, p strict, 1.0% inclusive | PASS | 13-case parametrised table; M7, M8 killed |
| V2 "LONGER WINDOW ONLY" rule | PASS | `test_longer_window_only_label`; M19 killed |
| 3600 s contiguity abort, bad close abort | PASS | tests; M16 killed |
| Runner refuses when spec hash empty or differs; fetch not reached | PASS | 3 tests. Match path in `main` untested (P2) |
| C1 flat, seed 7, >= 0.995 and no KEEP | PASS | `test_c1_flat_volatility_must_not_win` |
| C1 size check, 200 seeds, <= 10 rejections per variant | PASS | ran in full, see 2 |
| C2 planted weekend 1.5x: V1 I>0, W>=5, p<alpha | PASS | `test_c2` |
| C3 planted Tuesday 13-20h 2x: V2 KEEP incl. vs B0L | PASS | `test_c3` |
| C4 equivalence 1e-12, B0 == shipped `hv.study`, causality, boundary | PASS | `run_c4` (returns a single bool; see P2) |
| Power simulation exists (reported, non-gating) | PASS (smoke only) | 2 seeds, 1 multiplier, bounds check only |
| Nothing live changed | PASS | see 5 |
| No real-data result | N/A | by design; Binance blocked, owner's Mac |

## Mutation check (copy in scratchpad; repo never edited)
Setup: copy of `sonar/research` + the test file under the scratchpad, run with `-m "not slow"`.
24 behavioural mutants (M1-M24): **23 killed, 1 survived.**
- Survivor M22: size check counts a rejection on `p < ALPHA` alone, dropping `improvement > 0`.
  Equivalent mutant: `p < 0.0167` one-sided implies `t > 0`, hence `mean_d > 0`, hence `improvement > 0`.
  The condition is redundant; no test gap.
- Killed (all): weekday offset, weekend `>=5`, V1 EWMA ignoring g, class factor fed r2 not rd2,
  `<` vs `<=` on 100 h minimum, one-sided p at t=0, `>=`/`>` on 1.0% and on 5 blocks, block win `<=`,
  d sign, V2 cell = hour only, scoring start off by one, scored hour off by one (`times[:-1]`),
  missing lower clamp, eviction skipping `total`, contiguity `<`, alpha /2, HAC lag 9, `or` for `and` in
  v2_label, pup_shift 1.0 sigma, lambda 0.95, inverted class in `_mult`, unclamped class factor.
- **Frozen-constants-only catches** (8 constant mutants F1-F8, rerun with the two frozen-number tests
  deselected): LONG_WINDOW 4368->4000 survives (F3) and BOOT_BLOCK 168->24 survives (F4). Both are caught
  only by `test_frozen_preregistration_numbers`. The rest (alpha, threshold, MIN_SCORED, context lags,
  BLOCKS, V1 class window) are caught behaviourally as well. Reason for F3: the naive-reference test runs
  at 1500-1700 hours, before a 4368 h window fills.

## Findings
- P0: none.
- P1: none.
- P2-1: Full suite (both modes) not run: sandbox lacks `.venv`, PySide6, `sonar/macro`, `sonar/playmaker`.
  Re-run `./run-tests.sh` and the offscreen mode on the owner's Mac before Release. Risk is low: the new
  files are imported by nothing else.
- P2-2: Long-window behaviour (eviction at 4368 h in `_Est`/`_Cells`) has no end-to-end reference test; only
  `_Cells(2, window=3)` eviction and the frozen-number assertion guard it (F3). Add a naive-reference check
  at an origin > 4368 + 100 h, or accept.
- P2-3: `main()` happy path and provenance block (lines 525-541) are untested; `--print-spec-hash` too.
  Cheap to test with a monkeypatched `fetch_hourly`.
- P2-4: `run_c4` returns only `{"ok": bool}`; a failure gives no diagnosis. The bootstrap block size is
  never asserted (only `len == 2`).
- P2-5: Power-simulation test is a smoke test (two seeds, bounds 0..1); it cannot fail on wrong detection logic.
  Acceptable because it is non-gating.
- P2-6: Scope deviation from the spec: spec Scope says the code goes in `hourlyvol.py` and
  `tests/test_hourlyvol.py`; the engineer used a new module and left `hourlyvol.py` untouched. Safer for the
  agent run, but the spec text should be reconciled by the owner or architect.
- P2-7: `APPROVED_SPEC_SHA256` is empty, so the runner cannot run yet. Correct for now (owner records the
  approving commit hash and then fills this in). The spec file was edited after approval (982834d recorded
  approval); the hash must be taken after the final spec edit.

## 5. Unchanged-file and isolation checks
- Commit 2d6fee5 touches 4 files: new `sonar/research/hourlyvol_weekend.py`, new
  `tests/test_hourlyvol_weekend.py`, `TODO.md` (+6), `docs/company/activity.jsonl` (+3, the activity log).
  `tests/test_hourlyvol.py`, `sonar/research/hourlyvol.py`, `sonar/model.py` and all other code: no diff
  (`git diff --stat origin/master HEAD -- tests/test_hourlyvol.py sonar` shows only the new module).
  `activity.jsonl` is a log, not code. Note `git diff origin/master HEAD` overall also shows other, earlier
  commits (spec approval 982834d, trial-ledger docs/ADR); those are not part of 2d6fee5.
- Grep for `hourlyvol_weekend`: references only in `TODO.md`, the module itself, its test, and a stale
  `.claude/worktrees/agent-a6fb09a755df241fa` copy. No import from `sonar/`, `ui/`, scripts, spec files or CI.
- `git status --short` at the end of the run: clean (no output).
