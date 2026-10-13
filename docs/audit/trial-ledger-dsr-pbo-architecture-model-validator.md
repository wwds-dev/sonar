# Model-validator review, Architect phase: trial ledger, DSR (slice 1)

Reviewer: model-validator, 2026-10-13. Read-only; no repo file other than this report was written.
Reviewed: `.claude/worktrees/agent-a3ed0519d39f51b25/docs/specs/trial-ledger-dsr-pbo.md` (cited S:line),
`docs/adr/0004-trial-ledger-format.md`, `docs/audit/trial-ledger-dsr-pbo-domain-finance.md`;
ground truth `sonar/research/stats.py`, `study.py`, `validate.py`.
Playbook `model-validator.md`: `status: baseline` (not radar-verified).
Source honesty: the Bailey/Lopez de Prado papers were NOT fetched by me either. Formula checks
below are from my own knowledge plus numerical simulation; "verify against paper before Build" stays.
All numbers below were produced by scratch scripts (numpy 2.5.3, stdlib NormalDist); scripts not in repo.

## Verdict on the DSR input method (S:75-79, Architecture "Maths API")

**YES, conditionally.** Building `SR_hat = t_NW / sqrt(n)` and calling `dsr(SR_hat, T=n, ...)` is
statistically sound as an approximation: `sqrt(n-1) * t_NW/sqrt(n) = t_NW * sqrt((n-1)/n)`, so the HAC
correction survives and DSR reduces to `Phi(t_NW - t0)` where `t0 = sqrt(n)*SR0` is the expected best
of N null t-statistics. Because SR_hat is about 0.03 to 0.1 per period, the skew/kurtosis terms in the
denominator change DSR by well under 1%; they are harmless but immaterial for IC series (block means
tend to skew 0, kurt 3). Conditions that must be in the spec before Build: P1-1, P1-2, P1-3, P1-5.
Without P1-2 and P1-3 the answer would be NO.

## Findings

### P0
None.

### P1

**P1-1. N and V scope is undefined (S:89-93, S:209-212; ADR has no definition).** A reader cannot tell
whether N is (a) every non-control row in the ledger ever, (b) rows up to the survivor's `seq`, or (c) one
run. Under (a) the same survivor's DSR changes when unrelated later trials are logged, so a printed number
is not reproducible. Same for V ("over the counted non-control trials with a non-null t"): ledger-wide mixes
horizons, universes and window lengths. Fix: define N = count of distinct `trial_key`s with `seq <=` the
reported row's `seq` (state it), and print `seq`/ledger head in the report line. Pin V's population the same way.

**P1-2. V mixes units across trials with different n_dates (S:209-212).** `SR_hat = t/sqrt(n)`; under the null
`Var(SR_hat) ~ 1/n`, so trials with 250 and 1,250 dates have different SR scales. A ledger-wide sample
variance of SR_hat is then a blend that fits no single trial, while `sr` and `T` belong to one trial.
Fix: compute V on the dimensionless t (sample variance, ddof 1, over the counted trials) and pass
`var_sr = V_t / n_selected`. Keep the same set for N and V. Also pin the minimum count of non-null t's
(V from fewer than about 10 values is unusable; at N = 2 V has one degree of freedom).

**P1-3. Sign orientation and two-sided selection are unspecified (S:209-212; stats.py:160-166, study.py:79).**
DSR's SR0 is the expected maximum of N signed draws. Features are pre-registered with `expected` = +1/-1,
so SR_hat must be oriented (`expected * t`) before taking V and the max. For `expected == 0` (selected by
|t|, the volatility survivor class) the right null is the max of |t|, roughly N -> 2N; using signed SR0 flatters
the result. The ledger record (S:84-86) does not store `expected` or `n_obs`. Fix: add `expected`; orient
SR_hat; for `expected == 0` either refuse DSR or use 2N and say so.

