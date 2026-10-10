# ◇ SONAR — honest market scanner & paper-trading terminal

Live market data, live prediction-market odds, reputable news, and a probability model —
with **paper money instead of promises**. It began as a recreation of the viral "an AI built
an overnight trading bot" dashboard, with the marketing stripped out and the mechanics laid bare.

> **The viral post is engagement bait.** Its own numbers don't agree ($867 in the headline,
> $847 in the body) and the screenshot shows a $438,012 balance. No overnight bot prints
> money like that. What *is* real and worth building is the machine underneath: a live
> probability model priced against a real market. SONAR builds exactly that — and keeps it
> **paper money** so it can be honest about what it is.

SONAR asserts **no edge**. The score says what is *notable*, never which way a price will go;
the research behind that is in [CONFIDENCE.md](CONFIDENCE.md). Nothing here is financial advice.

## Six words you will meet

The full primer (about 25 terms, no finance background assumed) is **§1 of the Learn tab**
(`static/docs.html#learn`). These six come up on this page first.

| Word | What it means |
|---|---|
| **Paper trading** | Doing everything a trader does with imaginary money, to test an idea without risking anything. Everything in SONAR is paper. |
| **R:R** | Reward divided by risk. A target 15% away with a stop 10% away is 1.5. A bigger number sounds better and is not free: it lowers the hit rate by the same proportion. |
| **P(profit)** | The chance a position reaches its target before its stop. Here it is pinned at the driftless baseline `1/(1+R:R)` until closed positions say otherwise. |
| **Expected value (EV)** | What you would win or lose on average per attempt if you repeated a bet forever. Here it is zero before costs and negative after them. |
| **Calibration** | Whether the numbers mean what they say: of everything called 40% likely, did about 40% happen? |
| **Brier score** | A mark out of one for a set of probability guesses; lower is better. 0 is perfect foresight, 0.25 is a coin flip on everything. |

## What you do first

1. Run it (see **Run it** below). It opens on **My investments**, your paper book — it starts empty.
2. Open the **Screener**, pick one instrument that shows *worth a look*, and press **Buy** or **Short**.
   Paper money only; nothing here can touch a real account.
3. Open the **Learn** tab and read §1 and §10 — what the score claims (notability, never direction)
   and how the app grades itself.
4. Come back in a day. Positions close on their own when they reach their target or stop, and
   **My investments** shows whether the score kept to its odds. Twenty closed positions before it says anything.

## Eight tabs

Six on the main path, then the manual, then two experiments under a **Lab** heading at the foot of the rail
(Practice, with the hourly BTC model, and Sports). A native macOS app — PySide6 widgets, every chart drawn
with `QPainter`, no web view. Each tab carries **two names**: the plain one, and under it in small caps the
one this README and `static/docs.html` use (`ui/tabs.py` paints both).

| Tab | What it does | Asserts a direction? |
|---|---|---|
| **My investments**  <sub>PORTFOLIO</sub> | The page the app opens on: your paper book as a picture — profit or loss now, account value, what is invested, what every stop hitting would cost; **Is the score right?** (the calibration verdict); the account's value over time; a tile and a card per open position | — |
| **Screener**  <sub>ASSETS</sub> | 129 instruments (50 equities, 20 indices, 20 FX pairs, 21 crypto, 18 commodities) with R:R, P(profit), news level, **how old each row's price is**, and buy/short per row | **No** — direction is yours |
| **News**  <sub>WIRE</sub> | Live newswire across nine press blocs, the earnings and IPO calendar, what the news is pointing at, and **alerts** on what changed since the last scan | No |
| **My trades**  <sub>BOOK</sub> | Open paper positions, the calibration table, and the backtest button | — |
| **Big picture**  <sub>MACRO</sub> | Regime: curve, VIX, real rates, unemployment | No |
| **Learn** | The manual and glossary **inside the app** — `static/docs.html` rendered by Qt (`ui/learn.py`), with a contents list and a search box | — |
| **Practice**  <sub>LAB</sub> | Replay the plan over real bars and compare the realised hit rate with the barrier maths; attribute the score component by component; **Replay** real history one setup at a time with the future hidden. At its foot, the **hourly BTC up/down model**, graded against Polymarket every hour | **Yes** — the hourly model is the only independent one |
| **Sports**  <sub>PLAYMAKER</sub> | Prop pricing across **seven sports** (NFL, College Football, NBA, MMA/UFC, International Football, Golf, Cycling): paste books' prices, remove the margin three ways, find which book is out of line with its peers; an LLM read is commentary only | — |

