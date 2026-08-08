# ◇ SONAR — honest market scanner & paper-trading terminal

Live market data, live prediction-market odds, reputable news, and a probability model —
with **paper money instead of promises**. It began as a recreation of the viral "an AI built
an overnight trading bot" dashboard, with the marketing stripped out and the mechanics laid bare.

> **The viral post is engagement bait.** Its own numbers don't agree ($867 in the headline,
> $847 in the body) and the screenshot shows a $438,012 balance. No overnight bot prints
> money like that. What *is* real and worth building is the machine underneath: a live
> probability model priced against a real market. SONAR builds exactly that — and keeps it
> **paper money** so it can be honest about what it is.

## Three views

| View | URL | What it does | Asserts a side? |
|---|---|---|---|
| **Terminal** | `/` | BTC hourly up/down paper trading — model prices each hour, compares to Polymarket, takes at most one simulated bet | **Yes** — a real (paper) edge |
| **Scanner** | `/scan` | Ranks many live Polymarket markets (crypto, economy, politics, geopolitics) by a transparent confidence heuristic, with matched news | Crypto up/down only |
| **Assets** | tab | Screener over 26 instruments — equities, indices, forex, 11 crypto, commodities — with R:R, P(profit), and buy/short | **No** — direction is yours |
| **Wire** | tab | Live newswire (Reuters, AP, Bloomberg, FT…) beside the earnings and IPO calendar | no |
| **Book** | tab | Open paper positions, plus the calibration and backtest that grade the score | — |

Plus in-app docs at `/docs`, and a tooltips toggle that explains every number on hover.

## What's real vs simulated

| Real (read-only public data) | Simulated |
|---|---|
| BTC/ETH price + hourly candle — Binance (the actual Polymarket resolution source), Coinbase fallback | The bankroll ($10,000 paper) |
| Polymarket odds, best bid/ask, order books, market metadata | Every position — **no exchange, no wallet, no order placed anywhere** |
| Equities/indices/FX/commodities — Yahoo Finance | The P&L |
| News — Reuters, AP, Bloomberg, FT, BBC, MarketWatch, Yahoo, NPR, CNBC, Ars Technica, TechCrunch, The Verge | |

**No** authentication, **no** write access anywhere, and nothing here can move real money.

The probability model, both scanners and the paper engine make **zero AI/LLM calls** — that is
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

Both scanners rank by a **confidence score (0–100)**. Read it honestly: it is a heuristic for
how *notable and tradeable* something looks — **not** the probability you'll make money. Every
card shows its component mix as a bar.

- **Markets** — model edge (crypto only) `0.30`, liquidity `0.20`, timing `0.15`, momentum `0.15`,
  news `0.20`. Non-crypto markets reweight across the remaining four.
- **Assets** — news `0.35`, momentum `0.30`, catalyst `0.20`, volatility `0.15`. There is **no
  directional lean**: the backtest below found momentum carried none, so the row shows a news
  *level* (Quiet/Normal/Elevated/Spike) and you pick the side with buy or short.

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

## Risk tolerance and horizon

Two knobs, and it matters *where* they apply.

**Risk tolerance** (`--risk conservative|moderate|aggressive`) is about **you**, not the market.
It was always in the code — hardcoded as four constants at the top of `engine.py` — and is now
named. It changes what you **stake** and what you **see**, never what something **scores**:

| | edge threshold | Kelly | max stake | min liquidity |
|---|---|---|---|---|
| conservative | 7¢ | ¼ | 3% | $50k |
| **moderate** (default) | 4¢ | ½ | 8% | $10k |
| aggressive | 2.5¢ | ¾ | 15% | none |

**Horizon** (`--horizon intraday|week|month`) is about **when**. The hourly engine has no
horizon to pick — Polymarket's up/down market *is* one hour — so this shapes the two scanners:
the timing component now **peaks at your horizon** instead of always preferring "soonest", and
the asset screener switches its momentum window (1d / 5d / 20d) to match.

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
trades means no fees, and the model, scanners and paper engine make no AI calls at all. The
only standing resource is bandwidth — roughly **60 MB/hour (~1.4 GB/day)** left running 24/7,
dominated by the 90-second market scan; widening that to 5 minutes cuts traffic ~70%.

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
  news.py      reputable RSS/Atom (financial, political, tech), matching + sentiment
  scanner.py   multi-market confidence scoring and ranking
  assets.py    real-asset screener (equities/indices/FX/crypto/commodities)
  server.py    stdlib HTTP server over core.Live (headless mode)
ui/
  app.py       the window — Terminal / Markets / Assets / Macro
  charts.py    QPainter charts: equity curve, sparkline, depth, lattice, bars
  theme.py     palette, lifted from the original terminal's CSS
  worker.py    QThreads for the poll loop, LLM reads, and config changes
assets/
  make_icon.py one-off icon generator (QPainter, no extra deps)
static/
  index.html   the BTC terminal (canvas charts, tooltips)
  scan.html    the scanner + assets board
  docs.html    in-app documentation
```

### API

| | |
|---|---|
| `GET /api/state` | live snapshot: candle, market, signal, portfolio, calibration |
| `GET /api/scan` | ranked prediction markets for the current horizon + risk |
| `GET /api/assets` | the real-asset screen |
| `GET /api/config` | current risk/horizon, available options, LLM availability |
| `POST /api/config` | `{"risk": "...", "horizon": "..."}` — switches and rescans |
| `POST /api/read` | `{"kind": "btc\|market\|asset", "id": "..."}` — one LLM read |

## Roadmap

- **Pluggable providers** — every data source behind one adapter interface, each with its own
  on/off and free/paid toggle (Finnhub, Alpha Vantage, Twelve Data, Polygon, Tiingo, CoinGecko…).
- **Alpaca paper trading** — real simulated equity trades in Alpaca's **paper** sandbox, so
  stocks get the same honest treatment BTC already has. Paper endpoint only, guarded at startup.
- **Read-only balances** — Revolut and other accounts via an Open Banking aggregator, shown as
  context. Display only, never moving money.
- **Not planned: real-money execution.** SONAR will not place live orders, connect a funded
  broker for execution, or move real money.

## Not advice

This is a demonstration of a probability model and a set of transparent heuristics against live
markets. It is **not** financial advice, and paper P&L predicts nothing about real results — an
earlier run showed **+114% on a 44% win rate**, carried entirely by three longshot wins. That is
variance wearing a costume, and it is exactly why this stays on paper. Going live with real funds
would be an entirely separate decision, with real risk, real fees, and no guarantees.
