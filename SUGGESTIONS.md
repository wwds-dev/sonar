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
| 8 | Cross-sectional z-scoring within asset class, so a score means the same thing for a coin and a currency (`CONFIDENCE.md` §3) | research | S | PLANNED |
| 9 | Daily GPR-style political index computed from the newswire SONAR already reads (`CONFIDENCE.md` §7.1) | feature | M | IDEA |
| 10 | **Volatility component is inverted for ranking** — 10 of 12 configurations show a negative IC, quintile gradient 45.3%→34.5%, and the tie-break artefact is ruled out (zero ambiguous bars). But it fails the time-block test at 5/6, p=0.22, with the most recent period reversing — so the weights are unchanged. Also a design question, not only an empirical one: high volatility is correct for *notability* and backwards for *ranking winners* (`CONFIDENCE.md` §10a) | research | M | BLOCKED |
| 11 | **Cross-sectional z-scoring within asset class** (`CONFIDENCE.md` §10b H3) — structurally right and it halves the blend's regime-to-regime swing (range 0.22 → 0.11), but three of five classes have ≤3 members and a MAD over two instruments is not a standardisation. Needs a bigger watchlist first | research | M | BLOCKED |
| 12 | **Grow the watchlist so classes can carry a cross-sectional statistic** — the blocker on #11. Index, Forex and Commodity have 3, 3 and 2 members | data | M | IDEA |

## Safety rails

| # | Suggestion | Category | Effort | Status |
|---|---|---|---|---|
| 6 | Order-state poller so the book records fills rather than intents | bug | L | **DONE** — `Portfolio.poll_fills()`, wired into `_mark_book` |
| 7 | `GuardedBroker.confirmation_text` rendered verbatim in the dialog, never re-composed by callers — the `*** REAL MONEY ***` prefix only works if nothing else writes it | security | S | **DONE** — `execution.confirmation_text()` is the only composer, and no UI path re-writes it |
| 8 | Automated reconciliation and kill-switch drills | testing | M | **DONE** — `tests/test_drills.py`, 8 tests. The "in CI" half is still open: there is no CI, so nothing runs them but a person |
| 9 | **A CI runner.** Everything above is checked by someone remembering to. 868 tests in 3.5s would fit any free runner — the obstacle is the Qt window tests wedging ~1 in 3, which would make a red build meaningless | infra | M | IDEA |

## Interface

| # | Suggestion | Category | Effort | Status |
|---|---|---|---|---|
| 9 | Confidence score shown as a distribution rather than a single number | design | M | IDEA |
| 10 | Export a closed round trip as a one-page post-mortem (entry, exit, thesis, realized cost) | feature | S | IDEA |

## Done

| Suggestion | When |
|---|---|
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