Playmaker is `sonar/playmaker/` (its own nested git repo) plus its tab in `ui/app.py`. A language model's
percentage cannot size a bet there: `staking.Estimate` carries a source with every probability and returns a
zero stake for a narrative one. `sonar/playmaker/MODELS.md` surveys the models; read it before changing the scoring.

## What's real vs simulated

| Real (read-only public data) | Simulated |
|---|---|
| BTC/ETH price + hourly candle — Binance (the actual Polymarket resolution source), Coinbase fallback | The bankroll ($10,000 paper) |
| Polymarket odds, best bid/ask, order books, market metadata | Every position — **no exchange, no wallet, no order placed anywhere** |
| Equities/indices/FX/commodities — Yahoo Finance | The P&L |
| News — 24 feeds across nine press blocs: Reuters, AP, Bloomberg, FT, BBC, MarketWatch, Yahoo, NPR, CNBC, Ars Technica, TechCrunch, The Verge, plus Al Jazeera, Anadolu, Global Times, SCMP, TASS, Times of India, The Hindu, Japan Times, AllAfrica and Folha | |

**No** authentication, **no** write access anywhere, and nothing here can move real money.

The probability model, the asset screener and the paper engine make **zero AI/LLM calls** — that is
all local arithmetic over public data, and it needs no API key. The one exception is the
optional **LLM read** (below), which you invoke by hand on a single opportunity and which
requires an Anthropic key. Leave it off and SONAR runs keyless and free.

## The model

Each hour Polymarket asks: *will the BTC/USDT 1-hour candle close at or above its open?*
Part-way through the hour we know the open `o` and current price `c`; the rest of the hour
is modelled as a driftless random walk with per-hour volatility `σ`. With `τ` the fraction
of the hour remaining:

```
P(up) = Φ( ln(c / o) / (σ · √τ) )
```

- At the top of the hour (`τ=1`, `c=o`) → `0.5`. No information, no edge.
- As the hour runs out (`τ→0`) → collapses to 1 or 0 on the current sign.

Our only disagreement with the market is the volatility estimate: we use **realised** vol
while the market prices its own **implied** vol. That is the realised-vs-implied disagreement
quants trade on — but here it has **not** been shown to be an edge: over the hours scored so far
the model's calibration is no better than the market's (the Terminal's model-vs-market line says
which, live), and after crossing the spread it is frequently negative. The estimate is an EWMA scaled by
an hour-of-day profile; the study behind it is in
[docs/history/hourly-model-notes.md](docs/history/hourly-model-notes.md).

The engine takes at most **one** capped half-Kelly paper position per hour (max 8% of bankroll),
only when the model's probability for the side beats its **executable** price — the ask plus
slippage, not the midpoint — by 4¢ with enough time left, and settles it on the real candle.

It also **scores itself every hour, traded or not**: a mid-hour snapshot of the model's P(up) and the market's
is settled against the real candle and the two are compared by Brier score. The paper P&L only ever grades the
hours the model traded; this grades both forecasters on all 24, and records the book's **bid and ask** so a later
reader can tell whether a difference was ever **buyable**.

The project's recurring lesson, in one line: **one hour must never price another.** An hourly market must end
exactly one hour after its candle opens or the engine refuses the tick; the story is in the notes above.

## Confidence scores, and P(profit)

The Screener ranks by a **confidence score (0–100)**. Read it honestly: it is a heuristic
for how *notable* something looks — **not** the probability you'll make money. That is
`P(profit)`, and it is a separate number. Every row shows its component mix as a bar.
Weights: news `0.35`, momentum `0.30`, catalyst `0.20`, volatility `0.15`. There is **no
directional lean**: the row shows a news *level* (Quiet / Normal / Elevated / Spike) and you pick the side.

