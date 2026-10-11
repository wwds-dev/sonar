# Closing documentation review (tech-writer) - 2026-10-11

Scope: committed HEAD `001e0e4` (`git rev-list --count HEAD` = 181; `_build_info.json` stamp = build 180).
Read via `git show HEAD:<path>` and a clean `git archive HEAD` copy in the scratchpad (with the
gitignored `sonar/macro` and `sonar/playmaker` copied in) so the other session's uncommitted edits to
`TESTING.md`, `TESTPLAN.md`, `static/testplan.html` and code were not counted. Line numbers below are
HEAD line numbers. No file was modified except this one. Nothing committed.

Playbook: `docs/playbooks/tech-writer.md` has `status: baseline` (last-reviewed 2026-10-10, so not over
90 days). It is a seeded placeholder with no practices in it, so this review rests on `AGENTS.md`,
`app-context.md` and the agent prompt only.

## Verified correct at HEAD (so nobody re-checks)

| Claim | Where | Evidence |
|---|---|---|
| HTTP API table: all routes, methods, bodies, 503 on unhealthy, 30 s undo, `/`, `/docs`, `/testplan` | `docs/api.md:5-18` | `sonar/server.py` do_GET/do_POST (routes `/api/{state,assets,config,health,macro,book,wire,read,trade,undo,close}`); `core.py:552` `UNDO_WINDOW = 30.0`; health 200/503 |
| Port 8787 and loopback default | README:295 | `server.py` `--port` default 8787, `--host` default 127.0.0.1 |
| `SONAR_DATA` overrides the state directory; the agent plist sets it | README:259, 292 | `paths.py:228` `DATA_ENV`; `packaging/com.netrunner3000.sonar.plist:36-39`; `scripts/install_agent.sh:21` |
| Daily backup, last seven days | README:297, docs.html:913 | `paths.py:29` `BACKUP_KEEP = 7` |
| Flags `--selftest`, `--headless`, `--risk`, `--horizon`; `install_agent.sh --status/--uninstall`; `build_app.sh --install` | README:250-252, 291-292 | `main.py:4-5,159-164,256`; `install_agent.sh:55-56`; `build_app.sh:99` |
| Risk table (7/4/2.5 c edge, 1/4-1/2-3/4 Kelly, 3/8/15% stake, 4% daily vol) | README:216-220 | `sonar/risk.py:76-96` |
| 8 tabs, names, order, "Lab" group heading | README:40-56 | `ui/app.py:1124-1154` |
| 129 instruments, 24 feeds / nine blocs, `ROLL_BATCH` 26, gold at 20 min, red at 60 min | README:50,69,196-199 | `assets.py:249`; `ui/app.py:166-167`; split and feeds already verified in the first audit; docs.html:321,331 agree |
| LLM read model `claude-opus-5`, effort medium | README:238 | `sonar/llm.py:50-51` |
| Protocol mode: 5 top, 5 bottom, once a day, coin flip, 20-position floor, $10,000 start | README:298-300, 36-38 | `core.py:77-79`; `calibration.py:53` `MIN_SAMPLE = 20`; `portfolio.py:41` |
| `TEST_BUDGET_S`, 300 s | README:270 | `run-tests.sh:19` |
| Version scheme `v<MAJOR>.<BUILD>` | README:319-322, VERSIONING.md | `VERSION` = 2; build = commit count |
| Cost floor (EUR 1.05, 5.2% of EUR 20) and the study table figures | README:137-152 | `CONFIDENCE.md:553-554, 571-585` |
| 145 acceptance cases, 18 marked as regressions | README:272 | `TESTPLAN.md` at HEAD: 145 numbered rows, 18 with the warning mark |
| Every path and link in the README exists in HEAD | README whole file | `CONFIDENCE.md`, `GOING_LIVE.md`, `LICENSE`, `.env.example`, `docs/api.md`, `docs/execution-guard.md`, `docs/history/*` (all five files), `docs/specs/v1-product.md`, `scripts/*`, `packaging/`, `research_results/`, `docs_attention_study.json`, `static/*`, `ui/*` modules named in the Layout block, `tests/test_{plain_language,wording,ui_thread}.py`, `AGENTS.md`, `CLAUDE.md`. One exception: see P2-5 |
| Honesty framing | README:13-14, 140-157, 374-380; docs.html:75, 415, 420, 924, 1006 | No sentence claims edge, profit or certainty about SONAR's own results; exceptions that read as edge claims are P2-3 and P2-4 |

