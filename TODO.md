# SONAR — TODO

> **Legend** — priority `P0` critical · `P1` high · `P2` normal · `P3` low
> categories `security` `bug` `feature` `performance` `design` `docs` `testing` `infra` `research`
> owner `@me` (needs you — accounts, keys, money, judgement) · `@ai` (Claude can do this)

---

## Open

- [x] `P1` `testing` `@ai` ~~The probability model has no tests at all.~~
      `sonar/model.py` went 39% → **100%**. Writing the tests found a real bug:
      `prob_up` (closed form) and `lattice_distribution` (binomial approximation)
      disagreed by ten points at the top of every hour, because the lattice's
      exact-middle bin sits exactly on the barrier when price == open and handed
      all of it to "up". Fixed by splitting that bin. `TESTING.md` §1.
- [x] `P1` `testing` `@ai` ~~The paper engine's tick/enter/settle path is
      untested.~~ `sonar/engine.py` went 38% → **100%**: 39 tests against a real
      engine and state file, mutation-checked (five deliberate bugs planted,
      all five caught). `TESTING.md` §1.
- [ ] `P2` `testing` `@ai` **Split parse from fetch in `feeds.py` and
      `universe.py`** (30% and 17%) so the parsers can be tested on saved
      payloads, the way `playmaker/results.py` already is. A payload-shape
      change currently zeroes a price silently rather than raising.
      `TESTING.md` §2.
- [ ] `P2` `testing` `@ai` **`server.py` has never been run by a test** (0%),
      and it is now the documented answer for uptime. `TESTING.md` §2.
- [ ] `P2` `feature` `@ai` **The Lab tab cannot test the Playmaker models.**
      It measures the markets algorithm only — the Elo/Dixon-Coles scoring runs
      from a script, not the UI, so there is no way to re-run it after a change
      from inside the app. Everything it needs exists in
      `playmaker/scoring.py`.


- [ ] `P2` `bug` `@ai` **The window tests wedge about one run in three.**
      Sampling a hung process shows the main thread in `PyThread_release_lock`
      waiting on a pthread mutex that a torn-down Qt thread never released —
      a deadlock below Python, so `faulthandler_timeout` cannot fire (the dump
      needs the lock that is held). `./run-tests.sh` bounds it from outside the
      process and samples the stack before killing, which is the mitigation, not
      the fix. Ruled out already, so nobody repeats the search: the network
      (blocked, still hangs), shared state (`tmp_path`, still hangs), the poll
      thread (no-op'd, still hangs), undrained `deleteLater` (drained, got
      *worse* — 3/5), and cross-file window accumulation (each file in its own
      process, 1/5). Next thing to try is a session-scoped window fixture, or
      `pytest-forked`. The app itself is unaffected.

---

## v2 — shipped

Everything below landed. What remains in v2 is two items that need an account
and time rather than code, kept at the top.

- [ ] `P0` `infra` `@me` **Get a free Finnhub API key.** Equities have no keyless second source, so most of the watchlist rides on one undocumented Yahoo endpoint. No code needed — `providers.py` already registers Finnhub at preference 5, ahead of Yahoo, and picks the key up from `FINNHUB_API_KEY` in a git-ignored `.env`. Also removes the ~15-minute quote delay during market hours.
- [ ] `P1` `research` `@me` **Let the paper book run.** The calibration table stays empty until ~20 positions have closed. No amount of backtesting substitutes for a track record.

### Execution and the paper book

- [x] `P1` `bug` `@ai` ~~Async fills are unhandled.~~ Positions from an asynchronous broker are recorded `PENDING`: no unrealised P&L, never marked against a barrier, cash reserved but refunded if the order dies. `Portfolio.poll_fills()` is the order-state poller, wired into `_mark_book`; it rewrites the position from the venue's real quantity and fill price. Target and stop survive a worse fill on purpose — slippage should eat the reward, not move the goalposts.
- [x] `P2` `testing` `@ai` ~~Reconciliation drill.~~ `tests/test_drills.py` mutates the venue directly — a position appearing, vanishing, changing size — and asserts each is detected, halts the guard, and blocks the next order. Includes the control where the two agree and nothing fires.
- [x] `P2` `testing` `@ai` ~~Kill-switch drill.~~ Opens positions through the book and asserts the venue is flat afterwards — from a clean guard, from an already-halted one, and with the daily order cap exhausted.
- [x] `P2` `feature` `@ai` ~~`GuardedBroker`~~ fills the portfolio's broker seam through the execution guard, so the Book tab cannot become a second unguarded route to a venue. Confirmation defaults to *refuse*; a rejection **raises** rather than returning an error dict, because `Portfolio.enter` ignores that return value and a dict would leave the book holding a position that was never sent.
- [x] `P2` `feature` `@ai` ~~Cost ledger.~~ `sonar/costs.py` derives cost per round trip from the audit log — slippage measured against the decision mark rather than the limit, positive always meaning worse, and a refusal to name a figure below 20 completed round trips.

### The app itself

