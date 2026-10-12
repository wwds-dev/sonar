# QA verification: QA-11 (buyability robustness, k = 2, 3 se both ways) and QA-13 (time-aware backtest baseline)

- Verifier: `qa-engineer` (read-only), 2026-10-11. Saved by the orchestrator.
- Playbook `docs/playbooks/qa-engineer.md` is `status: baseline` (stale per AGENTS.md).
- Live `state.json` untouched (sha1 `2f45af63…` before and after); mutants in memory only; scratch under `/tmp/qa_v/`.

**Recommendation: code passes QA; do not release yet.** No P0/P1. Before release: the doc restatements (P2-1) and an owner/architect decision on the timeout check on screen (P2-2).

## 1. Suite, both modes, twice
| run | exit | result |
|---|---|---|
| native #1 | 0 | 1811 passed, 30 deselected, 44.1 s |
| offscreen #1 | 0 | 1811 passed, 30 deselected, 41.9 s |
| native #2 | 0 | 1811 passed, 30 deselected, 45.5 s |
| offscreen #2 | 0 | 1811 passed, 30 deselected, 41.2 s |

Every run prints 3 teardown tracebacks (`libshiboken … MainWindow already deleted`, `ui/app.py:3888 _confirm_hidden`) — pre-existing on HEAD, not in this diff.

## 2. Success measures
- **SM1 — the robustness rule itself refuses a result resting on its best hours: PASS.** M1 (no `robust_up`) fails 4 tests; k 2→1 killed by the two-hour test; old `loo_ev > 0` killed.
- **SM2 — a broad result still passes: PASS against the architect's restated criterion** (clears 3 se with and without its 2 best hours; T11-4 78W/42L reads "measured"). The spec's literal wording ("no hour over ~5% of gross profit ⇒ positive") is false by design: seed 1000, 97 of 913 such logs refused; seed 2024, 79 of 901 (P3-3).
- **SM3 — no unreachable branch: PASS.** Seed 1000: 1,101 measured / 182 carried (94 refused only at k=2); seed 2024: 1,112 / 164. Changed-line branch coverage: engine 48 st/16 br 0 missed; backtest 49/16 0 missed; ui 9/6 0 missed; scoring 46 st, 1 branch missed (`scoring.py:163`, the series loop never running out — unreachable in practice).
- **SM4 — driftless baseline at every ratio: PASS.** Seeds 1000–1039, 1,500 bars, h=5, step 5:

| R:R | n | hit | predicted | delta | se | \|d\|/se | 3 se | old untimed delta |
|---|---|---|---|---|---|---|---|---|
| 1:1 | 11,525 | 50.39% | 50.00% | +0.39 | 0.47 | 0.83 | 1.41 | +0.39 (0.8 se) |
| 1.5:1 | 10,924 | 40.15% | 39.43% | +0.72 | 0.50 | 1.44 | 1.50 | +0.15 |
| 2:1 | 10,037 | 31.27% | 30.95% | +0.33 | 0.53 | 0.62 | 1.59 | −2.06 (3.9 se) |
| 3:1 | 8,495 | 17.09% | 16.37% | +0.73 | 0.50 | 1.46 | 1.50 | −7.91 (15.8 se) |

  Seeds 2000–2039 also pass (3:1 closest, 2.47 se). Over 15 seed sets of 40 walks the mean residual is −0.03 / +0.19 / +0.17 / +0.47 pt (sd ≈ 0.5); one set in 15 fails 3 se at 3:1 (P3-1). M11 (untimed predicted) fails 2:1 and 3:1.
- **SM5 — shipped numbers do not move materially: PASS on numbers; restatement NOT VERIFIED (not done).** Live Yahoo, Lab default (129 symbols, 2y, h=5, step 3): hit 39.64% unchanged (n = 19,119); predicted 40.00% → 39.37% (−0.63 pt); old delta −0.36 pt, new +0.27 pt, se 0.42 (not significant). Synthetic default: −0.63 pt, identical hit. CONFIDENCE.md:587 should read about "39.64% against 39.37% (40% with unlimited time)".
- **SM6 — timeouts visible: PASS.** Summary carries `n_timeout`, `n_timeout_data_end`, `timeout_share`, `timeout_share_expected`; Lab shows "N ran out of time (x%)" (M24 caught by `test_timeouts_and_the_untimed_baseline_are_on_screen`); Terminal appends "· N timed out".
- **SM7 — copy: PASS on the strings read**; ux-designer/tech-writer review vs `ui/words.py` NOT VERIFIED. Buyability verdicts free of edge/profit/whale/leave-one-out/certainty (T11-8 guard). No automated guard on `backtest._verdict` (P3-6).

