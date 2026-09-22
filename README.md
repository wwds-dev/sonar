# ◇ SONAR — honest market scanner & paper-trading terminal

Live market data, live prediction-market odds, reputable news, and a probability model —
with **paper money instead of promises**. It began as a recreation of the viral "an AI built
an overnight trading bot" dashboard, with the marketing stripped out and the mechanics laid bare.

> **The viral post is engagement bait.** Its own numbers don't agree ($867 in the headline,
> $847 in the body) and the screenshot shows a $438,012 balance. No overnight bot prints
> money like that. What *is* real and worth building is the machine underneath: a live
> probability model priced against a real market. SONAR builds exactly that — and keeps it
> **paper money** so it can be honest about what it is.

## Eight tabs

A native macOS app — PySide6 widgets, every chart drawn with `QPainter`, no web view.

Each tab carries **two names**: the plain one it is called by, and — under it in
small caps — the one this README and `static/docs.html` use. The plain names came
in with the Plain Language direction (below); the originals stayed because forty
sentences in the manual refer to them. `ui/tabs.py` paints both, because Qt will
not: a `\n` in `setTabText` round-trips through the API and is then drawn on one
line and clipped.

| Tab | What it does | Asserts a direction? |
|---|---|---|
| **Live model**  \n<sub>TERMINAL</sub> | Hourly BTC up/down paper trade — the model prices each hour, compares to Polymarket, takes at most one simulated bet, and grades itself against the market on every hour, traded or not | **Yes** — the only independent model |
| **Screener**  \n<sub>ASSETS</sub> | 129 instruments (50 equities, 20 indices, 20 FX pairs, 21 crypto, 18 commodities) with R:R, P(profit), news level, **how old each row's price is**, and buy/short per row | **No** — direction is yours |
| **News**  \n<sub>WIRE</sub> | Live newswire across nine press blocs, the earnings and IPO calendar, what the news is pointing at, and **alerts** on what changed since the last scan | No |
| **My trades**  \n<sub>BOOK</sub> | Open paper positions, the calibration table, and the backtest button | — |
| **Big picture**  \n<sub>MACRO</sub> | Regime: curve, VIX, real rates, unemployment | No |
| **Practice**  \n<sub>LAB</sub> | Replay the plan over real bars with the parameters exposed, compare the realised hit rate against what the barrier maths predicted, and **attribute the score component by component** — IC, quintile spread, leave-one-out, and a KEEP / WEAK / DROP / INVERTED verdict per component. Also holds **Replay**: step through real history one setup at a time making your own calls, with everything after the cursor withheld, and see your hit rate and P&L against the model's on identical setups | — |
| **Sports**  \n<sub>PLAYMAKER</sub> | Sports prop pricing across **nine sports** (NFL, NBA, MLB, NHL, EPL, UCL, NCAAB, UFC, ATP) — paste a table of books' prices and it removes the margin three ways, finds which book is out of line with its peers, and sizes the result; an LLM read is appended as commentary | — |
| **Learn** | The manual and the glossary **inside the app** — `static/docs.html` rendered by Qt, with a contents list and a search box that takes one unfamiliar word. Same file the browser serves, so the prose cannot drift; `ui/learn.py` does the translation | — |

Playmaker is `sonar/playmaker/` plus its tab in `ui/app.py`. It was ported from
Sentinel's NFL agent early on but was never a standalone project, and the scaffold
that once reserved the name under `active/` has been removed. The package is its
own git repo nested here — versioned separately, but not a separate app.

It now holds the same line the rest of SONAR does. A language model's percentage
cannot size a bet: `staking.Estimate` carries a source with every probability and
returns a zero stake for a narrative one. Both sides of a market are required,
because a margin is how far prices sum past certainty and one side cannot reveal
it. The feature with an actual published track record is the cross-book screen —
Kaunitz, Zhong & Kreiner (2017) — which finds where books disagree with each
other rather than predicting anything.

It now predicts, too: Elo in FiveThirtyEight's published form, Dixon-Coles for
football, and Pythagorean as a cross-check, fed by a keyless ESPN results adapter.
Nothing predicts until it has been measured, the same gate `calibration.py` applies
on the markets side — NFL, NBA and EPL all came back KEEP on walk-forward skill
(+0.071 / +0.120 / +0.139). `sonar/playmaker/MODELS.md` surveys the models and
carries the staged plan; read it before changing the scoring.

