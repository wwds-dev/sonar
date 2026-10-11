# Spec: the agent says which code it runs, and will not be installed on a dirty tree

- Status: part 1 built (branch `p1-2-agent-provenance`); part 2 draft
- Owner approval: part 1 pending review of the branch; **part 2 (clean snapshot) GATE, pending**

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
- Part 2 (decision): where the agent's code comes from. Not built.
- Non-goals: off-machine alarm (P1-4), log location (P2-4), atomic app install (P2-3).

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

Failure modes common to all: the app and the agent can run different builds on one state
file. That already happens today (follow mode tolerates it); `/api/health.build` against the
app's About box makes it visible.

## Risks and open questions
- **Owner decision:** A, B or C, or keep part 1 only for the 30-day run.
- For A: is the frozen binary allowed to bind 127.0.0.1:8787 and post notifications from
  launchd with an ad hoc signature? Needs a drill before switching.

## Verification plan
- Part 1: `tests/test_agent_provenance.py` (22 tests); 11 mutants planted in a scratch copy,
  all killed (record: `docs/audit/t2-1-agent-provenance-code-reviewer.md`). Live agent not
  restarted: the running agent will report `build` only after the owner reinstalls it.
- Part 2: after the decision, a drill: install, edit a tracked file in the checkout,
  `launchctl kickstart -k`, confirm `build.commit` and behaviour unchanged.
