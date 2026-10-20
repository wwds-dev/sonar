# build-traceability: QA verify (2026-10-19)

Reviewer: `qa-engineer` (read-only). Saved by the orchestrator. The playbook is stale (`status: baseline`).

**Verdict:** passes the Verify phase. Measures 1, 2, 6 and 7 are met by tests. Measure 5 is met in temporary repos.
Measures 3 and 4 are pending until Release. 27 of 28 mutants were killed.

| # | Measure | Status |
|---|---|---|
| 1 | Stamp records copies as unknown and makes the top level dirty (`tests/test_version.py::TestTheStampNamesTheNestedCode`; M14 killed) | Met |
| 2 | Gate refusals, including outer dirty with nested clean and drift; overrides name the reasons (`test_agent_from_bundle.py` UNTRACEABLE ×10 through both installers) | Met |
| 3 | Bootstrap a fresh worktree; `test_ci_pins` passes with no skip | Pending (Release): still skips here (copies) |
| 4 | Real bundle passes `check_app.sh`; negative copy-only run; `docs/audit/build-traceability-verify.md` | Pending (Release, owner-gated). A read-only `check-stamp` on the old stamp gave rc 3 with 5 reasons |
| 5 | Tag command and its refusals (`tests/test_buildid.py`); retroactive v2.340 printed, rc 0, no tag created | Met in tests; post-release part pending |
| 6 | Ledger build string, old entries byte-identical, 64-char edge | Met |
| 7 | Docs: VERSIONING, RUNBOOK, version.py docstring; no "linear" claim | Met |

## Suite
- Native, run twice (`./run-tests.sh -q -p no:randomly`, then `./run-tests.sh`): 1 failed, 3099 passed, 3 skipped.
- Offscreen (`QT_QPA_PLATFORM=offscreen ./run-tests.sh`): same result.
- The only failure is the expected newest-entry-ahead check for v2.365.

## Mutation
- 28 mutants were planted in a scratch copy and each was restored and sha256-checked; 27 were killed.
- **Survivor: M25.** The bootstrap postcondition drops the `HEAD != pin` check (`bootstrap_nested.sh:178`). It's a
  backstop.
- Coverage: `sonar/version.py` 90%, `stamp_version.py` 92%. `buildid.py` measures 46% in-process because the CLI
  runs in subprocesses, so its real figure isn't measured.

## Test quality
- The three tests changed by design were not weakened; two are stronger.
- Real git and real scripts; only `codesign`, `launchctl` and the self-test are faked.

## Findings
- **P2-1.** Measures 3 and 4 are unverified (by design, the Release phase), so the definition of done is blocked
  until then.
- **P3-1.** M25 survived: no test for the bootstrap postcondition.
- **P3-2.** Untested: the `_checkout_pins` failure fallback (`sonar/version.py:375-376`) and the final `[:64]` cut
  (`:421`).
- **P3-3.** The `build_app.sh:120-121` tag-command wiring is untested.
- **P3-4.** Two weak tests: `test_the_gate_runs_under_the_system_python` and `test_an_absent_nested_dir_is_not_a_copy`
  (asserts only that WARNING is absent).
