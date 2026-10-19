# SRE release notes: alarm-delivery (v2.362, d548361)

Date 2026-10-19. Role `sre-release`. Worktree `.claude/worktrees/cool-leavitt-1b6b6d`, branch
`claude/pensive-benz-f395cc`, HEAD `d548361` (v2.362). The branch contains the installed v2.340 (`8e7d024`) and
`origin/master` (`be1b183`). Playbook `docs/playbooks/sre-release.md` is `status: baseline` (last-reviewed
2026-10-10). By the AGENTS.md rule that counts as stale. Radar note reused: `docs/company/radar-notes/2026-10-12-release.md`
(7 days old, no advisory affecting this build path).

**Status: built and smoke-tested. NOT installed.** I stopped at the install gate. Installing restarts the live
agent, and that needs a separate owner yes.

## 1. Preconditions

| Check | Result |
|---|---|
| CI green on `d548361` | **Not met.** The branch is not on `origin` (`git ls-remote` empty), so CI has never run on this commit. The last green `tests` and `security` runs are on `be1b183` (master, 2026-10-14). RUNBOOK §5 asks for CI green on the exact commit. |
| Suite in both modes | Not re-run by SRE. The spec's Verification records 2823 passed and 3 skipped in native and offscreen modes (QA round 3). |
| Clean tree | **Not met.** `docs/company/activity.jsonl` is modified: the phase log, appended to by this and other sessions. It is not bundled, but it makes the stamp `dirty: true`. |
| Nested repos | `sonar/macro` and `sonar/playmaker` in this worktree are plain copies with no `.git`. `diff -rq` (excluding `.git`, `__pycache__` and `.DS_Store`) shows they are identical to the main checkout's clean repos (macro `b3fa3e2`, playmaker `1162ba5`). `version._nested()` skips directories without `.git`, so the stamp's `nested` is `{}` and the bundle does not name the nested commits. |
| Packaging delta vs installed v2.340 | `git diff --stat 8e7d024 HEAD -- packaging scripts build_app.sh requirements.*` shows no change (only `main.py`, +6 lines). The launchd plist template and the install scripts are the same ones that installed v2.340. |
| `SONAR.spec` | Not in the tree. PyInstaller generates it on each build, and `*.spec` is git-ignored. app-context names it as if it were a source file. |

## 2. Worktree setup

- No `.venv` in the worktree. I created the symlink `.venv -> /Users/as/Documents/lab/active/sonar/.venv`, which has
  PyInstaller 6.22.2 and PySide6 6.11.2. Git shows it as untracked (`?? .venv`), because `.venv/` in `.gitignore` does not match a
  symlink. Do not stage it. Remove it with `rm .venv` (not `rm -r`) when done.
- The PyInstaller analysis path puts the worktree on `sys.path`, so the worktree's `sonar/` is what got bundled.
  Confirmed by the self-test's resource base and by the stamp's commit.
- `stamp_version.py` ran from the worktree: `Stamped v2.362 (d548361)`, `dirty: true`. The stamp's `root` is the
  worktree path. If the worktree is deleted later, the installed app's staleness line falls back to "no checkout
  to compare against".
- `build_app.sh` regenerated `assets/icon.icns` and `static/testplan.html`. Both came out byte-identical (no git diff).

## 3. Build

Command: `./build_app.sh` (no `--install`), exit 0.

- Artefact: `dist.noindex/SONAR.app` in this worktree, v2.362, 98 MB. `CFBundleShortVersionString` is 2.362.
- Seal: `Signature=adhoc`, `flags=0x2(adhoc)`, `TeamIdentifier=not set`. `codesign --verify --deep --strict` passes.
  No Developer ID or notarization (owner decision 2026-10-10).
- Built-in self-test: "All checks passed".
- **Side effect on the live data directory.** `build_app.sh` runs `--selftest` with the default data directory, so the
  self-test wrote and then deleted `~/Library/Application Support/SONAR/cache/__selftest__` (`main.py:73-76`).
  Nothing else there was touched. `install_app.sh` does the same through `check_app.sh` at install time.
  Proposal: make `build_app.sh` run the self-test with `SONAR_DATA` set to a temp directory whose path contains
  "Application Support".

## 4. check_app.sh

Run against the built bundle with a scratch data directory. The self-test requires the substring "Application Support" in the
state path (`main.py:68`), so I used `<scratchpad>/Application Support/smoke` and never touched the real directory.

| Command | Exit | Output |
|---|---|---|
| `scripts/check_app.sh dist.noindex/SONAR.app "<scratch>/Application Support/smoke"` | 1 | "Refusing: the agent would run code its commit does not name." (dirty stamp, as designed) |
| same with `--allow-dirty` | 0 | Seal ok, stamp present, `env -i` self-test passes |

## 5. Headless smoke test (second instance, never the live one)