News comes from nine press blocs, each feed tagged with its origin and whether it is state-directed
(`news.bloc_spread()`). News is **context, not a predictor**: sentiment is a small word-list heuristic, and
scraped text is **untrusted data** — read and summarised, never acted upon.
[CONFIDENCE.md](CONFIDENCE.md) is the research file on how the score is built and how it could be improved.

Targets and stops are scaled to how much a thing actually moves, so `reward:risk = k_target/k_stop`.
The barrier maths then fixes the hit rate — for a driftless walk, P(reaching the target before the
stop) is `k_stop/(k_target+k_stop)`, so

```
P(profit) = 1 / (1 + R:R)          EV = P·target − (1−P)·stop = 0
```

They are the same number twice. A fatter target buys a proportionally lower hit rate and expected
value multiplies out to **exactly zero**. Only *drift* — a real edge — creates profit, and drift is
only ever supplied by `sonar.calibration` from positions that actually closed. Never assumed.
That zero is **gross**: net of spread, commission and slippage the expectation is `−c` per trade, and
`sonar/costs.py` measures `c` from the execution audit log (€1.05 per round trip, 5.2% of the €20 risked,
in the worked example in [CONFIDENCE.md](CONFIDENCE.md) §13).

## What the research found

Six pre-registered studies, each more careful than the last; the full tables are in
[CONFIDENCE.md](CONFIDENCE.md) §13.

| question | answer |
|---|---|
| Does momentum predict the barrier outcome? | Not detected — flat, worse at extremes |
| Does a news/attention spike? | Not detected — +0.8 pts, ±3.1, over 25,504 setups |
| Does anything sort the cross-section? | Not detected — 0 of 16 survived FDR |
| Does the one surviving lead replicate? | No — one period, wrong asset class, no decay |
| Does anything work conditionally? | Not detected — 0 of 48, floor set by a control |
| Does a scheduled earnings date sharpen the barrier odds? | **Yes** — the first survivor, and a volatility effect, not a direction |

Five directional nulls and one volatility-shaped survivor. These studies can rule out large effects, not small
ones (at this sample an effect of about 3 points on the hit rate, or an IC of 0.04–0.07, would usually go
undetected), and the instruments studied are the ones listed today, which flatters long tests. `P(profit)` stays
pinned at its driftless baseline and nothing here is a reason to trade.

## Paper trading through Alpaca (optional)

The built-in book fills instantly at the quoted price with no fees and no queue, which makes it an optimistic
bound. Alpaca's **paper** environment does better — real symbols, market hours, order handling — with no money
anywhere. Copy `.env.example` to a git-ignored `.env` and fill in the paper keys (they start with `PK`); SONAR
picks them up automatically and falls back to the internal book if they are absent or misconfigured.

The host is a module constant with no parameter to override and a key that is not clearly a paper key is
refused before any request. Going live is not a flag in this file: it is a decision for a human with an account.

## Data providers, and the switch behind each one

Everything runs on Yahoo Finance, which is free, broad and **undocumented**. It can change shape or start
refusing requests without notice, and it already has: the `quoteSummary` endpoint used for earnings dates now
answers 401. One undocumented endpoint carrying the whole app is its largest fragility.

`sonar/providers.py` puts sources behind one interface — a **capability** (quotes, bars, FX, crypto), a **tier**
(keyless or keyed), and a persisted **on/off switch**. A request walks the enabled providers in preference order
and takes the first that answers, so a vendor going down is a skipped provider rather than a broken app.

| provider | tier | serves | note |
|---|---|---|---|
| Yahoo | keyless | quotes, bars, FX, crypto | Broad, free, unstable — the reason this exists |
| CoinGecko | keyless | crypto | Survives a coin being delisted from any one venue |
| Frankfurter | keyless | FX | ECB reference rates; stable, but daily not live |
| Finnhub | free key | quotes, bars | Documented and supported — the sturdiest upgrade |
| Twelve Data | free key | quotes, bars, FX, crypto | Wide coverage, tight request limit |
| Alpha Vantage | free key | quotes, bars | ~25 requests/day; research only |

