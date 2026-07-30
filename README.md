# ◇ SONAR — BTC Up/Down paper-trading terminal

A live, **honest** recreation of the "Claude built an overnight trading bot" dashboard
that goes around social media. Same look — a dark terminal with an equity curve, a
probability lattice, a live BTC pulse and an order book — but with the marketing stripped
out and the mechanics laid bare.

> **The viral post is engagement bait.** Its own numbers don't agree ($867 in the headline,
> $847 in the body) and the screenshot shows a $438,012 balance. No overnight bot prints
> money like that. What *is* real and worth building is the machine underneath: a live
> probability model priced against a real prediction market. This project builds exactly
> that — and keeps it **paper money** so it can be honest about what it is.

## What's real vs simulated

| Real (read-only public data) | Simulated |
|---|---|
| BTC price + hourly candle — Binance `BTCUSDT` (the actual Polymarket resolution source), Coinbase fallback | The bankroll ($10,000 paper) |
| Polymarket hourly "Bitcoin Up or Down" market — implied odds, best bid/ask, order book | Every position — **no exchange, no wallet, no order is placed anywhere** |
| Candle resolution (Up if close ≥ open) | The P&L |

There are **no** API keys, **no** authentication, and nothing here can move real money.

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
It is small and frequently negative after crossing the spread. The dashboard shows that
honestly.

The engine takes at most **one** capped fractional-Kelly paper position per hour, only when
`|model − market|` clears a threshold with enough time left, and settles it on the real candle.

The equity curve is seeded with a **fair-odds backtest** over the last 36 real hours
(expected value ≈ 0 by construction — it illustrates variance, not profit), then extends
with live paper trades marked by a gold "LIVE" divider.

## Run it

Zero dependencies — Python 3.11+ standard library only:

```bash
python3 -m sonar.server         # then open http://127.0.0.1:8787
# options: --host 0.0.0.0 --port 9000
```

Leave it running and the equity curve grows by one point each hour as markets resolve.
State persists to `data/state.json` (git-ignored).

## Layout

```
sonar/
  feeds.py    live BTC candle + Polymarket market/order-book (stdlib urllib)
  model.py    barrier probability + Galton-lattice distribution
  engine.py   paper portfolio: sizing, settlement, persistence, stats
  server.py   background poller + stdlib HTTP server serving the snapshot
static/
  index.html  the dark terminal dashboard (canvas charts, polls /api/state)
```

## Not advice

This is a demonstration of a probability model against a live market. It is **not** financial
advice, and paper P&L predicts nothing about real results. Going live with real funds would
be an entirely separate decision, with real risk, real fees, and no guarantees.
