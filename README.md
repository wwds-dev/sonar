# ◇ SONAR — honest market scanner & paper-trading terminal

Live market data, live prediction-market odds, reputable news, and a probability model —
with **paper money instead of promises**. It began as a recreation of the viral "an AI built
an overnight trading bot" dashboard, with the marketing stripped out and the mechanics laid bare.

> **The viral post is engagement bait.** Its own numbers don't agree ($867 in the headline,
> $847 in the body) and the screenshot shows a $438,012 balance. No overnight bot prints
> money like that. What *is* real and worth building is the machine underneath: a live
> probability model priced against a real market. SONAR builds exactly that — and keeps it
> **paper money** so it can be honest about what it is.

## Five tabs

A native macOS app — PySide6 widgets, every chart drawn with `QPainter`, no web view.

| Tab | What it does | Asserts a direction? |
|---|---|---|
| **Terminal** | Hourly BTC up/down paper trade — the model prices each hour, compares to Polymarket, takes at most one simulated bet | **Yes** — the only independent model |
| **Assets** | 26 instruments (equities, indices, FX, 11 crypto, commodities) with R:R, P(profit), news level, and buy/short per row | **No** — direction is yours |
| **Wire** | Live newswire, the earnings and IPO calendar, and what the news is pointing at | No |
| **Book** | Open paper positions, the calibration table, and the backtest button | — |
| **Macro** | Regime: curve, VIX, real rates, unemployment | No |

A Polymarket board used to sit here and was removed — mirroring a market's own odds back at
you is not analysis, and dropping it also removed ~52MB/hour of downloads. Full docs live in
the app behind the **Docs** button, plus a tooltips toggle explaining every number on hover.

## What's real vs simulated

| Real (read-only public data) | Simulated |
|---|---|
| BTC/ETH price + hourly candle — Binance (the actual Polymarket resolution source), Coinbase fallback | The bankroll ($10,000 paper) |
| Polymarket odds, best bid/ask, order books, market metadata | Every position — **no exchange, no wallet, no order placed anywhere** |
| Equities/indices/FX/commodities — Yahoo Finance | The P&L |
| News — Reuters, AP, Bloomberg, FT, BBC, MarketWatch, Yahoo, NPR, CNBC, Ars Technica, TechCrunch, The Verge | |

**No** authentication, **no** write access anywhere, and nothing here can move real money.

The probability model, the asset screener and the paper engine make **zero AI/LLM calls** — that is
all local arithmetic over public data, and it needs no API key. The one exception is the
optional **LLM read** (below), which you invoke by hand on a single opportunity and which
requires an Anthropic key. Leave it off and SONAR runs exactly as it always did: keyless,
dependency-free, and free.

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
(std of recent hourly returns) while the market prices its own **implied** vol. When they
differ we get a thin, statistical edge — the realised-vs-implied trade quants actually run.
It is small and frequently negative after crossing the spread.

The engine takes at most **one** capped half-Kelly paper position per hour (max 8% of bankroll),
only when `|model − market|` clears 4¢ with enough time left, and settles it on the real candle.

The equity curve is seeded with a **fair-odds backtest** over the last 36 real hours
(expected value ≈ 0 by construction — it illustrates variance, not profit), then extends
with live paper trades marked by a gold "LIVE" divider.

## Confidence scores

The Assets screen ranks by a **confidence score (0–100)**. Read it honestly: it is a heuristic
for how *notable* something looks — **not** the probability you'll make money. That is
`P(profit)`, and it is a separate number. Every row shows its component mix as a bar.

Weights: news `0.35`, momentum `0.30`, catalyst `0.20`, volatility `0.15`. There is **no
directional lean** — the research below found momentum carried none, so the row shows a news
*level* (Quiet / Normal / Elevated / Spike) and you pick the side with buy or short.

News is **context, not a predictor**. Sentiment is a small word-list heuristic, matching is
deliberately conservative, and scraped text is treated as **untrusted data** — read and
summarised, never acted upon.

## Risk, reward, and the probability of profit

