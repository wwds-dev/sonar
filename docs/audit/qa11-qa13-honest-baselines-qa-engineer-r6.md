# QA round 6: QA-11 / QA-13 loop 5 (uncommitted), qa-engineer, 2026-10-12

- Saved by the orchestrator (QA is read-only).

**Verdict: PASS on every loop-5 check. No P0 or P1.**
- All four suite runs are green.
- Both acceptance tests are deterministic, and each fails without its fix.
- Every owner decision from loop 5 is in the code as written.
- One new P2: the attribution placebo's bound only holds on the seeds it was fitted to, and the IC test still reads high on other seeds.
- Release waits on Document.

**Playbook:** `docs/playbooks/qa-engineer.md` is `status: baseline` (last-reviewed 2026-10-10), so treat it as stale and unverified.

**Read-only.** I edited nothing in the repo; the only write was the `log_activity.py` verify start/done lines in `docs/company/activity.jsonl`, which AGENTS.md requires.
- All mutants ran in `scratchpad/qa6/repo`. After every one, `cmp` confirmed the scratch copy matched the repo again.
- The SHA-1s of `sonar/`, `ui/` and `tests/` are the same at the end as at the start.
- `git status` changed only by two new files from the concurrent sessions, `docs/audit/…-code-reviewer-r6.md` and `…-model-validator-r6.md`. Neither is mine.