## P0

None. No sentence in the README or the manual claims an edge, profit or certainty for SONAR.

## P1 - wrong against the code or against another doc, where a reader looks first

1. **The README still says closed positions feed P(profit); the code no longer does.**
   README:25 ("pinned at the driftless baseline ... until closed positions say otherwise") and README:134-135
   ("drift is only ever supplied by `sonar.calibration` from positions that actually closed") describe the
   mechanism removed in commit `b981860` (T1-1). `sonar/calibration.py:15-20`: "It is a report, never an
   input. It used to ... move every row's `P(profit)`... Removed (owner decision, 2026-10-10)". Nothing
   outside `calibration.py` and `backtest.py` calls `implied_edge` (`grep` on HEAD). The manual got the
   fix (docs.html:815-818); the README did not, so the two now disagree on the central honesty claim.
   Fix: "P(profit) is always `1/(1+R:R)`. The track record is reported next to it and never changes it."
   (`sonar/scoring.py:42` has the same stale docstring "supplied by `sonar.calibration`"; code, so left to
   the engineer.)
2. **README test count is wrong at HEAD, and the repo's own guard fails because of it.**
   README:266 says 1,811 tests; HEAD collects **1,763** (`pytest --collect-only` on the clean HEAD copy:
   "1763/1793 tests collected (30 deselected)"), which is what `TESTING.md:13` and `TESTPLAN.md:20` say.
   Running `tests/test_testplan_page.py` on the HEAD copy: `1 failed, 20 passed`
   (`test_the_documented_suite_size_is_the_collected_one`, `tests/test_testplan_page.py:253`; it requires
   all three documents to equal the collected count). 1,811 is the worktree's count including the other
   session's uncommitted tests. Commit `001e0e4` ("README: current test count") therefore left committed HEAD
   red in both modes. It heals when the other session commits its `TESTING.md`/`TESTPLAN.md`/tests, but a
   release cut from HEAD today would fail the suite. Land README, TESTING and TESTPLAN with the tests in one
   commit.
