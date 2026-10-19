# SONAR runbook

For the owner, at a terminal, when something looks wrong. Real money is out of scope, so
"wrong" means the paper record is stale, missing or damaged. Written from
`docs/audit/closing-sre-release.md`; steps marked **(not drilled)** have not been rehearsed.

## 1. What runs where

| Thing | Value |
|---|---|
| Agent (launchd) | `com.netrunner3000.sonar`, runs `/Applications/SONAR.app/Contents/MacOS/SONAR --headless` (installed with `install_agent.sh`; `--checkout` runs `<checkout>/.venv/bin/python main.py --headless` instead) |
| API | `127.0.0.1:8787` (loopback only) |
| Data directory | `~/Library/Application Support/SONAR` (`SONAR_DATA`): `state.json`, `portfolio.json`, daily `*.bak.<date>` (7 kept) |
| Off-disk copy | the directory in `$SONAR_BACKUP_DIR` or in `<data>/backup-to` (30 kept) |
| Logs | `~/Library/Logs/SONAR/agent.out.log`, `agent.err.log` (not rotated); `<checkout>/data/logs/` in `--checkout` mode. `install_agent.sh --status` prints the path |
| Versions | the checkout (`git log -1`), the installed app (`/Applications/SONAR.app`, About box; the agent's code unless it was installed with `--checkout`), the running agent (`/api/health` `build`) |

The agent runs the **installed app**, so an edit in the checkout cannot reach it on a restart; a
new build reaches it only through `./build_app.sh --install`. That checks the new build first
(seal, clean stamp including `sonar/macro` and `sonar/playmaker`, `--selftest`), then disables and
stops the agent, swaps the app in with two renames, and starts the agent again, but only if it was
running. If anything fails after the stop, the agent stays stopped **and disabled** (it will not
start at login on a bad bundle) and the script says so; `./scripts/install_agent.sh` starts it.
`install_agent.sh` applies the same checks before it writes the plist.
`/api/health` reports the loaded code as `build: {version, commit, dirty, source, nested}`, read at
the agent's start (`dirty: null` means it could not be told).
In `--checkout` mode the agent runs the working tree: uncommitted edits load on any restart, and
the installer refuses a dirty tree (or nested repo) unless `--allow-dirty`.

## 2. Is it healthy?

```bash
./scripts/install_agent.sh --status
curl -s 127.0.0.1:8787/api/health
```

Healthy: `"ok": true`, `"problems": []`, and `build.dirty` false with the `build.commit` you expect. HTTP 503 means a problem: `poll` (no price for
minutes), `scan` (the board is not being rescanned), `settle` (no hour settled for hours), `loop` (the engine
loop ended) or `notify` (an alarm channel is failing, see below).

### Alarms: what reaches you, and when

The agent's watchdog checks health every 15 s. A problem that lasts past its threshold sends **one** alarm;
when every problem has cleared it sends one "working again". Nothing repeats in between.

| Problem | Alarm after | Worst case from the fault starting |
|---|---|---|
| `loop` | at once | about 1 min |
| `poll` | 10 min (the problem itself appears after 2 min without a price) | about 13 min |
| `scan` | 10 min | |
| `settle` | 75 min (a Mac waking from sleep shows it until the next hour settles) | |
| engine thread ended | at once: "SONAR stopped", then exit 3 and a launchd restart | at most one notice an hour gets through in a crash loop. With a topic, "through" means it reached the phone; with no topic, that the banner posted it. If it did not get through, the next restart tries again. The exit waits up to 12 s for it, so a crash loop with the network down waits up to 12 s on every restart (accepted), and the local banner is tried on every restart too |

Each alarm goes on two channels, each on its own thread, so a stuck one never holds up the other:

- **ntfy push to your phone** (`https://ntfy.sh/<topic>`). It says only what is wrong and for how long, the build,
  and the state of each channel, under the title "SONAR (paper) ...". It never says balances, positions, P&L,
  symbols, prices, error text or paths. A failed push is retried once after 20 s, then counted. The
  "SONAR stopped" notice gets one try only, because the agent is about to exit.
- **macOS banner** (`osascript`), only seen at this Mac. It carries the full local text. It is known to time out
  under load (`docs/audit/alarm-delivery-osascript-diagnosis.md`); its failures are counted, but a failing banner
  alone does not turn health red.

Every alarm, failure and the heartbeat is also a timestamped line in `~/Library/Logs/SONAR/agent.err.log`
(`SONAR 2026-10-14T09:00:03+01:00: ...`), with the full problem text.

**Heartbeat.** Every day at **09:00 local time** the agent pushes "SONAR (paper) alive, build vX; open problems:
...". It goes out even when problems are open, and lists their kinds. A Mac asleep at 09:00 sends it on wake.
**No heartbeat by about 09:15 means the agent is not able to tell you anything**: it is dead, hung, the Mac is
asleep or logged out, or the push channel is broken. Check §3.

**The blind spot.** The agent is its own alarm. If the process is dead or hung, the Mac is asleep or logged out,
or the watchdog thread is starved, nothing is sent, and the only sign is a missing heartbeat: up to about
24 hours of silence before you can notice. A separate probe outside the agent (an owner-approved follow-up, not
built yet) closes this gap. Until then, a missing 09:00 push is the alarm.

**Channel health in `/api/health`.** The `notify` block shows each channel:

```json
"notify": {"banner": {"state": "ok", "failures": 0, ...},
           "ntfy":   {"state": "not configured", "reason": "absent", "failures": 0, ...}}
```

- `state`: `ok`, `failing` (the last send failed less than an hour ago, or one has been in flight over 30 s),
  `not configured` (ntfy has no topic) or `unavailable` (the banner, off macOS). A failure with no new failure
  for an hour goes back to `ok`, and `last_fail_at` and `failures` still show it: look at those, not only at
  `state`.
- `failures` is `notify_failures`: events not delivered (after the retry) since the agent started. A restart
  resets the counts; the log keeps the history. `dropped` counts events thrown away because 16 were already waiting.
- `reason` (ntfy): `ok`, `absent` (no Keychain item), `invalid` (not 24-64 letters, digits, `-` or `_`),
  `keychain error` (for example, locked or denied) or `timeout`. The topic itself is never shown.
- A `notify` problem (503) means one of two things:
  - the ntfy channel is `failing`: a send failed within the last hour;
  - "an alarm did not reach the phone": with ntfy configured, an alarm failed to reach the phone, whether or not the
    banner showed it. This clears when a later push is delivered, or when the problems it was about clear.
- The banner never makes a `notify` problem. With no topic (`not configured`), banner timeouts are counted in
  `notify.banner` and health stays 200.

The agent logs one line at start: `push alarms: ntfy configured`, or `push alarms: ntfy not configured (<reason>)`.
It reads the topic once, at start: after changing the topic, restart the agent.

**Set up the push (once).** Make a long random topic, store it in the login Keychain, and subscribe to it in the
ntfy app on your phone:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(30))"     # prints a 40-character topic
security add-generic-password -s com.netrunner3000.sonar.ntfy -a topic -w
# -w last: security prompts for the value. Type the topic there (twice), e.g. <YOUR-40-CHARACTER-TOPIC>.
# Never pass it after -w on the command line, which would keep it in shell history.
```

`security` reads it for the agent (`security find-generic-password -s com.netrunner3000.sonar.ntfy -a topic -w`).
The item's access list trusts the Apple-signed `/usr/bin/security`, so a new SONAR build does not ask again.

What the Keychain does and does not protect:
- It keeps the topic out of the repo, the data directory and its backups, logs and `/api/health`.
- It does **not** keep it from other software running as you. Any process running as your user can run that same
  `security` command and read the topic without a prompt, while the login Keychain is unlocked.
- Anyone who knows the topic can read the pushes, and can also post fake ones, including a fake "alive". Keep it
  secret, and change it (and re-subscribe) if it leaks. Clear the terminal after generating it, because the
  generator prints it to the scrollback.
- ntfy.sh keeps messages for about 12 hours, may log IP addresses and topics, and delivers to phones through
  Google Firebase (https://docs.ntfy.sh/privacy/). Pushes say only what is wrong, for how long and the build.

**Test it.** This sends one test push and one banner, and reads nothing but the Keychain topic (no book, no data
directory):

```bash
/Applications/SONAR.app/Contents/MacOS/SONAR --test-alarm      # from a checkout: python main.py --test-alarm
```

It prints `ntfy: ok`, `ntfy: failing (HTTP 4xx / timeout / ...)` or `ntfy: not configured (absent)`, then the
banner's state, and exits 0 only if the push was delivered. It runs in your Terminal session, so it proves the
topic and the phone, not that the agent can read the Keychain: the agent's start line and the 09:00 heartbeat
prove that.

## 3. Stalled, crash-looping or silent

```bash
launchctl kickstart -k gui/$(id -u)/com.netrunner3000.sonar     # restart the agent
tail -50 ~/Library/Logs/SONAR/agent.err.log                     # why it stopped
./scripts/install_agent.sh --status                             # program, build, logs
```

- Never start a second headless agent by hand; two engines on one state file is what the engine lock
  prevents. Remove a stale `engine.lock` only after confirming its pid is dead (`ps -p <pid>`).
- A Mac asleep or logged out runs nothing. The hours are lost, not recoverable. Write the gap down.

## 4. Restore the book from a backup **(file steps drilled once from the off-disk copy; the Google Drive leg was never tested)**

`state.json` and `portfolio.json` are a pair: restore both from the **same date**.

1. Stop the agent and quit the app:
   ```bash
   launchctl bootout gui/$(id -u)/com.netrunner3000.sonar
   ```
2. Keep the broken pair aside, never delete it:
   ```bash
   cd ~/Library/Application\ Support/SONAR
   mkdir -p ../SONAR-broken && cp -p state.json portfolio.json ../SONAR-broken/
   ```
3. Copy a same-date pair over the live files (local `.bak.<date>` here, or the off-disk copy):
   ```bash
   cp -p state.json.bak.<date> state.json && cp -p portfolio.json.bak.<date> portfolio.json
   ```
4. Start the agent again (`./scripts/install_agent.sh`) and compare trade count and
   bankroll in the app with what the backup held.

To rehearse without touching the live book, point a source run at a scratch directory:
`SONAR_DATA=/tmp/sonar-drill python main.py --selftest` after copying the pair in, then load it with
`Portfolio` and `Engine`. A backup is only a backup once it has been loaded.

## 5. Release

Clean tree, CI green on that exact commit, `./run-tests.sh -q` and
`QT_QPA_PLATFORM=offscreen ./run-tests.sh -q` both pass, `./build_app.sh --install`, open the app, check
the version and that the stamp reads clean, check `./scripts/install_agent.sh --status` shows the
new build (the install restarted the agent), record the build and commit. Do not
install from a red commit. There is no `.prev` rollback yet: keep the previous `.app` aside by hand
before installing.

## 6. Open owner decisions

Developer ID signing and notarization; where the off-disk copy really leaves this disk (the
Google Drive job `com.andreas.gdrive-backup` failed to start on 2026-10-11); an always-on host; the probe outside
the agent that closes the alarm blind spot in §2 (the ntfy push itself is decided and built, not yet installed). (Decided 2026-10-11: the agent runs from the installed `SONAR.app`, option A in
`docs/specs/t2-1-agent-provenance.md`; built, and live once the owner reinstalls the agent.)
