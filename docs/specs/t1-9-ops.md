# Spec: T1-9 (part 1) — an off-disk copy of the book; CI reproducible

- Status: built (branch `fix/t1-9-ops`). Owner approval: delegated in chat ("go on").
- Source: `docs/audit/operations.md` (backups, CI, dependencies), architecture P1-4, security P3-7.
  Independent review skipped: each part is pinned by a test that fails without it.

## Changes
- **Off-folder backup:** the daily `.bak` copy of `state.json` / `portfolio.json` is also copied to
  `$SONAR_BACKUP_DIR` or the path in `<data>/backup-to` (keeps 30 per file). The `.bak` files share
  the data folder's disk; the nightly Google Drive job covers `~/Documents/lab` but not
  `~/Library/Application Support/SONAR`, where the live book is. `install_agent.sh` writes
  `backup-to` (default `~/Documents/lab/backups/sonar-data`, inside the Drive job) once.
- **CI:** nested repos checked out from `wwds-dev` (the remotes' owner; `Netrunner3000` only worked
  through a redirect) at pinned commits; `tests/test_ci_pins.py` fails when a local module checkout
  moves past its pin. Dependencies installed from `requirements.lock` with `--require-hashes`
  (PySide6 6.11.2, the tested version; pytest 9.1.1); verified installable for macOS and the
  `manylinux_2_34` CI runner.

## Not done (needs the owner)
- `backup-to` is written by `install_agent.sh`; the running agent's data folder does not have it yet.
- Signing and notarization (Developer ID), a macOS CI job, Actions pinned by SHA, agent availability
  when logged out or asleep — see `docs/audit/operations.md`.
- CI unverified until pushed.

## Verification
Full suite green natively and under `QT_QPA_PLATFORM=offscreen`.
