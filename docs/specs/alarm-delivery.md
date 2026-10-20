# Spec: Alarm delivery (off-machine push, heartbeat, notification health)

- Status: draft
- Owner approval: pending
- Priority: **P0** (operations audit wave 2, P0-1; also closes P2-5 §2 and the P2-2 timestamp part)
- Radar note: `docs/company/radar-notes/2026-10-14-feature-alarm-delivery.md`

## Problem
The owner is the only user of the headless agent, and the agent's only way to tell him something is wrong does not work.
- `notify_macos` (`sonar/server.py:236-252`) runs `osascript display notification` with a 10 s timeout. It is the
  agent's only outbound signal.
- `~/Library/Logs/SONAR/agent.err.log`: 45 of 47 attempts since 2026-10-12 11:51 failed with "could not post a
  notification ... timed out after 10 seconds". The missed alarms included "no successful price poll for 24 min" and
  "the board has not been rescanned for 16 min". Poll outages of 12-24 min happened at least 7 times in three days.
  Nobody was told (audit P0-1).
- Even when the banner works, it only reaches someone sitting at this Mac.
- A failed notification is only a stderr line. `/api/health` does not show it, so a broken channel looks healthy.
- Watchdog lines have no timestamp (`server.py:287`), so the log cannot show when an alarm fired.
- `docs/RUNBOOK.md` §2 says the agent "posts a macOS notification after 10 minutes". In practice that is false.
- The cause of the timeouts is not verified. The candidates are a TCC/automation prompt that a background bundle
  cannot show (ad hoc signing gives each build a new identity), or CPU starvation from `ProcessType Background`
  plus `Nice 5` on a machine with load average up to 182 (audit P1-2).

The 30-day clean run (due 2026-11-09) has "no silent stop" as a criterion. Right now nothing supports that claim.

## User and goal
**User:** the owner, away from the Mac, running the paper agent.
**Goal:** within a known time, the owner learns on his phone that the agent has a problem or has gone silent. He
can also tell from `/api/health` whether each alarm channel is working.

**Success measures (all must be shown):**
1. **Test: fallback.** With the banner forced to time out and a fake HTTP opener, one watchdog alarm produces exactly one
   ntfy POST to the configured topic. The test checks `X-Title`/`X-Priority` and a generic body. `/api/health` then
   shows the banner failure count at 1 and the ntfy failure count at 0.
2. **Test: ntfy fails.** When the POST raises or returns non-2xx, the ntfy failure count goes up, the watchdog keeps
   running and nothing is raised. An alarm that reached no channel is a health problem.
3. **Test: not configured.** With no topic, nothing goes to the network and banner behaviour is unchanged. `/api/health` shows
   the push channel as `not configured`, and the agent logs one timestamped startup line saying so.
4. **Test: the secret stays secret.** The topic string never appears in the `/api/health` body, any log line or an
   exception message (the test searches all output for it).
5. **Test: timestamps.** Every watchdog log line starts with a parseable local ISO timestamp.
6. **Owner evidence (phone).** Screenshots of (a) a test alarm sent on demand, and (b) one scheduled daily heartbeat.
   Both are received on the owner's phone and saved under `docs/audit/alarm-delivery-evidence/`.
7. **Latency.** Inject a poll fault into a *second* instance (temp `SONAR_DATA`, other port, never the live agent's
   data). The push must arrive on the phone within **14 min** (amended at the Architect gate, see below) of the fault starting: the 600 s threshold, plus the
   15 s watchdog tick, plus at most 60 s delivery, plus margin. Fault start and arrival time are recorded.
8. **Diagnosis recorded.** `docs/audit/alarm-delivery-osascript-diagnosis.md` names the cause of the timeouts as
   TCC, starvation, both or "not determined", with commands and output. It covers at least: one `osascript` run in the
   agent's own context (`launchctl asuser`); the same run from a throwaway launchd job with `ProcessType Background`
   and one with `Standard`; and the TCC/automation state for the bundle identity.
9. **RUNBOOK §2** describes what actually happens: the channels, the thresholds, the heartbeat, what
   `notify_failures`/`not configured` mean, and what a missing heartbeat means.

## Scope
- An ntfy push channel: stdlib `urllib` HTTPS POST to `https://ntfy.sh/<topic>`. Alarms, recoveries and the
  "SONAR stopped" notice go out on both channels.
- The topic is a secret, stored outside the repo (Application Support `.env` or Keychain; Architect decides). It never
  appears in logs, health output or the repo. Use a long random topic.
- Generic text only: what is wrong and for how long. No balances, positions, P&L, symbols or prices.
- A daily heartbeat ("SONAR alive, build vX") at a fixed local time. If it does not arrive, that itself is the alarm.
- `/api/health` gets per-channel failure counts (`notify_failures`) and channel state (`ok` / `failing` /
  `not configured`). A failing push channel is reported as a problem.
- A way to send a test alarm on demand (a CLI flag or script). It never touches the live book.
- The macOS banner stays as the local channel. Its timeouts are counted, not removed.
- Timestamp the watchdog's log lines (`server.py:287`).
- Diagnose the osascript timeouts and write up the evidence (measure 8). The plist is **not** changed here.
- Correct RUNBOOK §2.

