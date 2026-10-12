# Spec: sign-randomisation p-value for the backtest verdict and the attribution grades

- Status: Build approved by the owner (2026-10-12). The method needs owner sign-off (TODO.md, "After QA-11 / QA-13"). Revised the same day for the domain-finance Define review (`docs/audit/sign-randomisation-verdicts-domain-finance.md`: P1-1, P1-2, P2-1 to P2-7, P3-1 to P3-4) and aligned with the Architecture section and ADR 0003.
- **Owner decisions at the Build gate (2026-10-12)**, after the domain-finance Architect pass and the model-validator review (`docs/audit/sign-randomisation-verdicts-model-validator.md`):
  - **Cluster unit = 4-horizon block across ALL classes** (validator P1-1 option (a)), not (class, block). Cells with q < 8 are withheld; the validator expects this to cover about half of today's judged cells, mostly long horizons.
  - **DROP deferred** (open question 7 (a)): out of this change; a P3 backlog item and a CHANGELOG line saying DROP is uncalibrated.
  - **Build approved** on architect assumptions A1–A14 as amended. The expert view shows `p_tail` (labelled "in the direction of Δ"). User copy says "not told apart from chance", never the bare word "unconfirmed". The volatility / per-instrument-trait residual is disclosed in copy and CONFIDENCE.md.
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

Every rate below is measured by `model-validator`. The bars are a frozen real-bar set: the r5 live bars, or a fresh fetch saved to a scratchpad with a sha manifest. **Never `~/Library/Application Support/SONAR`.** Unless stated otherwise: step 3, 1y/2y/5y/10y × horizons 1–120, whole watchlist, judged runs only (`withheld is None`). Intervals: Wilson, plus a cluster bootstrap over (range, horizon) cells. **The withheld share is reported next to every judged-only rate.**

**Frozen, then held out.** The block definition (Architecture [A6]) is frozen on the r5 set before the full-scale run. Measures 1–3 are then confirmed on a held-out set: a fresh window or held-out symbols, with its own sha manifest. The held-out figure is the one the copy quotes. If measure 2 forces a new block, it is frozen again and confirmed on a new held-out set.

1. **Headline size (the clustered coin).** Use at least 20 coins per judged cell (≥ 2,000 judged runs, as in r5). The pooled verdict rate must be **≤ 5.0%**, and the upper bound of the cluster-bootstrap 95% interval must be ≤ 6.5%. "Beats" alone must be ≤ 2.5%. No range × horizon-band cell (the 20 cells of the r5 table) may exceed 10% (today up to 18.3%). Repeat at step 1 and step 10: each pooled rate ≤ 6%.
2. **Size does not depend on the placebo matching the test.** The test and the placebo both cluster by (class, h-day block), so passing (1) could be circular. Re-measure (1) with three other placebos. The pooled rate must be **≤ 7.5%** for each; above that, the block definition is revisited:
   - blocks twice as long;
   - block edges shifted by a seeded random offset;
   - one coin per class with blocks of the maximum hold (4h).

   The independent (per-trial) coin stays ≤ 2% (today 1.62%). An 8 h coin (slower than the block) is reported, not pass/fail: it shows the residual circularity.
3. **Attribution size.** Use real momentum trials with `c_news` replaced by noise, on the validator's 12 judged settings, with **≥ 40 seeds per setting per design** (n ≥ 480). KEEP/INVERTED must be **≤ 5% for both the (class, block) design and the per-symbol persistent design**. The iid design stays ≤ 2.5%. The blend's "ranks backwards" must fire on ≤ 5% of placebos.
4. **The IC lag is settled.** With the new test in place, (3)'s (class, block) rate stays ≤ 5% whether the DK lag is ½×, 1× or 2× one average hold. The lag then stays at 1×, documented as not being what calibrates the grade. If the randomisation p-value replaces DK in the IC test, the lag goes and the E4 test is retired with a reason.
5. **Power, headline (the test is not blind).** Use the same bars and the forced LONG/SHORT pairs:
   - Build an injected edge. For each trial, with probability π, take the direction whose forced outcome hit its target (when exactly one did). Otherwise use the coin.
   - Pick π so the realised Δ is about +3 pts at the Lab default (2y h5). The new rule must give a verdict on **≥ 80% of 40 seeds** (pass/fail). The prototype read 32/40 at Δ +2.86, exactly at the bar (Architecture §9).
   - **Required published output:** the clustered-edge power curve (π applied per (class, block)), next to the per-setup curve. Both use Δ ≈ 1, 2, 3 and 5 pts, at the Lab default, 5y h20 and 5y h60, for today's rule and the new rule, at the nested block. Power copy, anywhere, quotes only the clustered figure or says nothing.
   - Withheld runs count as no-verdict.
6. **Power, attribution.** A real component with a per-setup IC of about 0.035 is graded KEEP on **≥ 80%** of 30 runs, with withheld runs counted as no-grade. The r5 baseline was 28/30; the prototype read 59/60.
7. **Deterministic.** The same trials always give the same p-value and the same verdict:
   - across two runs;
   - across processes with different `PYTHONHASHSEED`;
   - natively and with `QT_QPA_PLATFORM=offscreen`.

   The seed comes from the run's own content, never from the clock. When Monte Carlo is used, the summary reports p, the number of clusters q and the number of draws B.
8. **Acceptance tests become rate tests** (Architecture §11). Bounds are set in advance from Binomial(N, p), never fitted to seeds. Each is seeded and stays under the 60 s per-test cap.
   - **Headline verdict test (a gate):** synthetic correlated worlds at h40 and h60, **~400 judged runs**. Bound ≤ 31 verdicts (99th percentile of Binomial(400, 5%)) and "beats" ≤ 18. It must fail on today's code (measured 12–13% there) and catch the mutant "randomisation gate removed".
   - **Exactness test:** 400 nested h-coins, gate alone, rejections within 10–32 (it catches a dead test that reads 0).
   - **Attribution test (a regression guard, labelled as one):** about 120 runs, bound ≤ 12. It cannot reliably fail today's code inside the cap. **The attribution size gate is the real-bar figure of measure 3.** Both its docstring and the CHANGELOG say so.
   - The validator runs the same logic on ≥ 5 disjoint seed sets, and every set must pass (today the attribution test passes on 1 of 3).