3. **CHANGELOG is about 50 builds behind and does not cover any of the audit fixes.**
   `CHANGELOG.md:13` newest entry is `v2.131 - 2026-10-08`; HEAD is build 181 and `TODO.md:67,70` says
   v2.178 is installed. Per `VERSIONING.md:48-60` the installed build gets an entry. User-visible changes
   since v2.131 with no entry: local API refuses foreign `Host`/`Origin` (`b71e819`); P(profit) no longer
   moves with the track record (`b981860`); hourly sigma replaced by the studied estimator (`038f2e7`);
   agent health check, watchdog and macOS alarm (`5dfc43d`); lock takeover and book-write fixes (`cfcdc39`,
   `b1ce48c`, `e633adf`); off-disk backup copy (`6603e96`); first-run card, Lab heading, loading and empty
   states (`d2755c6`, `37fc335`, `fb29c17`, `a09917c`); MIT licence. README:322 ("what each installed build
   contained is in `CHANGELOG.md`") and `docs/history/README.md:3` ("Newest decisions are in `CHANGELOG.md`")
   send readers to a file that stops at 2026-10-08. The first audit (item 17) noted this; the T1-11 spec did
   not close it. `AGENTS.md` definition of done requires an entry.

## P2 - contradicts another doc, or leaves a user stuck

1. **The manual says the app makes no LLM calls; the README says it can.** docs.html:902-904 ("the running
   app makes **zero AI/LLM calls**") and docs.html:897 ("Does it cost money? **No.**") against README:73-76
   and :313 (optional LLM read, billed per use) and the "read" button the manual itself lists (docs.html:316).
   Also docs.html:902 "no key" while Finnhub/Twelve Data keys are optional. The manual is what a newcomer reads.
2. **The manual states run figures as fixed facts that are no longer true.** docs.html:747-751: "calibration
   has zero closed positions of the twenty it needs, and the model-vs-market log has zero scored hours of its
   hundred." The owner's real book (`~/Library/Application Support/SONAR/state.json`) holds 230 scored hours
   and 355 trades. Not verified that "model-vs-market log" is the same counter as `scorelog`, but the sentence
   cannot be right as a standing statement. Fix: describe the rule ("needs 20 closed, 100 scored hours; the
   Is-the-score-right panel shows where you are") not today's count.
3. **"Asserts a direction? Yes" in the tab table** (README:55, docs.html:358) beside "SONAR asserts no edge"
   (README:13). The hourly model gives a probability that, by README:94-96 and docs.html:420, is not better
   than the market's. A reader who only scans the column takes "Yes" as a claim. Fix: "Gives a probability of
   up; not shown to beat the market".
4. **"The edge is real"** (docs.html:1027) in the Sports section. It refers to the published paper's result
   but is unqualified and sits in a tab SONAR itself has not validated. Fix: "In that paper the edge was real;
   SONAR has not shown it for itself, and the capacity was very small."
5. **A fresh clone cannot run, and the README does not say so.** `sonar/macro` and `sonar/playmaker` are
   gitignored nested repos (README:336-337, `git ls-files` shows neither) but are imported at start-up
   (`ui/app.py:45,47`, `main.py:21,130`). CI works around it with pinned checkouts of `wwds-dev/sonar_macro`
   and `wwds-dev/sonar_playmaker` (`.github/workflows/tests.yml:36-43`). README "Run it" (:240-261) never
   says where they come from, and README:60 links `sonar/playmaker/MODELS.md`, which is in the nested repo,
   not this one. Matters for `TODO.md` "Handing SONAR to other people".
6. **The off-disk backup is shipped and undocumented for users.** `SONAR_BACKUP_DIR` and `<data>/backup-to`
   (`sonar/paths.py:32,41-56`; `scripts/install_agent.sh:84-90`; keeps 30 copies, `paths.py:33`) appear only
   in `docs/specs/t1-9-ops.md`. README:297 and docs.html:913 say only "daily rotating backup (last seven
   days) beside themselves", which is the same-disk copy the spec says does not survive a lost disk. Add
   the env var, the `backup-to` file, the default path, and the 7-local / 30-off-disk counts.
7. **docs.html:874** ("drift is only ever supplied by closed positions") contradicts docs.html:815-818 on the
   same page (same stale idea as P1-1).
8. **"All negative" versus "not detected".** docs.html:924-925 ("Five studies ... all negative") and
   `CONFIDENCE.md:731-735` (answers "No - ...") overstate next to README:145-152 and 154-157, which were
   reworded in `c2e3b93` to "Not detected" with what the studies could not rule out. The honest-framing
   edit reached only the README.

## P3 - hygiene, jargon, completeness

1. Stale name "Terminal": README:95, docs.html:351 (history, fine) and :421 (not fine). The panel is at the
   foot of Practice.
2. Jargon without a definition at first use in the README: FDR (:149), IC (:155), EWMA (:96), half-Kelly (:100),
   slippage (:102), "barrier" (:126, :147). The six-word box is a good start; the closing items of the first
   audit (13) are partly open. "25-term glossary" (README:278): not verified (docs.html §1 has 38 table rows
   across several tables; no clean count).
3. Layout block (README:326-346) omits `sonar/crosssection.py`, `volatility.py`, `version.py`
   (`app-context.md` names `volatility.py` as a model file).
4. README:244 "Linux and Windows are untested and unsupported" while CI runs the whole suite on a Linux
   runner (`tests.yml`). Say "the app is macOS only; the test suite also runs on Linux in CI".
5. README:247-249 runs `python main.py` after `uv venv` with no activation step (`run-tests.sh` uses
   `.venv/bin/python`). Add `source .venv/bin/activate` or `uv run`.
6. README:350 "loopback-only": true by default; `--host` can change it (`server.py` argparse). README:71
   "**No** authentication, **no** write access anywhere" sits under the data-sources table and reads as a
   statement about the local API, which has write routes (`/api/trade`, `/api/close`). Reword to "the data
   sources need no login and SONAR only reads from them".
7. `docs/ROADMAP.md`: only Phase 2 is marked done (:15); Phases 1 and 3 have been executed (audit, T0/T1
   fixes). :4 points to `AGENTS.md` for "real money is out of scope" but that line is in
   `docs/company/app-context.md`. :35 names `docs/RUNBOOK.md`, which does not exist (planned).
8. `docs/audit/SUMMARY.md:7` still says "Nothing here has been fixed" and quotes 1,582 tests; add a one-line
   pointer to the closing reviews or mark the whole file as a dated snapshot.
9. `docs/company/app-context.md` "Docs and process files" omits `docs/api.md`, `docs/history/`, `LICENSE`,
   `.env.example`, `docs/audit/`.
10. The manual (`static/docs.html`) does not mention the launchd agent, follow mode, `SONAR_DATA` or the
    status line "following the engine at ..." (grep: only `--headless` at :899). A user with the agent
    installed sees behaviour the in-app manual never explains.
11. The Finnhub item still has three statuses: `SUGGESTIONS.md:11` PLANNED, `TODO.md:43` P0 `@me`,
    README:359 "single highest-value change" (first audit item 16, recorded as not done in the T1-11 spec).
12. No contributor entry point: nothing says how to run a single test, and VERSIONING.md is linked only in
    passing (README:322). README:368 "Revolut" aside still reads as a chat note (first audit item 21).
13. Not verified: bundle size ~98 MB (README:243), bandwidth ~8 MB/hour (README:314, docs.html:907), "Three
    tests build a real `MainWindow`" (README:270), coverage 80% (TESTING.md:13; no coverage run made),
    Yahoo `quoteSummary` answering 401 (README:172), Alpaca `PK` key rule at runtime (README:163-165).

## Were the initial audit's findings closed? (`docs/audit/docs.md`)

| # | Finding | State at HEAD |
|---|---|---|
| 1 | Five vs six studies | **Closed in README, GOING_LIVE:16, CONFIDENCE:731-735, docs.html:75,121,840**; wording residue in P2-8 |
| 2 | "Docs button" | Closed (README:54, :273) |
| 3 | 113 vs 129 | Closed (CONFIDENCE:571 explains; README no longer quotes 113) |
| 4 | "next gaps" paragraph | Closed (gone) |
| 5 | API table | Closed and moved to `docs/api.md`, verified against `server.py` |
| 6 | Layout out of date | Mostly closed; P3-3 residue |
| 7 | No "start here" | Closed (README:30-38) |
| 8 | Setup assumes tooling | Mostly closed (Python 3.11, uv, macOS); P2-5, P3-5 residue |
| 9 | `pip install anthropic` | Open, minor (README:234 vs `requirements.txt:5` comment) |
| 10 | Contributor entry, `.env.example`, LICENSE | `.env.example` and `LICENSE` closed; entry point open (P3-12) |
| 11 | Duplicate Tests/Testing headings | Closed |
| 12 | TODO open/done | Closed (`TODO.md` Open / Done) |
| 13 | Jargon | Partly closed (six-word box); P3-2 |
| 14 | Sprawl | Closed (README 380 lines, history moved to `docs/history/`) |
| 15 | SUGGESTIONS numbering | Closed (`I-9`, `I-10`, `I-15`) |
| 16 | Finnhub in three files | Open (P3-11) |
| 17 | Version example / CHANGELOG behind | Example harmless; **CHANGELOG gap worse (P1-3)** |
| 18 | GOING_LIVE first person | Closed (GOING_LIVE "Where this stands") |
| 19 | Disclaimer near top | Closed (README:13-14) |
| 20 | Study outputs undescribed | Closed (README:343) |
| 21 | Revolut aside | Open (P3-12) |

New since that audit and not covered by it: P1-1, P1-2, P1-3, P2-1, P2-2, P2-6.

## Verdict

The documentation work is mostly closed: the README is a clear 380-line what/how/where, links and file
paths all resolve, the API reference, ports, environment variables, flags, risk table and tab list match
the code, and nothing claims edge, profit or certainty for SONAR's own results. It is not ready to close.
Three things should be fixed before sign-off: the README still describes the removed mechanism by which the
track record moved P(profit) (README:25, :134-135 against `calibration.py:15-20`, the central honesty
statement and something the manual already corrected); the README's 1,811-test count makes committed HEAD
fail its own count-guard test (1,763 collected), which resolves only if the other session's work lands
with the README; and the CHANGELOG stops at v2.131 while build 178 is installed and every audit fix sits
unrecorded. After those, the manual's "zero LLM calls / No cost" and stale run-figure sentences, the
undocumented off-disk backup, and the missing note that a fresh clone needs the two nested repos are the
next fixes. I made no edits other than this file; the playbook is still `baseline`, so this review used
the repo rules rather than a tuned practice.
