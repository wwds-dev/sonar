# T2-1 review — code-reviewer, 2026-10-11

Spec `docs/specs/t2-1-agent-provenance.md` (closing-sre-release P1-2, part 1). Read-only review by a
separate `code-reviewer` agent. Playbook `status: baseline` (stale). Reviewer ran the three affected
test files (64 passed, 1 skipped) and the full native suite (1773 passed, 1 skipped); did not run
offscreen. Checked fine: the `if ! DIRTY="$(...)"` pattern under `set -e`; no consumer of
`health()` compares the whole dict (`server.py` reads `ok`, the watchdog and `ui/app.py` read
`problems`); `info()` is cached, so building `Live` adds no git calls beyond the first; the script
tests drive the real installer in scratch repos and cannot reach `launchctl`.

**P0/P1: none.**

| ID | Finding | Outcome |
|---|---|---|
| P2-1 | Nested repos `sonar/macro`, `sonar/playmaker` (imported by the agent, git-ignored by the outer repo) passed both the installer check and `build.dirty` | Fixed: installer checks each nested repo; `provenance()` reports `nested` and folds it into `dirty`; tests (scratch nested repo, fold table) |
| P2-2 | From a checkout, a failed git at start fell back to the git-ignored `_build_info.json` of the last package and reported it clean (reproduced by the reviewer: v2.180, 171d89d, dirty false) | Fixed: only live git counts from a checkout, only the stamp in a bundle; otherwise `dirty: null`; tests |
| P3-1 | `echo "$DIRTY" \| head -15` under `pipefail` died of SIGPIPE (exit 141) past ~64 KB, silently | Fixed: here-string; test with an 80 KB list |
| P3-2 | Only `$1` was read: `--allow-dirty --uninstall` installed | Fixed: more than one argument is a usage error; test |
| P3-3 | `--status` printed a Python repr and was untested | Fixed: `json.dumps`; test with fake `launchctl`/`curl` on `PATH` |
| P3-4 | Spec cited this record before it existed | Fixed: this file |
| P3-5 | No CHANGELOG entry | Fixed: "Unreleased" entry |

## Mutation check (author, scratch copy outside the repo)
11 mutants, all killed by `tests/test_agent_provenance.py`: health without `build`; stale stamp
trusted; nested True ignored; nested None ignored; non-repo nested dir read; installer skips nested
repos; `echo | head`; argument-count check removed; repr in `--status`; refusal without `exit 1`;
git failure read as clean.

## Not verified
The live agent was not reinstalled or restarted; it reports `build` only after the owner runs
`./scripts/install_agent.sh`. Part 2 (clean snapshot) is an owner decision and not built.
