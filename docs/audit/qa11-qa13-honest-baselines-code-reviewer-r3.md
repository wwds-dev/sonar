# Code review, round 3: QA-11 / QA-13 honest baselines (loop-2 changes, uncommitted)

- Reviewer: `code-reviewer` (read-only), 2026-10-11. Saved by the orchestrator. Mutants on a scratchpad copy; scripts in the session scratchpad `cr3/` (`coin.py`/`coin.json`, `coin2.py`, `gate.py`, `news.py`, `lab.py`, `cl.py`, `tz2.py`, `mut/mutate.py`), bars from the model-validator's r2 pickles.
- Playbook `docs/playbooks/code-reviewer.md` `status: baseline` (stale per AGENTS.md).
- Loop 2 touched `sonar/backtest.py`, `ui/app.py`, `tests/test_backtest.py`, `tests/test_lab_tab.py`, `tests/test_follow.py`, count lines; `engine.py`, `scoring.py`, `calibration.py` unchanged since round 2.

**Verdict: the code implements the loop-2 decisions correctly. No P0, no code-level P1.** h=120 verdict / 121 none; n=100 / 99; 20 dates / 19; UTC dates; no production path calls `summarise` without a horizon; real 10y CL=F no longer crashes. **Not ready to release:** P1 (model-level, owner + model-validator) — coin-flip placebos still get significant verdicts at h ≤ 120 in single-class universes and near the data edge; P2-1 a withheld run still prints a news finding; P2-2 Lab momentum-bucket table always "+0.0 vs baseline" (pre-existing); P2-3 docs.

## Evidence
- Suites: offscreen 1,839 passed / 30 deselected (119 s, contended); native 1,839 (59 s); targeted (backtest, scoring, engine, lab_tab, follow) 237 passed. Known teardown traceback (`ui/app.py:3957`).
- Follow flake: `test_whether_a_read_can_run_is_the_holders_answer` alone offscreen ×15, 0 failures.
- Callers: `summarise` ← `run()` (`sonar/backtest.py:676`, passes `horizon_days`) ← `ui/worker.py:69`; nothing outside backtest reads `significant`; summaries never persisted.
- Mutants 12: killed — each half of the run_symbol price guard; `or`→`and` in the too-few gate; local-time date counting (`TZ=America/Los_Angeles`); `last_entry` from first date; Lab `within` ignoring `withheld`; Lab colour ignoring `withheld`; "(of N fetched)" removed; longest-horizon hint removed; Terminal n=0 reason removed. Survived — `range_for_horizon` `<=`→`<` (equivalent: 30 + 3h never equals 500); `run()` passing step 1 to `longest_comparable_horizon` (P3-7).
- Real data: Lab default (2y, h=5, step 3) n=18,974, 566 entry dates, verdict "within 0.8 points … no edge detected"; 2y h=150 withheld "horizon"; 2y h=250 "nothing to compare", longest comparable 243; CL=F 10y: 0 decisions at close ≤ 0 for h 1–250; 10y whole watchlist h=60 completes, 129 compared.

## Findings
**P1-1 — coin-flip placebos still get verdicts at h ≤ 120** (code matches the owner's decision; the decision falls short of the spec's goal). `sonar/backtest.py:99-106`, `:513-521`. Coin direction, 1.5:1, step 3, 6 seeds: of 186 placebo runs with a verdict, 51 "significant" (27% vs nominal ~5%).

| Range | Universe | h | Placebo reads | Seeds | Size / spread |
|---|---|---|---|---|---|
| 2y | Equity | 120 | "beats … a reason to look closer", +3.3 to +5.4 pt | 5/6 | n ≈ 1,930, 47 dates |
| 2y | Index | 120 | "beats" | 4/6 | |
| 2y | Commodity | 80/90/100/120 | "beats" | 4/3/3/2 of 6 | |
| 2y | Crypto | 80 | "did worse than a coin flip" | 5/6 | |
| 2y | Crypto | 90, 120 | "worse than a coin flip", −4.2 to −8.3 pt | 6/6 each | |
| 1y | Whole watchlist | 84 | "below" | 5/6 | n ≈ 590, 43 dates, span 111 days |
| 1y | Index | 72 | "below" | 5/6 | n ≈ 195, 40 dates, span 56 days, holds up to 288 bars |

Controls: whole watchlist 2y h=120 clean (0/6) — the validator's "wide margin at h ≤ 120" holds for the whole watchlist only; class universes clean below h=60. Gates catch the tiny cases (1y h=108–120 withheld `too_few`). Root cause: gates count setups and calendar dates, not independent periods — 20 distinct dates arrive within ~3–4 weeks across instruments' step grids/calendars; se ignores cross-sectional correlation (P1-3, separate spec); a single-class universe concentrates one common trend or crash. Options (owner via model-validator): (a) se clustered by entry date/week (pool by date, then Newey-West) — needed now; (b) entry span ≥ 4 × h calendar days (catches 1y, not 2y Crypto/Equity); (c) lower cap for single-class universes (e.g. 60); (d) both-directions placebo per run. Add a placebo regression test on a correlated synthetic class.

