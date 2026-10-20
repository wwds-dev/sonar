# alarm-delivery: code-reviewer report (Review, 2026-10-19)

The playbook is stale (`baseline`, last reviewed 2026-10-10).

**Tests run:** `tests/test_alarm.py tests/test_health.py` 22 times: 21 runs gave 96 passed, 1 run had 1 failure (P2-2). The full suite was not run.

**Checked and sound:**
- `render` takes no free text.
- `_why` never uses `str(exc)`.
- Log lines are redacted.
- `states()` never contains the topic.
- `merge_json` keeps both keys, and alarm.json has a single writer.
- `test_alarm` and `main.py` import nothing from core.
- The opener ignores proxies and refuses redirects.

## P1
**P1-1. "An alarm reached no channel" turns health red and never clears.**
- Where: alarm.py:388, 446-454; server.py:307.
- Reproduced with a temp `SONAR_DATA`:
  - ntfy not configured and the banner timing out.
  - A poll alarm at t=700 fails, then recovers.
  - Health still returns `ok=False` with `[{'kind':'notify','text':'an alarm reached no channel'}]` at t=900 and three days later.
- Effects:
  - Only a later delivered alarm, or a restart, clears it.
  - `/api/health` stays 503, and every heartbeat says "open problems: notify".
  - With only the banner configured, health goes red, which the architecture rejected.
  - The planned external probe would page forever.
- Fix:
  - Clear the flag when a later event or the recovery is delivered, or once the alarmed kinds clear.
  - Decide, with owner sign-off, whether a banner-only lane may raise it at all.
  - Add a test: kinds clear, then health returns 200.

## P2
**P2-1. The "stopped" notice can be lost behind an ntfy retry.**
- Where: server.py:349-354; alarm.py:465-477.
- If the ntfy lane is in its 20 s retry wait or stuck on a hung send, "stopped" waits in the queue behind it.
- `drain(12)` then times out and `os._exit` kills the sender, so the notice is lost.
- `stopped_at` is already persisted, so the next hour of the crash loop is suppressed too.
- Fix: abandon retries before draining, or send urgent events first. Add a test.

**P2-2. The heartbeat crash-loop test is flaky.**
- Where: test_health.py:477-488.
- It failed 1 in 22 runs: `assert 4 == 2`, meaning two heartbeats were sent.
- The root cause is unknown.
- Line 483 asserts with no drain first, so it can pass vacuously.
- Fix: drain before that assert, then loop the test about 200 times. It may be a real double-send.

**P2-3. One failed event keeps ntfy "failing" (503) until the next event, which can be up to 24 h later.**
- Where: alarm.py:518.
- This matches the spec's wording. Needs the owner to confirm the intent, or the code to add an age bound or re-probe. Document it in the RUNBOOK.

## P3
- **P3-1.** server.py:331: a caller passing `notify` positionally gets an AttributeError, and on engine death it never reaches `exit_fn(3)`. No such caller exists today. Fix: make the argument keyword-only, or wrap the callable.
- **P3-2.** alarm.py:474, 486: if the `say`/log call raises inside `_serve`, the sender thread dies (also security P3-3).
- **P3-3.** alarm.py:603: `parse_args` exits on stray arguments. Fix: use `parse_known_args`.
- **P3-4.** server.py:268-279: the `_Callback` adapter drops the heartbeat. This only affects the test path.

**Not checked:** the full suite, the RUNBOOK and README copy, and the diagnosis document.

## Round 2 (2026-10-19), after fix round 1

**Tests:** `test_alarm`, `test_health` and `test_two_processes` ran 10 times, 112 passed each run. The flaky heartbeat, stopped and undelivered subset ran 60 more times with 0 failures.

**Verdict:** no P0 and no P1.

**Round-1 items:**
- **Fixed:** CR P1-1, P2-1, P2-2, P2-3, P3-1, P3-2 and P3-3; security P2-1, P3-1, P3-2 and P3-3.
- **Not fixed, optional:** CR P3-4 (test path only) and security P3-4. In the conftest guard, a string command such as `"osascript ..."` passes the guard, and `Popen` and `os.system` are still not caught.

