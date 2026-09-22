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
- [x] `P2` `testing` `@ai` ~~Split parse from fetch in `feeds.py`.~~ 30% → 82%,
      69 tests, none touching the network. Made a one-character lookahead bug in
      the warm-up (`closes[:i]` → `closes[:i + 1]`) into something a test fails
      on. `universe.py` (17%) still wants the same treatment.
- [x] `P2` `testing` `@ai` ~~`server.py` had never been run by a test.~~ 0% →
      92%, against a real server on an ephemeral port. `conftest.py` grew a
      `loopback` fixture so this did not mean weakening the suite's ban on
      sockets.
- [ ] `P2` `testing` `@ai` **`universe.py` is 17%** — `canonical_title`,
      `wiki_article`, `article_map` and the cache are pure string handling with
      no excuse for being untested. `TESTING.md` §2.
- [ ] `P3` `testing` `@ai` **`charts.py` (22%) and `tray.py` (0%)** — the
      painters take a series and produce geometry, and `update_state` is
      formatting over a snapshot dict. Both checkable without a screen.
- [ ] `P2` `testing` `@ai` **`research/features.py` is 31%** and every study's
      conclusion rests on it. A wrong feature invalidates findings rather than
      crashing — the worst kind of bug to leave untested.
### Approachability — the app is unreadable without a finance background

The user who commissioned this cannot read his own screener, and that is a
product defect rather than a gap in his education. The prose to fix it already
exists and is good (`static/docs.html` §1 and §8); what was missing was it being
*where the confusion is*. Ordered by value per unit of work — 1.x first, because
explaining a number in place is worth more than any amount of new prose.

- [x] `P1` `design` `@ai` ~~The manual opened a **web browser**.~~ It is now the
      **Learn** tab: `static/docs.html` translated into Qt rich text by
      `ui/learn.py`, contents on the left, a search box that takes one
      unfamiliar word. Same file the browser serves, so the prose cannot drift.
- [x] `P2` `design` `@ai` ~~A stale price looked identical to a live one.~~
      **AGE** column on every Assets row, counting between scans rather than
      freezing at what the scan measured.
- [x] `P1` `design` `@ai` ~~The GUI itself — font, contrast, dropdowns.~~
      **The Plain Language direction**, picked from three mockups. `ui/theme.py`
      is rewritten: proportional type for words, the same face with tabular
      numerals for figures, real monospace only where a pasted table's columns
      are made of spaces; `MUTED` and `FAINT` both clear 4.5:1 (`FAINT` was
      1.9:1); the toolbar's two knobs are 38px and captioned with the question
      they answer. `ui/tabs.py` paints both names on every tab — the plain one
      over the one the manual uses — because Qt draws a `\n` in a tab label on
      one line and clips it.
- [x] `P1` `design` `@ai` ~~Every heading needs a link to the paragraph that
      explains it.~~ Headings that name something non-obvious carry a docs
      anchor, open the Learn tab there, and `tests/test_plain_language.py`
      asserts every anchor resolves to a section that exists.
- [x] `P1` `design` `@ai` ~~Plain-English headings instead of abbreviations.~~
      `MOM` → "Recent move" over *over 5 days*, `VOL` → "Swing size" over *big
      swings*, `R:R` and `P(PROF)` merged into "If you traded it" reading "win
      1.5× the risk / 40% of the time", `CONF` → "Worth a look" with the score
      as a meter whose segments are still the component breakdown.
- [x] `P1` `design` `@ai` ~~One plain sentence per row.~~ "up hard, heavy news",
      generated from numbers already on the row. A test asserts it can never
      acquire a direction — that sentence is the easiest place in the app to
      break the rule the whole project rests on.
- [ ] `P2` `design` `@ai` **The other six tabs are still written in jargon.**
      The Screener is done and the shared stat strips got English captions via
      `STAT_WORDS`, but the Practice tab still asks for `STEP (BARS)`, and the
      Sports tab is a wall of devigging vocabulary. Same treatment, tab by tab.
