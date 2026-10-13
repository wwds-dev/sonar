# Code review: sign-randomisation verdicts (`git diff 049b930..HEAD`)

- **Reviewer:** `code-reviewer`, read-only. Saved by the orchestrator, 2026-10-12.
- **Playbook:** `status: baseline`; the owner chose to continue.
- **Ran:** 31 targeted tests, all passed (150.9 s, load ~118). Also a scratchpad probe of each rate test, gated and ungated. The full suite was not run.

## Findings
- **P2-1. The literal `{measured}` renders in every "beats" verdict.**
  - Where: `sonar/backtest.py:160`, used at `:999`. `tests/test_backtest.py:708-715` pins the placeholder.
  - Nothing automated blocks a release.
  - Fix: a guard that fails while any `_verdict` output contains `{` (or a release-checklist item). Fill the figure from the validator.
- **P2-2. The "below" sentence contradicts itself.**
  - Where: `backtest.py:1003-1008`.
  - Under the gate, "below" does show the chosen directions read worse than the swapped ones (one-sided 2.5% per run), so "does not show … coin flip" is wrong. The sentence also omits the per-run chance rate.
  - Fix: reword to match "beats", then update `tests/test_backtest.py:114` and `:720`.
- **P2-3. The four-horizon market-wide guard is not nested as built.**
  - Where: `tests/test_backtest.py:1704-1709`, `:1821`.
  - It uses `ceil(4·15·365/252)` = 87-day blocks, while production uses `4·ceil(15·365/252)` = 88.
  - Probe on worlds 0–14:

    | Coin | Ungated | Gated | Gate alone |
    |---|---|---|---|
    | 87-day market-wide (as built) | 58 | **24 (8.0%)** | 24 |
    | 88-day market-wide (production rounding) | 49 | **11 (3.7%)** | 12 |
    | 174-day per-class 8h | 63 | 21 (7.0%) | — |

  - The test passes only because the bound of 34 is a 99th percentile.
  - Fix: build the nested coin with production rounding. Keep the 87-day coin as an explicit off-grid / shifted-edge guard, with its 8.0% in the docstring. **Early evidence that measure 2's shifted-edges placebo may fail at full scale.**
- **P2-4. The exactness test takes about 55 s alone, against the 60 s faulthandler cap that ends the whole run.**
  - Where: `tests/test_backtest.py:1769`; `pyproject.toml:32-33`.
  - It measured 54.85 s at load 118, because it replays all 30 worlds unless it runs after the headline tests. The attribution guard took 34.1 s.
  - Fix: session-scoped fixture of worlds shared by the headline, exactness and guard tests, or assert exactness inside the headline tests.
- **P3-1.** Test A alone does not catch "gate removed" (ungated: 24 verdicts, 10 beats, within bounds). Test B does (31 > 24). Reword A's docstring to "with its twin, catches the gate removed".
- **P3-2.** The attribution guard (24 runs, ≤ 4) cannot tell gate from no gate. Accept it as labelled, or raise N after P2-4.
- **P3-3.** A run that fails closed (missing `opp_outcome`/`t`, or `horizon_days=None` with a universe) reads `few_clusters` with false advice ("0 stretches … a longer range"). Unreachable from `run()` today. Docstring `:661-665` is stale. Fix: a separate `unpaired` reason, or assert it cannot happen.
- **P3-4.** An untested component (`p_rand` None, treated as 1, `:1324`) reads UNCONFIRMED, with copy describing a reshuffle that never ran. Give it its own sentence.
- **P3-5.** The attribution gate keys on `horizon_days` and fails open; the headline keys on `universe` and fails closed (`:1291`). Make the exemption explicit, e.g. `gate=False`.
- **P3-6.** The A15 fallback above 80 days contradicts the measured map (10y is judged to h90). No profile is affected. Fix the docstring at `:376`/`:386`, or extend to 90.
- **P3-7.** The seed docstring (`randomisation.py:71-74`) overclaims validity. Say "harmless in practice; exact on the enumerated path".
- **P3-8.** The suite budget went from 300 s to 600 s (`run-tests.sh:23`). It is justified, but needs the owner's nod. With P2-4 done, 300–400 s may suffice.

