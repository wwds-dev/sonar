# Domain review (Finance), Review phase: hourly weekend / hour-of-week vol study

Commit reviewed: 2d6fee5 (`sonar/research/hourlyvol_weekend.py`, `tests/test_hourlyvol_weekend.py`).
Against: app-context Domain specialist section, approved spec `docs/specs/hourly-weekend-vol-study.md`,
Define review `docs/audit/hourly-weekend-vol-study-domain-finance.md`. Date 2026-10-13.
Playbook `docs/playbooks/domain-finance.md`: `status: baseline` (last-reviewed 2026-10-12, 1 day old); unverified guidance.
Not verified: the suite could not run in this sandbox (`tests/conftest.py` fails on `from sonar import macro`, nested repo absent),
so no control or test outcome, and no mutation check, was observed. Findings come from reading the code.
Not a statistician or lawyer; no legal opinion.

Counts: P0 0, P1 2, P2 7.

## What holds up
- No edge, profit or certainty wording in code, docstrings or output. Module docstring (lines 8-12) and `NOT_EVIDENCE` (71-74) state forecast loss only, no costs/slippage (not applicable), already-seen sample, DROP = success.
- Frozen constants match the spec (40-59); `test_frozen_preregistration_numbers` (tests 27-34) pins them. Nothing tunable from the CLI: `main` accepts only `--print-spec-hash` and `--power` (524-539).
- Hash gate: empty `APPROVED_SPEC_SHA256` refuses (512-514), mismatch refuses (515-518), `main` checks before any fetch (527; test 378-382).
- Family of 3, ALPHA = 0.05/3 (48-49). One-sided p as written (232-236), d = base - variant (251), HAC lag 168 (257), context lags 24/9 and block-168 bootstrap (262-265). Verdict order and V2 "LONGER WINDOW ONLY" label match spec (269-289, 356-357).
- Causality: factors read before push (200, 210, 212-213); ewma update uses `_mult(t)` before the profile push; scored hour uses `times[1:]` (314); weekday convention and Sun 23:00/Mon 00:00 boundary tested. Gap and non-positive-close abort (219-229). Scoring set common to all models (325-335).
- Controls can fail: C1 compares pooled QLIKE and verdict (413-415); C2/C3 require significance, blocks and KEEP on single seeded series (437, 444); C4 compares study path to a replay path, to shipped `hv.study`, and to perturbation (453-475). A wrong-boundary mutation guard exists (tests 324-329).

## P1

### P1-1. Run identity is not recorded, so "approved code ran on approved spec" cannot be shown
- `main` 537: the result block holds only `spec_sha256`, provenance and result. Spec (Freeze mechanism) says the owner records the approving commit hash in the spec and in the result block. The hash gate covers the spec file only: the constants, `classify`, `compare` and the controls live in this module, which is not pinned. Editing a constant and its pinning test in one commit passes every check while the spec hash stays unchanged. No run timestamp or code version is printed; the runner can be re-run on a later day (new 730-day pull, same hash) with nothing recording how many runs were made.
- Rule: pre-registration discipline and app-context "every figure traceable" (playbook, baseline, unverified). Scenario: the owner later reads a KEEP and cannot show which code and which pull produced it; a re-run after seeing a DROP is indistinguishable from the first run.
- Fix: print `git rev-parse HEAD` (and `git status --porcelain` clean flag) or a SHA-256 of this module, the UTC run time, and the approving commit hash from the spec in the output; ideally also pin the module hash beside `APPROVED_SPEC_SHA256`. Add a note in the result block that any re-run is a new run and must be logged.

