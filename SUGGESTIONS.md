# SONAR — Suggestions

Status: `IDEA` · `CONSIDERING` · `PLANNED` · `DONE` · `REJECTED`

---

## Data and model

| # | Suggestion | Category | Effort | Status |
|---|---|---|---|---|
| 1 | Finnhub as the second equities source — removes the single point of failure on the undocumented Yahoo endpoint | infra | S | PLANNED |
| 2 | Show provider provenance per quote in the UI, so a silent fallback is visible rather than invisible | design | S | CONSIDERING |
| 3 | Calibration table auto-refresh once ≥20 paper positions have closed | feature | M | PLANNED |
| 4 | Week-over-week scan deltas from the cached scans already on disk | feature | M | IDEA |
| 5 | Intraday bars or order flow as a research input — the only honest way to reopen the study | research | XL | IDEA |
| 6 | Volatility *forecast* instead of trailing realised vol | research | M | **DONE** — `sonar/volatility.py`. GARCH below 10 days (+11.6% at 3d, +17.8% at 5d on QLIKE), trailing-250 above (+5.6% at 20d). A synthetic control killed the first, much larger result: most of it was sample size, not clustering |
| 7 | Turn news/vol/catalyst from levels into surprises against each instrument's own baseline (`CONFIDENCE.md` §5) | research | S | PLANNED |
| 8 | Cross-sectional z-scoring within asset class (`CONFIDENCE.md` §3) | research | S | **DONE** — duplicate of #11, see there |
| 9 | Daily GPR-style political index computed from the newswire SONAR already reads (`CONFIDENCE.md` §7.1) | feature | M | IDEA |
| 10 | **Volatility component is inverted for ranking** — 10 of 12 configurations show a negative IC, quintile gradient 45.3%→34.5%, and the tie-break artefact is ruled out (zero ambiguous bars). But it fails the time-block test at 5/6, p=0.22, with the most recent period reversing — so the weights are unchanged. Also a design question, not only an empirical one: high volatility is correct for *notability* and backwards for *ranking winners* (`CONFIDENCE.md` §10a) | research | M | BLOCKED |
| 11 | Cross-sectional z-scoring within asset class | research | M | **DONE** — `sonar/crosssection.py`. Class median CONF spread 18 → 8.6 points; Forex's volatility component went from a 0.23 ceiling to a 0.60 one. Standardises the *raw* quantity, not the clipped component — doing the latter is a silent no-op for the saturated classes |
| 12 | Grow the watchlist so classes can carry a cross-sectional statistic | data | M | **DONE** — 26 → 129, every class ≥18. Every symbol verified to return a year of closes before being added; the growth also forced a rolling refresh, because refetching all of them took the request rate from ~13/min to ~64 and the source throttles below that |
| 13 | **Backfill a historical earnings calendar** so the catalyst weight can face attribution — it is 0.20 of the confidence score and the only component never measured (the replay honestly reports "not measured"). EDGAR filing dates are free; even a partial backfill grades the weight | research | M | IDEA |
| 14 | **Hit rate vs τ-at-entry**, once the hourly score log has a few weeks of data — the entry window (0.12–0.80 of the hour) is currently a guess, and the log records the τ of every snapshot | research | S | BLOCKED — needs the score log to fill |
| 16 | **Executable model-vs-market**, once the score log has data — the log now carries the bid/ask per snapshot, so beyond Brier ("who was better calibrated") it can answer whether the model's disagreements were ever buyable after the spread | research | S | BLOCKED — needs the score log to fill |
| 15 | Playmaker verdict polish: a block-bootstrap interval on the Brier difference instead of the `1/√games` margin, and one outer refit iteration in Dixon-Coles so `rho` and the home advantage feed back into the strengths (both named as simplifications in `poisson.py`) | research | S | IDEA |

## Safety rails

| # | Suggestion | Category | Effort | Status |
|---|---|---|---|---|
| 6 | Order-state poller so the book records fills rather than intents | bug | L | **DONE** — `Portfolio.poll_fills()`, wired into `_mark_book` |
| 7 | `GuardedBroker.confirmation_text` rendered verbatim in the dialog, never re-composed by callers — the `*** REAL MONEY ***` prefix only works if nothing else writes it | security | S | **DONE** — `execution.confirmation_text()` is the only composer, and no UI path re-writes it |
| 8 | Automated reconciliation and kill-switch drills | testing | M | **DONE** — `tests/test_drills.py`, 8 tests. Now also run by CI on every push (see Done) |

## Interface