A Polymarket board used to sit here and was removed — mirroring a market's own odds back at
you is not analysis, and dropping it also removed ~52MB/hour of downloads. Full docs live in
the app behind the **Docs** button, plus a tooltips toggle explaining every number on hover.

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
while the market prices its own **implied** vol. When they differ we get a thin, statistical
edge — the realised-vs-implied trade quants actually run. It is small and frequently negative
after crossing the spread.

Since Sep 2026 that estimate is an **EWMA scaled by an hour-of-day profile** rather than a
flat 72-hour standard deviation. Measured first, wired second, per this project's standing
rule: over 16,078 held-out hours (two years of BTCUSDT) the combination beat the old
trailing window by **7.5% on QLIKE**, winning all six time blocks — clustering (+3.9%) and
diurnal seasonality (+3.5%) are separate, additive facts about the same hour. GARCH also
beat the incumbent but was passed over: its 720-hour anchor means part of its win is
effective sample size, the artefact the daily study's synthetic control caught — the same
control shows EWMA and the profile find nothing on constant-volatility data, so their win
can only be the two hypothesised effects. `sonar/research/hourlyvol.py` records the study
and its pre-registered expectations.

The engine takes at most **one** capped half-Kelly paper position per hour (max 8% of bankroll),
only when the model's probability for the side beats its **executable** price — the ask plus
slippage, not the midpoint — by 4¢ with enough time left, and settles it on the real candle.
(The gate used to read the midpoint, which let a fat disagreement across a fat spread count as
an edge; a 4¢ mid edge across a 10¢ spread buys nothing.)

It also **scores itself every hour, traded or not**: a mid-hour snapshot of the model's P(up)
and the market's is settled against the real candle and the two are compared by Brier score.
The paper P&L only ever grades the hours the model traded — its boldest claims, a few a day —
while this grades both forecasters on all 24, which is the direct test of the
realised-vs-implied thesis and converges in weeks instead of months. Each snapshot also
records the book's **bid and ask** at that moment, because it cannot be backfilled: Brier says
who was better *calibrated*, and only the spread can later say whether the difference was ever
**buyable** — a model can beat the mid on every hour and still have every disagreement sit
inside the bid-ask.

The equity curve is seeded with a **fair-odds backtest** over the last 36 real hours
(expected value ≈ 0 by construction — it illustrates variance, not profit), then extends
with live paper trades marked by a gold "LIVE" divider. The seeded rows stay out of the
displayed win rate and trade count, which grade live trades only — a fresh install shows
an honest zero, not a record built from trades nobody took.

Settlement survives gaps honestly too: if the app slept or restarted past the end of an
open position's hour, the next candle's open is a price from hours after that market
resolved, so the engine fetches the hour's own close and settles against that — or **voids**
the position when the close cannot be recovered, because a shorter record beats a corrupt one.

## Confidence scores

The Assets screen ranks by a **confidence score (0–100)**. Read it honestly: it is a heuristic
for how *notable* something looks — **not** the probability you'll make money. That is
`P(profit)`, and it is a separate number. Every row shows its component mix as a bar.

Weights: news `0.35`, momentum `0.30`, catalyst `0.20`, volatility `0.15`. There is **no
directional lean** — the research below found momentum carried none, so the row shows a news
*level* (Quiet / Normal / Elevated / Spike) and you pick the side with buy or short.

Sources span nine press blocs, and each feed is tagged with its origin and whether it is state-directed. That is not decoration: `news.bloc_spread()` can then tell a story carried across five blocs from one outlet running the same line all day, and flag coverage that is state-only — evidence about a government rather than corroboration of an event. A geopolitical signal built on Anglo-American outlets alone measures what one bloc is talking about.

News is **context, not a predictor**. Sentiment is a small word-list heuristic, matching is
deliberately conservative, and scraped text is treated as **untrusted data** — read and
summarised, never acted upon.

[CONFIDENCE.md](CONFIDENCE.md) is the research file on how this score is built versus how the
institutional process builds one — cross-sectional standardisation, benchmark-relative
momentum, levels versus surprises, a daily GPR-style political index from the newswire already
being read, and the argument that the thing worth forecasting here is **volatility**, not
direction.

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

### The cost floor

That zero is **gross**. Net of what a round trip costs — spread, commission, slippage — the
expectation is

```
EV = −c   per trade, every trade
```