9. **Copy follows the number: every description of the decision rule, not just the rate.** It is restated in the same release wherever it appears:
   - `_verdict` (`sonar/backtest.py:787`, comment at `:777`) and the "two standard errors" wording (`:111` and elsewhere);
   - the "within … no edge detected. This is what no edge is supposed to look like." string (`sonar/backtest.py:771-774`, `ui/app.py:2862`). It becomes "not shown to differ from the prediction, which is not the same as no difference";
   - `static/docs.html` (Learn tab): `:568-573`, `:648-658` ("This is the number that decides", the rate at `:654`), `:665` ("two standard errors, the Lab's rule"), `:775-782`;
   - `CONFIDENCE.md:618-625`;
   - the Design section of `qa11-qa13-honest-baselines.md`.

   **The rate copy:**
   - gives the pooled figure **and** the worst setting (shape: "about 1 run in 20 overall, up to 1 in N at some settings");
   - says the rate is per run, so trying many settings makes a chance verdict likely;
   - gives the date, N, the interval and the withheld share, and cites the validator report and the bar-set sha manifest.

   **Grep check:** "1 run in 10", "two standard errors", "number that decides" and "no edge is supposed" each return only reviewed, current hits. Every new string keeps "before costs". No string implies edge, profit or certainty, and none presents the power bar as an economically meaningful edge (+3 pts at 1.5:1 is about +0.075 R before costs).
10. **Real runs reported.** The validator lists every real momentum run and real component grade that changes, and how many now read unconfirmed. Today: 0 headline verdicts and volatility INVERTED at 2 of 12 settings. The prototype expects both INVERTED grades to survive (Architecture §9, [A14]).
11. **Third state (P1-1).** A run outside the DK bar that the gate does not confirm reads `verdict_state = "unconfirmed"`. A component that today's rule would grade KEEP or INVERTED but the gate does not confirm reads `UNCONFIRMED`. Both are grey and both are pinned by tests that check:
    - the copy never says "within", "no edge", "beats", "below" or "survives FDR";
    - the Lab's "inside its own error bar" paragraph appears only for `within`;
    - the mirror fixture (outside the bar, p small) still reads "beats".

    The validator reports the unconfirmed share for every placebo, next to the verdict rate (prototype: 16 of 250 for the clustered coin, 45 of 250 for the 4 h coin).

## Scope

