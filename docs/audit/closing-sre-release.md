# SONAR closing release-readiness review (sre-release)

Date: 2026-10-11 22:30 local. Role: sre-release. Committed HEAD `001e0e4` = build 181 (`git rev-list --count HEAD` = 181;
the installed app is build 180, commit `171d89d`, README-only difference). Playbook `docs/playbooks/sre-release.md`:
`status: baseline`, last-reviewed 2026-10-10 (1 day old, but baseline = never verified by a radar run; it adds no practice
beyond AGENTS.md). Read-only checks only: nothing built, installed, restarted, tagged or pushed; data dir not touched
(listed and read nothing but `backup-to`). Another session's uncommitted edits were ignored, except where they change
what the agent would run (finding P1-2).

## Evidence gathered

| Check | Result |
|---|---|
| `codesign -dv /Applications/SONAR.app` | `Signature=adhoc`, `TeamIdentifier=not set`, `Sealed Resources version=2 ... files=203`, `Info.plist entries=10` (was "not bound" in the first audit) |
| `codesign --verify --deep --strict -v` | `valid on disk`, `satisfies its Designated Requirement` |
| `spctl -a -vv` | `rejected` (expected for ad hoc; first audit said "invalid Info.plist") |
| Info.plist / `_build_info.json` | `CFBundleShortVersionString 2.180`; baked `build 180, commit 171d89d, dirty false, source baked` |
| `curl 127.0.0.1:8787/api/health` | HTTP body `ok:true, mode:driving, problems:[], last_poll_age_s:0, run.scored 230, voided 0, coverage_pct 49.9, last_settled_age_s 1614, stale:false`; `last_error` still shows an old BTC-feed failure |
| `launchctl print gui/501/com.netrunner3000.sonar` | `state=running`, `runs=3`, pid 24123 (started Sat Oct 10 20:06:40), runs `.venv/bin/python <checkout>/main.py --headless`, `SONAR_DATA=~/Library/Application Support/SONAR`, logs under `<checkout>/data/logs/` |
| `gh run list --limit 5` | newest run (HEAD `001e0e4`, push) **failure**; previous four success |
| `gh run view 38175827483 --log-failed` | `tests/test_testplan_page.py::test_the_documented_suite_size_is_the_collected_one`: collected 1,763, documents say TESTPLAN 1763, TESTING 1763, README 1811. 1 failed, 1755 passed |
| `.github/workflows/tests.yml:34-43,56` | nested repos from `wwds-dev/...` at SHAs `b3fa3e2...` / `1162ba5...` (equal to the local checkouts, `git -C ... rev-parse HEAD`); `pip install --require-hashes -r requirements.lock` |
| `bash -n build_app.sh scripts/install_agent.sh`, `plutil -lint packaging/*.plist` | OK |
| `tmutil destinationinfo` | No destinations configured |
| `launchctl print gui/501/com.andreas.gdrive-backup` | `job state = spawn failed`, `last exit code = 78: EX_CONFIG`, `runs = 6` |
| `/Users/as/Documents/lab/_Admin/backup/logs` | newest backup log `backup_2026-10-08.log`; `launchd.err.log` (Jun 27) says `backup_to_gdrive.sh: Operation not permitted` |
| Application Support (names/mtimes only) | `state.json` and `portfolio.json` current; `.bak.2026-10-05 ... 2026-10-11` present for every day; `backup-to` = `/Users/as/Documents/lab/backups/sonar-data`; that folder holds only `.bak.2026-10-10` and `.bak.2026-10-11` (both files each) |
| `agent.err.log` | timestamped `poll failed (N in a row): RuntimeError: no fresh BTC price from Binance or Coinbase`, `SONAR: needs attention: ...`, `SONAR: working again`; one burst of 91 consecutive failures 21:39-21:45 today; plus `BrokenPipeError` tracebacks from the HTTP handler |
| `pmset -g custom` | AC: sleep 0; Battery: sleep 10, powernap 0 |

## Are the first audit's findings closed?

