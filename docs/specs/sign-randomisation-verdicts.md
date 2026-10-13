# Spec: sign-randomisation p-value for the backtest verdict and the attribution grades

- Status: Build approved by the owner (2026-10-12). The method needs owner sign-off (TODO.md, "After QA-11 / QA-13"). Revised the same day for the domain-finance Define review (`docs/audit/sign-randomisation-verdicts-domain-finance.md`: P1-1, P1-2, P2-1 to P2-7, P3-1 to P3-4) and aligned with the Architecture section and ADR 0003.
- **Owner decisions at the Build gate (2026-10-12)**, after the domain-finance Architect pass and the model-validator review (`docs/audit/sign-randomisation-verdicts-model-validator.md`):
  - **Cluster unit = 4-horizon block across ALL classes** (validator P1-1 option (a)), not (class, block). Cells with q < 8 are withheld; the validator expects this to cover about half of today's judged cells, mostly long horizons.
  - **DROP deferred** (open question 7 (a)): out of this change; a P3 backlog item and a CHANGELOG line saying DROP is uncalibrated.
  - **Build approved** on architect assumptions A1–A14 as amended. The expert view shows `p_tail` (labelled "in the direction of Δ"). User copy says "not told apart from chance", never the bare word "unconfirmed". The volatility / per-instrument-trait residual is disclosed in copy and CONFIDENCE.md.
  - **A15 approved (2026-10-12):** `range_for_horizon` picks 2y for h ≤ 10, 5y for h ≤ 30 and 10y for h ≤ 80, so that the Terminal's 20d and 60d lines are judged rather than always withheld.
  - **Owner decisions after validator r7 (2026-10-12, `docs/audit/sign-randomisation-verdicts-model-validator-r7.md`):**
    - **Measure 2 (P1-1): accept and disclose.** The 4h blocks stay. Copy quotes the worst held-out rate for random directions held up to *eight* holding periods, says the rate is per run, and notes that one setting band reads about 1 in 5. Measure 2's 7.5% bar is recorded as not met and disclosed, not re-architected.
    - **Drift (P1-2): withhold 10y and disclose.** A15 is amended: 2y for h ≤ 10, 5y for h ≤ 30, and no 10y. The Terminal's 60d line shows numbers without a verdict. All headline copy names the residual that a direction fixed per instrument (such as always long on today's list) can beat the bar.
    - **Lab 10y (2026-10-12, domain pass 4 P2-1):** the Lab withholds 10y as well. A 10y run shows its numbers with no verdict and a drift/survivorship reason, and the Lab's few_clusters tip no longer points at longer ranges.
    - **After fix-loop-2 review (2026-10-12):**
      - The Lab tip keeps "a longer range up to five years", with the clause dropped on runs already at 5y. This amends the Lab 10y bullet.
      - Measure 8 is accepted as "≤ 0.88 (sets share worlds)".
      - The 600 s suite budget is approved.
      - The Lab shows the Terminal's survivorship line on every result, in both modes.
    - **Rate figure: any verdict.** `CHANCE_VERDICT_RATE` = "about 1 run in 10" (9.11% [7.6–10.9], 1,152 judged held-out runs, 53% withheld; held-out manifest `404f5a77…`), worded "got a verdict either way".
    - **Measure 5:** the bar is reset from the curve to ≥ 28/40 at Δ ≈ +3 pts per-setup (measured 30/40). The curve is published. User power copy quotes only the clustered figure or says nothing.
  - **Required fixes, no further decision needed:**
    - The 8h and market-wide coins become pass/fail placebos (validator P2-1).
    - Validity text says the test is exact only for directions nested in its clusters, and the asymptotic claim is deleted (P2-2).
    - Attribution persistent-design size: n ≥ 480 per design, and the lag wording is qualified (P2-3).
    - The held-out set is truly independent: a fresh window or held-out symbols with its own manifest (P2-4).
    - Rate-test fixes (P2-5).
    - The rate copy quotes the worst held-out figure with its scope, never a pre-filled "1 in 20" (domain P1-A).
    - Domain pass-2 P2/P3 items.
- Priority: **P2**. Real momentum gets no headline verdict today (0 of 102 judged real-bar runs; validator r5 (b)), so no user sees a false headline verdict now. What users do see: attribution grades that fall inside the placebo false rate (volatility INVERTED at 1y and 5y h5; validator r6 (c)), and Learn-tab copy that admits "about 1 run in 10".
- Source: validator r5 (a) and P2-C, validator r6 (a), (d) and (e), QA r6 P2-1 (mutant E4), radar note `docs/company/radar-notes/2026-10-12-feature-sign-randomisation.md`, spec `qa11-qa13-honest-baselines.md` (owner decisions of round 5 and the polish after round 6).
- Playbook `docs/playbooks/product-manager.md` is `status: baseline` (stale by AGENTS.md). The owner chose to continue on it.

## Problem

The backtest says a direction "beats" or is "below" the prediction when Δ is outside the error bar. A placebo shows how often that happens by chance. The placebo picks one random direction per (asset class, ~h-day block): it moves together the way momentum does and carries no information. Even with the date-clustered (Driscoll–Kraay) bar, it gets a verdict on **11.37% [10.1–12.8]** of 2,040 judged real-bar runs. The target is 5% (validator r6 (d)). The rate varies by setting: **18.3%** at 2y h30–59 and **17.9%** at 5y h90–120 (r6 (e)). One reason: across seeds Δ spreads about 1.11× the shown se (up to 1.7× at long horizons), because DK runs thin when there are few long blocks (r5 (a)).

The attribution panel has the same problem. A meaningless component that holds one value per (class, block) is graded KEEP or INVERTED on **7.1% [4.5–11.0]** of runs. A meaningless component that stays fixed per symbol is graded on **4.6% [2.6–8.0]** (r6 (a)). The component IC runs at 1.4–1.5× its nominal variance. Over 96 QA runs it was graded 8.3% of the time, with a mean IC z² of 2.23 (QA r6 P2-1). Its DK lag (one average hold) does not bind on some seeds. Halving that lag survived the suite (mutant E4; now pinned by a test, but the lag itself was never justified).

The two acceptance tests are regression guards fitted to their seeds. `test_a_correlated_coin_rarely_gets_a_verdict` allows 7 of 60 runs. That equals the 99th percentile of Binomial(60, 5%), so the test cannot tell 5% from 11%. `test_a_meaningless_clustered_component_is_rarely_graded` fails on 2 of 3 other seed sets (QA r6 P2-1).

**Who is hurt:** a retail reader without finance training who reads "beats", KEEP or INVERTED as a calibrated finding. The copy hedges ("about 1 run in 10", "a reason to look closer, not a finding"). The fix is still a test whose false rate matches what the copy says.

## User and goal

**User:** Lab readers (plain and expert mode) and the Terminal's backtest line. **User question this answers:** "If SONAR says this direction beat the prediction, or that this component ranks winners, how often would a meaningless direction or component have read the same?"

**Goal, as measured:**
- **Size:** a verdict or a KEEP/INVERTED grade fires on ≤ 5% of meaningless clustered placebos on frozen real bars, confirmed on a held-out set (measures 1–3).
- **Power:** an injected per-setup edge of about +3 pts of hit rate, before costs, at the Lab default (2y h5) gets a verdict on **≥ 80% of 40 seeds** (measure 5). The clustered-edge power curve is published next to it. It is not a pass/fail bar, and any power copy quotes it or nothing.
- **Honest states:** a run outside the bar that the gate does not confirm shows a third, grey state, never "within" (measure 11).
- **Copy:** every description of the rule and the rate states the measured, per-run figure (measure 9).

## Success measures

Every rate below is measured by `model-validator`. The bars are a frozen real-bar set: the r5 live bars, or a fresh fetch saved to a scratchpad with a sha manifest. **Never `~/Library/Application Support/SONAR`.** Unless stated otherwise: step 3, 1y/2y/5y/10y × horizons 1–120, whole watchlist, judged runs only (`withheld is None`). Intervals: Wilson, plus a cluster bootstrap over (range, horizon) cells. **Every rate measure reports the withheld share as an output, next to its judged-only rate** (overall, and the `few_clusters` share separately).