- [x] `P1` `bug` `@ai` ~~Window opened wider than the screen.~~ SONAR once opened **4,540pt wide** on a 1,280pt display: an unwrapped `QLabel` reports a sizeHint as wide as its text, a layout cannot shrink below its children's minimums, and a `QTabWidget`'s minimum is its widest tab's — so one long prose label silently overrode every `resize()`. Fixed with `label(..., wrap=True)` and `_fit_to_screen()`. Covered by `tests/test_layout.py`, which measures against a 1280×775 baseline rather than whatever screen the runner has.
- [x] `P0` `bug` `@ai` ~~The window never started.~~ `refresh()` still read `Live.scan`, deleted when the Polymarket board went. It threw on every timer tick before drawing anything, so the app sat on "starting…" forever. `tests/test_refresh.py` now builds the real window against a real `Live` and calls the real `refresh()` for every status it can hit — the coverage whose absence let this ship.
- [x] `P1` `bug` `@ai` ~~Close button appeared dead.~~ Leaving macOS full screen re-activates the app when the Space transition finishes, *after* the deferred hide — so the Dock-click handler reopened the window it had just hidden. `reopen_allowed()` ignores an activation within a second of a self-hide.
- [x] `P1` `performance` `@ai` ~~Start-up took ~11s.~~ News and asset fetches now run concurrently, and `warmup()` publishes a snapshot before the heavy screen refresh instead of after. **11s → 1.8s**, first data at 1.7s.
- [x] `P1` `bug` `@ai` ~~SIGABRT on quit.~~ `shutdown()` did not name every QThread the window owns. Qt aborts when a running thread is destroyed, so quitting during a backtest died with SIGABRT. Every thread is now listed, with a test asserting it.
- [x] `P0` `bug` `@ai` ~~Closing SONAR could leave a blank white window that never went away.~~ `_refresh_wire()` fetched on the UI thread whenever the news (8 min TTL) or events cache aged out — a coin flip every eight minutes on whether the event loop blocked up to 30s, painting nothing and ignoring input. The Wire path now reads cache-only (`news.cached()`, `events.cached_payload()`); `tests/test_ui_thread.py` and `test_refresh.py` assert nothing reaches the network from a real window with both caches aged out.

### Data

- [x] `P2` `feature` `@ai` ~~The newswire read one bloc.~~ Ten non-Western sources added, each verified live: Al Jazeera, Anadolu, Global Times, SCMP, TASS, Times of India, The Hindu, Japan Times, AllAfrica, Folha. 24 feeds, nine press blocs, each tagged with origin and whether it is state-directed. `news.bloc_spread()` distinguishes a story carried across five blocs from one outlet repeating itself, and flags state-only coverage — evidence about a government rather than corroboration of an event. Shown in the newswire header.
- [x] `P2` `feature` `@ai` ~~Scheduled institutional events.~~ `sonar/institutions.py` — Fed press, FOMC, Fed speeches, Bank of England. Every source probed before inclusion and the failures recorded rather than dropped silently. The policy filter is load-bearing: most of what the Fed publishes is administrative, and counting it would repeat the volume-is-not-signal mistake. `pressure()` is a variance reading with no direction field, and a test asserts it has none.
- [x] `P2` `feature` `@ai` ~~Where each row could actually be traded.~~ `sonar/venues.py`: **nine of twenty-six rows cannot be bought as shown.** PRIIPs closes SPY/VOO/QQQ to EU retail; Monero was delisted by Binance globally and Kraken across the EEA; currency exchange is not an FX position. Marker and tooltip per row, with the verification date carried.

### Testing the algorithm

- [x] `P1` `feature` `@ai` ~~Lab tab.~~ Replays the plan over real bars with universe, range, horizon and step exposed, reporting the realised hit rate beside what the barrier maths predicted with its 2 s.e. band.
- [x] `P1` `feature` `@ai` ~~Component attribution.~~ Asks of each component the question its weight is a claim about — does ranking on it sort winners from losers? — three ways: IC, quintile spread, and leave-one-out. Verdicts are KEEP / WEAK / DROP / **INVERTED**, p-values through Benjamini-Hochberg together. Catalyst reports *not measured* rather than passing.
- [x] `P1` `feature` `@ai` ~~Replay mode.~~ `sonar/replay.py` grades **you**: one setup at a time on real history with everything after the cursor withheld, no rewind, the model scored on the same setups whether you skip or not, and risk-sized P&L so a coin and a currency pair cost the same to be wrong about.
- [x] `P2` `feature` `@ai` ~~Alerts.~~ Fire on a transition rather than a level, with a cooldown and a silent first scan. They say what changed and never what to do about it — a test asserts no alert can contain buy, short or "immediately".

### Documentation

- [x] `P3` `docs` `@ai` ~~Fold the cost floor into the README.~~ With the measured €1.05 per round trip and the note that the earlier estimate was optimistic.
- [x] `P2` `docs` `@ai` ~~`CONFIDENCE.md`~~ — how the institutional process builds a score versus how this one does: cross-sectional standardisation, benchmark-relative momentum, levels versus surprises, a daily GPR-style political index from the newswire already being read, and the argument that the thing worth forecasting here is volatility rather than direction.
- [x] `P2` `docs` `@ai` ~~In-app docs rewritten for seven tabs~~, adding the Lab, alerts and venue sections. The previous version described five tabs and knew nothing about half the app.

## v3 — only if the research is resumed

- [ ] `P2` `research` `@me` Intraday bars, order flow, or a tone-tagged news archive. Five studies found nothing in daily bars, free news and macro regimes; more features on the same data is not the answer.
- [ ] `P3` `feature` `@ai` Week-over-week deltas on scans, to show which signals are growing rather than merely large

## Explicitly not planned

- [ ] `P0` `security` `@me` **Real-money execution stays off.** SONAR will not place live orders or connect a funded broker. `portfolio.default_broker()` returns Alpaca paper or the internal book — a live venue would have to be constructed explicitly by a caller that means it, never via a fallback chain.
- Revolut integration — investigated and closed. No public retail-investment API; balances would need a licensed Open Banking aggregator.
