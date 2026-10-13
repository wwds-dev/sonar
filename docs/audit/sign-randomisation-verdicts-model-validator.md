# Model validation, Architect phase: sign-randomisation verdicts (ADR 0003)

- **Validator:** `model-validator` (read-only). Saved by the orchestrator, 2026-10-12.
- **Playbook:** `status: baseline`; the owner chose to continue.
- **Data:** r5 bar copy, sha256 manifest matched. `sonar/backtest.py` sha1 `132487f9…`.
- **Draws:** B = 3,999 in the sweeps; Monte-Carlo se at p = 0.05 is 0.0034.
- **Machine load:** 70–180 (other sessions).
- **Scripts and outputs:** session scratchpad `val/` (`vsweep.py`, `van.py`, `vband.py`, `vmkt.py`, `vsynth.py`, `vattr.py`, `indep.py`, `repro.py`, plus their `.jsonl` outputs). The scratchpad is temporary.

## Reproduced
- **Lab default 2y h5 from raw bars:** n 18,973; 7,504 wins; Δ +0.11 pts; se 0.88. This matches r5/r6.
- **Prototype's 6.0% [3.7–9.7]:** recomputed as 15/250 (CB 3.2–8.4; 8 "beats").
- **T re-implemented from the spec text:** matches the prototype to 6 decimals on 3 real runs.
- **Today's clustered-coin rate:** 226/2,040 = 11.1% (r6: 11.37%).

## Answers
- **Q1. Validity.**
  - The test is exact in finite samples for any meaningless direction drawn per cluster nested inside a (class, 4h) cluster, whatever the 1.5:1 asymmetry, the change in n, or the unequal classes.
    - Gate alone: 5.1% on 2,040. Composite: 4.0%.
  - Equal tails with the gate on Δ's tail is correct: P(beats) ≤ 2.5%.
  - Size is **not** controlled for directions shared across classes (P1-1).
  - The spec's asymptotic "weaker null" claim (:200) is unsupported.
- **Q2. Full scale, measure 1 met:**

  | Step | Runs | Gated rate | Notes |
  |---|---|---|---|
  | 3 | 2,040 | **4.02% [3.3–5.0]** (CB 3.2–4.9) | beats 1.67%; unconfirmed 7.1%; worst band 7.5% (n 40); q ≥ 10 always |
  | 10 | 2,020 | **3.47% [2.8–4.4]** | |
  | 1 | 400 | **4.75% [3.1–7.3]** | |

- **Q3. Block choice.**
  - 4h was chosen on the same bars, as the smallest block in which the coarsest placebo is nested. That is selection by construction.
  - At 4h, the h-coin and 4h coin pass by theorem; only the offset coin is a real check.
  - The held-out check (H5) is inadequate: it overlaps the 10y primary bars, has n = 75, and was read after the choice.
  - Power cost is small where judged:
    - 2y h5: 31 → 30 of 40
    - 5y h20: 24 → 24
    - 5y h60: 6 → 6
- **Q4. Attribution.**
  - Class-block: composite **2.5% [1.2–5.3]** at ½×, 1× and 2× the lag (n = 240). Gate alone: 5.0%.
  - Persistent per-symbol:
    - gate alone **8.8% [5.8–13.0]**;
    - composite 4.2% [2.3–7.5] pooled, 5.8% on fresh seeds.
    - The gate removes 1 of 8 of today's grades.
  - BH at 0.10 does not give a 5% per-grade size; the DK and spread conjuncts keep the composite low.
  - Keeping the lag at 1× does not settle QA r6 P2-1 as worded. Measure 4 needs n ≥ 480 and the persistent design.
- **Q5. Residual risks.**
  - Volatility INVERTED: accept, with conditions. The gate adds no evidence for it, and p_rand is anti-conservative for persistent components.
  - Trends slower than 4h: **do not accept silently**. The 8h coin, gated, reads **8.4% [7.3–9.7]**, up to 14.6% at 10y h90–120.
  - The cross-class gap is missing from the residual list.
- **Q6. Rate tests.**
  - The headline test (bound 31) fails today's code on 7/7 seed sets (47–59 verdicts) and passes gated (9–17). It is deterministic.
    - Wall time was **53.6 s at load ~150**, against the 60 s cap.
  - The exactness band 10–32 sits too tight against the true synthetic rate of 3.9% (about 5% of seeds fall below 10). Under nesting it cannot catch bugs in the statistic.
  - The attribution regression guard is correctly labelled.

## Findings
- **P1-1. Directions shared across classes are not controlled.** (2,040 runs, step 3)

  | Placebo | Today | Gated | Gate alone |
  |---|---|---|---|
  | One coin per h-block, all classes | 10.0% | **8.2% [7.1–9.5]** | 18.6% |
  | One coin per 4h block, all classes | 27.9% | **21.9% [20.1–23.7]** (45.4% at 5y h90–120) | 23.4% |

  - "Replacing DK is statistically viable" (ADR :44) is refuted.
  - Fix options (owner decision):
    - (a) **Cluster by 4h block across all classes.** Exact for these placebos (0/48, 1/48), but 51 of 102 judged cells are withheld (q < 8). No power loss where judged.
    - (b) **Keep (class, block)**, publish the cross-class and 8h rates, and narrow the copy.
- **P2-1.** Measure 2 can no longer fail at the chosen block. Add the 8h per-class coin and the two market-wide coins as pass/fail. ADR :43 is misleading.
- **P2-2.** Validity text (spec :199–200): say the test is exact only for directions nested in its clusters, and delete the asymptotic claim.
- **P2-3.** Attribution size for persistent components is not demonstrated. Qualify spec :248. Measure 3 needs n ≥ 480 per design, and measure 4 must include the persistent design.
- **P2-4.** The held-out confirmation is not independent. Use a fresh fetch or held-out symbols with their own manifest.
- **P2-5.** Test fixes:
  - split the headline rate test per horizon, or cache the pairs (60 s cap);
  - set the exactness band from the measured rate (e.g. 5–32), or use 800 coins;
  - assert 400 *judged* runs;
  - replace the nested circular-pass guard with the 8h and market-wide coins.
- **P3-1.** Measure 5 is a coin flip: P(≥ 32/40 | 80%) = 0.59. Set the bar from the curve, or use more seeds.
- **P3-2.** BH at 0.10 lets a component's grade depend on the others' p-values.
- **P3-3.** The content seed includes the observed directions. Harmless in practice; document it.

## Verdict
**Fit with conditions; not ready for Build until P1-1 is decided.**
- Measure 1 is met at full scale.
- Cross-class and slower-than-4h placebos still exceed 5%.
- Attribution size for persistent components is not shown.
- Before Build: the owner picks the cluster unit; measure 2 gains the 8h and market-wide placebos; the validity and lag wording is corrected; the P2-5 test fixes go in.