`env -i HOME=$HOME SONAR_DATA="<scratch>/Application Support/smoke" dist.noindex/SONAR.app/Contents/MacOS/SONAR --headless --host 127.0.0.1 --port 8788`,
started at 13:11:23.

| Check | Result |
|---|---|
| `/api/health` answers | HTTP 200 by 13:11:32 (within about 9 s; empty book). Again at 13:11:57. |
| `ok` / `problems` | `true` / `[]`, both times |
| `build` | `{"version": "v2.362", "commit": "d548361", "dirty": true, "source": "baked", "nested": {}}` |
| `notify` block | present. `ntfy: {"state": "not configured", "reason": "absent", "failures": 0, ...}`, `banner: {"state": "ok", "failures": 0, ...}` |
| Start line timestamped | `SONAR 2026-10-19T13:11:23+01:00: push alarms: ntfy not configured (absent)` |
| Heartbeat | `SONAR 2026-10-19T13:11:38+01:00: heartbeat queued; open problems: none`. Started after 09:00, so it went out in its first 15 s, as a **banner only** (no topic). `banner.last_ok_at` was 13:11:38. |
| `--test-alarm`, no topic | Confirmed beforehand that `security find-generic-password -s com.netrunner3000.sonar.ntfy -a topic` finds nothing. Output `ntfy: not configured (absent)`, `banner: ok`, **exit 1** in 0.2 s. Exit 1 is by design: it exits 0 only when a push was delivered. No push was sent. One local banner was posted. |
| Stop | SIGTERM, process gone within 2 s, port 8788 free afterwards |
| Live agent during all of this | `launchctl print` state running, pid 1196. `/api/health` on 8787: `ok true`, `problems []`, v2.340 `8e7d024`. Unchanged before and after. |

Not done: no Keychain item created, no push sent, the release smoke test from app-context (one scan, one paper trade,
quit, relaunch in the GUI) not run, measure 7 latency not run (owner checklist step 7).

Operator error, recorded: a stray `SONAR --version` probe started a GUI instance (pid 51884). `--version` is not
a flag the app knows, so it falls through to the GUI. That instance ran on the scratch `SONAR_DATA`, so it had its own lock
and was not on the live book. It was killed with SIGTERM about 2 minutes later.

## 6. Findings for the owner

1. **Release checklist step 5 cannot run as written before step 8.** The installed v2.340 has no `--test-alarm`
   (`git show 8e7d024:main.py` has no match). `main.py` dispatches on `"--x" in sys.argv` and falls through
   to `SonarApp(...)`, so `/Applications/SONAR.app/Contents/MacOS/SONAR --test-alarm` **opens a v2.340 window**
   instead of testing. Before install, use the built bundle:
   `dist.noindex/SONAR.app/Contents/MacOS/SONAR --test-alarm` (from this worktree).
2. **Do Keychain steps 2-4 before the install.** The agent reads the topic once, at start (RUNBOOK §2). An install
   before the Keychain item exists starts the agent at "not configured", and it needs another restart to pick the topic up.
3. **CI has not run on `d548361`** and the stamp is dirty (finding in §1). These are the only RUNBOOK §5 preconditions
   not met.
4. The bundle does not name its nested-repo commits (`nested: {}`). The contents match the main checkout's clean repos.
5. `build_app.sh` self-test probe in the live data directory (§3).

## 7. What install does to the running agent

From `scripts/install_app.sh` and `scripts/install_agent.sh`. `./build_app.sh --install` calls `install_app.sh` after a
**fresh rebuild**. It does not install the artefact tested here, and it deletes `dist.noindex/` afterwards. Today
`~/Library/LaunchAgents/com.netrunner3000.sonar.plist` points at `/Applications/SONAR.app/Contents/MacOS/`, so
`agent_on_app=1`. The agent is loaded, so `agent_running=1`.

1. `check_app.sh <src> ~/Library/Application Support/SONAR`: seal, stamp, clean check (refuses unless
   `--allow-dirty`), and `env -i` `--selftest` against the **live** data directory (cache probe write and delete). Any failure
   here leaves the app and the agent untouched.
2. `cp -R` to `/Applications/.SONAR.app.new`, then codesign-verify the copy.
3. `launchctl disable gui/$UID/com.netrunner3000.sonar`, then `launchctl bootout`. **The live agent (pid 1196) is
   terminated by SIGTERM.** Neither build installs a SIGTERM handler (`sonar/server.py`: only `KeyboardInterrupt`), so it
   dies at once, with no "stopped" notice (v2.340 has no alarm code anyway). It is never running while the bundle
   is swapped: there is no swap under a running process.
4. Swap: `mv SONAR.app .SONAR.app.old`, `mv .SONAR.app.new SONAR.app`, `rm -rf .SONAR.app.old`. **The old bundle is
   deleted.** There is no automatic rollback copy.
