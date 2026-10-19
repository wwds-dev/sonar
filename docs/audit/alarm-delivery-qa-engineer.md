# alarm-delivery: qa-engineer report (Verify, 2026-10-19), round 1

**Overall: pass with gaps.** The playbook is stale (`baseline`, last reviewed 2026-10-10).

## Measures

| # | Measure | Result | Evidence |
|---|---|---|---|
| 1 | Fallback | Met by test | `test_a_timed_out_banner_still_reaches_the_phone` |
| 2 | ntfy fails | Met by test | `test_a_failing_push_is_counted_and_the_watchdog_carries_on`, `test_a_failed_push_is_retried_once_then_counted`, `test_a_failed_push_says_why_without_the_topic`, `test_an_alarm_that_reached_no_channel_is_a_health_problem` |
| 3 | Not configured | Met by test, with gap Q15 | `test_with_no_topic_the_agent_says_so_once_and_sends_nothing` (checked through `states()` only) |
| 4 | Secret never shown | Met by test | `test_the_topic_never_appears_in_any_output` |
| 5 | Timestamps | Met by test | `test_every_watchdog_and_notifier_line_is_timestamped`, `test_notifier_log_lines_are_timestamped_and_redacted` |
| 6 | Phone screenshots | Needs owner evidence | goes in `docs/audit/alarm-delivery-evidence/` |
| 7 | Latency ≤ 14 min | Needs owner evidence | a second instance with a temp `SONAR_DATA` and another port |
| 8 | Diagnosis | Met (document) | `docs/audit/alarm-delivery-osascript-diagnosis.md` |
| 9 | RUNBOOK §2 | Met (document) | |

## Suite runs

| Mode | Result |
|---|---|
| Native | 2784 passed, 3 skipped, 66 deselected, rc 0 (171 s) |
| Offscreen | 2784 passed, 3 skipped, 66 deselected, rc 0 (171 s) |
| Alarm and health tests alone | 96 passed in 1.2 s; no sleeps, network or real time |

## Mutations: 21 of 23 caught

Missed:
- **Q9:** `undelivered` is never cleared, yet all tests still pass. This is the same bug as the code review's P1-1.
- **Q15:** a not-configured ntfy reports health 503, yet all tests still pass.

## Branch coverage

`sonar/alarm.py` 95%, `sonar/server.py` 95%. Not covered: alarm.py:423, 476→478, 555, 257, 259 and 223; server.py:240.

## Gaps

| Priority | Gap |
|---|---|
| P2 | No test for an undelivered alarm followed by a delivered one, or by its kinds clearing (Q9) |
| P2 | No test that a not-configured ntfy leaves health at 200 (Q15) |
| P3 | The path with no channel configured (alarm.py:423) is untested |
| P3 | `test_server` StubLive watchdog threads log an AttributeError noise line; this predates the change |
| P3 | The `_why` HTTPError branch (alarm.py:251) is unreachable |

Safety: no live state, Keychain or network was touched, and the tree was restored byte-identical (sha256 checked).

## Round 2 (2026-10-19), after fix round 1

**Overall: pass with gaps.**

**Measures:**
- 1-5 are met by tests. Gap Q15 is closed: `test_not_configured_ntfy_leaves_health_200` checks a real HTTP 200.
- 6 and 7 need owner evidence.
- 8 and 9 are met by documents.

**Suites:**

| Mode | Passed | Skipped | Deselected | rc |
|---|---|---|---|---|
| Native | 2796 | 3 | 66 | 0 |
| Offscreen | 2796 | 3 | 66 | 0 |

**Mutations:** 12 of 16 caught, run in a scratch copy only.
- Caught: Q9a, Q9b, Q9c, Q15, and N1, N2, N4, N5, N6, N7, N9, N10.
- Missed:
  - **N11 (P2):** removing `drain(STOP_FLUSH_S)` from the exit-3 path passes every test, so no test proves that exit waits for the "stopped" push.
  - **N8 (P3):** the decay value `FAILING_DECAY_S` is not pinned.
  - **N12 (P3):** `in_flight_s` is not tested together with a concurrent urgent send.
  - **N3:** an equivalent mutant (the `and not urgent` guard is redundant).

**Coverage:** alarm.py 96%, server.py 95%.

**Gaps (P3):**
- Two tests depend on timing: `test_a_watchdog_step_never_waits...` and `test_the_stopped_notice_is_not_stuck_behind_a_hung_send`.
- These defensive branches have no test: alarm.py 476-478, 518-519, 590-591.

**Safety:** the worktree's `.py` sha256 sums are identical before and after.

## Round 3 (2026-10-19), after fix round 2

**Overall: PASS, two P3 gaps.**

| Mode | Passed | Skipped | Deselected | rc |
|---|---|---|---|---|
| Native | 2809 | 3 | 66 | 0 |
| Offscreen | 2809 | 3 | 66 | 0 |

**Mutations: 16 of 18 caught.**
- The round-2 misses (N11, N8, N12) are now caught.
- Every round-2 fix is caught by a test.
- Missed (both P3):
  - **M7:** `_hurry` is cleared when the first urgent lane settles. No test has two urgent lanes still in flight.
  - **M8:** the `not self._closed` guard is untested. Close to an equivalent mutant.

**Coverage:** alarm.py 96% (only defensive excepts are uncovered), server.py 95% (lines :240 and :279->281 are uncovered).

**Test quality:**
- The N12 and M6 tests assert private state.
- `test_a_hung_push_delays_the_exit_by_at_most_the_flush` has a wall-clock bound.
- The test guard still lets through `os.system`, `$(...)` and `security>file`.

**Measures:** 1-5 are met by tests. 8 and 9 are met by documents. 6 and 7 need owner evidence.

**Safety:** all worktree `.py` sha256 sums are unchanged. No live state, Keychain or network was touched.