| Original finding | Status | Evidence |
|---|---|---|
| P0-1 dead poll thread looks healthy | **Closed** (code), not live-exercised | `sonar/server.py` Watchdog.step: engine thread dead -> log, notify, `os._exit(3)`; plist `KeepAlive SuccessfulExit=false` restarts |
| P0-2 staleness judged on last snapshot | **Closed** | `Live.health(now)` (`sonar/core.py:874-918`) computes age at read time; live curl shows ages |
| P0-3 swallowed per-poll errors | **Closed** | `agent.err.log` has timestamped, counted failures and recoveries |
| P1-1 no health endpoint / external monitor | **Mostly closed** | `/api/health` returns 200/503 (`server.py:154-160`). Watchdog runs inside the agent and alerts only by `osascript` banner (`server.py:223-251`). No off-machine channel, no daily "alive" ping, no check that survives the agent or the Mac being off. `/api/health` carries no version or commit |
| P1-2 agent not running logged out / asleep | **Open** | plist/`install_agent.sh` still say "keeps it alive when you are not [logged in]" (line 10); `gui/` domain only; no caffeinate. `coverage_pct` is 49.9 over 460 h |
| P1-3 agent runs the working tree | **Open** | `launchctl print` program = checkout python + `main.py`. `install_agent.sh` has no clean-tree check. See P1-2 below |
| P1-4 backups single-disk | **Partly closed** | daily `.bak` + 30-deep copy to `backup-to` works (files present). The onward Drive copy is not running (P1-1 below). No restore procedure, no drill, no `docs/RUNBOOK.md` |
| P1-5 CI pins / lock | **Closed for CI**, open for build | SHAs and `wwds-dev` pinned; lock has hashes. Build tools still unpinned (P2-1 below); Actions pinned by tag, not SHA |
| P2-1 invalid seal | **Closed** | `build_app.sh:85-87` re-seals ad hoc and verifies; `codesign --verify` passes on the installed bundle |
| P2-2 reproducible, gated build | **Open** | `build_app.sh:18` `uv pip install -q pyinstaller` unpinned; no lock entry (`grep -i pyinstaller requirements.lock` empty); no clean-tree, CI or suite gate (only `--selftest`, line 97); `*.spec` git-ignored |
| P2-3 smoke test / atomic install | **Open** | no `scripts/smoke.sh`; `build_app.sh:100-101` still `rm -rf` then `cp -R`, no `.prev` |
| P2-4 logs in checkout, unrotated | **Open** | plist 57-60 unchanged; logs not rotated, `.out.log` has no timestamps |
| P2-5 CI gaps (no macOS job, coverage floor) | **Open** | `tests.yml` is one ubuntu job; `TODO.md` lists the macOS job under notarization |
| P3-1 nested repos | **Partly** | pinned in CI; no `.gitmodules`, no `scripts/bootstrap.sh`; a fresh clone still cannot build |
| P3-3 lock edge cases | Addressed by commit e633adf (not re-verified) | git log |
| Stamp / version | **Closed** | `_build_info.json` baked and consistent with Info.plist and `git`; `dirty` is recorded |

## Findings, ranked

### P1 (block the 30-day run being a clean, evidenced one)

**P1-1. The off-disk copy is not off-disk in practice, and nothing says so.**
`backup-to` points at `~/Documents/lab/backups/sonar-data`, which is a folder on the same internal disk. It only becomes
off-disk if the Drive job copies it. `com.andreas.gdrive-backup` is `spawn failed`, exit 78, and the newest backup log is
`backup_2026-10-08.log`: three days without a Drive run, and no Time Machine destination. Spec success measure
(`docs/specs/v1-product.md:29-30`) is "daily and off-disk backups present for every day"; the spec `docs/specs/t1-9-ops.md`
rests on the Drive job covering the folder. Cause not diagnosed (the error log's last entry is June; the failing state may
be a macOS 26 LWCR/TCC issue; the job also may have been superseded by "Backup Control Center", which I did not inspect: not
verified). Fix (owner): get `launchctl kickstart gui/501/com.andreas.gdrive-backup` to succeed or retire it, then confirm a
log appears and the sonar-data files show on the Drive side. Add an age check on that copy to the monitor (below).