5. `SONAR_APP=/Applications/SONAR.app install_agent.sh`: `check_app.sh` again on the installed copy (second live
   self-test), rewrites the plist from the template (unchanged since v2.340), `launchctl bootout`, `enable`, then
   `bootstrap`, retried 6 times at 2 s. That starts the new agent (RunAtLoad), then sleeps 2 s and prints `--status`.
   - Any failure after step 3 leaves the agent **stopped and disabled**, and the script says so.
   - If a SONAR window is open from `/Applications`, it keeps running the old build and may take the engine lock while the
     agent is down. None is open now (`pgrep`: only pid 1196).
6. On its first start the new agent logs `push alarms: ntfy ...`. Started after 09:00 with no heartbeat day yet
   recorded in `alarm.json`, it sends the day's heartbeat within about 15 s: a banner if there is no topic, otherwise a
   push and a banner.

**Known false alarm.** `--status` curls `127.0.0.1:8787/api/health` with `-m 3`, about 2 s after bootstrap. The live agent
loads a full book, and its first answer can take minutes, so `build: not answering` right after install is expected.
Poll before judging (commands below).

## 8. Proposed commands (owner runs them, or says yes to each)

From `/Users/as/Documents/lab/active/sonar/.claude/worktrees/cool-leavitt-1b6b6d`.

**A. Rollback copy of the current v2.340 (reads `/Applications`, does not touch the agent):**

```bash
mkdir -p ~/SONAR-rollback.noindex/v2.340
ditto /Applications/SONAR.app ~/SONAR-rollback.noindex/v2.340/SONAR.app
codesign --verify --deep --strict ~/SONAR-rollback.noindex/v2.340/SONAR.app && echo sealed
grep -E '"(build|commit|dirty)"' ~/SONAR-rollback.noindex/v2.340/SONAR.app/Contents/Resources/_build_info.json   # 340, 8e7d024, false
```

**B. Before install (recommended):**

- Either commit `docs/company/activity.jsonl` and rebuild with `./build_app.sh` for a clean stamp, then repeat the smoke
  test in §5, or accept the dirty stamp knowingly (the only dirty file is the phase log, which is not bundled).
- Push the branch and wait for green `tests` and `security` on the exact commit (RUNBOOK §5).
- Do release checklist steps 2-4 (Keychain topic and phone subscription). Do step 5 with the built bundle:
  `dist.noindex/SONAR.app/Contents/MacOS/SONAR --test-alarm` (expect `ntfy: ok` and exit 0).

**C. Install (restarts the live agent: needs the owner's explicit yes).** This installs the exact bundle tested above:

```bash
./scripts/install_app.sh dist.noindex/SONAR.app --allow-dirty    # drop --allow-dirty if rebuilt from a clean tree
# then wait for the first answer; "build: not answering" in the script's own status is the known false alarm
for i in $(seq 1 36); do c=$(curl -s -m 4 -o /dev/null -w '%{http_code}' 127.0.0.1:8787/api/health); [[ $c == 200 || $c == 503 ]] && break; sleep 5; done; echo "http=$c"
./scripts/install_agent.sh --status
curl -s 127.0.0.1:8787/api/health | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["ok"], d["problems"], d["build"], d["notify"]["ntfy"])'
grep "push alarms" ~/Library/Logs/SONAR/agent.err.log | tail -1
```

Expect `build.version` v2.362 and `build.commit` d548361. Expect `notify.ntfy.reason` `"ok"` if the Keychain item exists,
otherwise `"absent"`. Alternatively, `ALLOW_DIRTY=1 ./build_app.sh --install` rebuilds and then installs. That gives
the same result, but the artefact is not the one smoke-tested here.

**D. Rollback to v2.340 (also restarts the agent; v2.340's stamp is clean, so no `--allow-dirty`):**

```bash
./scripts/install_app.sh ~/SONAR-rollback.noindex/v2.340/SONAR.app
for i in $(seq 1 36); do c=$(curl -s -m 4 -o /dev/null -w '%{http_code}' 127.0.0.1:8787/api/health); [[ $c == 200 || $c == 503 ]] && break; sleep 5; done
curl -s 127.0.0.1:8787/api/health | python3 -c 'import json,sys; print(json.load(sys.stdin)["build"])'   # v2.340, 8e7d024
```

v2.340 ignores `alarm.json` and the Keychain item, so a rollback needs no state cleanup. The older
`~/SONAR-rollback.noindex/v2.296` (07f0c9e, clean) stays available the same way.

## 9. Cleanup state

- The smoke instance is stopped, and port 8788 is free.
- The scratch data is in the session scratchpad and holds nothing of the live book.
- `dist.noindex/` is kept for command C.
- The `.venv` symlink is kept for the `--status` python and any rebuild.
- Nothing was committed, pushed, tagged or installed.
