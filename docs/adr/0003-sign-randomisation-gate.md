# 0003. A direction-randomisation gate on the backtest verdict and the attribution grades

- Status: accepted with changes (owner, Build gate, 2026-10-12). Revised by the architect the same day to match: the cluster is a 4-horizon block across all classes.
- Date: 2026-10-12

## Context

- **Headline.** The verdict ("beats" or "below the prediction") fires when Δ lies outside a date-clustered Driscoll–Kraay (DK) error bar. A meaningless direction, one coin per (asset class, h-day block), gets a verdict on 11.1–11.4% of judged real-bar runs, against a 5% target (validator r5, r6 and Architect review). It reaches 18% at some settings.
- **Attribution.** The grades (KEEP/INVERTED) run at 5–7% on clustered placebos. The component IC's DK lag was never justified (QA r6 P2-1).
- **Constraints.** stdlib only; deterministic per run.

Three choices are expensive to reverse:
- **The replay contract.** Every decision also resolves the opposite direction.
- **The cluster definition.** It decides which meaningless directions the app holds size against, and every published rate is tied to it.
- **The verdict states.** A new state reaches users, the docs and CONFIDENCE.md.

The first proposal clustered by (class, 4-horizon block). The validator showed that it does not control a meaningless direction shared across classes: market-wide coins gated 8.2% and 21.9% at full scale. The owner chose option (a): cluster across all classes. Numbers are in the spec's Architecture §9 and in `docs/audit/sign-randomisation-verdicts-model-validator.md`.

## Decision

1. **Direction randomisation as an extra gate.**
   - A verdict needs today's DK rule **and** `p_tail < 0.05`. Under the randomisation, each cluster's directions are swapped for the opposite forced direction.
   - The statistic is the cluster-robust t of the gap (win − predicted), recomputed under each pattern (RI-t). n changes with timeouts, and nothing assumes LONG and SHORT outcomes mirror each other.
   - The p-value is equal-tailed, and the gate is on the tail of Δ's sign; "beats" is a one-sided 2.5% test.
   - The gate can only remove.
2. **Clusters.** A cluster is one block of `MAX_HOLD_MULTIPLE × ceil(h·365/252)` calendar days **across every asset class**.
   - Edges are anchored at Unix day 0, and each setup is assigned by its UTC entry date.
   - Holds that spill over stay in their entry block.
3. **Inference.** Enumerate all 2^q patterns when q ≤ 12; under this unit that is the usual path. Otherwise use Monte Carlo with B = 11,999.
   - The seed is the sha256 of the run's sorted content (which includes the observed directions), drawn from a local `random.Random`. Sums use `math.fsum`.
   - **q < 8 is withheld** (`"few_clusters"`). The copy names the fix: a longer range or a shorter horizon.
4. **Verdict states.** `verdict_state` takes `within`, `unconfirmed`, `beats` or `below`.
   - `unconfirmed` is internal. Users read "not told apart from chance", in grey, never "within".
   - No passing string says "confirmed" or "verified".
   - The expert view shows `p_tail`, labelled "in the direction of Δ".
5. **Attribution.** A sign change of per-cluster centred IC products, on the **same all-class blocks**, with the Canay–Romano–Shaikh t and BH at 0.10.
   - A component that passes today's rule but not the randomisation reads `UNCONFIRMED`, worded "not told apart from chance".
   - The quintile spread keeps DK.
   - "Ranks backwards" also needs p ≤ `normal_p(Z_CLAIM)`, which is attainable only at q ≥ 10.
   - The IC lag stays at 1×.
6. **Boundary.**
   - The statistics live in a new pure-stdlib `sonar/randomisation.py`.
   - `backtest.py` owns blocks, states and copy.
   - `run_symbol` adds `opp_outcome`, `opp_bars_held` and `opp_predicted`.
   - `range_for_horizon` picks a range that yields q ≥ 8 for the Terminal: 2y for h ≤ 10, 5y for h ≤ 30, 10y for h ≤ 80. This is assumption A15, pending an owner nod.

## Validity, stated narrowly

**Exact for nested directions.** The test is exact in finite samples for a meaningless direction whose random draws are nested inside its clusters, whatever the 1.5:1 asymmetry, the change in n or the class sizes. Nested covers:
- one draw per setup;
- one per (class, h-block) or per (class, 4 h-block);
- one market-wide draw per h-block or per 4 h-block, on the same anchor.

**No guarantee otherwise.** There is none for directions that are not nested:
- shifted edges;
- blocks longer than 4 horizons;
- real momentum's persistence across blocks.

Their size is an empirical property, checked by pass/fail placebos (measure 2: 2× blocks, shifted edges, per-class 4 h and 8 h coins, market-wide h and 4 h coins). No asymptotic claim is made.

## Alternatives considered

- **(class, block) clusters** (the first proposal). They do not control directions shared across classes (8.2% and 21.9%). More clusters and fewer withheld runs did not outweigh that.
- **Keeping (class, block) and narrowing the copy** (validator option (b)). The owner declined it.
- **Blocks of h, 2 h or 3 h.** They fail the 2× and 4 h placebos (10.4–18.0%). 4 horizons is the longest hold, so a hold never reaches past the next block.
- **A sign flip of gap sums against the baseline.** It does not centre on the gap both directions share, so it cannot remove "every direction reads below".
- **A sign flip of the paired difference.** It changes the question, and a timeout on one side leaves the difference undefined.
- **A direction swap for attribution.** It would remove real effects that do not depend on direction.
- **Dropping setups that cross an edge.** It changes the sample.
- **Webb weights.** Enumeration already gives exact p at q 8–12. They stay on the watch list.
- **Curtailed Monte Carlo; numpy, scipy or `arch`.** Not needed, and stdlib only.
- **Scaling the bar by a factor.** A non-goal.

## Consequences

- **The false rate holds only for named placebos.** The app holds a measured false rate for named meaningless directions: nested ones, by theorem, and the measure-2 placebos, by measurement. Slower or un-nested patterns are a stated residual, not a guarantee. The copy quotes the **worst held-out figure** across measures 1–2 with its scope, never a pre-filled "1 in 20".
- **Fewer judged runs.**
  - 37% of today's judged settings (19-horizon grid; 50% on the validator's 41-horizon grid) become withheld for too few stretches, mostly at long horizons.
  - The Lab default (2y h5, q 22) stays judged.
  - Without A15, the Terminal's 20-day and 60-day lines are withheld.
- **Power** where judged is almost unchanged: 32 → 31 of 40 at the Lab default.
- **Not covered: traits fixed per instrument** (volatility). The copy, the Learn tab and CONFIDENCE.md say so.
  - Under this unit the real volatility INVERTED at 1y h5 no longer survives (randomisation p 0.047 fails BH).
  - At 5y h5 it does (p 0.0085).
- **Harder.**
  - A third headline state and a new component verdict need copy and colour.
  - The replay costs about twice the CPU: under 1 s at the Lab default, in `BacktestThread`. The headless agent never runs the backtest.
  - Test helpers that force `build_plan` must attach the opposite outcomes.
  - Synthetic rate tests must use horizons where q ≥ 8 on their worlds (h15 on 504 bars).
- **Migration: none.** No backtest summary is persisted. UI readers fall back to `significant`.
- **Monitor.**
  - Measure 9: the restated rate and rule everywhere they appear.
  - The held-out confirmation on a set independent in time or instruments, frozen with its own manifest.
- **Reversal.**
  - Code: remove the conjunct, and the verdicts revert to today's.
  - The published rates and the third-state copy would have to be restated.
  - The opposite fields can stay.
