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

## Safety rails

| # | Suggestion | Category | Effort | Status |
|---|---|---|---|---|
| 6 | Order-state poller so the book records fills rather than intents | bug | L | PLANNED |
| 7 | `GuardedBroker.confirmation_text` rendered verbatim in the dialog, never re-composed by callers — the `*** REAL MONEY ***` prefix only works if nothing else writes it | security | S | PLANNED |
| 8 | Automated reconciliation and kill-switch drills in CI | testing | M | CONSIDERING |

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

## Rejected

| Suggestion | Why |
|---|---|
| Real-money execution | Paper P&L predicts nothing; an earlier run showed +114% on a 44% win rate carried by three longshots. Variance in a costume. |
| Revolut holdings sync | No public retail-investment API |
| More features on daily bars | Five studies found nothing there |