| # | Suggestion | Category | Effort | Status |
|---|---|---|---|---|
| 9 | Confidence score shown as a distribution rather than a single number | design | M | IDEA |
| 10 | Export a closed round trip as a one-page post-mortem (entry, exit, thesis, realized cost) | feature | S | IDEA |
| 11 | **The manual inside the app** rather than behind a button that opens a browser | design | M | **DONE** — the Learn tab. `ui/learn.py` translates `static/docs.html` into Qt rich text (its CSS is variables and flexbox, none of which Qt renders); contents from the page's own headings, so a new section appears without anyone remembering to list it |
| 12 | **How old is this price?** on every Assets row | design | S | **DONE** — the AGE column. Anchored to the scan's `generated` stamp so it keeps counting between scans instead of freezing at what the scan measured; gold past a full rotation, red past an hour |
| 13 | A **link on every heading** that opens the Learn tab at the paragraph explaining that number | design | M | **DONE** — headings that name something non-obvious carry a docs anchor and are drawn in the link colour; `tests/test_plain_language.py` asserts every anchor resolves to a section that exists |
| 14 | **Plain-English headings**, and one plain sentence per row | design | S | **DONE** — headings are words, values carry a second line saying what they mean (*big swings*, *over 5 days*), and each row reads "up hard, heavy news". A test asserts that sentence can never acquire a direction |
| 15 | **Guided mode for the Lab** — controls phrased as questions, a verdict in words above the table, and the three tests that decide whether a result means anything stated inline rather than assumed | feature | L | PLANNED |
| 16 | **First-run cards**: paper money, notability is not direction, start on Assets, check claims in the Lab, the manual is a tab | feature | M | PLANNED |
| 17 | Say what would change an "unproven" — "needs ~20 closed positions, you have 3" — wherever the app refuses to claim something | design | S | PLANNED |
| 18 | **Plain / expert vocabulary switch** | design | M | **DONE** — `ui/words.py` plus a toolbar button. Plain is the default; expert restores MOM/VOL/R:R/CONF, the ticker and single-line tabs, and drops the second lines (~⅓ shorter rows). Vocabulary and density only — a test asserts the columns are identical in both, so there is never a second layout to keep true |
| 19 | **GUI direction** — three mockups (refined dark, light high-contrast, plain-language restructure) | design | L | **DONE** — Plain Language chosen. `ui/theme.py` rewritten, `ui/tabs.py` added, the Screener rebuilt around it. README §"The Plain Language direction" records the rules |

## Done

| Suggestion | When |
|---|---|
| A CI runner — `.github/workflows/tests.yml`, the suite on every push under `QT_QPA_PLATFORM=offscreen`. The recorded blocker (window tests wedging ~1 in 3) was fixed 2026-09-19 by the session-scoped conftest guards, so the row's premise was stale | Sep 2026 |
| Pre-run instrumentation — bid/ask on every hourly snapshot (unbackfillable), run-health line + STALLED menu-bar notification, daily rotating state-file backups, and protocol mode for the calibration table. Detail in `TODO.md` | Sep 2026 |
| The 2026-09-19 review fixes — gap settlement, seeded rows out of live stats, executable-edge gate, the hourly model-vs-market Brier log, EWMA × hour-of-day σ (measured +7.5% QLIKE first), overlap-corrected backtest error bars, rank-IC calibration verdict, measured draw rate, draws out of Playmaker accuracy, the run-tests.sh watchdog leak. Detail in `TODO.md` | Sep 2026 |
| Providers, Alpaca paper trading, the paper book, the research apparatus and the calibration loop | Aug 2026 |
| `GuardedBroker` shipped — rejections raise rather than return an error dict | Aug 2026 |
| Execution guard for the simulator | Aug 2026 |
| Startup latency — 26 asset-chart fetches and 14 news feeds parallelised (`ThreadPoolExecutor`, `~6s→~1s` and `~3s→~1 feed` respectively); the Terminal snapshot now publishes before the asset rescan, so the window shows live data instead of holding on "starting…" for the ~11s the full scan used to take | Aug 2026 |
| Dock-click-reopens-a-hidden-window bug fixed — a Space-transition exit re-fires the same activation event a real Dock click sends; the window now ignores that event for ~1s after it hides itself (`reopen_allowed`) | Aug 2026 |
| Shutdown crash fixed — the backtest and Playmaker threads were missing from the quit-time stop list, so a `SIGABRT` landed if either was still running when the window closed | Aug 2026 |
| Playmaker tab — `sonar/playmaker/`'s NFL prop-bet arithmetic got its own tab (renamed from "Sports"), and the module was renamed to match | Aug 2026 |
| Window-too-wide bug fixed — unwrapped prose labels were setting an unshrinkable minimum window width (opened 4,540pt wide on a 1,280pt screen); labels now wrap and `MainWindow._fit_to_screen()` clamps the opening size to the actual screen | Sep 2026 |
| Closing SONAR could leave a blank white window that never went away — the Wire tab was fetching news/events on the UI thread whenever their cache aged out; fixed to read cache-only, with tests asserting no network access from the UI thread | Sep 2026 |
| In-app docs (`docs.html`) gained a plain-English "Start here" intro, a 24-term glossary, and a "which tab do I want" table; a new section documents Playmaker for the first time | Sep 2026 |
| Playmaker gained native prediction models — Elo (FiveThirtyEight's published form), Dixon-Coles for football, Pythagorean as a cross-check, fed by a keyless ESPN adapter; NFL/NBA/EPL all came back KEEP on walk-forward skill | Sep 2026 |
| Testing roadmap tier 1 — `model.py` and `engine.py` (the two modules the Terminal tab and the Book are built on) taken from 39%/38% coverage to 100%, mutation-checked; found and fixed a real ten-point disagreement between `prob_up` and `lattice_distribution` on the Terminal tab. See `TESTING.md` | Sep 2026 |
| Playmaker packaging trap fixed — its model modules (`results`, `ratings`, `poisson`, `scoring`) were invisible to PyInstaller until first used, the same shape as the earlier `anthropic`/`execution`/`costs` trap; `build_app.sh` now hidden-imports them and `--selftest` checks for their presence | Sep 2026 |

## Rejected

| Suggestion | Why |
|---|---|
| Real-money execution | Paper P&L predicts nothing; an earlier run showed +114% on a 44% win rate carried by three longshots. Variance in a costume. |
| Revolut holdings sync | No public retail-investment API |
| More features on daily bars | Five studies found nothing there |