**P2-1 — a withheld run still states findings on the same Lab page.** `sonar/backtest.py:688-691` (attention buckets, news verdict, attribution computed regardless of `withheld`), `:695-735`, `ui/app.py:2781-2782`. Demo `cr3/news.py`: coin placebo, 5y, h=250, attention = pure noise → `withheld="horizon"`, yet "A news spike shifts the odds: below normal +3.3 pts (n=9012); normal +3.0 (n=7210); elevated +2.3 (n=4465); spike +2.8 (n=1755) — beyond two standard errors." Buckets inherit the drift-convexity bias; plain binomial se, no NW, no floor. On `too_few` runs `attribute()` (`:800`) can still print KEEP/INVERTED/DROP. Fix: when `withheld` is set, replace `news_verdict` with a withheld sentence and set every bucket's `significant` False; same gate (or "not judged") for attribution; tests at h=121 and n=99.

**P2-2 — Lab bucket tables show "?" and "+0.0 vs baseline" for every momentum bucket** (pre-existing at HEAD). `ui/app.py:2765-2779` reads `b["label"]`, `b["delta"]`; `_momentum_buckets` (`sonar/backtest.py:987-1000`) returns neither; attention buckets use `name`. Demo `cr3/lab.py`: 80% hit vs 40% predicted renders `? | 150 | 80.0% | +0.0`. `tests/test_lab_tab.py:207-215` passes on a hand-built shape `run()` never produces. Fix: emit `label` and `delta = hit_rate − predicted`; `b.get("label") or b.get("name")`; test on real `run()` output.

**P2-3 — docs not updated** (wider after loop 2). Stale: ADR 0001 `:31` ("its true, shorter T"), `:70` ("unchanged"), `:83` (timeout monitor); `CONFIDENCE.md:587`. Nothing documents the 120-day cap, the 100/20 gates, the Agresti–Coull floor, the "Instruments compared"/"Entry dates" rows, or the Terminal 5y range on "This year". Blocks release under D4; restate with n 18,974; 39.69% vs 39.44%.

**P3-1 — withheld copy overstates** (`sonar/backtest.py:597`, docstring `:36`): "even a coin-flip direction reads above the prediction" for every h > 120 — evidence is 5y h ≥ ~210 (h=200 +0.3 to +1.1, not significant); "Horizons up to 120 days get one" implies safety (see P1-1). Fix: "can read above the prediction (on five years of prices a coin-flip direction read 2–3 points above it at 210–250 days)".

**P3-2 — n=0 hint points to runs that can't get a verdict** (`ui/app.py:2674-2683`): quotes the longest series' horizon (crypto, 365 bars/yr) — 2y h=250 → "up to 243 days" (crypto-only, no verdict); 1y → "up to 120" (n ≈ 12, too few). Fix: min(that, `MAX_VERDICT_HORIZON`) and say longer horizons are shown without a verdict.

**P3-3 — Terminal still prints "· 0 timed out"** (`ui/app.py:3444-3445`, `is not None`). Fix: `if r.get("n_timeout")`.

**P3-4 — entry dates are UTC** (`sonar/backtest.py:513`): Yahoo stamps forex bars 23:00 UTC previous day during BST (301 of ~519 bars per pair) and ^AXJO during AEDT — a forex Monday entry dates Sunday; `first_entry` can read a day early; Equity+Forex gains up to ~1 extra "date"/week. Not material to gates. Fix: label "(UTC)" or use exchange-local date via `gmtoffset`.

**P3-5 — Terminal shows only the compared count** (no class mix or entry span; matters most on "This year", always withheld). Fix: append the span or record as Lab-only by design.

**P3-6 — sibling of the CL=F crash** (`sonar/assets.py:551-553`): `_daily_vol` guards only `closes[i-1] > 0`; it is the live scan's fallback when `volatility.forecast` is falsy (`:430`) → `ValueError` on a non-positive close. `volatility.log_returns` already guards both ends. Fix: guard both ends.

**P3-7 — test gap**: the step-1 `longest_comparable_horizon` mutant survives; `test_a_run_reports_the_longest_horizon_its_data_can_compare` uses 300 bars at step 3 where step doesn't change the answer. Fix: pick a length where it does.

## Copy
Withheld verdicts avoid edge/profit/certainty (guarded by `test_withheld_verdicts_promise_nothing_either`); withheld runs render grey without the "no edge" line on both surfaces; "beats … by 3.1 points" single sign; withheld strings not split via `words.pick` (plain enough for both). Remaining: P3-1 overstatement, P2-1 news verdict.

## Round-2 findings
| Source | # | Status |
|---|---|---|
| CR | P2-1 Terminal "This year" empty | Resolved (5y range, status, tooltip, n=0 reason); always withheld now |
| CR | P2-2 docs | Unresolved (P2-3) |
| CR | P3-1 n=0 headline | Resolved ("nothing to compare" + longest horizon; see P3-2) |
| CR | P3-2 always-zero clause | Resolved for "too near the end"; "· 0 timed out" remains (P3-3) |
| CR | P3-3 data-end vs short | Resolved (run()-level equality test); ADR definition pending |
| MV | P1-A long-horizon placebo | Resolved as decided; new evidence at h ≤ 120: P1-1 |
| MV | P1-B tiny samples, se=0 | Resolved as decided; correlated near-edge samples: P1-1 |
| MV | P2-A instrument count | Resolved |
| MV | P2-B negative-side residual | Unresolved (docs); P1-1 adds evidence |
| MV | P2-C entry span | Resolved in Lab; not Terminal (P3-5) |
| MV | P2-D CL=F crash | Resolved (real 10y); sibling P3-6 |
| MV | P3 docs | Unresolved |
| QA | P2-1 docs | Unresolved |
| QA | P2-2 follow flake | Resolved (15/15) |
| QA | P3 h=1 clause / double sign | Resolved |
| QA | P3 M20/F13/M8c/M25 | Not re-checked (code unchanged) |
