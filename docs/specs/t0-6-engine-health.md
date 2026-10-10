# Spec: T0-6 — a silent engine failure is made loud

- Status: built (branch `fix/t0-6-engine-health`)
- Owner approval: 2026-10-10 — alarm channel "macOS notification" (asked in chat).
- Source: `docs/audit/operations.md` P0 (silent stop, no alarm).
- Review: `docs/audit/t0-6-engine-health-security-engineer.md` (code + security) — no P0;
  P1 and both P2s fixed, P3s partly fixed.

## Problem
The agent ran its engine on a daemon thread; if it died, the HTTP server kept the process up,
launchd never restarted it, and the last snapshot kept saying all was well. Failed polls were
swallowed without a log line — and a full network outage raised nothing at all, because the feed
fetchers turn errors into `None`. Nothing reached the owner with the window closed.

## Success measure
- A poll with no fresh price, or one that raises, is a failed poll: logged to stderr (first, then
  ~once a minute), never counted as success (`tests/test_health.py`).
- `Live.health()` judges the engine at call time; `GET /api/health` → 200 / 503.
- An engine thread that ends unasked exits the process (code 3) so launchd restarts it; the
  "stopped" notice is sent at most once an hour across restarts.
- One macOS notification per problem kind after it lasts (poll 10 min, settle 75 min — past a
  wake from sleep), one on recovery; a later problem of another kind is still told.
- The window's status line shows the problems.
- 10 planted mutations, 10 caught. A real notification was posted and the argv form verified.

## Architecture
- `core.Live`: `_poll_once()` records each poll's outcome (`last_poll_ok_at`, `_poll_failures`,
  `last_poll_error` flattened to one line); `_poll` sets `_poll_fresh` from the candle;
  `health(now)` returns `ok`, `mode` (driving/starting/waiting/following/stopped/not started) and
  `problems` (`loop`, `poll`, `settle`). Waiting or following is not this engine's problem.
- `server`: `/api/health`; `Watchdog` thread in `main`; `notify_macos` passes the text to
  `osascript` as arguments (never script source), stripped to printable text and capped, and logs a
  refused call; `alarm.json` under `SONAR_DATA` holds the last "stopped" notice time.
- `ui/app.py`: the status line shows `health()` problems.

## Residual risk
- The 180 s start grace counts from before `warmup()`; on a very slow network the window and
  `/api/health` can show a problem early (the 10-minute alarm delay hides it from notifications).
- If the engine wedges while holding `engine.lock`, `health()` blocks and so does the watchdog.
- `/api/health` is unauthenticated like every route (audit security P1-1, T0-7); it adds the last
  error string, which `/api/state` already exposes.
- A raising poll shows the window's "error" early return, which hides the health text.

## Verification
Full suite 1,633 passed natively and under `QT_QPA_PLATFORM=offscreen`.

## CHANGELOG draft
**The agent tells you when it stops working.** A dead engine loop now restarts the agent; a
network outage or a stalled run posts a macOS notification (and one when it recovers); the
window's status line says what is wrong; `/api/health` answers 200 or 503.
