# Documentation audit — 2026-10-10

Scope: `README.md` (1062 lines), `static/docs.html` (1085), `CHANGELOG.md`, `TESTING.md`,
`TESTPLAN.md`, `GOING_LIVE.md`, `VERSIONING.md`, `TODO.md`, `SUGGESTIONS.md`, `AGENTS.md`.
No existing file was modified. Checked against HEAD `6424857` (build 149), `.venv` Python 3.11.

## Verified correct (so nobody re-checks)

| Claim | Where | Result |
|---|---|---|
| 8 tabs, names and order | README:13, docs.html:294, TESTPLAN:56 | `ui/app.py:1072-1097` adds exactly 8, in that order |
| 129 instruments: 50/20/20/21/18 | README:27, docs.html:110, 321 | `len(assets.WATCHLIST)`: Equity 50, Index 20, Forex 20, Crypto 21, Commodity 18 |
| 1,582 tests | README:775, TESTING:13, TESTPLAN:20 | `pytest --collect-only`: 1582 collected, 30 deselected (the `network` marker) |
| 24 news feeds | README:66, docs.html:331 | `len(news.FEEDS)` = 24 |
| 145 acceptance cases, 18 regressions | README:764-768 | 145 numbered rows; 18 rows marked with the warning sign |
| Version scheme `v2.<commit count>` | VERSIONING, `sonar/version.py` | `VERSION`=2, `_build_info.json` build 148, `rev-list --count` 149 (the build is stamped one commit behind HEAD, which is expected) |
| Scripts named in the docs exist | README:770, 823-825, VERSIONING:73 | `build_testplan.py`, `install_agent.sh`, `stamp_version.py` present |

## P0 — contradicts the product's own honesty rule or misleads on a headline claim

**None found.** No sentence claims an edge, profit or certainty. The no-edge position is stated
consistently in README, `static/docs.html`, GOING_LIVE and CONFIDENCE. The P1s below are the closest
thing: the evidence count is quoted two different ways.

## P1 — wrong or self-contradicting, in the places a new reader reads first

1. **"Five studies" vs "six studies".** README:364 says "Six studies" and README:328 is headed "The
   sixth study". But README:1040, `static/docs.html:75, 121, 758, 827, 911` and `GOING_LIVE.md:16`
   all say five, and `CONFIDENCE.md:12` says "Five pre-registered studies". The in-app manual,
   which a newcomer actually reads, is a study behind the README, and it says every one was
   negative, while README:364-370 says the sixth *passed* ("the first survivor").
   Fix: pick one count and one sentence for the sixth result ("a volatility-shaped survivor, not a
   directional edge"), then update docs.html §1, §11, §13, CONFIDENCE:12 and GOING_LIVE:16 to match.
   The manual's "All of them negative" (docs.html:827) is the line most likely to be wrong.
2. **README:57 and README:768 refer to a "Docs" button that no longer exists.** The rail foot has
   a wording switch and a **Test plan** button only (`ui/app.py:1206-1231`). The manual is the Learn
   tab, with "Open in browser" inside it (`ui/app.py:1325`). TESTPLAN:26 correctly says "next to
   *Learn*". Fix: README:57 "behind the Learn tab"; README:768 "next to the wording switch".
3. **README:219 "113 instruments" against 129 everywhere else.** It is probably the number that
   survived the backtest's data filter, but nothing says so. Fix: "113 of the 129 (the rest lacked
   five years of bars)", after confirming the reason.
4. **README:740-744 says `universe.py` and `research/features.py` are "the next gaps".** TESTING.md
   (progress note and the 2026-10-10 section) says `research/features.py` is done and the 80% figure
   is current. Fix: replace the paragraph with a pointer to TESTING §0, or drop the "next gaps" list.
5. **README API table (README:1024-1032) lists 5 of ~12 routes.** `sonar/server.py:53-116` also
   serves `/api/macro`, `/api/book`, `/api/wire`, `/api/trade`, `/api/close`, `/docs`, `/testplan`.
   The README:869 sentence about "original browser dashboards" does not say these exist. Fix: add
   the rows, or say "the main routes; see `sonar/server.py`".
6. **README Layout (README:968-1020) is out of date.** `macro.py` is now a package (`sonar/macro/`);
   the `playmaker/` entries omit `ratings.py`, `poisson.py`, `results.py`, `scoring.py` (named in
   README:706); `research/` omits `earnings.py` and `study.py`. `tests/`, `scripts/`, `packaging/`,
   `docs/`, `static/testplan.html` and `CONFIDENCE.md` are not listed. `ui/app.py` line lists
   "the Learn" as a tab but the 3,000-line file has no breakdown.

## P2 — onboarding gaps (new user / new contributor)

7. **No "start here" in the README.** The first screen is a story about a viral post (README:3-12),
   then a table dense with jargon. There is no three-line answer to "what is this, what do I do in
   the first five minutes". `TODO.md:119` ("Nothing greets a first launch") records the same gap
   inside the app. Fix: a 5-line "What you do first" block before the tab table: run it, open
   Screener, read Learn §1, place one paper trade, come back in a day.