### P1-2. The C1 size check is not part of the run gate
- Spec C1: failure of the 200-seed size check = "apparatus manufactures a pattern; study does not run". `run_controls` (495-498) and `main` (529, 536) run only C1 at seed 7, C2, C3, C4. `c1_size_check` (420-431) is reachable only from `@pytest.mark.slow` tests (tests 336-350), which are skipped in normal builds and whose summary test depends on module-level state from the four chunk tests. The size of the test (type-I rate at 0.0167, with lag 168 on a rolling nested differential) is the main unverified statistical risk the Define review raised (P1-4).
- Scenario: the real run proceeds, and reports a KEEP, though the test was never shown to be correctly sized on this machine at this commit.
- Fix: record a size-check result (rejections per variant out of 200, commit hash) in the audit note before the run, or have `main` refuse unless it is supplied (`--size-check-passed` is not tunable, so better: run it in `main` behind `--full`, printed in the output). Flag the size check outcome to the statistician requested in the spec.

## P2

### P2-1. Bare "KEEP" / "DROP" strings can be misread
- `classify` returns "KEEP" (277) and `DROP` (280), printed per comparison in the JSON (540) with no gloss next to them; the `scope` string sits one level up. "KEEP" can read as "keep it / keep the position"; `pup_shift` says "P(up)". The labels are spec-fixed, so keep them, but add a fixed text per label, e.g. `verdict_meaning`: "KEEP = candidate for a later spec only; forecast loss on historical BTC hours; not a signal, not profit". Also never print the words "weekday effect" except when V2 vs B0L passes (already enforced, 283-289).

### P2-2. Labels are missing on outputs outside `result`
- Period is raw epoch seconds (`first_bar`, `last_bar`, 534); add ISO UTC dates and the run time. `controls`, `power_v1` (539) and the `{"error": ...}` return (312) carry no `scope` string; `power_v1` is a detection rate on simulated series and should say "simulated". App-context requires period, sample size and cost treatment with every figure; `result` has n_scored and scope, the rest do not.

### P2-3. Numbers still print when controls fail
- With `controls_ok` False the verdict is "NOT RUN" (272-273) but improvement, t, p and pooled QLIKE are still emitted (353, 359-361). A failed-control run could be quoted selectively. Suppress or tag them "apparatus failed; not evidence".

### P2-4. B0L vs B0 attribution line is absent
- Spec: B0L vs B0 reported as attribution only. `FAMILY` (48) correctly excludes it, but no B0L-vs-B0 comparison is computed; only `pooled_qlike` is shown (360). The owner cannot split window length from profile shape for V1/V2 from the output alone.

### P2-5. Equivalence control is partly tautological, and the naive reference is thin on long windows
- `forecast_sigma` (364-374) reuses `_Est`, so C4's study-vs-replay comparison (458-462) cannot detect an error inside `_Est`/`_Cells`; only B0 vs shipped `hv.study` (463-467) and the test-file naive reference are independent. The naive reference is checked at 1500-1700 hours (tests 220), so the 4368 h eviction path for `_Cells(168, 4368)` is unexercised beyond the small unit test (tests 119-127). Add a naive-reference check past 4368+ hours for V2/B0L (slow-marked).

### P2-6. Controls rest on single hand-picked seeds
- C2 seed 2, C3 seed 3, C1 seed 7 (52, 436, 443). A pass is one draw; spec accepts this, and the power simulation (479-492) is the real resolving-power statement, but it only runs under `--power` (538). Make the power table part of the default output (non-gating) so the owner always sees "not detected here" in context. Git history shows one commit, so seed choice after seeing failures cannot be excluded; not verified.

### P2-7. Jargon collision
- `ALPHA` (49) is the significance level; in finance "alpha" means excess return, which this app says it does not claim. Rename to `SIGNIF_LEVEL` in code and output (the `alpha` key at 359). Cosmetic, avoids a future copy leak.

## Needs a qualified human
- The statistician's check of lag 168, DM validity for nested rolling forecasts and heavy-tailed single-hour QLIKE (spec open question 3) remains open; nothing in this commit settles it.
- Any proposal to wire V1/V2 into `forecast()` needs its own spec, `model-validator` and a fresh domain review (not before 2026-11-09 per the spec).
