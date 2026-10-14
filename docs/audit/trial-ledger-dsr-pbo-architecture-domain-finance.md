# Domain review (finance), Architect phase: trial ledger, DSR, PBO

Date: 2026-10-13. Scope: spec "## Architecture" (spec lines 132-249) and ADR 0003, in
`/home/user/sonar/.claude/worktrees/agent-a3ed0519d39f51b25/docs/`. Playbook `domain-finance.md`
is `status: baseline`, last-reviewed 2026-10-12 (not radar-verified). Papers not fetched; formula
statements are from memory ("not verified" against the source). I am not a statistician of record:
`model-validator` owns the known answers. Internal research tool, no retail copy, no UI: the
no-edge invariant is met in the wording I read (verdict-free report line, "historical, not
tradable", non-goals).

Summary: P0 0, P1 4, P2 8, P3 3.

## Formula check (from memory, not verified against papers)
- PSR (spec 64-65, 199-200): matches Bailey/Lopez de Prado 2012 as I know it (raw kurtosis,
  sqrt(T-1), denominator 1 - g3*SR + (g4-1)/4*SR^2). OK.
- SR0 (spec 66-67, 202-203): matches Bailey/Lopez de Prado 2014 as I know it
  (sqrt(V)*((1-g)*z(1-1/N)+g*z(1-1/(N*e)))). V is the cross-trial variance of Sharpe estimates.
  OK. N = 1 convention SR0 = 0 is correctly labelled "not from the paper".
- DSR = PSR(SR0): OK. Calling it a "probability" (spec 68) is the papers' reading but it is a
  confidence level under iid/stated-moment assumptions; see P2-6.
- Radicand: for consistent moments (raw kurt >= 1 + skew^2) it equals at least
  (1 - skew*SR/2)^2 >= 0, so a nonpositive radicand only arises from inconsistent inputs, which is
  the real hazard (P1-4).

## P1

### P1-1. "ledger: chain verified" overstates what an unanchored chain shows
Spec 99 hard-codes the report line "ledger: chain verified; completeness not verifiable". Spec
176-177 says an unanchored `verify()` reports `unanchored` and cannot see a deleted tail, and spec
94-98 says anyone who can edit can recompute later hashes. The line therefore prints "verified"
in the state where the check proves least. A deleted tail lowers N, which raises DSR: the
anti-conservative direction. Anchors sit in the same repo (commit message or CONFIDENCE.md), so
they are not external to an editor (ADR line 14 says "externally recorded"; it is not).
Rule: playbook "every displayed figure traceable"; app-context "no certainty". Scenario: the owner
reads "verified" next to a high DSR and treats N as audited.
Fix: print "ledger: internally consistent (anchored to seq S head H) | UNANCHORED"; never the word
"verified"; print head sha8 and seq with the line so the N is tied to a ledger state; print N as
"N >= x logged"; in the ADR say "recorded elsewhere in the same repo" not "externally".

### P1-2. trial_key omits the feature definition, so redefinition collapses into one trial
Spec 227-231: `trial_key` is built from slug, variant, family, horizon, universe, dates and a
parameter dict; same key and same `data_key` = "one trial, first record wins". No code or
feature-definition version is in the key (git_sha is deliberately outside it). A feature whose
computation was changed under the same variant name and params is a new trial but is deduped to
the first row. Parameter-dict completeness (costs, winsorising, lags, min-dates, IC method) is by
convention only. Net effect is N understated, DSR inflated. Also "first record wins" means the
counted/V row can differ from the row later reported.
Fix: add a feature-source hash (or `REGISTRY` entry version) to `trial_key`; define the parameter
dict as "every argument of the computation"; count reruns with different results as separate trials
or keep the worst-case rule explicit; DSR must use the same row that is counted.

### P1-3. "registered" kind and "log after compute" imply a pre-registration the chain cannot show
Spec 86-87 `kind` = `registered`|`reconstructed`; spec 169-171 appends after the result exists.
Nothing orders the append before the researcher saw the result, and `date` is self-reported. A
reader will take "registered" as pre-registered. The rule "no study reported unless logged" does not
stop computing, looking, and not logging.
Fix: rename (`logged_live`) or require a `plan` record appended before the run and a `result`
record after, with unmatched plans counted in N; state in the report line that logging is
self-reported.

### P1-4. Raw vs excess kurtosis is only caught by tests, not at runtime
Spec 207-209 lists the guards: `t < 2`, non-finite, `n_trials < 1`, `var_sr <= 0`, radicand. Passing
excess kurtosis (normal = 0) as raw is the classic slip: it shrinks the denominator terms and
silently inflates PSR/DSR whenever the radicand stays positive. The ledger field is named `kurt`
(spec 86, 159), which invites it.
Fix: rename to `kurt_raw`; raise `OverfitError` if `kurt < 1 + skew**2 - 1e-9` (impossible moments);
document the unit in the schema.

## P2

### P2-1. Six-study reconciliation does not fit the ledger schema
Spec 232-234 settles on "six studies: five directional nulls and one volatility survivor".
CONFIDENCE.md:562 says the sixth "found a volatility effect, not a drift"; :737 starts "The sixth
study: the catalyst weight"; :720 reports "48 feature-by-regime tests. Zero survivors"; :784 and
:786 call the sixth the "first survivor". The sixth is a barrier-odds study, not an IC series, so
`mean_ic`, `t_stat`, `sd_ic` do not describe it, and the 48 conditional tests are 48 trials that
must be backfilled. Spec line 20-22 ("all nulls") contradicts "survivor". "Survivor" also reads as
a positive verdict.
Fix: reconcile as a list of studies with trial counts (not "five plus one"); say in the ledger
schema how non-IC studies are recorded or that the first DSR applies to IC trials only; use
"passed the pre-registered test" instead of "survivor"; leave the actual count to Build with the
48 included.

### P2-2. "Unlogged count" is printed but cannot be known
Spec 236-238: unrecoverable trials are not invented as rows, "CONFIDENCE.md lists them as
'unlogged' and the report line prints that count". An unrecoverable trial has no countable
identity, and the report-line template (spec 100-102) has no such field. Reconstructed rows have
null sd/skew/kurt, so they raise N but are dropped from V (spec 211-212), biasing SR0.
Fix: print "reconstructed rows: k of N; counts unverified" and an explicit "N is a lower bound"; say
how V is computed when most backfilled rows are null.

### P2-3. Effective-N decision (spec 224-225): accepted, wording needs correcting
Deferring clustering and labelling N a raw count is reasonable. But spec 102-103 says correlated
features "overstate" N. Correlated trials also shrink V, and SR0 scales with sqrt(V), so the net
direction is not established. Do not call raw N conservative. Also: if trials are chosen by
|t| (two-sided), the one-sided SR0 for N draws understates the null maximum (effectively 2N).
Fix: wording "direction of bias unknown"; report DSR by one-sided selection only and say so; have
`model-validator` check the two-sided case.

### P2-4. data_key is too weak to detect revisions
Spec 228-229: sorted (symbol, date) pairs plus last close per symbol. Adjusted history (splits,
dividends, vendor corrections) can change earlier closes while the last close and the date grid
stay fixed. The revision then looks identical, is flagged `rerun`, and is counted once.
Fix: hash all closes (or per-symbol rolling hash) with explicit adjustment convention and source;
record source and fetch timestamp. Cheap relative to the cost of undercounting.

### P2-5. trial_id is used but not in the schema
Spec 230-231 says discovery and holdout "share a `trial_id`"; the record fields (spec 85-88, 158-159)
have `trial_key` and `data_key` only, and a holdout has different dates so a different `trial_key`.
Fix: add `trial_id` (and `role`: discovery|holdout) to the schema, ADR and tests.

### P2-6. "Probability" wording and assumptions not in the line
Spec 68 and the report line (100-102) say "DSR prob". Under the papers' assumptions it is a
one-sided confidence level for the true SR exceeding SR0, assuming moments estimated from the
sample. State "under iid-with-moment-correction assumptions" once in the docstring and in the
non-goals, and keep the "not a hit rate, not a chance of profit" sentence.

### P2-7. Unit mismatch in the NW-based DSR input (spec 75-79, 212-213)
`SR_hat = t_NW/sqrt(n)` is mean divided by the long-run (HAC) sd, not mean/sd, and it is per date,
while skew/kurt come from block-averaged ICs (block = horizon), which shrink skew by about
sqrt(h) and excess kurtosis by about h under iid. The denominator terms then use moments of a
different frequency from SR. Effect is small when SR_hat is small but not zero for the "keeps HAC
correction" claim. V pooled across horizons mixes scales. Flag for `model-validator` (open item 4
of the spec "adopted as specced" is premature). Not verified numerically.

