# SONAR operations / release audit

Role: sre-release. Date: 2026-10-10. Build audited: v2.148 (commit 704dfad, checkout HEAD 6424857).
Method: read `build_app.sh`, `SONAR.spec`, `.github/workflows/tests.yml`, `packaging/`, `scripts/`,
`VERSIONING.md`, `main.py`, `sonar/{core,enginelock,paths,engine,server}.py`, `ui/tray.py`; inspected the live
agent (`launchctl print`, `ps`, `curl 127.0.0.1:8787`), `~/Library/Application Support/SONAR`, `codesign`/`spctl`.
Nothing was built, installed, tagged, pushed or modified. "Not reproduced" marks findings from code reading only.

## Observed state (evidence)

- Agent is running: `launchctl` state=running, pid 15941, started 05:23 today, lock file in
  `~/Library/Application Support/SONAR/engine.lock` names that pid, `/api/state` answers `status: live`.
  It runs `.venv/bin/python main.py --headless` from the checkout (plist lines 24-25), not the installed app.
- `data/logs/agent.out.log` shows 8 start banners; `agent.err.log` is 0 bytes. No rotation, no timestamps.
- The checkout's own `data/` is archived (`data/ARCHIVED-2026-10-08.txt`); its `data/engine.lock` (pid 68945)
  is a leftover. The live book is `~/Library/Application Support/SONAR` (state.json 05:12, portfolio.json 04:54).
- Installed app: `codesign -dv` = ad-hoc, no TeamIdentifier; `spctl -a` = "invalid Info.plist (plist or
  signature have been modified)". No Time Machine destination configured (`tmutil destinationinfo`).
- Both nested repos are clean and in sync with `origin/main`; main repo `master` has only untracked `.claude/`,
  `AGENTS.md`, `CLAUDE.md`, `docs/`.

## Findings

### P0 — silent failures that look like health

**P0-1. A dead poll thread leaves a healthy-looking process.**
`sonar/server.py:146` runs `live.run` on a daemon thread while the main thread blocks in `serve_forever()`
(`server.py:164`). `Live.run` (`sonar/core.py:629-646`) calls `engine_lock.acquire()` and `self.warmup()`
outside the `try/except Exception`, and the loop only catches `Exception`. If the thread ends for any reason
(an exception in `warmup`, `_wait_for_lock` returning, a `BaseException`), the HTTP server keeps running, the
process stays alive, launchd's `KeepAlive` (plist 48-52) never fires, and the lock still names a live pid so
the app cannot take over. Result: no polling, no settling, no error. Not reproduced.
Fix: a supervisor in `server.main` that exits non-zero when the engine thread dies (`thread.is_alive()` check in
the main loop, or `sys.exit(1)` from a wrapper in the thread) so launchd restarts the agent.

**P0-2. The staleness alarm cannot fire when the loop is dead.**
`run_health.stale` is computed inside `_build()` (`core.py:909`, `engine.py:671`) using the `now` of the last
successful poll. A frozen loop therefore leaves the last snapshot's `stale: false` in place for ever. The
tray alert (`ui/tray.py:175-195`) reads that same field, and it only exists while the GUI is open. Nobody
checks `snap["now"]` against wall-clock. The only detector that works today is a person noticing the equity
curve stopped. Fix: compute age at read time (`time.time() - snap["now"]` and `last_settled_at` in the
`/api/state` handler and in the tray), and add the external check in P1-1.

**P0-3. Per-poll errors are swallowed without a log line.**
`core.py:637-639` stores `{"status": "error", "detail": str(exc)}` in the snapshot and prints nothing; there is
no `logging` or `traceback` anywhere in `core.py` (grep). `agent.err.log` is empty by construction. An exception
that fires every 4 s (`PRICE_EVERY`, `core.py:34`) would leave no trace after the next successful tick.
Fix: log with timestamp and traceback to stderr on the first failure and every N-th repeat; log recoveries.

### P1 — owner would not find out; recovery is manual

**P1-1. Monitoring today is: nothing that works when the app is closed.**
There is no `/api/health` (`curl /api/health` -> `not found`; routes at `server.py:53-110`), no heartbeat file,
no push channel (no osascript, mail, webhook or ntfy anywhere in `sonar/` or `ui/`). The one alert is a tray
balloon from the GUI (`ui/tray.py:184`), which requires the app to be running and the snapshot to be live (P0-2).
Fix (smallest): `/api/health` returning `{engine_thread_alive, last_poll_age_s, last_settled_age_s, lock_holder,
data_dir, version}` with HTTP 503 when stale; a second launchd job (every 15 min) that curls it and runs
`osascript -e 'display notification'` or posts to a push topic on failure and on recovery. Add a daily
"still alive" ping so silence is itself a signal.