## 1. Suites: PASS
Command: `./run-tests.sh tests/ -q -p no:cacheprovider` (the venv's python). Exit codes are the script's real ones.

| run | exit | result |
|---|---|---|
| native 1 | 0 | 1916 passed, 30 deselected, 51.5 s |
| offscreen 1 | 0 | 1916 passed, 82.8 s |
| native 2 | 0 | 1916 passed, 64.3 s |
| offscreen 2 | 0 | 1916 passed, 141.8 s (load average up to 68) |
| coverage (offscreen) | 0 | 1916 passed; total **84%** branch coverage |

- Each run prints the same 3 teardown tracebacks: `libshiboken … MainWindow already deleted`. They are older code, outside this change.
- None of the concurrent session's edits turned anything red this round.

## 2. Acceptance tests, 5 runs each: PASS
- **Clustered coin:** 5 of 5 pass, 5.5–6.8 s per call.
  - Seeded (fixed dates, `random.Random(seed)`), with no time or network dependence.
  - With the headline floor removed in the loop-5 code: `AssertionError: 9 of 60 runs gave a verdict on a coin`.
- **Attribution placebo** (`test_a_meaningless_clustered_component_is_rarely_graded`): 5 of 5 pass.
  - It takes 15.4–17.3 s under load; the engineer measured 4.9 s, so it is now the slowest test.
  - Seeded through `zlib.crc32`, so the same seeds every run.
  - It fails without the fix. Graded / IC z² / spread z² on worlds 0–3:

| configuration | graded | IC z² | spread z² | result |
|---|---|---|---|---|
| both floors (loop 5) | 2/24 | 1.61 | 1.57 | passes |
| IC floor off | 3/24 | 2.59 | 1.57 | fails the IC bound |
| spread floor off | 2/24 | 1.61 | 5.55 | fails the spread bound |
| both off (loop 4) | 6/24 | 2.59 | 5.55 | fails all three bounds |

- **The bound only holds on the fitted seeds (see P2-1).** Same test, both floors on, other disjoint sets of 24:

| worlds | graded | IC z² | spread z² | bounds broken |
|---|---|---|---|---|
| 4–7 | 1 | 3.51 | 1.62 | IC |
| 8–11 | 4 | 2.24 | 1.79 | count and IC |
| 12–15 | 1 | 1.56 | 1.60 | none |

  On worlds 4–7 the IC z² is 3.51 with and without the IC floor, so the date-clustered bar does not bind there and Newey–West is already the wider one. Over all 96 runs, 8 were graded (8.3%).

## 3. Loop-5 behaviour: PASS
**Decision 1: attribution uses the date-clustered (DK) error bar.**
- `_dk_mean_se` matches my brute-force double-sum DK to 4.6e-16 relative. That covers 40 random samples with calendar gaps, undated rows and lags 0–9.
- `_ic_t` equals mean / max(Newey–West, DK) to 1e-15 on 40 clustered samples; DK was the wider bar in all 40.
- `_quintile_spread` se and se_dk equal a brute-force DK of the top − bottom difference exactly.
- The component p-values equal `normal_p(_ic_t(...))` at each setup set's own lag (`_dk_lag_of`).
- `blend_ic_t` equals the same test on the blend's own setups.
- The headline did not move: the Lab default is byte-for-byte the r5 figures.

**Decision 2: verdict copy.**
- "beats" and "below" are **exactly** the validator r5 strings.
- The Lab difference line reads `+0.11 pts  (error bar ±1.76; setups entered on the same day counted together)`.
- The Terminal prints `r["verdict"]` verbatim for beats, below and withheld (checked by calling `_backtest_done` on a stub).
- No backtest verdict contains "standard error".
- The withheld verdict reads "can read above".
- Old wording survives only in the docs (P2-2).

**Decision 3: the attention gap is taken over the attention rows.**
- Mutant T1 (gap over every trial) is killed by 2 tests, including the reviewer's case of 25 covered instruments out of 129.

**Decision 4: small fixes.**
- The attention table is headed "vs the run as a whole" and shows `vs_run` (+0.2/−0.4, not +3.0). Momentum keeps "vs baseline".
- Older attention buckets, or mixed old and new ones, fall back to `delta` under "vs baseline".
- The null attention copy ends "no effect of a news spike was detected, which is not the same as none."
- **Lab colour:**
  - It follows `significant`: a significant run whose rounded figures sit inside ±2 se is amber; a non-significant run exactly on the boundary is grey.
  - Withheld runs are grey, without the "supposed to look like" paragraph.
  - An older summary without the flag falls back to the figures.
- **Old summaries:** a loop-4-era summary (no `significant`, `se_dk`, `vs_run` or blend fields) and a minimal pre-QA-13 one both render in the Lab and the Terminal. Neither shows the "wrong way round" sentence.

## 4. Live figures for the docs (cached bars from `qa5/live`, last bar 2026-10-12, 129/129 instruments; no refetch)
**Lab default (2y, h=5, step 3, whole watchlist)** is unchanged from r5:
- n 18,973 across 129 instruments.
- Hit rate 39.55%; predicted 39.44% (40% with unlimited time); Δ +0.11 pt.
- se 0.88 pt, the DK bar at an 11-day lag; z +0.12.
- Verdict: "within 1.8 points … no edge detected".
- 2,574 timed out (11.95%); 373 too near the end of the data; 572 entry dates, 2024-11-11 to 2026-09-29.
- Expectancy beyond a no-edge market +0.0027 R.

**Lab default attribution grades (now, with loop 4 in brackets):**
- **momentum WEAK:** IC −0.0146, p 0.534 [0.254]; spread −2.24 ± se 2.11 [1.13].
- **volatility DROP:** IC −0.0186, p 0.224 [0.045]; spread −3.14 ± se 2.56 [1.12].
- **Blend:** IC −0.0165, t −0.88 [−1.58]; no "backwards" sentence.

**Terminal profiles:**

| profile | Δ (± 2se) | verdict | attribution now | in loop 4 |
|---|---|---|---|---|
| h=1, 2y | −0.99 (±1.4) | within | momentum UNCLEAR (p 0.108); volatility DROP (p 0.022, survives BH; spread −3.97 inside ±4.40); blend t −1.93, no sentence | INVERTED / INVERTED; t −3.72, sentence shown |
| h=5, 2y | +0.11 (±1.8) | within | same as the Lab | same as the Lab |
| h=20, 2y | +0.86 (±3.0) | within | momentum WEAK; volatility DROP (p 0.144); t −0.66 | volatility INVERTED (p 0.004) |
| h=60, 2y | +3.05 (±9.3) | within | momentum WEAK; volatility DROP (p 0.122; spread −15.75, se 9.86); t −1.06 | volatility INVERTED (spread se 1.32) |
| h=250, 5y | +6.50 | withheld: horizon | not judged; t −0.78 | not judged; t −3.45 |

## 5. Mutation and changed-line coverage
**31 mutants, 26 killed, 5 survived** (focused files first, then the survivors on the full suite).
- **Killed:**
  - IC test: E1 the DK floor dropped from `_ic_t`; E2 max → min; E3 component times undated.
  - Blend t: E5 undated; E6 lag 0.
  - DK helpers: L1 `_dk_lag_of` −1; L2 `_dk_mean_se` not centred; L3 divides by √n; L4 Bartlett 1−l/L; L5 undated rows dropped.
  - Spread: S1 the floor dropped; S2 not centred; S3 lag 0; S4 bottom sign flipped; S6 `se_dk` reports se.
  - Attention: T1 gap over every trial.
  - Verdict copy: V1 "1 in 20"; V2 the no-guarantee sentence dropped; V3 "did worse than a coin flip"; V4 "reads above"; V5 bar at 1 se.
  - Lab: U1 colour from the rounded figures; U2 withheld gate dropped; U4 column stays `delta`; U5 the difference line at 1 se; U6 the same-day clause dropped.
- **Survived the full suite (1911 passed):**
  - **E4:** the component IC lag halved. No test pins the component's lag.
  - **E7:** `_ic_t` returns −99 when se == 0. That branch is never run, and coverage.py cannot see it because it is a conditional expression.
  - **S5:** the spread lag taken over the top and bottom fifths only. Close to equivalent.
  - **T2:** the null copy loses "which is not the same as none". The tests only check `startswith`.
  - **U3:** `all()` → `any()` for mixed old and new buckets. Equivalent in practice, since a summary has all of them or none.
- **Changed-line branch coverage, loop 4 → loop 5** (110 + 16 changed lines):
  - `sonar/backtest.py`: 27/27 statements, 4/4 branches.
  - `ui/app.py`: 4/4 statements, 2/2 branches.
  - Total 84%, over the 80% bar.

## Defects
- **P0/P1:** none.
- **P2-1 (new, model and test risk): the attribution placebo's bound is fitted to its seeds, and the IC test is still anti-conservative.**
  - On 2 of 3 other seed sets the test as written would fail: IC z² 3.51 and 2.24 against a bound of 2.0, and 4 graded against a bound of 3.
  - Mean IC z² over 96 runs is 2.23 (nominal 1.0); 8.3% were graded.
  - The IC's DK floor often does not bind (worlds 4–7). Most of the gain comes from the spread floor.
  - Loop 5 is a large improvement on loop 4 (real bars 24% → 5% per the engineer; volatility INVERTED is gone from every live profile). But the docs must not call the attribution grades calibrated.
  - Record this with the open clustered-coin ≤5% item as a model-validator follow-up: a longer or block-based lag for the IC, or sign randomisation.
- **P2-2: Document has not landed.**
  - `static/docs.html:627` still says "Error bar — Two standard errors on the difference".
  - `CONFIDENCE.md:578` still has "vs baseline | ±2 s.e.".
  - CHANGELOG, TODO, the ADR and the spec's old copy (around :200) are also not updated.
  - The figures in §4 are ready for them.
- **P2-3 (known, open):** the clustered-coin ≤5% target. The owner accepted the test as a regression guard.
- **P3:**
  - Untested mutants E4 (IC lag) and T2 (the owner-mandated null wording is not pinned exactly). E7: the se == 0 arm of `_ic_t` is never run.
  - `sonar/backtest.py:894` docstring line is 137 characters, against `line-length = 100`. E501 is not selected in `ruff.toml`, so lint passes.
  - Rounding: "beats by 2.0 points, outside its error bar (±2.0)" can appear at the boundary. Cosmetic, and true on the unrounded figures.
  - The placebo test is now the slowest in the suite (about 16 s under load).
  - The teardown tracebacks seen in every run predate this change.

## Release recommendation
The loop-5 code is release-ready against the owner's loop-5 decisions, with no P0/P1. Before release:
1. Land Document (P2-2) using the §4 figures. Say that the attribution and headline bars are not calibrated 5% tests.
2. Record the owner's call on P2-1 (follow-up item, or a loop 6 on the IC lag).
3. Re-run both suites twice right before the commit, because concurrent sessions are still writing.

## Files
Everything is under `/private/tmp/claude-501/-Users-as-Documents-lab-active-sonar/a26ec703-42e8-43e7-ab51-f430c0bd1c34/scratchpad/qa6/`:
- Suite logs: `native1.log`, `native2.log`, `offscreen1.log`, `offscreen2.log`, `suites.txt`
- Acceptance runs: `accept1-5.log`, `placebo_sets.txt`
- Behaviour, live figures and mutation: `behave.log`, `live.log`, `mutants.txt`, `mutants_full.txt`
- Coverage: `cov.json`, `cov_run.log`
- Scripts: `scripts/` (`mutate6.py`, `behave6.py`, `live6.py`, `placebo_read.py`)
- Lab summary: `live/lab_summary.pkl`

Code checked:
- `/Users/as/Documents/lab/active/sonar/sonar/backtest.py` (`_dk_mean_se` :481, `_dk_var` :492, `_dk_lag_of` :518, `_verdict` :770, `_attention_buckets` :870, `_quintile_spread` :965, `attribute` :1011, `_ic_t` :1127)
- `/Users/as/Documents/lab/active/sonar/ui/app.py` (:2711–2784, :3470)
- `/Users/as/Documents/lab/active/sonar/tests/test_backtest.py` (:647, :1226, :1255, :1320, :1357, :1410, :1448)
- `/Users/as/Documents/lab/active/sonar/tests/test_lab_tab.py` (:582, :592, :610)