**P1-4. Success measure 4 mean-DSR leg cannot kill N -> N-1 as the spec claims (S:41-44).** My run
(20 zero-mean N(0,1) series, T = 250, sample V ddof 1, 4,000 seeds; own code): best-series DSR > 0.95 in
0.025% (1/4000) of seeds (reviewer: 0.1%); PSR > 0.95 in 63.0% (reviewer 62.8%, agrees); N-1 gives 0.05%.
Mean DSR of the best series: 0.4951 (correct) vs 0.5032 (N-1); difference 0.0081, which is **inside the
0.02 tolerance**, so the leg passes the mutant. The count bound (<= 0.5%) also passes it. Likewise T-1 -> T
shifts mean DSR by 1.4e-5 at T = 250. Fix: compare per seed against the independent implementation on the
same generated data (tolerance about 1e-9, not 0.02); keep the count bounds only as gross-bug guards.
Kill T-1 -> T and similar only with a small-T known answer (T about 10 to 30), where the term matters.

**P1-5. NW t is anti-conservative at small n; DSR inherits it (S:75-79).** `evaluate` uses
`lags = max(overlap, 5)` (stats.py:181). Simulated null IC series, MA(19) (daily sampling, horizon 20),
20 series per run, 300 runs per row, own code, DSR built exactly as specced with V from the 20 series:

| n_dates | var of NW t under null (should be 1) | best-of-20 DSR > 0.95 | naive iid PSR > 0.95 |
|---|---|---|---|
| 250 | 1.96 | 5.0% (15/300; Wilson 95% about 3.0% to 8.1%) | 100% |
| 1,250 | 1.57 | 0.7% (2/300; interval wide) | 100% |

So the overlap correction fixes the gross problem (100% to under 1% at 1,250) but at n/horizon about 12 the DSR
false-pass rate is roughly 50 times the iid-theory 0.1%. The sample V partly absorbs the inflated spread, not
fully. Fix: a minimum `n_dates / horizon` (my two data points support about 60, not a derived threshold) below
which the report prints "DSR not computed: too few independent windows"; add the n/horizon figure to the line.
Add a measure that runs this overlap simulation at the repo's lags and records the measured rate.

**P1-6. Known-answer plan's paper-independent oracle is mis-specified (S:216-218).** "`expected_max_sr(n,1)`
within 3% of the Monte-Carlo mean of the max of n normals for n = 2, 10, 100". SR0 is an approximation.
Measured (40,000 draws): N = 2 formula 0.5198 vs true 0.5668, **-8.3%** (the correct formula fails the 3% test);
N = 10: 1.5746 vs 1.5356, +2.5%; N = 100: 2.5306 vs 2.5085, +0.9%. Worse, the g <-> 1-g swap mutant gives
-2.6% at N = 10 and -1.3% at N = 100, **inside** 3%, so the oracle would not catch it. Either the build
fails correct code and someone widens the test, or it passes the mutant. Fix: use the oracle only as a sanity
band with per-N pre-registered bounds (N = 2: -9% to -7%; N = 10: +2% to +3%; N = 100: +0.5% to +1.5%),
and rely on the 50-digit hand values at 1e-6 for transcription (those do separate g from 1-g: N = 10 differs
by 5%). Record the true E[max] by quadrature, not by MC, to avoid MC noise in the bands.

### P2

**P2-1. Controls in or out of N (S:92).** Excluding lowers N, which lowers SR0 and flatters DSR (anti-conservative).
Size: SR0 ratio N = 20 vs 18 is +2.5%; 25 vs 22 is +2.8%; 8 vs 6 is +12%; 3 vs 2 is +64%. Small for a full run
(about 25 trials), large for small N. `is_control` derived from `family == "control"` removes the mislabel
route (good, S:86-87). But the spec says "report N with and without" and the report line has one DSR
(S:100-103): which N feeds it? Fix: primary DSR uses N **including** controls (conservative direction, cannot be
gamed by labelling), the excluded-controls figure is secondary. Separately, controls are known-null draws:
log `sd(t)` of controls versus 1 as a calibration check on V (study.py:114-130 shows the repo already found the
random control at t = -1.87).

**P2-2. Effective N is not modelled and the two errors do not cancel.** Raw N overstates independent trials
(correlated features, overlapping horizons: stats `control_reference` docstring notes cross-sectional drift) but V
from correlated trials is compressed, and unlogged trials understate N. The report label "count, not
effective number" (S:92-93) is right; add that direction of net bias is unknown, so DSR is neither a bound nor
conservative. Do not describe it as a lower bound anywhere.