- The headline verdict in `summarise` and `_verdict` gets a per-run randomisation p-value. Clusters are (asset class, block). A flip means taking the opposite forced direction for every trial in the cluster. The statistic is studentised (Canay–Romano–Shaikh 2017).
- Attribution (`attribute`, `_ic_t`, `_quintile_spread`, the blend t) gets the same clusters and the same kind of p-value.
- Enumerate all flips when q ≤ 12. Otherwise use Monte Carlo with p = (1 + #{|T*| ≥ |T|}) / (1 + B).
- A minimum cluster count, below which the run is withheld with "too few separate stretches of time, across asset classes, to judge".
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

- DROP's missing error bar: out unless the owner chooses otherwise (open question 7).
- The h = 1 tie residual (a separate P2). Direction randomisation may cancel part of it; it is measured and reported, not targeted.
- Changes to the existing withheld rules, `MAX_VERDICT_HORIZON`, the span or too-few rules, `Z_CLAIM`, buyability or `model_vs_market`.
- The attention/news buckets: already 2.1% false with BH and DK (r6 (f)).
- Webb six-point weights or two-way (symbol × date) clustering: on the watch list only.
- Scaling the bar by a fudge factor to hit 5% pooled. It is cheaper, but it leaves the per-setting spread (8–18%) and does not calibrate attribution.

## Open questions for the owner

The owner has answered none of these yet. The architecture built on the recommended defaults, and its assumptions are answered at the same gate (mapping in brackets).

1. **Gate or replacement?** [A1] Recommended: the randomisation p as an extra gate. Replacing the DK bar is statistically feasible (Architecture §12), but it brings new on-screen numbers and copy.
2. **Targets:** pooled ≤ 5% (bootstrap upper bound ≤ 6.5%), "beats" ≤ 2.5%, every band ≤ 10%, robustness placebos ≤ 7.5%, attribution ≤ 5% on both clustered designs, all confirmed on the held-out set. Accept these, or set others? (The prototype's clustered coin read 6.0% [3.7–9.7] on 250 runs. Measure 1 at full scale decides.)
3. **Power bar:** a per-setup edge of +3 pts at the Lab default, ≥ 80% of 40 seeds, and a component IC of 0.035, ≥ 80%. The prototype meets the headline bar only just (32/40; clustered 29/40). Accept, or let the validator propose a bar after the full-scale curve?
4. **New withheld reason** [A2]: q < 8 shows "too few separate stretches of time, across asset classes, to judge". The prototype found it never binds on judged settings, but it is still new copy.
5. **Expert mode** [A3]: show "p vs random directions {p}, {q} stretches" in expert view only? Recommended yes.
6. **Suite runtime** [A4]: may the rate tests be marked `slow` (run in CI and `./run-tests.sh`, skipped in the quick loop), at about 25–40 s in total?
7. **DROP** [A5]. Once this gate removes grades, DROP becomes the main grade on real runs: red, firing on 18–28% of noise, with no rate in the docs. Choose:
   - (a) defer it explicitly to its own P3 spec and accept red DROP with no rate for this release (recommended, to keep this change small); or
   - (b) in this release, add DROP's measured noise rate to the Learn tab and soften its colour.

## Risks

- **Circular calibration.** The placebo and the test share the block. Measure 2 is the guard.
- **Dependence across blocks.** Holds last up to 4h bars, so trials in neighbouring blocks share future bars. The architecture chose 4 h blocks to contain this. A meaningless direction that holds per class for longer than 4 h is still not guarded ([A14]; the 8 h placebo of measure 2 reports it).
- **Grey everywhere.** The unconfirmed state will show on some meaningless runs (6–18% of placebos in the prototype), and real readings may land there too. The copy must read as "not told apart from chance", not as a fault.
- **Not a pure sign flip.** At 1.5:1 a long trial's outcome and a short trial's outcome are not complements. Timeouts depend on direction, so n changes under a flip. Validity rests on the directions being exchangeable under the null. The architect defines the statistic and the validator confirms it.
- **Power loss.** The app may almost never issue a headline verdict. That fits the product's stance ("not demonstrated", never "no edge"), but the Lab must not read as broken.
- **Cost.** Resolving both directions doubles the replay work (10y runs). Monte Carlo at B ≈ 10k on cluster sums is cheap. The architect states a budget.
- **Monte Carlo edges.** Near-identical settings get different seeds, so a borderline p can flip. B must keep the Monte Carlo se at p = 0.05 to about 0.002 or less.
- **Copy drift.** The rule and the rate are described in four files and a spec. Measure 9 and its grep check are the guard.

## Design  *(mandatory; written by the product manager, as the ux-designer is not run separately)*

The tech-writer words the final strings within these requirements. Every new string keeps "before costs" and "one replay of past prices". None says edge, profit, certain or luck.

**Plain mode (no new number):**
- **Unconfirmed (headline), grey `#7c8798`, Lab and Terminal line.** It names the bar and Δ, then says the result was not told apart from directions picked at random for whole asset classes and stretches of time. Shape: "Before costs, 3.1 points above the prediction, outside its error bar (±2.8), but directions picked at random for whole asset classes and stretches of time often land this far out, so this is not a finding." It never says within, no edge, beats or below. The Terminal uses the one word "unconfirmed".
- **Within:** "…not shown to differ from the prediction, which is not the same as no difference." This replaces "no edge detected. This is what no edge is supposed to look like."
- **Withheld (`few_clusters`):** "too few separate stretches of time, across asset classes, to judge".
- **Component `UNCONFIRMED`, grey, plain word "not confirmed".** Shape: "ranks setups on this replay, but random signs for whole asset-class stretches do as well too often to call it; not confirmed." It never says "survives FDR".
- **Rate copy (Learn tab and verdict footers):** follows measure 9 (pooled figure plus worst setting, per run, many settings make a chance verdict likely, with the date, N, interval and source).
- **Power copy:** either the clustered-edge figure or nothing.

**Expert mode:**
- The line "p vs random directions {p}, {q} stretches ({method}, {B} draws)". Its tooltip reads "share of random-direction reshuffles of whole class-stretches that read at least this far", never "chance it's luck".
- A component's randomisation p appears next to its IC t, and `UNCONFIRMED` shows both.

## Architecture  *(architect)*

- Status: written 2026-10-12, waiting on the owner gate. It touches the verdict logic of `summarise`, `attribute` and the replay contract of `run_symbol`. Decision record: `docs/adr/0003-sign-randomisation-gate.md`.
- Playbook `docs/playbooks/architect.md` is `status: baseline` (stale by AGENTS.md); the owner chose to continue.
- Built on the spec's recommended defaults. Define's open questions are unanswered. **Every assumption is tagged [A1]–[A14]** and listed at the end so the owner can flip it at the gate.
- Inputs: ADR 0001; the owner decisions in `qa11-qa13-honest-baselines.md`; validator r5/r6; QA r6 P2-1; radar notes of 2026-10-12; the Define-phase domain-finance findings P1-1, P1-2, P2-5, P2-6, P3-2 and P3-6 (`docs/audit/sign-randomisation-verdicts-domain-finance.md`).
- Every rate below was measured on a prototype in the scratchpad (§9). Nothing in `sonar/` or `tests/` changed.

### 1. Approach in one paragraph

Today's rule stays in force: Δ outside the date-clustered (DK) error bar. A second, independent test is added on top, and a verdict needs both: is the run's direction choice better than directions picked at random for whole stretches of one asset class? The second test re-scores the same run with every (asset class, block) cluster's directions swapped for the opposite forced direction, under all or many random patterns of swaps, and asks where the real run falls among them. It can only remove verdicts or grades, never add them [A1]. When a run is outside the bar but the second test does not confirm it, the run shows a third state of its own, "outside the bar, not confirmed against random directions". It is never "within" (domain-finance P1-1).

### 2. The statistic (headline)

**Clusters.**
- A cluster is (asset class, block). Class comes from `WATCHLIST`; a symbol off the watchlist counts as `"other"`. The mapping can be injected so that synthetic worlds can pass their own [A12].
- Each compared setup belongs to the block of its **UTC entry date**: block index = `entry_day // block_days`, where `entry_day = int(t // 86400)`.
- **Block length** [A6]: `block_days = MAX_HOLD_MULTIPLE × ceil(h × 365/252)` calendar days. That is four whole horizon-blocks (29 → 32 days at h = 5; 348 at h = 60).
- **Edges** are anchored at Unix day 0, the same for every class and every run. An edge therefore never depends on the sample: adding one early setup cannot shift every cluster and flip a p-value. Because the block is a whole multiple of the placebo's horizon-block, `ceil(h × 365/252)` days from the same anchor, the clustered coin of measure 1 nests exactly inside the test's clusters. For that coin the test is exact by construction (§9, exactness check).
- **Holds that spill into the next block** stay in the block they were entered in. Nothing is dropped and nothing is split. The block length is what controls spill:
  - with the block as long as the longest hold (4 h), a hold can reach the next block only, never one further;
  - the measured share of momentum's resolved setups that exit in a later block is 25–32% at 4 h, against 70–76% at 1 h (§9).
  - Dropping the setups that cross an edge was rejected: it would change the headline sample.
- **Why 4 h and not h.** With h-long blocks the test passes only the placebo it shares a block with (4.0%). It fails a placebo with blocks twice as long (10.4%) or four times as long (18.0%); that is the circular pass the spec warns about. 2 h and 3 h still fail the 4 h placebo (12.0%, 10.8%). 4 h passes all of them, at almost no cost in power (§9).

**Pairs.** For each compared decision there are two forced outcomes: the chosen direction's row and the opposite direction's row, from the same bar, the same σ̂ and the same window. Each orientation contributes, if it resolved:
- `s = win − predicted`, where `predicted` = `resolved_hit_probability(k_t, k_s, horizons)`. That value is the same for both directions, since it depends only on the k's and the window;
- `n = 1`.

A TIMEOUT contributes (0, 0). A short window is excluded in both orientations, because the window does not depend on direction. Per cluster g and orientation o ∈ {kept, flipped}, five sums are kept with `math.fsum`, so that row order cannot change the result: `s_g`, `n_g`, `s_g²`, `s_g·n_g` and `n_g²`.

**Statistic: a cluster-robust t of the gap under each flip pattern** (the RI-t of MacKinnon and Webb; studentised as Canay–Romano–Shaikh and Chung–Romano recommend):

```
N = Σ n_g(o_g)      S = Σ s_g(o_g)      Δ(o) = S / N
V(o) = Σ (s_g(o_g) − n_g(o_g)·Δ(o))²  = A − 2·Δ·Bsn + Δ²·C   (A, Bsn, C: the summed s², s·n, n²)
T(o) = Δ(o) · N / √V(o)        (T = 0 when N = 0 or V ≤ 0: fail closed)
```

- The observed T is computed by the same function with no cluster flipped. It is never taken from the summary's rounded Δ.
- **n changes under a flip.** A cluster's flipped (s, n) is its own opposite-direction sum, so a swap that turns a TIMEOUT into a resolved setup changes N. Nothing assumes that a LONG outcome mirrors a SHORT one: at 1.5:1 they are not complements.

**p-value: equal-tailed, with the gate on the tail of the observed sign** [A7]:
- `p_hi = #{T* ≥ T}/D` and `p_lo = #{T* ≤ T}/D` over the reference set of D patterns. With Monte Carlo the observed pattern counts once: `(1 + #)/(1 + B)`.
- The reported `p = min(1, 2·min(p_hi, p_lo))`.
- "beats" needs `2·p_hi < 0.05`, which is a one-sided 2.5% test, so the "beats ≤ 2.5%" target maps onto the test directly. "below" needs `2·p_lo < 0.05`.
- **Why equal-tailed and not |T|.** The reference distribution is centred on the gap that *both* directions show against the driftless baseline (the path and daily-bar residual of validator r5 (a)), not on 0. Equal tails cope with that asymmetry. They are also why the gate removes most false "below" verdicts of the *independent* coin on these cells (6.8% → 2.8%).

**Validity (domain-finance P3-6).**
- Under the null, each cluster's directions are as likely as their opposites. The test is then exact for any statistic and any cluster sizes. Unequal classes (Equity 50, Commodity 18) and unequal block populations do not matter for exactness.
- Under the weaker null, where directions carry no information on average but are not exactly exchangeable, studentising keeps the test asymptotically valid with heterogeneous clusters.
- Measured: on 800 h-coins (2y h40), the gate alone rejects **5.1%** at the matched block and 5.1% at the nested 4 h block. The tails are balanced (19 and 22 runs).

### 3. Enumeration, Monte Carlo and the seed [A10]

- **Enumerate** all 2^q patterns when q ≤ 12 (4,096 or fewer evaluations). Otherwise use **Monte Carlo with B = 11,999**, which gives a Monte Carlo se at p = 0.05 of √(0.05·0.95/12,000) = **0.0020**, meeting the spec's ≈0.002. The summary reports p, q, B (or the enumerated count) and the method.
- **Minimum clusters: q ≥ 8** [A2]. Below that the run is withheld (`"few_clusters"`), because the smallest attainable two-sided p, 2/2^q, would be ≥ 1.6%. q counts the clusters with at least one paired, compared setup in either orientation. At 4 h blocks the measured q on judged settings was 16–110 (2,258 at 10y h1). No judged run had q < 8 (0 of 1,250 primary runs).
- **Seed** = the first 8 bytes of `sha256("sonar-rand-v1|<test label>|<h>|" + the sorted lines "symbol|t|direction|outcome|opp_outcome")`.
  - It comes from the run's own content and never from the clock or `hash()`.
  - It does not depend on row order (the lines are sorted) or on `PYTHONHASHSEED`. Verified: the same seed, T and p under `PYTHONHASHSEED` 0, 123 and random.
  - It uses a local `random.Random(seed)` instance, never the module-global one, which the scan threads share.
  - The draw is `rng.randbytes(q).translate(table)` → `itertools.compress`, at C speed.
  - Python guarantees only `random()` stays the same across versions, so one golden-value test pins the stream: an interpreter upgrade that changes it fails loudly. Any p it moves moves only within Monte Carlo error.
- A float-order trap found in the prototype: reversing the row order moved T by 2e-15. `math.fsum` closes it, so no tie can flip.
- Curtailed or sequential Monte Carlo was not adopted: the cost does not need it (§6), and it would make the reported p depend on where sampling stopped.

### 4. How the gate composes

**Headline (`summarise` / `_verdict`).** One new field, `verdict_state`, drives the UI. The withheld order is unchanged, with one new reason appended after `"span"`:

```
withheld ∈ {"horizon", "single_class", "too_few", "span", "few_clusters"}   (first that applies)
outside_bar  = withheld is None and |Δ| > 2·se                (today's rule, se unchanged)
confirmed    = outside_bar and tail p < 0.05 in Δ's direction
verdict_state= "withheld" | "within" | "unconfirmed" | "beats" | "below"
significant  = verdict_state in ("beats", "below")            (meaning kept for every consumer)
```

- **Third state, `"unconfirmed"` (domain-finance P1-1).** Δ is outside the bar, but random directions for whole classes and stretches landed this far out too often.
  - It gets its own verdict sentence. The ux-designer and tech-writer word it, under three constraints: it names the bar ("outside its error bar ±x"); it never says "within" or "no edge detected"; it states that this is not told apart from random directions.
  - It is shown grey (`#7c8798`) in the Lab and on the Terminal line.
  - The Lab's "inside its own error bar" paragraph shows only for `"within"`. `ui/app.py:2807` reads `verdict_state` and falls back to `significant` for a hand-built summary.
  - Pinned by a test (§7).
- **A hand-built sample with `universe=None`** is not held to the gate or to `few_clusters`, just as it is not held to the universe rule today [A11]. `run()` always passes a universe.
- **Fail closed.** A judged run whose rows carry no opposite outcomes (only possible through a test that monkeypatches `run_symbol`) has q = 0, so it is withheld `"few_clusters"`. It never gets an ungated verdict.

**Attribution (`attribute`, `_verdict_for`, the blend).** A component is not a direction, so the group action is **a sign change of per-cluster scores**, not a direction swap [A8]. A direction swap would test "ranks the chosen direction's outcomes better than the opposite's" and would wrongly remove a real effect that does not depend on direction (high volatility helping either direction).
- **Score per cluster.** For the IC, `S_g` = Σ over the cluster of `(x_i − x̄)(y_i − ȳ)`: the same centred products `_ic_t` already sums.
- **Statistic.** The Canay–Romano–Shaikh t of the q cluster scores, centred under each draw. It uses the same enumeration and Monte Carlo rule, the same B, a content seed with label `ic|<component>`, and the same clusters as the headline.
- **Confirmation.** The randomisation p-values of the measured components go through Benjamini–Hochberg at the existing q = 0.10. `confirmed = survives_fdr (today, DK) and survives the randomisation BH`.
- **Third state for components:** a new verdict, **`UNCONFIRMED`** (grey), when today's rule says KEEP or INVERTED and the randomisation does not confirm it.
  - Its sentence never says "survives FDR" (domain-finance P1-1; today's KEEP copy at `backtest.py:1209` does).
  - `survives_fdr` keeps today's meaning; `p_rand` and `confirmed` are new.
  - DROP, WEAK and UNCLEAR are unchanged and are reached exactly as today.
  - UI: one entry each in `ATTRIBUTION_VERDICTS` (plain word, e.g. "not confirmed") and in `_VERDICT_COLOUR`.
- **The quintile spread** keeps its DK bar and is not gated separately. With the IC gate alone, the composed placebo rates were already 2.5% (§9). Gating the spread too would add a second chance to lose power for no measured gain [A8].
- **"Ranks backwards"** needs, in addition, `blend p_rand ≤ normal_p(Z_CLAIM)` = 0.0027 (two-sided 3σ, the claim bar it already uses). That needs q ≥ 10 to be attainable. It is a sentence shown only when it is true, so a failed gate just suppresses it.

**The component IC lag (QA r6 P2-1, mutant E4).** DK becomes a first-stage filter; the randomisation p is what calibrates the grade. Prototype: the class-block placebo is graded **2.5% at ½×, 1× and 2× the lag alike** (today's rule: 3.3%, 4.2%, 5.0%). So:
- the lag stays at 1×;
- `_ic_t`'s docstring says the lag is not what calibrates the grade;
- the E4 pin test stays as a pin of the code, with its docstring updated.

If the owner picks "replace" (open question 1), DK leaves the IC test, the lag goes, and E4 is retired with that reason.

### 5. Data flow

- **Not available today.** `summarise` receives only the chosen direction's rows. `run_symbol` (`backtest.py:396-401`) builds and resolves one plan per decision. Forced pairs exist only in the validator's scripts and in `tests/test_backtest.py:1207-1248`, through a monkeypatched `scoring.build_plan`.
- **New replay contract (`run_symbol`).** After the chosen plan, build the opposite plan with the same price, σ̂, horizon and k's, and `_resolve` it over the same `max_bars`. Each row gains three fields:
  - `opp_outcome` (`TARGET` | `STOP` | `TIMEOUT`);
  - `opp_bars_held`;
  - `opp_predicted`, equal to `predicted` when the opposite resolved, else `None`.

  Short-window rows get `None` in all three and skip the extra resolve. Existing fields and filtering are unchanged; `keep_timeouts` rows carry the opposite fields too, because a chosen TIMEOUT can resolve when flipped.
- **`run()`** is unchanged: it already passes `trials` and `timeouts` to `summarise`, and those carry the pairs.
- **`summarise`** builds the headline clusters from `trials + timeouts`, gets `classes` (default `WATCHLIST`), calls the randomisation module, and sets the new fields.
- **`attribute`** builds its score clusters from the resolved setups it already has. It needs no opposite outcomes.
- The opposite direction is never a row. Hit rate, buckets, `timing`, attention and attribution see exactly the setups they see today.
- **Out of scope here:** `sonar/replay.py` (the interactive Session; it imports `_resolve` and is unaffected) and `sonar/research/panel.py` (fetch helpers only).
- **Trap for the engineer:** a test helper that forces `build_plan` to one side would also force the *opposite* plan to that side, giving opposite = chosen, so every flip is a no-op and p = 1. The synthetic helpers must attach `opp_*` from the paired forced row, or force by swapping the side.

### 6. Cost per run (measured under load average 4–15 on 8 cores)

| | Lab default 2y h5 | Worst judged case 10y h1 |
|---|---|---|
| Replay, both directions (prototype: two full forced passes) | 0.4–0.6 s (one direction 0.2 s) | 2.5–2.9 s (one direction 1.5 s) |
| Headline randomisation, B = 11,999, 4 h blocks | 0.09 s (q 110) | 1.50 s (q 2,258) |
| Attribution gates (2 components) | 0.05 s | 0.74 s |
| `attribute()` today, for scale | 0.17 s | 1.21 s |

- **Lab:** under 1 s extra at the default and about 3–4 s at the worst case, on top of the network-bound fetch of 129 instruments (not measured). It runs in `BacktestThread`, never on the UI thread.
- **Terminal backtest line:** the same `run()` path at the profile's horizon, so the same cost.
- **Headless agent: zero.** The agent never calls `backtest.run`. The only caller is `ui/worker.py:71` (`BacktestThread`); `sonar/core.py` mentions the backtest only in comments.
- **Suite:** about 25–40 s for the two slow rate tests with the test-only B override (§7). The fast tests add under 2 s.

### 7. Summary fields, migration and compatibility

**New summary fields (headline):**
- `verdict_state`;
- `outside_bar`;
- `randomisation`: `{"p", "p_tail", "q", "draws", "method", "block_days", "seed"}` (seed as hex, for audit);
- `withheld` may be `"few_clusters"`.

**New attribution fields:**
- per component: `p_rand` and `confirmed`, and the verdict `"UNCONFIRMED"`;
- top level: `randomisation` `{"q", "draws", "block_days"}` and `blend_p_rand`.

`significant` keeps its meaning: a verdict was given. `std_error`, `se_dk` and `delta` are unchanged.

- **Expert view** [A3]: shows "p vs random directions {p}, {q} stretches". Plain mode shows no new number. The verdict sentence carries the meaning.
- **Migration: none.** No summary is persisted: `BacktestThread` → `_lab_result`, which lives in memory and is re-rendered on a wording switch (`ui/app.py:2435, 3499`). `research_results/*.json` are separate study outputs that the backtest and the UI never read (grep: no reader in `sonar/`, `ui/` or `tests/`). ADR 0001 found the same.
- **Compatibility:** UI readers fall back to `significant` when `verdict_state` is absent. Tests that build *judged* runs from hand-made rows through `run()` with a monkeypatched `run_symbol` (`_rigged_rows`, `tests/test_backtest.py:925-1040`) need `opp_*` fields in that helper. Without them they correctly read `"few_clusters"`. Adding the fields does not weaken those tests.

### 8. Module boundaries

- **New `sonar/randomisation.py`**, pure stdlib (`hashlib`, `itertools`, `math`, `random`) with no `sonar` imports. It works on sufficient statistics only:
  - `content_seed(lines, label)`;
  - `direction_p(clusters, seed, draws=B, enumerate_max=12)`, taking (s, n, s², s·n, n²) per orientation;
  - `sign_flip_p(scores, seed, …)`.

  It holds no state and takes no locks. It is safe on any thread because it uses its own `Random` instance.
- **`backtest.py`** owns the meaning: clusters, classes, block length, `verdict_state`, the composition and the copy. It imports the module. BH is reused from `sonar.research.stats.benjamini_hochberg`.
- **`run_symbol`** gains the opposite resolve and nothing else.
- **UI** (`ui/app.py`) reads fields only: `verdict_state`, the attribution verdict and colour maps, and the expert-view p line.
- Nothing touches the engine single-writer lock, follow mode, `SONAR_DATA`, state files or the nested repos.
- `backtest.py` (1,303 lines) grows by the composition only. The statistics live outside it, testable alone.

### 9. Feasibility prototype: measured numbers

**Setup.**
- Code: `/private/tmp/claude-501/-Users-as-Documents-lab-active-sonar/6947bd8a-9ebb-4b83-a5c1-536e27b9027b/scratchpad/arch/`. The files are `rand.py` (the gate), `common.py`, `sweep.py`, `attr.py`, `synth.py`, `synth_attr.py`, `exact.py`, `exact_attr.py`, `determ.py`, `worst.py`, `an.py` and `an_attr.py`. Outputs are `*.jsonl`.
- `sonar.backtest` was imported read-only. Nothing was written to the repo (`PYTHONDONTWRITEBYTECODE=1`). Application Support was never touched.
- **Bars:** validator r5's live bars, copied, with manifest `bars/MANIFEST.sha256`: `bars_1y` ccd4d23e…, `bars_2y` dda82b38…, `bars_5y` c2d5a956…, `bars_10y` dea8e6cb…
- **Primary set:** step 3, whole watchlist, 10 cells (1y h5, 1y h20, 2y h5, 2y h20, 2y h40, 5y h20, 5y h60, 5y h100, 10y h60, 10y h120), 25 coins per design per cell. That gives 250 runs per design, all judged (**withheld share 0%** for every design and for power, domain-finance P3-2).
- **Held-out set (P2-5):** `H5`, the 10y bars cut to bars before 2021-10-01. It is disjoint in time from the 1y, 2y and 5y sets. Cells: h5, h20 and h60, 75 runs per design.
- **Commands** (from the arch directory, `PYTHONDONTWRITEBYTECODE=1`, with the repo's `.venv/bin/python`):
  - `NP=6 python sweep.py placebo 1y:5,1y:20,2y:5,2y:20,2y:40,5y:20,5y:60,5y:100,10y:60,10y:120 25`
  - `MS=5 python sweep.py placebo_n <same cells> 25` (nested 4 h)
  - `python sweep.py power 2y:5,5y:20,5y:60 40 power`
  - `python sweep.py heldout H5:5,H5:20,H5:60 25`
  - `python an.py placebo placebo.jsonl`
  - `python an.py power power.jsonl`
  - `AMS=1,5 python attr.py attrp_n 1y:5,2y:5,2y:20,5y:5,5y:20,10y:60 20 placebo`
  - `AMS=1,5 A=0.021 python attr.py attrpow 2y:5,5y:20 30 power`
  - `python exact.py 2y 40 800`
  - `python exact_attr.py 2y 20 400`
  - `python synth.py synth_long 12 52 40,60 10`
  - `python synth_attr.py synth_attr_h60 0 40 60 6`
  - `python worst.py`

**Headline placebos, primary set.** Rates are the verdict rate among judged runs; Wilson 95% intervals; "CB" is a cluster bootstrap over the 10 cells. "Gated" means the DK verdict, q ≥ 8 and the tail p below 0.05.

| Placebo (250 judged runs each) | Today (DK only) | Gated, block 1 h | 2 h | 3 h | **4 h (chosen)** |
|---|---|---|---|---|---|
| Independent coin | 6.8% [4.3–10.6] | 2.0% | 2.0% | 2.0% | **2.8% [1.4–5.7]** |
| Clustered coin, h-blocks (measure 1) | 12.4% [8.9–17.1] | 4.0% | 5.2% | 6.0% | **6.0% [3.7–9.7]**, CB 3.2–8.4; "beats" 3.2% [1.6–6.2] |
| Coin, 2× blocks | 18.4% | 10.4% | 4.0% | 5.2% | **4.4% [2.5–7.7]** |
| Coin, seeded-offset edges | 7.6% | 5.2% | 4.4% | 3.2% | **3.2% [1.6–6.2]** |
| Coin per class, 4 h blocks | 23.2% | 18.0% | 12.0% | 10.8% | **5.2% [3.1–8.7]** |
| Real momentum (10 runs) | 0 verdicts | 0 | 0 | 0 | **0** |

- The 4 h column was measured twice, with `ceil(4h·365/252)` and with the nested `4·ceil(h·365/252)`. The counts were identical in every design.
- The clustered coin's 6.0% sits above the ≤ 5.0% target as a point estimate. Its interval contains 5%, and for this design the nested test is exact by construction. The direct check on 800 coins read 5.1% for the gate alone. Measure 1 at the spec's scale (≥ 2,000 runs) decides.
- **Unconfirmed** (outside the bar, gate not passed) at 4 h: 16 of 250 for the clustered coin and 45 of 250 for the 4 h coin. That is how often the new grey state would show on a meaningless direction.

**Held-out window (H5, 75 runs per design, 4 h blocks):**

| | Independent | h-coin | 2× | Shifted | 4 h coin |
|---|---|---|---|---|---|
| Today | 5.3% | 5.3% | 12.0% | 8.0% | 24.0% |
| Gated | 4.0% | 2.7% | 4.0% | 6.7% | 6.7% |

- Honest caveat: the held-out sweep ran at the same time as the primary one and was read after the 4 h choice had formed. It is a confirmation, not a sealed pre-registration. The validator should freeze the block and confirm on a fresh fetch with its own manifest.
- Held-out real momentum at **H5 h20 reads "beats"** today (Δ +2.89, se 1.18) and passes the gate (tail p 0.008). That is a 2016–2021 window no user setting shows. It is reported, not claimed.

**Power (domain-finance P1-2; 40 seeds per point; no run withheld). Cells read "today → gated at 4 h".**

| Setting | Per-setup oracle edge (Δ: verdicts) | Clustered edge per (class, block) (Δ: verdicts) |
|---|---|---|
| 2y h5 (Lab default) | +0.99: 8→7 · +1.89: 19→18 · **+2.86: 32→32 (80%)** · +4.72: 40→40 | +0.96: 4→4 · +1.80: 13→13 · **+2.91: 29→29 (73%)** · +4.64: 40→40 |
| 5y h20 | +0.49: 3→3 · +1.40: 9→9 · +2.61: 24→24 · +4.39: 39→39 | +0.72: 4→4 · +2.00: 16→16 · +2.56: 21→20 · +4.31: 39→39 |
| 5y h60 | +0.17: 1→0 · +1.51: 8→5 · +2.62: 13→12 · +4.39: 28→23 | +0.38: 3→3 · +1.85: 7→6 · +2.18: 11→6 · +4.36: 20→18 |

- The gate costs nothing at the Lab default and 1–5 of 40 at 5y h60.
- Measure 5's bar (≥ 80% at +3 pts at the Lab default) is met only at the edge: 32/40 per-setup at Δ +2.86, the same as today's rule. Clustered, it reads 29/40.
- Power was measured at `ceil(4h·365/252)`, not at the nested block. The placebo counts were identical between the two, but nested power is **not measured**.

**Attribution (6 judged settings: 1y h5, 2y h5, 2y h20, 5y h5, 5y h20, 10y h60; 20 seeds per design, n = 120 per design; real momentum trials with `c_news` replaced by noise). Cells give KEEP/INVERTED rates.**

| Design | Today (lag 1×) | Gated, 4 h |
|---|---|---|
| Per (class, block) | 4.2% [1.8–9.4] (½× 3.3%, 2× 5.0%) | **2.5% [0.9–7.1] at ½×, 1× and 2×** |
| Per symbol, persistent | 3.3% | **2.5% [0.9–7.1]** |
| iid | 0.8% | 0.8% |

- Exactness of the sign-flip test alone, 400 draws at 2y h20: iid 4.0%, class-block 3.5%.
- **Power:** a per-setup real component with mean IC 0.0349 is KEEP on **59/60** both today and gated (2y h5 and 5y h20, 30 each).
- **Not fixed by this design:** the gate alone runs at 7.5–8.3% on the *persistent per-symbol* placebo, because (class, block) clusters cannot see symbol-level persistence. The real volatility readings stay confirmed: randomisation p 0.032 at 1y h5 and 0.007 at 5y h5, both surviving BH. **So the two real volatility INVERTED grades that validator r6 flagged would very likely survive the gate.** Only symbol-level clustering would address them, and two-way clustering is a non-goal on the watch list. The composed persistent rate (2.5%) meets measure 3 on this sample.

**Synthetic worlds (the tests' `_correlated_world`):**
- Clustered coin at h5, h20 and h40 (360 runs): today 10.3% [7.5–13.8], gated 4.4% [2.8–7.1].
  - h40, 400 runs: 12.0% → 3.5%.
  - h60, 400 runs: 13.0% → 3.2%.
- Attribution class-block placebo (240 runs each):
  - h20: 6.7% → 3.8%;
  - h40: 6.2% → 3.8%;
  - h60: 10.4% → 3.8%.
- Cost: 800 coin runs took 51 CPU-s at B = 11,999. An attribution run takes about 0.65 s.

**Not measured:**
- the spec's full scale (≥ 2,000 judged runs over 20 bands, steps 1 and 10, 12 attribution settings at ≥ 40 seeds);
- a placebo *slower* than the block (for example an 8 h coin). The test is anti-conservative for any meaningless direction that holds per class for longer than its block. This is the residual circularity, and the validator should report it;
- power at the nested block, clustered real-component attribution power, and the "ranks backwards" rate under the gate;
- Lab wall time end to end with the network;
- determinism natively and offscreen. It is pure Python with no Qt, and determinism under `PYTHONHASHSEED` was verified.

### 10. Failure modes

| Failure | Effect | Handling |
|---|---|---|
| Opposite outcomes missing on a judged run | q = 0 | Withheld `few_clusters` (fail closed); a test pins that `run()` always supplies them |
| q < 8 | p cannot reach 5% | Withheld `few_clusters` [A2] |
| V(o) ≤ 0 or N = 0 under a pattern | Division by zero | T = 0, so ties count against the run (fail closed) |
| Interpreter changes `randbytes` | p moves within Monte Carlo error | A golden-value test fails loudly |
| Float summation order | A tie flips | `math.fsum` |
| Borderline p near 0.05 | Neighbouring settings can differ | Monte Carlo se 0.002; deterministic per data; documented |
| Slow meaningless direction (longer than 4 h) | Anti-conservative | Residual risk, stated; validator measure 2 plus an 8 h placebo |
| Thread safety | Shared RNG state | A local `Random(seed)` only; no module-global `random`; no shared state, no file writes |

### 11. Test strategy

**Fast (each under 2 s):**
1. `randomisation.py` unit tests:
   - an enumerated p on a hand fixture (q = 3, p known by hand);
   - the Monte Carlo formula `(1+#)/(1+B)`;
   - equal tails, with ties counted against the run;
   - fsum order independence (reversed rows give identical T and p);
   - content seed independent of row order and of `PYTHONHASHSEED` (subprocess);
   - one **golden value** pinning the stream.
2. **The replay contract:** on a synthetic walk, `opp_outcome`, `opp_bars_held` and `opp_predicted` equal a forced opposite replay row for row. Timeouts carry them; short windows carry `None`.
3. **Third state (P1-1):**
   - a fixture outside the DK bar whose clusters make p large gives `verdict_state == "unconfirmed"`, `significant` False, a sentence that never says "within" or "no edge", and the grey Lab colour;
   - the mirror fixture (outside the bar, p small) gives "beats".
   - Mutants it catches: the gate removed, and the wrong tail.
4. **Attribution third state:** a deterministic fixture where today's rule says KEEP and the cluster scores have q small and mixed signs gives `"UNCONFIRMED"`, `survives_fdr` True, `confirmed` False, and no "survives FDR" text. This catches the mutant "gate removed" with no rate needed.
5. **`few_clusters`:** q = 7 is withheld, q = 8 is judged, and it sits after `span` in the order. A hand-built `universe=None` sample is exempt.

**Slow (`@pytest.mark.slow`; run in CI and by `./run-tests.sh`; skipped by `-m "not slow"` in the quick loop [A4]):**

6. **Headline rate test** (replaces `test_a_correlated_coin_rarely_gets_a_verdict`):
   - 20 correlated worlds × h ∈ {40, 60} × 10 coins = **400 judged runs**;
   - pre-registered bound **≤ 31 verdicts** (the 99th percentile of Binomial(400, 5%)) and "beats" ≤ 18 (Binomial(400, 2.5%));
   - fails on today's code with probability ≥ 0.99 (measured 12–13% there, bound fails above 7.75%) and passes the gated code with probability ≈ 1 (3.2–3.5%);
   - catches "gate removed". This answers P2-6 by choosing the long horizons where today's code is worst, not by raising N to 1,200.
   - It uses a **test-only override** of the module's draw count to B = 1,999, because the faulthandler cap is 60 s per test (`pyproject.toml`), and that cap should not be raised. A Monte Carlo p with `(1+#)/(1+B)` is exactly valid at any B, so the test measures the same procedure's size. A separate fast test pins B = 11,999.
   - Runtime: about 25 CPU-s.
7. **Exactness test:** one synthetic world at h40, **400 nested h-coins**, gate alone. The rejection count must fall within the 0.5–99.5% band of Binomial(400, 5%), that is **10–32**. This catches statistic and flip bugs that a one-sided bound misses (a dead test reads 0). About 20 s.
8. **Circular-pass guard:** a 4 h-per-class coin and a seeded-offset coin on synthetic worlds, 200 runs each, with bound ≤ 24 (the 99th percentile of Binomial(200, 7.5%), measure 2's bar). A regression guard; the real-bar measure 2 is the gate.
9. **Attribution rate test** (replaces `test_a_meaningless_clustered_component_is_rarely_graded`): h60 class-block placebo, 20 worlds × 6 draws = 120 runs, bound ≤ 12.
   - Stated plainly as a **regression guard**: at 0.65 s per run, an N that reliably fails today's 10.4% cannot fit under the 60 s cap.
   - The size gate for attribution is the validator's frozen real-bar measure 3 (P2-6).
   - The existing "a real component still reads KEEP" assertion stays as the in-suite power check.
10. **Power in the suite:** a strong injected per-setup edge on synthetic worlds still gets "beats" with the gate on. The curves are the validator's job (measure 5).

**Validator (frozen real bars, sha manifest):** measures 1–7 and 10 at full scale. It should add the clustered-edge curve (P1-2), the withheld share next to every rate (P3-2), an 8 h placebo, and a confirmation on a fresh held-out window or held-out symbols with its own manifest (P2-5). Both suites run native and offscreen, twice each.

### 12. Alternatives rejected (details in ADR 0003)

- **Blocks of one horizon** (the placebo's own block): circular. It fails the 2× and 4 h placebos (10.4% and 18.0%).
- **Blocks of 2 h or 3 h:** the 4 h placebo reads 12.0% and 10.8%.
- **A sign flip of per-cluster gap sums against the baseline** (a wild cluster test of Δ = 0): it tests the same question as DK with another clustering. It does not centre on the gap both directions share, so it cannot remove "every direction reads below".
- **A sign flip of the per-setup paired difference (chosen − opposite):** it answers "beats its mirror", not "beats the prediction", and a timeout on one side leaves the difference undefined.
- **Replacing DK with the randomisation** (owner question 1): statistically feasible, since at 4 h the gate alone is about as good as the composition (4 h coin 5.2% both ways). It was not chosen by default because it brings new on-screen numbers and copy.
- **Dropping setups that cross block edges:** it changes the headline sample.
- **Webb six-point weights:** q ≥ 16 on judged settings at 4 h, so two-point flips can reach p well below 5%. Stays on the watch list.
- **A direction swap for attribution:** wrong null (see §4).
- **Gating the quintile spread as well:** no measured gain.
- **Curtailed Monte Carlo:** not needed for cost, and it would make the reported p depend on the stopping point.
- **numpy, scipy or `arch`:** stdlib only.

### 13. Assumptions for the owner to confirm at the gate

- **[A1]** The randomisation p is an extra gate: it only removes verdicts and grades (spec default).
- **[A2]** New withheld reason `few_clusters` when q < 8 (spec default). Measured: it never bound on judged settings.
- **[A3]** The p-value is shown in the Lab's expert view only (spec default).
- **[A4]** The rate tests are marked `slow`: they run in CI and `./run-tests.sh`, and `-m "not slow"` skips them in the quick loop. Each stays under the 60 s faulthandler cap through a test-only B = 1,999, and the cap is not raised (spec default, plus the cap detail).
- **[A5]** DROP's missing error bar stays out of scope (spec default).
- **[A6]** Block = `MAX_HOLD_MULTIPLE × ceil(h·365/252)` calendar days (4 horizons, nested), anchored at Unix day 0, by UTC entry date, with holds staying in their entry block.
- **[A7]** Equal-tailed p, with the gate on the tail of Δ's sign at 0.05 (so "beats" is a one-sided 2.5% test); "ranks backwards" at `normal_p(Z_CLAIM)` = 0.0027.
- **[A8]** Attribution uses a sign change of per-cluster IC scores (not a direction swap), BH at q = 0.10, on the IC only; the spread keeps its DK bar.
- **[A9]** Third states: headline `verdict_state = "unconfirmed"` and component verdict `"UNCONFIRMED"`, both grey, with copy by the ux-designer and tech-writer.
- **[A10]** B = 11,999; enumerate when q ≤ 12; seed = sha256 of the run's sorted content.
- **[A11]** A hand-built sample with `universe=None` is exempt from the gate, as from the universe rule.
- **[A12]** Class from `WATCHLIST`, with `"other"` for symbols off it; injectable for tests.
- **[A13]** The IC lag stays at 1×, documented as a first-stage filter; the E4 pin is kept.
- **[A14]** The known residual is accepted: real volatility INVERTED (persistent per symbol) very likely survives the gate, and a meaningless direction slower than 4 h per class is not guarded.
