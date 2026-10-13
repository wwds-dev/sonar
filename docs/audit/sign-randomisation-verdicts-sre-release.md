# Release: sign-randomisation verdicts (sre-release, 2026-10-13)

Branch `sign-randomisation-verdicts`, worktree `.claude/worktrees/sign-rand`, HEAD `225fd33`.
Radar: `docs/company/radar-notes/2026-10-12-release.md` (reused; no advisories, nothing to install).
Playbook `docs/playbooks/sre-release.md` is `status: baseline` (last-reviewed 2026-10-10); the owner
chose to continue on it. Nothing was installed, pushed, tagged or restarted. `/Applications`, the
launchd agent, the main tree and `~/Library/Application Support/SONAR` were not touched.
`log_activity.py` was not run (the caller said not to touch `docs/company/activity.jsonl`).

## Verdict: BLOCKED. Do not install this build

**The branch is behind what is installed.** The branch merged *local* `master` (`f106fff`, v2.270).
But `origin/master` is at `7375810` (v2.303), 33 commits ahead, and the installed app and the live
agent run **v2.296 / `07f0c9e`** (the shadow ledger, `docs/audit/shadow-ledger-sre-release.md` on
origin/master). `07f0c9e` is not an ancestor of `225fd33`:

```
$ git merge-base --is-ancestor 07f0c9e HEAD || echo "NOT in branch"
NOT in branch
$ curl -s 127.0.0.1:8787/api/health      # read-only
... "ok": true, "problems": [], "build": {"version": "v2.296", "commit": "07f0c9e", "dirty": false, "source": "baked"}
$ plutil -p /Applications/SONAR.app/Contents/Info.plist   # read-only
"CFBundleShortVersionString" => "2.296"
```

Installing the bundle built here would take the shadow ledger out of the app and the agent. That
ledger is a write-once, pre-registered record already running in the data directory. The agent
would then stop maintaining it. There is a second problem too: this bundle is stamped **v2.303
(`225fd33`)**, and `origin/master` is also v2.303 (`7375810`). That is one number for two different
commits, which is exactly what `VERSIONING.md` exists to prevent.

A dry-run merge (`git merge-tree --write-tree HEAD origin/master`, nothing written to any branch)
conflicts in docs only: `CHANGELOG.md`, `README.md`, `TESTING.md`, `TESTPLAN.md` (suite counts) and
`static/testplan.html` (regenerate it). Code merges cleanly, but the two lines of work meet in
`ui/app.py` and `static/docs.html`, so both suite modes have to be re-run after the merge.

The bundle at
`/private/tmp/claude-501/-Users-as-Documents-lab-active-sonar/6947bd8a-9ebb-4b83-a5c1-536e27b9027b/scratchpad/rel/DO-NOT-INSTALL-pre-merge/SONAR.app`
exists only as evidence that this change packages correctly. Delete it. Do not install it.

## Pre-flight (at 225fd33)

| Check | Result |
|---|---|
| Suite count | `pytest --collect-only -q tests/` (offscreen, main `.venv`): **2471/2523 collected (52 deselected)**. That matches README.md:271, TESTING.md:13 and TESTPLAN.md:20 ("2,471") |
| CHANGELOG | `## Unreleased (not installed)` is the top section, with the "Backtest verdicts: a check against random directions" entry |
| Version | `VERSION` = 2, `git rev-list --count HEAD` = 303, so the bundle is **v2.303**. See "Version on master" below |
| ruff | `ruff 0.17.0` (uv cache, offline), `ruff check --no-cache --quiet --output-format=concise --exit-zero .`: branch 97, `git archive master` export 97. Ignoring line numbers, the two sets are identical (0 new, 0 gone). Both are above `baseline.json`'s 86. That gap is older than this branch and not caused by it |
| gitleaks | 8.30.1 with `.gitleaks.toml`. `detect --log-opts=master..HEAD`: 32 commits, no leaks. `dir .` (working tree, 4.9 MB): no leaks |
| CI | **Not run on this branch** (it has not been pushed). The latest `origin/master` runs (`tests`, `security`, 2026-10-13 14:12Z) are green. No post-merge (225fd33) native/offscreen suite run is recorded in a file. The last recorded runs are before the merge (spec, "Final runs at load < 50": offscreen 495 s / 370 s and native 184 s ×2, all exit 0). Not re-run by me (load 100–170) |

### Version on master
- If merged as is into local `master` (ff): v2.303 at `225fd33`, v2.304 with this report commit. That
  collides with `origin/master`'s v2.303 and diverges from it. **Do not do this.**
- The correct path is to merge `origin/master` into the branch first. Then 303 + 1 (this report) + 33
  (origin-only commits) + 1 (merge commit) = **v2.338** at the merge commit. The CHANGELOG retitle
  commit then makes **v2.339**, or higher by one for each fix-up commit. Derive N at the time as
  `$(( $(git rev-list --count HEAD) + 1 ))` for the retitle commit.

## Build