Targets and stops are scaled to how much a thing actually moves, so `reward:risk = k_target/k_stop`.
The barrier maths then fixes the hit rate — for a driftless walk, P(reaching the target before the
stop) is `k_stop/(k_target+k_stop)`, so

```
P(profit) = 1 / (1 + R:R)          EV = P·target − (1−P)·stop = 0
```

They are the same number twice. A fatter target buys a proportionally lower hit rate and expected
value multiplies out to **exactly zero**. Only *drift* — a real edge — creates profit, and drift is
only ever supplied by `sonar.calibration` from positions that actually closed. Never assumed.

## What the backtest found

`sonar.backtest` replays the same plan over years of real bars: momentum and volatility from prior
bars only, then walk forward through actual highs and lows. A bar spanning both barriers scores as a
**loss** (daily data cannot order them) and costs are excluded, so reality is worse than this.

Over **25,504 independent setups** — non-overlapping windows, 5 years, 113 instruments:

| momentum bucket | hit rate | | attention | hit rate | vs baseline | ±2 s.e. |
|---|---|---|---|---|---|---|
| 0–2% | 39.5% | | below normal | 38.7% | −1.3 | 1.2 |
| 2–5% | 39.7% | | normal | 39.0% | −1.0 | 1.1 |
| 5–10% | 39.8% | | elevated | 40.8% | +0.8 | 2.0 |
| 10%+ | 38.7% | | **spike** | **40.8%** | **+0.8** | 3.1 |

Baseline is 40.0%. **Neither momentum nor news carries a usable edge.** Overall hit rate is 39.58%
against a 39.99% prediction — the barrier maths is right, and nothing in the score beats it.

An earlier run on 26 instruments put a news spike at **+4.9 points** and this README said so. It did
not survive: at 3.7× the sample the effect fell to **+0.8**, well inside its own error bar. That was
small-sample noise, and the honest thing is to record that it was reported and then withdrawn rather
than quietly delete it.

Two things follow. The Bullish/Bearish lean stays deleted — momentum never justified it. And
`P(profit)` stays pinned at its driftless `1/(1+R:R)` baseline, because no measured drift exists to
move it. The confidence score remains what it always claimed to be: a **notability** heuristic for
what is worth a human look, explicitly *not* a profit predictor.

What is still untested: SONAR's own word-list **sentiment**. Wikipedia pageviews measure attention
volume, not tone, so the direction half of the news idea has never been put on trial.

## Chasing the one lead, and killing it

The study above left a single candidate: `dist_52w_high` — proximity to the
52-week high — at t = +3.39 in the holdout. `sonar/research/validate.py` puts a
lead through three tests a real effect should pass and a lucky one should not.

**1. Consistency across non-overlapping periods.** Six blocks, five years:

| period | IC | t |
|---|---|---|
| 2022-04 → 2023-01 | +0.045 | +0.61 |
| 2023-01 → 2023-09 | −0.033 | −0.67 |
| 2023-09 → 2024-05 | +0.036 | +0.84 |
| 2024-05 → 2025-01 | +0.028 | +0.65 |
| 2025-01 → 2025-10 | +0.015 | +0.44 |
| **2025-10 → 2026-06** | **+0.136** | **+3.90** |

The entire effect lives in the final block — which *is* the earlier study's
holdout window. That is the whole explanation of the +3.39, and the reason a
single holdout cannot be trusted no matter how it is embargoed.

**2. Decay across horizons.** A signal being used up fades smoothly. This one
goes +0.026 (5d), +0.028 (10d), +0.037 (20d), +0.034 (60d) — it *rises* to the
horizon it was discovered at and falls after. That is the shape of noise found
by looking.

**3. Where it appears.** The 52-week-high anomaly is an *equity* effect with a
behavioural story about anchoring on a salient price. Measured by class:

| class | IC | t |
|---|---|---|
| Crypto | +0.087 | +2.84 |
| Equity | +0.002 | +0.09 |

It is absent exactly where the theory says it should be strongest, and present
only where the theory does not apply. The mechanism is not the stated one.

**The comparison that settles it.** Every candidate was run against the same
tests as the controls, and they are indistinguishable:

| feature | blocks agreeing | sign-test p | beats noise floor |
|---|---|---|---|
| dist_52w_high | 5/6 | 0.219 | 1/6 |
| attention_z | 4/6 | 0.688 | 0/6 |
| reversal_1 | 4/6 | 0.688 | 0/6 |
| mom_250_ex1m | 4/6 | 0.688 | 1/6 |
| *random_control* | *4/6* | *0.688* | — |
| *price_level* | *3/6* | *1.000* | — |

A seeded random number scores 4/6. So does attention. So does reversal. The
lead is dead, and nothing else in the registry is alive.


## Do any of them work *sometimes*?

The last idea worth testing. Unconditional effects are rare in the literature;
what it usually reports is effects that switch on in particular states — momentum
working in calm markets, the low-volatility anomaly strongest when rates fall. So
`sonar/research/regimes.py` splits every date by VIX (against its own trailing
median), by whether the 10y–2y curve is inverted, and by the direction of policy
rates, all classified **point-in-time**, and re-runs every feature inside each
state.

48 feature-by-regime tests. **Zero survivors.** The strongest:

| interaction | IC (state A) | IC (state B) | difference | t |
|---|---|---|---|---|
| attention_trend × VIX | −0.009 | +0.019 | −0.028 | −1.81 |
| mom_20 × VIX | +0.042 | −0.002 | +0.043 | +1.71 |
| attention_z × VIX | −0.007 | +0.021 | −0.029 | −1.61 |

And the noise floor, from the controls put through identical conditioning:
`price_level × curve` reached **t = +1.72**. The best real interaction is
1.81. A feature that cannot predict anything scored 1.72 by being sliced the
same way.

Conditioning doubles the hypothesis count, which is exactly how "it only works
when X" results get published and then fail. Here it produced nothing that a
control could not match.

## Where the research ended up

Five studies, each more careful than the last:

| question | answer |
|---|---|
| Does momentum predict the barrier outcome? | No — flat, worse at extremes |
| Does a news/attention spike? | No — +0.8 pts, ±3.1, over 25,504 setups |
| Does anything sort the cross-section? | No — 0 of 16 survived FDR |
| Does the one surviving lead replicate? | No — one period, wrong asset class, no decay |
| Does anything work conditionally? | No — 0 of 48, floor set by a control |

That is a complete negative result over this feature space, and it is the
expected one: these are liquid instruments priced by people running the same
arithmetic. The value built here is not a signal but an apparatus that can tell
the difference — one that has now caught itself three times (a +4.9 attention
claim, a Thursday effect, and a t = +3.39 holdout), each time because a control
was run under identical conditions rather than compared to a textbook threshold.

**What this means for the app.** SONAR stays what it is: an honest notability
screener with real paper trading. `P(profit)` stays pinned at its driftless
`1/(1+R:R)` baseline, because five studies have failed to find the drift that
would move it. Nothing here is a reason to trade.


## Paper trading through Alpaca (optional)

The built-in book fills instantly at the quoted price with no fees and no queue,
which makes it an optimistic bound rather than a simulation. Alpaca's **paper**
environment is the cheap way to do better: real symbols, real market hours, real
order handling, orders that sit unfilled when the market is shut — and no money
anywhere.

```bash
# a free Alpaca PAPER account, then in a git-ignored .env:
APCA_API_KEY_ID=PK...        # paper keys start with PK
APCA_API_SECRET_KEY=...
```

SONAR picks it up automatically and falls back to the internal book if it is
absent or misconfigured.

**On the guards.** Alpaca's live and paper APIs differ by one hostname, so a
typo or a stray environment variable is all that separates a simulation from
real orders. The host is a module constant with no parameter to override; a key
that is not clearly a paper key (`PK…`) is refused before any request; the
account is checked at connect time; and the whole set is re-checked on every
order rather than only at construction. Each failure raises — a broker adapter
that keeps working after a safety check fails is worse than none.

One trap worth recording, because the tests caught it: a substring check for the
live host looks like sensible defence in depth and is actively wrong.
`api.alpaca.markets` is contained in `paper-api.alpaca.markets`, so it rejects
the only safe URL. The guard uses exact host equality.