**P1-2. The agent does not run when the owner is logged out, or when the Mac sleeps.**
`install_agent.sh:9-11` and the plist comment promise it "keeps it alive when you are not [logged in]". It is
bootstrapped into `gui/$(id -u)` (`install_agent.sh:31,99`), which exists only for a logged-in session; at the
login window nothing runs. Sleep halts polling too (no `caffeinate`, no power assertion; hours missed are
voided, per `engine.run_health`). Coverage will quietly be below 100% by construction. Fix: correct the claim;
decide whether to use `caffeinate -i` in `ProgramArguments`/`pmset` and say so in the runbook; record planned
gaps (lid closed overnight) in the readiness log instead of discovering them in `coverage_pct`.

**P1-3. The agent runs the working tree, not a release.**
plist `ProgramArguments` points at `<checkout>/main.py` with the checkout venv. Any uncommitted edit, branch
switch or concurrent agent session (AGENTS.md "concurrent sessions share this worktree") changes what the next
launchd restart (crash, reboot, `ThrottleInterval` 60 s) executes. A half-edited `sonar/core.py` can crash-loop
the experiment at 60 s intervals with the evidence buried in an unrotated log. The installed app and the agent
can also be different builds (the app is stamped, the agent is not; `/api/state` has no version). Fix: run the
agent from a tagged snapshot (installed bundle's `Contents/MacOS/SONAR --headless` already works through
`main.py`), or at minimum expose the running commit in `/api/health` and have `install_agent.sh` refuse a dirty tree.

**P1-4. Backups are single-disk, 7 days deep and unmonitored.**
`paths.daily_backup` (`paths.py:31-61`) copies `state.json`/`portfolio.json` to `*.bak.<date>` beside the
originals, keeping 7. Same volume, same directory, no off-machine copy, no Time Machine destination configured,
and `protocol.json`, `wording.json`, `providers.json` and the cache are not backed up. A backup is made only on
the first save of a day, so days without a save leave gaps (Application Support has no `.bak` for 10-02/03).
A disk failure, `rm -rf` of the directory, or a corruption that parses (so `read_state` accepts it) ages out of
the window in a week. `read_state` (`paths.py:90`) does recover from an unparseable file - good - but not
from a parseable-and-wrong one. There is no restore procedure or test of one. Fix: nightly `rsync`/`tar` of
`Application Support/SONAR` to a second location (the lab already has `com.andreas.gdrive-backup`; confirm it
covers this path - not verified), a 30-day tier, and a documented, rehearsed restore (runbook R3).

**P1-5. CI pulls unpinned, redirecting nested repos and unpinned dependencies.**
`tests.yml:31-38` checks out `Netrunner3000/sonar_macro` and `Netrunner3000/sonar_playmaker`, default branch HEAD.
The real remotes are `wwds-dev/...` (`git -C sonar/macro remote -v`); the GitHub API answers 301 for the old
owner, so CI works only while the redirect lives (and breaks if anyone ever recreates a repo under the old
name). No ref is pinned, so a push to either module repo can turn the main repo's CI red, or green against code
the working tree does not have; a local commit not pushed to the module repo is invisible to CI (and the reverse).
`requirements.txt:1` is `PySide6>=6.6` (local venv is 6.11.2), no lockfile, no hashes, `pytest` unpinned,
`actions/checkout@v4`/`setup-python@v5` by tag. Fix: use `wwds-dev/...` with an explicit `ref:` recorded in a
file (`sonar/macro.rev`) updated by a script, or convert to real submodules; add `requirements.lock`
(`uv pip compile`) and install from it in CI and `build_app.sh`.

### P2 — release hygiene

**P2-1. Not signed, not notarised, and the ad-hoc signature is already invalid.**
`SONAR.spec:34` `codesign_identity=None`, `entitlements_file=None`. `build_app.sh:78-79` edits `Info.plist` with
`plutil` after PyInstaller has ad-hoc signed the bundle, so `spctl -a` reports "invalid Info.plist (plist or
signature have been modified)" and `codesign` shows `Info.plist=not bound`. It launches today only because a
locally built app carries no quarantine attribute. If a copy is ever downloaded, AirDropped or restored from a
cloud backup, Gatekeeper will refuse it. No Developer ID, no hardened runtime, no `notarytool` step. Acceptable
for a single-owner local tool; recorded so it is a decision, not an accident. Fix (cheap): set the plist version
before signing (PyInstaller `--osx-entitlements`/post-step then `codesign --force --deep -s -`), so at least the
seal verifies; Developer ID + notarisation only if the app ever leaves this machine.