## Checked and sound
- Randomisation arithmetic:
  - enumeration includes the observed pattern; Monte Carlo uses (1+#)/(1+B) with B = 11,999; ties count against the run;
  - the sign of `p_tail` equals the sign of Δ; fsum makes the sums order-free; N recomputes under a swap;
  - the V floor is fail-closed; the draw is unbiased; the seed is independent of hash seed and row order.
- Cluster blocks: correct (8/32/88/116/348 pinned), Unix-0 anchor, UTC entry date, no class in the key. Attribution uses the same blocks.
- State composition: the order is right and `significant` is derived from the state.
- Copy: no user string says "confirmed", "verified" or bare "unconfirmed".
- Threading: `BacktestThread` is unchanged, no module state, nothing heavy on the UI thread.

## Verdict
No P0 or P1. The statistics, the clusters and the composition are correct and pinned. Before release, fix the placeholder (P2-1), the "below" copy (P2-2) and the 55 s exactness test (P2-4). The 87-day coin reading 8.0% goes to the validator (P2-3).

## Re-review after fix loop 1 (`a0b4fdf..HEAD`)

**Ran**
- `tests/test_backtest.py` and `tests/test_attribution.py`: 94 passed in 302 s.
- Lab copy tests, both modes.
- `-m release`, and the suite-size test (2,203).
- Ruff 0.17.0 on clean exports.
- The full suite was not run.

**Status of earlier findings**
- All earlier P2/P3 findings are resolved, except **P3-8** (the 600 s budget), which waits on the owner.
- These are correct and pinned: the `unpaired` path, `attribute(gate=True)` failing closed, `range_for_horizon` returning 2y/5y only, the `_cached_world` cache (deterministic, never mutated), exactness equal to `summarise` (full dict equality), the release marker override, and the copy constants (no `{`).

### Findings
No P0, P1 or P2.
- **P3-1.** Nothing runs the release check. Neither the `sre-release` agent nor the app-context release checklist mentions `-m release`, and CI deselects it. Either drop the marker (the test takes ~0 s) or add it to the release checklist.
- **P3-2.** The headline rate tests take 28 s alone and up to 50 s in file order at load ~56, against the 60 s cap that aborts the run. This contradicts the build note ("≤ 22 s"). Split them into 150-run tests or share precomputed runs, and record the worst case honestly.
- **P3-3.** The residual says "can beat the bar too" under a "below" reading (`backtest.py:169-170`, `:1028`, `:1054`). Use "land outside the bar".
- **P3-4.** Session caches hold about 225 MB for the rest of the suite. Clear them on module teardown.
- **P3-5.** The branch adds **7 ruff findings**: B905 in `sonar/randomisation.py:142,148,149,154,155,162,203` (049b930 = 97, HEAD = 104). They are not bugs, but they break the definition of done; add `strict=True`. The gap from 86 to 97 is drift on master.
- **P3-6.** The Lab still judges 10y. The owner has since decided: withhold 10y in the Lab too.

### Verdict
Ready for Verify. P3-1, P3-3 and P3-5 are cheap to fix before merge.

## Re-review after fix loop 2 (`87d664b..HEAD`)

**What was run:**
- 143 fast targeted tests offscreen, and the Lab tests natively: all passed.
- 17 slow rate tests passed; the maximum was 17.1 s at load ~150.
- With the gate removed (alpha 1.01), 7 rate tests fail, matching their docstrings.
- Ruff: 97 findings at 049b930 and 97 at HEAD, as identical sets.
- The binomial bounds were recomputed independently and are correct.

The full suite and coverage were not run.

All earlier items are resolved, except first-review P3-8 (the 600 s budget, an owner call).

### Findings
No P0, P1 or P2.
- **P3-1.** The owner bullet ("tip no longer points at longer ranges") contradicts the shipped "or a longer range up to five years" (`backtest.py:1040`, `:1016`). The owner should confirm or drop it.
- **P3-2.** "Far more often" (`backtest.py:984`) goes beyond the held-out figures (10–12.5% vs 9.1%). The domain review raised the same point.
- **P3-3.** The drift rule's order is only half pinned. Moving `drift` below `span` survives the suite. Add `_rigged_rows(50)` with rng="10y" expecting `drift`, and universe="Equity" with rng="10y" expecting `single_class`.
- **P3-4.** Measure 8's catch probability, re-stated as "about 0.88", assumes the sets are independent, but they share worlds, so the true figure is lower. Say "≤ 0.88 (sets share worlds)". The owner's nod is needed on re-stating a success measure.
- **P3-5.** The attribution footer says "judged together" on withheld runs, where nothing is judged (`ui/app.py:3079-3091`).
- **P3-6.** `static/docs.html:716` still gives the old range advice and has no 10y row (Document).

### Verdict
No P0/P1/P2. Ready for Verify. P3-1 and P3-4 need the owner. P3-3 is a cheap test gap.

## Final review of fix loop 3 (`8991772..HEAD -- sonar ui tests`)

**What was run:**
- Fast tests: 123 passed offscreen; 46 passed native for the Lab file.
- The new 600-run test passes alone in 41.4 s (load ~65), and in under 5 ms in suite order (cache hit).
- Mutation check: 9 of 9 mutants killed (drift order, `offers_longer_range`, span tip, rng passthrough, footer skip, survivorship line, `_short_window_reason`).
- Ruff: 97 at HEAD, with identical findings on the changed files.
- The full suite and coverage were not run.

### Findings
No P0, P1 or P2.
- **P3-1.** The 600-run test stays under the 60 s cap only because of the cache. Run alone above load ~100, it can trip the faulthandler abort. Document it as the exception, or pool the counts inside the headline cases.
- **P3-2.** "About 1 in 4" appears on every 10y horizon but was measured only at h20 and h60 (`backtest.py:1001-1002`). The error is in the cautious direction. Scope the figure to "at 20- to 60-day horizons", or have the owner accept it as is.
- **P3-3.** The comment at `backtest.py:996` claims both figures are quoted, but only r5 is.
- **P3-4.** The removed `summarise([], rng="10y")["n"] == 0` assertion leaves the empty-run path unpinned. Restore it.
- **P3-5.** `tests/test_backtest.py:2116` is 103 characters.

### Verdict
No P0/P1/P2. Ready for Verify. The P3s are cheap and optional; P3-2 is a wording call.