which makes `c` the number that decides whether any of this is worth doing, and the only one
in the project that can be measured rather than estimated. `sonar/costs.py` measures it from
the execution audit log:

```python
from sonar import costs
costs.summary()        # cost per round trip, or a refusal to name one yet
```

Run through the ledger at crypto taker fees of 0.2% a side plus 5bp of slippage, on a €2,000
account risking 1% per trade:

| | |
|---|---|
| cost per round trip | **€1.05** (50.0 bps per side) |
| as a share of the €20 risked | **5.2%** |
| over 100 trades | **−€105** |

An earlier estimate in `GOING_LIVE.md` put this at ~4% and ~€0.80. Measuring it gave 5.2% and
€1.05 — the estimate was optimistic, which is the usual direction and the reason the ledger
exists. `summary()` reports `reliable: False` below 20 completed round trips and declines to
name a figure, the same threshold and reasoning as `calibration.MIN_SAMPLE`.

Five pre-registered studies failed to find drift to put against that floor. That is the whole
argument for keeping this on paper, and it is arithmetic rather than caution.

## What the backtest found

`sonar.backtest` replays the same plan over years of real bars: momentum and volatility from prior
bars only, then walk forward through actual highs and lows. A bar spanning both barriers scores as a
**loss** (daily data cannot order them) and costs are excluded, so reality is worse than this.

Over **25,504 setups** — 5 years, 113 instruments. (An earlier version of this section
called them *independent*; at a replay step shorter than the holding time, neighbouring
setups share the bars that decide them, so they are not. The Lab's error bars now carry a
Newey-West correction for that overlap. Overlap only ever *widens* an error bar, so the
null below survives the correction — it was, if anything, understated before.)

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

## The Plain Language direction

Chosen 2026-09-22, after the person this app is for said he could not read his
own screener. Three changes, each a rule rather than a taste:

- **Proportional type carries words; monospace carries only code.** Menlo was
  drawing English prose, which it is bad at. `theme.text` is the interface font,
  `theme.figure` is the same face with tabular numerals so a column of prices
  still lines up, and `theme.code` is the real monospace — used in exactly two
  places, both of which take a pasted table whose columns are made of spaces.
- **Contrast is a floor.** `MUTED` and `FAINT` now clear 4.5:1 against the panel
  they sit on; `FAINT` used to measure 1.9:1, which is decoration, not text.
  Raising it exposed a latent bug worth knowing about: every `QLabel` inherited
  the window background from the blanket `QWidget` rule and painted it over the
  panel beneath, which was invisible while the two colours were three points
  apart and became a dark box behind every cell once they were not.
- **The board is written in English.** `MOM` is "Recent move", `VOL` is "Swing
  size" over the words *big swings*, `R:R` and `P(PROF)` are one column reading
  "win 1.5× the risk / 40% of the time", and `CONF` is "Worth a look" with the
  score as a meter whose segments are still the component breakdown. Every row
  carries one plain sentence — "up hard, heavy news" — generated from numbers
  already on the row, and `tests/test_plain_language.py` asserts that sentence
  can never acquire a direction.

Headings that name something non-obvious are links: clicking one opens the Learn
tab at the section explaining it, and a test checks every one of those anchors
resolves to a section that exists. The two toolbar knobs are captioned with the
question they answer ("How much risk are you willing to take?") rather than with
the word `risk` in 9pt grey.

### How old is a price on the Screener board?

Visible on the row, in the **Updated** column, because a price that is quietly out
of date is the failure mode this project treats as unacceptable.

The board does not refetch all 129 instruments at once. Doing that took the
request rate from ~13 a minute to ~64 and got this machine throttled — and a
throttled scan does not error, it returns fewer rows and the screen silently
shrinks. So `assets.ROLL_BATCH` refetches the **26 stalest** rows per scan and
scores the rest from cache. The cadence underneath: the poll loop ticks every
4s (`core.PRICE_EVERY`), a rescan is due after 90s (`core.SCAN_EVERY`), and the
scanner's own cache holds for 120s (`AssetScanner.ttl`) — so the screen
recomputes about every three minutes, and one instrument comes round roughly
every fifteen. The column goes gold past 20 minutes and red past an hour, which
means the rotation is losing ground rather than that the price is wrong.

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
reinstall wipes it), and lazily-imported modules — `anthropic`, `sonar.execution`, `sonar.costs`,
and `sonar.playmaker`'s model modules (`results`, `ratings`, `poisson`, `scoring` — reached only
when someone opens the Playmaker tab and asks for a rating, so nothing imports them at start-up)
— are invisible to PyInstaller's static analysis without an explicit `--hidden-import`.
`--selftest` asserts all of them are present in the packaged build so a lost hidden-import fails
loudly rather than silently — the playmaker case shipped the same trap a second time before it
was caught.