**P2-2. Build is not reproducible and not gated.**
`build_app.sh:17-18` activates `.venv` and runs `uv pip install -q pyinstaller` unpinned on every build;
`SONAR.spec` is git-ignored (`.gitignore` `*.spec`) while still checked in-tree as a generated artefact, so the
real recipe is the command line in the script (the spec can drift). `upx=True` in the spec is a no-op without
UPX but a risk if it is installed. The build does not require a green CI run, a clean tree (it warns only,
`stamp_version.py:33-41`), or the suite: the only gate is `--selftest`. The stamp records `dirty` but the
shipped v2.132 of 2026-10-08 already could not be traced to a commit. Fix: `build_app.sh --install` refuses a
dirty tree unless `--allow-dirty`, runs `./run-tests.sh -q` first, pins pyinstaller in the lock.

**P2-3. The smoke test is not automated.**
The sre-release checklist (launch, one scan, one paper trade, quit, relaunch with state intact) has no script.
`--selftest` covers wiring and paths only. `build_app.sh --install` does `rm -rf /Applications/SONAR.app`
before copying (line 92): a failed copy or an interrupted run leaves no app and the previous build is gone
(cleaned `build/dist` on line 98). Fix: copy to a temp name and `mv`; keep the previous bundle as
`SONAR.app.prev`; add `scripts/smoke.sh` (headless boot on a temp `SONAR_DATA`, `/api/state` == live, quit,
relaunch, compare `state.json` hash/trade count).

**P2-4. Logs are unbounded and live in the wrong place.**
Plist 58-60 writes to `<checkout>/data/logs/`, whereas the state is in Application Support; the checkout
`data/` is declared archived. Logs never rotate (stdout buffered banners only; nothing time-stamped), and the
install script's `--status` points there. Fix: log to `~/Library/Logs/SONAR/`, `newsyslog` entry or in-process
`RotatingFileHandler`, timestamp every line.

**P2-5. CI gaps.**
`tests.yml` runs only on ubuntu with `QT_QPA_PLATFORM=offscreen` (AGENTS.md DoD requires native **and**
offscreen; the macOS-native run is local-only), no macOS runner (so nothing exercises `appkit_guard`, `enginelock`
zombie `ps` handling, launchd plist, or PyInstaller), no `network`-marked tests, no coverage floor (README
quotes 80% branch), no plist/`plutil -lint` or `bash -n` check, no dependency audit, no `concurrency` group
cancelling superseded runs, `push:` and `pull_request:` both trigger (double runs on PR branches). CI is not a
required check as far as the repo shows (not verified; I do not have GitHub access). Fix: add a macOS job running
`main.py --selftest` from source and `plutil -lint packaging/*.plist`; a weekly scheduled run to catch upstream
drift (PySide6, ESPN/Polymarket endpoint changes via `-m network`).

### P3 — fragilities to record

**P3-1. Nested-repo checkout fragility.** `sonar/macro/` and `sonar/playmaker/` are gitignored in the parent
(`.gitignore`, `/sonar/macro/`, `/sonar/playmaker/`) and are their own repos; there is no `.gitmodules`. A fresh
`git clone` of SONAR cannot import `sonar.macro`/`sonar.playmaker` (half the suite) and `build_app.sh` then
produces a bundle missing them, caught only by `--selftest` ("MISSING"). The parent records no revision of the
children: you cannot reproduce "the code that ran on 2026-10-08" from the parent commit. `git_autosync`
(`git add -A` in the lab) is why they are ignored; another session removing the ignore line would embed
gitlinks. The module repos are on `main`, the parent on `master`. Fix: pin by recorded SHA (P1-5) and add a
`scripts/bootstrap.sh` that clones the children at those SHAs; add a CI step that fails if the parent
`git ls-files` references anything under those paths.

**P3-2. `~/Documents` and TCC.** The agent's program, venv and working directory sit under `~/Documents`
(plist 24-34). It works today; a macOS privacy change or a new python binary signature can make launchd's
access to Documents prompt or fail with no UI to answer, which is a silent stop (agent.err.log is where it would
show, if anything). Note in the runbook; consider moving the agent's runtime out of Documents (P1-3 snapshot).

