# Code review: hourly weekend / hour-of-week vol study (commit 2d6fee5)

Reviewer: code-reviewer (read-only). Date: 2026-10-13.
Scope: `sonar/research/hourlyvol_weekend.py` (545 lines), `tests/test_hourlyvol_weekend.py` (403 lines)
against `docs/specs/hourly-weekend-vol-study.md` and `docs/audit/hourly-weekend-vol-study-domain-finance.md`.
Playbook: `docs/playbooks/code-reviewer.md` is `status: baseline` (last-reviewed 2026-10-10, 3 days old): seeded, not radar-verified, so unverified guidance.

Counts: P0 0, P1 0, P2 3, P3 6.

Evidence run: `tests/conftest.py` cannot load in this sandbox (`ImportError: cannot import name 'macro' from 'sonar'`, nested repo absent), so I ran
`python3 -m pytest --noconftest -c /dev/null --rootdir=. -p no:cacheprovider tests/test_hourlyvol_weekend.py`:
52 passed in 136 s including the 5 slow tests (200-seed C1 size check passes the <= 10 per variant limit). With `-m "not slow"`: 47 passed in 11 s.
Native/offscreen full-suite modes: not verified here.

## Checked and found correct
- Frozen constants (lines 40-59) match the spec: windows 4368 and 1440 (`hv.DIURNAL_WINDOW`), lag 168, context lags (24, 9), bootstrap block 168,
  family of 3 in the spec's order, ALPHA = 0.05/3, THRESHOLD 0.01, KEEP_BLOCKS 5, MIN_CLASS_HOURS 100, MIN_SCORED 2000, clamp from `hv.PROFILE_CLAMP`, C1 floor 0.995, 200 seeds / 10 rejects, power 1.05-1.3 x 50 seeds.
- Calendar (80-91): `((t//86400)+3)%7`; Sun 23:00 weekend, Mon 00:00 not; tested at tests:37-43. Scored-hour alignment uses `ts = times[1:]` (314), forecast path uses `times[-1]+3600` (373).
- No look-ahead: in `study_weekend` (325-346) every model's `var(t)` is read before `push`; in `_Est.push` (202-213) the EWMA update uses `_mult(t)` and the class factor input uses `prof.factor(cell)`, both before `prof.push`/`cls.push`. Seasonal profiles, the 4368 h B0L/V2 windows and V1's rd2 (stored as r^2/f_h as of before that hour, never recomputed) see only earlier hours. Scoring starts after 4368 h for all models on one shared set. Causality is tested (C4, 468-475: perturbing return j leaves forecasts for hours <= j bit-identical).
- Sidedness: `one_sided_p` (232-236) is correct against two-sided `stats.normal_p` (stats.py:93-95): t>0 -> 0.5*p2; t<=0 -> 1-0.5*p2; a worse variant gets p > 0.5. `newey_west_t` returning (0,0) on n<10 or var<=0 yields p = 0.5, never a false positive. d = base - variant (251), positive = variant better. Tested (tests:52-72).
- QLIKE: reuses `hv.qlike` (floors both sides at MIN_VOL). Zero returns, tiny EWMA and underflow to sigma 0 all stay finite in the loss. Empty/short class: `_ClassFactor.factor` returns 1.0 below 100 hours before any division (157-158); zero-total guards in `_Cells.factor` and `_ClassFactor.factor`. Tested.
- Verdict rules (269-280) match spec rules 1-6 in order (NOT RUN, INSUFFICIENT, KEEP/WEAK at I >= 1.0% and p < ALPHA, DETECTED BELOW THRESHOLD for 0 < I < 1.0%, DROP); `v2_label` demotes only a KEEP lacking I>0 and p<ALPHA vs B0L. Parametrized test covers the boundaries (p strict, I at exactly 1.0%).
- SHA-256 gate: `check_spec` (508-519) raises on empty approved hash and on any mismatch; `approved=""` is not treated as "use default" (`is None` test). `APPROVED_SPEC_SHA256 = ""` is committed, so `main()` refuses today; `main` calls `check_spec` before `run_controls` and before `fetch_hourly` (527-531); tests:361-382 cover empty, changed, and no-fetch.
- Nothing existing modified: commit touches only the two new files plus TODO.md and docs/company/activity.jsonl. `grep` finds no importer of the new module outside its own test (the matches under `.claude/worktrees/` are a stale worktree copy). It imports `hourlyvol` and `stats` only to read constants and reuse `_Diurnal`, `qlike`, `_Rolling`, `log_returns`; `test_the_live_forecast_is_untouched` (tests:391-396). `sonar/model.py`, `forecast()`, `hourly_sigma` untouched.
- Stdlib only (hashlib, json, math, random, sys, pathlib). Copy: module docstring (8-12) and `NOT_EVIDENCE` (71-74) carry "historical, simulated, forecast loss only", not profit, no costs/slippage (n/a), already-seen sample. No edge, profit or certainty claim found.