Going live is not a flag in this file. It is a decision for a human with an
account, and SONAR does not implement it.


## Data providers, and the switch behind each one

Everything runs on Yahoo Finance, which is free, broad and **undocumented**. It
can change shape or start refusing requests without notice, and it already has:
the `quoteSummary` endpoint used for earnings dates now answers 401. One
undocumented endpoint carrying the whole app is its largest fragility.

`sonar/providers.py` puts sources behind one interface — a **capability**
(quotes, bars, FX, crypto), a **tier** (keyless or keyed), and a persisted
**on/off switch**. A request walks the enabled providers in preference order and
takes the first that answers, so a vendor going down is a skipped provider
rather than a broken app.

| provider | tier | serves | note |
|---|---|---|---|
| Yahoo | keyless | quotes, bars, FX, crypto | Broad, free, unstable — the reason this exists |
| CoinGecko | keyless | crypto | Survives a coin being delisted from any one venue |
| Frankfurter | keyless | FX | ECB reference rates; stable, but daily not live |
| Finnhub | free key | quotes, bars | Documented and supported — the sturdiest upgrade |
| Twelve Data | free key | quotes, bars, FX, crypto | Wide coverage, tight request limit |
| Alpha Vantage | free key | quotes, bars | ~25 requests/day; research only |

Keys go in the same git-ignored `.env` as the Alpaca ones.

**What this immediately revealed.** Switch Yahoo off and crypto still resolves
via CoinGecko, FX via Frankfurter — but **equities return nothing at all**. They
have no keyless second source, so a single undocumented endpoint is a single
point of failure for most of the watchlist. A free Finnhub key is the fix, and
the layer now makes that visible instead of leaving it to be discovered when
Yahoo breaks.

**Stooq is deliberately absent.** It appears in most "free market data" lists
and an earlier version of this README recommended it; both its CSV endpoints
now return an HTML bot-block page. An adapter would have parsed that into
silence and looked like a working fallback.


## Risk tolerance and horizon

Two knobs, and it matters *where* they apply.

**Risk tolerance** (`--risk conservative|moderate|aggressive`) is about **you**, not the market.
It was always in the code — hardcoded as four constants at the top of `engine.py` — and is now
named. It changes what you **stake** and what you **see**, never what something **scores**:

| | edge threshold | Kelly | max stake | max daily vol |
|---|---|---|---|---|
| conservative | 7¢ | ¼ | 3% | 4% |
| **moderate** (default) | 4¢ | ½ | 8% | none |
| aggressive | 2.5¢ | ¾ | 15% | none |

**Horizon** (`--horizon intraday|week|month`) is about **when**. The hourly engine has no
horizon to pick — Polymarket's up/down market *is* one hour — so this shapes the asset screener
only: it switches its momentum window (1d / 5d / 20d) to match, and writes the exit plan
against that holding period.

Both are live-switchable from `POST /api/config`; the boards rescan immediately.

> Confidence scores are deliberately **not** affected by either. Confidence measures the market;
> risk measures you. Folding one into the other would mean the same market scored differently for
> a cautious user than a reckless one — and the number would stop measuring anything.

## The LLM read (optional, off by default)

A second, **separate** track: an on-demand narrative read of one selected opportunity.

`model.prob_up()` is a *calibrated* probability — when it says 0.6, roughly 60% of those hours
should close up, and the engine checks by settling every trade against the real candle. An LLM's
stated conviction is not that; it is fluent, not calibrated. So the two are never averaged:

- **`confidence`** — arithmetic, component bars, unchanged.
- **`llm_read`** — direction, conviction, catalysts, risks. Labelled uncalibrated everywhere.

The part that earns its keep: every stated conviction is **logged onto the trade record**, and
SONAR already resolves trades against ground truth. `engine.llm_calibration()` buckets them and
reports the realised hit rate per bucket, so after enough hours you can see whether the model's
confidence ever tracked reality. Rising hit rate across buckets means it carries information;
flat or inverted means it doesn't — and you'll know.

