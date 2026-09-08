# SONAR — TODO

> **Legend** — priority `P0` critical · `P1` high · `P2` normal · `P3` low
> categories `security` `bug` `feature` `performance` `design` `docs` `testing` `infra` `research`
> owner `@me` (needs you — accounts, keys, money, judgement) · `@ai` (Claude can do this)

---

## v2 — current

- [ ] `P0` `infra` `@me` **Get a free Finnhub API key.** Equities have no keyless second source, so most of the watchlist rides on one undocumented Yahoo endpoint. Single highest-value change in the project.
- [ ] `P1` `research` `@me` **Let the paper book run.** The calibration table stays empty until ~20 positions have closed. No amount of backtesting substitutes for a track record.
- [x] `P1` `bug` `@ai` ~~Async fills are unhandled.~~ Positions from an asynchronous broker are recorded `PENDING`: no unrealised P&L, never marked against a barrier, cash reserved but refunded if the order dies. `Portfolio.poll_fills()` is the order-state poller, wired into `_mark_book`; it rewrites the position from the venue's real quantity and fill price. Target and stop survive a worse fill on purpose.
- [x] `P2` `testing` `@ai` ~~Reconciliation drill.~~ `tests/test_drills.py` mutates the venue directly — a position appearing, vanishing, and changing size — and asserts each is detected, halts the guard, and blocks the next order. Includes the control where the two agree and nothing fires.
- [x] `P2` `testing` `@ai` ~~Kill-switch drill.~~ `tests/test_drills.py` opens positions through the book and asserts the venue is flat afterwards — from a clean guard, from an already-halted one, and with the daily order cap exhausted.
- [x] `P3` `docs` `@ai` ~~Fold the cost floor into the README.~~ Now a subsection of *Risk, reward, and the probability of profit*, with the measured €1.05 per round trip and the note that the earlier estimate was optimistic.
- [x] `P1` `bug` `@ai` ~~Window opened wider than the screen.~~ SONAR once opened **4,540pt wide** on a 1,280pt display — an unwrapped `QLabel` reports a sizeHint as wide as its text, a layout can't shrink below its children's minimums, and a `QTabWidget`'s minimum is its widest tab's, so one long prose label silently overrode every `resize()` call. Fixed: `label(..., wrap=True)` on the long prose labels, plus `MainWindow._fit_to_screen()` (`ui/app.py`) which opens at `PREFERRED_SIZE` (1180×820) or the actual screen's available geometry minus a margin, whichever is smaller, instead of an unconditional `resize(1180, 820)`. Covered by `tests/test_layout.py` (5 tests, measuring `minimumSizeHint()` against a 1280×775 13" MacBook baseline rather than whatever screen the test runner has).

## v3 — only if the research is resumed

- [ ] `P2` `research` `@me` Intraday bars, order flow, or a tone-tagged news archive. Five studies found nothing in daily bars, free news and macro regimes; more features on the same data is not the answer.
- [ ] `P3` `feature` `@ai` Week-over-week deltas on scans, to show which signals are growing rather than merely large

## Explicitly not planned

- [ ] `P0` `security` `@me` **Real-money execution stays off.** SONAR will not place live orders or connect a funded broker. `portfolio.default_broker()` returns Alpaca paper or the internal book — a live venue would have to be constructed explicitly by a caller that means it, never via a fallback chain.
- Revolut integration — investigated and closed. No public retail-investment API; balances would need a licensed Open Banking aggregator.
