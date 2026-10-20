# alarm-delivery: why the agent's osascript banners time out

Spec `docs/specs/alarm-delivery.md`, success measure 8. Engineer, 2026-10-14, 21:07-21:16 local (+01:00).

## Verdict: starvation (verified). TCC is not the cause.

- At the same machine load, a `ProcessType Background` + `Nice 5` launchd job hit the 10 s limit on **6 of 10**
  `osascript` banners. 4 of those 10 also hit the probe's own 15 s cap. A `ProcessType Standard` job hit it on
  **0 of 10**, and so did the interactive shell (0 of 10).
- The live agent's real failures show the same pattern in the unified log: `osascript` crawls through every step,
  and its TCC request is answered (no prompt, no denial) only after the 10 s timeout has already killed it.
- No TCC prompt or denial was found for the agent's `osascript`. The TCC request is a `preflight=yes` query
  for `kTCCServiceListenEvent`, and `tccd` answers it with `authValue=1` without a prompt. It is slow only
  because everything is slow at background priority on this machine.

The fix belongs to the separate "starved engine" spec (tier-3 item 2): the plist's `ProcessType`/`Nice`. This
spec does not change the plist (Non-goals). With this build, the push no longer depends on the banner: each
channel has its own thread, and a banner failure is counted, not hidden.

## Ground rules kept
- The live agent `com.netrunner3000.sonar` (pid 12034) was not kickstarted, booted out or signalled.
- `~/Library/Application Support/SONAR*` was not read or written. The live plist in `~/Library/LaunchAgents`
  and `agent.err.log` were only read.
- The throwaway jobs ran from a scratch directory `$D` with their own labels `com.netrunner3000.sonar-diag.{c,d}`.
  They were loaded with `launchctl bootstrap gui/501 $D/<v>.plist` and removed with `launchctl bootout`. Nothing
  went into `~/Library/LaunchAgents`. `SONAR_DATA` pointed at `$D/data`, but no SONAR code ran in the probes.
- Every probe run posted a visible "SONAR diag" banner. None of them raised a permission prompt.

## 1. Read-only facts

```
$ uptime
21:07  up 9 days,  2:46, 3 users, load averages: 97.50 80.73 70.16

$ ps -o pid,ni,pri,%cpu,etime,command -p $(pgrep -f 'SONAR.*--headless')
  PID NI PRI  %CPU  ELAPSED COMMAND
12034  5   4   0.0 19:38:03 /Applications/SONAR.app/Contents/MacOS/SONAR --headless --host 127.0.0.1 --port 8787

$ launchctl print gui/$(id -u)/com.netrunner3000.sonar | grep -Ei 'spawn type|nice|throttle'
	nice = 5
	spawn type = background (5)

$ plutil -p ~/Library/LaunchAgents/com.netrunner3000.sonar.plist      # excerpt
  "Nice" => 5
  "ProcessType" => "Background"
  "ThrottleInterval" => 60

$ codesign -dv --verbose=2 /Applications/SONAR.app                    # excerpt
Identifier=com.netrunner3000.sonar
CodeDirectory v=20400 size=6000 flags=0x2(adhoc) hashes=181+3 location=embedded
Signature=adhoc
TeamIdentifier=not set
```

The agent runs at `PRI 4`, compared with 20 for a normal process. The signature is ad hoc, so every build has a new
code identity.

## 2. What the agent's log says

```
$ grep -c "could not post a notification" ~/Library/Logs/SONAR/agent.err.log
45
$ grep -c "timed out after 10 seconds" ~/Library/Logs/SONAR/agent.err.log
45
$ grep -c "notification refused" ~/Library/Logs/SONAR/agent.err.log
0
```

- The log has 47 notification attempts ("needs attention", "working again" or "engine thread ended"), and 45 of
  them failed. Every failure was the 10 s timeout. None was an AppleScript refusal (rc != 0), which is what a
  TCC denial would look like.
- The watchdog lines have no timestamp, so failure times come from the nearest earlier timestamped
  `poll failed` line. The failures fall between 2026-10-12 15:18 and 2026-10-14 18:17.
- This build fixes the timestamps: every watchdog and alarm line now starts `SONAR <ISO time>:`.

## 3. The live agent's own failure, in the unified log

`/usr/bin/log show --start "2026-10-14 18:14:00" --end "2026-10-14 18:20:00" --predicate 'subsystem ==
"com.apple.TCC" OR process == "osascript" OR process == "usernoted" OR process == "tccd"' --style compact`
returned 24,774 lines. The agent's "working again" banner at 18:17:10 ran as `osascript` pid 72555. Its full trace:

