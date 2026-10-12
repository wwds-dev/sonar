# 0003. A direction-randomisation gate on the backtest verdict and the attribution grades

- Status: proposed (architect, 2026-10-12). Waiting on the owner gate for `docs/specs/sign-randomisation-verdicts.md`.
- Date: 2026-10-12

## Context

- **Headline.** The verdict ("beats" or "below the prediction") fires when Δ lies outside a date-clustered Driscoll–Kraay (DK) error bar. A meaningless direction, one coin per (asset class, h-day block), still gets a verdict on 11.4% of judged real-bar runs (validator r5/r6), against a 5% target. The rate reaches 18% at some settings.
- **Attribution.** The grades (KEEP/INVERTED) run at 5–7% on clustered placebos. The component IC's DK lag was never justified (QA r6 P2-1, mutant E4).
- **Constraints.** stdlib only; deterministic per run; reversible copy.

Three choices here are expensive to reverse:
- **The replay contract.** Every decision now also resolves the opposite direction.
- **The cluster definition.** The block length decides which placebos the app holds size against. Every published rate is tied to it.
- **The verdict states.** A new state, "outside the bar, not confirmed", reaches users, the docs and CONFIDENCE.md.

The prototype and every number are in the spec's Architecture section (§9).

## Decision

1. **Direction randomisation, as an extra gate.**
   - A verdict needs today's DK rule **and** a randomisation p below 0.05 on the tail of Δ's sign. Under the randomisation, each (class, block) cluster's directions are swapped for the opposite forced direction.
   - The statistic is the cluster-robust t of the gap (win − predicted), recomputed under each pattern (RI-t). n changes when a swap turns a timeout into a resolved setup, and nothing assumes LONG and SHORT outcomes mirror each other.
   - The p-value is equal-tailed; "beats" is a one-sided 2.5% test.
   - The gate can only remove verdicts.
2. **Clusters.** A cluster is (asset class, block of `MAX_HOLD_MULTIPLE × ceil(h·365/252)` calendar days). Edges are anchored at Unix day 0, and each setup is assigned by its UTC entry date.
   - The block is four whole horizon-blocks: as long as the longest hold, and nested over the measure-1 placebo's blocks.
   - Holds that spill over stay in their entry block.
3. **Inference.** Enumerate all 2^q patterns when q ≤ 12; otherwise use Monte Carlo with B = 11,999 (Monte Carlo se 0.002 at p = 0.05) and p = (1+#)/(1+B).
   - The seed is the sha256 of the run's sorted content, drawn from a local `random.Random`. Sums use `math.fsum`.
   - A run with q < 8 is withheld (`"few_clusters"`).
4. **Three outcomes for a judged run.** `verdict_state` takes the values `within`, `unconfirmed`, `beats` or `below`. `unconfirmed` (outside the bar, not confirmed) has its own copy and a grey colour, and it never reads as "within". `significant` keeps its meaning.
5. **Attribution.** A component is not a direction, so attribution uses a sign change of per-cluster centred IC products, with the Canay–Romano–Shaikh t, the same clusters and B, and BH at q = 0.10.
   - A component that passes today's rule but fails the randomisation reads **UNCONFIRMED** (grey), never "survives FDR".
   - The quintile spread keeps its DK bar.
   - "Ranks backwards" also needs p ≤ `normal_p(Z_CLAIM)`.
   - The IC lag stays at 1×, documented as a first-stage filter.
6. **Boundary.** The statistics live in a new pure-stdlib `sonar/randomisation.py` that works on sufficient statistics. `backtest.py` owns clusters, states and copy. `run_symbol` adds `opp_outcome`, `opp_bars_held` and `opp_predicted` per row.

## Alternatives considered

- **h-long blocks** (the placebo's own block). They pass the matching placebo (4.0%) and fail the placebos with 2× blocks (10.4%) and 4 h blocks (18.0%). That is the circular pass the spec warned about.
- **2 h or 3 h blocks.** The 4 h placebo reads 12.0% and 10.8%. At 4 h every measured placebo is 2.8–6.0%, at almost no power cost (Lab default: 32/40 both ways).
- **Replacing DK with the randomisation** (spec open question 1). It is statistically viable: at 4 h the gate alone matches the composition. It was not chosen by default because it puts new numbers and copy on screen. This ADR becomes "replace" by dropping step 1's DK conjunct and retiring the IC lag. The fields and module stay.
- **A sign flip of per-cluster gap sums against the baseline.** That is the same question as DK with another clustering. It does not centre on the gap both directions share, so it cannot remove "every direction reads below". The direction randomisation removes most of it: independent coin 6.8% → 2.8%.
- **A sign flip of the paired difference (chosen − opposite).** It changes the question to "beats its mirror", and a timeout on one side leaves the difference undefined.
- **A direction swap for attribution.** It would remove real effects that do not depend on direction (volatility helping either side).
- **Dropping setups that cross an edge.** It changes the headline sample.
- **Webb six-point weights.** q ≥ 16 on judged settings, so they are not needed; they stay on the watch list.
- **Curtailed Monte Carlo.** The cost does not need it, and the reported p would depend on the stopping point.
- **numpy, scipy or `arch`.** stdlib only.
- **Scaling the bar by a factor.** A non-goal: it leaves the per-setting spread in place.

## Consequences

- **Measured on the prototype** (r5 bars, 250 judged runs per design, 0% withheld):
  - the clustered coin goes from 12.4% to 6.0% [3.7–9.7]; the gate alone is exact at 5.1% on 800 coins;
  - the robustness placebos go from 7.6–23.2% to 3.2–5.2%;
  - attribution placebos read 2.5% at every IC lag;
  - power is unchanged at the Lab default, with a loss of 1–5 of 40 at 5y h60.

  The spec's full-scale measures are the validator's to run.
- **Easier.** The copy can state a false rate that the test is built to hold. The IC lag question is settled. The acceptance tests become pre-registered rate tests that fail on today's code (headline: today 12–13% on long synthetic horizons, bound 31/400).
- **Harder.**
  - A third headline state and a new component verdict need copy, colour and plain-mode words.
  - The replay costs about twice the CPU. Measured: under 1 s extra at the Lab default and about 3–4 s at 10y h1, all in `BacktestThread`. The headless agent never runs the backtest.
  - Test helpers that force `build_plan` to one side must attach the opposite outcomes, or every flip becomes a no-op.
- **Residual risk, stated.**
  - A meaningless direction that persists per class for longer than 4 horizons is not guarded (the circularity moves; it does not vanish).
  - Persistent per-symbol components are not helped. The real volatility INVERTED grades very likely survive the gate (randomisation p 0.032 and 0.007). Two-way clustering stays on the watch list.
  - A Python upgrade could change the `randbytes` stream. A golden-value test catches it, and p would move only within Monte Carlo error.
- **Migration: none.** No backtest summary is persisted: `_lab_result` lives in memory, and `research_results/*.json` are separate studies that no code reads. UI readers fall back to `significant` when `verdict_state` is absent.
- **Must be monitored.** Measure 9 (copy follows the number): the restated false rate in `_verdict`, `static/docs.html`, `CONFIDENCE.md` and the honest-baselines spec, in the same release.
- **Reversal.**
  - Code: remove the conjunct, and the verdicts revert to today's.
  - Published rates and the third-state copy would have to be restated again.
  - The opposite-direction fields are harmless to leave in place.
