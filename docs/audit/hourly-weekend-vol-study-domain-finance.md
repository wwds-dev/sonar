# Domain review (Finance), Define phase: hourly weekend / hour-of-week vol study

Spec: `.claude/worktrees/agent-a8db6a84aa271e26c/docs/specs/hourly-weekend-vol-study.md` (draft, owner approval pending)
Ground truth read: `docs/company/app-context.md` (Domain specialist section and Invariants present),
`docs/playbooks/domain-finance.md`, `docs/research/2026-10-industry-techniques-shortlist.md`,
`sonar/research/hourlyvol.py`, `sonar/research/stats.py`, `tests/test_hourlyvol.py`.
Date: 2026-10-13. Reviewer is not a lawyer or statistician of record; items for a qualified human are flagged.

Playbook note: `docs/playbooks/domain-finance.md` is `status: baseline` (last-reviewed 2026-10-12, 1 day old).
It is seeded, not radar-verified; treat its guidance as unverified. It has nothing on research-study
methodology, so the statistical points below come from the app's own Invariants (multiple testing,
look-ahead, calibration sample size) and general practice (background knowledge, not verified this session).

Overall: the spec is unusually honest. It makes no edge, profit or certainty claim, says a DROP is a
success, labels the evidence as one unreviewed repo at a daily horizon, and keeps the live engine out
of scope. No copy-level violation found. The problems are that the pre-registration is not yet
actually fixed, and that several of its rules are ambiguous, mis-specified or untested for size.

Counts: P0 0, P1 6, P2 8.

## P0
None. No wording implies edge, profit or certainty; nothing user-visible; paper/real-money invariants untouched.

## P1

### P1-1. "Fixed before any run" is not yet true, and nothing enforces it later
- Spec lines 36-37, 67-71, 122-129. The spec states the rule is "committed to this file before any real-data run",
  but status is draft and five numbers the rule depends on (family size/alpha, 1.0% threshold, V2 window,
  weekend definition, run timing) are still open questions to the owner. Repo rule: do not commit without being asked,
  so there is no timestamped freeze.
- Rule concerned: pre-registration practice and app-context Invariant "multiple testing" (not verified against an external standard).
- Scenario: the thresholds get chosen after someone has seen B0 or V1 numbers on the same 730-day pull. The spec's own
  risk list (line 123) admits the owner has already seen B0 on this history.
- Fix: make approval of the answers to questions 1-5 the freeze point. Record the approving commit hash in the spec and in
  the result block, and have the runner print that hash and refuse to run if the spec file differs from it. Also fix the data
  cut-off date (end of the 730-day pull), since `fetch_hourly` pulls "now minus 730 days" and a re-pull on another day is a different sample.
  Say plainly in the result block that the sample is already seen: the result is exploratory confirmation, not a clean holdout.

### P1-2. V2's window is confounded with its profile (the GARCH artefact the repo already caught once)
- Spec lines 46-50. V2 uses 4368 h, B0 uses 1440 h. A V2 win could come from a longer, less noisy estimation window (and slower adaptation
  of the seasonal level), not from weekday structure. `hourlyvol.py:304-310` and the daily study already rejected a win on exactly this ground ("effective sample size").
- C1 (constant volatility) cannot catch this, because on a flat series V2 with 26 obs per cell should lose; the artefact appears on real, time-varying data.
- Scenario: a KEEP is read as "weekday structure matters" when it means "a longer hour-of-day window helps". A later spec wires in the wrong thing.
- Fix: add a pre-registered decomposition diagnostic, B0L = 24-cell hour-of-day on the 4368 h window. Either require V2 to beat B0L too
  (then the family is 3, alpha 0.05/3 = 0.0167, stated now), or report V2 vs B0L as a non-gating attribution line and forbid the words
  "weekday effect" in the result unless V2 also beats B0L. Same question for V1: B0 vs V1 share a window, so V1 is clean on this point.

### P1-3. The DM / p-value specification is internally inconsistent about sidedness
- Spec line 59-61 asks for a "one-sided" p < 0.025 using `stats.normal_p`. `sonar/research/stats.py:93-95` `normal_p` is **two-sided** (`2*(1-Phi(|t|))`).
  Used as written, p<0.025 two-sided equals one-sided 0.0125, silently stricter than Bonferroni 0.05/2; or if halved, the sign convention matters
  (it also returns the same p for a V that is worse than B0).