Headlines go to the model as **titles only**, inside a delimited block, marked untrusted. No
article bodies are sent, and the system prompt states that instructions appearing inside that
block are never to be followed.

```bash
pip install anthropic          # only needed for this feature
export ANTHROPIC_API_KEY=...   # or: ant auth login
```

Runs `claude-opus-5` at `medium` effort, on demand for one opportunity — never across the board
on every scan, which would cost real money for no benefit.

## Run it

SONAR is a native macOS app — PySide6 widgets, every chart drawn with `QPainter`. There is no
web view, which is why the bundle is ~98MB rather than ~300MB.

```bash
uv venv .venv && uv pip install -r requirements.txt
python main.py              # the app
python main.py --selftest   # check a build's wiring and exit
python main.py --headless   # the old HTTP daemon instead
```

Build a signed `.app`:

```bash
./build_app.sh              # add --install to copy into /Applications
```

The build script runs `--selftest` **against the frozen binary**, because that is where
packaging fails: a bundle is read-only and code-signed, so writable state must live in
`~/Library/Application Support/SONAR/` (writing inside the `.app` breaks the signature and a
reinstall wipes it), and lazily-imported modules — `anthropic`, here — are invisible to
PyInstaller's static analysis without an explicit `--hidden-import`.

Note the frozen app and the source tree keep **separate portfolios**: `~/Library/Application
Support/SONAR/state.json` versus `data/state.json`. Installing does not inherit a dev bankroll.

Leave it running and the equity curve grows by one point each hour as markets resolve. The
active risk profile is saved with the state, so a bankroll keeps the profile it was built
under; delete the state file to reset to a clean $10,000.

### Uptime

SONAR is a daemon wearing an app: the equity curve only means something if positions settle on
the hours they were priced for. So two things protect that.

**The close button hides.** The window disappears, the engine keeps running, and the menu-bar
item shows bankroll and open position. Quitting is a separate, deliberate menu action — and
clicking the Dock icon brings the window back if the menu-bar item is hard to find.

**A launchd agent** keeps it running when you are not logged into the app at all:

```bash
./scripts/install_agent.sh             # install and start
./scripts/install_agent.sh --status
./scripts/install_agent.sh --uninstall
```

Running both is safe. `sonar/enginelock.py` enforces **one engine per state file**: whoever
starts first drives, and the other opens read-only rather than settling the same hour twice —
which would double-count the portfolio silently. A lock left behind by a killed process is
reclaimed rather than blocking forever.

**Headless is still dependency-free.** `python main.py --headless` runs the same
`sonar.core.Live` behind the stdlib HTTP server with the original browser dashboards.

## Execution guard (simulator only)

`sonar/execution.py` is the safety layer that would sit between a signal and a real order. It
contains **no broker integration** — it talks to an abstract port whose only implementation is
an in-process simulator, so every rule in it is testable:

- an order is never sent without explicit human confirmation
- idempotent client order ids, recorded *before* the send, so a double-click cannot double-fill
- hard caps on notional, quantity, orders per day, and open positions, checked locally
- an instrument allowlist that **fails closed** — empty permits nothing
- unpriced orders rejected: no limit price means no notional to cap
- an unknown outcome halts the guard rather than retrying, because a retry is how one order
  becomes two
- append-only audit log, and a kill switch that latches closed

There is deliberately **no live venue wired up**. SONAR's only calibrated model prices the
Polymarket hourly BTC market, which conventional brokers cannot trade; the assets board, which
they can trade, explicitly asserts nothing. Connecting execution to the board SONAR does not
model would be pointing a careful safety layer at the wrong signal.

### What it costs

**Nothing, unless you use the LLM read.** Every data source is a free keyless public API, no
trades means no fees, and the model, the screener and the paper engine make no AI calls at all.
The only standing resource is bandwidth — roughly **8 MB/hour (~190 MB/day)** left running 24/7.
It used to be 60 MB/hour: dropping the multi-market Polymarket board removed ~52 MB/hour, which
was the single largest thing SONAR downloaded, for a board that mirrored the crowd's own prices
and could say nothing of its own.

