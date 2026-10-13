# T2-1 part 2 review — code-reviewer and security-engineer, 2026-10-12

Spec `docs/specs/t2-1-agent-provenance.md`, part 2, owner decision option A: the launchd agent runs
the installed `SONAR.app` headless. Two separate read-only reviews of the first version of the
diff (no launchctl, installers or SONAR binary run against the real system). Both playbooks
`status: baseline` (stale). Code reviewer: 42 targeted tests passed. Security: threat model
(assets, `/Applications` boundary: admin group here is `root` and `as` only), experiments in a
scratchpad.

**P0: none.**

| ID | Source | Finding | Outcome |
|---|---|---|---|
| P1-1 | code | Bundle mode ignored the nested repos: the stamp's `dirty` read the outer repo only, so a build with uncommitted `sonar/playmaker` edits installed as clean | Fixed: `stamp_version.py` folds nested repos into `dirty` (unknown = dirty) and records `nested`; a bundle's health reports it; tests |
| P1-2 | code | `install_app.sh` stopped the agent and deleted the app before checking the source: a trailing slash installed `Contents/` and an empty file (reproduced); a bad path deleted the app; a refusal after the copy left the agent stopped silently | Fixed: source validated, slash stripped, relative path resolved first; `check_app.sh` on the source before anything changes; staged copy, verified, swapped by rename; failure message; tests |
| P2-1 | security | After a failed install the plist stayed enabled, so launchd would start a rejected or half-copied bundle at the next login | Fixed: `launchctl disable` before the stop; `install_agent.sh` enables before bootstrapping (launchd refuses a disabled service); message says STOPPED and DISABLED; fake `launchctl` enforces it; test |
| P2-1 | code | `--status` with nothing installed ran `uninstall` (`&& ... \|\|`) and printed "Removed" | Fixed: `if/else`, and `status` returns 0; test |
| P2-2 | code | Spec claimed it "never restarts on a half-copied bundle" — false across a login | Fixed by the disable and the rename swap; spec rewritten |
| P2-3 | code | An agent stopped on purpose (a restore) was restarted by an install | Fixed: restarted only if loaded before; test |
| P3 | both | sed into the plist: `&`, `\|`, `</string>` rewrote it silently; a failed sed had already emptied it (reproduced) | Fixed: `plistlib` to a temp file, then `mv`; test with all three |
| P3 | security | `$SONAR_APP`/`$SONAR_APPS_DIR` could point launchd anywhere | Fixed: only `/Applications` or `~/Applications` unless `SONAR_UNSAFE_PATHS=1`; tests |
| P3 | both | Override hint `ALLOW_DIRTY=1 $0` did not work | Fixed: hint names `--allow-dirty` and `ALLOW_DIRTY=1 ./build_app.sh --install` |
| P3 | security | `--selftest` ran with the installer's environment, not launchd's | Fixed: `env -i HOME SONAR_DATA`; test |
| P3 | code | `pgrep` pattern change untested; window open from the app during install | Fixed: fake `pgrep` matches a fake process list; both patterns tested; warning when the window runs from the app; test |
| P3 | code | TESTPLAN 0.2 and RUNBOOK wording out of date | Fixed |
| P3-1 | security | Ad hoc seal proves integrity, not origin; a swapped `/Applications` bundle would run at login (no new boundary on this Mac) | **Deferred to the owner**: CDHash pinning, `~/Applications`, or Developer ID (spec) |
| P3-5 | security | TCC may block the ad hoc binary's off-disk copy under `~/Documents`; failures only reach stderr | **Not verified**: drill item at the live switch (spec) |
| Info | security | Bundle mode loads no `.env` (none exists); keys must never be bundled | Noted |

## Mutation check (author, scratch copy outside the repo)
Round 1: 16 mutants, all killed. Round 2 (after the fixes): 26 mutants over `check_app.sh`,
`install_agent.sh`, `install_app.sh`, `stamp_version.py`, `version.py`, all killed.

## Not verified
Anything under real launchd: TCC, notifications from the ad hoc binary, App Management protection,
the real install round trip. A manual scratch run of the installed v2.190 binary with `--headless`
(scratch `SONAR_DATA`, port 8799) drove, answered `/api/health` 200 and stopped on SIGTERM.

## Live switch, 2026-10-12 (owner's go-ahead)
- Before: launchd ran `<checkout>/.venv/bin/python main.py --headless` (pid 59891), health `ok`,
  driving, 241 scored, 0 voided, coverage 50.9 %, no `build` field. Old plist kept in the session
  scratchpad for rollback; `./scripts/install_agent.sh --checkout` is the documented rollback.
- `./scripts/install_agent.sh` from the main checkout (master 8a28a53): checks passed on the
  installed v2.215 (`5b34235`, `dirty: false`); `program = /Applications/SONAR.app/Contents/MacOS/SONAR`,
  pid 53323; health `ok`, driving, 241 scored, 0 voided, `build: {v2.215, 5b34235, dirty false,
  baked}`; old python agent gone; `engine.lock` held by the new pid; logs in `~/Library/Logs/SONAR/`.
- Restart drill: checkout HEAD `8a28a53` ≠ the app's `5b34235`; `launchctl kickstart -k` → runs 2,
  pid 54281, still the bundle, `build.commit` 5b34235, polling (age 1 s), record unchanged. The
  shared checkout was not edited (another session works in it); the differing HEAD stands in for
  the edit.
- LLM reads were already off under the old agent (no `anthropic` in the venv either): unchanged.
- Not yet verified: the first off-disk copy written by the app (due at the first save after
  local midnight; `.bak` files keep the source mtime, so `ls` shows the previous evening) under
  `~/Documents/lab/backups/sonar-data` (macOS privacy);
  notifications from the ad hoc binary.
