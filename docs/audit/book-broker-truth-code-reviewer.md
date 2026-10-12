# Code review: book-broker-truth (SONAR), 2026-10-12

Playbook `docs/playbooks/code-reviewer.md`: `status: baseline` (2026-10-10), not yet verified by a radar run.

Ran: `.venv/bin/python -m pytest tests/test_broker_docs_truth.py tests/test_version.py` (70 passed; the new file collects 36); `tests/test_testplan_page.py -k suite_size` (passes in the current mixed worktree); an AST probe of the scan against synthetic snippets.

Doc claims checked against code, all true now: `core.py:163,959` build `Portfolio(path)` with no broker; `portfolio.py:193` falls back to `PaperBroker()`; `default_broker()` (`portfolio.py:137`) has no caller; `AlpacaPaperBroker` is built only inside `default_broker`; "exactly at target or stop" matches `portfolio.py:442`. README:340-341 relabel is accurate (`costs.py:15-18` cost ledger; `universe.py` and `venues.py` used by `ui/app.py`). No leftover automatic-use or comparative claims; GOING_LIVE.md:259-262 left alone as the spec says.

## P1
**P1-1 The suite-size figure 1,907 includes other sessions' uncommitted tests; committing this change alone turns the suite red.** README.md:270, TESTPLAN.md:20, TESTING.md:13, static/testplan.html:110.
- This change adds 36 tests (1,763 + 36 = 1,799). The other ~108 come from other sessions' uncommitted `tests/test_backtest.py`, `test_engine.py`, `test_follow.py`, `test_lab_tab.py`, `test_scoring.py`.
- Failure: stage only this change's files and commit → `test_testplan_page.py::test_the_documented_suite_size_is_the_collected_one` collects 1,799 vs 1,907 and fails. The reverse order also fails.
- Fix: at commit time set the figure to the count collected from the files actually committed (1,799 if this lands alone on HEAD) and re-run the suite-size test against the staged tree; or commit the count together with the other sessions' tests.

## P2
**P2-1 The static scan misses realistic ways to wire Alpaca into the book.** tests/test_broker_docs_truth.py:43-57 (`_calls`), :65-72. Its docstring and CHANGELOG.md:20-21 overclaim ("fails if the book is ever given a broker").

| Case | Result |
|---|---|
| `portfolio.Portfolio(p, b)`, `Portfolio(p, broker=b)`, `Portfolio(*a)`, `Portfolio(p, **kw)` | caught |
| `portfolio.default_broker()`, bare `default_broker()` | caught |
| `self.book.broker = alpaca.AlpacaPaperBroker()` after construction | **missed** |
| `from sonar.portfolio import Portfolio as P; P(p, b)` | **missed** |
| `from sonar.portfolio import default_broker as db; db()` | **missed** |
| `functools.partial(portfolio.Portfolio, broker=b)` | **missed** |
| `getattr(portfolio, "default_broker")()` | **missed** |

Fix: (1) flag any `AlpacaPaperBroker(` call outside `portfolio.default_broker`; (2) flag assignment to an attribute named `broker` outside `Portfolio.__init__`; (3) resolve `ImportFrom` aliases for `Portfolio` and `default_broker`; (4) flag any reference to `default_broker` outside its def (covers `partial` and passing it around); (5) optionally the behavioural `isinstance(book.broker, PaperBroker)` check. With 1-4 the `getattr` string case can be dismissed as deliberate evasion.

**P2-2 The "Unreleased" CHANGELOG heading breaks VERSIONING.md and no test catches it.** CHANGELOG.md:13. VERSIONING.md:48-56: the entry names build `git rev-list --count HEAD` + 1 (v2.190 if next), in the same commit. `tests/test_version.py:304-305` only matches `^## v(\d+)\.(\d+)`, so the heading is invisible. Fix: rename at commit time; optionally make test_version.py fail on a non-version `## ` heading above the newest version entry.

## P3
- **P3-1** False-claim check on docs.html runs on raw HTML (:101-106): `and SONAR <b>uses</b> it` or `more&nbsp;honest` would pass. Fix: `html.unescape(re.sub(r"<[^>]+>", "", text))` before collapsing whitespace.
- **P3-2** "does better" checked across all of README.md and GOING_LIVE.md (:94): false positives with a misleading message. Scope it (and "more honest") to the Alpaca section and `.env.example`.
- **P3-3** docs.html section regex (:118) depends on the next heading being `<h2`/`<h3`; fails loudly if not. Noted only.
- **P3-4** CHANGELOG.md:20-21 and TODO.md:507-508 overstate the test until P2-1 is fixed.

Checked, nothing found: copy matches the Design wording with no "should", profit or edge words; comparative wording conditional; `.env.example` matches check 4; GOING_LIVE.md:103-105 accurate; README regex ignores `###`; `**kwargs` and positional-`None` false positives are harmless.

## Re-review (loop 1), 2026-10-12
**Verdict: PASS.** Runs: new test 37 passed; `test_testplan_page.py` + `test_version.py` 55 passed; 10 mutations on scratch copies.
- P1-1 suite size: **open for commit time** (1,908 = 1,763 + 37 + ~108 from other sessions; 1,800 if committed alone).
- P2-1 resolved for Alpaca (aliases, `default_broker` references, `AlpacaPaperBroker(` outside owners, `.broker` assignment and `setattr` all caught). Still missed but each needs the adapter or `default_broker`, which are caught: `B = portfolio.Portfolio; B(p, b)`, `partial(Portfolio, broker=b)`, subclass `super().__init__(p, b)`, `object.__setattr__`, `__dict__["broker"]`.
- P2-2 "Unreleased" heading: **open for commit time**.
- P3-1..P3-4 resolved. `Guard.__init__` allowlist justified (`execution.py:427` is the guard's own `BrokerPort`; owner-existence guard at :173-179).
- New P3: **N1** owner allowlist covers the whole function, not just `self.broker` (:131-133); **N2** `book.broker.timeout = 3` flagged as a swap (:137-139): check only the outermost target; **N3** `GuardedBroker` (`execution.py:344`) not a watched constructor; **N4** docstrings `execution.py:348-350` and `portfolio.py:138-142` repeat removed claims. N4 fixed by the orchestrator ("would sit"; "Nothing calls this yet … would be more realistic"). N1–N3 logged as follow-ups.
