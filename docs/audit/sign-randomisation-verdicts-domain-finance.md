# Domain review (finance): sign-randomisation verdicts

Reviewer: `domain-finance` (read-only). Saved by the orchestrator, 2026-10-12.
The playbook `domain-finance.md` is `status: baseline`; the owner chose to continue on it. No regulatory citation was verified against primary sources. Jurisdiction is UNVERIFIED in app-context.

## Pass 1: Define (spec `docs/specs/sign-randomisation-verdicts.md`)

### P0
None. The gate only removes verdicts, the app is paper-only, and no claim of edge, profit or certainty is added.

### P1
- **P1-1. A gated run gets copy that contradicts the number shown next to it.**
  - Where: spec lines 80 and 113; `sonar/backtest.py:655`, `:717`, `:771-774`; `ui/app.py:3607-3614` and `:2807-2809`.
  - Today `significant = withheld is None and abs(delta) > 2*se`.
  - With the gate, a run with Δ +3.1, bar ±2.8 and p 0.09 lands in the "within 2.8 points … no edge detected" branch, printed directly under `delta +3.10 pts (± 2.8)`.
  - Fix: add a third state, "outside the bar but not confirmed against random directions". It needs its own reason or flag, grey colour and a pinning test.
  - Attribution needs the same, so that a component which fails the randomisation p does not show "survives FDR" copy (`backtest.py:1208-1210`).
  - Make Design mandatory.
- **P1-2. The Goal's "A real edge still gets one" is not measured.**
  - Where: spec line 22; measures 5-6.
  - The power pass/fail uses only a per-setup oracle edge, while the clustered edge is report-only, even though the spec's own premise is class/block co-movement.
  - Fix:
    - Restate the Goal as measured ("an injected per-setup edge of ~+3 pts at 2y h5 gets a verdict on ≥80% of 40 seeds").
    - Make the clustered-edge power curve a required published output.
    - Any power copy must quote the clustered figure or say nothing.

### P2
- **P2-1.** The withheld reason says "independent stretches", but the spec's Risks section says the blocks are dependent. Use "too few separate stretches of time, across asset classes, to judge".
- **P2-2.** "no edge detected. This is what no edge is supposed to look like." (`backtest.py:771-774`) overstates what a lower-powered test supports.
  - Add the string to measure 9.
  - Suggested wording: "…not shown to differ from the prediction — which is not the same as no difference."
- **P2-3.** Copy that describes the decision rule goes stale, not just the rate.
  - Affected: `static/docs.html:648-654` ("This is the number that decides"), `:657-658`, `:568-573`, `:775-782`; `CONFIDENCE.md:618-620`.
  - Widen measure 9 to every description of the rule, and add a grep check.
- **P2-4.** The rate is per run, but users try many settings.
  - Copy should give the pooled figure and the worst setting ("about 1 run in 20 overall, up to 1 in 10 at some settings").
  - It should say that trying many settings makes a chance verdict likely, and carry the date, N and interval.
- **P2-5.** The test is calibrated and judged on the same r5 bars. Freeze the block definition and confirm measures 1-3 on a held-out set (a new window or held-out symbols, with its own sha manifest). Quote the held-out figure.
- **P2-6.** As specified, the rate tests rarely fail on today's code.
  - The 99th percentile of Binomial(200, 5%) is 18. At today's synthetic ~7.5%, a 200-run test fails only ~17% of the time (600 runs → 58%, 1,000 → 82%, 1,200 → 90%).
  - Default to N ≈ 1,200 (slow) or the real-bar gate. Keep the fast test, labelled as a regression guard.
- **P2-7.** DROP becomes the main grade users see. It is red (`ui/app.py:2627`) and fires on 18-28% of noise, with no rate in the docs. Either add its measured noise rate and soften its colour in the same release, or record an explicit owner deferral.

### P3
- **P3-1.** Expert tooltip for the p-value: "share of random-direction reshuffles of whole class-stretches that read at least this far". Not "chance it's luck".
- **P3-2.** Report the withheld share next to each judged-only rate, and count withheld runs as no-verdict in the power measures.
- **P3-3.** The restated rate should cite the validator report, its date and the bar-set sha manifest.
- **P3-4.** +3 pts of hit rate at 1.5:1 is ≈ +0.075 R before costs. Keep "before costs" in every new string, and never present the power bar as an economically meaningful edge.
- **P3-5.** Not verified, and relevant only if SONAR is ever distributed: hypothetical performance comes under the SEC Marketing Rule 206(4)-1, FINRA 2210 and ESMA/BaFin retail guidance. As a personal, paper-only tool, there is no evidenced concern.
- **P3-6.** Statistical validity goes to the model-validator: symmetry with 5 unequal classes, 1.5:1 non-complementary outcomes, and n that changes with direction-dependent timeouts.

