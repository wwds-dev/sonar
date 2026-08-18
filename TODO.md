# SONAR — TODO

> **Legend** — priority `P0` critical · `P1` high · `P2` normal · `P3` low
> categories `security` `bug` `feature` `performance` `design` `docs` `testing` `infra` `research`
> owner `@me` (needs you — accounts, keys, money, judgement) · `@ai` (Claude can do this)

---

## v2 — current

- [ ] `P0` `infra` `@me` **Get a free Finnhub API key.** Equities have no keyless second source, so most of the watchlist rides on one undocumented Yahoo endpoint. Single highest-value change in the project.
- [ ] `P1` `research` `@me` **Let the paper book run.** The calibration table stays empty until ~20 positions have closed. No amount of backtesting substitutes for a track record.
- [ ] `P1` `bug` `@ai` Async fills are unhandled — `Portfolio.enter` records the position at the intended price the moment `execute` returns. Against any real venue that means *accepted*, not *filled*. Needs an order-state poller before the book means anything.
- [ ] `P2` `testing` `@ai` Reconciliation drill as an automated test: mutate the venue behind SONAR's back, assert it detects the divergence and halts
- [ ] `P2` `testing` `@ai` Kill-switch test — open a position, call `flatten()`, assert flat at the venue rather than only in the log
- [ ] `P3` `docs` `@ai` Fold the GOING_LIVE §0 arithmetic into the README so the cost floor is visible without opening a second file

## v3 — only if the research is resumed

- [ ] `P2` `research` `@me` Intraday bars, order flow, or a tone-tagged news archive. Five studies found nothing in daily bars, free news and macro regimes; more features on the same data is not the answer.
- [ ] `P3` `feature` `@ai` Week-over-week deltas on scans, to show which signals are growing rather than merely large

## Explicitly not planned

- [ ] `P0` `security` `@me` **Real-money execution stays off.** SONAR will not place live orders or connect a funded broker. `portfolio.default_broker()` returns Alpaca paper or the internal book — a live venue would have to be constructed explicitly by a caller that means it, never via a fallback chain.
- Revolut integration — investigated and closed. No public retail-investment API; balances would need a licensed Open Banking aggregator.
