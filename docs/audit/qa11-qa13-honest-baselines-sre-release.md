# Release: QA-11/QA-13 honest baselines (sre-release, 2026-10-12)

Owner approval: "Release after commit" (2026-10-12). Commit shipped: `231540b` on master.
Playbook `docs/playbooks/sre-release.md` is `status: baseline` (last-reviewed 2026-10-10): stale
by definition, no radar-verified practice in it. `/radar-check release` was not run.

## Result

| Item | Value |
|---|---|
| Version | **v2.190** (`231540b`, 2026-10-12T10:18:07+01:00), stamp `dirty: false` |
| Built from | clean detached worktree of `231540b` (scratchpad), nested repos copied in, main `.venv` |
| Installed | `/Applications/SONAR.app`: CFBundleShortVersionString 2.190, ad hoc signature, `codesign --verify --deep --strict` passes; binary sha256 `13c8144f...51c2b7`, same as the build output |
| Previous app kept | `/Users/as/Documents/lab/backups/sonar-app-prev.noindex/SONAR-v2.180-171d89d.app` (signature verifies) |
| Smoke test | **passed** on a sandbox copy of the book (details below) |
| Agent restart | **not done, blocked**. See "Agent" below. The agent still runs its 2026-10-10 code |

## Pre-build checks

- **CI on `231540b`: not verified.** The commit has not been pushed (`git branch -r --contains
  231540b` is empty; origin/master = `756917f`), so no workflow has run on it. Pushing needs the
  owner's say-so.
- Instead, the full suite ran in the clean worktree: native `./run-tests.sh tests/ -q`, exit 0,
  1876 passed / 3 skipped / 30 deselected (49 s). Offscreen gave the same counts, exit 0 (48 s).
  The 3 skips: `test_ci_pins` x2 (the copied nested repos have no `.git`) and `test_version`
  (Lab Project Monitor not beside the worktree). 1876 + 3 = 1,879, matching the commit message.
- Nested repos: `sonar/macro` at `b3fa3e2` and `sonar/playmaker` at `1162ba5`, both clean and both
  equal to the CI pins in `.github/workflows/tests.yml`. Copied with `rsync --exclude .git
  --exclude __pycache__`.
- Gitignored inputs: `build_app.sh` needs only `.venv` (symlinked to the main one) and the two
  nested repos. **No `.env` exists in the main checkout, and the build does not bundle one**: its
  only `--add-data` entries are icon, `static`, `_build_info.json` and `VERSION`.
- `git status --porcelain --untracked-files=no` in the worktree was empty before and after the
  build. The regenerated `static/testplan.html` and icon matched the commit.

## Build

`./build_app.sh` (without `--install`) printed: `Stamped v2.190 (231540b)`, `Sealed (ad hoc)`,
`Built: dist.noindex/SONAR.app v2.190 (98M)`, then ran `--selftest` against the built binary:
"All checks passed". Execution guard present (simulator only), playmaker 7 sports, LLM read off
(the anthropic SDK is not in the venv). Install followed runbook §5 by hand: the old app was set
aside with `ditto`, then `rm` + `cp -R` + `touch`, the same as `--install`.

Note: the build-time self-test runs with the default data dir, so it wrote and deleted a probe
file in the live `~/Library/Application Support/SONAR/cache/`. That is standard `build_app.sh`
behaviour and the book files were not touched.

## Smoke test (installed bundle, sandbox book)

Sandbox: `state.json`, `portfolio.json`, `protocol.json`, `wording.json` and `cache/` were copied
from the live dir into a scratch dir. **`engine.lock` and `backup-to` were deliberately not
copied**, so the sandbox could not follow the live agent and could not write to the off-disk
backup. `SONAR_BACKUP_DIR` was unset.

1. **Launch + scan:** ran `SONAR_DATA=<sandbox> /Applications/SONAR.app/Contents/MacOS/SONAR
   --headless --port 8799`. After 20 s, `/api/assets` returned 129 scanned assets. `/api/health`
   gave ok true, mode driving, problems []. The sandbox lock was held by the smoke pid on :8799.