```
18:17:10.197 osascript[72555] activating connection ... com.apple.analyticsd          <- start
18:17:10.322 osascript[72555] activating connection ... com.apple.security.syspolicy.exec
18:17:10.326 osascript[72555] [com.apple.xprotect:xprotect] Using XProtect rules location: ...XPScripts.yr
18:17:11.013 osascript[72555] invalidated ... (syspolicy.exec done, 0.7 s)
18:17:11.351 .. 11.897 osascript[72555] (Security) SecKeyVerifySignature / SecTrustEvaluateIfNecessary (x4)
18:17:12.842 osascript[72555] activating connection ... com.apple.coreservices.launchservicesd
18:17:14.915 osascript[72555] (CoreServicesInternal) CFURLResolveBookmarkData                 <- 2.1 s later
18:17:16.464 osascript[72555] (TCC) TCCAccessRequest() IPC                                     <- 6.3 s after start
18:17:18.591 tccd[636] activating connection ... com.apple.tccd.system.peer[72555]             <- 2.1 s to accept
18:17:19.795 tccd[636] REQUEST: ... sender_pid=72555 ... function=TCCAccessRequest
18:17:19.809 tccd[636] AUTHREQ_CTX: msgID=72555.1, ... service=kTCCServiceListenEvent, preflight=yes
18:17:19.809 tccd[636] AUTHREQ_ATTRIBUTION: ... responsible={TCCDProcess: identifier=com.netrunner3000.sonar,
             pid=12034, ... binary_path=/Applications/SONAR.app/Contents/MacOS/SONAR}, requesting={... com.apple.osascript ...
18:17:23.758 tccd[636] AUTHREQ_RESULT: msgID=72555.1, authValue=1, authReason=5, ... error=(null)
18:17:23.758 tccd[636] invalidated because the client process (pid 72555) either cancelled the connection or exited
```

- The agent's `subprocess.run(timeout=10)` killed `osascript` at about 18:17:20.2. The TCC answer came 3.5 s after that.
- The answer was not a prompt and not a denial: it was a preflight query, answered with `authValue=1`.
- Every step before TCC was already slow: about 6.3 s to reach the TCC request. On a Standard-priority process the
  whole run takes 0.2-0.6 s (§4).
