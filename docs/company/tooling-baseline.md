# Tooling baseline: SONAR

Measured 2026-10-12 by `/harden sonar`. Report-only; nothing was committed or activated.
The worktree had uncommitted changes from other sessions at measurement time.

## Added (files only; no source, test or existing CI edited)
- `.github/workflows/security.yml` (gitleaks on push/PR, weekly pip-audit, non-blocking)
- `.github/dependabot.yml` (pip, github-actions; weekly)
- `.gitleaks.toml`
- `ruff.toml` (pyproject.toml has no `[tool.ruff]`, so a separate file; pyproject.toml untouched)
- `.githooks/pre-commit` (executable, NOT activated)
- `docs/company/tooling/baseline.json` (ratchet baseline; must be committed or the ratchet fails)
- `docs/company/tooling-baseline.md` (this file)

`.github/workflows/tests.yml` already runs the suite, so `quality.yml` was not created.
Consequence: CI does not yet run the ruff ratchet or a coverage floor. Wiring those into
`tests.yml` is an owner/engineer decision (existing CI was left alone).

## Measurements
Re-verified 2026-10-12 on the resumed run. Worktree had other sessions' uncommitted changes.

| Check | Command | Result |
|---|---|---|
| Lint | `uvx ruff check --no-cache --quiet --output-format=concise --exit-zero .` | 86 findings (B905 23, F401 21, E702 15, F841 4, E402 4, B007 4, B904 3, B023 3, E731 2, other) |
| Ratchet | `python docs/company/tooling/ratchet.py --update ruff uvx ruff check --no-cache --quiet --output-format=concise --exit-zero .` | baseline.json: ruff = 86 |
| Secrets, history (matches CI) | `gitleaks detect --redact -c .gitleaks.toml` | no leaks found (315 commits, 4.75 MB) |
| Secrets, working tree | `gitleaks detect --no-git --redact -c <scratch config excluding build, dist*, .venv, __pycache__, .git>` | no leaks found (17.7 MB) |
| Dependencies | `uvx pip-audit -r requirements.txt` | no known vulnerabilities (requirements.txt lists only `PySide6>=6.6`; `anthropic` is commented out, so it was not audited) |
| Tests + coverage | `QT_QPA_PLATFORM=offscreen COVERAGE_FILE=<tmp> .venv/bin/python -m coverage run --branch --source=sonar,ui -m pytest tests/ -q` (cap 300 s when measured) | 1861 passed, 30 deselected, 87 s; total branch coverage 84% (10370 statements, 2662 branches) |
| Tests + coverage, since 2026-10-12 | `.venv/bin/python -m coverage erase`; `COVERAGE=1 ./run-tests.sh tests/ -q -m 'not network and not slow'`; `COVERAGE=1 TEST_BUDGET_S=1200 ./run-tests.sh tests/ -q -m slow -o faulthandler_timeout=0`; `.venv/bin/python -m coverage report --skip-empty` (offscreen as above) | see the paragraph below |

Coverage floor: **83%** (measured 84 minus 1). The project's own bar is 80% branch.
The suite cap went from 300 s to 600 s on 2026-10-12 with `run-tests.sh`'s budget (spec
`sign-randomisation-verdicts.md`, Build notes): the slow-marked randomisation rate tests replay
hundreds of runs. Without coverage each stays under pytest's 60 s per-test cap, but under coverage
on a loaded machine they took 57–77 s and aborted a one-pass run (QA P2-2, P2-A). So coverage is
measured in two passes appended to one data file (row above; `COVERAGE=1` in `run-tests.sh`):
the fast pass under the usual caps, then the slow pass with the per-test cap lifted
(`-o faulthandler_timeout=0`) and the external watchdog at 1200 s. QA's equivalent fallback plus
slow pass read 87% branch (fix loop 1).
Not wired into CI: the existing `tests.yml` was left alone, so no floor step runs yet.

## Branch triggers
`.github/workflows/tests.yml` has `on: push:` and `pull_request:` with no branch filter, so it
runs on every branch; no mismatch with the real branch (`master`, remote `origin/master`).
`security.yml` has the same unfiltered triggers.

## Contradictions with app-context.md
- None in commands. The "30 deselected" tests are the `network`-marked tests (`addopts = "-m 'not network'"` in pyproject.toml). A `release` marker was added and dropped again on 2026-10-12 (code review P3-1): its one test runs in the default suite.

## UNVERIFIED
- Native (non-offscreen) run: only the offscreen run was done; app-context requires both to pass.
- Test teardown printed a `RuntimeError: ... MainWindow already deleted` traceback from a
  `ui/app.py` timer (`_confirm_hidden`) while the suite still passed; not investigated.
- An earlier interrupted attempt hung at exit after the progress reached 100%; the resumed run
  exited cleanly in 87 s, so the hang is intermittent (the `run-tests.sh` watchdog exists for it).
- Lint scope includes the nested repos `sonar/macro` and `sonar/playmaker` if present on disk;
  CI checkouts differ, so the CI count may differ from 86.
- No workflow was executed on GitHub.