- [ ] `P1` `feature` `@ai` **The Lab is the least readable tab in the app** and
      it is the one that decides whether anything here is true. Three parts:
      a guided mode whose controls are questions rather than `STEP (BARS)`;
      a verdict in words above the table ("did not beat chance: 41% against a
      40% baseline, error bar ±3 — that is noise"), generated from numbers the
      run already produces; and the three tests that decide whether a result
      means anything (error bar, out-of-sample, multiple testing) stated inline
      with a link to §8 rather than assumed.
- [ ] `P2` `feature` `@ai` **Nothing greets a first launch.** Five cards on
      first run — it is paper money; a high score means *notable*, never *going
      up*; start on Assets; check any claim in the Lab; the manual is the Learn
      tab — reopenable from Learn, with the "seen" flag in
      `paths.user_data_base()`.
- [ ] `P2` `design` `@ai` **"unproven" reads as broken rather than honest.**
      Everywhere the app refuses to claim something, say what would change it
      and how far along it is: "unproven — needs ~20 closed positions, you have
      3". The Book tab has the count already.
- [x] `P2` `design` `@me` ~~Decide the vocabulary question.~~ **Both.** The
      `Wording` button switches plain ↔ expert; `ui/words.py` remembers it.
      The worry that it would be built and never used was answered by what it
      costs: the headings and the tab bar already carried both names, so the
      switch is a re-caption rather than a second interface. It changes the
      vocabulary and the row density, never the layout — `tests/test_wording.py`
      asserts the columns are identical in both.

---

- [ ] `P2` `feature` `@ai` **The Lab tab cannot test the Playmaker models.**
      It measures the markets algorithm only — the Elo/Dixon-Coles scoring runs
      from a script, not the UI, so there is no way to re-run it after a change
      from inside the app. Everything it needs exists in
      `playmaker/scoring.py`.

---

## v2 — current

The arc. Its precise build number is derived, not written here — `v2.100` today
— so this heading names the phase and `sonar/version.py` names the build; see
`VERSIONING.md` for the scheme and `CHANGELOG.md` for what each installed build
contained. Everything below landed. What remains open in v2 is two items that
need an account and time rather than code, kept at the top.

- [ ] `P0` `infra` `@me` **Get a free Finnhub API key.** Equities have no keyless second source, so most of the watchlist rides on one undocumented Yahoo endpoint. No code needed — `providers.py` already registers Finnhub at preference 5, ahead of Yahoo, and picks the key up from `FINNHUB_API_KEY` in a git-ignored `.env`. Also removes the ~15-minute quote delay during market hours.
- [ ] `P1` `research` `@me` **Let the paper book run.** The calibration table stays empty until ~20 positions have closed. No amount of backtesting substitutes for a track record. **Protocol mode** (Book tab, off by default) now fills it systematically — coin-flip direction, fixed small stakes — so the remaining decision is only to switch it on and leave the app running.

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
- [x] `P0` `bug` `@ai` ~~SONAR aborted when its menu bar menu opened on macOS 27.~~ `-[NSEvent clickCount]` raises there for an event that has no click count, and Qt's cocoa plugin asks for it whenever a menu begins tracking; the Objective-C exception unwinds through C++ frames that catch nothing, into `terminate()`. Reproduced directly before fixing — a bare `NSEvent` asked for `clickCount` aborts the interpreter with `NSInternalInconsistencyException`, the same stack as `SONAR-2026-09-22-180253.ips` and as Lab Hub's. PySide6 6.11.2 is the newest release, so there was nothing to upgrade to. `ui/appkit_guard.py` is Lab Hub's guard, ported: it swizzles that one selector to answer 0 for the event types with no click count and call through for the ten that have one, installed in `main.py` before `QApplication`. `--selftest` now **fails** without it, `tests/test_appkit_guard.py` runs against the real Objective-C runtime, and a mutation that skips the swizzle aborts the test process rather than passing. This matters more here than elsewhere: the close button hides to the menu bar, so that menu is the way back into the app. **Delete both copies once Qt ships a fixed cocoa plugin.**
- [x] `P1` `feature` `@ai` ~~The app could not say which version it was.~~ `v<MAJOR>.<BUILD>` — MAJOR hand-edited in `VERSION`, BUILD derived from `git rev-list --count HEAD` and zero-padded, which is the lab-wide scheme `imprint` and `sentinel_fork` already use and the one the Lab Project Monitor derives, so the dashboard and the app read from the same two inputs and cannot disagree. Shown beside the wordmark, in the window title (bug reports arrive as screenshots), in the menu-bar menu, in `Info.plist`, and in `--selftest`, which now **fails** for a frozen bundle with no build stamp. Hovering reports commit, date, packaged-vs-checkout, and how far behind the checkout it is — and says it cannot know rather than claiming "up to date" when there is nothing to compare against. Frozen builds carry `_build_info.json` from `scripts/stamp_version.py`. Scheme in `VERSIONING.md`, history in `CHANGELOG.md`. This answers the failure that prompted it: a rebuild lands, the app is opened, the new work is not there, and nothing on screen explains that the bundle is older than the conversation.
- [x] `P0` `bug` `@ai` ~~"SONAR doesn't quit" — the blank white window, fourth report and the actual cause.~~ `shutdown()`'s last resort for a thread that would not stop was `QThread.terminate()`. It kills the thread wherever it stands, and a thread running Python holds the **GIL**, which is then never returned — so every Python thread blocks in `take_gil` forever, the Qt event loop included. Nothing repaints, and macOS shows the window's empty backing store: a white rectangle in an app themed `#080b11`, ignoring every click. Not a rare race — `live.stop()` only lands between fetches, so any quit during an in-flight request had to outlast an 8–30s socket timeout inside the grace, then terminated a thread that was by construction mid-`read()`. The fix is to stop trying to stop it and leave by `os._exit` instead, which skips the QThread destructors whose `qFatal()` was the only reason terminate was wanted; the engine writes through on every change and the engine lock is a PID file the next launch reclaims, so nothing is lost. The per-thread 4s wait also became a 1.5s budget **shared across all six threads** — six waits on the UI thread was up to 24s of the same unpainted window, self-healing but identical to look at. `tests/test_shutdown.py` fails the build on any `.terminate()` call by AST, and quits a real subprocess mid-fetch — against the old code that test does not fail, it hangs.
- [x] `P0` `bug` `@ai` ~~Closing SONAR could leave a blank white window that never went away.~~ `_refresh_wire()` fetched on the UI thread whenever the news (8 min TTL) or events cache aged out — a coin flip every eight minutes on whether the event loop blocked up to 30s, painting nothing and ignoring input. The Wire path now reads cache-only (`news.cached()`, `events.cached_payload()`); `tests/test_ui_thread.py` and `test_refresh.py` assert nothing reaches the network from a real window with both caches aged out.

### Caught by the instrumentation on night one — 2026-09-22

- [x] `P1` `bug` `@ai` **The score log booked comparisons against expired
      markets.** When the hour's slug lookup fails, `feeds.current_market()`'s
      series fallback can return the *previous* market — still open pending
      resolution, priced ~0 or ~1, end time in the past — which clamps τ to
      exactly 0.0 and, at the top of an hour, pairs a model reading of exactly
      0.5 with a market reading of ~certainty. Three such rows landed in the
      first night of the first live run and were identifiable by τ=0.0.
      Fixed twice over: `current_market()` returns None for a market whose end
      has passed (the same rule as a stale candle), and `_maybe_score()`
      requires τ strictly inside (0, 0.5] — a bound that *is* the alignment
      check, since an hourly market ending within the next half hour can only
      be the candle's own. The three rows were scrubbed from the live log with
      the agent stopped, and `n_scored_total` decremented to match. Trading
      was never exposed: `enter_tau_min` already blocked τ=0 entries.

### Pre-run instrumentation — 2026-09-20, before the collection run starts

- [x] `P2` `docs` `@ai` **Docs and learning centre brought up to the app that
      exists.** §1 gained "How you will know whether any of it works" (the
      three self-grading loops, in plain English) and a 25th glossary term
      (Bid / ask — the spread, and why right-but-unbuyable exists); §8 gained
      "Reading the model-vs-market line" and the overlap-corrected error-bar
      lesson; §10 describes the rank-IC verdict, the live-only stats and
      protocol mode; §13 gained the void-never-guess bullet. Stale facts
      corrected everywhere they lived: the watchlist is 129, not 26 (docs ×3,
      README, TESTPLAN §3); the venue census is 58-proxied/1-untradeable of
      129, not nine of twenty-six (docs §9, AGENTS.md); the suite is 1,253,
      not 1,073 (TESTPLAN ×3, TESTING, README); the window-test wedge is fixed,
      not "known" (TESTPLAN §12, TESTING §7, README). TESTPLAN grew cases
      2.8–2.9 (model-vs-market + health line), 5.19–5.23 (protocol mode) and
      10.6–10.8 (STALLED, recovery, backups) — 101 cases, 17 ⚠ regressions.

- [x] `P1` `feature` `@ai` **The hourly snapshot records the touch.** Brier
      says who was better *calibrated*; only the bid/ask at the moment of the
      snapshot can later say whether the difference was ever **buyable** — and
      it cannot be backfilled, so it rides on every score-log row from day
      one.
- [x] `P1` `feature` `@ai` **Run health.** Hours scored vs elapsed, voided
      settlements (previously traceless by design), and time since anything
      last settled — on the Terminal tab and in `/api/state`
      (`Engine.run_health`). BTC settles around the clock, so **two silent
      hours always means a stall**: the menu-bar item posts a notification and
      shows STALLED instead of letting a dead run look healthy.
- [x] `P1` `infra` `@ai` **Daily state-file backups.** `state.json` and
      `portfolio.json` are the experiment's only output and live outside git;
      `paths.daily_backup` keeps the last seven days beside each file, one
      known-good copy per day, taken before the day's first overwrite.
- [x] `P2` `feature` `@ai` **Protocol mode** (Book tab checkbox, off by
      default, persisted): once a day, fixed-small paper entries on the five
      highest- and five lowest-confidence rows, direction by **coin flip** —
      random on purpose, since the score claims notability and never
      direction. Fills the calibration table with measurement instead of
      discretion; capped at 40 open; toggling off leaves positions to resolve.
      Also settable via `POST /api/config {"protocol": true}`.

### The 2026-09-19 review — every finding fixed the same day

- [x] `P0` `bug` `@ai` ~~Settlement after a feed gap used the wrong close.~~
      `tick()` settled a rollover against the new candle's open, which is only
      the previous hour's close on a *contiguous* feed — after a sleep or
      restart it is a price from hours after the position's market resolved,
      so a losing hour could book as a win, corrupting the record the app
      exists to collect. The engine now fetches the hour's own close
      (`feeds.hour_close`, outside the poll lock) and **voids** the position
      when it cannot be recovered. Tests cover contiguous (lookup must not be
      consulted), gap-with-lookup and gap-void.
- [x] `P1` `bug` `@ai` ~~The fair-odds warm-up rows counted in the live stats.~~
      `stats()` mixed the ~36 seeded synthetic trades into the win rate and
      P&L, so a fresh install showed a record built from trades nobody took.
      `Trade.kind` separates them (old state files migrate on the seeded
      title); the header shows live trades only.
- [x] `P1` `bug` `@ai` ~~The edge gate read the midpoint but paid the ask.~~
      A 4¢ midpoint edge across a 10¢ spread passed the threshold and entered
      with a negative executable edge, sized small, every time the book was
      wide late in the hour. The gate is now on `model_side_prob − price`.
- [x] `P1` `research` `@ai` ~~The model was only ever scored on hours it
      traded.~~ Selection-biased and slow: a few bankroll-noisy observations a
      day, all from the model's boldest claims. The engine now snapshots
      model-vs-market mid-hour for **every** hour, settles both against the
      real candle, and compares Brier scores (`Engine.model_vs_market`,
      Terminal tab) — the direct test of the realised-vs-implied thesis, at 24
      observations a day.
- [x] `P1` `research` `@ai` ~~The Terminal's σ contradicted the project's own
      volatility research.~~ The screener got GARCH in Sep 2026; the hourly
      model — the only place a probability is asserted — kept a flat 72-hour
      std. `sonar/research/hourlyvol.py` ran the pre-registered study: over
      16,078 held-out hours, EWMA × hour-of-day profile beat trailing-72 by
      **+7.5% QLIKE, 6/6 blocks** (clustering +3.9% and seasonality +3.5% are
      additive). GARCH also won but was passed over — its 720-hour anchor is
      partly a sample-size win, the artefact the daily study's control caught;
      the synthetic controls (constant vol, planted seasonality, planted
      regimes) run in the suite on every build. Wired as `core.Live._sigma`
      with the measured fallback ladder.
- [x] `P2` `bug` `@ai` ~~Backtest error bars assumed independent trials.~~ At
      a step shorter than the holding time neighbouring setups share deciding
      bars; `summarise()` now takes the wider of the binomial and Newey-West
      bars. README's "independent setups" claim corrected — the null survives,
      since overlap only widens bars.
- [x] `P2` `bug` `@ai` ~~The calibration verdict demanded strict bucket
      monotonicity~~, which one noisy bucket always breaks even under a real
      gradient. Replaced with a per-position rank IC (`score_ic`) with a
      2-sigma bar.
- [x] `P2` `bug` `@ai` ~~`observed_draw_rate` claimed "measured" and always
      returned the default~~ — nothing ever set the attribute it read. The Elo
      table now counts draws as it fits; the default stands in below 50 games.
- [x] `P3` `bug` `@ai` ~~Playmaker accuracy counted every draw as a hit~~,
      flattering draw-heavy leagues for free. Draws now stay out of the
      accuracy denominator (Brier/log-loss, which drive verdicts, already
      scored them properly).
- [x] `P2` `bug` `@ai` ~~`run-tests.sh` blocked piped invocations for the full
      300s budget~~ — killing the watchdog subshell orphaned its `sleep`,
      which held stdout open after a 10-second suite had finished. The trap
      now reaps the sleep; wall time 300s → 10s.
- [x] `P2` `infra` `@ai` ~~No CI.~~ `.github/workflows/tests.yml` runs the
      suite on every push (`QT_QPA_PLATFORM=offscreen` + Qt runtime libs). The
      recorded blocker — window tests wedging ~1 in 3 — was fixed 2026-09-19,
      so the drills stop depending on someone remembering. Unverified until
      the next push reaches GitHub.
- [x] `P3` `bug` `@ai` ~~Dead code in `volatility.study()`~~ — an unused
      `by_symbol` block whose zip misaligned whenever an instrument was
      skipped. Deleted.

### The score itself — Sep 2026

- [x] `P1` `research` `@ai` ~~Volatility forecast instead of trailing realised vol.~~
      `sonar/volatility.py`. GARCH below ten days (+11.6% at 3d, +17.8% at 5d on
      QLIKE), a 250-day trailing window above it (+5.6% at 20d). The first
      answer — +24.5% on 26/26 instruments and 6/6 blocks — was an artefact of
      sample size, and a synthetic control with constant volatility is what
      caught it. Both are in `CONFIDENCE.md` §8.
- [x] `P1` `data` `@ai` ~~Grow the watchlist.~~ 26 → 129, every class ≥18, every
      symbol verified to return a year of closes first. Forced a rolling refresh:
      refetching all of them took the request rate from ~13/min to ~64 and the
      source throttles silently below that, returning fewer rows rather than an
      error.
- [x] `P1` `research` `@ai` ~~Cross-sectional z-scoring within asset class.~~
      `sonar/crosssection.py`. The volatility component had a median of 1.00 in
      Crypto and 0.14 in Forex — it was measuring asset class, not volatility.
      Class median CONF spread 18 → 8.6 points. Standardises the *raw* quantity;
      standardising the clipped component is a silent no-op.
- [x] `P2` `docs` `@ai` ~~A learning centre.~~ `static/docs.html` §1 is a
      plain-English primer with a 24-term glossary; §8 teaches how to read a Lab
      result — error bars, attribution verdicts, how much data a number needs,
      and five ways to fool yourself that each happened in this project.

### Data

- [x] `P2` `feature` `@ai` ~~The newswire read one bloc.~~ Ten non-Western sources added, each verified live: Al Jazeera, Anadolu, Global Times, SCMP, TASS, Times of India, The Hindu, Japan Times, AllAfrica, Folha. 24 feeds, nine press blocs, each tagged with origin and whether it is state-directed. `news.bloc_spread()` distinguishes a story carried across five blocs from one outlet repeating itself, and flags state-only coverage — evidence about a government rather than corroboration of an event. Shown in the newswire header.
- [x] `P2` `feature` `@ai` ~~Scheduled institutional events.~~ `sonar/institutions.py` — Fed press, FOMC, Fed speeches, Bank of England. Every source probed before inclusion and the failures recorded rather than dropped silently. The policy filter is load-bearing: most of what the Fed publishes is administrative, and counting it would repeat the volume-is-not-signal mistake. `pressure()` is a variance reading with no direction field, and a test asserts it has none.
- [x] `P2` `feature` `@ai` ~~Where each row could actually be traded.~~ `sonar/venues.py`: **nine of twenty-six rows cannot be bought as shown.** PRIIPs closes SPY/VOO/QQQ to EU retail; Monero was delisted by Binance globally and Kraken across the EEA; currency exchange is not an FX position. Marker and tooltip per row, with the verification date carried.

### Testing the algorithm

- [x] `P1` `feature` `@ai` ~~Lab tab.~~ Replays the plan over real bars with universe, range, horizon and step exposed, reporting the realised hit rate beside what the barrier maths predicted with its 2 s.e. band.
- [x] `P1` `feature` `@ai` ~~Component attribution.~~ Asks of each component the question its weight is a claim about — does ranking on it sort winners from losers? — three ways: IC, quintile spread, and leave-one-out. Verdicts are KEEP / WEAK / DROP / **INVERTED**, p-values through Benjamini-Hochberg together. Catalyst reports *not measured* rather than passing.
- [x] `P1` `feature` `@ai` ~~Replay mode.~~ `sonar/replay.py` grades **you**: one setup at a time on real history with everything after the cursor withheld, no rewind, the model scored on the same setups whether you skip or not, and risk-sized P&L so a coin and a currency pair cost the same to be wrong about.
- [x] `P2` `bug` `@ai` ~~The window tests wedged about one run in three.~~ Same root cause as the blank window, and the reason it resisted a long search: the conftest guards were `autouse=True` at **function** scope, but pytest builds fixtures highest-scope-first, so for the three tests that take a **module**-scoped `window` fixture none of them was in force when the window was built. "The poll thread (no-op'd, still hangs)" had been ruled out against a patch that was not yet applied. Those tests were starting the real `Live.run()`, taking the engine lock in the user's real application directory and going to the network; the thread never finished, so the fixture's teardown reached `terminate()`. The guards are session-scoped now, with the function-scoped ones kept for per-test `tmp_path` and for naming the test in the network error. Three consecutive full runs: 1,182 passed in 9.3s, deterministic.
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
