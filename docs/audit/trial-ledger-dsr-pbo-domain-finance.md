# Domain review (finance), Define phase: trial ledger, DSR, PBO

Spec: `.claude/worktrees/agent-a331b351ae89b1035/docs/specs/trial-ledger-dsr-pbo.md` (cited as S:line).
Reviewer: domain-finance, 2026-10-13. Read-only. Not a legal or actuarial opinion.

Playbook `docs/playbooks/domain-finance.md`: `status: baseline`, last-reviewed 2026-10-12 (1 day old, but baseline = not radar-verified). Treat its practices as seed, not verified.
Source honesty: the Bailey/Lopez de Prado papers were not fetched by the spec author or by me (shortlist tags them [S]; spec tags formulas [mem]). Formula verdicts below are from my own knowledge, so they too are "not verified against the paper". The spec is honest about this; keep that gate.

No edge/profit/certainty wording found, except the inverted sentence in P1-1. No app invariant is touched (internal tooling, no UI, no live trading).

Evidence run (scratch, nothing written to the repo): numpy simulation of success measure 6 (4000 seeds, 20 zero-mean series, T=250, sample-variance V). Result: DSR>0.95 in 0.1% of seeds; undeflated PSR>0.95 in 62.8%; with N replaced by N-1, DSR>0.95 in 0.25%.

## Formula check

| Formula (S:line) | Verdict |
|---|---|
| PSR, S:59-61 | Matches my recollection of Bailey/LdP 2012: Phi((SR-SR*)sqrt(T-1)/sqrt(1-g3 SR+((g4-1)/4)SR^2)), raw kurtosis, per-period SR. Missing edge guard: radicand can be <=0 for large SR with skew/kurtosis; define behaviour (raise/None), and require T>=2. |
| SR0, S:62-64 | Matches my recollection of Bailey/LdP 2014 (Euler-Mascheroni mix of z(1-1/N) and z(1-1/(N e))). V must be the variance of the estimated Sharpes across trials in the SAME per-period units as SR; spec should say V needs N>=2 and is undefined at N=1. N=1 -> SR0=0 is a convention, not from the paper; label it so (S:39-41 does). |
| DSR = PSR(SR0), S:65 | Correct as stated. |
| PBO/CSCV, S:66-69 | Structure right (S blocks, C(S,S/2) splits, argmax IS, logit, PBO = share logit<=0). One point I am fairly (not fully) sure of: the paper's relative rank is r/(N+1), not r/N, so the logit is finite when n* ranks best. "Relative rank among N" (S:68) is ambiguous on that and on rank direction (rank 1 = worst or best). Pin both; they flip PBO to 1-PBO or give infinite logits. |

## Findings

### P0
None.

### P1

**P1-1. Inverted meaning of a passing DSR (S:95-96).** "A passing DSR means 'not distinguishable from the best of N noise draws'" is backwards. A high DSR means the survivor exceeds the expected best-of-N noise Sharpe (S:22-23 says it correctly). A reader skimming the report line would take a pass as a fail. Rule: honesty-of-claims (app-context invariants). Harm: owner or agent misreads a null as a lead or the reverse. Fix: "A DSR below the cut-off means not distinguishable from the best of N noise draws; a high DSR means only that it is not explained by selection among N tries, not that it works or is tradable." Also say DSR is a probability, not a p-value: the report line `DSR p = ...` (S:86) invites reading it as a p-value where small is good. Rename `DSR prob`.