### What holds up
- The gate can only remove verdicts.
- The size bound comes with an interval, and "beats" ≤ 2.5% is capped separately.
- Measure 2 guards against a circular pass.
- The test is deterministic and reports p, q and B.
- Plain mode gets no new number.
- "Before costs" and "one replay of past prices" stay in the copy.
- P2 priority is defensible.

### Verdict
No P0. Two P1s (the third copy state, and the measured Goal) must be fixed in the spec before the gate. The P2s are about copy and test honesty. Statistical validity and regulatory questions go to the model-validator and to a qualified human respectively.

## Pass 2: Architect (spec "## Architecture" + `docs/adr/0003-sign-randomisation-gate.md`)

Status of the Define findings:
- P1-1 and P1-2 are resolved (spec :22-24, :25, :46, :74-79, :139-147; arch :160, :224-243; tests §11.3-4).
- The other Define P2s are resolved, except DROP (P2-7), which is open and waiting on the owner.
- The prototype's held-out set is partial (see P3-D).

### P0
None.

### P1
- **P1-A. The false-rate copy has no defined basis, and the prototype does not support "about 1 run in 20".**
  - Evidence:
    - The gated clustered coin reads 6.0% [3.7-9.7] (CB 3.2-8.4, arch :345), which fails measure 1's own bar at prototype scale.
    - Held-out shifted and 4h coins read 6.7% (n=75, :360).
    - Measure 2 allows 7.5%.
    - Slower-than-4h patterns are unguarded ([A14]).
  - Fix:
    - The copy quotes the worst held-out figure across measures 1-2, with N and interval, rounded conservatively.
    - It names its scope ("directions picked at random over stretches of up to four holding periods; longer-lasting patterns can beat the bar more often by chance").
    - Remove the pre-filled "1 in 20" from spec :68.
    - Restate ADR :63 as "a false rate measured for named placebos; slower patterns are a stated residual".
    - If full scale fails, the copy states the measured figure, not the target.

### P2
- **P2-A.** The bare word "unconfirmed" (spec :139, the Terminal) implies that verdicts which pass are "confirmed".
  - Use "not told apart from chance" or "inconclusive" in user copy. `confirmed` can stay as an internal field name.
  - Pin that the beats/below/KEEP/INVERTED strings never say "confirmed" or "verified".
  - Grey is right.
- **P2-B.** Volatility INVERTED survives the gate (randomisation p 0.032 and 0.007, arch :387), yet spec :4 still cites it as the harm this change addresses.
  - Restate :4.
  - Copy and the Learn tab must say the check does not cover traits fixed per instrument.
  - Measure 10 names the two grades. Record the residual in CONFIDENCE.md.
- **P2-C.** The expert view shows the two-sided `p`, which can be small from the opposite tail next to "unconfirmed" (arch :193-195, :223, :290; spec :147). Show `p_tail` ("in the direction of Δ"), or both labelled, and pin it.
- **P2-D.** Power sits at the bar: 32/40, Wilson ≈ [65-90]%; clustered 29/40 ≈ [57-84]%. There is no fail plan.
  - If measure 5 fails, the gate still ships, but the power copy is withdrawn.
  - Add `static/docs.html:669-674` ("What it can detect") to measure 9.
- **P2-E.** DROP (carried over from Define P2-7). The owner answers open question 7. If (a), record a backlog item with a P3 spec, and a CHANGELOG line.

### P3
- **P3-A.** Measure 9 misses `CONFIDENCE.md:600` and `static/testplan.html:246`. List `sonar/engine.py:640` (model_vs_market, a non-goal) as reviewed and out of scope.
- **P3-B.** Component UNCONFIRMED copy: "looks like it ranks setups (or ranks them backwards) on this replay, but…".
- **P3-C.** The held-out momentum "beats" (H5 h20, p 0.008) stays out of all user copy.
- **P3-D.** H5 is cut from the same 10y bars and has n=75. Do not quote it. Use the fresh window or held-out symbols.
- **P3-E.** Copy should say that nearby settings can disagree.
- **P3-F.** The 31/400 gate test is a gate against today's code (7.75%), not proof of 5%. Its docstring should say so.

### Verdict
No P0. Define P1s are resolved. There is one new P1 (the basis of the rate copy), which must be fixed in measure 9 and ADR :63 before the gate. The P2s are wording and residual disclosure. Statistical validity at full scale goes to the model-validator.
