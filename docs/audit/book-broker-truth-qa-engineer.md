# QA verify: book-broker-truth (SONAR), 2026-10-12

Verdict: **PASS**, with two P2 gaps that don't block. Playbook `docs/playbooks/qa-engineer.md`: `status: baseline` (2026-10-10).

## Success measures (spec `docs/specs/book-broker-truth.md`)
| # | Measure | Verdict | Evidence |
|---|---|---|---|
| 1 | Static scan: no broker passed to `Portfolio(`, nothing calls `default_broker(` | MET | AST scan of `sonar/`, `ui/`, `main.py`; catches a second positional argument, `*args`, `broker=`, `**kw`; a guard test proves the scan finds a `Portfolio(` call; `core.py:163,959` pass. Optional runtime `isinstance` check not implemented (P2-1). |
| 2 | None of the 6 false claims in README, docs.html, GOING_LIVE.md, .env.example | MET | 24 parametrised cases; whitespace collapsed, case-insensitive (mutation l). |
| 3 | Alpaca section (README, docs.html) says "always uses the built-in simulator", "optimistic bound", "slippage or fees" | MET | Section-scoped (README `##` to next `##`; docs.html `<h3>` to next h2/h3, tags stripped); also asserts "does not use it yet". |
| 4 | `.env.example` contains "not used by the book" | MET | `.env.example:5`. |
| — | Rest of scope | MET | GOING_LIVE.md:103-105; README:340-341 relabel; CHANGELOG Unreleased entry; TODO done row; counts read 1,907 in README, TESTING.md, TESTPLAN.md, static/testplan.html. |
| — | Suite green natively and offscreen | MET | see commands. |

## Mutations
Applied to the file in place with a copy in the scratch dir; `pytest tests/test_broker_docs_truth.py -q`; restored with `shutil.copyfile`; `cmp` identical for all 14.

| ID | Mutation | Result |
|---|---|---|
| a | `core.py:163` gets `portfolio.default_broker()` positionally | KILLED |
| b | `core.py:163` gets `broker=x` | KILLED |
| c | README regains "picks them up automatically" | KILLED |
| d | docs.html section drops "optimistic bound" | KILLED |
| e | .env.example drops "not used by the book" | KILLED |
| f | `self.book.broker = alpaca.AlpacaPaperBroker()` after construction | **SURVIVED** |
| g | `Portfolio(path, **opts)` | KILLED |
| h | `Portfolio(path, starting_cash=1.0, broker=b)` | KILLED |
| i | README section drops "slippage or fees" | KILLED |
| j | GOING_LIVE regains "where Alpaca already sits" | KILLED |
| k | docs.html "SONAR uses it:" (no "and") | **SURVIVED** |
| l | docs.html "and SONAR\n uses it" across lines | KILLED |
| m | docs.html "always" → "usually" | KILLED |
| n | README "the book uses it when keys are set" | KILLED |

Required a–e: 5/5 killed. Overall 12/14.

## Commands
- `.venv/bin/python -m pytest tests/test_broker_docs_truth.py -q`: 36 passed.
- `./run-tests.sh -q` (twice): 1907 passed, 30 deselected, rc=0.
- `QT_QPA_PLATFORM=offscreen ./run-tests.sh -q`: 1907 passed, 30 deselected, rc=0.
- Branch coverage of changed lines: n/a (no production code touched).

## Issues
- P0/P1: none.
- **P2-1** Reassigning the broker after construction is not caught (mutation f); neither is a direct `AlpacaPaperBroker(` call or an aliased import (reasoned, not run). Fix (test-only): no assignment to an attribute named `broker` outside `sonar/portfolio.py`, no `AlpacaPaperBroker(` call outside `portfolio.py`/`alpaca.py`; or the runtime `isinstance(book.broker, PaperBroker)` check with `alpaca.available()` patched True.
- **P2-2** Exact-phrase list lets paraphrases through (mutation k). Accepted by the spec; mutation n shows the section's positive assertion catches the likeliest rewrite.
- **P3-1** Teardown noise in both modes: `RuntimeError: libshiboken: Internal C++ object (MainWindow) already deleted` from `ui/app.py:3973 _confirm_hidden` (timer after window destroyed). Not caused by this change; latent flake source for whoever owns the in-flight ui/app.py change.
- **P3-2** "optimistic bound" and "slippage or fees" appear once each in docs.html, so mutation d cannot distinguish section-scoped from file-wide; code reading confirms section scope.
- **P3-3** Test quality otherwise good: no mocks, no time/network dependence, empty-scan guard, actionable messages.

Clean tree: `shasum -c` on pre-run snapshot passed; `git diff --stat` for mutated files byte-identical before and after; no files created in the repo.
