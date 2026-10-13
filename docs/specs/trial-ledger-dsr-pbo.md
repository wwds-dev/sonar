# Spec: Trial ledger, deflated Sharpe ratio and probability of backtest overfitting

- Status: draft (revised after `docs/audit/trial-ledger-dsr-pbo-domain-finance.md`, 8 P1 fixed)
- Owner approval: Define gate approved by the owner on 2026-10-13: "approve both as proposed". Every open question is settled as this spec proposes it. An Architect section and its gate still come before Build.
- Priority: **P2** (research integrity; nothing user-visible; not blocking any release)
- Source: `docs/research/2026-10-industry-techniques-shortlist.md` item 3. PM playbook is
  `status: baseline` (stale: not radar-verified).
- Labels: **[code]** read in this repo; **[mem]** from memory. The papers could not be fetched, so
  every [mem] item is **"verify against the paper before Build"**; `model-validator` recomputes
  the known answers independently from the paper.

## Problem
The owner reading research results cannot answer "how many things have we tried?".
`benjamini_hochberg`/`apply_fdr` (q = 0.10) correct only within one run [code: stats.py]. `study.run()`
returns a dict that nothing persists [code: only `save()`, no caller]; the pre-registered studies
and H1-H3 exist only as prose in `CONFIDENCE.md` 10b and 13 (it speaks of five studies and a
sixth; the count is reconciled at Build). `ic_to_sharpe` is a rough fundamental-law translation
with no sampling error [code]. Harm today is small (all nulls); it matters the first time
something survives.

