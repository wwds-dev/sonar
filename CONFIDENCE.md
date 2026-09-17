# Improving the confidence score

Research notes on what the institutional process does differently, what of it
transfers to SONAR, and what the evidence actually supports. Nothing here is
implemented. Ranked recommendations are at the end.

---

## 0. What "improve" can honestly mean

The score's stated job is **notability** — "something is happening here, worth a
look" — and it is explicitly not a profit prediction. Five pre-registered studies
over 116,563 asset-days found no directional edge in momentum, news sentiment,
public attention, distance to the 52-week high, or macro regimes. `TODO.md`
records the conclusion: more features on the same daily bars is not the answer.

So there are two different projects, and they should not be confused:

**(a) Make the score a better notability ranker.** Its current defects are
structural and visible in the arithmetic — no edge claim required to fix them,
and no new data needed. §1–§4.

**(b) Make it predict something.** Direction has been tested five times and
failed. But *volatility* is a different question, it has not been tested, and
the literature is consistent that attention and news predict it. §8. This is
also the one that pays off inside SONAR immediately, because volatility already
sets the target, the stop, the R:R and therefore `P(profit)`.

The political layer the app is built around belongs mostly to (b), as a
**variance** signal rather than a directional one. §7.

---

## 1. What the score computes today

From `sonar/assets.py`:

```python
_W = {"momentum": .30, "volatility": .15, "news": .35, "catalyst": .20}

comp["momentum"]   = min(1, abs(mom) / scale)      # scale is per-horizon
comp["volatility"] = min(1, vol / 0.03)            # 3%/day saturates
comp["news"]       = coverage                      # saturates ~2 fresh headlines
comp["catalyst"]   = catalyst_score(days_away, horizon)

confidence = 100 * Σ w_k · comp_k
```

Five defects follow from that arithmetic alone, before any question of edge:

**1. It is not comparable across instruments.** Every component is scaled
against a fixed absolute constant. `vol / 0.03` means a crypto pair sits near 1.0
essentially always and an FX pair essentially never. The volatility term is
therefore close to an asset-class dummy — it tells you what kind of thing you are
looking at, not that anything is happening to it.

**2. Momentum is unbenchmarked.** `abs(mom)/scale` does not know what the rest of
the market did. NVDA +10% in a week when semiconductors are +9% scores exactly
the same as NVDA +10% when semis are flat, and only the second is information.

**3. Three of the four components are levels, not surprises.** News coverage,
volatility and earnings proximity all measure *how much*, not *how much more than
usual for this instrument*. Markets price expectations; what moves them is the
deviation from expectation. A permanently well-covered name scores permanently
high on news for no reason connected to today.

`news_level()` already found this the hard way — its docstring records that
coverage "saturates at two fresh headlines, so a well-followed name like Apple sat
at 1.0 almost permanently and two-thirds of the board read Spike". The fix applied
there (count fresh stories instead) is correct and local. The same disease is
still in the `news` component itself, and in `volatility`, and in `catalyst`.

**4. The components are correlated and then summed as if they were not.** News
spikes and price moves co-occur — that is most of what a news spike is. Adding
0.35·news to 0.30·momentum double-counts the shared part, so the blend is
effectively more concentrated than its weights suggest.

**5. Absolute momentum discards the sign, then the score is used to rank.** That
is defensible given the research (no directional edge to extract) but it means the
score cannot distinguish a 10% rally from a 10% collapse, which are not equally
notable in every context.

---

## 2. The institutional pipeline

What a Barra/MSCI-style equity model does to a raw signal before it is allowed to
mean anything, in order:

1. **Winsorize** — clip at roughly ±3 standard deviations so one bad print cannot
   dominate. SONAR's `min(1, x/scale)` is a crude one-sided version of this: it
   caps the top but does nothing about the distribution below.