**P2-3. skew/kurt from block-averaged ICs use a different series than SR_hat (S:77, Architecture "Ledger file").**
SR_hat is per-date and HAC-scaled; g3/g4 describe block means of length `horizon`. Immaterial numerically
(see verdict) but with 3 to 4 years there are only about 40 to 60 blocks, so g4 is very noisy. State in
the spec that they are inert for IC inputs and cannot move DSR materially; do not read them as evidence of
normality. Add a test that the radicand stays positive for the observed range of SR_hat and kurt.

**P2-4. Known answers are not independent of the spec author's memory (S:215-221).** Papers cannot be fetched;
the validator transcribes from memory too, so a shared misremembering passes. Mitigations in the plan are good
(50-digit constants, structurally different independent implementation, MC band after P1-6). Add: label every
constant "from memory, unverified against paper" until the owner or a human checks the paper once; a wrong formula
that is internally consistent would then be flagged, not "proved". My own recollection agrees with the
spec's PSR (raw kurtosis, T-1) and SR0 formulas (g = 0.5772156649, z(1-1/N), z(1-1/(Ne))); that is not
independent confirmation.

**P2-5. T-1 mutant needs a small-T case, PSR mutants need a case where each term matters (S:33-35).**
Spec says so for skew/kurt; apply the same to T (shift is 0.2% at T = 250). Use T about 12, SR about 0.5,
g3 = -0.7, g4 = 5, and assert each mutant moves the result by more than 1e-3.

**P2-6. Windows and discovery row (Architecture "Items left open" 2).** `study.split` trims the holdout with a
calendar-day gap (study.py:55); `n_dates` for the discovery row is shorter than the 5y panel. Store the actual
IC count used (already `n_dates`) and never reuse the panel date count. The `rerun`/data-revision rule (first
record wins) means a re-run on revised data that turns a null into a survivor is ignored; flag it in the line.

**P2-7. Layering.** Importing `validate._ic_series` (private, Option A) is acceptable only with the signature test
named in the spec; a change in `_ic_series` filtering (>= 8 names, validate.py:53) silently changes `n_dates`.
Pin by a golden-series test. (Code-quality point, flagged for code-reviewer.)

## Claim-by-claim verdict

| Claim | Verdict |
|---|---|
| NW-based `SR_hat` keeps the HAC correction in `sqrt(T-1)*SR_hat` (S:75-79) | Supported algebraically; supported only at large n/horizon by simulation (P1-5) |
| DSR input method sound | Supported with conditions P1-1/2/3/5 |
| N defined so a reader cannot be misled | Unsupported (P1-1) |
| V defined consistently | Unsupported (P1-2) |
| Excluding controls is harmless (S:92) | Partly: small for N about 25, material for small N (P2-1) |
| Measure 4 count bound can fail (S:41-44) | Supported only for "no deflation at all"; does not catch N-1 (P1-4); reviewer's 0.1% and 62.8% reproduced approximately (0.025%, 63.0%) |
| Mean-DSR leg "must kill N-1" (S:43-44) | Unsupported (diff 0.008 < 0.02) |
| MC oracle within 3% (S:217) | Unsupported (P1-6) |
| Hand 1e-6 known answers catch transcription error | Supported for g/1-g swap, skew sign, kurt type, (1-g) drop, given the PSR case in P2-5; shared-memory risk remains (P2-4) |
| SR0 / PSR / DSR formulas | Unverifiable against paper (not fetched); consistent with my recollection |
| Chain limits stated honestly (S:94-99, ADR) | Supported (no overclaim found; "completeness not verifiable" is explicit) |
| Report line carries no verdict wording | Supported; add n/horizon, seq, ledger head (P1-1, P1-5) |

## Reproduction log (two headline numbers from raw simulation)
1. Reviewer's 62.8% undeflated PSR > 0.95: mine 63.0% (4,000 seeds, N(0,1), T = 250). Reviewer's 0.1% DSR > 0.95:
   mine 0.025% (1 event); consistent in kind, both far below the nominal 5%, which confirms the domain
   reviewer's point that the threshold barely discriminates.
2. SR0 vs E[max of N normals]: N = 2 -8.3%, N = 10 +2.5%, N = 100 +0.9% (P1-6).
3. Overlap sim table in P1-5.

## Ranked summary
P0: 0. P1: 6 (P1-1 to P1-6). P2: 7. DSR input method: YES, conditional on P1-1, P1-2, P1-3, P1-5.
