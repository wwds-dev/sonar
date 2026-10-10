# T0-6 review — security-engineer (code + security), 2026-10-10

Read-only; no notifications posted, the running agent untouched. Playbook `status: baseline`.
All 14 initial tests fail on HEAD and pass with the diff.

**P0: none.**

| ID | Finding | Outcome |
|---|---|---|
| P1 | A full feed outage never counted as a failed poll: `feeds._get` returns None on network errors, so `_poll` raised nothing; no log, 200 from `/api/health`, no `poll` alarm (only `settle`, after ~3 h 15 min) | Fixed: `_poll_fresh` from the candle; `_poll_once` records a poll without a fresh price as failed; tests drive a real poll with `_get` returning None |
| P2 | `json.dumps` quoting cannot be broken out of, but control characters made AppleScript reject the call (-2741), and the return code was not checked: the alarm silently dropped | Fixed: text passed as `osascript` arguments, stripped to printable, capped; refused calls logged |
| P2 | A startup crash → exit 3 → relaunch every 60 s posted "SONAR stopped" every minute | Fixed: last notice time in `SONAR_DATA/alarm.json`, at most hourly |
| P3 | Start grace counted from before `warmup()` | Deferred (spec residual risk) |
| P3 | One `alarmed` flag for all kinds hid a later problem of another kind | Fixed: per-kind; test |
| P3 | Watchdog and UI take `engine.lock` via `run_health`; lock order fine, but a wedge under it freezes the watchdog | Deferred (spec residual risk) |
| P3 | Window's error early return hides health text | Deferred |
| P3 | `/api/health` exposes `last_error` unauthenticated | Deferred to T0-7 (route auth) |
| P3 | Newlines in exception text could forge log lines | Fixed: error flattened to one line |

Also traced: a malformed `engine.lock` (`{"pid": null}`, non-dict) makes `enginelock.holder()`
raise outside any `try` → crash loop at startup (now rate-limited notices). Recorded for the
stale-lock work (audit code-review P3-8, architecture P1-3).