2. **Standardize cross-sectionally** — convert to a z-score *across the universe
   on that date*, so the number means "unusual relative to peers today" rather
   than "large against a constant chosen once".
3. **Neutralize** — regress out the things you do not intend to bet on (sector,
   size, market beta) and keep the residual. This is the step SONAR has no
   analogue of at all.
4. **Combine with correlation in mind** — orthogonalize correlated signals, or
   weight by inverse correlation, rather than summing.
5. **Evaluate by IC and IR** — the cross-sectional rank correlation between score
   and forward return, and Grinold's `IR ≈ IC · √breadth`.

Step 5 SONAR already has, in `sonar/research/`. Steps 1–4 it does not.

The order matters: neutralizing before standardizing, or standardizing against a
constant instead of against the cross-section, both give you a number that looks
like a z-score and is not one.

---

## 3. Fix: make the score cross-sectionally comparable

The smallest change with the largest effect on honesty. For each component, on
each scan:

```
z = (x − median(x across the board today)) / MAD(x across the board today)
```

Median and MAD rather than mean and standard deviation, because the board is 26
instruments and one crypto move should not set the scale for the equities.

Then **standardize within asset class** as well, so "unusual for a currency pair"
and "unusual for a coin" are the same number. This removes the asset-class dummy
described in §1.1 without removing volatility from the score.

Cost: no new data, no new dependency, and the result is testable — a score that is
comparable across instruments should rank better on any target than one that is
not, and `research/stats.py` can measure whether it does.

---

## 4. Fix: benchmark momentum against its own class

Replace raw `abs(mom)` with the residual after removing the class move:

```
resid = mom_instrument − β · mom_class
```

where `mom_class` is the equal-weighted move of that instrument's asset class on
the board, and β can start at 1.0 (simple demeaning) before anything fancier.
This is step 3 of §2 at the crudest useful level, and with 26 instruments across
five classes the class mean is estimable from the board itself — no extra fetches.

SONAR already carries `^GSPC`, `^IXIC` and `^DJI`, so equities have a natural
benchmark sitting in the watchlist already.

---

## 5. Fix: turn levels into surprises

For each component, replace the absolute level with a deviation from that
instrument's own recent baseline:

| component | today | instead |
|---|---|---|
| news | coverage volume | today's matched-story count vs that symbol's trailing 30-day median |
| volatility | `vol / 0.03` | realised vol vs that symbol's own trailing 60-day vol (a vol-of-vol ratio) |
| catalyst | days until earnings | days until earnings **weighted by the instrument's historical move on earnings days** |

The volatility one is the most valuable and the cheapest: SONAR already computes
`_daily_vol(closes)` over a window, so the ratio of a short window to a long one
is two lines and turns a constant into a signal. A name whose vol has doubled
against its own baseline is notable; a name that is simply always volatile is not.

The catalyst one is what the sell-side actually means by an earnings signal.
Proximity alone says a date is coming; the expected move says whether the date
matters for *this* instrument.

---

## 6. Fix: stop double-counting correlated components

Two options, in increasing order of effort:

- **Orthogonalize news against momentum.** Regress the news z-score on the
  momentum z-score across the board, keep the residual. What remains is coverage
  that is *not* explained by the price having moved — which is the interesting
  part, and arguably what "news" was always meant to capture.
- **Weight by inverse correlation** rather than by the fixed `_W` constants.

Either makes the stated weights mean what they appear to mean. The current
weights were chosen by judgement, and there is nothing wrong with that — but they
are being applied to overlapping quantities, so the effective weighting is not the
written one.

---

## 7. The political layer, done the way it is done properly

This is the part SONAR is built around, and it is also where the most careless
work in the industry happens. Three things transfer.

### 7.1 Build a daily GPR-style index from the feeds already being read

The Caldara–Iacoviello **Geopolitical Risk index** is the reference measure: it
counts newspaper articles matching threat categories as a *share of total
articles*, across ten major papers, in eight categories — war threats, peace
threats, military buildups, nuclear threats, terror threats, war beginning, war
escalation, terror acts.