Note the frozen app and the source tree keep **separate portfolios**: `~/Library/Application
Support/SONAR/state.json` versus `data/state.json`. Installing does not inherit a dev bankroll.

Leave it running and the equity curve grows by one point each hour as markets resolve. The
active risk profile is saved with the state, so a bankroll keeps the profile it was built
under; delete the state file to reset to a clean $10,000.

### Tests

```bash
./run-tests.sh                 # the suite, 300s budget
./run-tests.sh -k playmaker    # anything after the script is passed through
TEST_BUDGET_S=60 ./run-tests.sh
```

Three tests build a real `MainWindow`. The suite is **deterministic since
2026-09-19** — the wedge that used to hit one run in three was the conftest
guards being function-scoped below a module-scoped window fixture, so the
window tests ran unguarded; the guards are session-scoped now. `run-tests.sh`
keeps its external watchdog as a backstop, so a hang today is a regression to
report, not weather.

`TESTING.md` is the coverage roadmap: what's tested, what isn't, and the order to fix it
in. Tier 1 is done — `model.py` and `engine.py` both went from ~39% to **100%**, mutation-checked,
and writing the engine's cross-check test found a real ten-point disagreement between the app's
two ways of computing P(up) (a lattice bin sitting exactly on the barrier), since fixed. Tier 2
landed too (`feeds.py` 30% → 82%, `server.py` 0% → 92%); `universe.py` and
`research/features.py` are the next gaps.

### Learning what the numbers mean

The **Learn** tab *is* the manual — contents on the left, a search box that
takes one unfamiliar word ("vig", "Brier", "drawdown"), and **Open in browser**
for the full-fidelity page. It used to be a button that launched a web browser,
which is the wrong place for it: someone looking at a number they do not
understand is exactly the person who will not go and find a second window.
§1 is a plain-English primer with a 25-term glossary — it assumes no finance
background. **§8 is the one to read
before trusting a Lab run**: how to read an error bar, what the four attribution
verdicts mean, how many trials a number needs before it means anything (at 20
trials the band is ±21.5 points), and five ways to fool yourself, each of which
happened here and each naming what caught it.

### Testing

`TESTING.md` is the automated side — what is covered, what is not, and the order
to fix it in. **`TESTPLAN.md` is the manual side**: 101 acceptance cases for
signing off v2, run against the installed bundle rather than the checkout,
because several of the failures only exist in a build. Seventeen of them are marked
as regressions, which makes the list double as this project's bug history.

The app's **Test plan** button (next to *Docs*) opens it as a page that remembers
which cases you have passed or failed; the daemon serves it at `/testplan`. That
page is generated from the markdown by `scripts/build_testplan.py` — edit the
markdown, never the HTML, and `tests/test_testplan_page.py` fails if the two
drift apart.

```bash
./run-tests.sh tests/ -q          # 1,253 tests, bounded by an external watchdog
./build_app.sh --install          # then the installed binary's --selftest
```

### Uptime

SONAR is a daemon wearing an app: the equity curve only means something if positions settle on
the hours they were priced for. So two things protect that.

**The close button hides.** The window disappears, the engine keeps running, and the menu-bar
item shows bankroll and open position. Quitting is a separate, deliberate menu action — and
clicking the Dock icon brings the window back if the menu-bar item is hard to find.

Leaving full-screen and hiding are also untangled from each other: exiting a full-screen
Space and clicking the close button both trigger the macOS activation event a real Dock click
uses, so for about a second after either one the window ignores that event rather than
reopening itself the moment it just hid. Everything that reopens the window goes through one
method, because a reveal has to call off the hide a full-screen close leaves pending.

**Nothing the window waits on may fetch**, which is a wider rule than it sounds. The UI
thread reads the shared snapshot under a lock every second, so a background thread holding
that lock across a network call freezes the window just as thoroughly as fetching on the UI
thread would: the window goes blank, ignores the close button, and comes back a few seconds
later when the fetch finishes. That is what the central-bank feed did every fifteen minutes.
Build the payload first, then take the lock for the assignment — `tests/test_ui_thread.py`
checks both the behaviour and, by AST, that no known fetch sits inside a lock.