## 3. Mutation check — 23 mutants, 21 killed, 2 survived
Killed — QA-11: no robust rule; k 2→1; rest vs full-sample se (only by `test_the_rest_is_judged_by_its_own_error_bar`); LOST at 2 se; positive at 2 se; old LOO > 0; dropping worst instead of best; "carried" reported as "measured". QA-13: untimed predicted; T=4 everywhere; wrong timeout_share denominator; expectancy at shipped rr; implied drift from untimed maths; minus image term dropped; series cut to one term; underflow guard 0.5; data-end count includes every timeout; Girsanov sign flipped; null expectancy vs untimed; `run()` drops timeouts; Lab hides timeouts.

Survived — **M8** `_mean_se` without Newey-West (`sonar/engine.py` ~111): no test pins the HAC widening (P3-2). **M20** `timeout_share_expected` over resolved trials only: near-equivalent (depends only on windows).

## 4. Live buyability on a copy
Gate 2.5c; scorelog 226; priced 212; unpriced 1; out of window 10; bad book 3; `z_claim` 3.0. Verdict: "+6.5% per stake over 117 hours at the 2.5c gate, within noise of zero (three standard errors). Nothing buyable shown either way." (t ≈ 0.48)

| gate | n | ev | se | robust_ev (n−2) | robust_se | loo_ev | top_share |
|---|---|---|---|---|---|---|---|
| 1c | 130 | −0.0014 | 0.1239 | −0.1041 | 0.1113 | −0.0610 | 0.115 |
| 2c | 123 | +0.0370 | 0.1296 | −0.0710 | 0.1187 | −0.0258 | 0.116 |
| **2.5c** | **117** | **+0.0647** | **0.1338** | **−0.0485** | **0.1316** | −0.0011 | 0.119 |
| 4c | 100 | +0.1399 | 0.1528 | +0.0086 | 0.1545 | +0.0636 | 0.126 |
| 7c | 75 | +0.2316 | 0.1886 | +0.0578 | 0.1461 | +0.1307 | 0.150 |
| 10c | 49 | +0.0037 | 0.2124 | −0.2059 | 0.1605 | −0.1098 | 0.208 |

The verdict is past 100 hours and speaks; follow-mode users see the new copy only after the agent runs the new build.

## 5. Lab render with old-shaped summaries: PASS
Pre-QA-13 dict, no `symbols`, `n_timeout` without `timeout_share`, new fields None, n = 0 in both shapes — none raise; old shape falls back to "Expectancy" with the raw figure.

## 6. Defects
- **P2-1 — docs still state the old checks** (blocks release under D4): `TESTPLAN.md:212` / `static/testplan.html:245` (7.5: "Predicted reads 40%", the 14% vs 25% bias, the 1:1/1.5:1 pin); `TODO.md:251` (leave-one-out, "one whale"); `CONFIDENCE.md:587` ("39.58% against a 39.99% prediction"); `static/docs.html:669-676` (no 3 se / two-best-hours wording).
- **P2-2 — the timeout check ADR 0001 relies on is not on screen, and on live data it is out by 2×.** Lab (`ui/app.py:2685-2688`) shows only the realised share. Live Lab default: realised 12.9% (11.5% excluding 300 data-end timeouts) vs 6.2% expected. An effective window of ~3 horizons explains that rate and gives q ≈ 38.7% instead of 39.4% (−0.7 pt, comparable to the 0.84-pt 2-se bar). Verdict unchanged today. Owner/architect: show the expected share and state the gap in CONFIDENCE.md (architect's stated next step for this case: a bootstrap baseline).
- **P3-1** small positive residual at 3:1 on driftless walks (mean +0.47 pt over 15 sets, 1 in 15 fails 3 se); shipped test deterministic; within ADR's ±0.6 pt.
- **P3-2** no test pins the Newey-West widening in buyability (M8).
- **P3-3** SM2 text in the spec not amended to the restated criterion.
- **P3-4** Terminal backtest line (`ui/app.py:3404`) shows raw `expectancy_r` (−0.009 R on the live run) and "predicted" without "resolved in time".
- **P3-5** when every setup times out, the timeout count is dropped (`ui/app.py:2674`, `_backtest_done` return early on n = 0).
- **P3-6** `backtest._verdict` has no banned-word guard.
- Housekeeping: README.md's diff also carries another session's AGENTS.md/CLAUDE.md lines — stage by name.

## Release recommendation
Verified in code. Before Release (D4, together): tech-writer completes P2-1 with the re-measured figure (39.64% realised vs 39.37% predicted, 40% untimed, n = 19,119, 2,824 timed out); owner/architect decides P2-2; optionally tests for P3-2 and P3-6; after release restart the agent.