Keys go in the same git-ignored `.env` as the Alpaca ones (names in `.env.example`). Switch Yahoo off and crypto
still resolves via CoinGecko, FX via Frankfurter — but **equities return nothing at all**: they have no keyless
second source. A free Finnhub key is the fix. **Stooq is deliberately absent**: both its CSV endpoints now return
an HTML bot-block page, which an adapter would have parsed into silence.

### How old is a price on the Screener board?

Visible in the **Updated** column, because a price that is quietly out of date is the failure mode this project
treats as unacceptable. The board does not refetch all 129 instruments at once (that got this machine throttled,
and a throttled scan returns fewer rows rather than an error): `assets.ROLL_BATCH` refetches the **26 stalest**
rows per scan and scores the rest from cache, so one instrument comes round roughly every fifteen minutes. The
column goes gold past 20 minutes and red past an hour, which means the rotation is losing ground rather than
that the price is wrong.

## Plain wording, or expert

The **Wording** button switches between **plain** (the default: "Recent move", "Swing size", "Worth a look") and
**expert** (`MOM`, `VOL`, `R:R · P(PROF)`, `CONF`). It changes the vocabulary and density, never the layout
(`ui/words.py`; rules pinned by `tests/test_plain_language.py` and `tests/test_wording.py`). Design records, including
the Cockpit shell and the portfolio landing page, are in [docs/history/](docs/history/README.md).

## Risk tolerance and horizon

Two knobs, and it matters *where* they apply.

**Risk tolerance** (`--risk conservative|moderate|aggressive`) is about **you**, not the market. It changes
what you **stake** and what you **see**, never what something **scores**:

| | edge threshold | Kelly | max stake | max daily vol |
|---|---|---|---|---|
| conservative | 7¢ | ¼ | 3% | 4% |
| **moderate** (default) | 4¢ | ½ | 8% | none |
| aggressive | 2.5¢ | ¾ | 15% | none |

**Horizon** (`--horizon intraday|week|month`) is about **when**: the hourly engine has no horizon to pick, so it
shapes the asset screener only (momentum window 1d / 5d / 20d, and the exit plan). Both are live-switchable from
`POST /api/config`. Confidence scores are deliberately **not** affected by either.

## The LLM read (optional, off by default)

A second, **separate** track: an on-demand narrative read of one selected opportunity. `model.prob_up()` is a
*calibrated* probability; an LLM's stated conviction is fluent, not calibrated, so the two are never averaged.
Every stated conviction is **logged onto the trade record**, and `engine.llm_calibration()` buckets them and
reports the realised hit rate per bucket, so you can see whether the model's confidence ever tracked reality.
Headlines go to the model as **titles only**, inside a delimited block, marked untrusted.

```bash
pip install anthropic          # only needed for this feature
export ANTHROPIC_API_KEY=...   # or: ant auth login
```

Runs `claude-opus-5` at `medium` effort, on demand for one opportunity — never across the board on every scan.

## Run it

