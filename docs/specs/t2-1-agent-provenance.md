# Spec: the agent says which code it runs, and will not be installed on a dirty tree

- Status: part 1 built; part 2 built, merged (38404c0) and **live since 2026-10-12 11:55**
  (owner's go-ahead): the agent runs the installed v2.215
- Owner approval: part 1 merged to master 2026-10-11; **part 2: owner chose option A (the
  installed bundle) on 2026-10-11**; switching the live agent is the owner's step (below)

## Problem
`docs/audit/closing-sre-release.md` P1-2. The launchd agent `com.netrunner3000.sonar` runs
`<checkout>/.venv/bin/python <checkout>/main.py --headless`. Any restart (crash, reboot, the
watchdog's `os._exit(3)`, the 60 s `ThrottleInterval` retry) loads whatever is in the working
tree, including another session's uncommitted model edits. That either crash-loops the run or
silently changes the model mid-run, which breaks "30 days on the same code". `/api/health` had
no version or commit, so nobody could tell which happened. `install_agent.sh` had no clean-tree
check.

## User and goal
The owner, checking the 30-day paper run. Success measure:
1. `curl -s 127.0.0.1:8787/api/health` carries `build: {version, commit, dirty, source}` for
   the code the process loaded, including the nested repos `sonar/macro` and `sonar/playmaker`
   (`tests/test_agent_provenance.py`).
2. `./scripts/install_agent.sh` on a tree (or nested repo) with uncommitted tracked changes exits 1 without
   touching launchd, listing the files; `--allow-dirty` installs with a WARNING (same test file,
   driving the real script in a scratch git repo).
3. (part 2) a working-tree edit cannot reach the running agent on restart.

## Scope / Non-goals
- Part 1 (built): health field, installer refusal, `--status` prints the running build.
- Part 2 (option A, built): the agent runs the installed app; `build_app.sh --install` stops
  and restarts it around the copy; logs move to `~/Library/Logs/SONAR` (bundle mode).
- Non-goals: off-machine alarm (P1-4), log rotation (P2-4), a `.prev` rollback bundle (P2-3).

## Design
No UI. Installer wording: "WARNING: the agent runs this working tree, and it has uncommitted
changes:" then up to 15 `git status --porcelain` lines, then "Refusing to install..." with the
`--allow-dirty` command. Unknown flags are a usage error (exit 2) so a typo cannot install.

## Architecture
### Part 1
- `sonar/version.py: provenance()` returns `{version, commit, dirty, source, nested}` from the
  cached `info()`. `dirty` is `None` (unknown is not clean) when the source is not the one this
  process should trust: live `git` from a checkout, the `baked` stamp in a bundle. A checkout
  whose git failed at start would otherwise report the git-ignored `_build_info.json` of the
  last package as clean. `nested` holds `{commit, dirty}` per nested repo that is a checkout
  (cached `_nested()`); it folds into `dirty`: True if any is dirty, else None if any is unknown.
- `Live.__init__` stores it in `self.build`; `Live.health()` returns it as `build`. Read once,
  at process start, so it means "what this process loaded", and `health()` never shells out.
- `install_agent.sh` preflight runs `git status --porcelain --untracked-files=no` in the tree
  and in each nested repo before anything else; a failing git counts as dirty. Untracked files
  do not count, matching `sonar/version.py`. More than one argument is a usage error.
- Limitation, stated: `dirty` is the state at start. Edits made after start are not reported
  until the next restart, which is when they would load. Part 2 removes that window.

### Part 2: run the agent from a clean snapshot (GATE: process boundary, expensive to reverse)
| Option | How | For | Against |
|---|---|---|---|
| **A. The installed bundle** (recommended) | plist runs `/Applications/SONAR.app/Contents/MacOS/SONAR --headless`; frozen `main.py` already routes `--headless` | one artifact for app and agent: "three versions" become two; the bundle is what the release gate tested; frozen default data dir is already Application Support | `build_app.sh --install` does `rm -rf` then `cp -R` (P2-3): the agent restarts into a half-copied bundle if it dies mid-install, so the install must bootout/bootstrap the agent around the copy; ad hoc signature and TCC for a background binary not tested; `--headless` in the frozen binary never run (not verified) |
| B. A pinned worktree | `install_agent.sh --pin <ref>` makes `git worktree add ~/Library/Application Support/SONAR/agent-src <ref>` with its own `.venv` from `requirements.lock`; plist points there | exact commit, no build needed; outside `~/Documents` (TCC) | a second venv to keep; nested repos `sonar/macro`, `sonar/playmaker` are not submodules and must be copied in; a third code location |
| C. `git archive` per release | snapshot `HEAD` into `agent-src/<build>/`, keep the last two | immutable, simple rollback | same nested-repo and venv problems as B |

#### Option A as built
- `scripts/check_app.sh <app> <data-dir> [--allow-dirty]` judges a bundle for both scripts: a
  `.app` with an executable; `codesign --verify --deep --strict`; `Contents/Resources/_build_info.json`
  saying `"dirty": false` (missing key = unknown = refused; `--allow-dirty` overrides with a
  WARNING); `SONAR --selftest` under `env -i HOME SONAR_DATA`, i.e. without the shell's environment,
  as launchd runs it.
- The stamp (`scripts/stamp_version.py`) folds the nested repos into `dirty` (dirty or unreadable =
  dirty) and records them as `nested`; a bundle's `/api/health` reports that `nested`.
- `scripts/install_agent.sh` defaults to the bundle: `/Applications/SONAR.app` or
  `~/Applications/SONAR.app` only (`$SONAR_APP` elsewhere needs `SONAR_UNSAFE_PATHS=1`, tests).
  It runs `check_app.sh`, then writes the plist with `plistlib` to a temp file and moves it into
  place (paths with `&`, `|`, `<` arrive intact; a failure leaves the installed plist as it was),
  enables, bootstraps. The plist runs `SONAR --headless --host 127.0.0.1 --port 8787`,
  `WorkingDirectory` = the data directory, logs in `~/Library/Logs/SONAR/`, `SONAR_DATA` as before.
  `--checkout` keeps the working-tree agent (python + main.py, logs in `data/logs/`) behind part
  1's clean-tree check. The checkout's dirtiness does not matter in bundle mode: it is not run.
- `scripts/install_app.sh <app> [--allow-dirty]` (called by `build_app.sh --install`, which passes
  `ALLOW_DIRTY=1` through): refuses a source that is not a `SONAR.app` directory (a trailing slash
  is stripped, a relative path is read from where it was typed) before anything changes. When the
  agent's plist points into the destination: `check_app.sh` on the source first; copy to
  `.SONAR.app.new` beside it and verify the copy; `launchctl disable` and `bootout`; swap with two
  renames; re-run `install_agent.sh`, which checks the installed copy, enables and bootstraps, but
  only if the agent was loaded before (one stopped on purpose, e.g. for a restore, is left stopped).
  Any failure after the stop leaves the agent stopped and disabled, so launchd cannot start a bad
  or half-swapped bundle at the next login, and says so. It warns when the window is open from the
  destination app (it keeps the old build). Without the agent on the app it only swaps.
- Drill so far (2026-10-12): the installed v2.190 binary ran `--headless` on a scratch
  `SONAR_DATA` and port 8799, took its own lock, polled, answered `/api/health` HTTP 200
  `ok:true, mode:driving`, and stopped on SIGTERM. Not drilled: running under launchd (TCC,
  notifications from the ad hoc binary), the real install round trip.

Failure modes common to all: the app and the agent can run different builds on one state
file. That already happens today (follow mode tolerates it); `/api/health.build` against the
app's About box makes it visible.

## Risks and open questions
- **Owner decision (2026-10-11): A.** Built; review record `docs/audit/t2-1-part2-review.md`.
- Deferred (owner): the ad hoc seal proves the bundle is intact, not who built it; anyone who can
  write `/Applications` (here: this user and root only) could swap it. Pinning the build's CDHash,
  a per-user `~/Applications` install, or Developer ID signing would close it.
- To drill at the switch: macOS privacy (TCC) for the ad hoc binary writing the off-disk copy under
  `~/Documents/lab/backups` (`backup-to`), since copy failures only reach stderr.
- Open: notifications posted by the ad hoc binary under launchd, and macOS privacy prompts for
  a background binary, are untested until the live switch.
- The installed app must contain part 1 (v2.191 or later) for `/api/health` to report `build`.

## Verification plan
- Part 1: `tests/test_agent_provenance.py` (22 tests); 11 mutants planted in a scratch copy,
  all killed (record: `docs/audit/t2-1-agent-provenance-code-reviewer.md`). Live agent not
  restarted: the running agent will report `build` only after the owner reinstalls it.
- Part 2: `tests/test_agent_from_bundle.py` (fake bundle, fake `launchctl` that refuses to
  bootstrap a disabled service, fake `codesign`/`pgrep` on PATH, HOME in tmp); 42 mutants over two
  rounds, all killed. Owner's live switch (Release GATE), in order: commit clean; `./build_app.sh
  --install`; `./scripts/install_agent.sh`; `./scripts/install_agent.sh --status` shows
  `program = /Applications/SONAR.app/...` and `build.dirty: false`; edit a tracked file in the
  checkout, `launchctl kickstart -k gui/$(id -u)/com.netrunner3000.sonar`, confirm
  `build.commit` is unchanged; revert the edit. Rollback: `./scripts/install_agent.sh --checkout`.