**P3-3. Engine lock edge cases.** `EngineLock.acquire` degrades to "running unlocked" on any `OSError` /
`ValueError` (`enginelock.py:132-137`), which is the double-writer scenario the module exists to prevent; PID
reuse after reboot can make a stale lock look alive (`_alive` only checks the pid number, `enginelock.py:75-83`,
not the process start time or command line). The lock lives in `paths.user_data_base()`; with `SONAR_DATA`
unset the app and the agent have different locks and books (this happened for weeks, per README/plist notes).
Fix: add start time to the lock record and compare; refuse (not degrade) when the directory is unwritable;
log the book path at agent start (currently only risk/horizon/LLM are printed, `server.py:151-158`).

**P3-4. Feed degradation is invisible in the UI-less path.** `feeds.is_stale` returns `None` for old candles
(`feeds.py:126-145`), so the snapshot carries no candle/market and signals vanish, but the status stays `live`.
The reason is in no log. Fix: surface per-feed last-success age in `/api/health`.

**P3-5. Housekeeping.** Stale `data/engine.lock` (pid 68945) in the archived directory; `.coverage` (475 KB)
and `.DS_Store` files in the tree; `anthropic` not installed in the agent venv (LLM read off, by design);
`pyproject.toml` still says `dependencies = []  # stdlib only` while `requirements.txt` requires PySide6, and
`[project.scripts]` points at `sonar.server:main` with no extras: two sources of truth for deps.

## Proposed monitoring (smallest set that would have caught the above)

| Signal | Source | Alarm |
|---|---|---|
| Engine thread alive, last poll age | new `/api/health` | age > 60 s |
| Last settlement age | `run_health.last_settled_age_s` computed at read time | > 2 h (already the engine's rule) |
| Agent restarts | launchd `runs` count / log start banners | > 2 per day |
| Feed freshness | per-feed last-success age | > 15 min |
| Disk & backups | newest `*.bak.*` mtime, off-machine copy mtime | > 26 h |
| Version drift | running commit vs checkout vs installed app | differ |
| Heartbeat | daily "alive, n scored, coverage x%" notification | missing = alarm |

Delivery: a separate launchd job (not the agent itself) every 5-15 min; macOS notification plus one push channel
the owner reads off-machine. The watcher must not share fate with the agent.

## Proposed runbook outline (`docs/RUNBOOK.md`, one page)

1. **What runs where** - agent (launchd label, program, data dir `~/Library/Application Support/SONAR`, URL
   127.0.0.1:8787, logs), app (installed bundle), who holds the lock; the three version numbers (checkout,
   installed app, agent).
2. **Is it healthy?** - one command: `scripts/install_agent.sh --status` + `curl :8787/api/health`; what green
   looks like (thread alive, last settle < 2 h, coverage), what each red means.
3. **R1 Agent stopped / stalled** - check launchctl, pid, lock file; if the process is alive but stale (P0-1):
   `launchctl kickstart -k gui/$(id -u)/com.netrunner3000.sonar`; if lock is stale: verify pid dead, remove
   `engine.lock`; never run a second headless by hand.
4. **R2 Crash loop** - read `agent.err.log`; `git status` of the checkout (P1-3); revert or `install_agent.sh
   --uninstall`; expect gap hours to be void.
5. **R3 Backup and restore** - what is backed up, where, how often; stop the agent, quit the app, restore
   `state.json` + `portfolio.json` as a pair (same date) from `.bak.<date>` or the off-machine copy, start,
   verify trade count/equity vs the backup; rehearsal date.
6. **R4 Release** - clean tree, CI green (incl. nested refs), `./run-tests.sh -q` native and offscreen,
   `build_app.sh`, selftest, install, smoke script, restart agent, record build + commit; owner gate.
   Rollback = `SONAR.app.prev`.
7. **R5 Rebuild a machine** - clone parent and children at the pinned SHAs, `uv pip install -r requirements.lock`,
   `install_agent.sh`, restore state.
8. **R6 Planned absences** - sleep/logout/travel: what is lost, how to log the gap.
9. **Contacts/escalation and decision log** - open owner decisions: signing/notarisation, off-machine backup,
   run agent from snapshot vs checkout, always-on host.

## Top actions, in order

1. P0-1 / P0-2 / P0-3 and P1-1 together: health endpoint, supervised engine thread, read-time staleness, logged
   errors, external watcher. These decide whether the dry-run readiness gates the owner is waiting on are
   trustworthy.
2. P1-4: off-machine backup and a rehearsed restore.
3. P1-5 / P3-1: pin nested repos and dependencies, fix the CI remote names.
4. P1-3: stop executing the live working tree as the production agent.
5. P2-1..P2-3: make the bundle's signature valid, gate and atomically install builds.
