# Release: sign-randomisation verdicts (sre-release, 2026-10-13)

Branch `sign-randomisation-verdicts`, worktree `.claude/worktrees/sign-rand`. Re-run on HEAD
`fe9a360`, the merge of `origin/master` (`7375810`). Before this report commit that is v2.338.
Radar: `docs/company/radar-notes/2026-10-12-release.md` (reused, under 30 days; no advisories,
nothing to install). Playbook `docs/playbooks/sre-release.md` is `status: baseline`
(last-reviewed 2026-10-10), so it is stale by the AGENTS.md rule; the owner chose to continue on
it. Nothing was installed, pushed, tagged or restarted. `/Applications`, the launchd agent, the main
tree and `~/Library/Application Support/SONAR` were not touched. The only access to them was
read-only: a `curl` of `/api/health`, `plutil -p`, and `git --no-optional-locks`. `log_activity.py`
was not run, because the caller said not to touch `docs/company/activity.jsonl`.

## Verdict: GO, once the owner approves the release gate

The earlier blocker is cleared. `origin/master` is still `7375810` after `git fetch`, and it is an
ancestor of HEAD. So is `07f0c9e`, the installed v2.296 with the shadow ledger.
`git diff origin/master..HEAD` touches only this feature's files (30 files). In `sonar/` those are
`sonar/backtest.py` and `sonar/randomisation.py`. Neither `sonar/core.py` nor `sonar/calibration.py`
is touched, so the shadow ledger code is the same as v2.296's. The built bundle passes the self-test,
the scan/trade/relaunch smoke, the offline backtest smoke on the bundled bytecode, and a shadow-ledger
create-and-reread check, all against a temp `SONAR_DATA`.

**Do not install the scratchpad bundle.** It is v2.338, built before the CHANGELOG retitle, and it
exists only as evidence. The release build is made after the retitle commit (step 3 below).

## Pre-flight (at fe9a360)