- The same window shows `usernoted` itself cancelling work for another app ("Timeout of 10.0 reached. Cancelling
  work", 5 times, `bundle=com.anthropic.claudefordesktop`). The notification daemon is also slow under this
  load. That is a side observation, and it did not stop the Standard-priority probes.

## 4. The probes

`$D/probe.py` runs this N = 10 times, 2 s apart:
`/usr/bin/osascript -e 'display notification "diag N" with title "SONAR diag"'`.
Each run has its own 15 s cap, so a 10 s timeout and a slow success can be told apart. For each run it logs the ISO
start and end, the elapsed ms, the rc, stderr and `uptime`. `$D/probe.sh` execs it with the checkout venv's
Python. The plist for (c):

```xml
<key>Label</key><string>com.netrunner3000.sonar-diag.c</string>
<key>ProgramArguments</key><array><string>$D/probe.sh</string><string>c</string><string>10</string></array>
<key>RunAtLoad</key><true/>
<key>EnvironmentVariables</key><dict><key>SONAR_DATA</key><string>$D/data</string></dict>
<key>ProcessType</key><string>Background</string><key>Nice</key><integer>5</integer>
```

(d) is the same plist with `<key>ProcessType</key><string>Standard</string>` and no `Nice`. Both were bootstrapped
one right after the other, so they ran at the same time:

```
$ launchctl bootstrap gui/501 $D/c.plist   -> rc=0
$ launchctl bootstrap gui/501 $D/d.plist   -> rc=0
$ launchctl print gui/501/com.netrunner3000.sonar-diag.c | grep -Ei 'spawn type|nice|state'
	state = xpcproxy                     <- still being spawned 3 s after bootstrap
	nice = 5
	spawn type = background (5)
$ launchctl print gui/501/com.netrunner3000.sonar-diag.d | grep -Ei 'spawn type|nice|state'
	state = running
	spawn type = daemon (3)
...
$ launchctl bootout gui/501/com.netrunner3000.sonar-diag.c   -> rc=0
$ launchctl bootout gui/501/com.netrunner3000.sonar-diag.d   -> rc=0
$ launchctl list | grep sonar
12034	0	com.netrunner3000.sonar                                  <- only the live agent remains
```

| Variant | Context | N | min ms | mean ms | max ms | over 10 s | hit 15 s cap | load average (1 min) during the runs |
|---|---|---|---|---|---|---|---|---|
| (a) | this interactive shell | 10 | 191 | 315 | 609 | 0 | 0 | 101-106 |
| (b) | `launchctl asuser 501 $D/probe.sh b 10` | 10 | 225 | 277 | 365 | 0 | 0 | 101-108 |
| (c) | launchd job, `Background` + `Nice 5` (the live plist) | 10 | 4,704 | 12,144 | 19,453 | **6** | **4** | 77-109 |
| (d) | launchd job, `Standard`, no `Nice` | 10 | 1,285 | 2,701 | 4,888 | 0 | 0 | 111-118 |

Raw lines, abridged (`uptime` trimmed to the 1-min load):

```
c run=1  start=21:11:24.125 ms=8026  rc=0     load 109.38
c run=2  start=21:11:34.574 ms=19453 rc=CAP15 load 100.36
c run=3  start=21:12:09.172 ms=19246 rc=CAP15 load 93.42
c run=4  start=21:12:30.783 ms=15552 rc=CAP15 load 94.10
c run=5  start=21:12:48.792 ms=15476 rc=CAP15 load 92.98
c run=6  start=21:13:06.513 ms=4704  rc=0     load 91.70
c run=7  start=21:13:13.386 ms=6159  rc=0     load 87.70
c run=8  start=21:13:21.947 ms=6000  rc=0     load 86.28
c run=9  start=21:13:30.818 ms=12552 rc=0     load 82.90
c run=10 start=21:13:46.083 ms=14273 rc=0     load 77.22
d run=1  start=21:10:37.498 ms=4888  rc=0     load 114.56
d run=2  start=21:10:44.710 ms=3344  rc=0     load 115.47
...
d run=10 start=21:11:23.352 ms=1694  rc=0     load 111.33
```

**Reading the results.**
- (d) ran at a *higher* load (111-118) than (c) (77-109), and every (d) run finished in under 5 s.
- (c) also took about 47 s just to spawn: its first run started at 21:11:24, while (d)'s started at 21:10:37.
- The probe's own bookkeeping was slow under (c) too. Run 2 measured 19.5 s against a 15 s cap, so the kill and
  reap took another 4.5 s.
- The unified log for (c) run 2 (`osascript` pid 45787) shows it entering the XProtect script check at
  21:11:35.528 and logging nothing more before the kill. Run 3 (pid 50542) crawled through the same steps as the
  agent's pid 72555.
- (c)'s TCC requests were answered with no prompt, as before. For example, `osascript[44970]`:
  `TCCAccessRequest() IPC` at 21:11:31.088, and `AUTHREQ_RESULT: msgID=44970.1, authValue=1, authReason=5` 8 ms later.
- That matches the plan's rule: "(c) times out and (d) does not, at similar load: starvation".

(b) is weaker evidence than planned. Run without root, `launchctl asuser` ran the probe as a child in this same
session. It did not run it in the agent's background spawn class. So (b) proves only that the agent's user and
GUI session can post banners at Standard priority.

## 5. Not done, and why
- **(e) the artificial-load rerun** (`yes > /dev/null` on every core). Skipped: the machine was already at load
  77-118 from other work during (c) and (d), so the load did not need reproducing.
- **(f) SONAR's own `notify_macos` inside job (c).** Skipped: (c) already isolates the priority, and the banner
  code's argument passing is covered by tests.
- **TCC.db.** Not readable without Full Disk Access:
  ```
  $ sqlite3 -readonly "$HOME/Library/Application Support/com.apple.TCC/TCC.db" "select service,client,auth_value,auth_reason from access where client like '%sonar%' or client like '%osascript%' or client like '%ScriptEditor%';"
  Error: unable to open database "/Users/as/Library/Application Support/com.apple.TCC/TCC.db": unable to open database file
  ```
- **Notification settings for Script Editor and SONAR (screenshot): needs owner.** System Settings ->
  Notifications -> Script Editor (banners from `osascript` are attributed to it) and SONAR. If banners are off
  there, a successful `osascript` would still show nothing. That would be a separate, silent failure, and it
  does not explain the timeouts.

## 6. What this means for the owner
- The banner will keep timing out under load while the agent runs as `Background` + `Nice 5`. The ntfy push in
  this build does not depend on it, because it runs on its own thread.
- The same starvation can delay the agent's other work, including the push thread and the watchdog itself.
  That is what the "starved engine" spec has to weigh when it decides on `ProcessType`.
- Any change to the live plist needs the owner's yes and a restart of the live agent during the 30-day run
  (spec Owner decision 6). None was made here.
