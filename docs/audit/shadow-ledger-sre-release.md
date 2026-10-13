# Release: shadow ledger (ADR 0002 Amendment 1), 2026-10-13

Owner approval: "approve" (2026-10-13) for merge, changelog move, build and install, smoke test and
push. The session's release agent was refused by the permission classifier ("Production Deploy"), so
the owner ran the worktree, build/install and push commands; the orchestrator did the read-only
checks. Radar: `docs/company/radar-notes/2026-10-12-release.md` (under 30 days, reused).

## Result
| Item | Value |
|---|---|
| Version | **v2.296**, commit `07f0c9e` (changelog move), stamp `dirty: false`, built in a clean detached worktree `.claude/worktrees/release-2296` |
| Merge | master (v2.266, f106fff) merged into the branch as `68c8fd9`; conflicts in `ui/app.py` and docs resolved; two master tests moved to Amendment 1 (see the merge commit) |
| Pushed | `origin/master` f106fff → 07f0c9e (fast-forward, by the owner) |
| Installed | `/Applications/SONAR.app` v2.296; build self-test "All checks passed"; ad-hoc sealed |
| Agent | pid 20829 on the new build. It first reported `mode: waiting`: the SONAR window (pid 81469, open about 17 h on an older build) held the engine lock. After the owner quit the window: `mode: driving`, `/api/health` ok true, problems [], v2.296 / 07f0c9e / dirty false |

## Tests (at 68c8fd9; 07f0c9e changes only CHANGELOG.md)
Native 2,580 passed, 3 skipped, exit 0. Offscreen 2,580 passed, 3 skipped, exit 0. `-m slow` on the
shadow and calibration files 31 passed, exit 0. `TEST_BUDGET_S=900`, load 30–95: not a quiet-machine
pass. Logs: session scratchpad `merge/`.

## Smoke test
- Live agent, structure only (pre-registration: no outcome, state, R, z or look value printed):
  `/api/book` carries `shadow` (dict, `error` null); `shadow.ledger` is a dict with `error` null and
  `created_at` set. In the data directory: `shadow_ledger.json` (528 B), `shadow_ledger.id` (98 B),
  first copy `shadow_ledger.json.bak.2026-10-13.created.c9ee3723` (528 B).
- **Not run this release:** the sandbox smoke (scan, open a paper trade, SIGTERM, relaunch, state kept)
  on a copy of the book; the GUI window on v2.296 (no screenshot); the README retire steps on the real
  app.

## Follow-ups
- Reopen the SONAR window so it runs v2.296 (it follows the agent).
- Advance local `master` in the main checkout (`git merge --ff-only origin/master` there) if no other
  session is using it.
- Remove the release worktree: `git worktree remove --force .claude/worktrees/release-2296`.
- This record is committed after v2.296, so the checkout is one commit ahead of the installed build.
- Backlog from this work: `TODO.md` (fsync before rename; failed look copy reported; retired-count cap;
  look hashes in CHANGELOG at each look's Document phase).