`./build_app.sh` without `--install`, run from the worktree. The worktree has no `.venv`, so a
git-ignored `.venv/bin/activate` shim sourced the main tree's venv (Python 3.11.15, PyInstaller
6.22.2, PySide6 6.11.2; `uv pip install --dry-run pyinstaller`: "Would make no changes"; built with
`UV_OFFLINE=1`). The shim was removed afterwards. `SONAR_DATA` pointed at an empty
`.../scratchpad/rel/sandbox/Application Support/SONAR` (the self-test requires that path string).
`sonar/macro` and `sonar/playmaker` in the worktree are byte-identical (`diff -rq`, excluding `.git`)
to the main tree's checkouts at the CI pins `b3fa3e2` / `1162ba5`. They have no `.git`, so the stamp's
`nested` is `{}`.

| Item | Value |
|---|---|
| Exit / time | 0, 25 s |
| Output | moved to `.../scratchpad/rel/DO-NOT-INSTALL-pre-merge/SONAR.app`; worktree `dist.noindex/`, `build/` and `SONAR.spec` removed |
| Size | **98 MB** |
| Stamp | `{"build": 303, "commit": "225fd33", "dirty": false, "source": "baked", "root": ".../worktrees/sign-rand"}` |
| Info.plist | `CFBundleShortVersionString` / `CFBundleVersion` 2.303, `com.netrunner3000.sonar` |
| Signing | ad hoc (`Signature=adhoc`, no Team ID; owner decision 2026-10-10). `codesign --verify --deep --strict` passes after build, after the move and after all smoke runs |
| Tree after build | `git status` clean. `static/testplan.html` (from `TESTPLAN.md`) and `assets/icon.icns` regenerated byte-identical |
| Self-test | "All checks passed": v2.303 (baked, 225fd33), "Up to date with the checkout", state and cache under the sandbox, clickCount guard installed, execution guard and cost ledger present, playmaker 7 sports. "LLM read: off — anthropic SDK not installed": the main venv has no `anthropic`, so the hidden import adds nothing. Probably the same in v2.296 (same venv), not verified. The self-test's macro snapshot fetched over the network |

## Smoke test of the built bundle (sandbox `SONAR_DATA`, never the live directory)

| Check | Result |
|---|---|
| Launches (GUI) | `QT_QPA_PLATFORM=offscreen`, 40 s alive, exits on SIGTERM, no traceback (log: two Qt font/size-hint notices only). Window title not read (offscreen); the title uses the same `version.info()` that reports v2.303 below |
| Launches (headless) | `--headless --port 8799`: `/api/health` ok true, problems [], `build` v2.303 / 225fd33 / dirty false / baked |
| Scan, trade, relaunch | first scan priced 129 assets; `POST /api/trade` CL=F LONG opened `ec68ec8bc28a`; SIGTERM; relaunch: `/api/book` still holds `ec68ec8bc28a`; `portfolio.json` and `state.json` and their daily `.bak` written in the sandbox. No tracebacks in either log |
| Lab-style backtest, **bundled bytecode** | The `sonar`/`ui` modules were pulled out of the bundle's `PYZ.pyz` (`PyInstaller.archive.readers`; 52 modules; `backtest.__file__` asserted to be the extracted copy). They were run with the venv's 3.11 interpreter under `-I` with `urllib.request.urlopen` blocked, on `tests/test_backtest.py:18` `synthetic()` bars, `horizon_days=20, step=3`. Drift 0.004 ×2 at 2y/5y: `verdict_state='beats'`, `p_tail=0.0078`, `q=8`. No drift ×4 at 2y/5y: `'within'`, `p_tail=1.0`, `q=8`, "not shown to differ from the prediction, which is not the same as no difference". **10y** (both): `withheld='drift'`, `verdict_state='withheld'`, `p_tail=None`, sentence "No verdict on ten years ... (about 1 run in 10) ..." |
| Learn tab HTML | bundle `static/docs.html` is byte-identical to the worktree's. It has `<h3>The check against chance</h3>` (line 689), and "about 1 run in 10" appears 3 times |
| static/testplan.html | byte-identical to the worktree's and regenerated unchanged at build, so current with `TESTPLAN.md` (reads 2,471) |

Not smoke-tested: the GUI window on screen (no screenshot); a Lab or Terminal backtest on real fetched
bars; the agent on this build. Network: the self-test macro fetch and the headless scans fetched
live market data. The backtest smoke was offline.

## Owner steps to finish (only after the blocker is cleared)

**0. Clear the blocker (engineer, QA, review; owner go needed).** In this worktree run
`git merge origin/master`. Resolve the five doc conflicts: suite counts to the new collected count,
and `python3 scripts/build_testplan.py` for `static/testplan.html`. Keep the branch's entry under
`## Unreleased (not installed)` above `## v2.296`. Then run `./run-tests.sh -q` and
`QT_QPA_PLATFORM=offscreen ./run-tests.sh -q`, twice if flaky, and have a code-reviewer pass over the
merge resolution. Then re-run this release (rebuild and smoke) on the merged HEAD.