The LLM read is the one paid path: it bills normal Anthropic API rates per invocation, and only
when you ask for one. It is not wired into any polling loop.

## Layout

```
main.py        entry point — app, --selftest, --headless
sonar/
  core.py      the headless engine driver; both the app and the daemon use it
  feeds.py     BTC/ETH candles + Polymarket market, order book, multi-market scan
  model.py     barrier probability + Galton-lattice distribution
  risk.py      risk profiles — staking and filtering, never scoring
  horizon.py   return horizons, intraday → year — timing curve + momentum window
  macro.py     FRED regime (curve, VIX, real rates, labour) for long horizons
  paths.py     dev vs frozen path resolution — the packaging landmine
  engine.py    paper portfolio: sizing, settlement, persistence, stats, LLM calibration
  llm.py       the optional narrative read (the only module with a dependency)
  news.py      reputable RSS/Atom (financial, political, tech, wires), matching + sentiment
  assets.py    real-asset screener (equities/indices/FX/crypto/commodities)
  scoring.py   volatility-scaled target/stop → R:R, P(profit), EV, position sizing
  portfolio.py the general paper book: buy/short anything, mark, settle, persist
  calibration.py did high scores actually win? the loop that grades the screener
  backtest.py  replay the plan over years of real bars, with an attention proxy
  events.py    Nasdaq earnings and IPO calendars — scheduled catalysts
  universe.py  the tradeable universe from Nasdaq + Wikipedia article resolution
  providers.py pluggable data sources: capability, tier, and an on/off switch
  alpaca.py    Alpaca **paper** broker, with the live endpoint made unreachable
  enginelock.py single-writer guard so two SONARs cannot double-count one book
  server.py    stdlib HTTP server over core.Live (headless mode)
  research/    the study apparatus — features, panel, stats, validate, regimes
ui/
  app.py       the window — Terminal / Assets / Wire / Book / Macro
  charts.py    QPainter charts: equity curve, sparkline, depth, lattice, bars
  theme.py     palette, lifted from the original terminal's CSS
  worker.py    QThreads for the poll loop, LLM reads, and config changes
assets/
  make_icon.py one-off icon generator (QPainter, no extra deps)
static/
  index.html   the BTC terminal (canvas charts, tooltips)
  docs.html    in-app documentation
```

### API

| | |
|---|---|
| `GET /api/state` | live snapshot: candle, market, signal, portfolio, calibration |
| `GET /api/assets` | the real-asset screen |
| `GET /api/config` | current risk/horizon, available options, LLM availability |
| `POST /api/config` | `{"risk": "...", "horizon": "..."}` — switches and rescans |
| `POST /api/read` | `{"kind": "btc\|asset", "id": "..."}` — one LLM read |

## What is left

The build backlog is finished — providers, Alpaca paper trading, the paper book, the research
apparatus and the calibration loop all shipped. What remains is not more code:

- **A free Finnhub key.** Equities currently have no keyless second source, so most of the
  watchlist rides on one undocumented Yahoo endpoint. This is the single highest-value change.
- **Let the paper book run.** A real track record is the one thing no amount of backtesting
  substitutes for, and the calibration table stays empty until ~20 positions have closed.
- **Better data, if the research is ever resumed.** Five studies found nothing in daily bars,
  free news and macro regimes. Anything further needs intraday bars, order flow, or a news
  archive with tone — all of which cost money. More features on this data is not the answer.

**Not planned: real-money execution.** SONAR will not place live orders, connect a funded
broker, or move real money. Going live is a decision for a human with an account.

**Investigated and closed: Revolut.** There is no public retail-investment API, so reading
holdings is not possible; balances would need a licensed Open Banking aggregator. Reopen only
as a deliberate project, not a spike.

## Not advice

This is a demonstration of a probability model and a set of transparent heuristics against live
markets. It is **not** financial advice, and paper P&L predicts nothing about real results — an
earlier run showed **+114% on a 44% win rate**, carried entirely by three longshot wins. That is
variance wearing a costume, and it is exactly why this stays on paper. Going live with real funds
would be an entirely separate decision, with real risk, real fees, and no guarantees.