Two facts make this directly actionable here:

- The **official index is monthly**, released around the 10th. That is useless for
  a 3–10 day hold. The daily variant exists but has not been reliably maintained.
- **SONAR already reads twenty-four newswires continuously** across nine press
  blocs — including BBC politics, the wire services, Al Jazeera, Global Times and
  TASS — and already parses and timestamps every headline, tagged with its origin
  and whether the outlet is state-directed. That last part matters here: GPR
  counts threat-category articles as a share of total, and knowing which bloc
  each article came from turns one index into one per bloc.

So the honest move is not to download GPR — it is to **compute a GPR-style index
locally, daily, from the feed SONAR already has**, using the published category
structure. Share-of-total-articles is the key normalisation: it is what makes the
measure robust to a feed simply publishing more on a given day, and it is exactly
the level-vs-surprise correction of §5 applied to politics.

This is a genuinely novel capability for an app this size, and it is free.

### 7.2 Political beta, from the prediction market already being read

The institutional way to attach a political event to an instrument is not to
assert a direction. It is to measure sensitivity:

```
Δ return_instrument  =  α + β · Δ price_prediction_market  + ε
```

Run over the window around a live political market, `β` is that instrument's
**political beta** — how much it moves per point of probability shift. SONAR
already reads Polymarket. This gives a per-instrument, per-event exposure number
that is measured rather than asserted, and it degrades gracefully: if β is
indistinguishable from zero, the honest output is "this event does not touch this
instrument", which is a useful thing to be able to say.

### 7.3 Politics is a variance signal, not a direction signal

A scenario framework — which is how banks actually express political risk — says
an election or a ruling widens the distribution of outcomes. It does not say which
tail. That maps cleanly onto SONAR's existing machinery: a wider distribution
means wider barriers, which means a different R:R and a different `P(profit)`,
and the app already computes all three from volatility.

This is the correct home for the political layer, and it requires no directional
claim of any kind.

---

## 8. The redirect with evidence behind it: forecast volatility, not direction

> **Built, 2026-09-17 — `sonar/volatility.py`.** Measured over 26 instruments
> and five years of daily bars, scored by QLIKE against the volatility that
> actually followed. GARCH wins below ten days (+11.6% at 3d, +17.8% at 5d);
> a 250-day trailing window wins above it (+5.6% at 20d); the quarter horizon
> already used one.
>
> **The first answer was wrong, and the control is why we know.** Against the
> incumbent, GARCH scored +24.49% on 26/26 instruments and 6/6 time blocks. On a
> synthetic random walk with *constant* volatility — nothing to cluster on — it
> still "won" by 27%. The confound was sample size: GARCH saw 250 days and the
> incumbent saw 22, because the scan fetched a one-month chart. A plain
> trailing-250 beat GARCH on both synthetic and real data.
>
> What survived is narrower and real: GARCH loses where there is no clustering
> and wins on real data at short horizons, which is the effect actually being
> claimed. Recorded here because the first number was the most impressive result
> this project has produced and it was an artefact.

The five nulls all tested **direction**. Volatility was never the target.

The literature is consistent that news and investor attention predict **realised
volatility** rather than returns: attention measures improve one-day-ahead
volatility forecasts with statistically and economically meaningful gains, the
relationship strengthens around news releases and in stressed markets, and the
same measures fail to predict direction. That is the same shape as SONAR's own
finding — a news spike beat the directional baseline by 0.8 points against a 3.1
error bar — and it points at what the signal was always measuring.

Why this matters more here than it would in most apps: **SONAR already consumes a
volatility forecast structurally.** `scoring.build_plan()` scales the target and
stop by `vol`, which sets `R:R`, which fixes `P(profit) = 1/(1+R:R)`. A better
volatility forecast therefore improves the plan, the sizing and the stated
probability — without claiming a directional edge anywhere.

