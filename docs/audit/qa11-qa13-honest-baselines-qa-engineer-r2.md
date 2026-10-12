# QA re-verification, round 2: QA-11 / QA-13 loop-1 changes (uncommitted)

- Verifier: `qa-engineer` (read-only), 2026-10-11. Saved by the orchestrator. Mutants in memory; scratch `/tmp/qa_v2/`; `state.json` sha1 unchanged.
- Playbook `docs/playbooks/qa-engineer.md` `status: baseline` (stale per AGENTS.md).

**Recommendation: code passes QA; do not release until Document lands (P2-1).** No P0/P1. Model-validator's round-1 P1-1 fixed for truncation (placebo on live bars). Fix the pre-existing flaky follow test (P2-2, test-only) before the next push.

## 1. Suites, twice each
| run | exit | result |
|---|---|---|
| native #1 | 0 | 1820 passed, 30 deselected, 44.1 s |
| offscreen #1 | 0 | 1820 passed, 30 deselected, 47.4 s |
| native #2 | 0 | 1820 passed, 30 deselected, 45.2 s |
| offscreen #2 | 0 | 1820 passed, 30 deselected, 70.6 s |

Pre-existing noise: 3 teardown tracebacks (`MainWindow already deleted`, `ui/app.py:3922 _confirm_hidden`); slow offscreen #2 also printed `watchdog step failed ('StubLive' object has no attribute '_stop')` from `sonar/server.py:321`.

**Follow flake — confirmed, test-side race, pre-existing (added 490ca57, 2026-10-10).** The `following` fixture (`tests/test_follow.py:152`) waits for `snapshot["following"]` and non-empty `positions["open"]`; `Live._mirror` (`sonar/core.py:1024-1044`) runs `_mirror_book` before `_mirror_config` (which sets `_holder_llm`), and `self.following` is set before `_mirror` runs — so for one loopback round trip `_holder_llm is None`, `llm_available()` returns "…has not said yet whether it can", and `"anthropic SDK not installed" in why` (`:465`) fails. Evidence: alone offscreen 1/25 fails; with `_mirror_config` delayed 100 ms (`/tmp/qa_v2/plug/slowcfg.py`) 10/10 fail (22 others pass); delay + wait for `_holder_llm` (`fixedwait.py`) 0/10. Fix (test only): wait for `live._holder_llm is not None`, or `_wait(lambda: "anthropic SDK not installed" in live.llm_available()[1])` as the sibling test at `:475` does. Reordering the mirror only moves the race.

## 2. Success measures
- **SM1 PASS** — robust rule removed, k 2→1, old `loo_ev > 0`, worst-instead-of-best, "carried" as "measured": each killed by 4–6 tests.
- **SM2 PASS** against the restated criterion (T11-4); spec text not amended (P3-3).
- **SM3 PASS** — changed-line coverage: backtest 58 st / 20 br, none missed; engine 48/16 none; ui/app 29/20 none; scoring 46/16, `163→168` missed (unreachable in practice).
- **SM4 PASS with the floor** — seeds 1000–1039, 1,500 bars, h=5, step 5; 80 short windows per ratio:

| R:R | n | timeouts | hit | predicted | delta | se | \|d\|/se | 3 se | vs untimed |
|---|---|---|---|---|---|---|---|---|---|
| 1:1 | 11,462 | 218 | 50.34 | 50.00 | +0.34 | 0.47 | 0.72 | 1.41 | +0.34 (0.7 se) |
| 1.5:1 | 10,880 | 800 | 40.15 | 39.45 | +0.69 | 0.50 | 1.38 | 1.50 | +0.15 |
| 2:1 | 10,003 | 1,677 | 31.30 | 30.99 | +0.31 | 0.53 | 0.58 | 1.59 | −2.03 (3.8 se) |
| 3:1 | 8,466 | 3,214 | 17.12 | 16.41 | +0.71 | 0.50 | 1.42 | 1.50 | −7.88 (15.8 se) |

  Seeds 2000–2039 pass (closest 3:1 at 2.45 se). Over 15 sets: mean residual −0.04 / +0.34 / +0.33 / +0.59 pt (sd ≈ 0.6); 3:1 fails 3 se once in 15.
