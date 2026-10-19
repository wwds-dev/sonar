# build-traceability: security review (2026-10-19)

Reviewer: `security-engineer` (read-only). Saved by the orchestrator. Diff: the uncommitted diff against 7a08185,
plus `scripts/buildid.py` and `scripts/bootstrap_nested.sh`. The playbook is stale (`status: baseline`). No
dependency audit was run (no manifest changed), the suite was not run, and the bootstrap was not run on the real
nested dirs.

**Verdict: pass, with no P0, P1 or P2.** There are eight P3 hardening items.
- **Gate:** the only way past it is forging the stamp as the same user (out of scope). Every failure other than
  exit 3 refuses. Malformed stamps give rc 2 or 3, never 0.
- **Clones:** pinned to the full SHA, checked with `cat-file -e`, then a detached checkout.
- **Inputs:** `tests.yml` values are validated (literal path, `wwds-dev/sonar_<name>`, 40-hex ref).
- **Local fallback:** strips `refs/remotes/origin`, so the origin check can't be fooled.
- **Files:** copies are moved, never deleted, and `rm -rf` only targets `$WORK/<name>.tmp.$$`.
- **Execution:** `python3 -I` is used everywhere, and no tags are created.

## P3
- **P3-1.** The pin parser can be made to disagree with CI (`buildid.py:48-49, 73-84`). A `run: |` block with fake keys
  parses as a pin, and a `with: {…}` flow mapping is skipped (reproduced in scratch). Fix: reject the file if any line
  outside the matched blocks mentions `sonar/macro`, `sonar/playmaker` or `sonar_(macro|playmaker)`, or contains
  `with: {`. Or require exactly two checkout steps, each with all three keys.
- **P3-2.** Credentials in the origin URL would be written to the report (`bootstrap_nested.sh:70,86,96,121,139`),
  which is pasted into a committed audit file. Not exploitable today. Fix: strip userinfo before printing, and
  optionally refuse a credentialed origin.
- **P3-3.** The network can block with no prompt and no timeout (`:80,158`). Fix: `GIT_SSH_COMMAND='ssh -o
  BatchMode=yes -o ConnectTimeout=10'`, `-c credential.interactive=never`, and `-c http.lowSpeedLimit=1 -c
  http.lowSpeedTime=30`.
- **P3-4.** The local-fallback clone doesn't re-hash objects (`:85`). Fix: `--no-local`, or `-c
  transfer.fsckObjects=true`, or `fsck` before checkout.
- **P3-5.** There's no `--` before the URL (`:80,85`), so an origin starting with `-` would be read as an option. Fix:
  add `--`, and have `remote_url` reject a leading `-` or `::`.
- **P3-6.** `--move` follows a symlinked nested dir out of the repo (`:125,140-170`). Fix: refuse when `-L "$path"`.
- **P3-7.** Existing before this change: untracked files don't count as dirty (`sonar/version.py:154`, `_dirty`
  `--untracked-files=no`). An untracked package can shadow a tracked module and get bundled. Fix: count untracked,
  non-ignored paths in the nested repos.
- **P3-8.** `stamp['major']` isn't validated before it goes into the printed tag command (`buildid.py:331`); fix:
  require `^\d+$`. If the second `mv` fails (`bootstrap_nested.sh:137-138`), move the copy back.

## Radar (proposals only)
- SLSA v1.2 has been current since November 2025 and is backwards compatible, with a new Source Track. Cheap option:
  record the nested URIs as `git+https://github.com/wwds-dev/sonar_<name>@<sha40>` with `digest.gitCommit`. Sources:
  - https://slsa.dev/blog/2025/11/announce-slsa-v1.2
  - https://slsa.dev/spec/v1.2/onepage
- The pinned-SHA clone pattern is correct. `git fetch --depth 1 origin <sha>` is cheaper.
- Optionally make the allowed transports explicit: `-c protocol.allow=never` plus https, ssh and file.
- No new tooling is proposed.
