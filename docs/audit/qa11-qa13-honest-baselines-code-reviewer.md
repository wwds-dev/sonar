# Code review: QA-11 / QA-13 honest baselines (uncommitted diff)

- Reviewer: `code-reviewer` (read-only), 2026-10-11. Saved by the orchestrator.
- Spec: `docs/specs/qa11-qa13-honest-baselines.md`; ADR 0001.
- Playbook `docs/playbooks/code-reviewer.md` is `status: baseline` (stale per AGENTS.md).

**Verdict: ship after fixes.** No P0 or P1. Maths, caching, truncation, branch order and Lab fallbacks verified by running code. Before release: P2-2 needs a test; P2-3 is Document-phase and must land; P2-1 needs an owner/architect call (the spec contradicts itself).

## Evidence run
- `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_scoring.py tests/test_backtest.py tests/test_engine.py tests/test_lab_tab.py` → 186 passed in 3.80s.
- `QT_QPA_PLATFORM=offscreen ./run-tests.sh` → 1811 passed, 30 deselected in 41s; one known teardown traceback ("Internal C++ object (MainWindow) already deleted", `ui/app.py:3888`). Native: not verified by the reviewer.
- Image series vs eigenfunction series over k_t ∈ {1,1.5,2,3,5}, k_s ∈ {0.5,1,2}, m ∈ ±{0,1,3,5}, T ∈ {0.05…20}: worst disagreement 1.4e-6 at k_t=5, k_s=2, m=5, T=0.05, where the eigen reference is the wrong one (−1.4e-6 vs 3.7e-100). Elsewhere within 1e-9.
- Monotone in m: no violations across 1,001 m × 18 (k, T) pairs — the bisection is sound.
- Extremes: no NaN, negative or sum > 1 for T ∈ {1e-9…1e4}, m ∈ {±20, ±5, 0}; underflow guard returns 0, 1, 0.5 correctly.
- Truncation unbiased: 12 driftless 10-year walks at h=250, data-truncated resolved trials gap +0.002 (n=1,533); `window`/`bars_held` match `_resolve`'s bound.
- Implied drift matches `calibration.implied_edge` exactly for untimed hit rates 0.02–0.99; the ±5 bracket never binds.
- `expectancy_vs_null_r` = (1+rr)(w−q): correct.
- Cost (worst case h=250, step 1, 10y, 5 walks): `summarise` 0.52s, `run_symbol` 0.32s; at h=5 `summarise` 0.02s. Bisection groups bounded by 4h windows; the 8,192-entry cache churns at h=250 (54,636 misses), harmless.
- Mutants (pytest `-p` plugins, no file edits): `predicted` on the untimed baseline — killed (7); LOO-style `robust_ev > 0` — killed (4); classifier rounding — killed (1); two Newey-West mutants **survive** (P2-2).

## Findings

**P2-1 — `timeout_share_expected` computed but shown nowhere** (`sonar/backtest.py:440`, `ui/app.py:2683-2689`). Spec (447-449, 573-575) and ADR 0001 call it the on-screen check on σ̂ and the vol model. Scenario: coarse paths realised 9.45% timeouts vs 5.34% expected; the user sees only "1,175 ran out of time (9.4%)". Fix: add "(a walk with nothing in it leaves {expected:.1%})" to the Resolved setups row, or drop the claim from spec/ADR.

**P2-2 — the Newey-West half of the buyability error bar is untested** (`sonar/engine.py:101-111`, `:134`). Mutant c (rest's se plain only) and mutant d (no HAC in `_mean_se`) pass all 103 tests in `tests/test_engine.py`. Scenario: clustered wins clear 3 plain se but not 3 HAC se; dropping HAC would read "measured". Fix: a block-clustered test where `3·plain < ev < 3·hac` must be "within noise", and one where only the rest is clustered.

**P2-3 — docs still describe the removed check and the old baseline:** `TODO.md:251` (leave-one-out, "one whale"), `static/docs.html:620` (Predicted = `1/(1+R:R)`, 40%), `static/docs.html:669-676` (no 3 se / two-best-hours), `CONFIDENCE.md:587` ("39.58% against a 39.99% prediction"). Fix in Document, before release.

**P3-1 — the unrounded test pins the classifier, not `buyability()`** (`tests/test_engine.py:1133`). A regression rebuilding the verdict from rounded row values at `engine.py:780` would pass. Fix: a scorelog with t within ~1e-4 of 3 asserted through `buyability()`, or accept the gap explicitly.

**P3-2 — double sign in the backtest's negative verdict** (`sonar/backtest.py:456`): "Hit rate is -10.0 points below the prediction". Fix: `abs(delta)`.

**P3-3 — Terminal line disagrees with the Lab** (`ui/app.py:3402-3405`): "predicted" without "resolved in time"; raw `expectancy_r` (−0.014R at 1.5:1 on a no-edge market) while the Lab shows `expectancy_vs_null_r` — the two can differ in sign. Fix: label "raw expectancy" or show the vs-null figure.

**P3-4 — buyability cost under the engine lock** (`sonar/engine.py:750`): two Newey-Wests per gate per snapshot; at n=8,760 ~18.2ms/gate vs 8.4ms (~110ms/snapshot after a year vs ~50ms). Within the spec's budget. Optional: compute robust fields only when n ≥ `SCORE_MIN_SAMPLE`.

**P3-5 — `test_unresolved_trials_are_dropped_not_counted` is vacuous** (`tests/test_backtest.py:102`): flat bars give vol 0, so `_resolve` never runs. Covered now by `test_the_default_output_is_resolved_rows_only`. Delete or rename.

## Note for model-validator (pre-existing, not caused by this diff)
Lognormal prices with arithmetic barriers: bias grows with horizon and splits by direction. Driftless 10-year walks at h=250 vs the new baseline: LONG +4.7 pt, SHORT −19.1 pt; aggregate −6.1 pt (seeds 0–11, step 5) and −1.4 ± 3.75 pt (seeds 20–31, step 3). The Lab allows h up to 250; ADR 0001's stated residual ("−1 to −2 pt at h=20") does not cover it. Not blocking; follow-up should restate the long-horizon residual or move to log-space barriers.

## Copy
No verdict string contains "edge", "whale", "profit" or "leave-one-out"; T11-8 covers all five branches. The Lab label "Expectancy beyond a no-edge market" contains "edge" (spec-approved; worth a ux-designer glance).
