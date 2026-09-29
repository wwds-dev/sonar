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
| 7 | Turn news/vol/catalyst from levels into surprises against each instrument's own baseline (`CONFIDENCE.md` §5) | research | S | PLANNED |
| 9 | Daily GPR-style political index computed from the newswire SONAR already reads (`CONFIDENCE.md` §7.1) | feature | M | IDEA |
| 10 | **Volatility component is inverted for ranking** — 10 of 12 configurations show a negative IC, quintile gradient 45.3%→34.5%, and the tie-break artefact is ruled out (zero ambiguous bars). But it fails the time-block test at 5/6, p=0.22, with the most recent period reversing — so the weights are unchanged. Also a design question, not only an empirical one: high volatility is correct for *notability* and backwards for *ranking winners* (`CONFIDENCE.md` §10a) | research | M | BLOCKED |
| 14 | Hit rate vs τ-at-entry | research | S | BLOCKED — first readout at 118 trades says nothing yet: 75% of entries land at τ 0.6–0.85 and the other buckets hold 5–10 trades with ±28–44-point bands. Re-read at gate ② |
| 15 | Playmaker verdict polish | research | S | **PART DONE** — the KEEP bar is now `Score.skill_floor`, a seeded block-bootstrap interval on the per-game Brier differences. The Dixon-Coles outer refit stays open: it would shift fitted numbers, and the football feed measurement to re-earn them should run through the Lab's new sports panel first |

## Interface

| # | Suggestion | Category | Effort | Status |
|---|---|---|---|---|
| 9 | Confidence score shown as a distribution rather than a single number | design | M | IDEA |
| 10 | Export a closed round trip as a one-page post-mortem (entry, exit, thesis, realized cost) | feature | S | IDEA |
| 15 | **Guided mode for the Lab** — controls phrased as questions, a verdict in words above the table, and the three tests that decide whether a result means anything stated inline rather than assumed | feature | L | PLANNED |
| 16 | **First-run cards**: paper money, notability is not direction, start on Assets, check claims in the Lab, the manual is a tab | feature | M | PLANNED |
| 17 | Say what would change an "unproven" — "needs ~20 closed positions, you have 3" — wherever the app refuses to claim something | design | S | PLANNED |

## Done

| Suggestion | When |
|---|---|
| **The Cockpit shell** — GUI round 2, from a mockup approved before any code moved: the eight tabs became a left rail (both names each, folding to icons below 1420pt), a page header names every screen and keeps the risk/horizon knobs visible everywhere, and the Terminal's six equal cells became a hierarchy with the edge largest. CHANGELOG v2.116, README §"The Cockpit shell" | 2026-09-29 |
| GUI direction — three mockups (refined dark, light high-contrast, plain-language restructure); Plain Language chosen. `ui/theme.py` rewritten, `ui/tabs.py` added, the Screener rebuilt around it. README §"The Plain Language direction" records the rules | 2026-09-22 |
| Plain / expert vocabulary switch — `ui/words.py` plus the Wording button. Plain default; expert restores MOM/VOL/R:R/CONF, the ticker and single-line names, and drops the second lines. Vocabulary and density only — a test asserts the columns are identical in both | Sep 2026 |
| The manual inside the app — the Learn tab; `ui/learn.py` translates `static/docs.html` into Qt rich text, contents built from the page's own headings | Sep 2026 |
| "How old is this price?" — the AGE/Updated column, anchored to the scan's `generated` stamp so it keeps counting between scans; gold past a full rotation, red past an hour | Sep 2026 |
| A link on every heading — headings that name something non-obvious open the Learn tab at the explaining section; a test asserts every anchor resolves | Sep 2026 |
| Plain-English headings and one plain sentence per row — "up hard, heavy news", generated from numbers already on the row; a test asserts the sentence can never acquire a direction | Sep 2026 |
| Executable model-vs-market — `Engine.buyability()` prices the model's side at each hour's recorded touch across five edge gates, refusing below 100 qualifying hours; the first version's 'positive at every gate' was 77% one settlement-state row and died under adversarial review | 2026-09-29 |
| Backfill a historical earnings calendar — `sonar/research/earnings.py` (EDGAR Item-2.02 8-Ks); the catalyst weight became the first component ever to pass attribution (IC +0.040, 6/6 blocks, phase-shift control inverts). A volatility effect, not a direction | Sep 2026 |
| Cross-sectional z-scoring within asset class — `sonar/crosssection.py`; class median CONF spread 18 → 8.6 points. Standardises the raw quantity, not the clipped component (the latter is a silent no-op for saturated classes). Was listed twice (#8/#11) | Sep 2026 |
| Grow the watchlist — 26 → 129, every class ≥18, every symbol verified to return a year of closes first; forced the rolling refresh, because refetching all of them got the source throttling | Sep 2026 |
| Volatility forecast instead of trailing realised vol — `sonar/volatility.py`: GARCH below 10 days (+11.6% at 3d, +17.8% at 5d on QLIKE), trailing-250 above. A synthetic control killed the first, much larger result | Sep 2026 |
| Order-state poller so the book records fills rather than intents — `Portfolio.poll_fills()`, wired into `_mark_book` | Sep 2026 |
| `GuardedBroker.confirmation_text` rendered verbatim, never re-composed — `execution.confirmation_text()` is the only composer | Sep 2026 |
| Automated reconciliation and kill-switch drills — `tests/test_drills.py`, run by CI on every push | Sep 2026 |
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