**P2-a. The undelivered flag clears only when every kind is clear, not just the alarmed ones.**
- Where: server.py:364-367.
- Deviates from owner decision (a).
- Scenario: a poll alarm fails on ntfy, poll recovers, and an unrelated scan problem is still open. Health stays 503 until all kinds clear or the next ntfy delivery, which can be about 24 h away.
- Fix: track the undelivered alarm's own kinds and clear the flag when they clear. Add a test with two overlapping kinds.

**P2-b. A failed "stopped" notice still silences the next hour.**
- Where: server.py:254-262, 350-354.
- `stopped_at` is persisted before the send.
- Fix: persist it only after delivery succeeds, or have the owner accept this as a residual.

**P3:**
- **P3-a:** alarm.py:427, 534: `_hurry` is set and never cleared, so later retries are skipped. Harmless in production because the process exits right after.
- **P3-b:** alarm.py:297-320, 477, 500: `channel.why` is shared between the urgent thread and the lane thread. Cosmetic.
- **P3-c:** server.py:349-355: if the log call raises, `exit_fn(3)` is skipped. This predates the change. Fix: try/finally.
- **P3-d:** alarm.py:448: the say call for a dropped event does not use `_safe_say`.

## Round 3 (2026-10-19), after fix round 2

**Tests:** `test_alarm`, `test_health` and `test_two_processes` ran 10 times; all 10 passed (125 tests each). **Verdict:** no P0, no P1, no P2.

**Round-2 items, all fixed:**
- CR P2-a: alarm.py:484-490, :505
- CR P2-b: server.py:356-362
- CR P3-a to P3-d
- QA N11, N8 and N12
- Conftest guard widened. Remaining gaps are in P3-3 below.

**Regression checks, all sound:** lock order, the `_urgent_live` counter, the urgent send fitting within `STOP_FLUSH_S`, and that "stopped" and the heartbeat never set the undelivered flag.

**P3:**
- **P3-1. "Delivered" covers any channel, including the banner** (server.py:261-265, :361; alarm.py:545-546).
  - If the network is down but the banner posts, `stopped_at` is saved and the phone gets no "stopped" notice for an hour.
  - The docstring and the health text "an alarm reached no channel" do not describe this correctly. The RUNBOOK (lines 52 and 93) does.
  - Fix: gate the save on ntfy delivery, or reword the docstring and health text.
- **P3-2. A crash loop while the network is down now waits up to 12 s on every restart.** This is bounded and documented; it is a residual for the owner to accept.
- **P3-3. Gaps in the conftest guard** (conftest.py:48-60).
  - Commands wrapped in `sh -c` and commands joined with `;` get past it.
  - `"echo don't"` raises `ValueError` from `shlex.split`.
  - Fix: catch the error and fall back to `split()`, and scan the `-c` payload.

## Final check (2026-10-19), after the owner's round-3 P3 pass

**Verdict: PASS.** No regressions, and no P0, P1 or P2.

Tests:
- The targeted tests ran 5 times, 139 passed each run.
- Full suite: 2823 passed. The new guard does not refuse any ordinary command in the suite.

Confirmed:
- `stopped_at` is recorded only after delivery on ntfy when ntfy is configured (alarm.py:387-393, server.py:363-364).
- The health text matches RUNBOOK:93.
- The guard has no shlex.
- `_hurry` is cleared only when `_urgent_live` drops to 0 or below.

P3 (test-only, latent; recorded as known limitations of the guard):
- **P3-1** (conftest.py:69-70): a shell string that contains the word "security", such as `git commit -m "security fix"`, is falsely refused.
- **P3-2** (conftest.py:72): `Popen(Path(...))` raises `TypeError`. Fix: handle `os.PathLike` in the string branch.
- Known gaps: `env osascript`, `python -c` payloads and `os.system` are not caught.
