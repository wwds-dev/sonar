# SONAR runbook

For the owner, at a terminal, when something looks wrong. Real money is out of scope, so
"wrong" means the paper record is stale, missing or damaged. Written from
`docs/audit/closing-sre-release.md`; steps marked **(not drilled)** have not been rehearsed.

## 1. What runs where

| Thing | Value |
|---|---|
| Agent (launchd) | `com.netrunner3000.sonar`, runs `<checkout>/.venv/bin/python main.py --headless` |
| API | `127.0.0.1:8787` (loopback only) |
| Data directory | `~/Library/Application Support/SONAR` (`SONAR_DATA`): `state.json`, `portfolio.json`, daily `*.bak.<date>` (7 kept) |
| Off-disk copy | the directory in `$SONAR_BACKUP_DIR` or in `<data>/backup-to` (30 kept) |
| Logs | `<checkout>/data/logs/agent.out.log`, `agent.err.log` (not rotated) |
| Three versions | the checkout (`git log -1`), the installed app (`/Applications/SONAR.app`, About box), the running agent |

The agent runs the **checkout's working tree**, not the installed app. Uncommitted edits load on
any restart. Check `git status` before restarting it. `install_agent.sh` refuses a tree with
uncommitted tracked changes (in it or in `sonar/macro`, `sonar/playmaker`) unless given
`--allow-dirty`; `/api/health` reports the loaded code as `build: {version, commit, dirty, source,
nested}`, read at the agent's start (`dirty: null` means it could not be told).

## 2. Is it healthy?

```bash
./scripts/install_agent.sh --status
curl -s 127.0.0.1:8787/api/health
```

Healthy: `"ok": true`, `"problems": []`, and `build.dirty` false with the `build.commit` you expect. HTTP 503 means a problem: `poll` (no price for
minutes), `settle` (no hour settled for hours) or `loop` (the engine loop ended). The agent posts
a macOS notification after 10 minutes of a poll problem; that banner only reaches you at this Mac.

## 3. Stalled, crash-looping or silent

```bash
launchctl kickstart -k gui/$(id -u)/com.netrunner3000.sonar     # restart the agent
tail -50 data/logs/agent.err.log                                # why it stopped
git status --short                                              # is the tree what you think it is?
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
4. Start the agent again (`./scripts/install_agent.sh` from the checkout) and compare trade count and
   bankroll in the app with what the backup held.

To rehearse without touching the live book, point a source run at a scratch directory:
`SONAR_DATA=/tmp/sonar-drill python main.py --selftest` after copying the pair in, then load it with
`Portfolio` and `Engine`. A backup is only a backup once it has been loaded.

## 5. Release

Clean tree, CI green on that exact commit, `./run-tests.sh -q` and
`QT_QPA_PLATFORM=offscreen ./run-tests.sh -q` both pass, `./build_app.sh --install`, open the app, check
the version and that the stamp reads clean, restart the agent, record the build and commit. Do not
install from a red commit. There is no `.prev` rollback yet: keep the previous `.app` aside by hand
before installing.

## 6. Open owner decisions

Developer ID signing and notarization; where the off-disk copy really leaves this disk (the
Google Drive job `com.andreas.gdrive-backup` failed to start on 2026-10-11); running the agent from
a clean snapshot instead of the working tree; an always-on host; an off-machine alarm channel.