- **SM5 PASS** (hit +0.05 pt from the floor, by owner decision). Live Lab default (fresh Yahoo, 129/129, 2y, h=5, step 3) — **for CONFIDENCE.md:587: 39.69% realised against 39.44% predicted for setups that resolved in time (40% with unlimited time); n = 18,975 across 129 instruments; 2,608 ran out of time (12.1%; 84 data-end); 360 too near the end of the data; Δ +0.25 pt, se 0.42; "no edge detected"; expectancy beyond a no-edge market +0.0064 R; raw −0.0076 R; implied drift +0.0043σ.** HEAD on the same bars: 39.64% vs 40.00%, n 19,121 (hit +0.05, predicted −0.56). Synthetic default (60 × 504, seeds 3000–3059): same movement; 180 short windows.
- **P1-1 placebo on live bars** (random direction, 4 seeds), floor on vs off: h=5 −0.31…+0.63 (same); h=60 −0.26…+0.36 vs +0.22…+0.59; h=120 −0.37…+0.40 (|z| ≤ 0.4) vs +0.75…+1.51; h=250 n = 0 (Lab says why) vs +5.2…+6.1 (z +3.8…+4.3). (2y only; see model-validator r2 for 5y/10y.)
- **SM6 PASS** — timeout and short-window counts in Lab and Terminal, including n = 0.
- **SM7 PASS on strings** — `test_no_backtest_verdict_promises_anything`; ux/tech-writer review not verified.

## 3. Mutation — 47 mutants, 43 killed, 4 survive
Earlier: M8 (`_mean_se` without NW) now killed by 2 tests; M8b, M8d killed; **M20 survives**. Floor mutants F1–F12 all killed (floor removed 5; `<`→`<=` 1; floor 1.0 2; floor 3.0 1; judged on full window 5; default keeps short resolved 3; short rows predicted 1; short timeouts to timeouts 2; short resolved into trials 2; n=0 drops short count 3; main summary drops it 1; `run()` doesn't pass short 3). **F13** (expected share including short windows) survives. Copy/UI mutants C1, C2, U1–U5, M24 killed. Other survivors: **M8c** (NW lags 1) and **M25** (`buyability()` verdict from rounded row values). Round-1 M1–M7, M9, M11–M19, M21–M23 still killed.

## 4. Earlier findings
- P2-1 docs — **not resolved** (Document): `CONFIDENCE.md:587`; `TODO.md:251`; `static/docs.html:620-622`, `:669-676`; TESTPLAN 7.5 / `static/testplan.html`; ADR 0001 `:40`, `:83` and spec `:404-405`, `:447-449`, `:574-576` still call `timeout_share_expected` an on-screen check; SM5 "unchanged" should allow +0.05 pt.
- P2-2 timeout on screen — resolved by owner decision (field only); still misstated in ADR/spec. Live: 12.1% vs 5.3%.
- P3-1 3:1 residual — still present (+0.59 pt; 1/15 fails 3 se).
- P3-2 NW test — resolved (M8c survives). P3-3 SM2 text — not amended. P3-4 Terminal line — resolved. P3-5 counts at n=0 — resolved. P3-6 verdict guard — resolved. CR P3-5 vacuous test — resolved. CR P3-1 — open (M25).

## 5. Defects
- P0/P1: none.
- **P2-1** docs/spec/ADR restatements (blocks release under D4); figure above.
- **P2-2** flaky `tests/test_follow.py::test_whether_a_read_can_run_is_the_holders_answer` (fix in §1).
- P3: M20/F13 (`timeout_share_expected` denominator untested; acceptable now it is non-diagnostic); M8c (NW lag length unpinned); M25; 3:1 residual +0.59 pt; "· 0 too near the end of the data" printed at h=1 on every run (`run_symbol` stops at `len−3`); positive verdict "beats the prediction by +3.1 points" redundant sign.
- Pre-existing, out of scope (cross-symbol se, separate spec): Lab default on driftless walks, 40 sets, delta sd ≈ 0.80 pt ≈ 1.3× reported se (0.62); 4/40 "significant" at 2 se vs nominal 5%.