**Quitting never waits for the network.** A quit that lands while the app is fetching gives
the background threads about a second and then ends the process, printing what it gave up on.
That is deliberate: the alternative is a window that stops repainting while it waits, which is
indistinguishable from a hang — and the earlier attempt to stop a stuck thread outright froze
the app completely. Nothing is lost by leaving this way, because the engine writes each change
as it happens rather than saving on exit.

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

**The run watches itself.** Over a weeks-long collection run, hours can go missing silently —
feed down, machine asleep, agent dead — and the damage would only show at review time as a
mysteriously small n. So the Terminal tab carries the run's vital signs (hours scored vs
elapsed, settlements voided, time since anything last settled), and because the BTC market
resolves around the clock, **two silent hours always means a stall**: the menu-bar item posts
a notification and flags STALLED rather than sitting there looking healthy. The state files
also keep a **daily rotating backup** (`.bak.<date>`, last seven days) beside themselves —
they are the experiment's output and live nowhere else.

**Protocol mode** (a checkbox on the Book tab, off by default) is how the calibration table
fills without discretion: once a day it opens fixed-small paper positions on the five highest-
and five lowest-confidence rows, direction chosen by **coin flip**. Random on purpose — the
score claims notability, never direction, and a coin flip isolates exactly the claim the
calibration table exists to test. Turning it off leaves open positions to resolve; closing
them early would censor the outcomes being measured. Paper money, as everything here.

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
- notional also capped as a share of equity **read from the venue**, so a stale local bankroll
  cannot size the next position; a port that cannot report equity is refused
- append-only audit log
- a kill switch that cancels, **flattens**, then latches — `flatten()` is exempt from the halt
  latch and every cap, because a limit that can stop you closing a position is one that traps
  you in it, and it stays idempotent because a duplicate closing order opens the opposite
  position rather than closing twice
- `reconcile(expected=...)` halts on any disagreement between local state and the venue —
  a position opened by hand in the broker's own app is otherwise invisible
- `GuardedBroker` fills the portfolio's broker seam through the guard, so the Book tab
  cannot become a second unguarded route to a venue. Confirmation defaults to *refuse*, and
  a refusal **raises** rather than returning an error dict — `Portfolio.enter` ignores that
  return value, so a dict would leave the book holding a position that was never sent
- the book distinguishes **accepted** from **filled**. A broker declares `synchronous`; when it
  is false a position is recorded `PENDING`, carries no unrealised P&L, and is never closed on a
  barrier — `poll_fills()` then rewrites it from the venue's real quantity and price, or refunds
  the reserved cash if the order died. The target and stop are deliberately *not* re-derived
  from a worse fill: slippage should eat the reward, not move the goalposts
- `settle()` polls orders to a terminal state and records what each one actually cost;
  `sonar/costs.py` turns that into cost per round trip. Slippage is measured against the
  decision mark rather than the limit, so deliberately crossing the spread is not scored as
  a cost, and the summary refuses to name a figure below 20 completed round trips

There is deliberately **no live venue wired up**. SONAR's only calibrated model prices the
Polymarket hourly BTC market, which conventional brokers cannot trade; the assets board, which
they can trade, explicitly asserts nothing. Connecting execution to the board SONAR does not
model would be pointing a careful safety layer at the wrong signal.

If you intend to connect one anyway, [GOING_LIVE.md](GOING_LIVE.md) is the implementation
guide: venue choice, the `BrokerPort` contract, what paper trading hides, and the trap that
there are **two** broker seams here and only one of them is guarded.

### What it costs

**Nothing, unless you use the LLM read.** Every data source is a free keyless public API, no
trades means no fees, and the model, the screener and the paper engine make no AI calls at all.
The only standing resource is bandwidth — roughly **8 MB/hour (~190 MB/day)** left running 24/7.
It used to be 60 MB/hour: dropping the multi-market Polymarket board removed ~52 MB/hour, which
was the single largest thing SONAR downloaded, for a board that mirrored the crowd's own prices
and could say nothing of its own.

The LLM read is the one paid path: it bills normal Anthropic API rates per invocation, and only
when you ask for one. It is not wired into any polling loop.

