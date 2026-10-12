# Release: time-stop shadow readout (sre-release, 2026-10-12)

Owner approval: "commit, push, build and kickstart" (2026-10-12); "go ahead with your picks" for the three open questions. Radar: `docs/company/radar-notes/2026-10-12-release.md` (nothing to adopt). Playbook `sre-release.md` is `status: baseline`.

## Result
| Item | Value |
|---|---|
| Version | **v2.260**, commit `e773541`, stamp `dirty: false` (built in a clean detached worktree) |
| Pushed | `origin/master` fast-forwarded 24dedb1 -> e773541 by the owner (the session's push was blocked by the permission classifier). Local `master` in the main checkout was **not** advanced (blocked), so it still reads 24dedb1 until someone runs `git merge --ff-only` there |
| Installed | `/Applications/SONAR.app` 2.260, `codesign --verify --deep --strict` passes, build self-test "All checks passed" |
| Agent | restarted by `build_app.sh --install` (pid 59183, runs the installed app). `/api/health`: ok true, problems [], build v2.260 / e773541 / dirty false. Slow to answer at first (load 65) |
| Previous app | `~/Library/Application Support/SONAR-rollback.noindex/SONAR-2.190.app` (as listed; not re-verified) |

## Tests (branch HEAD ef8571e, load 40-70)
Native 2398 passed, 1 skipped, exit 0. Offscreen 2398 passed, 1 skipped, exit 0 and slow 22 passed, exit 0, both only with `TEST_BUDGET_S=900`: at the default 300 s external watchdog, offscreen printed 100% and then wedged in Qt teardown and was killed, and slow was killed too. Load-adjusted, not a clean quiet-machine pass. The one skip vs three in the handoff was not investigated.

## Smoke test
- Live agent: `/api/book` carries `shadow` (filled after the first pass; null in the first minutes). TESTPLAN 11.16 identities hold (count sums, n_reached split); 51 entries, no error, `next_t` 2026-10-20. No time-stop outcome field was printed (pre-registration).
- Sandbox copy of the book, installed bundle, headless on :8799: 8 assets scanned, paper trade `TSM LONG` opened, SIGTERM, relaunch, trade persisted, `shadow` key present, no tracebacks.
- Not verified: the GUI window (no screenshot taken; GUI not launched this release); the live book's own trade path.

## Owner questions (decided by "your picks")
1. TESTPLAN 11.23 weekend Yahoo stamp check: run Sat 2026-10-17; not release-blocking.
2. Persisted look ledger: deferred; needs ADR 0002 §7 amendment before look 1 (45 entries) is due.
3. `SH_FINAL_NONE`: ships as ADR §3 words; replace with the validator's softer wording (ADR §3 amendment + domain-finance review) before all three looks are evaluated.

## Follow-ups
- Advance local `master` in the main checkout (blocked this session).
- The scratch release worktree could not be removed without `--force` (untracked venv symlink and nested-repo copies); remove it with `git worktree remove --force`.
- This report is committed after v2.260, so the checkout is one commit ahead of the installed build; staleness will say so.
