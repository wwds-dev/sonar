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
