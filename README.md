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
| **Assets** | `/scan` → `$ Assets` | Screener over 17 real instruments — equities, indices, forex, crypto spot, commodities | **No** — a computed "lean" only |

Plus in-app docs at `/docs`, and a tooltips toggle that explains every number on hover.

## What's real vs simulated

| Real (read-only public data) | Simulated |
|---|---|
| BTC/ETH price + hourly candle — Binance (the actual Polymarket resolution source), Coinbase fallback | The bankroll ($10,000 paper) |
| Polymarket odds, best bid/ask, order books, market metadata | Every position — **no exchange, no wallet, no order placed anywhere** |
| Equities/indices/FX/commodities — Yahoo Finance | The P&L |
| News — BBC, MarketWatch, Yahoo, NPR, Ars Technica, TechCrunch, The Verge | |

**No** API keys, **no** authentication, **no** write access anywhere, and nothing here can move
real money. The running app also makes **zero AI/LLM calls** — the model is local arithmetic.

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
- **Assets** — news `0.45`, momentum `0.35`, volatility `0.20`. The Bullish/Bearish **lean** is
  just the sign of *(5-day momentum + crude news sentiment)*: a computed indicator, not advice.

News is **context, not a predictor**. Sentiment is a small word-list heuristic, matching is
deliberately conservative, and scraped text is treated as **untrusted data** — read and
summarised, never acted upon.

## Run it

Zero dependencies — Python 3.11+ standard library only:

```bash
python3 -m sonar.server         # then open http://127.0.0.1:8787
# options: --host 0.0.0.0 --port 9000
```

Leave it running and the equity curve grows by one point each hour as markets resolve.
State persists to `data/state.json` (git-ignored; delete it to reset to a clean $10,000).

### What it costs

**Nothing.** Runs locally, every source is a free keyless public API, no trades means no fees,
and no AI calls at runtime. The only resource is bandwidth — measured at roughly **60 MB/hour
(~1.4 GB/day)** if left running 24/7, dominated by the 90-second market scan. Widening that
interval to 5 minutes cuts total traffic ~70%. Relevant only on metered connections.

## Layout

```
sonar/
  feeds.py     BTC/ETH candles + Polymarket market, order book, multi-market scan
  model.py     barrier probability + Galton-lattice distribution
  engine.py    paper portfolio: sizing, settlement, persistence, stats
  news.py      reputable RSS/Atom (financial, political, tech), matching + sentiment
  scanner.py   multi-market confidence scoring and ranking
  assets.py    real-asset screener (equities/indices/FX/crypto/commodities)
  server.py    background pollers + stdlib HTTP server (/api/state, /api/scan, /api/assets)
static/
  index.html   the BTC terminal (canvas charts, tooltips)
  scan.html    the scanner + assets board
  docs.html    in-app documentation
```

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