## Non-goals
- **Changing the plist's priority** (`ProcessType`/`Nice`). That belongs to the separate tier-3 item 2 spec,
  "starved engine". This spec only supplies the diagnosis it needs.
- **A separate probe job outside the agent** (the audit's preferred design). See Open question 1.
- Other monitoring-table signals: health latency, settle age and coverage alarms, backup age (P2), the Drive job and
  `com.andreas.gdrive-backup` (P2-5 §6), version drift, log rotation and `handle_error` noise (the rest of P2-2).
- Self-hosting ntfy, accounts or reserved topics, other channels (mail, Pushover, Telegram).
- Any change to trading, scoring or the book. Real money stays out of scope.
- **A "guard halted" alarm.** The execution guard's halt is not wired into the live agent today. If a broker-paper
  executor is ever wired in, "guard halted" becomes a health kind that pushes, with its own fixed phrase (domain P3-2).

## Challenge to the request
The owner chose in-agent ntfy, and it fixes the observed failure (the alarm text existed but never left the Mac). It
does **not** cover several failures: a dead or hung process, a Mac that is asleep or logged out, or a starved
watchdog thread. In each case the thing that should send the alarm is the thing that is broken. The heartbeat is the
only cover, and it detects silence only after up to ~24 h, and only if the owner notices that a push did *not* come.
The audit says "the probe must not be the agent itself". This spec is the smaller, honest first step, not the full fix.
The RUNBOOK must state the 24 h blind spot plainly.

## Risks
- **The secret leaks** through logs, health, crash text or a committed `.env`. Secure phase required (network + secret).
- **Network blocks the watchdog.** A slow POST on the watchdog thread delays the next check or the exit-3 restart.
  Delivery needs a hard timeout and must not hold up `exit_fn(3)` for long. Architect decides.
- **Alarm storms** on a crash loop. The existing hourly "stopped" throttle must cover the push too, or the phone
  gets one push a minute.
- **The 30-day clean run.** Shipping this means restarting the live agent before 2026-11-09. The owner decides when.
- **Diagnosis disturbs the live agent.** Throwaway launchd jobs must use their own labels and never touch
  `~/Library/Application Support/SONAR*`.
- **Third-party host.** If ntfy.sh is down or rate-limits, pushes are lost. That is counted, not hidden.

## Open questions for the owner
1. Should we also build the separate 5-min probe job (a launchd `curl /api/health` and ntfy push) as a follow-up P1?
   It closes the "agent is the probe" gap. Recommended: yes, as its own spec after this one.
2. What text may leave the Mac? Is "no price poll for 14 min" acceptable? May the heartbeat include "scored N hours,
   coverage X%" (the audit's suggestion), or only "alive, build vX"?
3. What time should the heartbeat go out, and should it also go out when there are open problems (marked as such)?
4. Where should the topic live: Application Support `.env` (simple) or Keychain (safer, but needs a `security` call)?
5. Should a failed push be retried once after N minutes, or only counted?
6. When may the live agent be restarted onto this build during the 30-day run?
7. Should ntfy priority be 4 (high) for alarms and 2 (low) for the heartbeat and recoveries?

## Owner decisions (2026-10-14, Define gate approved)
1. The external 5-minute probe is a follow-up P1, written as its own spec.
2. Off-machine text is limited to an allowlist: the problem kind, its duration, the build version, the state of each channel, and a "SONAR (paper)" title prefix. Never balances, P&L, positions, symbols, prices, model scores, exception or server text, or paths (domain P1-1). A test enforces this for every health kind (domain P2-1).
3. Heartbeat:
   - Wording: "SONAR (paper) alive, build vX", plus optionally "paper run: N of M hours recorded (X%) since <date>".
   - Sent daily, even when problems are open, listing the kinds of those problems.
   - Send time is an operations choice.
4. The topic is stored in the Keychain.
5. A failed push is retried once, then counted.
6. The live agent is restarted onto this build only with the owner's explicit yes at Release.
7. ntfy priority is 4 for alarms and 2 for heartbeats and recoveries.

Also adopted from the domain review:
- P3-2: if a broker-paper executor is ever wired in, add a non-goal note that "guard halted" becomes a pushing health kind.
- P3-3: the test alarm reads no book, health or price data.

## Architecture
*Architect, 2026-10-14. ADR: `docs/adr/0005-ntfy-push-alarm-keychain-topic.md`.*

**Owner gate: yes.** This section changes all three things that trigger the gate:
- **State:** the `alarm.json` schema.
- **Concurrency:** new sender threads, and a bounded wait before `exit_fn(3)`.
- **Module boundaries:** a new module `sonar/alarm.py`, new wiring in `Handler` and `Watchdog`, and a new `main.py` flag.

The playbook `docs/playbooks/architect.md` is `status: baseline` (last reviewed 2026-10-10), so it is stale.

### Current code (anchors)
- **`notify_macos`** (`sonar/server.py:236-252`):
  - It runs `osascript` synchronously on the caller's thread, with `timeout=10`.
  - On failure it prints to stderr with no timestamp.
  - It returns nothing, so the caller cannot count failures.
- **`ALARM_AFTER_S` / `WATCH_EVERY`** (`server.py:221-222`).
- **`_stopped_notice_due`** (`server.py:258-269`):
  - It reads `user_data_base()/alarm.json`.
  - It then **overwrites** the file with `{"stopped_at": now}` alone.
- **`Watchdog`** (`server.py:272-323`):
  - `step` (`:292-315`) calls `self.notify` inline in three places: "stopped" at `:297`, the alarm at `:311` and the recovery at `:315`.
  - It builds the alarm body from `problems[].text` (`:301`, `:310-311`). This is the domain P1-1 leak.
  - The default `log` (`:287`) has no timestamp.
  - `run` (`:317-323`) logs `{exc}` raw.
- **Wiring** (`server.main`, `server.py:346-352`): `Watchdog(live, engine)` uses the default `notify_macos`. `Handler.live` is set at `:352`.
- **`/api/health`** (`server.py:155-160`) returns `self.live.health()` with status 200 or 503.
- **`Live.health`** (`sonar/core.py:1519-1563`):
  - Problem kinds are `loop` (`:1541`), `poll` (`:1549-1550`, with `last_poll_error` appended at `:1548`), `scan` (`:1553`, `:1555`) and `settle` (`:1559`).
  - It returns `build` (`:1563`), which is `version.provenance()` (`core.py:210`).
  - `HEALTH_MAX_POLL_AGE = 120` (`core.py:108`).
- **Headless entry:** `main.headless` (`main.py:152-167`) and the dispatch at `main.py:255-260`.
- **Existing watchdog tests:** `tests/test_health.py:99-200`. They inject `notify`, `exit_fn` and `log`, and `conftest` redirects `user_data_base` (`tests/conftest.py:40-95`).

### Approach
**1. New module `sonar/alarm.py`.** It is stdlib only. It must not import `core`, `engine` or `portfolio`, so the test-alarm path cannot reach the book. It contains:

- **`Event`.** A frozen dataclass:
  - `kind`: one of `loop | poll | scan | settle | other | stopped | recovery | heartbeat | test`.
  - `duration_s`: `float | None`.
  - `open_kinds`: a tuple of kinds, for the heartbeat.
  - `urgent`: a bool. It is True for the "stopped" notice: one attempt only, no retry.

  It has **no free-text field**, which is the domain P1-1 fix by construction.
- **`render(event, build, channel_states) -> (title, body, priority)`.** This is the only place push text is made.
  - The title is `"SONAR (paper) needs attention"`, `"SONAR (paper) stopped"`, `"SONAR (paper) working again"`, `"SONAR (paper) alive"` or `"SONAR (paper) test alarm"`.
  - The body is built from fixed per-kind phrases in `PHRASES`. For example: `poll` gives "no successful price poll for at least {m} min", `settle` gives "no hour settled for at least {h} h", and `loop` gives "the engine loop stopped". An unknown kind gives "other problem".
  - After the phrase come `build {v}` and `channels: banner {state}, ntfy {state}`.
  - `{v}` must match `^v?[0-9][0-9A-Za-z.+-]{0,31}$`, else it is replaced by `unknown`. The duration is a whole number of minutes or hours.
  - Priority is 4 for an alarm or `stopped`, and 2 for `recovery`, `heartbeat` and `test` (Owner decision 7).
  - The heartbeat body is "SONAR (paper) alive, build vX; open problems: poll, settle" (or "open problems: none"), followed by the channel states. The optional "recorded hours" line from Owner decision 3 is **deferred**. It is the only allowlisted field that reads engine data, and it can be added later behind the same allowlist test.
- **`Channel` protocol** with `name`, `configured`, and `send(title, body, priority, timeout) -> bool`. The method raises nothing.
  - **`BannerChannel(run=subprocess.run)`.** This is today's `notify_macos` logic moved here, including `_plain` and argument passing (`server.py:225-252`). It returns True on rc 0. It is `unavailable` off darwin. It gets the full local text, not the push body, so the banner behaviour on this Mac is unchanged (measure 3).
  - **`NtfyChannel(topic, opener=None)`.**
    - It sends `Request("https://ntfy.sh/" + topic, data=body.encode("ascii", "replace"), method="POST")` with headers `X-Title`, `X-Priority` and `Content-Type: text/plain`.
    - The opener has `ProxyHandler({})` plus a no-redirect handler, in the same style as `core._follow_opener` (`core.py:66-71`).
    - `timeout=10`. Any 2xx is success. It never reads or logs the response body.
    - When `topic` is None, it is `not configured` and `send` is never called.
- **`read_topic(run=subprocess.run) -> (topic | None, reason)`.**
  - It runs `["/usr/bin/security", "find-generic-password", "-s", "com.netrunner3000.sonar.ntfy", "-a", "topic", "-w"]` with `timeout=5`.
  - It validates the result against `^[A-Za-z0-9_-]{24,64}$`.
  - The reason is one of `ok | absent | invalid | keychain error | timeout`. It is never the value and never `security`'s stderr.
- **`Notifier(channels, log, clock=time.time)`.** It owns per-channel state and one sender thread per channel. See Threading below.
  - `send(event, local_text)` queues the event on every configured channel.
  - `states() -> dict` gives the health block.
  - `drain(deadline_s)` waits for the queues to empty.
  - `redact(s)` replaces the topic with `[topic]`. Every log line the notifier and the watchdog write goes through `redact`. This is defence in depth: no code path is meant to put the topic in text.
- **`Heartbeat(path, localtime=time.localtime)`.** It holds the persisted schedule. See State below.
- **`test_alarm(argv) -> int`.** The CLI entry. See Test alarm below.
- **`ts()`.** Returns `datetime.now().astimezone().isoformat(timespec="seconds")` (for example `2026-10-14T09:00:03+02:00`), the prefix for every alarm and watchdog log line (measure 5).

**2. Changes to `sonar/server.py`.**
- `notify_macos` stays as a thin wrapper over `BannerChannel`, so existing imports and tests keep working.
- `Watchdog.__init__` takes `notifier=` instead of `notify=`. The old `notify=` keyword stays as an adapter for the existing tests until they are migrated.
- **Inside `step`:**
  - The alarm builds `Event(kind, duration_s=now - bad_since[k])` for each due kind. If several kinds are due in one tick, it sends one event with `open_kinds` set, and the push names every kind.
  - The local log keeps today's full text: `f"SONAR {ts()}: needs attention: " + "; ".join(texts)`.
  - The recovery and "stopped" paths do the same.
  - `self.log`, including the `run` exception line at `:323`, gets the `ts()` prefix and `redact`.
  - `step` calls `self.heartbeat.due(now)` after the health check (see State).
- A new function `agent_health(live, notifier, now)` returns `live.health(now)`, extended with:
  - `"notify": notifier.states()`;
  - a problem `{"kind": "notify", "text": "the ntfy alarm channel is failing (N failures)"}` when ntfy is configured and `failing`;
  - a problem `"an alarm reached no channel"` when the last alarm event was delivered nowhere.

  The `Handler` (`:155-160`, via a new class attribute `Handler.notifier`) and `Watchdog.step` both call it. **`core.Live.health` is not changed**, so the GUI and `core` stay unaware of alarms.
- **`notify` is health-only.** It is excluded from the watchdog's alarm set and from `_was_alarmed`. Alarming about a failing alarm channel through the alarm channels would loop: undelivered → problem → alarm → delivered → clear → "working again". It still makes `/api/health` return 503, and the heartbeat lists it.
- **Banner failures are counted, not a problem.** They show in `notify.banner` but do not cause a 503. The banner is the local channel and is known to be flaky (spec Scope). Making it a problem would turn health red on 45 of 47 alarms.
- **`main()`:**
  - Calls `topic, why = alarm.read_topic()` before the threads start. This blocks for at most 5 s at agent start, and only then.
  - Logs one line: `SONAR <ts>: push alarms: ntfy configured` or `... ntfy not configured (absent)` (measure 3).
  - Builds the `Notifier`, passes it to the `Watchdog`, and sets `Handler.notifier`.

**3. `main.py`.** It gets a `--test-alarm` dispatch before `--headless` (`main.py:255-260`), which calls `alarm.test_alarm`. `sonar/server.py`'s `__main__` gets nothing; one entry is enough.

**/api/health shape.** The block is added beside the existing fields. It never contains the topic:
```json
"notify": {"banner": {"state": "ok|failing|unavailable", "failures": 0, "consecutive": 0,
                      "last_ok_at": null, "last_fail_at": null, "in_flight_s": null},
           "ntfy":   {"state": "ok|failing|not configured", "reason": "ok|absent|invalid|keychain error|timeout",
                      "failures": 0, "consecutive": 0, "last_ok_at": null, "last_fail_at": null,
                      "in_flight_s": null, "dropped": 0}}
```
- `failures` is the spec's `notify_failures`: events not delivered after the retry, counted since the process started.
- A channel's `state` is decided in this order:
  1. `failing` if its last event failed, or if a send has been in flight longer than 30 s. The 30 s rule exists because DNS resolution is not covered by the urllib timeout.
  2. Otherwise `ok` if it has delivered anything, or if nothing has been sent yet.
- The counts are kept in memory. A restart resets them, and the log keeps the history.

### Threading
- **One daemon sender thread per configured channel,** each with a `queue.Queue(maxsize=16)`. A hung `osascript` therefore never delays the ntfy push, and the reverse is also true.
- **`Notifier.send` never blocks.** It uses `put_nowait`. If a queue is full, the event is dropped and counted in `dropped` and `failures`.
- **No network or subprocess call happens on the watchdog thread.** The only exception is the bounded "stopped" path below. A 15 s tick stays a 15 s tick.
- **Per event on ntfy:**
  1. Try once (`timeout=10`).
  2. On failure, wait `NTFY_RETRY_AFTER_S = 20`. The wait is an `Event.wait` that stops when the notifier stops.
  3. Try again. A second failure is counted (Owner decision 5).
  4. `urgent` events skip the retry.

  The worst case is 10 + 20 + 10 = 40 s, which is inside the spec's 60 s delivery budget.
- **The banner gets one try only** (`timeout=10`, as today), and failures are counted.
- **State updates** go through one `threading.Lock` per notifier. `states()` is called from `Handler` threads and takes a copy under the lock.
- **The exit-3 path** (`server.py:294-299`):
  1. `if _stopped_notice_due(now): notifier.send(Event("stopped", urgent=True)); notifier.drain(STOP_FLUSH_S)`.
  2. Then `exit_fn(3)`.

  `STOP_FLUSH_S = 12` (one 10 s attempt plus slack). The exit is delayed by at most 12 s, and only when the notice is due (at most once an hour). launchd's `ThrottleInterval 60` holds the restart longer than that anyway. `os._exit` kills the daemon senders if they are still busy.
- **Crash-loop throttling.** `_stopped_notice_due` gates the **event**, before it reaches any channel, so the hourly limit covers ntfy and the banner together. In the alarm path, the `alarmed` set (`server.py:303-309`) still means one push per kind until that kind clears.

### State and migration
- **`alarm.json`** (in `user_data_base()`, beside the book):
  - Old: `{"stopped_at": <epoch>}`.
  - New: `{"stopped_at": <epoch>, "heartbeat_day": "YYYY-MM-DD", "heartbeat_at": <epoch>}`.
- **Writes.** Every write is read-merge-write: `paths.read_preferences` then `paths.write_atomically` (`paths.py:131-147`, `:173`). `_stopped_notice_due` changes from overwrite to merge, or it would erase the heartbeat keys.
- **Single writer.** The watchdog thread is the only writer in a process. Sender threads never write files. One agent per `SONAR_DATA` is an existing invariant (RUNBOOK §3), so no file lock is added.
- **Migration.**
  - None is needed forward: a missing key means "never sent".
  - On rollback, the old build drops the heartbeat keys. That causes at most one duplicate heartbeat (ADR 0005).
  - A corrupt or non-object file reads as `{}` (`paths.py:173-185`). The result is one extra heartbeat or "stopped" notice, never a crash.
- **Heartbeat schedule.** `HEARTBEAT_AT = (9, 0)`, local time.
  - The owner left the time to operations. 09:00 is waking hours, when a missing push gets noticed. A Mac asleep at 09:00 sends on wake, and a late heartbeat is itself information.
  - `Heartbeat.due(now)` is True when `localtime(now) >= today 09:00` and `heartbeat_day != today`. The day is a local date string, so DST changes and a clock set back cannot fire twice on the same date.
  - The day is persisted **when the event is queued**, not when it is delivered. A crash loop after 09:00 therefore sends one heartbeat, not one per restart. A heartbeat lost to a failed push is not re-sent that day; its absence on the phone is the alarm.
  - The file is read once, when the watchdog's `Heartbeat` is built, and cached in memory after that. Disk is touched only when a heartbeat is sent.
  - The heartbeat goes out in every engine mode (driving, waiting, following). It lists the open problem kinds, including `notify`. Mode is **not** in the allowlist, so it is not pushed. See Questions for the owner.

### Test alarm: CLI flag, not an endpoint
**Chosen:** `SONAR.app/Contents/MacOS/SONAR --test-alarm`. From a checkout, `python main.py --test-alarm`.

**What it does:**
- It reads the Keychain topic.
- It sends `Event("test")` synchronously on each channel, with the retry.
- It prints one line per channel: `ok`, `failing (HTTP 4xx / timeout / ...)` or `not configured (absent)`. The topic is never printed.
- It exits 0 only if ntfy delivered.
- Its build string comes from `version.info()` only.
- It never imports `core`, never calls `paths.ensure_dirs`, and never reads or writes `SONAR_DATA`. P3-3 is enforced by a test that imports `alarm` in a subprocess and asserts that `sys.modules` has no `sonar.core`, `sonar.engine` or `sonar.portfolio`.

**Why not a localhost endpoint:**
1. It would be a new route on a server whose threat model is cross-site POSTs and DNS rebinding (`server.py:38-46`). Any page that got past the guard could spam the phone.
2. It only works while the live agent is running, and it would make the live agent do work during the 30-day run.
3. A CLI works with no agent at all, so the owner can test before the restart that Owner decision 6 gates.

**Gap:** the CLI runs in the owner's Terminal session, not in the agent's launchd context, so it proves the topic and the phone, not the agent's Keychain access. That is proved by the agent's startup log line (`ntfy configured`), by `notify.ntfy.reason == "ok"` in `/api/health`, and by measure 6(b), the scheduled heartbeat sent by the agent itself.

### Failure modes
| Failure | Behaviour |
|---|---|
| ntfy.sh down, 429 or 5xx | Retry once, then count. `notify.ntfy` is `failing`. A `notify` problem makes health 503. The local log line names the HTTP status, never the URL. |
| DNS or TLS hangs past the timeout | The sender thread is stuck. `in_flight_s > 30` shows `failing`. The queue fills, then events are dropped and counted. The watchdog is unaffected. |
| `osascript` hangs or times out | Banner `failing`, counted. ntfy is unaffected (separate thread). Health is not 503 for the banner alone. |
| Keychain locked or `security` prompts | 5 s timeout → `not configured (timeout)` at start. Logged once. Behaviour as today. Needs a restart to pick up a topic. |
| Topic leaks into text | `render` takes no text. `redact` covers log lines. Measure 4 test. |
| Crash loop | One "stopped" event an hour on all channels (`_stopped_notice_due`). Exit delayed by at most 12 s. |
| Process dead, hung, Mac asleep, or user logged out | **Not covered**, because the sender is the thing that is broken. The heartbeat's absence after about 24 h is the only signal. The external probe follow-up closes this. RUNBOOK §2 must say so. |
| `alarm.json` unwritable | Today: `except OSError: pass`. Same for the heartbeat. Result: a possible duplicate "stopped" notice or heartbeat, never a missed alarm. |
| A new health kind added in `core` | `render` maps it to "other problem". The allowlist test fails until someone adds a phrase. |

### Alternatives rejected
- **Sending on the watchdog thread with a short timeout.** A hung DNS lookup ignores the urllib timeout and would stop every later check. Rejected for the per-channel senders.
- **One sender thread for both channels.** The banner's 10 s timeouts (45 of 47) would delay every push by 10 s, and a hung `osascript` would block ntfy. Rejected.
- **Putting channel state into `core.Live.health`.** `core` would gain alarm knowledge that the GUI never uses. Rejected for `server.agent_health`.
- **Alarming on the `notify` kind.** Circular, and it flaps (see Approach 2). Rejected; health-only.
- **The topic in `.env`, or Keychain through Security.framework.** See ADR 0005.
- **Persisting the heartbeat day only on successful delivery.** Each crash-loop restart after 09:00 would push again until one succeeded. Rejected.

### Latency (measure 7): the budget in the spec is short
- A `poll` problem first appears when the last good poll is older than `HEALTH_MAX_POLL_AGE = 120 s` (`core.py:108`, `:1546-1547`).
- The watchdog then waits `ALARM_AFTER_S["poll"] = 600 s` from **that** moment (`server.py:304-306`).
- Worst case from the fault starting: 120 + 600 + 15 (tick) + 40 (delivery with retry) = 775 s, about **12.9 min**. That is over the 12 min in measure 7.
- The architect does not change the alarm thresholds in this spec. Recommendation: the owner amends measure 7 to **14 min**.
- The alternative is to start the `poll` clock at `last_poll_ok_at`. That would change the behaviour the RUNBOOK documents, so it needs the owner's yes.

### Diagnosis plan (measure 8): never touches the live agent or its data
- **Evidence file:** `docs/audit/alarm-delivery-osascript-diagnosis.md`. This is the spec's name. The briefing said `alarm-delivery-diagnosis.md`, but the spec name wins.
- **Run directory:** everything runs from a scratch directory, `D=$(mktemp -d)`, with a temporary `SONAR_DATA=$D/data` wherever SONAR code is imported.
- **launchd jobs:** each throwaway job has its own label `com.netrunner3000.sonar-diag.<variant>`. It is loaded with `launchctl bootstrap gui/$(id -u) $D/<variant>.plist` and removed with `launchctl bootout gui/$(id -u)/<label>`.
- **What is never done:** nothing goes into `~/Library/LaunchAgents`. The live agent is never `kickstart`ed, `bootout`ed or signalled. `~/Library/Application Support/SONAR*` is never read or written. Only `agent.err.log` is read, and only read.

**Read-only facts:**
1. `uptime`, and `ps -o pid,ni,pri,%cpu,etime,command -p $(pgrep -f 'SONAR.*--headless')` (the agent's real nice and priority).
2. `launchctl print gui/$(id -u)/com.netrunner3000.sonar | grep -Ei 'processtype|nice|state'`.
3. `codesign -dv --verbose=2 /Applications/SONAR.app` (the ad hoc identity).
4. The timeout counts and timestamps from `agent.err.log`.
5. `log show --last 2d --predicate 'subsystem == "com.apple.TCC" OR process == "osascript" OR process == "usernoted"' --style compact`, filtered to the minutes of logged timeouts.
6. Notification settings for Script Editor and SONAR (screenshot). `TCC.db` is read only if Full Disk Access already allows it; otherwise "not readable".

**Probe script `$D/probe.sh`.** It runs `osascript -e 'display notification "diag N" with title "SONAR diag"'` N = 10 times. For each run it logs to `$D/<variant>.log`:
- the ISO start time and end time;
- the elapsed ms;
- the return code;
- stderr;
- `uptime`.

It uses its own 15 s cap, so a 10 s timeout and a slow success can be told apart.

**Variants:**
- (a) Interactive Terminal: the baseline.
- (b) `launchctl asuser $(id -u) $D/probe.sh`: the agent's user and session.
- (c) A launchd job with `ProcessType Background` and `Nice 5`, copied from the live plist.
- (d) The same job with `ProcessType Standard` and no `Nice`.
- (e) Optional: (c) and (d) again while `yes > /dev/null` runs on every core for 2 min, to reproduce load. It is killed after.
- (f) Optional: the same Python path the agent uses, `SONAR_DATA=$D/data .venv/bin/python -c "from sonar.server import notify_macos; ..."`, inside job (c).

**Reading the results:**
- If (c) times out and (d) does not, at similar load, the cause is **starvation**.
- If every launchd variant fails fast or times out regardless of priority, and TCC log lines appear, the cause is **TCC**.
- Otherwise: **both** or **not determined**, with the numbers.

The write-up records every command, the raw output excerpts, N, the per-variant timeout rate and the verdict. The plist is not changed here (spec Non-goals).

### Test strategy
All new tests go in `tests/test_alarm.py`, with the watchdog ones in `tests/test_health.py`. None of them use a real Keychain, real network or real `osascript`. Fakes are injected: `run=` for `security` and `osascript`, `opener=` for ntfy (a fake whose `open(req, timeout)` records `req.full_url`, the headers and the data, or raises), `clock=` and `localtime=`. Senders are flushed with `notifier.drain(5)`. A guard fixture makes `urllib.request.urlopen` and `socket.create_connection` raise, so an accidental real call fails the test.

| Measure | Test |
|---|---|
| 1 fallback | Banner `run` raises `TimeoutExpired`, with a fake opener returning 200. One due `poll` alarm → `drain` → exactly one request, to `https://ntfy.sh/<topic>`, with `X-Title` starting "SONAR (paper)" and `X-Priority: 4`. The body passes the allowlist check. `agent_health()["notify"]` shows banner failures 1 and ntfy failures 0. |
| 2 ntfy fails | The opener raises `URLError`, then returns 500, then raises `HTTPError(404)`. Two attempts are made (the retry), `failures` goes up, `step` returns normally, the `notify` problem is present and the status is 503. A further `step` still alarms on a new kind. An `urgent` event makes one attempt only. |
| 3 not configured | `read_topic` with fake `security` rc 44 (item not found) → `absent`. The guard fixture shows no network call. The banner is called exactly as today (argument test `test_health.py:150-162` still passes). Health shows `not configured`. The startup log has exactly one `ntfy not configured` line with an ISO prefix. |
| 4 secret | Random 40-character topic. Run alarm, recovery, stopped, heartbeat and test events, a failing opener whose exception message contains the full URL, and an `HTTPError` with `url=` set. Then search `capsys` out and err, the injected log list, `json.dumps(agent_health())`, the `Handler` `/api/health` response body, and `str()` of every exception raised. The topic must not appear anywhere. |
| 5 timestamps | The default `Watchdog` log and `Notifier` log, captured from stderr. Every line matches `^SONAR \d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[+-]\d\d:\d\d: ` and parses with `datetime.fromisoformat`. |
| 6 phone | Owner evidence only. The test alarm is the CLI. The heartbeat must come from the agent. |
| 7 latency | Manual. A second instance with a temporary `SONAR_DATA` and port 8788, polls broken by an unreachable proxy injected through its environment. Record the fault start and the phone arrival. See Latency above. |
| 8 diagnosis | Manual, as planned above. |
| 9 RUNBOOK | Review. |
| Allowlist (P1-1, P2-1) | Parametrized over every kind in `ALARM_AFTER_S`, plus `notify`, `stopped`, `recovery`, `heartbeat`, `test` and an unknown kind. `live.health` is monkeypatched so every problem text is `"AAPL $187.42 at /Users/as/x https://evil.example/?q=1 ValueError: secret"` and `last_error` is the same. The event is driven end to end through `Watchdog.step` into the fake opener. Assertions: the title starts "SONAR (paper)"; the body is pure ASCII and matches the closed grammar `PHRASES` plus build plus channels; there is no `$`, `/`, `http`, `AAPL`, `Error`, `secret` or `:` outside the fixed "channels:" label; the only upper-case run is `SONAR`; and every digit run is a duration, the build or a count. A second assertion checks that every kind `core.Live.health` can emit (grep `"kind": "` in `core.py`, made into a test constant with a sync check) has a `PHRASES` entry. |
| Heartbeat | Fake `localtime`: before 09:00 → not due. 09:00 → sent once, with `open problems: poll` when poll is open. A second `Watchdog` (restart) built on the same scratch `alarm.json` on the same day → not sent. Next day → sent. `stopped_at` survives a heartbeat write, and the reverse (the merge). |
| Threading | The fake banner `run` blocks on an `Event` → `step()` returns in under 0.5 s and ntfy is still delivered. With ntfy blocked, 17 sends give 1 dropped. Exit path: with a hung opener, `step` with a dead engine thread calls `exit_fn(3)` within `STOP_FLUSH_S + 1`. Three restarts in one hour give exactly one ntfy request (extending `test_health.py:172-183`). |
| Test-alarm isolation (P3-3) | Subprocess `python -c "import sonar.alarm, sys; ..."` asserts that `sonar.core`, `sonar.engine` and `sonar.portfolio` are not in `sys.modules`. `test_alarm()` with fakes and `SONAR_DATA` pointing at an empty temp dir leaves that directory empty. |

**Mutation checks for QA:** drop the retry; push `text` instead of the phrase; persist the heartbeat on delivery instead of on queueing; overwrite `alarm.json` instead of merging; skip `_stopped_notice_due` for ntfy; remove the `notify` exclusion from alarming. Each must turn a test red.

Run both suite modes (native and `QT_QPA_PLATFORM=offscreen`) per app-context. `sonar/alarm.py` has no Qt, but `test_health.py` runs in both.

### Questions for the owner at this gate
1. Amend measure 7 to 14 min, or start the `poll` alarm clock at the last good poll (a behaviour change)? See Latency.
2. Should the heartbeat include the engine mode word (`driving`, `waiting` or `following`)? It is operational, but it is not in Owner decision 2's allowlist. Default: no.
3. Heartbeat at 09:00 local: is that acceptable?

## Owner decisions (2026-10-14, Architect gate approved)
1. Measure 7 is amended to **14 min**, because the worst case is about 12.9 min. Alarm timing is unchanged.
2. The heartbeat goes out daily at 09:00 local.
3. The engine-mode word is left out of the heartbeat.
4. Two domain P3s are fixed in Build:
   - A: the allowlist grammar allows exactly the fixed labels "channels:" and "open problems:", and keeps the bare-colon ban everywhere else.
   - B: an Event carries a duration for each kind, with a test for two kinds due at once.
   - P3-2 also adds a Non-goals line: if a broker-paper executor is wired in, "guard halted" becomes a health kind that pushes.

## Owner decisions (2026-10-19, Review)
Taken on the review round 1 findings (`docs/audit/alarm-delivery-{code-reviewer,qa-engineer,security-engineer,domain-finance}.md`):
- **(a) "An alarm reached no channel"** is raised only when ntfy is configured and the alarm failed on it. It clears
  as soon as a later event is delivered on ntfy, or once the alarmed kinds clear. Banner-only installs never go
  red from banner timeouts. (Code review P1-1, QA Q9/Q15.)
- **(b) ntfy "failing" decays** after 1 h without a new failure. Health then shows `ok`, but with `last_fail_at`,
  and `failures` stays visible. RUNBOOK §2 says so. (Code review P2-3.)
- **(c) Security P3-2 is accepted.** The unauthenticated topic and the ntfy.sh terms (about 12 h cache, possible
  IP and topic logging, Firebase delivery; https://docs.ntfy.sh/privacy/) are recorded in ADR 0005. "Reserved topic
  plus access token" goes on the backlog next to the external-probe follow-up.

## Owner decisions (2026-10-19, round 3)
Taken on the round-3 review findings:
- **CR P3-1.** With ntfy configured, `stopped_at` is saved only when the "stopped" notice reached the phone (ntfy).
  A banner alone does not count. With no topic, a banner delivery counts. The health text is now "an alarm did not
  reach the phone".
- **CR P3-2, accepted residual.** A crash loop with the network down waits up to `STOP_FLUSH_S` (12 s) for the
  undelivered "stopped" notice on every restart, before exit 3. It is bounded, and launchd's `ThrottleInterval 60`
  dominates the restart cadence anyway. RUNBOOK §2 says so.
- **CR P3-3.** The test-suite guard is hardened against `sh -c` payloads, `;`/`&&`/`|` chains and `$(...)`.

## Verification
The full reports are in `docs/audit/alarm-delivery-qa-engineer.md` (rounds 1-3) and `docs/audit/alarm-delivery-code-reviewer.md` (rounds 1-3, plus a final check).
- **Round 3:** QA PASS.
- **Test suite:** 2823 passed, 3 skipped in both native and offscreen modes, after the final P3 pass.
- **Mutation testing:** 16 of 18 mutations were caught in round 3. The 2 that survived (M7 and M8) are closed or equivalent. M7 was fixed and tested in the final pass.
- **Branch coverage:** `sonar/alarm.py` 96%, `sonar/server.py` 95%.

| # | Measure | Status |
|---|---|---|
| 1-5 | Fallback, ntfy failure, not configured, secret never shown, timestamps | Met by tests |
| 6 | Phone screenshots | Needs owner evidence (Release checklist) |
| 7 | Latency of 14 min or less | Needs owner evidence (Release checklist) |
| 8 | Diagnosis | Met: `docs/audit/alarm-delivery-osascript-diagnosis.md` (CPU starvation, not TCC) |
| 9 | RUNBOOK §2 | Met |

## Release checklist (owner)
Do these in order. Nothing here touches the live book until step 8.

1. **Notification settings.** Screenshot System Settings > Notifications for Script Editor and SONAR (diagnosis
   item 6). Save it under `docs/audit/alarm-delivery-evidence/`.
2. **Make a topic** (a long random name that works like a password):
   `python3 -c "import secrets; print(secrets.token_urlsafe(30))"`. Clear the terminal afterwards.
3. **Store it in the Keychain:** `security add-generic-password -s com.netrunner3000.sonar.ntfy -a topic -w`.
   Keep `-w` last and type the topic at the prompt (twice), never on the command line.
4. **Subscribe** to the topic in the ntfy app on your phone.
5. **Test:** `/Applications/SONAR.app/Contents/MacOS/SONAR --test-alarm` (from a checkout:
   `python main.py --test-alarm`). Expect `ntfy: ok` and exit code 0, and the push on the phone.
6. **Measure 6 evidence.** Save two phone screenshots in `docs/audit/alarm-delivery-evidence/`: (a) the test
   alarm from step 5, and (b) one 09:00 heartbeat sent by the agent itself (after step 8).
7. **Measure 7 latency,** on a *second* instance only: a temporary `SONAR_DATA` (for example `$(mktemp -d)`), another
   port (8788), and polls broken through its own environment (an unreachable proxy). Never the live agent or its
   data. Write down when the fault started and when the push arrived; the bar is 14 min. Stop the instance after.
   After 09:00 it also sends its own "alive" push within its first 15 s: that one is not measure 6(b).
8. **Restart the live agent onto this build only with your explicit yes** (Owner decision 6), through
   `./build_app.sh --install` (RUNBOOK §5).
9. **Confirm the agent can read the topic:** its start line in `~/Library/Logs/SONAR/agent.err.log` reads
   `push alarms: ntfy configured`, and `curl -s 127.0.0.1:8787/api/health` shows `notify.ntfy.reason` equal to
   `"ok"`.
