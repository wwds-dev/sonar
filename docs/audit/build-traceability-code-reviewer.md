# build-traceability: code review (2026-10-19)

Reviewer: `code-reviewer` (read-only). Saved by the orchestrator. Diff: the uncommitted diff against 7a08185. The
playbook is stale (`status: baseline`).

**Verdict:** no P0, P1 or P2. The gate, exit codes, install ordering, never-delete bootstrap, `build_id` and
new-records-only ledger all match A1-A11. There are eight P3s.

**What was run:**
- `./run-tests.sh tests/test_buildid.py tests/test_bootstrap_nested.py tests/test_version.py tests/test_ci_pins.py
  tests/test_agent_provenance.py tests/test_agent_from_bundle.py -q` gave 249 passed, 3 skipped, 1 failed. The failure
  is the expected v2.365 newest-entry-ahead check.
- With `test_shadow_ledger.py`: 301 passed.
- `buildid.py pins` under `/usr/bin/python3 -I` passes, and the file parses at 3.9.
- `bash -n` passes under bash 3.2.
- ruff and shellcheck are not installed. The full suite was not run.

## P3
- **P3-1.** The stamp reads `HEAD` twice, so `commit`/`build` and `sha` can disagree if another session commits in
  between (`scripts/stamp_version.py:69`, `sonar/version.py:131-135, 344-346`). `tag_command` could then propose the
  wrong commit for a number (`buildid.py:119-121, 330-334`). Fix:
  - resolve `HEAD` once and derive the short commit and count from that sha;
  - add a verdict reason when `sha` doesn't start with `commit`;
  - check `rev-list --count <sha> == build` in `tag_command`.
- **P3-2.** `set -e` is off inside `clone_pin` when it's called from `if` or `||` (`bootstrap_nested.sh:89-94, 115,
  126`). A failed `update-ref -d` could leave the main checkout's branches as `refs/remotes/origin/*`, which would fool
  the origin check. Fix: check each command explicitly, then assert that `for-each-ref refs/remotes/origin` is empty.
- **P3-3.** One duplicate key anywhere in `tests.yml`, even in a non-pin step, breaks every caller (`buildid.py:82-83,
  90-91`). This fails closed. Fix: only check duplicates in the pin blocks, and decide whether the same pins in several
  jobs are allowed.
- **P3-4.** A token in the origin URL is reused and printed into the saved report (`buildid.py:267-281`,
  `bootstrap_nested.sh:86, 96, 121, 139`). Latent today; see also the security review's P3-2. Fix: strip userinfo.
- **P3-5.** The origin check reads the checkout that runs the installer, not the bundle's own source
  (`check_app.sh:44-45`, `buildid.py:209-214`). Re-running `install_agent.sh` from an un-bootstrapped worktree refuses
  a correct bundle with exit 3. Fix: fall back to the main checkout's nested repo, or document the limit in RUNBOOK §1.
- **P3-6.** If the second `mv` fails (`bootstrap_nested.sh:137-138`), the owner isn't told where the copy went. Fix:
  print the `aside` path between the two `mv`s, or move the copy back.
- **P3-7.** `CHANGELOG.md:13` and `docs/specs/shadow-ledger.md:375` hard-code v2.365, which only holds for exactly
  one commit on 7a08185. A merge to master changes the number. Fix: in the ledger spec, say "from the
  build-traceability release (ADR 0002 Amendment 2)", and fix the CHANGELOG heading at release.
- **P3-8.** A comment says `/api/health` carries `traceable`/`untraceable`, but `provenance()` doesn't return them
  (`stamp_version.py:90`, `sonar/version.py:305-323`). Fix: change the comment, or add the fields with a test.