**P1-2. Success measure 6 cannot fail for a wrong implementation (S:44-48, 6).** The spec states nominal 5% false-positive rate and threshold <=8%. My simulation shows the correct DSR gives about 0.1% (the max of 20 draws has a much narrower spread than one Sharpe's standard error, so SR0 + 1.645 SE is far into the tail). The bound is 16 events in 200 seeds against an expected 0.2. Mutant "N-1" gave 0.25%, so it passes the test; only no deflation at all fails. Rule: a test that cannot fail is not evidence (AGENTS.md "mutation-checked"). Fix: replace the 5% premise with a measured rate. Pre-register a bound from a larger run (for example, expected rate about 0.1-0.5%, fail above 2%), add an assertion on the mean DSR of the best series or on its quantiles (more sensitive than a threshold count), and keep the PSR >= 50% leg (observed 62.8%, fine). Do not tune the bound after seeing the implementation's output without saying so.

**P1-3. Two of the nine mutants are likely equivalent, so "100% killed" (S:49-53) is unattainable or will be met by weakening.**
- Swap IS/OOS: with full enumeration of C(16,8) splits, the set of (IS, OOS) pairs is closed under swapping (each split's complement is also a split). PBO is identical. Test 4 (noise, about 0.5 either way) and test 5 (planted strategy dominates both halves) do not kill it either.
- `<=` to `<`: if the rank is r/(N+1) with N=20, the median 0.5 is never hit, so the mutant is equivalent. It only differs under r/N or odd ties.
Fix: drop both from the kill list or declare them equivalent mutants with the reason; or test the internal per-split function on a tiny hand-built matrix (S=4, N=3) with a known answer, which kills "rank off by one" as well. Do not accept an `if` hack to make them killable.

**P1-4. Circular test 1 and PSR mutants without an independent oracle (S:35, 49-53).** DSR(N=1) == PSR(SR*=0) holds by construction (SR0 defined as 0), so it kills no PSR mutant. The hand-computed known answer (S:37-41) covers SR0 only. Mutants "T-1 to T", "skew sign flip", "raw kurtosis to excess" need a PSR known answer with nonzero skew and kurtosis, computed independently. Add it to success measure 3.

**P1-5. Hash chain plus concurrent append contradict each other (S:46-47, 77-78).** Each record carries `prev_sha256` of the previous line, which requires a read-then-append. Two processes using `O_APPEND` single writes lose no record, but both can read the same previous line and fork the chain. Test 7 would pass while the chain is broken. Also, a truncated final line that is "skipped with a warning" is a trial silently dropped from N, and the next record's `prev_sha256` is undefined. Fix: take an exclusive lock (`fcntl.flock`) around read-last-line + write; verify the whole chain in a `verify()` that reports forks and gaps; in report generation, fail closed (refuse to print N) on an unverified ledger instead of warning.

**P1-6. What the hash chain proves is overstated (S:100-101, 77-78 "so edits show up").** It detects an edit to an earlier line only if the head hash is anchored elsewhere; anyone able to edit can recompute every later hash. It does not detect deleted trailing lines, omitted trials (the real risk, S:99-101), false field values, a false date, or a dirty working tree behind the recorded git SHA. Git history helps only if branches are protected against force-push and rebase; the spec does not say so. Fix: state these limits in the spec and in the report line ("ledger integrity: chain verified; completeness not verifiable"); record the head hash in the commit message or CONFIDENCE.md at each study; record `git_dirty`; say plainly that N is a self-reported lower bound.

**P1-7. DSR on IC series with overlapping horizons (S:102-106, open question 2).** Correctly flagged, but it is a Define-level correctness problem, not only an Architect choice. `sqrt(T-1)` with T = n_dates overstates evidence by roughly sqrt(horizon) for 20-day windows (stats.py:15-20, 68-74). IC mean/sd is an IR of rank correlations, not a return Sharpe, and carries no cost treatment (stats.py:199-207 admits this). Moreover the ledger record (S:80-82) stores mean_ic, t_stat, p_value but not the SD, skew or kurtosis of the IC series, so neither SR nor V nor g3/g4 can be computed from the ledger. Suggested direction for the owner decision: derive the per-period statistic from the Newey-West t (SR_hat = t/sqrt(T), so sqrt(T-1)·SR_hat keeps the HAC correction), or use T_eff = n_dates / horizon; compute g3/g4 on non-overlapping or block-averaged ICs; add `sd_ic`, `skew`, `kurt` to the record. Until decided, the report line must say "IC-based, overlap-corrected by method X; not a return Sharpe; gross of costs".

**P1-8. CSCV on overlapping, autocorrelated series leaks across block boundaries (S:66-69, 108-110).** Adjacent blocks share forward windows, so IS and OOS are not independent; the repo's own study design uses an embargo for this reason (study.py:12-13, 49-58). Test 4 uses iid noise and cannot detect it. Fix: purge/embargo `horizon` periods at each block boundary in PBO, add a noise test with an autocorrelated (MA(19)) series, and keep PBO deferred as proposed. With features instead of strategies the PBO's meaning is weak (acknowledged S:109); label it "selection stability across blocks", not "probability the strategy is overfit".

### P2

**P2-1. Trial definition and N bias (S:70-83, 111-113).**
- Excluding controls is defensible for N (they are not candidate survivors) but the flag is writer-set: a real variant mislabelled `is_control` lowers N and flatters DSR. Derive it from `family == "control"` in the registry (study.py:73) and have `verify()` reject other uses. Report N both with and without controls; the control-exclusion default is not the conservative direction.
- Raw N counts correlated trials (features overlap, horizons overlap), so it overstates independent trials, while reconstructed backfill and unlogged variants understate N. The directions differ; do not call N a "lower bound" without also calling DSR "conservative for correlation". Say N is a count of logged trials, not an effective number of independent trials (the paper uses an effective N/clustering).
- Window is part of the trial key, so a discovery run and its holdout run for the same feature count as two trials (study.py:69-70), yet it is one hypothesis. State which. The default `rng="5y"` rolls with time, so "identical inputs" (S:77) is not well defined; key on explicit start/end dates and data snapshot.
- Trials that fail the 30-date minimum return None (stats.py:179-180) and have no mean_ic/t_stat; the record schema must allow nulls.
- DSR must be applied to the discovery selection, not the holdout; say so.

**P2-2. Inconsistent counts (S:16 vs S:83).** "Five pre-registered studies" vs "six existing studies"; CONFIDENCE.md has a "sixth study" heading (CONFIDENCE.md:737). Reconcile; `features.REGISTRY` size was not read (S:84-85); a grep for `Feature(` returned 1 line, so it is built another way. Backfill N is not verified; keep it labelled "reconstructed from prose".

**P2-3. Success measure 4 and 5 thresholds (S:42-45).**
- Noise PBO is about 0.5 by symmetry (independent blocks, exchangeable trials), so [0.40, 0.60] is defensible in centre. Its width should come from measured spread: splits within a seed are highly dependent, so per-seed PBO is noisy. Compute the standard deviation of the 50-seed mean at Build and set the band at about 4 SE, written down before looking at results. Today it can fail for a gross bug (always 0 or 1) but not for subtle ones.
- Planted +0.3 sd per period (S:44) is an enormous per-period Sharpe (roughly 4 SE for a 200-point half) and is trivially dominant, so <= 0.05 tests only the gross case. "Same shape" is undefined. Add a weak-signal case with an expected intermediate PBO computed independently.
- Say whether 4 and 5 use one seed or a mean.

**P2-4. Report line lacks the figures the playbook requires (S:86-87).** Add period/window, n_dates, horizon, and "gross of costs and slippage; historical, not tradable" (playbook "Current practices", baseline; CONFIDENCE.md cost-floor section). Keep the line in the internal research output only; the non-goal of no UI (S:90) is right and should stay a hard rule, because any DSR shown to retail users without finance training would read as a quality score.

**P2-5. Harvey-Liu-Zhu t>3 context (S:111-113).** The spec rightly keeps it as context, tagged unverified. If shown, cite as "[S, snippet-only]" and keep it out of any pass/fail, as proposed. No change.

**P2-6. Pass/fail framing vs non-goal (S:6-47, 95-96).** Measure 6 uses "DSR > 0.95" as a "claim"; the non-goals forbid a gate. Fine for tests, but the 0.95 cut-off should not appear in the report line as a verdict. Print the number only.

## Needs a qualified human
None legal. Statistical method choices (effective T, effective N) belong to `model-validator` at Architect/Review, who should recompute the SR0 and PSR known answers independently from the paper.