## Which version am I running?

The header says, next to the name: **`v2.103`** — a number that moves with
every commit. The window title carries it
too, because bug reports arrive as screenshots and the title is in every one.

```
v<MAJOR>.<BUILD>
   │        └── git rev-list --count HEAD, zero-padded to three digits
   └─────────── the product arc, from the VERSION file
```

MAJOR is hand-edited and changes only on a deliberate milestone. BUILD is the
commit count — derived, so it cannot be forgotten, and a version that is never
bumped by hand is never silently wrong. The Lab Project Monitor computes the
same string from the same two inputs, so the dashboard and the app cannot
disagree.

**Hover the version** and it reports the commit, the date, whether this is a
packaged build or a checkout, and whether a newer build exists:

```
SONAR v2.103
commit c3fcd81
2026-09-22
packaged build
7 commits behind the checkout (v2.107). Re-run ./build_app.sh --install to catch up.
```

When that cannot be known — a packaged app on a machine with no source — it says
so rather than claiming to be current. A version display that guesses is worse
than none, because it gets believed.

This exists because of a specific, repeated failure: a rebuild would land, the
app would be opened, and the new work was not there — the bundle in
`/Applications` was older than the conversation about it, and nothing on screen
could say so. `main.py --selftest` prints the same information and **fails** if a
frozen bundle has no build stamp. Full scheme in `VERSIONING.md`; what each
installed build contained is in `CHANGELOG.md`.

## Layout

```
main.py        entry point — app, --selftest, --headless
sonar/
  core.py      the headless engine driver; both the app and the daemon use it
  feeds.py     BTC/ETH candles + the hourly Polymarket market and its order book
  model.py     barrier probability + Galton-lattice distribution
  risk.py      risk profiles — staking and filtering, never scoring
  horizon.py   return horizons, intraday → year — timing curve + momentum window
  macro.py     FRED regime (curve, VIX, real rates, labour) for long horizons
  paths.py     dev vs frozen path resolution — the packaging landmine — plus daily state backups
  engine.py    paper portfolio: sizing, settlement, the hourly model-vs-market score log, run health, LLM calibration
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
  execution.py the order guard: caps, confirmation, idempotency, flatten, audit
  costs.py     what a round trip actually cost, derived from the audit log
  institutions.py central-bank releases, FOMC and speeches — scheduled catalysts
  venues.py    where a row could actually be traded, and where it could not
  replay.py    step through history one setup at a time — grades you, not the model
  alerts.py    what changed — fires on transitions, never asserts a direction
  enginelock.py single-writer guard so two SONARs cannot double-count one book
  server.py    stdlib HTTP server over core.Live (headless mode)
  playmaker/   sports prop pricing, nine sports — the Playmaker tab
    devig.py   three devig methods (multiplicative, Clarke power, Shin), cross-book consensus, outlier screen
    staking.py Estimate (probability + interval + source); Kelly at the interval's low end
    MODELS.md  what the successful sports models do, and the staged plan
  research/    the study apparatus — features, panel, stats, validate, regimes,
               and hourlyvol (the measured EWMA × hour-of-day σ the Terminal prices with)
ui/
  app.py       the window — Terminal / Assets / Wire / Book / Macro / Lab / Playmaker / Learn
  learn.py     static/docs.html translated into what Qt's rich text can render
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
| `GET /api/state` | live snapshot: candle, market, signal, portfolio, model-vs-market, run health, calibration |
| `GET /api/assets` | the real-asset screen |
| `GET /api/config` | current risk/horizon/protocol, available options, LLM availability |
| `POST /api/config` | `{"risk": "...", "horizon": "...", "protocol": true}` — switches and rescans |
| `POST /api/read` | `{"kind": "btc\|asset", "id": "..."}` — one LLM read |

## What is left

The build backlog is finished — providers, Alpaca paper trading, the paper book, the research
apparatus and the calibration loop all shipped. What remains is not more code:

- **A free Finnhub key.** Equities currently have no keyless second source, so most of the
  watchlist rides on one undocumented Yahoo endpoint. This is the single highest-value change.
- **Let the paper book run.** A real track record is the one thing no amount of backtesting
  substitutes for, and the calibration table stays empty until ~20 positions have closed.
  **Protocol mode** (Book tab) fills it systematically — coin-flip direction, fixed small
  stakes — so the table measures the score rather than the operator's moods.
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
