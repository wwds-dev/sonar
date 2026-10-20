# starved-engine: code review (2026-10-19)

Reviewer: `code-reviewer` (read-only). Saved by the orchestrator. Diff: the uncommitted diff against d548361, plus
`scripts/diag_priority.py` and `tests/test_diag_priority.py`. The playbook is stale (`status: baseline`).

**Verdict:** no P0 or P1. The `SONAR_ALARM` parsing keeps the live default, and the `server.py` wiring and the
plist/install path are correct. The harness has four P2s.

**Commands:** `.venv/bin/python -m pytest -q tests/test_alarm.py tests/test_diag_priority.py
tests/test_agent_from_bundle.py` gave 226 passed. `--collect-only tests/` gave 2929. The harness was not run.

**Checked and correct:**
- `alarm_mode`: unset, empty, whitespace or any-case `on` all mean on (`alarm.py:640-644`). Any other value skips the
  Keychain.
- `server.py:433-434` is the only caller.
- `--test-alarm` still reads the Keychain, as it should.
- The plist comment is valid XML.
- `install_agent.sh` renders from the template and writes only `SONAR_DATA` into the environment.
- Every bootstrap and bootout goes through `check_label`.
- 8787 is refused, and only `/api/health` is fetched from it.
- `wait_first_scan` really does wait for the cold scan (`core.py:341-368, 1504-1506`).

## P2
- **P2-1. The alarm-off check will likely abort `run` at the load the run needs.**
  - **Where:** `ALARM_CHECK_S = 30` (`:82`) and per-request `timeout=10` (`:633-643, 685, 689-690`).
  - **Why:** the Background engine took 3-24 s to answer health, and spawning took about 47 s in the diagnosis.
  - **Fix:** a per-request timeout of at least 30 s and a startup deadline of at least 120 s, still failing closed.
    Optionally also confirm off mode from the engine's log line.
- **P2-2. Failed samples are dropped from p50/p95.**
  - **Where:** `:289-291, 414-420, 431-436, 479-480`.
  - **Why:** 10% timeouts still leave p95 at 500 ms. "Max < 10 s" catches this for health, but `/api/state` (A5's
    decision input) has no backstop.
  - **Fix:** count a non-answer as +inf (or the timeout) and test that 10% failures push p95 over the bar.
- **P2-3. Cleanup on interrupt or error can stop halfway.**
  - **Where:** `:197, 603-623, 669-672, 741-745`.
  - **Why:**
    - (1) The `finally` resets SIGINT to `SIG_DFL` before cleanup, so a second Ctrl-C kills it mid-cleanup.
    - (2) SIGHUP (tab closed) isn't handled, so engines keep polling.
    - (3) `bootout` with the 30 s `_cmd` timeout raises `TimeoutExpired` out of cleanup, so the rest is never booted
      out and `rmtree` never runs.
    - (4) A failed `bootout` is still reported as "booted out".
    - RUNBOOK §7 `cleanup` without `--dir` never deletes the scratch dir.
  - **Fix:**
    - Set `SIG_IGN` for INT, TERM and HUP during cleanup.
    - Handle HUP like TERM.
    - Wrap each bootout in try/except, with a longer timeout and the real return code.
    - Have `cleanup` with no `--dir` scan `$TMPDIR/sonar-diag-*` via `check_scratch`.
    - Add a test that sends SIGTERM mid-run.
- **P2-4. The path guard can be bypassed by letter case (confirmed).**
  - **Where:** `_under` uses a case-sensitive `relative_to` (`:107-127`). `check_outside_live(home/'library/application
    support/SONAR/x.md')` passed.
  - **Fix:** compare casefolded parts, and add a mixed-case test.

## P3
- **P3-1.** The market-hours projection leaves out the unbounded follower `input()` (`:660, 696`). Fix: check
  again just before the hour starts.
- **P3-2.** An error mid-hour throws away every sample (`:703-713, 731`). Fix: append rows to `<out>.partial` as they
  arrive, and point to `cleanup` when a port is refused.
- **P3-3.** `tests/test_diag_priority.py:561, 615` need a real `ROOT/.venv/bin/python`, so they fail in a fresh
  worktree. Fix: monkeypatch it.
- **P3-4.** RUNBOOK §7 says in the present tense that the agent runs Standard, but it isn't installed yet. ADR 0006
  still says "proposed", though both gates are approved.
- **P3-5.** `.gitignore` has `.venv/`, which doesn't match the worktree's `.venv` symlink. Fix: add `.venv`.

## Not verified
- That launchd reports `spawn type` for Standard as expected.
- That curl's `%{time_total}` always uses a `.` as the decimal separator.
- That the follower's child processes exit on `terminate()`.