Concretely: replace the single trailing `_daily_vol(closes)` with a forecast that
blends trailing realised vol, a GARCH-style persistence term (vol clustering is
one of the most robust facts in finance), and the news/attention surprise from
§5. Then test it against realised forward vol using the existing apparatus.

**This is the highest-value item in this document**, because it is the only one
where the target is something the evidence says is predictable *and* the app is
already built to use the answer.

---

## 9. Replace the sentiment word list

`sonar/news.py` uses a hand-written lexicon of roughly seventy general-English
words. The finance-specific problem with general lexicons is well documented:
Loughran and McDonald found that around three quarters of the words flagged
negative by the standard Harvard psychosocial dictionary are not negative in a
financial context — *tax, cost, liability, capital, depreciation* are ordinary
vocabulary in a filing, not bad news.

The **Loughran-McDonald Master Dictionary** is free, maintained at Notre Dame, and
current through 2025. It ships categories for negative, positive, **uncertainty**,
litigious, modal (strong/moderate/weak) and constraining.

For SONAR the interesting column is not positive/negative — the research already
says tone does not predict direction here. It is **uncertainty**, which maps onto
§8: uncertain language is a variance signal, and variance is the thing SONAR can
actually use.

The module docstring's honesty rule stays intact either way: this is still context
and untrusted data, and a better dictionary does not make it a predictor.

---

## 10. How to know whether any of it worked

SONAR already has the apparatus, and it should be used unchanged: pre-registered
hypotheses with expected signs, Newey-West HAC errors for overlapping windows,
Benjamini-Hochberg FDR control, purged and embargoed splits, moving-block
bootstrap intervals, and noise controls that must fail.

Two additions specific to this work:

- **Target realised forward volatility**, not forward return, for anything coming
  out of §5, §7 and §8. Testing a variance signal against a directional target is
  how the last five studies would have missed it even if it were there.
- **Score the confidence score itself with a Brier score and a reliability
  diagram.** If the score is going to carry a number between 0 and 100, the
  question "when it says 70, what happens 70% of the time?" should have an answer.
  `sonar/calibration.py` already grades closed positions; the reliability curve is
  the natural presentation of that and it is the standard tool in forecasting.

---

## 10a. The volatility component, chased and not quite caught

The component attribution in the Lab tab produced the project's first
evidence-backed lead against its own score, and following it properly is worth
recording — including where it stopped.

**The lead.** Volatility carries a weight of 0.15 and a *negative* information
coefficient: ranking instruments up for being volatile ranks them down for
winning. Over 11,373 resolved setups at a 20-day horizon the quintile gradient
is clean and almost monotonic:

| volatility quintile | hit rate |
|---|---|
| Q1 (lowest) | 45.3% |
| Q2 | 47.5% |
| Q3 | 40.9% |
| Q4 | 37.8% |
| Q5 (highest) | **34.5%** |

Against a 40.0% baseline, and a 10.8-point spread end to end.

**It is not an artefact of the tie-break.** `_resolve` scores a bar that spans
both barriers as a loss, and wider daily ranges mean more such bars — so a
high-volatility instrument could be marked down by the rule rather than by the
market. Measured directly: **zero ambiguous bars in any quintile.** The barriers
are scaled to volatility and sit roughly 4.5 vol-days apart at this horizon, so a
single bar spanning both essentially never happens. The hypothesis is dead and
the effect is real.

**It holds cross-sectionally.** Twelve configurations across five asset classes
and two horizons: the IC is negative in ten, significantly inverted in five, and
leave-one-out says removing the component *raises* the blend's IC in ten. Only
forex leans the other way, and only at the longer horizon.

**It does not clear the time-block test**, which is the one that has killed
every previous lead in this project:

| period | low-vol | high-vol | spread |
|---|---|---|---|
| 2021-10 → 2022-08 | 46.2% | 29.8% | +16.4 |
| 2022-08 → 2023-06 | 47.5% | 28.8% | +18.7 |
| 2023-06 → 2024-03 | 44.9% | 42.0% | +2.9 |
| 2024-03 → 2024-12 | 40.1% | 31.9% | +8.2 |
| 2024-12 → 2025-10 | 60.7% | 34.3% | +26.4 |
| 2025-10 → 2026-08 | 33.5% | 42.5% | **−9.0** |

Five of six agree, which is a sign-test p of **0.22** — nowhere near the bar, and
the most recent period reverses outright. `dist_52w_high` died on exactly this
test after looking stronger in aggregate.

**So the weights are unchanged.** The lead is real, large, consistent with the
well-documented low-volatility anomaly, and still one regime away from being a
finding. Six blocks cannot separate "a real effect that recently paused" from
"an effect that was always regime-dependent", and guessing between those is how
the +4.9 attention claim got published and withdrawn.

### The part that is a conclusion

Chasing it surfaced something the arithmetic cannot settle: **the score is being
asked to do two jobs that point opposite ways here.**

* As a **notability** heuristic — its stated and only claimed job — high
  volatility belongs with a positive weight. Something *is* happening to a
  moving instrument, and that is what the number says.
* As a **ranking that sorts winners**, which the app explicitly disclaims, the
  same component is backwards.

"INVERTED" is therefore only a defect under a job the score does not claim. That
is not a reason to ignore it — it is the choice, stated plainly, and it belongs
to whoever owns the product rather than to the arithmetic. Flipping the sign
would buy a better ranking and cost the thing the score honestly measures.

## 10b. The three structural fixes, pre-registered and measured

§3, §4 and §5 proposed fixes on the grounds that they were structurally right
rather than that they would predict. Three hypotheses were written down with
their failure conditions **before** anything was measured, and then measured over
11,123 resolved setups at a 20-day horizon.

| # | Hypothesis | Predicted | Measured | Verdict |
|---|---|---|---|---|
| H1 | volatility as a surprise (`vol₁₀/vol₆₀`) rather than a level | IC moves toward zero | −0.0885 → **−0.0337** | supported on aggregate |
| H2 | momentum residualised against its asset class | \|IC\| **rises** | 0.0237 → **0.0097** | **failed** — it fell |
| H3 | components z-scored within asset class | blend IC improves | −0.0553 → **−0.0242** | supported on aggregate |

**H2 failed on the criterion I set for it.** The prediction was that stripping
the class move would leave a *more* informative residual. It left a less
informative one. Benchmark-relative momentum is standard practice everywhere in
the industry and it did not transfer here, and the pre-registration is why that
is reportable rather than quietly dropped.

**H3 subsumes H1.** Z-scoring within class already removes the asset-class
artefact that the surprise ratio was invented to remove — the shipped
`min(1, vol/0.03)` is close to a dummy for "is this crypto", and standardising
against peers fixes that directly. Combining both is *worse* than H3 alone
(−0.0337 against −0.0242), which is what redundant corrections look like.

### None of them clears the consistency bar

Across six non-overlapping periods, every one of them lands at **5 of 6, sign
test p = 0.22** — the identical bar that killed `dist_52w_high` and the inverted
volatility result. That is now four candidates that looked strong in aggregate
and could not hold across regimes.

There is one thing in the block table that is not about prediction. The shipped
blend swings from −0.153 to +0.070 across those periods; the z-scored blend
stays between −0.094 and +0.012. **A range of 0.22 versus 0.11** — the
standardised score is markedly more stable regime to regime, whatever its mean.
Stability is a different claim from predictive power, and it is the one a
notability score should probably be judged on.

### The blocker that decides it

H3 is structurally right regardless of any IC: a score that reads 0.9 for a coin
and 0.1 for a currency pair *because of what they are* is not comparable across
the board, and comparability is the whole point of a ranking. But it cannot be
implemented as specified on this watchlist:

```
Crypto 11 · Equity 7 · Index 3 · Forex 3 · Commodity 2
```

A median and MAD over **two** instruments is not a standardisation, it is noise
with a z in front of it. Three of five classes have three or fewer members. So
the honest options are to standardise against the whole board rather than the
class — which reintroduces exactly the asset-class contamination the fix was for
— or to grow the watchlist until the classes can carry it.

Nothing was shipped. The score is unchanged.

## 11. What not to do

- **Do not add more features to daily bars and re-run the same study.** That is
  explicitly the conclusion of the existing research, and five nulls is evidence
  about the data, not about the feature list.
- **Do not tune the weights until the score looks good.** The calibration loop
  exists so that outcomes move the score; a weight search against historical
  returns is the same overfitting the pre-registration was built to prevent.
- **Do not let the LLM touch the score.** `sonar/llm.py` already argues this at
  length: a calibrated number and a fluent one must not be averaged, because
  afterwards you can never tell which you are looking at.
- **Do not report a score improvement as an edge.** A better-constructed
  notability ranker is a better notability ranker. The directional claim stays
  dead until something measured revives it.

---

## 12. Ranked

| # | Change | Effort | Evidence behind it | Needs new data? |
|---|---|---|---|---|
| 1 | **Volatility forecast instead of trailing vol** (§8) | M | Strong — attention→vol is well replicated | No |
| 2 | **Levels → surprises** (§5) | S | Strong — surprise-vs-level is the core of event studies | No |
| 3 | **Cross-sectional z-scoring within asset class** (§3) | S | Structural; fixes a defect visible in the arithmetic | No |
| 4 | **Local daily GPR-style political index** (§7.1) | M | GPR methodology is published and validated | No — uses the existing feed |
| 5 | **Benchmark-relative momentum** (§4) | S | Standard practice; residualization is step 3 everywhere | No |
| 6 | **Loughran-McDonald uncertainty** (§9) | S | Strong for the lexicon claim; uncertainty→vol is §8 | One CSV |
| 7 | **Orthogonalize news against momentum** (§6) | M | Standard practice | No |
| 8 | **Political beta from Polymarket** (§7.2) | M | Sound method; unproven at this scale | No |
| 9 | **Brier score + reliability diagram** (§10) | S | Standard forecasting practice | No |

Items 2, 3 and 5 are each a handful of lines, need nothing new, and make the score
mean what it claims to mean. They are the place to start, and none of them
requires believing an edge exists.

Item 1 is the one worth doing properly, because it is the only target on this list
that the evidence says is predictable and that the app is already built to consume.

---

## Sources

- [Measuring Geopolitical Risk — Caldara & Iacoviello (Federal Reserve IFDP 1222)](https://www.federalreserve.gov/econres/ifdp/files/ifdp1222.pdf)
- [Geopolitical Risk (GPR) Index — data and methodology](https://www.matteoiacoviello.com/gpr.htm)
- [Loughran-McDonald Master Dictionary — Notre Dame SRAF](https://sraf.nd.edu/loughranmcdonald-master-dictionary/)
- [The Barra US Equity Model (USE4) Methodology Notes](https://www.top1000funds.com/wp-content/uploads/2011/09/USE4_Methodology_Notes_August_2011.pdf)
- [MSCI Core Multiple-Factor Indexes Methodology](https://www.msci.com/documents/10199/ecc2cfae-0766-fa4f-8ce5-0fc3028272f3)
- [Forecasting U.S. equity market volatility with attention and sentiment to the economy](https://arxiv.org/pdf/2503.19767)
- [When does attention matter? Investor attention and volatility around news releases](https://www.sciencedirect.com/science/article/pii/S1057521922001466)
- [Realised Volatility Forecasting: Machine Learning via Financial Word Embedding](https://arxiv.org/pdf/2108.00480)
