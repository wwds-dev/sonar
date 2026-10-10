# T1-1 review — model-validator, 2026-10-10

Read-only (the real book read, never written). Wilson verified by hand (10/21 → [0.2834, 0.6763]).
New tests fail on the old code (7). Real book: new 21 graded, 47.6%, CI 28–68%, not calibrated,
IC −0.32; old code on the same book: calibrated, +0.0899σ applied to every row.

**P0: none.**

| ID | Finding | Outcome |
|---|---|---|
| P1-1 | Re-checking after every close: P(trip at least once | no edge) 16.5% by n=50, 23% by 100, 30% by 200, 37% by 500 at z=1.96; z=3.0 → 2.7–3.7% | Claims now need z=3.0 (`Z_CLAIM`), also for the rank-IC verdict |
| P1-2 | The pooled hit rate cannot measure drift: coin-flip protocol direction; m=0.5 → 42.1% pooled; discrete-mark driftless walk 40.6–41.3%, t3 tails 41.2–42.4%; passing the gate would feed geometry into every LONG plan; paper fills at the barrier hide gaps | **Owner decision: report only** — calibration never moves P(profit) |
| P2-1 | Dropping MANUAL closes is selective | Moot for P(profit); `n_manual` shown on screen; residual risk |
| P2-2 | Drift used the point estimate | Moot (no drift) |
| P3-1 | Mixed historical p_profits: not an issue today (all 0.40); delayed fills latent | Residual risk |
| P3-2 | Tests failed on missing keys, no negative-drift / scanner test | Scanner-level test added (`test_a_winning_book_never_moves_p_profit`) |
| P3-3 | UI never showed `n_manual`; "22 of 21" possible | `n_manual` row added on the landing page |
| P3-4 | Rank-IC verdict also re-checked every close | Threshold raised to 3σ |
