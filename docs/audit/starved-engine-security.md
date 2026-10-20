# starved-engine: security review (2026-10-19)

Reviewer: `security-engineer` (read-only); saved by the orchestrator. Scope: the uncommitted diff on
`claude/pensive-benz-f395cc` plus `scripts/diag_priority.py`. The playbook is stale (`status: baseline`).
`pip-audit` was not run, because no manifest changed and the script is stdlib only.

**Verdict: PASS, with no P0 or P1.** There is one P2 and five P3s.
- No secrets are written to any plist on disk.
- Every subprocess call uses an argument list with no shell.
- All HTTP goes to 127.0.0.1, and the live port only ever gets `/api/health`.

## Radar (security)
- `launchctl setenv` is a known way to tamper with the environment on a Mac. Elastic flags it as defense evasion
  (MITRE T1574), which supports keeping the global environment from reaching `SONAR_ALARM` on the live agent.
  Sources:
  - https://elastic.co/guide/en/security/8.x/modification-of-environment-variable-via-launchctl.html
  - https://www.elastic.co/docs/reference/security/prebuilt-rules/rules/macos/defense_evasion_modify_environment_launchctl
- Moving `ProcessType` to Standard has no security downside.
- Possible later addition: a CI check that allowlists the `EnvironmentVariables` keys in `packaging/*.plist`.

## What checks out
- **No secrets in plists.** The diag plists hold only `SONAR_DATA`, `SONAR_BACKUP_DIR`, `SONAR_ALARM=off` and the
  blanked keys (`diag_priority.py:362-363, 388`). The follower's environment stays in memory only (`:692-695`).
- **No topic in memory in diag mode.** Any mode other than `on` never reads the Keychain. An unknown value falls
  back to banner-only. The logged value is sanitised (`plain(mode, 40)`), and `global_env` prints only set or
  empty.
- **Evidence output:** the health body is reduced to a typed whitelist (`:294-323`), and the state and config bodies
  go to `/dev/null`.
- **Subprocess:**
  - Labels pass the anchored `LABEL_RE`, and the live label is refused.
  - The `osascript` text goes after `--` as an argument.
- **Paths:**
  - Paths are resolved, then any under LaunchAgents or Application Support is refused (`:107-127`).
  - The scratch dir must be a direct `sonar-diag-*` child of `gettempdir()`.
  - The plist label is checked again before bootstrap.
  - The live agent is only read, and its pid is compared before and after.

## P2
**P2-1. A global `SONAR_ALARM` silently disables the live agent's phone alarm.**
- **Where:** `sonar/alarm.py:640-644`, `sonar/server.py:433-434`, and `scripts/install_agent.sh:59-75` (no status
  check).
- **Scenario:** a stray `launchctl setenv SONAR_ALARM off` (or `1`, `true`, `yes`, which count as unknown and become
  banner-only). The live agent picks it up at its next restart.
- **Impact:** ntfy goes off and `/api/health` stays ok. The only signal is that the daily heartbeat stops arriving.
- **Fix:** (a) pin `SONAR_ALARM=on` in the template's `EnvironmentVariables`, so the per-job value wins. This is
  cheapest and closes the gap. Change the test at `tests/test_agent_from_bundle.py:349` to assert `== "on"`. Other
  options: (b) ignore the variable when `XPC_SERVICE_NAME` is the live label; (c) make health non-ok when the mode
  isn't `on` on the live label; (d) add a check to `install_agent.sh --status`.

## P3
- **P3-1.** A `kill -9` skips the `finally` block, which leaves the diag jobs running and the scratch dir on disk.
  Fix: `cleanup` with no `--dir` scans `gettempdir()/sonar-diag-*` through `check_scratch` and removes the dirs, or
  the RUNBOOK passes `--dir`.
- **P3-2.** `launchctl`, `ps` and `curl` are looked up on `PATH` (`:210, 217, 223, 235, 270, 277, 344`). Fix: use
  absolute paths, as `osascript` already does.
- **P3-3.** `cleanup` boots out every `sonar-diag.*` job, including another session's run (`:613-615`). Fix: a
  per-run label suffix or a lock file.
- **P3-4.** The Alpaca keys aren't blanked (`BLANK_KEYS`, `:67-68`). Nothing calls the broker today
  (`sonar/portfolio.py:135-152`). Fix: add `APCA_API_KEY_ID` and `APCA_API_SECRET_KEY`; an empty value wins over
  `.env`'s `setdefault`.
- **P3-5.** `--out` is checked (`:661`), then written through the unresolved path (`:731`), a small TOCTOU gap.
  Fix: write the resolved path with `O_NOFOLLOW`.