2. **Paper trade:** `POST /api/trade {"symbol":"TSM","direction":"LONG"}` returned `ok: true`,
   "opened LONG TSM", id `dcd49f26ca92`. On disk the sandbox had 29 open positions (28 before).
3. **Quit:** SIGTERM; the process exited in 1 s. SIGINT had no effect, because a backgrounded
   non-interactive job ignores SIGINT, so this is not an app fault. SIGTERM leaves `engine.lock`
   behind with the dead pid.
4. **Relaunch (headless):** the stale lock was reclaimed automatically and health was ok. TSM
   `dcd49f26ca92` was present in `/api/book`.
5. **GUI:** launched the bundle's GUI with `SONAR_DATA=<sandbox>`. It stayed up for 45 s, took the
   lock (`role: app`), polled, and logged no traceback. Quit via AppleScript `quit`: the process
   exited and released the lock. osascript reported "User cancelled (-128)" even though the quit
   happened. Relaunched the GUI: the trade was still on disk, then quit again cleanly.
6. **Isolation check:** the live `engine.lock` sha is unchanged (still pid 24123). The live book
   still has 28 open positions and no TSM / `dcd49f26ca92`. Nothing new appeared in
   `~/Documents/lab/backups/sonar-data` after 23:12 yesterday. The live `portfolio.json` changed
   at 10:26, which is the agent's own equity mark.

Not verified:
- The window's contents. `screencapture` returned a black frame because this shell has no Screen
  Recording permission, so the About-box version, the "stamp reads clean" line and the visual
  state were not seen.
- Scan and trade went through the engine's HTTP API, not the window's buttons.
- The new GUI following the live (older) agent was not tried, because it would touch the live book.

## Agent: not restarted (stopped and reporting)

`launchctl print gui/501/com.netrunner3000.sonar` and runbook §1 both say the agent runs
`/Users/as/Documents/lab/active/sonar/.venv/bin/python main.py --headless` from the **main
checkout's working tree**, not the installed app. That tree currently holds another session's
uncommitted, unapproved book-broker-truth edits to `sonar/alpaca.py`, `sonar/execution.py` and
`sonar/portfolio.py` (modified 04:34–04:40 today). `kickstart -k` would load that code against the
live book, including the paper-only guard file. So the restart cannot "run the new build", and
doing it now would run unreviewed code. I did not run it.

Current agent health, read-only: pid 24123, started 2026-10-10 20:06:40, `launchctl` state
running. `GET 127.0.0.1:8787/api/health` returned HTTP 200 with `ok: true`, `problems: []`,
`last_poll_age_s` 2 and `last_settled_age_s` 1583. `last_error` showed an intermittent "no fresh
BTC price from Binance or Coinbase", single failures in the err log, never 2 in a row. It
most likely runs the 171d89d (v2.180) tree, the last commit before its start. **Not verified**:
`/api/health` reports no version.

Ways to finish the restart (owner decides):
- (a) The book-broker-truth session commits or stashes, the tree is clean at `231540b`, then
  `launchctl kickstart -k gui/$(id -u)/com.netrunner3000.sonar` between hours.
- (b) Act on runbook §6 "run the agent from a clean snapshot": point the plist at a pinned
  worktree or at the bundle's `--headless`, which the smoke test shows works.

## Follow-ups

- **Staleness check in the installed app:** the stamp's `root` is the removed scratch worktree,
  so the installed app will say "No checkout to compare against" instead of "Up to date". A
  build from the main checkout would not have this. Fix options: a `SONAR_STAMP_ROOT` override in
  `scripts/stamp_version.py`, or build from a kept worktree.
- `/api/health` should report `version`/`commit`/`dirty`. Without it, which code the agent runs
  can only be inferred from its start time.
- SIGTERM (what launchd sends on `kickstart -k` and `bootout`) leaves a stale `engine.lock`.
  Relaunch reclaims it, but a SIGTERM handler that releases the lock would be cleaner.
- The sandbox book's cash after the trade was `2.27e-13`: float residue and cash at about 0
  (QA-14 territory).
- The temporary worktree was removed with `git worktree remove`, without force. The sandbox copy
  was deleted. The main worktree was not modified apart from this file and the
  `docs/company/activity.jsonl` entry (`release blocked`).
