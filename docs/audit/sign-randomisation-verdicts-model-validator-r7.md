# Model validation r7 (Verify): sign-randomisation verdicts on the built code

**Setup**
- `model-validator`, read-only. Saved by the orchestrator, 2026-10-12.
- Playbook `status: baseline`; the owner chose to continue on it.
- Built code imported from the worktree (commits ad0db01, ce668bf, 6423c56). `SONAR_DATA` pointed at an empty scratch dir; Application Support was never touched.
- Load 55–266 on 8 cores; about 90 min of compute.
- Scripts and outputs are in the session scratchpad `val2/` (temporary).

**Held-out set** (frozen before any run)
- Primary: watchlist from 2006-01-01 to 2016-09-30, 110/129 instruments (crypto 2). `primary_bars.json` sha256 `404f5a77…f25110`. Survivor-biased, like r5.
- Secondary: 96 non-watchlist symbols over the r5 window. `47ab947c…dbbfdc92e0`. Fetched and frozen, **not run**.

**Reproduced**
- Lab default 2y h5: n 18,973, Δ +0.11, se 0.88, q 22.
- An independent re-implementation of T and p equals the built `p_tail` on 8/8 runs.
- Deterministic across PYTHONHASHSEED values.

## Headline placebos (step 3, judged runs)
| Placebo | r5 | Held-out | Bar | Result |
|---|---|---|---|---|
| m1 per-class coin, 1h | **3.04% [2.4–3.9]** (2,040) | **3.96% [3.2–4.9]** (1,920); beats 1.51% | ≤5.0, CB ≤6.5, beats ≤2.5 | pass |
| m2 per-class coin, 8h | **9.48% [8.0–11.3]** | **9.11% [7.6–10.9]**; beats 5.12% | ≤7.5 | **FAIL** |
| m2 market-wide coin, 1h | 4.17% | 3.73% | ≤7.5 | pass |
| m2 market-wide coin, 4h off-grid (87-day) | **8.66% [7.2–10.4]** | 5.73% | ≤7.5 | **FAIL r5** |
| m2 market-wide coin, 4h nested (88-day) | 5.88% (408) | 6.25% (384) | exactness | consistent |
| m2 shifted edges | 7.19% [5.9–8.8] | 5.99% | ≤7.5 | pass (point estimate) |
| independent coin | 1.47% | 2.86% (384) | ≤2 | inconclusive |
| per-symbol persistent direction | **15.7% [12.5–19.5]** | **9.64%** | none | see P1-2 |

**Withheld share**
- 50.0% on r5 and 52.9% on held-out, essentially all `few_clusters`.
- Settings are judged up to about 1y h7, 2y h15, 5y h40–45 and 10y h90.

**Worst band**
- Measure-1 coin: 6.7% (r5) and 5.8% (held-out). Both ≤10%, so the band rule passes.
- 8h coin: up to 20.8% [13.1–31.6] at H5y h30–59.

## CHANCE_VERDICT_RATE
- Worst held-out figure across measures 1–2 (8h per-class coin):
  - **All verdicts:** 105/1,152 = **9.11% [7.6–10.9] → "about 1 run in 10"**.
  - **Beats only:** 59/1,152 = 5.12% [4.0–6.6] → "about 1 run in 19".
  - 52.9% of runs withheld.
- Scope must say **eight** holding periods, not four (`sonar/backtest.py:409-411`).
- The per-setting worst figure for that placebo is about 1 in 5 (H5y h30–59). If the Learn tab quotes a worst setting, it must quote that figure.

## Findings
- **P1-1. Measure 2 fails.**
  - The 8h coin reads 9.5% on r5 and 9.1% on held-out; the off-grid market-wide 4h coin reads 8.7% on r5.
  - Under the spec (:50), the block definition goes back to the owner: accept and disclose, or reopen (a new block then needs a new held-out set).
- **P1-2. Per-symbol persistent direction / drift is not controlled. Under A15 it reaches the Terminal's 60d line (10y).**
  - Per-symbol coin at 10y h20: 22.5% r5 / 12.5% held-out. At 10y h60: 31% r5 / 10% held-out.
  - Long-only reads "beats" at 10y h20 on both sets (Δ +7.7, p 0.0008 r5; Δ +4.6, p 0.034 held-out), and at 10y h60 on r5 (Δ +12.2, p 0.004).
  - Long-only reads "beats" on 34/51 judged r5 cells and 14/48 held-out cells.
  - Time-block flips cannot remove a direction fixed per instrument.
  - Recommendation: withhold or caveat the 10y Terminal line, and disclose "fixed per instrument" among the headline's residuals.
- **P2-1.** The tests' market-wide 4h coin is off-grid, not nested. Keep it as the stronger guard, relabel it, and tighten N or the bound: ≤34/300 passes a true 8.7% rate about 94% of the time.
- **P2-2.** `summarise` with a universe but without `timeouts` is still judged, and conditions on the chosen direction. Gate alone: 10/60 vs 1/60 rejections. Fail closed, or pin it with a test.
- **P2-3. Measure 5 not met.**
  - 2y h5 per-setup, Δ +2.81: 30/40 = 75% [60–86].
  - Clustered, Δ +2.98: 25/40.
  - 5y h20: 25/40 per-setup, 24/40 clustered.
  - Curve, per-setup: Δ +0.8/2.0/2.8/4.8 → 7/19/30/40.
  - Curve, clustered: Δ +0.5/1.7/3.0/5.0 → 1/11/25/40.
  - The gate costs 0–4 of 40 against today's rule. Suggested bar: ≥28/40 at Δ ≈ +3, or 80 seeds.
- **P2-4. Measure 10.**
  - Volatility INVERTED is confirmed on r5 at 1y h3, 1y h5 (p 0.0469, survives only because 2 components are measured) and 5y h5. It never grades on held-out.
  - Real momentum: 0 verdicts on either set. 4 held-out runs that today's code calls "below" now read not told apart from chance.
- **P3-1.** Fail-closed copy blames range or horizon instead of missing data.
- **P3-2.** The `attribute` exemption keys on horizon, not universe, and attribute does not check q ≥ 8 itself.
- **P3-3.** The V floor is fine and conservative.
- **P3-4.** The held-out set is survivor-biased with almost no crypto. Measure 1 held-out N is 1,920, just under the 2,000 target.

## Verdict per measure
| Measure | Verdict |
|---|---|
| 1 (step 3) | **Met** on both sets |
| 1 (steps 1, 10) | not measured |
| 2 | **Not met** |
| 3, 4 (n ≥ 480) | not measured (indicative n = 76: 2.6%) |
| 5 | **Not met**, borderline; curve published |
| 10 | measured |
| determinism | met |