## P0
None.

## P1
None.

## P2

### P2-1. The C1 size check is not part of the runner's control gate
- `hourlyvol_weekend.py:495-498` (`run_controls`) and `:529-536` (`main`). Spec C1: "Failure = apparatus manufactures a pattern; study does not run", and the 200-seed size check (<= 10/200 per variant) is a C1 requirement. It exists as `c1_size_check` (420-431) and as `@pytest.mark.slow` tests (tests:336-350), but `run_controls` runs only C1 seed 7, C2, C3, C4. `pyproject.toml:45` deselects `slow` by default.
- Scenario: owner sets the hash and runs `python3 -m sonar.research.hourlyvol_weekend` without ever running `-m slow`; if the HAC at lag 168 over-rejects (size > 5%), `controls["ok"]` is True and a KEEP is printed from an apparatus whose size was never checked. (It passes today, 200 seeds, but the gate is a process promise, not code.)
- Fix: either call `c1_size_check()` from `run_controls` behind a `--full-controls` default-on flag (about 2 minutes), or print "C1 size check: NOT RUN in this invocation" in the output and in `controls` so the result block cannot silently omit it; add a line to TODO.md that the owner runs `-m slow` before the real run.

### P2-2. The result block does not record the approving commit hash
- `hourlyvol_weekend.py:537`: `out = {"spec_sha256": ..., "provenance": ..., "result": ...}`. Spec "Freeze mechanism": the owner records the approving commit hash "here and in the result block"; the finance review P1-1 required it. Nothing in the runner accepts or prints it.
- Scenario: the result note cannot be tied to an approved commit; only a file hash which, after the owner edits the spec to record the commit, no longer matches the hash of what was reviewed.
- Fix: add `APPROVED_SPEC_COMMIT = ""` beside the hash constant, include it in `out`, and refuse to run if empty (same pattern as `check_spec`). Document the order: spec edit with the commit -> compute `--print-spec-hash` -> set both constants.

### P2-3. `study_weekend(warmup=...)` lets a caller score B0L and V2 on incomplete windows
- `hourlyvol_weekend.py:305,311,325`. `warmup` is a free parameter; any value below `LONG_WINDOW` (4368) scores the 26-week models before their window is full, contradicting spec "starting after 4368 h of warm-up". The runner uses the default, so the real run is safe; the risk is a future caller or test and the `trace` path.
- Scenario: `study_weekend(c, t, warmup=1440)` returns a verdict computed from V2 with a partial window, with no warning.
- Fix: `if warmup < LONG_WINDOW: raise ValueError` (or drop the parameter); the tests use only the default.

## P3
- P3-1. `pup_shift` (`:298`) divides by `sv` with no floor; `sig` (329-330) is not floored at `MIN_VOL` while `qlike` is. A sigma that underflowed to 0 raises ZeroDivisionError after a full run. Not reachable on real BTC data; use `max(sv, hv.MIN_VOL)`.
- P3-2. `check_series` (`:227`): empty `closes` gives "non-positive close in the series" (0 != -1), a misleading message. Add an explicit `len(closes) < 2` error.
- P3-3. C4's equivalence part (`:458-462`) compares `_Est` driven by the study loop with `_Est` driven by `forecast_sigma`: same class, so it proves loop wiring, not estimator correctness. Independent correctness rests on `test_estimators_equal_a_naive_reference` (tests:208-224), which stops at 1700 hours, so 4368 h eviction for B0L/V2 is covered only by the small-window unit test (tests:119-127). Acceptable; a naive-reference run past 4368+ hours for V2 (one seed, one origin) would close it.
- P3-4. Slow size check (tests:332-350) aggregates through module globals across five tests; run alone (`-k`) or reordered, the last test fails on its guard assert (safe-fail, but confusing). Also the `slow` marker is registered only in `pyproject.toml`.
- P3-5. The hash gate is case-sensitive and byte-exact on `read_bytes` (`:505`): an upper-case pasted hash or CRLF checkout refuses to run (safe-fail). Mention in the comment at 61-64. No `main()`-level test for a non-empty wrong hash (only `check_spec`, tests:368-375).
- P3-6. Wording: the verdict label "KEEP" (`:277`) is shared vocabulary with `hourlyvol.Verdict` but reads as "adopt"; the result note should say "improvement detected" rather than "keep" outside this file. No change needed in code.

## Not verified
- Real-data behaviour (Binance blocked; no pull attempted). Native and offscreen full-suite runs and coverage floor not run here (conftest import failure in this sandbox; unrelated to the commit).
- Statistical validity of HAC lag 168 for nested rolling forecasts is a statistician question the spec already routes to the owner; not assessed.
- Spec file sha256 as of review: `24b0b9f06fcc5dc31d87a25826d056acbe56c87d51d8b2c4d5c0ed23e55b8965` (it will change when the commit hash is recorded).