| Check | Result |
|---|---|
| origin/master | `git fetch origin`, then `git rev-parse --short origin/master` gives `7375810`, unchanged. `merge-base --is-ancestor` holds for both `origin/master` and `07f0c9e` in HEAD |
| gitleaks | 8.30.1 with `.gitleaks.toml`. `detect --log-opts=origin/master..HEAD`: 33 commits, no leaks. `detect --log-opts=225fd33..HEAD` (the new commits, origin's included): 31 commits, no leaks. `dir .`: 5.49 MB, no leaks |
| Suite count | `QT_QPA_PLATFORM=offscreen pytest --collect-only -q tests/` (main `.venv`): **2638/2699 collected (61 deselected)**. This matches README.md:287, TESTING.md:13 and TESTPLAN.md:20 ("2,638"). The orchestrator's four runs report 2,635 passed. The gap of 3 matches the 3 skips recorded for v2.296 (`docs/audit/shadow-ledger-sre-release.md`). I did not see the run logs or re-run the suite (load about 73) |
| CHANGELOG | Line 13 `## Unreleased (not installed)` holds "Backtest verdicts: a check against random directions". It sits above `## v2.296 — 2026-10-13` (line 67) |
| Version | `VERSION` = 2, `git rev-list --count HEAD` = 338, so the bundle is **v2.338** (`fe9a360`). See "Version on master" |
| ruff | 97 vs 97, as reported by the orchestrator. Not re-run by me this time. The earlier run at 225fd33 found the same 97/97 with 0 new findings |
| CI | The branch is not pushed, so CI has not run on it. `origin/master` `7375810`: `tests` success and `security` success (2026-10-13 14:12Z, `gh run list --branch master`) |
| activity.jsonl | `git diff origin/master HEAD -- docs/company/activity.jsonl` is empty, so the branch carries origin's log unchanged |

### Version on master
- HEAD `fe9a360` = v2.338. **This report commit = v2.339.**
- Main tree: fast-forward `master` `f106fff` → `7375810` (v2.303), then fast-forward to the branch
  (v2.339). The CHANGELOG retitle commit is then **v2.340**, and that is the version to build and
  install. Any commit added before the retitle raises it by one, so derive it at the time as
  `N=$(( $(git rev-list --count HEAD) + 1 ))`.

## Build

`./build_app.sh` without `--install`, from the worktree, with `UV_OFFLINE=1`. A git-ignored
`.venv/bin/activate` shim sourced the main tree's venv (Python 3.11.15, PySide6 6.11.2); it was removed
afterwards. `SONAR_DATA` pointed at an empty `.../scratchpad/rel/sandbox2/Application Support/SONAR`.
`sonar/macro` and `sonar/playmaker` are byte-identical (`diff -rq`, excluding `.git`) to the main
tree's checkouts at `b3fa3e2` / `1162ba5`. Those are the pins in `.github/workflows/tests.yml:37,42`.

| Item | Value |
|---|---|
| Exit / time | 0, 24 s (log `.../scratchpad/rel/build-fe9a360.log`) |
| Output | `/private/tmp/claude-501/-Users-as-Documents-lab-active-sonar/6947bd8a-9ebb-4b83-a5c1-536e27b9027b/scratchpad/rel/v2.338-fe9a360/SONAR.app`. The worktree's `dist.noindex/`, `build/`, `SONAR.spec` and the shim were removed, and `git status` is clean |
| Size | 98 MB |
| Stamp | `{"build": 338, "commit": "fe9a360", "dirty": false, "source": "baked", "nested": {}}` |
| Info.plist | `CFBundleShortVersionString` / `CFBundleVersion` 2.338, `com.netrunner3000.sonar` |
| Signing | ad hoc (`Signature=adhoc`, TeamIdentifier not set; owner decision 2026-10-10). `codesign --verify --deep --strict` passes after the build, after the move and after all smoke runs |
| Bundled static | `static/docs.html` and `static/testplan.html` are byte-identical to the worktree's |
| Self-test | "All checks passed". It reports v2.338 (baked, fe9a360), "Up to date with the checkout", state and cache under the sandbox, the clickCount guard installed, the execution guard and cost ledger present, and playmaker 7 sports. "LLM read: off" because there is no `anthropic` in the venv (same as before). The macro snapshot fetched over the network |

## Smoke test of the built bundle (temp `SONAR_DATA` and `SONAR_BACKUP_DIR`, never the live directory)

Script: `.../scratchpad/rel/scripts/smoke_headless.sh` (it refuses any path containing
`/Library/Application Support/SONAR`). Output: `.../scratchpad/rel/smoke-v2338/run.txt`.

| Check | Result |
|---|---|
| Headless launch | `--headless --port 8799`. `/api/health`: ok true, problems [], `build` v2.338 / fe9a360 / dirty false / baked, `mode: driving` |
| Scan | The first scan priced 129 assets after about 12 s |
| Paper trade | `POST /api/trade` CL=F LONG: ok true, id `40423a532170`, "opened LONG CL=F" |
| Quit / relaunch | SIGTERM exits in about 1 s. On relaunch `/api/book` open ids are `['40423a532170']`, so state is intact. `portfolio.json`, `state.json` and the daily `.bak` are in the sandbox |
| **Shadow ledger (v2.296), first launch** | Structure only, no outcomes printed. `/api/book` `shadow` is a dict with `error` None. `shadow.ledger` is a dict with `error` None, `reason` None and `created_at` set. The ledger started with anchors first: the marker in `portfolio.json` (`shadow_ledger`, a dict, id `143c13e1`), the sidecar `shadow_ledger.id` (98 B), `shadow_ledger.json` (528 B) and its first copy `shadow_ledger.json.bak.2026-10-13.created.143c13e1`. These sizes match the live v2.296 record's (528 B / 98 B) |
| **Shadow ledger, relaunch** | Ledger read back: `ledger.error` None, `ledger_id` still `143c13e1`, and no second `.created.` copy. The off-site copy (`SONAR_BACKUP_DIR`) received `portfolio.json.bak.*` and `shadow_ledger.json.bak.*.created.143c13e1` |
| Shadow code in bundle | The bundled bytecode, extracted from `PYZ.pyz`, has `core.Live._shadow_pass`, `_shadow_ledger_open`, `_shadow_ledger_write` and `_shadow_ledger_record`, and `calibration.shadow_time_stop`, `shadow_with_ledger`, `ledger_new` and `ledger_marker_parse` |
| GUI launch | `QT_QPA_PLATFORM=offscreen` on the same sandbox. Still alive at 40 s, exits on SIGTERM in about 2 s, 0 tracebacks. The log has two Qt font/size-hint notices and "poll failed: no fresh BTC price from Binance or Coinbase". The live v2.296 agent shows the same message with ok true, so it is not new |
| Backtest, **bundled bytecode** | 52 `sonar`/`ui` modules extracted. Run under `-I` with `urlopen` blocked, on `synthetic()` bars, `horizon_days=20, step=3`. Drift ×2 at 2y/5y: `beats`, `p_tail=0.0078`, `q=8`. No drift ×4 at 2y/5y: `within`, `p_tail=1.0`, "not shown to differ from the prediction, which is not the same as no difference". 10y (both): `withheld='drift'`, `p_tail=None`, "No verdict on ten years ... (about 1 run in 10)". `SMOKE OK`. Identical to the pre-merge run |
| Tracebacks | 0 in `headless1.log`, `headless2.log` and `gui.log` |

Not smoke-tested: the GUI window on screen (no screenshot); a Lab or Terminal backtest on real fetched
bars; the launchd agent on this build (no install by instruction); the shadow ledger against a book
with protocol positions (the sandbox book has none, so no entries or looks were exercised; the suite
covers those).

## Owner steps (after the release GATE approval)

**1. Main tree: set the activity log aside, then fast-forward.** `docs/company/activity.jsonl` is
dirty there (5 local lines, read-only `git diff --numstat`), and `origin/master` adds 26 lines to the
same file, so `--ff-only` would refuse. The branch carries origin's copy unchanged, so the second
fast-forward does not touch it.
```bash
cd /Users/as/Documents/lab/active/sonar
git fetch origin && git rev-parse --short origin/master   # expect 7375810; if not, stop and re-merge
git diff -U0 -- docs/company/activity.jsonl | grep '^+{' | cut -c2- > ~/sonar-activity-local.jsonl
git checkout -- docs/company/activity.jsonl
git merge --ff-only origin/master                   # f106fff -> 7375810 (v2.303)
git merge --ff-only sign-randomisation-verdicts     # -> this report commit (v2.339)
cat ~/sonar-activity-local.jsonl >> docs/company/activity.jsonl
```
Other sessions may append to the log meanwhile. If a merge refuses, re-run the `git diff` line first.

**2. Release commit (v2.340).** In `CHANGELOG.md` change `## Unreleased (not installed)` to
`## v2.N — 2026-10-13` with `N=$(( $(git rev-list --count HEAD) + 1 ))` (expect 340). Then
`git add CHANGELOG.md && git commit -m "Release v2.N: sign-randomisation verdicts — changelog moved to installed version"`.
Name the file; never `-A`. Leave the activity log unstaged.

**3. Build and install from a clean tree.** The dirty activity log in the main tree would stamp the
build dirty, and `install_app.sh` refuses dirty builds. Build in a clean detached worktree, as for
v2.296:
```bash
git worktree add --detach .claude/worktrees/release-2340 master
cd .claude/worktrees/release-2340
rsync -a --exclude .git --exclude __pycache__ ../../../sonar/macro/ sonar/macro/
rsync -a --exclude .git --exclude __pycache__ ../../../sonar/playmaker/ sonar/playmaker/
mkdir -p .venv/bin && echo 'source /Users/as/Documents/lab/active/sonar/.venv/bin/activate' > .venv/bin/activate
mkdir -p ~/SONAR-rollback.noindex/v2.296 && ditto /Applications/SONAR.app ~/SONAR-rollback.noindex/v2.296/SONAR.app
./build_app.sh --install
```
The self-test must say v2.340, baked, dirty false. `--install` checks the seal and the clean stamp,
stops the agent, swaps the app in, and restarts the agent. Then quit and reopen the SONAR window. An
old window holds the engine lock, so the agent shows `mode: waiting` until it is closed.

**4. Agent and push.** Run `./scripts/install_agent.sh --status` and
`curl -s 127.0.0.1:8787/api/health`. Expect ok true, problems [], `build` v2.340 at the release
commit, dirty false, and `mode: driving`. If the agent is not on the new build, use the RUNBOOK §3
kickstart: `launchctl kickstart -k gui/$(id -u)/com.netrunner3000.sonar`. Push when you choose with
`git push origin master` (a fast-forward from `7375810`). Then remove the release worktree with
`git worktree remove --force .claude/worktrees/release-2340`. `release-2296` is still listed and can
go too.

## Rollback
This change adds no state files and changes no formats. The branch's code diff is
`sonar/backtest.py`, `sonar/randomisation.py` and `ui/app.py`, none of which writes under
`SONAR_DATA`. The shadow ledger code is unchanged from v2.296, so v2.296 reads the same ledger.
```bash
cd /Users/as/Documents/lab/active/sonar
./scripts/install_app.sh ~/SONAR-rollback.noindex/v2.296/SONAR.app   # same checks, stop/swap/restart
./scripts/install_agent.sh --status        # expect v2.296 / 07f0c9e / dirty false
```
If the swap fails after the stop, the agent is left stopped and disabled. Start it with
`./scripts/install_agent.sh`. To roll back the source, revert the release commits on master
(`git revert`, newest first); never reset a pushed branch.

## What to watch after install
- `/api/health` for the first hour: ok true, problems [], `build` = the release commit, dirty false.
  `last_error` "no fresh BTC price from Binance or Coinbase" is known on v2.296 with ok true. It
  only matters if `poll` shows up in `problems`. Under load the endpoint can take more than 5 s (it
  took 2.4 s on the second try today), so use `curl -m 20`.
- `tail -50 ~/Library/Logs/SONAR/agent.err.log`: no tracebacks after the restart.
- **The live shadow ledger continues and does not restart.** `/api/book` → `shadow.error` null and
  `shadow.ledger.error` null. `shadow_ledger.id` should still name the v2.296 record (`c9ee3723…`, per `docs/audit/shadow-ledger-sre-release.md`; not read by me),
  and no new `shadow_ledger.json.bak.*.created.*` should appear beside the 2026-10-13 `c9ee3723`
  one. A new `.created.` copy means a fresh ledger was started: stop and roll back. Check structure
  only; print no outcomes (pre-registration).
- The Lab: a 10y run reads "No verdict on ten years"; a 2y or 5y verdict quotes "about 1 run in 10".
  The Terminal backtest uses 2y (day/week) and 5y (month), so fetches are slower. Quarter and year
  profiles show numbers without a verdict.
- The window title and header read `v2.340`.

## Follow-ups
- Delete the evidence bundle and sandboxes under
  `/private/tmp/claude-501/-Users-as-Documents-lab-active-sonar/6947bd8a-9ebb-4b83-a5c1-536e27b9027b/scratchpad/rel/`
  (`v2.338-fe9a360/`, `sandbox*/`, `smoke-v2338/`).
- `baseline.json` ruff is 86 while master and the branch count 97. That is older than this branch;
  the owner or `/harden` should reconcile it.
- The playbook is `status: baseline`; the next radar run should review it.

## Earlier run (225fd33): blocked, now cleared
The first run blocked because the branch had merged stale local `master` (`f106fff`, v2.270) and
lacked `origin/master` (`7375810`), including the installed v2.296 shadow ledger (`07f0c9e`).
Installing that build would have removed the ledger from the app and the agent, and its stamp
(v2.303) collided with `origin/master`'s v2.303. That bundle has since been deleted. The merge
`fe9a360` resolves both problems.
