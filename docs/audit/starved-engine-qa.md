# starved-engine: QA verify (2026-10-19)

Reviewer: `qa-engineer` (read-only). Saved by the orchestrator. The playbook is stale (`status: baseline`).

**Verdict:** the code and tests pass, but not every success measure is shown yet. Measure 1 is shown and measure 6
is partly met. Measures 2, 3 and 5 are pending until the measured hour, and measure 4 until install plus 7 days.
34 of 38 mutants were killed.

## Measures
| # | Measure | Status |
|---|---|---|
| 1 | plist guard, template + installer-rendered (`tests/test_agent_from_bundle.py:344-390`; mutants P1-P3, I1 killed) | Shown |
| 2 | Side-by-side hour, bg/std | Pending: the measured hour |
| 3 | CPU ≤ 5 % of a core | Pending: the measured hour |
| 4 | Installed agent, 7 days | Pending: install + 7 days |
| 5 | Follower never shows "not answering" (proxy tested; launch path not covered) | Pending: the measured hour |
| 6 | RUNBOOK priority + numbers | Partial: text done, numbers `_TBD_` |

The FOLLOW_TIMEOUT decision (scope b) waits on measure 2.

## Suite
- Native: `./run-tests.sh -q -p no:cacheprovider` gave 1 failed, 2925 passed, 3 skipped, 66 deselected (163 s).
- Offscreen: `QT_QPA_PLATFORM=offscreen ./run-tests.sh -q -p no:cacheprovider` gave the same result (160 s).
- The only failure is the expected `test_version` newest-entry-ahead check: v2.363 against build 362, which goes
  green at commit.
- Changed lines in `alarm.py` and `server.py` have 100% branch coverage. `diag_priority.py` is at 92%.

## Mutation
- 34 of 38 mutants were killed.
- The survivors:
  - **D22:** the pid-changed exit returns 0 (`:736-738`).
  - **D23:** `wait_first_scan` ignores the scan problem (`:652`).
  - **D24:** a failed bootstrap is ignored (`:211-213`).
  - **D15:** the market-hours loop is replaced with `break` (`:184-189`).
- All files were restored and checked with `shasum -c`. The script is
  `scratchpad/qa/mut.py`.

## Findings
- **P2-1.** `ALARM_CHECK_S = 30` (`:82, 685`) can abort measure 2 at load ≥ 50, where the bg spawn took about 47 s.
- **P2-2.** The live-pid-changed guard is untested (D22).
- **P2-3.** The cold-scan stagger is untested (D23). If bg's first scan exceeds the 600 s cap, std starts anyway and
  the two cold scans overlap.
- **P3-1.** Bootstrap failure is untested (D24).
- **P3-2.** The market-hours loop is not exercised (D15).
- **P3-3.** The SIGINT/SIGTERM handlers are reset to `SIG_DFL` rather than the previous ones (`:742-743`).
- **P3-4.** `make_scratch` leaks the dir when `check_scratch` refuses (`:147-148`).
- **P3-5.** `watch` counts health samples with a poll or scan problem, not alarms, and keeps no banner attempt count,
  so measure 4's "failures per attempt" can't be computed (`:757-760`; spec:74).
- **P3-6.** The CLI dispatch for probe, watch and cleanup, and exit code 130, are not covered (`:822-835`).
- **P3-7.** Existing before this change: leftover watchdog threads from the older `tests/test_server.py` `server.main`
  tests print noise.
- **Test-quality gap:** no end-to-end test shows that `/api/health` carries `notify.ntfy.reason == "off
  (SONAR_ALARM)"`.