Challenge: this answers one real question ("is this survivor still unusual given everything
tried?"), adds no feature, breaks no invariant. It must not become a Sharpe-ranking tool; SONAR
has features, not a pool of strategy return streams. Slice 1 = ledger + DSR. Slice 2 = PBO, only
after slice 1 and an owner yes.

## User and goal
User: the owner and advising agents, in internal research output only (never retail users).
Goal: every research run appends its trials; any reported survivor carries N, a DSR
probability, and (slice 2) a PBO.

**Success measure** (numeric, in `tests/`, stdlib only; bounds fixed before looking at output):
1. PSR known answer with nonzero skew and kurtosis (T, SR, g3, g4 chosen so each term matters),
   value computed by hand from the paper, tolerance 1e-6. Kills the T-1, skew-sign and
   excess-kurtosis mutants. (DSR at N = 1 equals PSR(0) holds by construction; kept as a
   consistency check, not as evidence.)
2. SR0 known answers for N = 2 and N = 10 at V = 1, by hand, tolerance 1e-6. N = 1 is a stated
   convention (SR0 = 0; V undefined), pinned by a test and labelled "not from the paper".
3. DSR strictly decreasing for N = 1, 5, 20, 100 at fixed inputs.
4. Noise run, 20 zero-mean series, T = 250, sample V, 4,000 seeds. Reviewer's simulation
   (numpy, not verified by me): best-series DSR > 0.95 in **0.1%**, undeflated PSR > 0.95 in
   **62.8%**, N replaced by N-1 gives 0.25%. Pass requires: DSR > 0.95 in **<= 0.5%** of seeds;
   PSR > 0.95 in **>= 50%**; mean DSR of the best series within **0.02** of the value measured by
   an independent implementation written at Build. The count bound alone cannot catch N-1, so
   the mean-DSR leg is the one that must kill it; QA confirms by mutation.
5. Mutants that must each fail at least one test: drop the `(1-g)` term; swap `g`/`1-g`; T-1 to T;
   skew sign; raw to excess kurtosis; N to N-1 (via leg 4 mean); PBO rank off by one (via the
   tiny-matrix test below). Declared **equivalent, not required**: swapping IS/OOS (the set of
   all C(S,S/2) splits is closed under swap, PBO identical) and `<=` to `<` (with rank r/(N+1)
   and N even-sized median never hit). Per-split PBO function also tested on a hand-built
   S = 4, N = 3 matrix with a known answer.
6. Slice 2 only: iid noise (T = 400, N = 20, S = 16): mean PBO over 50 seeds within 4 standard
   errors of 0.5, SE measured at Build and written down first; MA(19) noise with the embargo on
   gives the same band; planted +0.3 sd trial gives <= 0.05; a weak planted trial gives an
   intermediate PBO computed independently. State whether each uses one seed or a mean.
7. Ledger: 1,000 appends from two processes (with the lock) re-read as 1,000 records, chain
   `verify()` clean; a forked chain, a gap, a truncated line or a deleted tail makes `verify()`
   report failure, and report generation then **refuses to print N** (fail closed).
8. New module branch coverage >= 90% (repo floor 80%).

## Scope (all formulas [mem], verify against the paper before Build)
New `sonar/research/overfit.py`, stdlib only. Inverse normal CDF: `statistics.NormalDist().inv_cdf`
(confirm minimum Python at Build); CDF via `math.erf` as `normal_p` does [code]. No edits to
`stats.py`, `study.py`, `validate.py`.
- **PSR** (Bailey, Lopez de Prado 2012): `Phi((SR-SR*)*sqrt(T-1)/sqrt(1-g3*SR+((g4-1)/4)*SR^2))`,
  per-period SR, raw kurtosis. Require T >= 2; if the radicand <= 0, raise (defined, tested).
- **SR0** (2014): `sqrt(V)*((1-g)*z(1-1/N)+g*z(1-1/(N*e)))`, g = 0.5772156649; V = variance of the
  trials' estimated Sharpes in the same per-period units, needs N >= 2.
- **DSR** = PSR(SR0). It is a **probability, not a p-value**: report it as `DSR prob`.
- **PBO via CSCV** (Bailey, Borwein, Lopez de Prado, Zhu 2015): S even blocks (default 16), all
  C(S,S/2) splits; IS argmax `n*`; relative OOS rank `w = r/(N+1)` with **rank 1 = worst, N = best**
  (pin both; the other choices flip PBO to 1-PBO or give infinite logits); `logit = ln(w/(1-w))`;
  `PBO = share of splits with logit <= 0`. **Embargo of `horizon` periods at every block boundary**
  (as `study.split` does for the same overlap reason [code]). Label it "selection stability across
  blocks", not "probability the strategy is overfit".
- **DSR on overlapping IC series (decision, not deferred):** do not use raw n_dates as T. Take
  `SR_hat = t_NW / sqrt(n)` from the Newey-West t already computed [code], so
  `sqrt(T-1)*SR_hat` keeps the HAC correction; g3, g4 computed on block-averaged (non-overlapping)
  ICs. This is IC-based, a rank-correlation information ratio, **not a return Sharpe, gross of
  costs**; the report line says so. Final method confirmed by `model-validator` at Architect.
- **Ledger:** JSON Lines, append-only, `docs/research/trial-ledger.jsonl`, in git (not
  `SONAR_DATA`, which belongs to the running app). Written only by research scripts through
  `ledger.append()`; engine, agent, scoring and calibration never import it. Append takes an
  exclusive `fcntl.flock` around read-last-line + write. Record (nulls allowed, since `evaluate`
  returns None under 30 dates): date, study slug, variant, family, horizon, universe, explicit
  start/end dates and data snapshot (not `rng="5y"`), n_dates, mean_ic, **sd_ic, skew, kurt**,
  t_stat, p_value, `kind` (`registered`|`reconstructed`), `git_sha`, `git_dirty`, `prev_sha256`.
  `is_control` is derived from `family == "control"` [code: study.py:73], not set by the writer.
- **Trial** = one (variant, horizon, parameter set, universe, explicit date range) whose result was
  computed and could be read, reported or not, including those failing the 30-date minimum.
  A discovery run and its holdout run of one variant are **one trial**; DSR is applied to the
  discovery selection, never the holdout. Controls logged but excluded from N; report N with and
  without them. N is a **count of logged trials, not an effective number of independent trials**:
  correlated features overstate it, unlogged or reconstructed ones understate it.
- **What the chain proves:** the lines present are in the recorded order and an edit to an earlier
  line is detected only if the head hash was anchored elsewhere (record it in the commit message
  or CONFIDENCE.md per study). It does **not** prove completeness, omitted trials, true field
  values, true dates, or that the tree behind `git_sha` was clean; anyone who can edit can
  recompute later hashes. Git history helps only with force-push and rebase protection (owner
  setting). Report line carries "ledger: chain verified; completeness not verifiable".
- **Report line** (internal research output only): `N logged trials (with/without controls); DSR
  prob = x; window, n_dates, horizon; IC-based, overlap-corrected, gross of costs and slippage;
  historical, not tradable`. No verdict wording and no 0.95 cut-off in the line.
- Backfill: earlier studies entered once as `reconstructed` from prose; counts unverified;
  `features.REGISTRY` size not read for this spec.

## Non-goals
No UI, no README or `static/docs.html` copy; no change to engine, agent, scoring, calibration
or `backtest.py`. The 30-day clean agent run (2026-10-10 to 2026-11-09) must not be disturbed:
files-only change, no bundle rebuild or release before 2026-11-09 (SRE to confirm). No new
dependencies. No strategy ranking. A high DSR prob means only that the result is **not explained
by selection among the N logged tries**; a low one means it is not distinguishable from the best
of N noise draws. Neither says it works, is tradable, or has edge.

## Risks and open questions (**O** = owner decides)
1. N is self-reported and only as honest as the logging; the chain cannot fix omission. **O**:
   accept N as a lower-bound-in-spirit count, with the rule "no study reported unless logged"?
2. **O**: approve the NW-based DSR input above, or restrict DSR to non-overlapping samples.
3. **O**: PBO deferred to slice 2 (its meaning is weaker with features than strategies).
4. **O**: show the Harvey-Liu-Zhu t > 3 hurdle at all? Disputed (Chen 2021 argues too strict)
   [S, snippet-only, unverified]; proposed as context beside N, never a gate.
5. **O**: branch protection against force-push on the ledger's branch.
6. Formula transcription error is the main technical risk (all [mem]); mitigated by independent
   hand-computed known answers and a paper check before Build.
7. Left open (P2, cheap but Architect-level): effective-N clustering; exact snapshot key for
   "identical inputs"; reconciling the five/six study count; PSR/SR0 behaviour for extreme inputs
   beyond the raise.

## Verification plan (qa-engineer)
Both `./run-tests.sh` modes, twice; measures 1 to 8; mutation list above; `git diff` touches only
`overfit.py`, tests, the ledger, `docs/`, CHANGELOG.