**P1-2. The agent executes the working tree, and the tree is dirty right now.**
The agent restarted at 20:06 on Oct 10 and runs `<checkout>/main.py`. `git status` shows uncommitted changes to
`sonar/engine.py`, `sonar/scoring.py`, `sonar/backtest.py`, `sonar/calibration.py`, `ui/app.py`. Any launchd restart (crash,
reboot, the watchdog's own `os._exit(3)`, a 60 s `ThrottleInterval` retry) loads those edits, not build 180. A half-finished
edit then either crash-loops the experiment or silently changes the model mid-run, which defeats "30 days on the same
code". `/api/health` has no commit field, so you cannot tell which it is. Fix: run the agent from a clean snapshot (a
`git worktree` or tag checked out outside `~/Documents`, or the bundle's own binary), or at minimum add
`{version, commit, dirty}` to `/api/health` and have `install_agent.sh` refuse a dirty tree.

**P1-3. No restore procedure and no rehearsed drill; no RUNBOOK.**
`docs/RUNBOOK.md` does not exist; README has no restore steps (grep "restore" in README.md/TODO.md: none). The spec requires
one drill before day 30 (`v1-product.md:44`). `state.json` and `portfolio.json` must be restored as a same-date pair, the
agent stopped first; none of that is written. Draft runbook in the section below.

**P1-4. The alarm reaches the owner only as a macOS banner on this Mac.**
The measure is "health never red for over 10 min without an alarm reaching the owner". The Watchdog posts via `osascript`
(`server.py:240`). If the Mac is asleep, the owner is away, Focus is on, or the machine is logged out, there is no alarm
and, as a plain consequence, no daily "still alive" signal whose absence would say something. Whether banners from an
`osascript` child of a launchd agent are actually displayed was not tested (not verified; the log says `needs attention`
was posted, not that it was seen). Fix: one push channel the owner reads off-machine (ntfy or e-mail) from a separate
5-15 minute launchd job that curls `/api/health` plus checks the newest backup mtime, plus a daily heartbeat.

### P2

**P2-1. Release gate is red at HEAD.** CI run 38175827483 on `001e0e4` failed: README says 1811 tests, TESTING/TESTPLAN say
1763, collected 1763. Cause is a doc number, not code, and the other session's uncommitted TESTING/TESTPLAN edits may fix
it, but as committed the "CI green" precondition fails. Do not release from `001e0e4`. (Build 180, what is installed, was
green: run 38077618258.)

**P2-2. The build is not reproducible or gated.** PyInstaller is installed unpinned at every build; the lock has only
PySide6 and pytest; `*.spec` is ignored so the recipe is a CLI line; no clean-tree, CI-green or test gate before
`--install`; `rm -rf /Applications/SONAR.app` before the copy leaves no app if the copy fails; no `SONAR.app.prev` rollback;
no automated smoke script (launch, scan, trade, quit, relaunch). The shipped build was reproduced only by convention.

**P2-3. Sleep and logout still cost coverage.** `coverage_pct` 49.9 (lifetime, 460 h). On AC power `sleep 0` helps, on
battery it is 10 min; lid close sleeps regardless; at the login window nothing runs. Not computed for the 30-day window, so
whether the "no silent stop" criterion is threatened is unknown. Decide: keep the Mac on AC and awake (or `caffeinate -i` in
the plist), and log planned gaps.

**P2-4. Logs.** Agent logs live in the checkout (`data/logs/`), unrotated, with no timestamps on stdout. A 91-in-a-row poll
failure burst today wrote about 1.5 KB; a day-long outage with throttled counters is fine, but `BrokenPipeError`
tracebacks from the HTTP handler (a browser closing early) add noise that hides real errors. Move to
`~/Library/Logs/SONAR/` with rotation.

**P2-5. CI breadth.** Ubuntu only (no macOS job: `appkit_guard`, enginelock `ps` handling, plist lint, PyInstaller and the
selftest are untested in CI), no coverage floor, Actions by tag (`actions/checkout@v4`, `setup-python@v5`), no `concurrency`
group, `push` and `pull_request` both trigger.

### P3

- `/api/health` `ok:true` while `last_error` shows an old failure: harmless but misleading; clear on recovery or add `last_error_at`.
- Backups cover `state.json` and `portfolio.json` only; `protocol.json`, `wording.json` and `providers.json` (small, `providers.json`
  is tracked) are not, and `.bak` is the first save of the day, so recovery point is up to a day behind.
- Bundle id `com.netrunner3000.sonar` and agent label vs GitHub owner `wwds-dev`: two identities, cosmetic until others install it.
- Engine lock and `~/Documents` TCC (original P3-2) not re-assessed.

## (a) What blocks running as the owner's daily app for the 30-day run

Not blockers: reproducible-enough build, valid ad hoc seal, version stamp, health endpoint, watchdog, 30-day local copies.
Blockers, in order:
1. P1-1: an off-disk copy that is not leaving the disk (Drive job spawn failed since at least Oct 8).
2. P1-2: agent bound to a dirty working tree; pin it before day 1 evidence is collected, or the clean run is not on one code version.
3. P1-3: write the RUNBOOK and run the one restore drill (needs a copy that exists off the live folder; one of the
   existing `.bak.2026-10-11` files is enough for the drill).
4. P1-4: a signal that reaches you when you are not looking at the Mac.
5. P2-1: get CI green again on the next commit; do not install a build from a red commit.
6. P2-3: decide AC power/sleep policy and record planned gaps.

## (b) What blocks handing SONAR to other people

All of (a), plus:
- **Not notarized or Developer-ID signed**: `spctl` says `rejected`, `TeamIdentifier=not set`; a downloaded copy will be refused
  (TODO items 1/1b, owner enrolment pending). Hardened runtime and entitlements untested.
- **No installer for the agent**: `install_agent.sh` needs this repo, `.venv`, and writes into the checkout and
  `~/Documents/lab/backups`; a second Mac has no agent (TODO item 3 says so).
- **Cannot build from a clone**: nested repos `sonar/macro` and `sonar/playmaker` are ignored and not submodules; no bootstrap script.
- **No macOS CI**, no coverage floor, Actions unpinned by SHA; unpinned PyInstaller.
- **No update path or support channel**, no legal text (TODO items 2 and 4): owner decisions.
- Backup default path and notifications assume this owner's layout (`~/Documents/lab`, osascript banner).

## Proposed monitoring (smallest set)

| Signal | Source | Alarm |
|---|---|---|
| Agent up, poll age | `/api/health` 200/503 from a separate launchd job, every 5 min | any 503 for 10 min, or no answer |
| Settle age | `run.last_settled_age_s` | > 2 h (existing rule) |
| Version drift | `/api/health` plus commit (to add) vs installed build | differ, or dirty |
| Backups | newest `.bak.*` in Application Support, in `backup-to`, and Drive-side copy | > 26 h |
| Restarts | `launchctl print ... runs` | > 2 per day |
| Heartbeat | daily push "alive, scored N, coverage X%" | absence = alarm |

Delivery: macOS notification plus one off-machine push; the watcher must not share fate with the agent.

## RUNBOOK outline (to write as `docs/RUNBOOK.md`; I was asked to write only this file)

1. What runs where: label, checkout python, `SONAR_DATA`, 127.0.0.1:8787, logs, three versions (HEAD, installed, agent).
2. Healthy: `scripts/install_agent.sh --status`, `curl -s 127.0.0.1:8787/api/health` (ok true, problems empty).
3. Stalled or crash loop: `launchctl kickstart -k gui/$(id -u)/com.netrunner3000.sonar`; read `agent.err.log`; `git status`
   (P1-2); never start a second headless; stale `engine.lock` only after confirming the pid is dead.
4. Restore: stop agent (`install_agent.sh --uninstall` or `launchctl bootout`), quit app, copy a same-date
   `state.json.bak.<d>` + `portfolio.json.bak.<d>` over the live pair (keep the broken pair aside), start, compare trade
   count and equity with the backup; drill into a scratch `SONAR_DATA` first.
5. Release: clean tree, CI green on that commit, `./run-tests.sh` native and offscreen, `build_app.sh`, selftest, install,
   smoke, restart agent, record build and commit; owner gate; rollback = `.prev` bundle (to build).
6. Planned absences: sleep and logout lose hours; log them.
7. Open owner decisions: signing, Drive/off-machine backup, agent from snapshot, always-on host, push channel.

## Verdict

The code-level findings from the first audit (silent stop, stale-looking health, swallowed errors, the invalid seal, CI
pins, in-app health endpoint and watchdog, 30-deep local copy) are genuinely closed and I could see them working on the live
agent (health 200 with live ages, timestamped failures, a valid ad hoc seal, matching version stamp). What is not closed is
the operations around them: the "off-disk" copy rides a Drive job that has been in `spawn failed` since at least Oct 8, the
agent executes a working tree that currently holds uncommitted model edits, the alarm is a desktop banner with no
off-machine signal, there is no RUNBOOK or restore drill, and the commit at HEAD fails CI on a doc count. For the owner's
30-day run, fix P1-1, P1-2 and P1-3 (and take the P1-4 push channel if you want the "alarm reaches the owner" criterion
to be evidence rather than hope) before treating day-by-day results as clean; the installed build 180 itself is sound. For
handing SONAR to others it is not ready: it needs Developer ID signing and notarization, a clone-and-build path for the
nested repos, an agent installer that does not depend on this checkout, and a macOS CI job, none of which exist yet.
Nothing was tagged, pushed, committed or published.