**Expected loss of coverage (accepted at the Build gate).** The all-class 4-horizon unit withholds any run with q < 8. Of the 62 settings judged today, **23 (37%) become withheld** (51 of 102 cells on the validator's 41-horizon grid), mostly long horizons: judged up to 1y h7, 2y h15, 5y h40, 10y h90 (Architecture §3). **The Lab default 2y h5 stays judged at q 22.** A falling verdict count caused by withholding is not a size gain: the withheld share is what separates the two.

**Frozen, then held out.** The block definition (Architecture [A6]) is frozen on the r5 set before the full-scale run. Measures 1–3 are then confirmed on a held-out set: a fresh window or held-out symbols, with its own sha manifest. The held-out figure is the one the copy quotes. If measure 2 forces a new block, it is frozen again and confirmed on a new held-out set.

1. **Headline size (the per-class coin, one direction per (class, h-block)).** Use enough coins per judged cell for **≥ 2,000 judged runs**, as in r5 (about twice the r5 coins per cell, since about half the cells are now withheld). The pooled verdict rate must be **≤ 5.0%**, and the upper bound of the cluster-bootstrap 95% interval must be ≤ 6.5%. "Beats" alone must be ≤ 2.5%. No range × horizon-band cell that is still judged may exceed 10% (today up to 18.3%). Repeat at step 1 and step 10: each pooled rate ≤ 6%. Reported: the withheld share per cell and pooled.
2. **Size does not rest on placebos the test is exact for.** This coin is nested in the test's all-class 4-horizon blocks, so the test is exact for it by construction (Architecture §2) and passing (1) proves only that the code is right. Nested coins are therefore **not** the circularity guard. Re-measure (1) with these placebos; each pooled rate must be **≤ 7.5% (pass/fail)**, and above that the block definition is revisited:
   - **one coin per class with blocks of 8 horizons** (not nested: slower than the cluster; under the earlier unit it read 8.4%);
   - **one market-wide coin per h-block** (earlier unit: 8.2%);
   - **one market-wide coin per 4-horizon block** (earlier unit: 21.9%);
   - block edges shifted by a seeded random offset (not nested).

   The two market-wide coins are nested in the new unit; they are pass/fail because they are the failures that forced it, and they confirm the fix at full scale. The per-class coins with 2 h and 4 h blocks are nested and are reported as exactness checks, not pass/fail. The independent (per-trial) coin stays ≤ 2% (today 1.62%). Reported for every placebo: the withheld share and the unconfirmed share (measure 11).
3. **Attribution size.** Use real momentum trials with `c_news` replaced by noise, on **12 settings that stay judged under the all-class unit** (q ≥ 8; the validator's 2y h40 and 10y h120 are now withheld and are replaced), with **≥ 40 seeds per setting per design: n ≥ 480 per design**. KEEP/INVERTED must be **≤ 5% for both the (class, block) design and the per-symbol persistent design**. The iid design stays ≤ 2.5%. The blend's "ranks backwards" must fire on ≤ 5% of placebos (it can fire only at q ≥ 10; the share of settings where it cannot is reported). Reported: the withheld share per design.
4. **The IC lag is settled, for both designs.** With the new test in place, (3) is re-run at ½×, 1× and 2× one average hold, at n ≥ 480 per design, **for the (class, block) design and the persistent per-symbol design**.
   - The (class, block) rate must stay ≤ 5% at all three lags. That supports "the lag is not what calibrates the grade", **for components that vary over time only**.
   - For the persistent design the DK bar and the spread carry the size (the gate removes little). If its rate rises above 5% at ½×, the lag stays at 1× and the E4 pin stays, with that reason in its docstring. If it stays ≤ 5% at all three, the lag still stays at 1× [A13], and the E4 pin stays as a regression guard.
5. **Power, headline (the test is not blind).** Use the same bars and the forced LONG/SHORT pairs:
   - Build an injected edge. For each trial, with probability π, take the direction whose forced outcome hit its target (when exactly one did). Otherwise use the coin.
   - Pick π so the realised Δ is about +3 pts at the Lab default (2y h5). The new rule must give a verdict on **≥ 80% of 40 seeds** (pass/fail). The prototype read 32/40 at Δ +2.86, exactly at the bar (Architecture §9).
   - **Required published output:** the clustered-edge power curve (π applied per (class, h-block)), next to the per-setup curve. Both use Δ ≈ 1, 2, 3 and 5 pts, at the Lab default, 5y h20 and 5y h40, for today's rule and the new rule. (5y h60 is withheld under the new unit, q 6, so 5y h40, the longest judged 5y setting, replaces it.) Power copy, anywhere, quotes only the clustered figure or says nothing.
   - Withheld runs count as no-verdict, and the withheld share is reported per setting.
6. **Power, attribution.** A real component with a per-setup IC of about 0.035 is graded KEEP on **≥ 80%** of 30 runs, with withheld runs counted as no-grade and the withheld share reported. The r5 baseline was 28/30; the prototype read 59/60 (earlier unit; not yet re-measured for the all-class unit).
7. **Deterministic.** The same trials always give the same p-value and the same verdict:
   - across two runs;
   - across processes with different `PYTHONHASHSEED`;
   - natively and with `QT_QPA_PLATFORM=offscreen`.

   The seed comes from the run's own content, never from the clock. When Monte Carlo is used, the summary reports p, the number of clusters q and the number of draws B.
8. **Acceptance tests become rate tests** (Architecture §11, tests 8–11). Bounds are set in advance from Binomial(N, p), never fitted to seeds. Each is seeded, slow-marked [A4] and caches its forced pairs once per world. Without coverage each stays under the 60 s per-test cap (at most about 20 s at load 50–65, fix loop 2); under coverage on a loaded machine they do not, so coverage runs them in a separate pass with the per-test cap lifted (§14).
   - **Headline verdict tests (a gate against today's code): four sets of 150** (fix loop 2; split from two tests of 300). Each: 15 synthetic worlds (504 bars) × 10 per-class h-coins at **h15 = 150 judged runs**. Each asserts **`q == 8` on every run and exactly 150 judged** (withheld share 0), so a calendar change fails loudly instead of quietly withholding. Bounds: **≤ 14 verdicts** (99th percentile of Binomial(150, 5%)) and **"beats" ≤ 9** (Binomial(150, 2.5%)). At today's rate on these worlds (9.2%, QA) at least one of the four fails with probability ≤ 0.88 (sets share worlds; the verdict bound alone); on these seeds the gate removed reads 14, 10, 18 and 13 verdicts and the third set fails. They must catch the mutant "randomisation gate removed". The docstring says this is a gate against today's code, not proof of 5%; proof is measure 1.
   - **Exactness, over the same runs:** across the 600 runs of the four headline sets, gate-alone rejections must lie in **13–37** (0.5–99.5% band of Binomial(600, 4.0%)). It catches a dead or inverted statistic.
   - **All 600 headline runs together** (fix loop 3, QA P3-1): **≤ 43 verdicts** (99th percentile of Binomial(600, 5%), P(X ≤ 43) = 0.992), set in advance. With the gate they read 20; with the error bar alone 55, so this bound catches the gate removed where only set [15-0] does. Its own slow test, so the exactness test stays under the 60 s cap alone; in the suite it reads the headline tests' cache.
   - **Circular-pass guards (pass/fail),** on the same worlds at h15, **two sets of 150 judged runs each**, bound **≤ 19** per set (99th percentile of Binomial(150, 7.5%), measure 2's bar): a per-class 8 h coin, a market-wide h-block coin, a market-wide 4 h coin (nested, and off the grid).
   - **Attribution test (a regression guard, labelled as one).** Its horizon is **re-measured where q ≥ 8** (h60 on 504-bar worlds is now withheld). The engineer first measures today's rate there, then sets N and the bound from Binomial. **The attribution size gate is the real-bar figure of measure 3.** Its docstring and the CHANGELOG say so. The "real component still KEEP" assertion stays.
   - The validator runs the same logic on ≥ 5 disjoint seed sets, and every set must pass (today the attribution test passes on 1 of 3).
9. **Copy follows the number: every description of the decision rule, not just the rate.** It is restated in the same release wherever it appears:
   - `_verdict` (`sonar/backtest.py:787`, comment at `:777`) and the "two standard errors" wording (`:111` and elsewhere);
   - the "within … no edge detected. This is what no edge is supposed to look like." string (`sonar/backtest.py:771-774`, `ui/app.py:2862`). It becomes "not shown to differ from the prediction, which is not the same as no difference";
   - `static/docs.html` (Learn tab): `:568-573`, `:648-658` ("This is the number that decides", the rate at `:654`), `:665` ("two standard errors, the Lab's rule"), `:775-782`;
   - `CONFIDENCE.md:618-625`;
   - the Design section of `qa11-qa13-honest-baselines.md`.

   **The rate copy:**
   - quotes the **worst** held-out figure across measures 1–2 with its scope (directions picked at random over stretches of up to four holding periods), never a pre-filled "1 in 20" (Architecture §7);
   - says the rate is per run, so trying many settings makes a chance verdict likely;
   - gives the date, N, the interval and the withheld share, and cites the validator report and the bar-set sha manifest.

   **Grep check:** "1 run in 10", "two standard errors", "number that decides" and "no edge is supposed" each return only reviewed, current hits. Every new string keeps "before costs". No string implies edge, profit or certainty, and none presents the power bar as an economically meaningful edge (+3 pts at 1.5:1 is about +0.075 R before costs).
10. **Real runs reported.** The validator lists every real momentum run and real component grade that changes, how many now read "not told apart from chance", and how many are now withheld (`few_clusters`). Today: 0 headline verdicts and volatility INVERTED at 2 of 12 settings. Under the all-class unit the prototype expects the 1y h5 INVERTED grade to become "not told apart from chance" (p 0.047, fails BH) and the 5y h5 grade to survive (p 0.0085) (Architecture §9).
11. **Third state (P1-1).** A run outside the DK bar that the gate does not confirm reads `verdict_state = "unconfirmed"`. A component that today's rule would grade KEEP or INVERTED but the gate does not confirm reads `UNCONFIRMED`. Both are grey and both are pinned by tests that check:
    - the copy never says "within", "no edge", "beats", "below", "survives FDR" or the word "unconfirmed" (users read "not told apart from chance"), and no beats, below, KEEP or INVERTED string says "confirmed" or "verified";
    - the Lab's "inside its own error bar" paragraph appears only for `within`;
    - the mirror fixture (outside the bar, p small) still reads "beats".

    The validator reports the unconfirmed share for every placebo, next to the verdict rate and the withheld share (all-class prototype, 80 judged runs each: 5 for the per-class h-coin, 9 for the 4 h coin, 11 for the 8 h coin).

## Scope

- The headline verdict in `summarise` and `_verdict` gets a per-run randomisation p-value. Clusters are 4-horizon blocks across all asset classes (owner decision; Architecture [A6]). A flip means taking the opposite forced direction for every trial in the cluster. The statistic is studentised (Canay–Romano–Shaikh 2017).
- Attribution (`attribute`, `_ic_t`, `_quintile_spread`, the blend t) gets the same clusters and the same kind of p-value.
- Enumerate all flips when q ≤ 12. Otherwise use Monte Carlo with p = (1 + #{|T*| ≥ |T|}) / (1 + B).
- A minimum cluster count (q ≥ 8), below which the run is withheld `few_clusters` with copy that names the fix (Architecture §4). It binds on 37–50% of today's judged settings.
- **The third state:** headline `unconfirmed` and component `UNCONFIRMED`, grey, each with its own sentence (see Design).
- The replay resolves the opposite direction for each decision point.
- The tests above, every doc that describes the rule or the rate (measure 9), and the CHANGELOG.

**Constraints:**
- stdlib only (`random.Random`; no numpy, scipy or `arch`);
- seeded and deterministic per run;
- tests never touch Application Support;
- both suites run natively and with `QT_QPA_PLATFORM=offscreen`, twice each;
- stage files by name.

**Smaller version (recommended):** the p-value is an **extra gate** (verdict = outside the DK bar **and** randomisation p < 0.05; a grade = today's rule **and** a randomisation p that survives BH). It can only remove verdicts, never add them. The shown bar and its copy stay coherent: anything that gets a verdict is still "outside its error bar", and anything outside the bar but not confirmed says exactly that. It never says "within". No new number appears in plain mode.

## Non-goals

- DROP's missing error bar: deferred by the owner to the P3 backlog item (TODO.md), with a CHANGELOG line saying DROP is uncalibrated.
- The h = 1 tie residual (a separate P2). Direction randomisation may cancel part of it; it is measured and reported, not targeted.
- Changes to the existing withheld rules, `MAX_VERDICT_HORIZON`, the span or too-few rules, `Z_CLAIM`, buyability or `model_vs_market`.
- The attention/news buckets: already 2.1% false with BH and DK (r6 (f)).
- Webb six-point weights or two-way (symbol × date) clustering: on the watch list only.
- Scaling the bar by a fudge factor to hit 5% pooled. It is cheaper, but it leaves the per-setting spread (8–18%) and does not calibrate attribution.

## Open questions for the owner

**Answered at the Build gate (2026-10-12):** gate, not replacement [A1]; `few_clusters` at q < 8 [A2], now binding on 37–50% of judged settings; expert view shows `p_tail` only [A3]; rate tests slow-marked under the 60 s cap [A4]; DROP deferred, option (a) [A5]; the all-class cluster [A6]. The size targets (measures 1–4) stand as written in the spec approved for Build; this revision only re-aims them at the all-class unit.

**Still open:**

1. **[A15] Terminal range rule (needs an owner nod now; the only open architecture item).** `range_for_horizon` picks the shortest range that gives q ≥ 8: **2y for h ≤ 10, 5y for h ≤ 30, 10y for h ≤ 80**. Without it, the Terminal's 20-day and 60-day lines are always withheld. Cost: bigger fetches on those two profiles (10y has hit Yahoo rate limits before; wall time not measured). The Lab keeps the user's range and shows the `few_clusters` fix. Recommended: yes.
2. **Measure 5's power bar, after the curve (not blocking Build).** P(≥ 32/40 | true 80%) is 0.59, so the bar is a coin flip (validator P3-1). The validator proposes a bar or a seed count from the full-scale curve; the owner accepts it at Verify.

## Risks

- **Circular calibration.** The test is exact for any coin nested in its blocks, so nested placebos cannot show circularity. The non-nested placebos of measure 2 (the 8 h coin, shifted edges) are the guard, pass/fail.
- **Dependence across blocks.** Holds last up to 4h bars, so trials in neighbouring blocks share future bars. The architecture chose 4 h blocks to contain this. A meaningless direction that persists longer than 4 h is not guaranteed ([A14]); measure 2's 8 h coin is pass/fail for it.
- **Coverage loss.** 23 of 62 judged settings become withheld, mostly long horizons; without [A15] the Terminal's 20- and 60-day lines always read withheld. The Lab must name the fix, not read as broken.
- **Grey everywhere.** The unconfirmed state will show on some meaningless runs (3–14% of placebos in the all-class prototype), and real readings may land there too. The copy must read as "not told apart from chance", not as a fault.
- **Not a pure sign flip.** At 1.5:1 a long trial's outcome and a short trial's outcome are not complements. Timeouts depend on direction, so n changes under a flip. Validity rests on the directions being exchangeable under the null. The architect defines the statistic and the validator confirms it.
- **Power loss.** The app may almost never issue a headline verdict. That fits the product's stance ("not demonstrated", never "no edge"), but the Lab must not read as broken.
- **Cost.** Resolving both directions doubles the replay work (10y runs). Monte Carlo at B ≈ 10k on cluster sums is cheap. The architect states a budget.
- **Monte Carlo edges.** Near-identical settings get different seeds, so a borderline p can flip. B must keep the Monte Carlo se at p = 0.05 to about 0.002 or less.
- **Copy drift.** The rule and the rate are described in four files and a spec. Measure 9 and its grep check are the guard.

## Design  *(mandatory; written by the product manager, as the ux-designer is not run separately)*

The tech-writer words the final strings within these requirements. Every new string keeps "before costs" and "one replay of past prices". None says edge, profit, certain or luck.

**Plain mode (no new number):**
- **Unconfirmed (headline), grey `#7c8798`, Lab and Terminal line.** It names the bar and Δ, then says the result was not told apart from directions picked at random over stretches of time across the watchlist. Shape: "Before costs, 3.1 points above the prediction, outside its error bar (±2.8), but directions picked at random over stretches of time across the watchlist land this far out often enough that this is not told apart from chance." It never says within, no edge, beats, below or "unconfirmed" (Architecture §4); the Terminal uses a short form of "not told apart from chance".
- **Within:** "…not shown to differ from the prediction, which is not the same as no difference." This replaces "no edge detected. This is what no edge is supposed to look like."
- **Withheld (`few_clusters`):** names the fix, as Architecture §4: "too few separate stretches to judge (q of the 8 needed); a shorter horizon gives more, or a longer range up to five years". On a run already at five years the range clause is dropped (owner, after the fix-loop-2 review).
- **Component `UNCONFIRMED`, grey, plain words "not told apart from chance".** Sentence as Architecture §4 (domain P3-B). It never says "survives FDR", "confirmed" or "verified".
- **Rate copy (Learn tab and verdict footers):** follows measure 9 (pooled figure plus worst setting, per run, many settings make a chance verdict likely, with the date, N, interval and source).
- **Power copy:** either the clustered-edge figure or nothing.

**Expert mode:**
- The line "p vs random directions, in the direction of Δ: {p_tail} ({q} stretches)" (Architecture §7). Its tooltip reads "share of random-direction reshuffles of whole stretches that read at least this far", never "chance it's luck".
- A component's randomisation p appears next to its IC t, and `UNCONFIRMED` shows both.

## Architecture  *(architect)*

- **Status:** revised 2026-10-12 after the owner's Build-gate decisions (top of this spec). The validator review (`docs/audit/sign-randomisation-verdicts-model-validator.md`) and domain-finance pass 2 are folded in. The engineer builds from this version.
- **Decision record:** `docs/adr/0003-sign-randomisation-gate.md` (revised to match).
- **Scope:** the change touches the verdict logic of `summarise`, `attribute` and the replay contract of `run_symbol`.
- **Playbook:** `docs/playbooks/architect.md` is `status: baseline` (stale by AGENTS.md); the owner chose to continue.
- **Assumptions:** tagged [A1]–[A15] and listed in §13. A1–A14 are approved as amended. A15 is new and needs an owner nod.
- **What changed from the gated version:**
  - the cluster is now a 4-horizon block across **all** classes;
  - the 8 h per-class coin and the two market-wide coins are now pass/fail placebos;
  - the validity text is narrowed to nested directions;
  - attribution clusters on the same all-class blocks, and the lag wording is qualified;
  - the rate tests are rebuilt for the new unit and the 60 s cap;
  - expert view shows `p_tail`, and the copy rules are set;
  - a truly independent held-out set is specified;
  - the Terminal range rule is new [A15].
- **Prototype:** all rates in §9 were re-measured for the all-class unit on the scratchpad prototype. Nothing in `sonar/` or `tests/` changed.

### 1. Approach in one paragraph

- **Today's rule stays.** Δ must still lie outside the date-clustered (DK) error bar.
- **A second test is added; a verdict needs both.** It asks whether the run's direction choice beats directions picked at random for whole stretches of time across the whole watchlist. It re-scores the same run with each 4-horizon block's directions swapped for the opposite forced direction, under all (or many random) patterns of swaps, and asks where the real run falls among them.
- **It only removes.** It can take away verdicts or grades, never add them [A1].
- **A third state for runs outside the bar but not passing.** Such a run is shown as "not told apart from chance": grey, never "within".
- **Few stretches means no verdict.** A run with fewer than 8 blocks is withheld.

### 2. The statistic (headline)

**Clusters** [A6] (owner decision, validator P1-1 option (a)):
- A cluster is one block of `block_days = MAX_HOLD_MULTIPLE × ceil(h × 365/252)` calendar days **across every asset class**: 32 days at h = 5, 116 at h = 20, 348 at h = 60.
- Each compared setup belongs to the block of its UTC entry date: block index `int(t // 86400) // block_days`.
- Edges are anchored at Unix day 0. They never depend on the sample.
- Holds that spill into the next block stay in their entry block; nothing is dropped or split.
- Because a block lasts as long as the longest hold, a hold reaches at most the next block. 25–32% of momentum's resolved setups exit in a later block.
- The class drops out of the cluster key. `classes` is no longer needed for the headline [A12 narrowed: the class map stays only for `compared_by_class` and the placebos].
- **Why all classes.** With (class, block) clusters, a meaningless direction shared by every class was not controlled: one coin per h-block across all classes gated 8.2%, and one per 4 h block 21.9%, at full scale (validator P1-1). All-class blocks nest both, so for them the test is exact.

**Pairs.**
- For each compared decision there are two forced outcomes: the chosen direction and the opposite one, from the same bar, σ̂ and window.
- An orientation that resolved contributes `s = win − predicted` and `n = 1`, where `predicted = resolved_hit_probability(k_t, k_s, horizons)`; it is the same for both directions.
- A TIMEOUT contributes (0, 0). Short windows are excluded in both orientations.
- Per cluster and orientation, five sums are kept with `math.fsum`: s, n, s², s·n and n².

**Statistic: the cluster-robust t of the gap under each flip pattern (RI-t):**

```
N = Σ n_g(o_g)   S = Σ s_g(o_g)   Δ(o) = S/N
V(o) = Σ (s_g(o_g) − n_g(o_g)·Δ(o))² = A − 2·Δ·Bsn + Δ²·C
T(o) = Δ(o)·N/√V(o)      (T = 0 when N = 0 or V ≤ 0: fail closed)
```

- The observed T comes from the same function with no flip, never from rounded summary fields.
- A flip that turns a TIMEOUT into a resolved setup changes N. Nothing assumes that LONG and SHORT outcomes mirror each other.

**p-value** [A7]:
- `p_hi = #{T* ≥ T}/D`, `p_lo = #{T* ≤ T}/D`, where D is the number of patterns. Under Monte Carlo the observed pattern counts once: `(1+#)/(1+B)`.
- `p = min(1, 2·min(p_hi, p_lo))` is an output field.
- **`p_tail`** = `min(1, 2·p_hi)` when Δ > 0, else `min(1, 2·p_lo)`.
- The gate is `p_tail < 0.05`. "beats" is therefore a one-sided 2.5% test.
- Equal tails because the reference distribution centres on the gap that both directions share, not on 0.

**Validity** (validator P2-2; the earlier asymptotic claim is withdrawn):
- **Exact for nested directions.** The test is exact in finite samples for a meaningless direction whose random draws are nested inside the test's clusters, whatever the 1.5:1 asymmetry, the change in n or the class sizes. Nested here covers:
  - one draw per setup;
  - one per (class, h-block) or per (class, 4 h-block) on the same anchor;
  - one market-wide draw per h-block or per 4 h-block.
- **No guarantee otherwise.** There is none for directions not nested in the clusters:
  - edges shifted off the anchor;
  - blocks longer than 4 horizons (the 8 h coin);
  - real momentum, whose direction persists across blocks.
- For those, size is an empirical property, measured by the measure-2 placebos and nothing else.
- **Measured** (under the (class, block) unit, where the same theorem applies): gate alone 5.1% on 800 nested coins with balanced tails (prototype), and 5.1% on 2,040 runs (validator).

### 3. Enumeration, Monte Carlo and the seed [A10]

**Enumerate or sample.**
- Enumerate all 2^q patterns when q ≤ 12, otherwise Monte Carlo with B = 11,999 (MC se 0.0020 at p = 0.05).
- Under the all-class unit q is small: 8–22 on most judged settings, 453 at 10y h1. So **enumeration is the usual path, not the exception**: 2 of the 4 prototype cells that stay judged (q 11) enumerate, and every setting with q 8–12 does.
- An enumerated p is exact. It moves in steps of 1/2^q.

**Minimum clusters: q ≥ 8** [A2]. Below it the run is withheld `"few_clusters"`.
- At q = 8 the smallest one-sided tail is 1/256, so `p_tail` can still reach 0.0078.
- "Ranks backwards" (p ≤ 0.0027) can fire only at q ≥ 10, because 2/2^9 = 0.0039. That is accepted and documented.
- q counts the blocks with at least one paired, compared setup in either orientation.

**Expected withheld settings** (measured: momentum, step 3, horizons 1, 2, 3, 5, 7, 10, 15, 20, …, 120). A setting stays judged up to:

| Range | Judged up to | q at that horizon |
|---|---|---|
| 1y | h 7 | 8 |
| 2y | h 15 | 9 |
| 5y | h 40 | 9 |
| 10y | h 90 | 8 |

- Of 62 settings judged today, **23 (37%) become withheld**. On the validator's 41-horizon grid, 51 of 102 judged cells (50%).
- **Lab default 2y h5:** q 22, judged.
- **Terminal profiles on today's range rule:**
  - 1-day (2y, q 88): judged;
  - 5-day (q 22): judged;
  - **20-day (2y, q 7): withheld**;
  - **60-day (2y, q 3): withheld**;
  - 250-day: withheld today (horizon).
- See [A15] for the range rule that keeps the Terminal's 20- and 60-day profiles judged.

**Seed.**
- Seed = the first 8 bytes of sha256 over `"sonar-rand-v1|<label>|<h>|"` and the sorted lines `symbol|t|direction|outcome|opp_outcome`.
- It uses a local `random.Random`. The draw is `randbytes(q).translate(table)` → `compress`.
- It is independent of row order and of `PYTHONHASHSEED` (verified).
- **Documented (validator P3-3):** the seed includes the observed directions, so a flipped dataset gets a different stream. This is harmless for validity in practice, and the reason is stated in the docstring.
- One golden-value test pins the RNG stream.

### 4. How the gate composes

**Headline.** One new field, `verdict_state`, drives the UI.

```
withheld ∈ {"horizon", "single_class", "too_few", "span", "few_clusters"}   (first that applies)
outside_bar   = withheld is None and |Δ| > 2·se
confirmed     = outside_bar and p_tail < 0.05          (internal name only)
verdict_state = "withheld" | "within" | "unconfirmed" | "beats" | "below"
significant   = verdict_state in ("beats", "below")
```

- **`"unconfirmed"` is an internal value. Users never see that word** (domain pass 2 P2-A).
- **The user sentence says "not told apart from chance".** It names the bar ("outside its error bar ±x"). It says directions picked at random over stretches of time across the watchlist landed this far out often enough. It never says "within" or "no edge".
- **Grey everywhere.** It is grey on the Lab and on the Terminal line.
- **The Lab's "inside its own error bar" paragraph** shows for `"within"` only (`ui/app.py:2807` reads `verdict_state`, falling back to `significant`).
- **"confirmed" and "verified" are banned.** A pin test checks that no beats, below, KEEP or INVERTED string contains either word.
- **Withheld copy for `few_clusters`.** It names the fix, as the span copy does: "too few separate stretches to judge (q of the 8 needed); a shorter horizon gives more, or a longer range up to five years". On a run already at five years the range clause is dropped (owner, after the fix-loop-2 review).
- **Hand-built samples are exempt.** A sample with `universe=None` is not held to the gate [A11].
- **Missing pairs fail closed.** A judged run without opposite outcomes has q = 0 and is withheld.

**Attribution.**
- **Group action: a sign change of per-cluster centred IC products** `S_g = Σ (x_i − x̄)(y_i − ȳ)`, using the Canay–Romano–Shaikh t, the same enumeration and Monte Carlo rule, and a seed labelled `ic|<component>`.
- **Decision: attribution clusters on the same all-class 4-horizon blocks as the headline** [A8].
  - A market-wide component (one value per stretch for every instrument, such as a watchlist-wide attention wave) would put the same x into every class's cluster for that block. That makes (class, block) scores dependent and the test anti-conservative. All-class blocks nest it.
  - It adds no new withheld path. A run with q < 8 is already withheld and grades nothing (`NOT_JUDGED`).
  - Measured exactness: 5y h20, q 16, 400 draws: iid noise 5.8%, class-block noise 5.0%.
- **BH and confirmation.** BH at q = 0.10 runs across the measured components. `confirmed = survives_fdr (DK) and survives the randomisation BH`.
  - BH lets one component's grade depend on the others' p-values (validator P3-2). The composite stays low because the DK and spread conjuncts remain.
- **Component third state: `UNCONFIRMED`** (internal value), grey.
  - Plain word: "not told apart from chance".
  - Sentence (domain P3-B): "looks like it ranks setups (or ranks them backwards) on this replay, but a meaningless reading held for stretches of time ranked them this well often enough that this is not told apart from chance."
  - It never says "survives FDR".
- **The quintile spread** keeps its DK bar.
- **"Ranks backwards"** also needs blend `p_rand ≤ normal_p(Z_CLAIM)`.
- **Traits fixed per instrument are not covered** (domain P2-B; validator Q5). A component that is a fixed trait of each instrument, such as volatility, is not covered by any time-block randomisation. The gate alone runs at 8.8% on that placebo. The copy and `CONFIDENCE.md` say so, and the Learn tab says the check "does not cover traits fixed per instrument".

**The component IC lag (QA r6 P2-1; validator P2-3), qualified:**
- **Class-block components:** the composite grade rate does not depend on the lag. It was 2.5% at ½×, 1× and 2× under (class, block) clusters (n = 120, and validator n = 240), and 3.8% at all three under all-class clusters (n = 80).
- **Persistent per-symbol components:** the randomisation gate adds little (validator: it removes 1 of 8 of today's grades). There the DK bar and the spread conjunct carry the size, and the lag matters as much as it does today. **The claim "the lag is not what calibrates the grade" is limited to components that vary over time.**
- **Measure 4 must include the persistent design at n ≥ 480.** If the persistent rate moves above 5% at ½× the lag, the lag stays at 1× and the E4 pin stays, with that reason.
- The lag stays at 1× [A13].

### 5. Data flow

- **Not available today.** `summarise` has only the chosen direction's rows (`backtest.py:396-401`).
- **`run_symbol`** builds the opposite plan (same price, σ̂, h, k's), `_resolve`s it over the same `max_bars`, and adds three fields to each row: `opp_outcome`, `opp_bars_held` and `opp_predicted` (`None` if the opposite timed out). Short windows get `None` in all three and skip the resolve.
- **Downstream.** `run()` passes `trials + timeouts` as today. `summarise` builds all-class block clusters from them. `attribute` builds its score clusters from its resolved setups.
- **The opposite is never a row.** Hit rate, buckets, timing and attention are unchanged.
- **Out of scope:** `sonar/replay.py` and `sonar/research/panel.py`.
- **Helper trap.** A test helper that forces `build_plan` to one side also forces the opposite plan. Helpers must attach `opp_*` from the paired forced row.

### 6. Cost per run (load average 4–160 on 8 cores during the prototype)

| | Lab default 2y h5 | Worst judged case 10y h1 |
|---|---|---|
| Replay, both directions | 0.4–0.6 s (one direction 0.2 s) | 2.5–2.9 s (one direction 1.5 s) |
| Headline randomisation | q 22, MC: about 0.03 s | q 453, MC: about 0.3 s (scaled from 1.5 s at q 2,258) |
| Attribution gates (3 components) | under 0.05 s | about 0.2 s |
| Enumerated q ≤ 12 (2^q ≤ 4,096 patterns) | | under 0.05 s |

- The cost is dominated by the doubled replay: under 1 s extra at the Lab default, about 2 s at worst, in `BacktestThread`.
- The Terminal costs the same.
- The headless agent costs nothing: it never calls `backtest.run`.
- [A15] would make the Terminal's 20-day and 60-day lines fetch 5y and 10y bars. That is more network time (not measured), off the UI thread.

### 7. Summary fields, migration and compatibility

**Headline fields:**
- `verdict_state`;
- `outside_bar`;
- `randomisation`: `{"p", "p_tail", "q", "draws", "method", "block_days", "seed"}`;
- `withheld` may be `"few_clusters"`.

**Attribution fields:**
- per component: `p_rand` and `confirmed`, and the verdict `"UNCONFIRMED"`;
- top level: `randomisation {"q", "draws", "block_days"}` and `blend_p_rand`.

`significant`, `std_error`, `se_dk` and `delta` are unchanged.

**Expert view** [A3]: "p vs random directions, in the direction of Δ: {p_tail} ({q} stretches)" (domain pass 2 P2-C).
- The two-sided `p` is an output field only and is not shown.
- A pin test checks that the expert line reads `p_tail`.
- Plain mode shows no new number.

**Rate copy** (measure 9; domain P1-A): a placeholder until the validator's held-out figure exists.
- Wording: "about 1 run in {N}, measured on {held-out set, date}, N = {runs}, interval {lo–hi}, {withheld share} withheld".
- {N} comes from the **worst** held-out figure across measures 1–2, rounded conservatively.
- It names the scope: "directions picked at random over stretches of up to four holding periods; patterns that last longer can beat the bar more often by chance".
- It says the rate is per run, so trying many settings makes a chance verdict likely.
- It says nearby settings can disagree (P3-E).
- **Never a pre-filled "1 in 20".** If full scale fails, the copy states the measured figure.
- The H5 momentum "beats" and every H5 figure stay out of user copy (P3-C, P3-D).

**Migration: none.** No summary is persisted: `_lab_result` lives in memory, and `research_results/*.json` are separate studies that nothing reads. UI readers fall back to `significant`. Hand-built judged fixtures (`_rigged_rows`) need `opp_*`.

### 8. Module boundaries

- **New `sonar/randomisation.py`** (pure stdlib, no `sonar` imports, no state):
  - `content_seed`;
  - `direction_p(clusters, seed, draws, enumerate_max)`;
  - `sign_flip_p(scores, seed, …)`.
- **`backtest.py`** owns blocks, `verdict_state`, composition and copy. BH comes from `sonar.research.stats`.
- **`run_symbol`** adds the opposite resolve.
- **`range_for_horizon`** gains the cluster-count rule [A15].
- **UI** reads fields only.
- Nothing touches the engine lock, follow mode, `SONAR_DATA`, state files or the nested repos.

### 9. Prototype numbers

**Setup.**
- Code: `/private/tmp/claude-501/-Users-as-Documents-lab-active-sonar/6947bd8a-9ebb-4b83-a5c1-536e27b9027b/scratchpad/arch/`. The all-class unit is in `sweep2.py`, `qmap.py`, `synth.py` (`CL=all`), `attr.py` (`CL=all`) and `exact_attr.py`. The earlier unit is in `sweep.py` and `attr.py`.
- Bars: the r5 copy, `bars/MANIFEST.sha256`.
- Step 3, whole watchlist, B = 11,999 unless stated.

**Commands** (`PYTHONDONTWRITEBYTECODE=1`, run with the repo's `.venv/bin/python`):
- `NP=4 python sweep2.py all4h 1y:5,1y:20,2y:5,2y:20,2y:40,5y:20,5y:60,5y:100,10y:60,10y:120 20`, then `python an2.py all4h.jsonl`
- `python sweep2.py all4h_pow 2y:5,5y:20 40 power`
- `python qmap.py`
- `CL=all B=1999 python synth.py synth_all 0 20 5,10,15 10` and `CL=all B=1999 python synth.py synth_all15 20 60 15 10`
- `COIN=mkt CL=all B=1999 python synth.py synth_mkt15 0 30 15 10`
- `CL=all AMS=5 python attr.py attr_all 1y:5,2y:5,5y:5,5y:20 20 placebo`
- `CL=all python exact_attr.py 5y 20 400`

**Headline placebos, all-class unit.**
- 10 cells × 20 coins = 200 runs per design.
- 4 cells stay judged: 1y h5 (q 11), 2y h5 (q 22), 5y h20 (q 16) and 10y h60 (q 11). That is 80 judged runs per design.
- **Withheld share 60% on these cells.** The 6 newly withheld cells have q of 4 to 7.

| Placebo | Today (judged cells) | Gated | Not told apart |
|---|---|---|---|
| Independent coin | 3.8% | 1.2% [0.2–6.7] | 2 |
| Per-class coin, h-blocks (measure 1) | 12.5% | **6.2% [2.7–13.8]**, "beats" 2 | 5 |
| Per-class coin, shifted edges | 6.2% | 2.5% [0.7–8.7] | 3 |
| Per-class coin, 4 h blocks | 17.5% | 6.2% [2.7–13.8] | 9 |
| **Per-class coin, 8 h blocks** | 20.0% | **6.2% [2.7–13.8]** | 11 |
| **Market-wide coin, h-blocks** | 6.2% | **2.5% [0.7–8.7]** | 3 |
| **Market-wide coin, 4 h blocks** | 13.8% | **5.0% [2.0–12.2]** | 7 |
| Real momentum | 0 of 4 judged | 0 | 0 |

- n = 80 is far too small for the spec's bars. These numbers say the design is sound, not that it passes.
- The validator's full-scale (class, block) run has the reference figures. Measure 1 was met at 4.02% on 2,040 runs. Under the class unit, the 8 h coin read 8.4% and the market-wide coins 8.2% and 21.9%.

**Power at the Lab default and 5y h20, all-class unit** (40 seeds; q 22 and 16; none withheld). Each cell gives Δ, then verdicts today → gated:

| Setting | Per-setup edge | Clustered edge per (class, h-block) |
|---|---|---|
| 2y h5 | +0.99: 8→6 · +1.89: 19→19 · **+2.86: 32→31** · +4.72: 40→40 | +0.96: 4→4 · +1.80: 13→12 · **+2.91: 29→29** · +4.64: 40→40 |
| 5y h20 | +0.49: 3→3 · +1.40: 9→9 · +2.61: 24→23 · +4.39: 39→39 | +0.72: 4→4 · +2.00: 16→12 · +2.56: 21→20 · +4.31: 39→35 |

- The all-class unit costs at most 1 of 40 at the Lab default.
- At 5y h20 it costs up to 4 of 40 on the clustered edge.
- Measure 5's bar sits at the edge (validator P3-1).

**Attribution, all-class clusters** (4 judged settings: 1y h5, 2y h5, 5y h5, 5y h20; 20 seeds; n = 80 per design; 10y h60 stopped for machine load):
- Class-block noise: 5.0% today → 3.8% gated, at ½×, 1× and 2× the lag alike.
- Persistent per symbol: 3.8% → 3.8%.
- iid: 0 → 0.
- Gate-alone exactness (400 draws, 5y h20): iid 5.8%, class-block 5.0%.
- **Real volatility:** at 1y h5, randomisation p 0.047 **does not survive BH**, so that INVERTED grade would read "not told apart from chance". At 5y h5, p 0.0085 survives.

**Synthetic worlds** (the tests' `_correlated_world`, 504 bars, all-class clusters, B = 1,999):

| Setting | q | Today | Gated | Runs |
|---|---|---|---|---|
| h5 | 21 | 7.5% | 5.0% | 200 |
| h10 | 11 | 6.0% | 2.0% | 200 |
| **h15** | **8 (every world shares the calendar)** | **11.0% [8.7–13.8]** | **2.8% [1.8–4.5]** | **600**; gate alone 4.0% |
| Market-wide coin, h15 | 8 | 12.0% | 4.7% | 300 |

- On 756-bar worlds today's code reads only 9.5–10% at h15 and h20, and h30 is withheld (q 6).
- Cost: about 0.02 s per run at q = 8, enumerated.

**Not measured:**
- the full scale for the all-class unit (measures 1–3, steps 1 and 10);
- attribution at n ≥ 480, the 10y h60 attribution setting, and the blend rate;
- synthetic rates for the 8 h and market-wide 4 h coins;
- power at 5y h60 under the all-class unit (it is withheld at q 6);
- Lab and Terminal wall time with [A15];
- native and offscreen determinism.

### 10. Failure modes

| Failure | Handling |
|---|---|
| No opposite outcomes on a judged run | q = 0, so withheld (fail closed). A test pins that `run()` supplies them. |
| q < 8 | Withheld `few_clusters`; the copy names the fix. Expect it on 37–50% of today's judged settings. |
| V ≤ 0 or N = 0 under a pattern | T = 0, and ties count against the run. |
| RNG stream changes | Golden test. |
| Float order | `math.fsum`. |
| Discrete enumerated p near 0.05 | Exact, in 1/2^q steps; documented. |
| A meaningless direction not nested in 4 h all-class blocks (slower trends, shifted edges, momentum's persistence) | Measured, not guaranteed: measure 2's placebos are pass/fail. |
| Traits fixed per instrument | Not covered. Disclosed in copy and CONFIDENCE.md. |
| Thread safety | Local `Random`; no shared state. |

### 11. Test strategy

**Fast (each under 2 s):**
1. `randomisation.py` units:
   - enumerated p by hand (q = 3);
   - the Monte Carlo formula;
   - equal tails and `p_tail`, with ties against the run;
   - fsum order independence;
   - seed independent of order and of `PYTHONHASHSEED` (subprocess);
   - the golden value;
   - B = 11,999 pinned.
2. The replay contract: `opp_*` equals a forced opposite replay row for row.
3. Third state:
   - outside the bar with p large gives `"unconfirmed"`, `significant` False, a "not told apart from chance" sentence, the grey colour, and no "within", "no edge" or "unconfirmed" in user text;
   - the mirror (outside the bar, p small) gives "beats".
   - Mutants it catches: the gate removed, and the wrong tail.
4. The expert line reads `p_tail` (domain P2-C). No beats, below, KEEP or INVERTED string says "confirmed" or "verified".
5. Attribution `UNCONFIRMED` fixture: deterministic, catches "gate removed", and never says "survives FDR".
6. `few_clusters`:
   - q = 7 is withheld, q = 8 is judged;
   - it sits after `span`;
   - its copy names the fix;
   - a hand-built `universe=None` sample is exempt.
7. [A15] `range_for_horizon`: each profile horizon maps to a range that gives q ≥ 8 on a synthetic calendar.

**Slow (`@pytest.mark.slow`; run in CI and by `./run-tests.sh`; skipped with `-m "not slow"`) [A4].** Every test caches its forced pairs once per world, asserts its exact judged count, and stays well under the 60 s cap (validator P2-5).

8. **Headline rate tests: two tests**, split for the cap. Together they replace `test_a_correlated_coin_rarely_gets_a_verdict`.
   - Each test: 15 synthetic worlds (504 bars) × 20 per-class h-coins at **h15** = **300 judged runs**. Assert `len(judged) == 300` and `q == 8` on every run, so a calendar change fails loudly instead of quietly withholding.
   - Pre-registered bounds: **≤ 24 verdicts** (99th percentile of Binomial(300, 5%)) and **"beats" ≤ 14** (Binomial(300, 2.5%)).
   - Today's code (11.0%) fails a given test with probability 0.95, and **at least one of the two with 0.997**. The gated code (2.8%) passes both with probability ≈ 1. *(Superseded at fix loop 2: four sets of 150, bounds 14 and 9; see measure 8 and §14.)*
   - q = 8 means enumeration (256 patterns), so the tests run the production path with no B override.
   - About 10–15 CPU-s each.
   - **The docstring says this is a gate against today's code, not proof of 5%** (domain P3-F). Proof of 5% is measure 1 at full scale.
9. **Exactness assertion, inside the same runs** (P2-5, no extra runtime). Over the 600 runs of tests 8a and 8b, the gate-alone rejections must lie in **13–37**: the 0.5–99.5% band of Binomial(600, 4.0%), centred on the measured 4.0%, which is below 5% because enumerated p is discrete. This catches a dead or inverted statistic.
10. **Circular-pass guards (pass/fail; they replace the nested guard; validator P2-1, P2-5).** Three tests on the same worlds at h15, 300 judged runs each. Bound **≤ 34** (99th percentile of Binomial(300, 7.5%), measure 2's bar):
    - a per-class coin with 8 h blocks;
    - a market-wide coin with h-blocks (measured 4.7% gated);
    - a market-wide coin with 4 h blocks.

    The 8 h and market-wide 4 h synthetic rates are not measured yet. The bound is pre-registered, not fitted.
11. **Attribution regression guard** (replaces `test_a_meaningless_clustered_component_is_rarely_graded`): h60 class-block placebo, 120 runs, bound ≤ 12. Labelled a guard. The size gate is the real-bar measure 3.
    - Note: under all-class clusters, synthetic 504-bar worlds at h60 have q < 8, so these runs would be **withheld**. The test must use worlds and a horizon where q ≥ 8: for example h15 on 504-bar worlds, which needs a fresh measurement of today's rate there before the bound's power is known. The engineer measures it first, then sets N from Binomial.
    - The "real component still KEEP" assertion stays.
12. **Power:** a strong injected per-setup edge on synthetic worlds still reads "beats".

**Validator** (frozen real bars, then the held-out set below):
- measures 1–7 and 10 at full scale for the all-class unit, with the withheld share next to every rate;
- measure 2's three new pass/fail placebos;
- measure 3 at n ≥ 480 per design, on settings judged under the new unit (2y h40 and 10y h120 are now withheld, so pick 12 that are not);
- measure 4 including the persistent design;
- measure 5's bar set from the curve (P3-1).

**Held-out set (validator P2-4; domain P3-D).** It must be independent of the r5 bars in time or in instruments, frozen with its own sha256 manifest **before** any held-out run.
- **(a) Primary: a fresh window.**
  - The watchlist's symbols, daily bars from 2006-01-01 to 2016-09-30 (before the 10y set starts).
  - Fetched with a scratch script that calls Yahoo's chart endpoint with `period1`/`period2` (stdlib `urllib`, `backtest._UA`, the same JSON parse as `backtest.fetch_bars`). `fetch_bars` takes only `range=` strings, so no change to `sonar/` is needed.
  - Coverage is reported per class. Most crypto has no pre-2016 history, so that class will be thin.
- **(b) Secondary: held-out symbols.**
  - About 100 liquid instruments not on the watchlist (other US equities and ETFs, FX crosses, futures), with a class map written down before the fetch.
  - Same window as r5, via `fetch_bars`.
- **Rules for both:**
  - Bars go to a scratchpad as JSON (not pickle) with `MANIFEST.sha256`.
  - Scripts never import the engine or the UI, and never read or write `~/Library/Application Support/SONAR`. `backtest.fetch_bars` touches no state. Run with `SONAR_DATA` pointed at an empty temp directory as a belt-and-braces measure.
  - QA reuses the same manifest.
  - The copy quotes the held-out figure (§7).

### 12. Alternatives rejected (details in ADR 0003)

- **(class, block) clusters.** Not exact for directions shared across classes (market-wide coins 8.2% and 21.9% at full scale). Superseded by the owner's decision.
- **h-long, 2 h or 3 h blocks.** They fail the 2× and 4 h placebos (10.4–18.0%).
- **A sign flip of gap sums against the baseline.** It does not centre on the gap both directions share.
- **A sign flip of the paired difference.** It changes the question, and a timeout on one side leaves the difference undefined.
- **A direction swap for attribution.** Wrong null.
- **Dropping setups that cross an edge.**
- **Webb weights.** Still on the watch list. q is often 8–12 now, but enumeration makes those p-values exact.
- **Curtailed Monte Carlo.**
- **numpy or scipy.**
- **Replacing DK with the randomisation.** Dropped: under the earlier unit the gate alone was refuted for market-wide directions (validator P1-1). Under this unit it is untested as a replacement.

### 13. Assumptions (A1–A14 approved as amended at the Build gate; A15 new)

- **[A1]** An extra gate that only removes.
- **[A2]** `few_clusters` when q < 8. **It now binds often:** 37–50% of today's judged settings.
- **[A3]** Expert view shows `p_tail` ("in the direction of Δ") only.
- **[A4]** The rate tests are slow-marked. Each stays under the 60 s cap through split tests and cached pairs. The cap is not raised.
- **[A5]** DROP is deferred (owner): a P3 backlog item plus a CHANGELOG line.
- **[A6]** Block = `MAX_HOLD_MULTIPLE × ceil(h·365/252)` days **across all classes**, anchored at Unix day 0, by UTC entry date.
- **[A7]** Equal-tailed p; the gate on `p_tail < 0.05`; "ranks backwards" at 0.0027, attainable only at q ≥ 10.
- **[A8]** Attribution: a sign change of per-cluster IC scores on the **same all-class blocks**, BH at 0.10, IC only; the spread keeps DK.
- **[A9]** Third states are internal `unconfirmed` / `UNCONFIRMED`. User copy says "not told apart from chance", in grey.
- **[A10]** B = 11,999; enumerate at q ≤ 12; content seed (it includes the observed directions, documented).
- **[A11]** `universe=None` hand-built samples are exempt.
- **[A12]** The class map is used only for `compared_by_class` and the placebos; the headline no longer needs it.
- **[A13]** The lag stays at 1×. "Not what calibrates the grade" holds only for components that vary over time.
- **[A14]** Residuals are disclosed, not fixed: traits fixed per instrument (volatility), and directions not nested in the clusters, which are measured by measure 2.
- **[A15] New, needs an owner nod.**
  - `range_for_horizon` (used by the Terminal) picks the shortest of 2y, 5y and 10y that gives at least 8 blocks: **2y for h ≤ 10, 5y for h ≤ 30, 10y for h ≤ 80** (margins from the measured map). Without it, the Terminal's 20-day and 60-day lines are always withheld.
  - The cost is a larger fetch on those two profiles, and 10y fetches have hit Yahoo rate limits before (validator r5).
  - The Lab keeps the user's range and shows the `few_clusters` reason with its fix.

### 14. Build notes (engineer)

Deviations from the sections above, recorded at fix loop 1 (2026-10-12) so a reader of the
architecture finds them here:

- **Suite budget 300 s → 600 s** (`run-tests.sh`; QA P3-6, code review P3-8). [A4] holds for the
  per-test cap: pytest's 60 s `faulthandler_timeout` is not raised, and every rate test stays
  under it alone and in suite order. The whole-suite watchdog budget was raised instead: offscreen
  runs took 445 s and 534 s on a loaded machine (QA). `docs/company/tooling-baseline.md` records
  the same cap for the coverage step. After fix loop 1 it is still needed: native runs took
  181 s and 190 s, offscreen 471 s and 546 s (load 38–102 on 8 cores), with each offscreen rate
  test at 15–36 s in suite order. 546 s is close to 600; raising it further is the owner's call.
- **The exactness test reads the randomisation alone** (code review P2-4): the same stretches and
  p as `summarise` (`_direction_clusters`, `_randomisation`, checked equal on three runs), not the
  whole summary, so it is not "inside the headline tests" by cache any more but over the same
  600 runs. All rate tests share one session cache of worlds 0–29.
- **Guards:** the market-wide four-horizon coin is now nested with the test's own rounding
  (`MAX_HOLD_MULTIPLE × ceil(h·365/252)` = 88 days at h15); the 87-day coin is kept as a
  separate off-grid guard (code review P2-3, validator r7 P2-1). Every guard asserts q = 8 on all
  300 runs. Measure 2 is accepted as not met (owner, after r7), so the 8h and off-grid guards are
  regression guards; their docstrings say what they cannot tell apart.
- **Fail closed, explicitly:** `summarise` over a universe without its `timeouts` (now `None` by
  default), a pair, an entry time or a horizon is withheld `"unpaired"` with its own sentence
  (code review P3-3, validator r7 P2-2). `attribute` without a horizon grades nothing unless the
  caller says `gate=False` (code review P3-5); `run()` always passes its horizon.
- **Copy:** beats and below share one caveat that quotes `CHANCE_VERDICT_RATE` ("about 1 run in
  10", any verdict) and `CHANCE_VERDICT_RATE_WORST` ("about 1 in 5" at some settings), names
  directions held up to eight holding periods, says the rate is per run and that nearby settings
  can disagree, and ends with the fixed-per-instrument residual, which the unconfirmed sentence
  carries too (owner decisions after r7).

Fix loop 2 (2026-10-12), after the loop-1 re-review, QA re-verify and domain pass 4:

- **Lab 10y withheld (owner, Lab 10y).** The rule lives in `summarise`, keyed on the run's range:
  a new `rng` argument (`run()` passes its own) and `NO_VERDICT_RANGES = ("10y",)` give the
  withheld reason `"drift"`, checked after `horizon` and `single_class` (the reader's settings) and
  before the sample rules. Chosen over the caller because §8 puts verdict composition and copy in
  `backtest.py` and has the UI read fields only; a hand-built sample without a range is not held
  to it [A11]. Attribution reads the withheld run as not judged, as every withheld run. The
  sentence uses "lands outside the bar" rather than "beats", to match the residual below and the
  per-symbol coin, which reads either side. The Lab's `few_clusters` tip reads "A shorter horizon
  gives more, or a longer range up to five years."
- **Copy.** The fixed-per-instrument residual is "A direction fixed per instrument, such as always
  long, can also land outside the bar, because the list holds today's survivors; this check cannot
  see that." (code review P3-3, domain P3-1). The expert IC line says "before the correction for
  the {n} components measured", n from attribution's `randomisation.measured` (domain P2-2). An
  untested component is `UNTESTED`, read "not tested" (domain P3-2). KEEP and INVERTED say
  "before costs" (domain P3-3).
- **Rate tests in 150-run sets** (code review P3-2, QA P2-A): headline 4 × 150 (bounds 14 and 9),
  each guard 2 × 150 (bound 19), the attribution guard 2 × 12 (bound 3, the 99th percentile of
  Binomial(12, 5%)). The z² bounds are unchanged. Slowest test without coverage about 20 s at load
  50–65. A module teardown clears the world caches (code review P3-4). Coverage is measured in two
  appended passes under the watchdog (`COVERAGE=1 ./run-tests.sh`), the slow one with
  `-o faulthandler_timeout=0` and a 1200 s budget (app-context, TESTING.md, tooling baseline).
- **Release marker dropped** (code review P3-1): the placeholder check runs in the default suite.
- **Ruff:** `strict=True` on the seven `zip` calls in `sonar/randomisation.py`; 97 findings at
  049b930 and at the branch head, no new finding (code review P3-5).

Fix loop 3 (2026-10-13), after the loop-2 reviews (code review, domain pass 5, QA re-verify) and
the owner's "After fix-loop-2 review" decisions:

- **Range tips.** `LONGEST_JUDGED_RANGE = "5y"` and `offers_longer_range(rng)` in `backtest.py`:
  the span and `few_clusters` tips say "…, or a longer range up to five years" except on a run
  already at 5y (or 10y, never judged); `summarise` passes its `rng` to `_withheld_verdict`. The
  Lab and Terminal "nothing to compare" reason (`_short_window_reason`) uses the same rule:
  "A shorter horizon, or a longer range of five years at most, leaves room for that." ("up to"
  is avoided there because an existing test reads "up to" as the longest-comparable-horizon
  figure). The Terminal's `few_clusters` tip is unchanged ("A shorter profile gives more.").
- **Survivorship on every Lab result.** `ui/app.py` `SURVIVORSHIP_LINE`, the Terminal's footer
  text, is shown under every Lab result with numbers, in both wordings; a run that compared
  nothing shows no result and so no line.
- **Drift sentence and residual** (domain pass 5 P3-1, P3-2; code review P3-2). "Far more often"
  is gone; the drift sentence quotes "more often than the chance rate a verdict quotes (about 1
  run in 10); on one set of past bars about 1 in 4", and it and `FIXED_PER_INSTRUMENT` name both
  causes: "because each instrument keeps its own trend over the years and the list holds only
  today's survivors; this check cannot see that."
- **Attribution footer** (code review P3-5): no "judged together" / Benjamini-Hochberg line on a
  withheld run; the not-judged note stands alone.
- **Tests.** Drift order pinned (a sparse 10y run reads `drift`; Equity at 10y reads
  `single_class`; the fixed-order test carries the range); the Lab's range reaches
  `backtest.run` (QA mutants D12, D13); the 600 headline runs together ≤ 43 verdicts as its own
  slow test (QA P3-1; in the exactness test it would push that test past the 60 s cap run alone:
  measured 63 s at load 127). Measure 8's catch probability reads "≤ 0.88 (sets share worlds)"
  (code review P3-4, owner).
- **Offscreen teardown "hang" (QA P2-1), measured, not changed.** Final runs at load < 50 (start):
  offscreen exit 0 twice (495 s, 370 s), native exit 0 twice (184 s each). A scratch timing plugin
  showed `pytest_unconfigure` (conftest's Qt teardown) deleting 814 leftover top-level widgets,
  89 `MainWindow`s and 712 `QFrame`s, in 22–47 s offscreen at load 30–100; base 049b930 has the
  same 814 widgets and took 24 s at load 65. Running the slow rate tests first barely changes the
  live objects (140k vs 136k) and the teardown times overlap (29–41 s with them, 22–32 s
  without). QA's watchdog sample is spread across `~QMainWindowWrapper` and other deletions, so
  the process was busy, not deadlocked: an offscreen suite of 330–450 s plus a teardown that
  grows with load passes 600 s at load 150–200. Not caused by this change; making the window
  fixtures delete their windows, or finding why each offscreen window takes about 0.3 s to
  destroy, is a separate item.

Final P3s and the merge of master (2026-10-13), after the final code review of loop 3:

- **Pooled headline bound (code review P3-1).** The separate 600-run test is gone: each headline
  case records its set's verdicts and the case that completes the four asserts ≤ 43, so no case
  summarises 600 runs on its own (a case run alone checks its set only). Supersedes measure 8's
  "its own slow test" above. The ten-year sentence scopes "about 1 in 4" to 20- to 60-day horizons
  (P3-2).
- **Marker `slow` → `rate` [A4].** Master (v2.260–v2.266, `docs/specs/shadow-time-stop.md` V-12)
  made `slow` an opt-in marker deselected by default. Kept as `slow`, the rate tests would no longer
  run in CI or by `./run-tests.sh`, against [A4]. They are now marked `rate`, which runs by default;
  the coverage passes use `-m 'not network and not slow and not rate'` and `-m rate`
  (`docs/company/app-context.md`, `TESTING.md` §7). [A4]'s intent is unchanged; the marker name is.
