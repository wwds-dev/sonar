# Model validation: QA-11 / QA-13 (scoring.py, engine.py, backtest.py; uncommitted)

- Validator: `model-validator` (read-only), 2026-10-11. Saved by the orchestrator.
- Playbook `docs/playbooks/model-validator.md` is `status: baseline` (stale per AGENTS.md).
- Model tests pass (165: test_scoring, test_backtest, test_engine). Scratch scripts in the session scratchpad: `v1_analytic.py` (eigenfunction cross-check), `v2_mc.py` (continuous-BM Monte Carlo), `v3_bars.py` (synthetic walks through the repo's backtest), `v4_live.py` (live run, cached `bars.pkl`), `v5_placebo.py` (coin-flip / fixed-direction placebos), `v7_buy.py`, `v8_alt.py` (buyability repeated looks; live price mix `prices.json`).

**Verdict: fit with caveats, provided P1-1 is resolved before release.** QA-11: fit; false "measured" very well controlled; "LOST" not symmetric (P2-2). QA-13: maths exact; honest at shipped/default settings (1.5:1, h ≤ 60, 2y) on synthetic and live data; not honest at long Lab horizons on 2y (h ≥ 120), user-selectable today, where it now produces edge-like false positives (P1-1); off at 3:1, latent (P2-1).

## Reproduced
- Image series vs an independent eigenfunction derivation (Fourier-sine with drift, closed-form flux, gambler's ruin untimed part), k_t ∈ {1,1.5,2,3,5}, k_s ∈ {0.5,1,2}, T ∈ [0.1,10], m ∈ [−3,2.5]: max difference **6.9e-12**. Girsanov tilt e^{μ(L−x)}·Σ[G((2j+1)L−x) − G((2j+1)L+x)] algebraically correct. T=4 table exact: q = 0.5000 / 0.3946 / 0.3100 / 0.1643, timeouts 0.9 / 5.2 / 12.3 / 26.2%. q strictly increasing in m on [−5,5]; nothing negative at tiny T.
- Continuous-BM Monte Carlo (40k paths, Brownian-bridge corrected): within 0.1–1.4 MC se for (1.5:1,T=4,m=0), (3:1,T=4), (1.5:1,m=0.3), (2:1,T=1,m=−0.5), (1.5:1,T=0.4).
- Implied-drift inversion exact: 205 trials, 39 windows (min T=0.4), m ∈ {−0.7…0.6} recovered to 1e-6; drifted LONG-only walks m̂ = −0.007 / 0.149 / 0.300 for m = 0 / 0.15 / 0.30.
- Live Lab default (129 symbols, 2y, h=5, step 3, Yahoo today): hit 39.64%, predicted 39.37% (untimed 40%), Δ +0.27 pt (se 0.42); predicted moves −0.63 pt — SM5 holds.
- Live buyability (copy of state.json, aggressive): 117 hours at 2.5c, +6.5%/stake, se 13.4%, "within noise".

## Findings

**P1-1 — at long Lab horizons the new baseline turns a no-information market into "beats the prediction".** Horizon spinbox 1–250 (`ui/app.py:2348`), ranges 1y/2y/5y/10y. At h=250 on 2y every window is truncated (T < 2); the Gaussian short-T tail of q underestimates far-target hits on fat-tailed data. Coin-flip placebo on live bars (random direction, 4 seeds): h=20 −0.35 pt; h=60 +0.34; h=120 +1.15 (z +1.5); **h=250 +5.7 pt, z +4.1, 4/4 seeds significant at 2 se**. The real momentum run at h=250 reads "+8.9 points … a reason to look closer" — mostly the placebo bias; the old baseline read −7.5 ("worse than a coin flip"). The bias flipped from conservative to edge-suggestive, the direction the invariant forbids. By window (h=250 placebo): T < 0.5 **+20.4 pt** (n=648); 0.5 ≤ T < 2 +2.4 pt. At h=5 and 60, T < 0.5 also reads +12 to +17 pt but such trials are rare. ADR's residual statement does not cover this. Fix options (owner): compare only trials with a window floor (e.g. T ≥ 2, or full windows), counting the rest with the data-end exclusions; or suppress the verdict when truncated trials are a large share.

**P2-1 — at 3:1 on real data the baseline over-corrects** (latent; no R:R control). Coin placebo h=5: +1.64 pt, z +4.5, 6/6 seeds; full windows +1.81 pt (not truncation). Causes: fat tails plus convexity from assets drifting differently; averaging ±m gives +0.64 / +2.48 / +5.27 pt at m = 0.1/0.2/0.3 at 3:1; conditioning amplifies vs untimed (+15% vs +7.5% relative at m=0.2). At 1.5:1 and 2:1 the placebo stays within 0.32 pt at every h ≤ 60 — the ADR's ±0.6 holds there only. Before any R:R control ships, add a deterministic direction-placebo null (score both directions at every decision point). Live per-direction deltas (LONG +3.6, SHORT −3.7 pt at h=5): asset drift dominates; pre-existing confound.

**P2-2 — buyability "LOST" is anti-conservative; "measured" over-conservative.** Per-stake returns are right-skewed (10% of live buys ≤ 16.5c; cheapest 5.5c). EV exactly 0, live prices, one new hour per look:

| | false "LOST" | false "measured" |
|---|---|---|
| single look n=100 (3 se, nominal 0.135%) | **0.78%** | ~0.01% |
| looks n=100→300 | **2.9–3.5%** | 0.03% |
| looks n=100→1500 | **4.0%** | 0.13% |

D5's symmetric 3 se gives ~30:1 asymmetric error rates. With real costs EV < 0, so LOST is often true, but "more than three standard errors" implies ~0.1%. A bounded alternative tested on the same paths, Z = Σ(win − price)/√Σ p(1−p): 0.6% / 1.1% false up/down over looks 100–300 and 5–10× the power — but it tests win rate against price paid, not per-stake EV.

**P2-3 — the `timeout_share_expected` "monitor" is neither shown nor diagnostic.** Only at `backtest.py:440`. Live default: 12.9% realised vs 6.1% expected, yet the baseline is fine there (placebo +0.03 pt); at 3:1, where it is off, the gap is small (29.9 vs 27.1); perfectly specified synthetic walks show 6.3–8.3% vs 5.5% from sub-step monitoring. Restate the ADR wording.

**P3-1 — the k=2 robustness rule** is a coherent conservative screen ("measured" ⊂ "claims_up"; false acceptance 0.15% → 0.03% over 200 looks), not a test: dropping the top k biases the mean down by ~k·max/n while se shrinks less. On the live mix at n=300, EV +9.7%: costs ~0.9 t on average; ~50–60% of genuine 3-se readings become "carried" (architect measured 11% with a uniform-price generator). Power to say "measured": EV +6.5% → 0.3% by n=300; +9.7% → 0.85% (300), 22% (1500); +16% → 4.1% (300; 9.1% without the rule), 78.5% (1500). No plausible edge is certified in the first ~300 hours — fits the app's stance; the owner should know. The "carried" copy ("rests on a couple of hours") misdescribes broad edges built on cheap buys. Versus T1-1: at 2 se, looks 100→1500 trip 10.3% up + 24.6% LOST; 3 se fixes the up side.

**P3-2 — `expectancy_vs_null_r` is the right null given resolution** (E[(1+rr)(w−q) | resolved, T] = 0; = (1+rr)·Δ; live +0.0067 R = 2.5 × 0.27 pt). Under the null the timeouts' mark-to-market carries the offsetting P&L, so it is a rescaled hit-rate gap, not P&L. Shown without an error bar (live 0.6 se). Terminal line (`ui/app.py:3405`) still shows raw `expectancy_r` (−0.009 R live).

**P3-3 — multiple testing.** Confirmed only the active profile's gate gives the verdict (`readings[at_gate["gate"]]`). Residual: switching profiles reads up to 3 nested gates with different τ windows; rolling SCORELOG_MAX = 3000 means looks never stop. `model_vs_market` (outside this diff) still claims at 2 se hourly; the buyability verdict shows on hover over that line.

## Answers
- **Conditioning on resolution a valid null?** Yes under the model: E[TARGET | resolved, W_i] = q(W_i/h). Synthetic 160 walks h=5: Δ −0.02 ± 0.25 pt; true σ arithmetic: +0.31 (sub-step monitoring); estimated σ adds Jensen noise; vol clustering −0.47 pt with timeouts 18.7% vs 5.5%; ties-as-STOP ~0.2% at h=1, 0 at h ≥ 5; lognormal effects cancel to first order in a 50/50 direction mix. Where the model is wrong, conditioning magnifies the error: short windows, far targets, fat tails (P1-1, P2-1).
- **Unbiased with drift?** The estimator is consistent (q monotone in m; bisection exact). Drift unrelated to the signal biases any baseline through convexity, this one more.
