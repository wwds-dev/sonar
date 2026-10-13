# Spec: Trial ledger, deflated Sharpe ratio and probability of backtest overfitting

- Status: draft (revised after `docs/audit/trial-ledger-dsr-pbo-domain-finance.md`, 8 P1 fixed)
- Owner approval: pending (Define gate)
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
   PSR > 0.95 in **>= 50%**; and, per seed, DSR of the best series equal to an independent
   implementation (written at Build by `model-validator`, same generated data) within **1e-9**.
   Architect revision: the old "mean DSR within 0.02" leg cannot kill N-1 (measured mean DSR
   0.4951 vs 0.5032, gap 0.008 < 0.02), and the count bound passes it too; the per-seed
   comparison is what kills N-1. 4b: MA(19) overlap noise, horizon 20, 20 series, 1,000 seeds:
   at n = 1,250 DSR > 0.95 in <= 2% (measured 0.7%); at n = 250 DSR is "not computed" (n/horizon
   < 60; measured false-pass 5.0%), rate recorded only. T-1 vs T is killed by a small-T known answer.
5. Mutants that must each fail at least one test: drop the `(1-g)` term; swap `g`/`1-g`; T-1 to T;
   skew sign; raw to excess kurtosis; N to N-1 (via the leg 4 per-seed comparison); PBO rank off by one (via the
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
  start/end dates and data snapshot (not `rng="5y"`), n_dates, mean_ic, **sd_ic, skew, kurt_raw**,
  t_stat, p_value, `kind` (`logged_live`|`reconstructed`; Architect renamed from `registered`,
  see Architecture for further fields), `git_sha`, `git_dirty`, `prev_sha256`.
  `is_control` is derived from `family == "control"` [code: study.py:73], not set by the writer.
- **Trial** = one (variant, horizon, parameter set, universe, explicit date range) whose result was
  computed and could be read, reported or not, including those failing the 30-date minimum.
  A discovery run and its holdout run of one variant are **one trial**; DSR is applied to the
  discovery selection, never the holdout. Controls logged; Architect revision: primary N **includes** controls
  (conservative, cannot be gamed by labelling), N without them is printed beside it. N is a **count of logged trials, not an effective number of independent trials**:
  correlated features overstate it, unlogged or reconstructed ones understate it.
- **What the chain proves:** the lines present are in the recorded order and an edit to an earlier
  line is detected only if the head hash was anchored elsewhere (record it in the commit message
  or CONFIDENCE.md per study). It does **not** prove completeness, omitted trials, true field
  values, true dates, or that the tree behind `git_sha` was clean; anyone who can edit can
  recompute later hashes. Git history helps only with force-push and rebase protection (owner
  setting). Report line carries "ledger: internally consistent, anchored to seq S head H | UNANCHORED;
  completeness not verifiable; logging self-reported" (never "verified").
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
   accept N as a self-reported count of logged trials (net bias direction unknown, not a bound), with the rule "no study reported unless logged"?
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

## Architecture

Architect: 2026-10-13, revised the same day against `docs/audit/trial-ledger-dsr-pbo-architecture-domain-finance.md`
(4 P1) and `...-architecture-model-validator.md` (6 P1). Playbook `architect.md` is `status: baseline`
(last-reviewed 2026-10-10; not radar-verified). Stdlib only (Python 3.13 here). Gate applies: new
persistent state. ADR: `docs/adr/0003-trial-ledger-format.md`. All maths is [mem], not checked against
the papers; every known-answer constant is labelled "from memory, unverified against paper" until a
human checks the paper once.

### Layout and boundaries
- `sonar/research/overfit.py`: pure maths (PSR, SR0, DSR; PBO in slice 2). No I/O, no `sonar` imports.
- `sonar/research/ledger.py`: schema, `append`, `read_all`, `verify`. Imports `json`, `hashlib`,
  `fcntl`, `os` only.
- `sonar/research/trialreport.py`: adapter and report. Imports `ledger`, `overfit`, `stats`,
  `validate`; builds a record from an IC series (`stats.evaluate`, `newey_west_t`), formats the report
  line, and has `python -m sonar.research.trialreport verify [--head SHA --seq N]`.
- Import direction `trialreport -> {ledger, overfit, stats, validate}`; nothing imports `trialreport`;
  `stats.py`, `study.py`, `validate.py` stay unedited and never import the new files: no cycle.
  `study.run()` returns only summaries, so sd/skew/kurt need the IC series from `validate._ic_series`
  (underscore name, same package). Option A (recommended): import it, pinned by a signature test and
  a golden-series test (its `>= 8 names` filter, validate.py:53, silently changes `n_dates`).
  Option B: small additive edit to `study.py`, excluded by this spec. **Owner.**
- Engine, agent, `scoring`, `calibration`, `core`, `ui`: no import, no data path; `SONAR_DATA`
  untouched. Guard test: nothing outside `sonar/research/` and `tests/` mentions `ledger`/`overfit`.
  Files-only, so the clean-agent run to 2026-11-09 is unaffected (SRE confirms no rebuild).

### Ledger file
`docs/research/trial-ledger.jsonl`, UTF-8, one canonical JSON object per line (`sort_keys`,
separators `(",",":")`, `allow_nan=False`), `\n` terminated. Chain fields: `schema` (1), `seq`
(0-based), `prev_sha256` (genesis = 64 zeros), `sha256` = SHA-256 of the canonical line without
`sha256`. Record fields as in the spec, with these changes:
- `kind` is `logged_live` or `reconstructed` (not "registered": nothing orders the append before the
  researcher saw the result; `date` and `git_sha` are self-reported). Report text says "logging is
  self-reported".
- `kurt_raw` (normal = 3) replaces `kurt`; `skew`, `sd_ic`, `n_blocks`, `block_len` from
  block-averaged ICs (block = horizon); `t_stat` is the existing NW t.
- `expected` (+1, -1, 0) and `n_obs` added; `metric` is `ic` or `other` (a non-IC study, e.g. the
  barrier-odds sixth study, is logged with null IC fields: counts in N, not in V).
- `trial_id` and `role` (`discovery`|`holdout`) added; a holdout row shares the `trial_id` of its
  discovery row and does not count in N.
- `feature_hash`: sha256 of the feature function's source plus its `REGISTRY` entry
  (`inspect.getsource`); `source`, `fetched_at` for the data.
- `trial_key` = sha256 of canonical JSON of (study slug, variant, family, `feature_hash`, horizon,
  sorted universe, explicit start, explicit end, **every argument of the computation**: costs,
  winsorising, lags, min-dates, IC method). `data_key` = sha256 of **all** adjusted closes per
  (symbol, date), with the adjustment convention and source recorded.
- Same `trial_key` and `data_key` = one trial; **the first row is the counted row, and DSR uses that
  row**. A later row with the same keys but a different result is flagged `rerun_differs` and printed
  in the report line (so a null re-run into a pass cannot hide). Same `trial_key`, different
  `data_key` = data revision: counted once, flagged. A changed `feature_hash` is a new trial.

**Append** `ledger.append(record, path=DEFAULT) -> dict`: open `O_RDWR|O_CREAT|O_APPEND`; `flock`
`LOCK_EX` on that fd (`LOCK_NB` retry up to 30 s, then `LedgerError`); read the last line; require it
ends in `\n` and its `sha256` recomputes; set `seq`/`prev_sha256`; one `write`; `flush`; `fsync`;
unlock. No side lock file. No `fcntl` (Windows) is an `ImportError`: fail closed. The repo has no
`flock` today (`execution.py:235` is `O_APPEND` plus fsync, and its reader skips bad lines: fail-open,
right for an audit log, wrong here), so this is a new, deliberately stricter convention. `flock` is
advisory and bound to the inode: do not append during a rebase, checkout or editor save that replaces
the file (the writer would hold a lock on the old inode).

**Fail closed:** `append` and report raise `LedgerError` (never warn) on a torn or unparseable tail,
bad hash, seq gap, `prev` mismatch, unknown `schema`, or unwritable file. A caller that cannot append
logs nothing and must not report.

**Verify** `verify(path, expect_head=None, expect_seq=None) -> VerifyResult(ok, n, head, errors)`
walks every line under `LOCK_SH`. Detects: edited line, fork, reorder, gap, truncated line, junk
line. A deleted tail is detected only against an anchor (`expect_head`/`expect_seq`, recorded
elsewhere in the same repo: commit message or `CONFIDENCE.md`; an editor of the repo can edit that
too, so it is not external). Test 7's deleted-tail case supplies the anchor. **The word "verified"
is never printed.** Proves: order and internal consistency of the lines present. Does not prove:
completeness, truth of fields or dates, a clean tree behind `git_sha`, or resistance to an editor who
recomputes later hashes. `is_control` is derived from `family == "control"` on read; `verify` rejects
a stored `is_control`.

### Concurrency and crash recovery
- Two writers: serialised by `LOCK_EX`, tail read inside the lock: no fork. A crashed holder
  releases on fd close.
- Crash mid-write: torn line (no `\n`). Next `append` refuses; `verify` reports it. No silent repair.
  An owner-run `trialreport repair --drop-torn-tail` truncates a final line lacking `\n` only (no
  hash can reference it) and prints what it removed. If that line was a trial it is unlogged: rerun
  it, do not patch it.
- Read while append: readers take `LOCK_SH` and see whole lines. A lockless `cat`/`git` reader may see
  a torn tail; `verify` flags it. Filesystems without flock: unsupported (`OSError` -> `LedgerError`).
- Git: two branches that both append fork the chain at merge. One ledger branch; resolve a conflict by
  re-appending, never by hand-editing. Branch protection is open question 5.

### Definitions: N, V, orientation, minimum windows
- **N** for a reported row R = number of distinct `trial_key`s among counted rows (non-holdout, first
  row per key) with `seq <= R.seq`, **controls included** (primary; the conservative direction and
  cannot be gamed by labelling). Secondary figure: N without controls, printed beside it with its own
  DSR. Headline = the larger N, fixed before looking. Later appends never change a printed number.
- **Orientation:** `t_or = expected * t_stat`. For `expected == 0` (selected by |t|) DSR is **refused**
  ("DSR not computed: direction not pre-registered"): the right null is the max of |t| (about 2N) and
  a signed SR0 would flatter. Recommended; the alternative (use 2N) is not built in slice 1. **Owner.**
- **V** = sample variance (ddof 1) of `t_or` over the same counted rows with `metric == ic` and
  non-null t (controls included), a dimensionless population; pass `var_sr = V_t / n_dates_R` and
  `sr = t_or_R / sqrt(n_dates_R)`. Fewer than 10 such rows: `OverfitError`, report prints "DSR not
  computed: V needs >= 10 trials". Also log `sd(t)` of control rows versus 1 as a calibration check.
  Reconstructed rows with null t raise N, not V; the line prints "reconstructed rows: k of N; counts
  unverified".
- **Minimum windows:** `n_dates / horizon >= 60`, else "DSR not computed: too few independent
  windows". Basis: Newey-West null simulations (model-validator): best-of-20 DSR>0.95 false-pass
  5.0% at n=250, 0.7% at n=1,250 (horizon 20, so ratios 12.5 and 62.5). 60 is a measured, not derived,
  threshold; success measure 4b re-measures it. The line prints the n/horizon figure.
- N is a **count of logged trials, not an effective number**; the direction of its net bias is
  unknown (correlated trials overstate N but compress V; unlogged ones understate N). Never call N a
  lower bound or DSR conservative. The report prints "N >= x logged trials".

### Maths API (`overfit.py`; every formula [mem], check against the papers before Build)
```
class OverfitError(ValueError)
EULER_GAMMA = 0.5772156649015329
def psr(sr, t, skew, kurt_raw, sr_star=0.0) -> float
  # [mem] Phi((sr - sr_star)*sqrt(t-1) / sqrt(1 - skew*sr + (kurt_raw-1)/4 * sr**2))
def expected_max_sr(n, var_sr) -> float        # SR0, n >= 2, var_sr > 0
  # [mem] sqrt(var_sr)*((1-g)*inv_cdf(1-1/n) + g*inv_cdf(1-1/(n*e)))
def dsr(sr, t, skew, kurt_raw, n_trials, var_sr) -> float   # psr(..., sr_star=expected_max_sr(...))
def sr_from_nw(t_nw, n_dates) -> float         # t_nw / sqrt(n_dates)
```
`n_trials == 1` gives `sr_star = 0` (convention, not from the paper; pinned). `OverfitError` on:
`t < 2`, non-finite input, `n_trials` not an `int` (bool rejected) or `< 1` or `> 10**9`,
`var_sr <= 0` or undefined with `n_trials >= 2`, **`kurt_raw < 1 + skew**2 - 1e-9`** (impossible
moments; catches excess kurtosis passed as raw), radicand <= 0. No clamping, no `None`. `Phi`
saturates to 0 or 1 through `erf`; the report **displays `>0.999` / `<0.001`, never 1.000**. DSR is a
one-sided confidence level under the papers' assumptions (iid with moment correction), not a hit rate
and not a chance of profit; docstring and non-goals say so. Under the input method
`sqrt(t-1)*t_nw/sqrt(n)` is about `t_nw`, so DSR reduces to roughly `Phi(t_or - t0)`, `t0 = sqrt(n)*SR0`;
the HAC correction survives (model-validator: YES, conditional on the definitions above). skew and
kurt_raw come from block means (a different frequency than `sr`; about 40-60 blocks, so g4 is noisy)
and are numerically inert for IC inputs (`sr` ~ 0.03-0.1): not evidence of normality. A test keeps
the radicand positive over the observed range of `sr` and `kurt_raw`.

PBO signature is left to slice 2 (`pbo_split(matrix, is_idx, oos_idx) -> float`).

**Known answers.** `model-validator` produces them before `overfit.py` is written, in
`tests/known_answers_overfit.py` as 50-digit `decimal` constants with derivations, from a fresh
transcription of the paper (not from this spec). PSR cases: one with each term mattering, and a small-T
case (T about 12, SR about 0.5, skew -0.7, kurt_raw 5) where each mutant moves the result by more than
1e-3. SR0 hand values at N = 2, 10 (separate g from 1-g by 5% at N = 10). The independent
implementation for measure 4 is written by `model-validator`, structured differently (expected max by
numerical quadrature). Monte-Carlo oracle: SR0 is an approximation, so it is only a **sanity band
against the quadrature-exact E[max]**, with pre-registered per-N bounds on `SR0/E[max]-1`: N=2 in
[-9%, -7%], N=10 in [+2%, +3%], N=100 in [+0.5%, +1.5%] (measured -8.3, +2.5, +0.9); it does not
replace the 1e-6 hand values.

### Items the spec left open
1. **Effective-N clustering: out of slice 1** (needs a correlation model the ledger cannot supply;
   N is a raw count, bias direction unknown, labelled). Revisit at slice 2. **Owner confirms.**
2. **Identical inputs**: `trial_key` + `data_key` above.
3. **Study count.** CONFIDENCE.md:562 (five pre-registered studies, a sixth with a volatility effect),
   :720 (48 feature-by-regime tests, zero survivors), :737 (sixth study), :784-786 ("first survivor").
   Reconcile as a **list of studies with trial counts**, not "five plus one"; the 48 regime tests are
   48 trials; wording "passed the pre-registered test", not "survivor". Counts are filled at Build
   from CONFIDENCE.md and the code; unrecoverable trials are not invented as rows; the line prints
   "reconstructed rows: k of N; counts unverified". `REGISTRY` size is read at Build.
4. **Extreme inputs**: above (raise, display caps, `n` bounds).
5. **Plan/result records.** Recommended for slice 1: not built; `logged_live` rows only, and the
   report says logging is self-reported. Option: a `plan` record appended before each run, with
   unmatched plans counted in N (makes omission after peeking visible). **Owner.**

### Test and mutation hooks (Verify)
- `tests/test_overfit.py`: measures 1-5 and the listed mutants; `t < 2`, impossible-moments
  (excess-as-raw), radicand, `n_trials == 1`, bool/huge n, undefined V, non-finite errors.
- Success measure 4 is revised (see above): the mean-DSR leg compares per seed against the independent
  implementation on the same data at tolerance 1e-9, which is what kills N-1 (measured gap in mean
  DSR 0.008 is inside the old 0.02, so the old leg could not); count bounds stay as gross-bug guards.
  Measure 4b (overlap simulation) runs MA(19), horizon 20, 20 series, at n=1,250 and n=250, 1,000 seeds,
  records the false-pass rate; pre-registered bound at n=1,250: DSR>0.95 in <= 2% (measured 0.7%,
  wide interval); at n=250 the report must print "not computed" and the rate is recorded only.
- `tests/test_trial_ledger.py`: two processes (`multiprocessing`) x 500 appends re-read as 1,000,
  `verify` clean; fork, gap, edited line, torn tail, deleted tail (anchored), stored `is_control`,
  unknown schema each fail; report refuses N on every one and never prints "verified"; `append`
  refuses on a torn tail; changed `feature_hash` counts as a new trial; N/V by `seq` unchanged by
  later appends; `expected == 0` refused. Mutants: remove `flock` (fork test fails; run 20x), skip
  tail-hash check, hash before canonicalising, drop `feature_hash` from the key, N from the whole
  ledger instead of by `seq`. `fsync` removal untestable, declared.
- Layout guard tests as above; coverage >= 90% on the three new files.
