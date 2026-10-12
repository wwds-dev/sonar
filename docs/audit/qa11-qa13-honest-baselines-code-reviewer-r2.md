# Code review, round 2: QA-11 / QA-13 honest baselines (loop-1 changes, uncommitted)

- Reviewer: `code-reviewer` (read-only), 2026-10-11. Saved by the orchestrator. Mutants in memory via a pytest `-p` plugin; scripts in the session scratchpad.
- Playbook `docs/playbooks/code-reviewer.md` still `status: baseline` (stale per AGENTS.md).

**Verdict: ship after fixes.** No P0/P1. The floor is correct: T = 2 is compared, full windows (T = 4) never touched, h = 1 cannot produce a short window, step has no effect, n = 0 summaries carry the counts. Before release: P2-1 (Terminal backtest always empty on the "This year" profile, unexplained) and P2-2 (Document-phase restatements, now covering the floor; QA's figures are stale).

## Evidence
- `test_scoring`, `test_backtest`, `test_engine`, `test_lab_tab`: 195 passed. Full suite offscreen 1,820 passed / 30 deselected (45.0 s); native 1,820 (48.7 s). Known `libshiboken … MainWindow already deleted` traceback still prints.
- Mutants, 14: 12 killed (floor removed — 5 tests; `<`→`<=`; floor on timeouts only; `run()` routes short timeouts into `n_timeout`; n = 0 drops counts — 3; `abs(delta)` removed; Lab hides short count; Terminal hides short count; Terminal raw expectancy; Terminal drops "resolved in time"; `_mean_se` without NW — both NW tests; rest's se plain — `test_the_rest_gets_the_wider_error_bar_too`). Survived: `n_timeout_data_end` also counting short windows (P3-3); a reworded n = 0 explanation (weak mutant — kept the asserted phrase).
- Floor edges: `range(MIN_LOOKBACK, len(bars) - 2, step)` (`sonar/backtest.py:284`) guarantees window ≥ 2 bars, so at h = 1 T ≥ 2 and `n_short_window` is 0; `window/horizon_days` exact at T = 2; `step` does not enter `window`; full windows T = 4 asserted.
- Where the floor bites: decisions start at i ≥ h (`:289`), so a compared row needs ~3h + 3 bars. 2y (~502 bars) → n = 0 for h ≳ 166; 1y → h ≳ 83. 20 walks × 502 bars: h = 250 and 200 give n = 0, n_short 1,660 / 2,000, n_timeout 0; h = 126: n = 615 vs 1,660 short.
- SM5 effect (129 synthetic walks, 2y, h = 5, step 3), floor on vs off: n 18,418 / 18,620; hit 39.29% / 39.21%; predicted 39.44% / 39.36%; n_timeout 1,448 / 1,633; n_timeout_data_end 57 / 242. "Realised hit rate unchanged" is no longer literally true (~+0.08 pt).
- Consumers (grep): nothing outside `sonar/backtest.py`, `ui/app.py` and tests reads `n_timeout_data_end`, `short_window`, `truncated`, `keep_timeouts`; only production caller of `run_symbol` is `run()` via `ui/worker.py`; dropping resolved short rows touches only `tests/test_earnings.py` and `tests/test_backtest.py` (both pass).

## Findings
**P2-1 — Terminal backtest always empty on the "This year" profile, unexplained** (`ui/app.py:3404-3406`, `:3410-3421`, `ui/worker.py:59`, `sonar/horizon.py:135`). `_run_backtest` passes `momentum_days` with fixed `rng="2y"`; YEAR has `momentum_days=250`, ~502 bars, so every decision is short → "backtest: no resolved trials · 0 timed out · 1,660 too near the end of the data". No range control; tooltip/status ("replaying two years of bars…") give no way out; the Lab's explanation isn't repeated. (Before the floor this call produced the P1-1 false positive.) Fix: pick the range from the horizon ("5y" when 3·h + MIN_LOOKBACK > ~500 bars), update tooltip/status, append the Lab's one-line reason at n = 0 with short windows, show "· 0 timed out" only when non-zero.

**P2-2 — docs contradict the code; QA's restatement numbers are stale** (Document, before release). ADR 0001: "a trial cut short … gets its true, shorter T" (floor now excludes T < 2); "realised hit rate is unchanged" (~+0.08 pt); timeouts "shown against / monitored by … `timeout_share_expected`" (owner restatement pending); Alternatives "drop every decision point whose full window does not fit" — the adopted floor is a partial form; record it as the decision. Spec body `:380-385`, `:449-450`, `:575`. `TESTPLAN.md:212` / `static/testplan.html` ("Predicted reads 40%"). Unchanged since round 1: `TODO.md:251`, `static/docs.html:620`, `:669-676`, `CONFIDENCE.md:587`. QA's 39.64% / 39.37% / n 19,119 / 2,824 were pre-floor. Fix: re-measure the live Lab default on current code; state the floor, `n_short_window` and the new meaning of `n_timeout_data_end` (truncated timeouts with 2 ≤ T < 4 only) in the ADR.

**P3-1 — n = 0 headline says "no resolved trials" when setups resolved but were not compared** (`sonar/backtest.py:403`, `ui/app.py:2675`, `:2668`). The explanation (`:2688-2690`) names rule and remedy but understates the need (data must also cover one horizon before each setup: 2y supports h ≤ ~166, 1y h ≤ ~83). Fix: "nothing to compare" when `n_short_window > 0` and n = 0; optionally state the largest horizon the range allows.

**P3-2 — always-zero clause at h = 1** (`ui/app.py:2705-2706`, `:3414-3415`): `is not None` prints "· 0 too near the end of the data" on every Intraday Terminal line and h = 1 Lab run. Fix: `> 0`.

**P3-3 — relation between `n_timeout_data_end` and `n_short_window` not pinned** (`sonar/backtest.py:399`): semantics changed (242 → 57); `tests/test_backtest.py:460` asserts only `>= 0`; the add-`len(short_windows)` mutant survives. Fix: assert equality with truncated non-short timeouts in a `run()`-level test; document the field.

## Copy
No verdict implies edge/profit/certainty; `test_no_backtest_verdict_promises_anything` guards every branch; plain/expert via `words.pick` on both surfaces; "Expectancy beyond a no-edge market" uses "edge" as a denial (spec-approved); "ran out of time" (Lab) vs "timed out" (Terminal) per Design.

## Note for model-validator (not against this diff)
On 2y every compared row at h ≳ 119 is truncated with 2 ≤ T < 4 — no full windows; P1-1's placebo bands don't show whether T ∈ [2,4) is clean at long h. Driftless walks at h = 60 (20 × 502 bars, five seed sets): one set read "worse than a coin flip" (−7.1 pt, se 3.1) with or without the floor; deltas spread ~4.2 pt vs reported se ~3.3 — the known optimistic-se issue at long horizons, not caused by the floor.

## Round-1 findings
| # | status |
|---|---|
| P2-1 `timeout_share_expected` not shown | Resolved by owner decision; ADR/spec restatement pending (P2-2) |
| P2-2 NW untested | Resolved (`tests/test_engine.py:1109`, `:1126`) |
| P2-3 docs | Unresolved (Document); wider now |
| P3-1 unrounded test classifier-only | Unresolved, accepted gap (`tests/test_engine.py:1185`; `engine.py:778` reads `rd["reading"]`) |
| P3-2 double sign | Resolved |
| P3-3 Terminal vs Lab | Resolved |
| P3-4 perf under lock | Unchanged (optional) |
| P3-5 vacuous test | Resolved |