- Scenario: the implementer picks one reading after seeing a borderline result. This is a researcher degree of freedom inside a pre-registration.
- Fix: write the formula: t from `newey_west_t(d)` with d_t = loss_B0 - loss_V (positive = V better), p = 0.5*normal_p(t) if t>0 else 1-0.5*normal_p(t).
  State the family alpha explicitly (spec never says the 0.05 is one-sided 0.05; line 69 implies it).

### P1-4. The HAC lag (24) and the DM asymptotics are weakly justified for this loss differential
- Spec line 61. The differential V2 minus B0 is concentrated on specific weekday-hours, so it has structure at lag 24 and especially lag 168, which a
  24-lag Bartlett window (`stats.py:84-86`, weights fall to 0 at lag 25) does not capture. Standard errors may be too small, p too small. The repo's
  own default rule would give about 9 lags for n=13,150 (`stats.py:81`), so 24 is a judgment, not the cited rule. Single-hour QLIKE is also
  heavy-tailed (|r| floored at `MIN_VOL`=1e-6 gives a loss near 16 on a near-zero hour, `hourlyvol.py:61,82-84`), so a normal reference for t is optimistic.
  Also, V1/V2 nest B0 and are estimated on a rolling window; the normal DM reference is standard for fixed rolling windows (Giacomini-White
  framing) but is not verified here.
- The existing module docstring (`hourlyvol.py:29-31`) says no HAC is needed for this loss. The spec reverses that without saying so; reconcile.
- Fix: pre-register lag 168 as the gate (or require p<0.025 at both 24 and 168), and add the existing moving-block bootstrap (`stats.bootstrap_ci`) on the pooled
  differential as a second, non-gating sanity line. Needs a qualified statistician's glance (flag).

### P1-5. The control gate "at most 1 of 20 seeds with DM p < 0.025" is poorly calibrated, and the controls are under-specified
- Spec lines 76-77 (C1), 78-82. For a correctly sized test at 0.025, P(2 or more of 20 rejections) = 8.8% (binomial, my arithmetic). With V1 and V2 both
  gated that is about 17% chance of a false alarm that "voids" the study; read as per-variant it is about 9%. With 20 seeds it also cannot detect a mild size
  distortion. Unstated: N for C1/C2/C3 (must exceed 4368 + a few thousand scored hours for V2 to score at all); the seeds; whether "1 of 20" is per variant or total;
  runtime on "every build" (20 seeds x ~18k hours x 168-cell profile).
- C2 (>=3% improvement) and C3 (KEEP) thresholds are set without any run. My rough, hand-derived estimate (not run, Gaussian approximation) says a 1.5x weekend sigma gives
  roughly a 3-4% pooled QLIKE gain over a no-weekend forecaster, so 3% is borderline and may fail on a faithful implementation, tempting a retune after the fact.
  The same arithmetic says a 1.0% pooled gain needs weekend variance to differ from weekday by roughly a third. C2 uses a planted effect far larger than any plausible real one,
  so passing C2 proves nothing about detecting a 1% effect (see P2-2).
- Fix: fix seeds and N in the spec; make the C1 size check a fixed-seed regression with a stated per-variant rule and a larger seed count (e.g. 200, offline, marked slow) or drop the count rule and assert only pooled-QLIKE >= 0.995 x B0 plus not-KEEP, as the existing test does (`tests/test_hourlyvol.py:46-57`). Add a smaller planted effect (weekend sigma 1.1x) to C2 and report the detection result (not gate on it) so the owner sees the study's real resolving power.

### P1-6. V1 is not specified precisely enough to be one estimator (a hidden degree of freedom)
- Spec lines 40-45. Open points: (a) "clamped to PROFILE_CLAMP" - each factor separately, or the product (range 0.0625 to 16)?; (b) the weekend factor is computed from
  **deseasonalised** r^2 while the hour-of-day factor in `_Diurnal.factor` (`hourlyvol.py:154-162`) is computed from **raw** r^2, so weekend hours are over-represented
  in some hour cells in a given window and the two factors overlap; the order/circularity is not defined; (c) the weekend class is by the **target** hour's UTC open time, and the
  study aligns returns to `times[1:]` (`hourlyvol.py:218`), so the weekday must use the same shift or the Sunday/Monday boundary is off by one hour (Unix day 0 is a Thursday, and the test series start at t=0, `tests/test_hourlyvol.py:32-36`); (d) behaviour when the window holds fewer than N weekend hours.
