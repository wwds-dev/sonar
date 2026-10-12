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

## Pass 3: Review (`git diff 049b930..HEAD`)

The reviewer ran the non-slow tests in the 3 affected files offscreen: 120 passed. Slow tests and native mode were not run.

### P0
None.

### P1
- **P1-1. The `CHANCE_VERDICT_RATE` placeholder renders literally in every "beats" verdict, and nothing blocks its release.** (`sonar/backtest.py:160`, `:999`; `tests/test_backtest.py:708-717` actually asserts the placeholder.)
  - Fix: add a release-blocking check that fails while `{` appears in the constant or in any `_verdict(…,"beats")` output.
  - The figure that replaces it is the validator's worst held-out false-verdict figure across measures 1–2, rounded conservatively (N = floor(1/rate)); if it misses 5%, the miss is stated.
  - Date, N, interval, withheld share, report and manifest go in the Learn tab and CONFIDENCE.md.

### P2
- **P2-1.** The copy says "this verdict", but measures 1–2 measure any verdict (pooled; beats-only is ≤ 2.5%). Spec measure 9 ("worst held-out") and Design :158 ("pooled + worst setting") disagree. Either say "a verdict either way" and fill the slot with the worst pooled held-out rate, or keep "this verdict" and fill it with the worst beats-only rate. Add "up to 1 in M at some settings" if a judged cell is materially worse.
- **P2-2.** The per-instrument residual is shown in plain mode only (`ui/app.py:3001`). The volatility INVERTED "why" line is shown in both modes without it. Add a both-modes line ("does not cover traits fixed per instrument, such as volatility") and pin it.
- **P2-3.** A15 puts the Terminal 60d line on 10y of today's (survivor) watchlist, with no survivorship clause in the Terminal. Per-instrument drift is a fixed trait that random stretch swaps average out, so it may pass the gate (not verified).
  - The validator should measure a long-only / drift placebo at 10y h20/h60.
  - Add a survivorship clause to the Terminal footer.
  - The tooltip at `:1952-1953` is untrue for the 250-day profile, which is always withheld.

### P3
- **P3-1.** The expert p explanation is off by 2× (`ui/app.py:2900-2903` vs `randomisation.py:164`).
- **P3-2.** The attribution `p_rand` is shown raw next to BH-based grades. Add "(before the correction for testing four components)".
- **P3-3.** The "below" copy is internally tense (`backtest.py:1003-1008`).
- **P3-4.** Two pass-2 items are still open: the slower-pattern residual and "nearby settings can disagree". They belong at least in the Learn tab and CONFIDENCE.md.
- **P3-5.** The `few_clusters` fix "a longer range" does not apply in the Terminal.
- **P3-6.** Spec :156 and :293 still say "independent stretches". The code correctly says "separate".

### Checklist
- No user string says "confirmed", "verified" or bare "unconfirmed" (pinned).
- "Not told apart from chance" is grey and correct.
- `few_clusters` copy is fine.
- "Before costs" is kept.
- `p_tail` is expert-only and labelled.

### Verdict
No P0. One P1: the placeholder, which needs a release-blocking check. The new copy holds. P2s: the rate-slot semantics, the expert-mode residual, and A15 survivorship.

## Pass 4: Review of fix loop 1 (`git diff a0b4fdf..HEAD -- sonar ui`)

The reviewer ran 32 targeted non-slow tests offscreen; all passed.

### P0 / P1
None.

### P2
- **P2-1. The Lab still judges 10y**, where r7 measured the fixed-direction residual at its worst:
  - per-symbol coin at 10y h20–h60: 22.5–31% on r5, 10–12.5% on held-out;
  - long-only reads "beats" at 10y h20.

  The Lab's `few_clusters` fix also says "A longer range…" (`backtest.py:1009`), and the Lab has no survivorship line.
  - The owner must say whether "withhold 10y" covers the Lab.
  - Then either withhold 10y in `summarise`, or caveat it with the r7 figures and a survivorship line.
  - Either way, reword the Lab's `few_clusters` fix.
- **P2-2. The expert attribution line says "four components"**, but BH runs over the components actually measured, usually two (`ui/app.py:2988-2989`; pinned at `tests/test_lab_tab.py:880`). Use "{n} components measured".
- **P2-3. The Learn tab and CONFIDENCE.md still carry the old rule and the r5 figure** (`static/docs.html:650-656`; `CONFIDENCE.md:617-625`). Must land in Document before Release, with:
  - the r7 provenance;
  - the measure-2 disclosure;
  - the slower-pattern residual;
  - "nearby settings can disagree";
  - the fixed-per-instrument line.

### P3
- **P3-1.** The fixed-per-instrument line uses the wrong verb after "below", and can read as a buy-and-hold tip. Suggested: "A direction fixed per instrument, such as always long, can also land outside the bar, because the list holds today's survivors; this check cannot see that."
- **P3-2.** An untested component is labelled "not told apart from chance", but its "why" text says the check did not run. Give it a separate label.
- **P3-3.** The KEEP/INVERTED "why" lines lack "before costs" (`backtest.py:1585-1596`).
- **P3-4.** Spec :161 and :298 still say "independent stretches".

### Verdict
No P0/P1. Every headline string traces to r7. Before merge: fix P2-2, and get the owner's answer on P2-1. P2-3 belongs to Document.