SONAR is a native macOS app — PySide6 widgets, every chart drawn with `QPainter`. There is no
web view, which is why the bundle is ~98MB rather than ~300MB. It needs **Python 3.11 or newer**
and [`uv`](https://docs.astral.sh/uv/) (`brew install uv`); Linux and Windows are untested and
unsupported. Keys, when you want them, go in a `.env` beside `main.py` (copy `.env.example`) — never in the repo.

```bash
uv venv .venv && uv pip install -r requirements.txt
python main.py              # the app
python main.py --selftest   # check a build's wiring and exit
python main.py --headless   # the old HTTP daemon instead
./build_app.sh              # build a signed .app; add --install to copy into /Applications
```

The build script runs `--selftest` **against the frozen binary**, because that is where packaging fails
(writable state lives in `~/Library/Application Support/SONAR/`; lazily-imported modules need a `--hidden-import`).

The frozen app and a source run keep **separate portfolios** by default (`~/Library/Application Support/SONAR/state.json`
versus the checkout's `data/state.json`). `SONAR_DATA` points a source run at another directory — the launchd
agent's plist sets it to the app's, so the agent and the installed app share one book. The active risk profile
is saved with the state; delete the state file to reset to a clean $10,000.

### Tests

```bash
./run-tests.sh tests/ -q          # 1,763 tests, bounded by an external watchdog
QT_QPA_PLATFORM=offscreen ./run-tests.sh -q   # the same suite, offscreen — both must pass
```

Three tests build a real `MainWindow`; `run-tests.sh` keeps an external watchdog as a backstop (`TEST_BUDGET_S`
changes the 300s budget; anything after the script is passed to pytest). `TESTING.md` is the automated side —
what is covered and what is not. **`TESTPLAN.md` is the manual side**: 145 acceptance cases for signing off v2,
run against the installed bundle, shown in the app by the **Test plan** button; the page is generated by
`scripts/build_testplan.py` (edit the markdown, never the HTML).

### Learning what the numbers mean

The **Learn** tab *is* the manual: a plain-English primer with a 25-term glossary (§1), and **§8, the one to read
before trusting a Practice run** — how to read an error bar, what the attribution verdicts mean, and how many
trials a number needs before it means anything (at 20 trials the band is ±21.5 points).

### Uptime

SONAR is a daemon wearing an app: the equity curve only means something if positions settle on the hours they
were priced for. The full notes are in [docs/history/uptime-notes.md](docs/history/uptime-notes.md); in short:

- **The close button hides.** The window disappears, the engine keeps running, and the menu-bar item shows
  bankroll and open position. Quitting is a separate, deliberate menu action, and quitting never waits for the network.
- **Nothing the window waits on may fetch**, and no background thread may hold the shared lock across a network
  call (`tests/test_ui_thread.py` checks it).
- **A launchd agent** keeps it running when you are not logged into the app: `./scripts/install_agent.sh`
  (`--status`, `--uninstall`). It writes `SONAR_DATA` into the plist so the agent and the app share one directory.
- **One engine per state file** (`sonar/enginelock.py`). Whoever starts first drives; the other **follows**,
  mirroring the agent's snapshot over localhost and handing every write to it, and takes over the moment the lock
  is free. The status line says *following the engine at 127.0.0.1:8787* while this is so.
- **The run watches itself.** The hourly model's panel carries the run's vital signs; two silent hours always
  means a stall, and the menu-bar item says so. State files keep a daily rotating backup (last seven days).
- **Protocol mode** (a checkbox on My trades, off by default) opens fixed-small paper positions on the five
  highest- and five lowest-confidence rows once a day, direction by **coin flip**, so the calibration table fills
  without discretion. Turning it off leaves open positions to resolve.

`python main.py --headless` runs the same `sonar.core.Live` behind the stdlib HTTP server and stays dependency-free.

## Execution guard (simulator only)

`sonar/execution.py` is the safety layer that would sit between a signal and a real order: human confirmation,
idempotent order ids, hard caps, a fail-closed allowlist, an audit log, a kill switch that flattens, and venue
reconciliation. It contains **no broker integration**; there is deliberately no live venue wired up. The rules
are listed in [docs/execution-guard.md](docs/execution-guard.md); [GOING_LIVE.md](GOING_LIVE.md) is a plan only.

## What it costs

**Nothing, unless you use the LLM read** (billed per invocation at normal Anthropic API rates, only when you ask).
Every data source is a free keyless public API; the only standing resource is bandwidth, roughly **8 MB/hour
(~190 MB/day)** left running 24/7.

## Which version am I running?

The header shows a number like **`v2.103`** (`v<MAJOR>.<BUILD>`: the `VERSION` file, then `git rev-list --count
HEAD`, so it cannot be forgotten); the window title carries it too. **Hover it** for the commit, date, packaged
build or checkout, and whether a newer build exists. `main.py --selftest` fails if a frozen bundle has no build
stamp. Scheme in `VERSIONING.md`; what each installed build contained is in `CHANGELOG.md`.

## Layout

```
main.py        entry point — app, --selftest, --headless
sonar/         the engine and models (each module's docstring says what it is for)
  core.py engine.py enginelock.py   the driver, the paper engine, the single-writer lock
  model.py feeds.py risk.py horizon.py   the hourly model, its feeds, risk profiles, horizons
  assets.py scoring.py portfolio.py calibration.py   the screener, the plan maths, the book, the grade
  backtest.py replay.py research/    the replay, step-through, and the study apparatus
  news.py events.py institutions.py alerts.py   headlines, calendars, central banks, what changed
  providers.py paths.py server.py llm.py   data sources, path/backup logic, the HTTP server, the optional LLM
  alpaca.py execution.py costs.py universe.py venues.py   dormant real-money code, kept on purpose
  macro/         FRED regime for long horizons — its own git repo, gitignored here
  playmaker/     sports prop pricing, seven sports — its own git repo, gitignored here
ui/              app.py (the window), tabs.py (rail + page header), words.py (plain/expert), learn.py,
                 charts.py, theme.py, worker.py (QThreads), tray.py, icons.py
static/          index.html (BTC terminal), docs.html (the manual), testplan.html (generated)
tests/           the suite (see TESTING.md)      scripts/   build_testplan.py, install_agent.sh, stamp_version.py
packaging/       the launchd plist              docs/      specs, ADRs, audit reports, playbooks, ROADMAP, history
research_results/, docs_attention_study.json     outputs of the studies, kept as their record
```

### API

| | |
|---|---|
| `GET /api/state` | live snapshot: candle, market, signal, portfolio, model-vs-market, run health, calibration |
| `GET /api/assets` | the real-asset screen |
| `GET /api/config` | current risk/horizon/protocol, available options, LLM availability |
| `POST /api/config` | `{"risk": "...", "horizon": "...", "protocol": true}` — switches and rescans |
| `POST /api/read` | `{"kind": "btc\|asset", "id": "..."}` — one LLM read |
| `GET /api/health` | is the engine doing its job — 200, or 503 with the problems listed |
| `GET /api/book`, `/api/wire`, `/api/macro` | the paper book, the alerts and central-bank calendar, the macro regime |
| `POST /api/undo` | `{"id": "...", "kind": "trade\|close"}` — take back a trade or a manual close made in the last 30 s (the window's Undo); it never reaches the graded record |
| `POST /api/trade`, `/api/close` | `{"symbol": "...", "direction": "LONG\|SHORT"}`, `{"id": "..."}` — paper trades; how a second window hands its actions to the engine that holds the book |
| `GET /`, `/docs`, `/testplan` | the BTC terminal page, the manual, the acceptance plan |

Every route answers only requests that name this machine in their `Host` header; writes must be JSON from no foreign `Origin` (see `docs/specs/t0-7-api-origin.md`).

## What is left

The build backlog is finished; what remains is not more code (`TODO.md` has the open items, and
`docs/specs/v1-product.md` defines v1.0 as 30 clean days).

- **A free Finnhub key.** Equities have no keyless second source, so most of the watchlist rides on one
  undocumented Yahoo endpoint. This is the single highest-value change.
- **Let the paper book run.** A real track record is the one thing no backtest substitutes for, and the
  calibration table stays empty until ~20 positions have closed. **Protocol mode** (My trades) fills it.
- **Better data, if the research is ever resumed.** Five studies detected no directional effect in daily bars,
  free news and macro regimes (large effects ruled out, small ones not). Anything further needs intraday bars,
  order flow, or a news archive with tone, all of which cost money.

**Not planned: real-money execution.** SONAR will not place live orders, connect a funded broker, or move real
money. **Investigated and closed: Revolut** — no public retail-investment API; reopen only as a deliberate project.

## Not advice

This is a demonstration of a probability model and a set of transparent heuristics against live
markets. It is **not** financial advice, and paper P&L predicts nothing about real results — an
earlier run showed **+114% on a 44% win rate**, carried entirely by three longshot wins. That is
variance wearing a costume, and it is exactly why this stays on paper. Going live with real funds
would be an entirely separate decision, with real risk, real fees, and no guarantees.