### P2-8. Headline N and extreme output
(a) Spec 103 reports N "with/without controls" but the line has no headline; excluding controls
gives the smaller N and the higher DSR. Fix the headline (larger N) before looking, print both
DSRs. (b) `Phi` saturates to 1.0 (spec 209-210) and would print "DSR prob = 1.000", which reads as
certainty. Display capped (">0.999") and never format 1.0. (c) N >= 2 but fewer than two non-null
trials makes V undefined; spec 210-212 does not say what happens: raise `OverfitError`.

## P3
- P3-1. `1 - 1/n` rounds to 1.0 near n ~ 1e16, then `inv_cdf` raises `StatisticsError`; spec 209
  says arguments "stay inside (0,1) for any n >= 2". Wrap or bound n; reject bool/non-integer n.
- P3-2. `flock` is advisory: an editor, `git checkout` or rebase that replaces the file leaves
  a writer holding a lock on the old inode (fork risk). Document; do not append during git
  operations. ADR "Unix only" is fine.
- P3-3. Ledger provenance: `git_sha`/`git_dirty` are self-reported; add data source and fetch time
  alongside `data_key` for the playbook's "source and timestamp" rule.

## Needs a qualified human
Nothing legal. The statistical choices in P1-2, P2-3 and P2-7 need `model-validator` against the
papers before Build.