8. **Setup instructions assume tooling.** README:688 `uv venv .venv && uv pip install ...` never
   says to install `uv`, never states the Python floor (`pyproject.toml:6` requires >=3.11; the
   default `python3` on this machine is 3.14, has no PySide6, and no pytest), and says "native
   macOS app" without saying Linux/Windows are unsupported or untested. `run-tests.sh` defaults to
   `.venv/bin/python`, so a contributor who skips the venv gets a confusing failure.
9. **README:678 `pip install anthropic` vs `requirements.txt:5`.** The line is commented out in
   `requirements.txt` and the instruction is in a different section from the install block.
10. **No contributor entry point.** `AGENTS.md` is the process, but no doc says how to run one test,
    how CI runs (QT offscreen twice rule is only in TESTING:13), how to add a docs section so
    `ui/learn.py` renders it, or that `CHANGELOG` needs `rev-list --count + 1` (that last is in
    VERSIONING:48, which is not linked from README). No `.env.example` though README:400, 616 tell
    the reader to create `.env` with three different keys (Alpaca, Finnhub, FRED/Anthropic).
    No LICENSE file.
11. **README:746 "Learning what the numbers mean" and README:760 "Testing" are nested under "Run
    it" next to "### Tests" (README:724).** Two headings named Tests/Testing 36 lines apart with
    overlapping content (the run-tests commands appear at 724 and 775).
12. **`TODO.md` mixes done and open under "## Open".** README:9-57 of TODO.md is mostly struck-through
    `[x]` items; the `## v2 — current` section holds the genuinely open P0/P1 (Finnhub key, let
    the book run). A reader looking for what is open must scroll ~140 lines. Fix: move done items
    to a `## Done` section or to CHANGELOG, keep only `[ ]` in Open.

## P3 — jargon, duplication, hygiene

13. **Undefined jargon on first use**, README: R:R (26-27, defined only at 164), IC, quintile spread,
    leave-one-out (README:32), Newey-West (README:222), FDR (README:371), Brier (README:57
    precursor in docs; defined in docs.html:657 glossary only), Kelly, devig/Shin (README:44-47),
    EWMA, QLIKE, GARCH, "barrier" and "lattice". Fix: README should link to Learn §1 glossary at
    first use, or carry a six-term mini-glossary near the top.
14. **Doc sprawl and duplication.** The same facts live in several places and drift: the study
    results (README 213-390, CONFIDENCE.md 533 lines, docs.html §11, GOING_LIVE §0, TODO "score
    itself"), the test counts (README:775, TESTING:13, TESTPLAN:20, TESTING per-module counts), and
    the plain-language rules (README 545-630, 85 lines, plus docs.html and TESTPLAN §3). README at
    1062 lines holds product description, research notebook, design history ("The Cockpit shell",
    "The portfolio landing page", README:432-545) and runbook. Fix: move the design-history sections
    to `docs/specs/` or CHANGELOG, move study narrative to CONFIDENCE.md, leave README at about 300
    lines of what/how/where.
15. **Duplicate numbering in `SUGGESTIONS.md`.** `#9`, `#10`, `#15` each appear twice (Data and model
    table at lines 11-18 and Interface table at 23-27). References such as "suggestion 10" are
    ambiguous. Fix: renumber or prefix (D-10, I-10).
16. **`SUGGESTIONS.md` #1 is PLANNED and TODO.md:150 is a P0 `@me`** for the same Finnhub key while
    README:1039 calls it "the single highest-value change" — three statuses for one item. Keep
    the status in one file.
17. **README:928-955 "Which version am I running?" uses `v2.103`/`v2.107` as the example** while the
    current build is v2.148 and the CHANGELOG head is v2.131. Harmless if labelled as an example;
    label it. CHANGELOG:1-12 explains that only installed builds are listed, but does not say
    the current HEAD is ahead of the newest entry.
18. **GOING_LIVE.md:476 and :483 are first-person assistant prose** ("I will not write the live
    adapter... Ask, and I will start with §6"). The document is otherwise a plan; AGENTS.md says
    the owner is the only approver. Fix: rewrite as "Out of scope until the owner says otherwise in
    writing" and a neutral pointer to §6.
19. **README:1056-1062 "Not advice" is correct but sits last at line 1056.** The disclaimer a reader
    needs belongs near the top, next to the "paper money" statement (README:59 "What's real vs
    simulated" is good — link to it from line 3).
20. **docs_attention_study.json and `research_results/` at the repo root** are not described in the
    Layout section; a newcomer cannot tell whether they are inputs, outputs or leftovers.
21. **README:430 "Revolut" investigated and closed (README:1049-1052)** is unrelated to everything
    else and reads like a chat note. Move to `docs/` or drop.

## Suggested order of work

1. Settle the study count and propagate it (item 1), one commit across five files.
2. Fix the two "Docs button" references and the 113/129 number (items 2, 3).
3. Add the "first five minutes" block and the setup prerequisites (items 7, 8).
4. Refresh Layout and API tables (items 5, 6), then split README (item 14).
5. Housekeeping: SUGGESTIONS numbering, TODO open/done split, GOING_LIVE voice (items 12, 15, 16, 18).

Not verified: the 113-instrument cause; the 25-term glossary count (README:754) — docs.html has no
machine-countable glossary markup; the 98 MB bundle size (README:686); the 96%/99% coverage figures
in TESTING.md (no coverage run was made).