- Scenario: the shipped-equals-measured guarantee (P1-1 lesson, spec line 44-45, test at `tests/test_hourlyvol.py:128-145`) fails silently for the weekend term,
  and a later production port differs from what was measured.
- Fix: write the V1 and V2 estimators as pseudocode in the spec and extend the existing equivalence test (C4) to V1 and V2 against a `forecast()`-style path, not only "factor forced to 1.0".
  Add a boundary test: Sunday 23:00 UTC is weekend, Monday 00:00 UTC is not, in the same convention as `hods_from_times`.

## P2

### P2-1. Verdict rule has gaps and a confusing WEAK definition
- Spec lines 56-66. Improvement in (0, 1.0%) with p < 0.025 matches neither KEEP, WEAK nor DROP. WEAK says "block count is 4 of 6 or fewer than 5" (redundant; also admits 0-3 of 6).
  A failed control (condition 4) yields no defined label. The existing `Verdict.verdict` (`hourlyvol.py:174-186`) compares against trailing-72 and has no pooled-threshold or DM term, so the spec needs a new B0-relative class.
- Fix: a total truth table over (improvement bucket, blocks won, p, controls). Add the label "NOT RUN (control failed)". Suggest a label for small-but-significant ("DETECTED, BELOW THRESHOLD").
  Note blocks are `n//6` wide and drop the remainder (`hourlyvol.py:268`); state it.

### P2-2. The 1.0% threshold and 5-of-6 rule: defensible as conventions, not as derived, and the "worthwhile" claim is not connected to the user
- The spec admits 1.0% is a judgment (line 58, 112). 5-of-6 mirrors `Verdict.verdict` (`hourlyvol.py:184`), which is a fair consistency choice, but 5/6 is a weak block test (P(>=5 of 6) under a coin flip is 7/64 = 11%), so it is not a multiplicity control on its own; the DM p and Bonferroni carry the weight. Blocks of 91 days are few and autocorrelated across regimes.
- A 1% pooled QLIKE gain is not tied to its effect on the displayed probability `prob_up`. Mis-scaling sigma by a few percent moves P(up) very little for hours where |ln(c/o)| is small.
- Fix: before any run, convert 1.0% into an effect on `prob_up` (for example the mean absolute change in displayed P(up) between B0 and V on the scored hours), and report it. Then the owner approves a number in the unit the user sees. Run a power simulation at 1.05x to 1.3x weekend sigma and report it as context (stated as "not detected here" semantics, as the spec already says line 112-113).

### P2-3. Multiple-testing accounting is sound for 2 comparisons but leaves hidden variants outside the family
- Spec lines 68-72. Family of 2 and Bonferroni 0.025 is conservative and fine, provided P1-2 (B0L) is settled. Three further things sit outside it: (a) the UTC weekend boundary is a flagged third variant (line 116-117), good, but the report should state that any Asia/US-aligned boundary result found later is exploratory; (b) the reporting of other models beside V1/V2 (garch, trailing72) in the shared `study()` output must not be read as extra hypotheses; (c) the earlier five-model study on the same data is excluded from the count (line 70); state why in one sentence: same dataset, different question, so the earlier selection (ewma_diurnal chosen over garch, `hourlyvol.py:304-310`) does bear on B0 being the best-of-five baseline, which makes B0 harder to beat and biases against V, not for it. That is conservative, so acceptable, but say so.
- Benjamini-Hochberg skipped for n=2: fine.

### P2-4. Look-ahead check: the design is causal on paper, but needs explicit tests
- The existing profile is causal (factor read before `push`, `hourlyvol.py:249-254`). For V2 the 4368 h warm-up (line 51) plus scoring "starting after the longest warm-up" is right and removes a leakage route (V2 scored on an incomplete window). Check also that the *scoring set is identical* for all models and that V1/V2 state is updated only after the hour is scored.
- Fix: add a causality test that perturbs the return at hour i and asserts that forecasts for hours <= i do not change (for V1 and V2). The fixed 26-week window itself was chosen with knowledge of the 24-cell noise argument but, per the spec, not tuned on data; keep it stated as such.

