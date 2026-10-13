# Industry techniques for SONAR: ranked shortlist

Date: 2026-10-13. Status: **advice for the owner, nothing approved or built.**
Author: Claude (research workflow `wf_678365b8-3f4` plus a read of this repo).

## How much to trust this

The research workflow could not read most sources. The environment's network policy rejected
arxiv.org, nber.org, papers.ssrn.com, ideas.repec.org, sciencedirect.com, huggingface.co and
others, so 23 of 24 fetch agents returned nothing and only 3 claims reached verification.
Every item below carries one of these tags:

- **[V]** verified 3-0 by independent agents against the primary source. Only the three
  volatility claims from one GitHub repo reach this tier, and that repo is unreviewed.
- **[S]** from a search-result snippet. The source page was not fetched, and its numbers were
  not checked.
- **[K]** from Claude's background knowledge, not checked this session.

Nothing here is an edge claim. Anything tagged [S] or [K] should be read at source before it
drives a design.

## What SONAR already has (so none of this is proposed twice)

Stdlib-only code. Wilson intervals (`sonar/calibration.py`), Benjamini-Hochberg, Newey-West and
bootstrap intervals (`sonar/research/stats.py`), a pre-registered hourly volatility study with
QLIKE, walk-forward and a constant-volatility control (`sonar/research/hourlyvol.py`), and
hour-of-day seasonality. **Not present:** any day-of-week term, deflated Sharpe, probability of
backtest overfitting, reliability diagrams with bands, conformal intervals.

## Timing constraint

The headless agent is on a 30-day clean run from 2026-10-10 to 2026-11-09
(`docs/specs/v1-product.md`). Restarting it on a new build disturbs that run. So:

- Items 1 and 3 may be built now as offline research code, with nothing wired into the engine.
- Putting a winning item 1 term into the live forecast waits until after 2026-11-09.
- Item 4 changes score history, so it also waits until after 2026-11-09.
- Item 2 is app-side only and does not need an agent restart.

## Ranked shortlist

### Do: study first, ship only if it wins

**1. Weekend / hour-of-week term in the hourly BTC volatility forecast.**
Sigma is the only quantity the hourly model disagrees with the market about, so it is the
highest-leverage input.
- Evidence: a weekend dummy cut QLIKE about 15% and per-weekday dummies about 22% on BTC daily
  variance, DM p < 0.001 [V]. One unreviewed repo, daily horizon, 5-minute data, no EWMA
  comparator. A 2025 peer-reviewed paper supports adjusting for intraday periodicity, on
  equities [S].
- Fit: no new data, no edge claim, pass or fail decided by the existing study harness.
- Effort: small. Extend `_Diurnal` to 168 hour-of-week buckets or add a weekend factor, then
  pre-register and run the existing walk-forward and control.

**2. Show calibration with uncertainty, not a single number.**
- Evidence: isotonic (CORP) reliability diagrams with resampling bands [S]. Binned expected
  calibration error is biased in either direction depending on bin count and sample size, so avoid
  a single ECE headline [S].
- Fit: strong. This is the roadmap's "calibration published with intervals".
- Effort: small to medium. User-visible, so it needs the Define and Design gates.

**3. A trial ledger plus deflated Sharpe and probability of backtest overfitting.**
- Evidence: Bailey and Lopez de Prado, 2014 and 2015 [S]. Harvey-Liu-Zhu argue new factors need
  t > 3 [S], and Chen (2021) argues that is too strict [S]. State the test-family size either way.
- Fit: internal tooling, no UI, no new data. SONAR has Benjamini-Hochberg but not these.
- Effort: small. Stdlib maths with known-answer tests.

**4. Fix the notability score's structural defects** (robust cross-sectional z-scores, momentum
relative to peers, surprise instead of level). Already ranked in `CONFIDENCE.md` sections 1 to 4.
This research neither adds to nor weakens that case. Biggest effort, and the score history
will break, so it needs the Architect gate and `model-validator`.

### Lab experiments: small, pre-registered, may show nothing

**5. Adaptive conformal intervals around the volatility and P(up) forecasts.** Gibbs and Candes
2021 [S]. The guarantee is long-run average coverage, not conditional coverage.

**6. Polymarket order-book imbalance against the hourly market price.** Evidence is thin. One 2026
paper reports public-feed trade direction matches on-chain records only about 59% of the time
[S, unverified]. First check that SONAR logs order-book snapshots at all (not verified).

**7. Simple-average combination of the current forecast with a HAR-style one.** Only after 1.

### Skip

- **ML or deep learning to predict returns or direction.** Nagel (2025) argues the "virtue of
  complexity" results reduce to recency or momentum [S]. SONAR's own five null studies found no
  momentum edge. A model needs a heavy dependency in a stdlib-only app, and the score must stay
  explainable to users without finance training.
- **ML for volatility.** XGBoost and LSTM were not significantly better than linear HAR given
  the same inputs: DM p = 0.73 and 0.57 against the richer linear model [V]. The headline 16%
  gain was p = 0.161.
- **LLM sentiment inside the score.** Look-ahead contamination inflates backtests (Glasserman
  and Lin, 2023) [S]. Keep the LLM read as labelled commentary, as now.
- **Volatility targeting as a return booster.** Real-time out-of-sample versions generally
  underperform the unmanaged strategies (Cederburg et al., 2020) [S], and gains vanish after
  costs outside the market factor (Barroso and Detzel, 2021) [S].
- **Kelly sizing.** With no edge the Kelly stake is zero [K]. Playmaker already returns a zero
  stake for narrative probabilities.
- **Replicating Medallion, Axcom or similar.** The workflow verified nothing on firm
  disclosures, and no algorithm is public.

## Not researched, no evidence either way

Transaction-cost and slippage modelling, risk parity, drawdown control, and what Two Sigma, AQR
or DE Shaw have disclosed. The sources were blocked.

## Sources (all [S] unless marked)

- Volatility repo [V]: https://github.com/ayoubguenbib/btc-volatility-forecasting
- Dumitru, Hizmeri, Izzeldin 2025: https://ideas.repec.org/a/eee/jbfina/v170y2025ics0378426624002565.html
- CORP reliability diagrams: https://arxiv.org/abs/2008.03033v1
- ECE bias: https://arxiv.org/pdf/2012.08668
- Adaptive conformal inference: https://arxiv.org/abs/2106.00170v3
- Deflated Sharpe: https://papers.ssrn.com/abstract=2460551 ; backtest overfitting: https://papers.ssrn.com/abstract=2326253
- Harvey, Liu, Zhu: https://nber.org/papers/w20592 ; Jensen, Kelly, Pedersen: https://www.nber.org/papers/w28432
- McLean and Pontiff: https://Www.Gwern.net/doc/economics/2016-mclean.pdf
- Nagel 2025: https://www.nber.org/papers/w34104
- Glasserman and Lin 2023: https://arxiv.org/pdf/2309.17322
- Polymarket microstructure 2026: https://arxiv.org/pdf/2604.24366
- Volatility-managed portfolios: https://ideas.repec.org:443/a/eee/jfinec/v138y2020i1p95-117.html