**1. Main tree: set the activity log aside, then fast-forward.** `docs/company/activity.jsonl` is
dirty there (5 local lines), and `origin/master` adds 26 lines to the same file, so `--ff-only` would
refuse. It is an append-only log, so save the local lines, reset the file, and append them again:
```bash
cd /Users/as/Documents/lab/active/sonar
git diff -U0 -- docs/company/activity.jsonl | grep '^+{' | cut -c2- > ~/sonar-activity-local.jsonl
git checkout -- docs/company/activity.jsonl
git merge --ff-only origin/master                   # f106fff -> 7375810 (v2.303)
git merge --ff-only sign-randomisation-verdicts     # the merged branch from step 0
cat ~/sonar-activity-local.jsonl >> docs/company/activity.jsonl
```
(Other sessions may append to the log while you do this. Re-run the `git diff` line first if a
merge refuses.)

**2. Release commit.** In `CHANGELOG.md` change `## Unreleased (not installed)` to `## v2.N — <date>`
with `N=$(( $(git rev-list --count HEAD) + 1 ))`, the same as `07f0c9e` did for v2.296. Then
`git add CHANGELOG.md && git commit` (name the file; never `-A`).

**3. Build and install from a clean tree.** The main tree's dirty activity log would stamp the build
dirty, and `install_app.sh` refuses dirty stamps. So build in a clean detached worktree, as for v2.260
and v2.296:
```bash
git worktree add --detach .claude/worktrees/release-2N master
cd .claude/worktrees/release-2N
rsync -a --exclude .git --exclude __pycache__ ../../../sonar/macro/ sonar/macro/
rsync -a --exclude .git --exclude __pycache__ ../../../sonar/playmaker/ sonar/playmaker/
mkdir -p .venv/bin && echo 'source /Users/as/Documents/lab/active/sonar/.venv/bin/activate' > .venv/bin/activate
# keep the current app aside first (RUNBOOK §5: there is no automatic .prev)
mkdir -p ~/SONAR-rollback.noindex/v2.296 && ditto /Applications/SONAR.app ~/SONAR-rollback.noindex/v2.296/SONAR.app
./build_app.sh --install
```
`--install` checks the new build (seal, clean stamp, self-test), disables and stops the agent, swaps
the app in, and restarts the agent if it was running. Quit and reopen the SONAR window afterwards so
it runs the new build.

**4. Agent.** Check `./scripts/install_agent.sh --status` and `curl -s 127.0.0.1:8787/api/health`. You
want ok true, problems [], `build.version` v2.N, the release commit, dirty false. If the agent is not
on the new build or did not come back, use the RUNBOOK §3 kickstart:
```bash
launchctl kickstart -k gui/$(id -u)/com.netrunner3000.sonar
```
Then push `master` when you choose (`git push origin master`, a fast-forward from `7375810`), and
remove the release worktree (`git worktree remove --force .claude/worktrees/release-2N`).

## Rollback
This change adds no state files or formats. It writes nothing new under `SONAR_DATA` (the branch diff
touches `sonar/backtest.py`, `sonar/randomisation.py` and `ui/app.py`; no new writes). Going back to
v2.296 is therefore code-only:
```bash
cd /Users/as/Documents/lab/active/sonar
./scripts/install_app.sh ~/SONAR-rollback.noindex/v2.296/SONAR.app   # same checks, stop/swap/restart
./scripts/install_agent.sh --status        # expect v2.296 / 07f0c9e / dirty false
```
`install_app.sh` needs the folder to be named `SONAR.app`, which is why the copy above sits in a
`v2.296/` subfolder. If anything fails after the stop, the agent is left stopped and disabled. Start
it with `./scripts/install_agent.sh`. Source rollback: `git revert -m 1 <merge>` on master, never a
reset of a pushed branch.

## What to watch after install
- `/api/health` for the first hour: ok true, problems [], `build` = the release commit, dirty false.
  `last_error` "no fresh BTC price from Binance or Coinbase" was present on v2.296 today with ok true.
  It is only a problem if `poll` turns up in `problems`.
- `tail -50 ~/Library/Logs/SONAR/agent.err.log`: no tracebacks after the restart.
- The shadow ledger still runs: `/api/book` → `shadow` is a dict with `error` null and
  `shadow.ledger.error` null. Check structure only; print no outcomes (pre-registration).
- The Lab: a 10y run reads "No verdict on ten years"; a 2y or 5y run quotes "about 1 run in 10". A
  third grey reading, "not told apart from chance", can appear. The Terminal backtest uses 2y for the
  day and week profiles and 5y for the month profile, so expect slower fetches. Quarter and year
  profiles show numbers without a verdict.
- The window title and header read `v2.N`. If the window was left open on v2.296 it keeps the old
  code and can hold the engine lock (agent `mode: waiting`), so quit and reopen it.

## Follow-ups
- `baseline.json` ruff is 86 while master and branch both count 97 (`ratchet.py` would fail on
  master). This predates the branch; owner or `/harden` to reconcile.
- Local `master` in the main tree is 33 commits behind `origin/master`. Whoever merges master into a
  feature branch should merge `origin/master`, or fast-forward local master first.