### P2-5. Data provenance claim in the spec is inaccurate
- Spec lines 106-108: "`fetch_hourly` errors on an incomplete pull". `hourlyvol.py:381-412` errors only on a failed page (exception). It does not check contiguity of `times`, and `study()` does not check `b - a == 3600` (only `forecast()` does, `hourlyvol.py:338`). A silent interior gap (exchange maintenance) makes a 2-hour return labelled as one hour and shifts the weekday/hour alignment for everything after it, which matters more for a weekday cell than for a 24-cell profile. `log_returns` also drops non-positive closes, which shifts alignment unless lengths mismatch (`hourlyvol.py:219`).
- Fix: correct the sentence; add a contiguity assertion to the new study path; record the Binance endpoint, symbol, first/last bar times, count of bars and a hash of the pulled series in the result block so the figure is traceable (playbook: every figure traceable to source and timestamp).

### P2-6. Evidence honesty: good, with three small tightenings
- Spec lines 22-24 correctly states one unreviewed repo, daily horizon, no EWMA comparator. Tighten: (a) the shortlist's "[V]" means three independent agents confirmed the repo states the number, not that the number is correct or reproduced (shortlist lines 12-14); say "reported by" (the spec does) and never "verified" in the result note; (b) the spec cites 15% only; the shortlist also lists a per-weekday dummy of about 22%; mention it, since it is the basis for testing V2; (c) the weekend effect might also be a daily-aggregation artefact of 5-minute realised variance: at the hour horizon EWMA may already absorb it (spec line 26-27 says so, good).
- "[S] 2025 paper, not read" is correctly flagged; do not cite it in the result block.

### P2-7. Wording that edges toward a market view, in a study with no user-visible copy
- Spec line 13-14: "sigma is the only input where SONAR disagrees with the market". This is lifted from code comments and it suggests SONAR holds a view that differs from the market's, which sits next to the "no edge" invariant (app-context lines 5-6, 61-65). The shortlist also says "highest-leverage input". Not copy a user sees, so P2.
- Fix: "sigma is the only input that is estimated by SONAR rather than read from the market price". Keep the existing non-goal line 98-99 ("a better sigma is a better-scaled forecast, not a trading advantage") and carry it verbatim into the result block and docs/audit note.
- The user line (line 30) says "owner-only today" while app-context says users are retail investors without finance training; since the later live spec would reach them, say that the result note must not enter user-facing docs (`static/docs.html`, `ui/words.py`) without Define/Design and this domain review.

### P2-8. Result-reporting duties and timing
- Spec lines 91-92 requires period, sample size and "historical and simulated"; also add cost/slippage treatment ("not applicable: no trading, loss is forecast loss, not P&L") so the playbook's cost line is satisfied and nobody reads QLIKE gain as return. Also add the explicit sentence that this is a forecast-accuracy figure and says nothing about profit.
- Open question 6 (run on the same Mac as the agent during the 30-day clean run): it is a network pull of ~18 requests plus CPU; the risk is low but the answer should be recorded. Not a finance issue; noted for the owner.

## What holds up (checked)
- No claim of edge, profit or certainty; DROP framed as success (lines 36-37, 98-99).
- Paper/real-money invariants and `GOING_LIVE.md` not touched; no UI, no copy, no dependency (lines 92-100).
- Live engine, `model.py`, `forecast()` and the 2026-10-10 to 2026-11-09 clean run are explicitly protected (lines 93-96).
- Scoring starts after the longest warm-up on a common set; profile windows are causal; clamps and windows are fixed, not searched.
- Numbers I rechecked: 1440 h x 2/7 = about 411 weekend hours (ok); 4368/168 = 26 (ok); 17,520 - 4,368 = 13,152 scored hours, 6 blocks of 2,192 (spec says about 2,190, ok); 730 days gives about 104 weekends (ok).
- Not verified: no real-data run was made or attempted (Binance blocked in this sandbox); the power arithmetic in P1-5 and P2-2 is a hand approximation and should be replaced by a simulation in the study.

## Needs a qualified human
- A statistician should review P1-4 (HAC lag, DM validity for nested models under a rolling window, heavy-tailed loss).
- Nothing here raises a securities-law question at this stage; re-run the domain review when any winner is proposed for the live forecast.
