# Spec: QA-11 / QA-13 — honest baselines for the buyability verdict and the backtest

- Status: approved for Build (2026-10-11)
- Owner approval: 2026-10-11 — design and ADR 0001 approved; D1′ k = 2; D3 3 se both ways; D5 symmetric; D6 ADR accepted; D7 the Lab shows `expectancy_vs_null_r`; D4 QA-11 and QA-13 ship together after review and QA (no separate early release).
- Owner decisions after Review/Verify (2026-10-11): **P1-1** (long-horizon false positive from data-truncated windows, `docs/audit/qa11-qa13-honest-baselines-model-validator.md`) — window floor: only trials with at least 2 horizons of data after entry are compared; shorter data-end windows are excluded and counted with the data-end exclusions. **P2-2** (buyability LOST anti-conservative, ~3–4% false alarms under repeated looks) — no code change; record the measured rate in docs. **Timeout monitor** — restate ADR 0001 and this spec: `timeout_share_expected` is an output field, not an on-screen monitor and not diagnostic; the coin-flip/direction placebo is the real check.
- Owner decisions after round-2 validation (2026-10-11, `docs/audit/qa11-qa13-honest-baselines-model-validator-r2.md`): **P1-A** — no backtest verdict above a 120-day horizon; show the numbers and say why (an asset's own trend dominates there). **P1-B** — no verdict unless at least 100 compared trials from at least 20 distinct entry dates, and the error bar has a floor so it can never read 0; below that, show the numbers and say there are too few to judge. Also in this loop (orchestrator's recommendation, owner deferred): show the instruments actually compared (by class) and the compared entry-date span; guard the volatility calculation against a zero or negative close (10y crash on CL=F); the Terminal backtest picks a range long enough for the profile's horizon and says why when nothing is compared.
- Owner decisions after round-3 review/QA/validation (2026-10-11, `docs/audit/qa11-qa13-honest-baselines-*-r3.md`), loop 3 of 3: **P1-C** — no backtest verdict on a single-asset-class universe (numbers shown; a single class shares one trend, so it cannot be judged); verdicts only on the whole watchlist. **P1-B remainder** — no verdict unless the compared entries span at least 5 horizons. Also in loop 3: no attribution KEEP/DROP/INVERTED and no news-spike finding on a run that gets no verdict; fix the Lab momentum-bucket table ('?' labels, '+0.0' gaps; pre-existing); fix the follow-mode stale-mirror race in `sonar/core.py` (protocol/knob flip-back; pre-existing) with a generation guard. Not in loop 3 (owner left out): the small P3 copy fixes.
- Owner decision after round-4 validation (2026-10-12, `docs/audit/qa11-qa13-honest-baselines-model-validator-r4.md`), escalated after three loops — **loop 4 authorised**: the backtest error bar becomes se = max(current se, Driscoll–Kraay se clustered by entry calendar date across instruments, Bartlett kernel over L = ceil(avg_bars_held·365/252) days) for the headline verdict (P1-D); the news/attention buckets use the same clustered error bar, are compared against the run's own Δ rather than the prediction, with Benjamini–Hochberg across the buckets (P1-E); a clustered-coin placebo (one random direction per class and ~h-day block) becomes the acceptance test. Also: the blend-IC 'ranks backwards' sentence is shown only on judged runs and only when significant (code review r4 P2-1).
- Owner decisions after round-5 review/QA/validation (2026-10-12, `docs/audit/qa11-qa13-honest-baselines-*-r5.md`) — **loop 5 authorised**: (1) attribution (component IC and quintile-spread tests, KEEP/DROP/INVERTED, and the blend 'ranks backwards' t) uses the same date-clustered Driscoll–Kraay error bar as the headline (validator r5 P1-A, QA r5 P2-1); (2) verdict copy drops "two standard errors": 'beats' says Δ is outside its error bar, the bar is not a guarantee, and a direction picked at random for a whole asset class landed outside it about 1 run in 10 in our tests; 'below' no longer says "worse than a coin flip"; the Lab line says "error bar ±x; setups entered on the same day counted together" (validator r5 strings); (3) attention buckets are compared against the gap of the setups that carry attention, not the whole run (code review r5 P2-1); (4) small fixes: the Lab attention table shows the figure the verdict uses (`vs_run`), the null attention copy says "no effect detected, which is not the same as none", "even a coin-flip direction can read above", and the Lab colour follows `significant`/`withheld`, not rounded fields. The clustered-coin ≤ 5% target stays open (needs a sign-randomisation test); the acceptance test is a regression guard.
- Orchestrator polish after round 6 (2026-10-12, no P0/P1; owner's standing instruction to continue; copy follows the owner's round-5 hedging decision; reviewable at the release gate): INVERTED no longer gives an instruction — "…this component would push the wrong instruments up the board. Worth testing with its sign flipped, or dropped. From one replay of past prices: a reason to look closer, not a finding." KEEP gains "— from one replay of past prices" (validator r6 P2-A); the Lab attention column is headed "vs setups with attention" (code review r6 P3-1); the null attention copy and the component IC lag are pinned by tests (QA r6 E4, T2); `backtest.py:894` docstring rewrapped. Recorded for later, not built: the attribution grades are not calibrated 5% tests (QA r6 P2-1; validator r6: 5–7% on clustered placebos); DROP has no error bar (validator r6 P3).
- Priority: QA-11 **P1** (live verdict speaks within days); QA-13 **P2** (latent at the shipped ratio)
- Source: QA pass 2026-10-10; `docs/audit/model-validation.md` P1-3; `docs/audit/code-review.md:129`;
  `TESTPLAN.md` 7.5; `tests/test_backtest.py:171-194`; `tests/test_engine.py:974-985`.

## Problem

Both checks promise a reader a safeguard that is not there. For an app whose product is
"no edge is claimed", a safeguard that only appears to work is a defect.

**QA-11: the one-whale gate cannot fire.** `Engine.buyability()` (`sonar/engine.py:608-736`)
prices "buy the model's side at the touch" per hour. Once 100 qualifying hours exist at the
active profile's gate, it gives a verdict. The docstring (`:632-635`) and the TODO entry
(`TODO.md:246-253`) say a positive verdict "must survive leave-one-out", so that one huge
longshot win cannot carry it. The positive branch (`:714`) requires `ev > 2*se` **and**
`loo_ev > 0`. The second condition is implied by the first. If one return B carries the sum and
the rest sum to ≤ 0, the mean is ≤ B/n, and the standard error is already ≳ B/n, so the mean
cannot clear 2 se. Of 3,000 random scorelogs, none cleared 2 se with `loo_ev ≤ 0`. So:
- the "One whale is a story, not an edge" branch (`:721-725`) is dead code;
- `test_one_whale_cannot_carry_a_positive_verdict` passes because of the 2 se gate, not because
  of leave-one-out, so it would still pass if LOO were deleted;
- the positive copy says "surviving leave-one-out", a check that adds nothing.

The verdict is close to speaking. The live log had about 95 of 100 qualifying hours at the
aggressive 2.5c gate. It is shown on hover over the Terminal's model-vs-market line
(`ui/app.py:3533-3539`) and in the portfolio snapshot (`sonar/core.py:1250`).

The verdict has a second honesty gap. It is recomputed every hour from n = 100 onward at
**2 se**. The T1-1 validation found that a gate checked again after every new result trips on a
no-edge book 23–37% of the time at a nominal 95%. T1-1 answered that by moving claims to
`Z_CLAIM = 3.0`. This verdict did not get that change.

**QA-13: the backtest's baseline is biased at any ratio but the shipped one.**
`backtest.run_symbol` (`sonar/backtest.py:265-268`) drops TIMEOUT trials. These are trials that
touched neither barrier within `horizon_days × MAX_HOLD_MULTIPLE` bars, or before the data ran
out (`:226`). It then compares the resolved hit rate with `plan.p_profit = k_s/(k_t+k_s)`, which
is the probability with no time limit. The dropped trials are mostly ones a far target had not
reached yet. On a driftless walk:

| R:R | resolved hit rate | baseline used | reads as |
|---|---|---|---|
| 1:1 | ≈ 50% | 50% | fine |
| 1.5:1 (shipped) | 39.9% | 40% | fine |
| 2:1 | 30.7% | 33.3% | −2.6 pts, "harmful" at large n |
| 3:1 | 14.4% | 25% | −10.6 pts, "actively harmful" |

At wider ratios, a market with nothing in it reads as an inverted signal. The verdict copy
(`:347-349`) would tell a retail user the lean "would have lost money faster than a coin flip".
Today nothing runs a ratio other than 1.5:1: there is no R:R control in the Lab, as TESTPLAN 7.5
and the test docstring now say. But `timing()` (`:706`) and the attention buckets (`:421`)
inherit the same `predicted`, attribution ranks only resolved trials, and the report never says
how many trials were dropped. Separately, `summarise` computes `implied_edge_sigma` and
`expectancy_r` from the shipped constants (`:293, :321`), not from the trial's own R:R.

## User and goal

**User:** retail investors with no finance training. They read the Lab's backtest readouts and
the hourly model's "at the touch" verdict, and they take a sentence like "beyond two standard
errors and surviving leave-one-out" at face value.

**Goal:** every robustness check the copy names actually runs, and every baseline is the one a
market with nothing in it would produce.

## Success measures

Each is a test or a number. `qa-engineer` mutation-checks each one.

1. **The whale is refused by the robustness rule itself.** A constructed scorelog clears 2 se (or
   the D3 threshold) on the mean, but it is carried by one hour, and by two hours. The verdict is
   the "one whale" / "carried by a few hours" verdict, not the positive one. The test fails if the
   robustness rule is deleted while the significance gate stays (a mutant the current test
   survives).
2. **A broad edge still passes.** A constructed log in which wins are spread over many hours at
   ordinary prices (no hour holds more than about 5% of gross profit) and the mean clears the
   threshold gets the positive verdict.
3. **No unreachable branch.** A randomised test (≥ 3,000 logs) finds both outcomes of the
   robustness rule among logs that clear the significance gate. Coverage shows every verdict
   branch executed.
4. **Driftless baseline holds at every ratio.** On driftless walks at 1:1, 1.5:1, 2:1 and 3:1,
   `summarise(...)["delta"]` is within 3 se of 0. The sample must be large enough that 3 se ≤ 2
   points, so the test can see the 2:1 bias it is meant to catch. With today's code the test
   fails at 2:1 and 3:1.
5. **The shipped numbers do not move materially.** At 1.5:1 on the Lab's default run, the
   realised hit rate is unchanged and `predicted` moves by less than 1 point. The README / docs
   figure ("39.58% vs 39.99%") is re-measured and restated.
6. **Timeouts are visible.** The backtest summary reports `n_timeout` (and its share), and the
   Lab shows it next to n.
7. **Copy.** No verdict string in `buyability()` or `backtest._verdict` implies edge, profit or
   certainty. A positive result is described as a measurement with its caveats, not as a
   finding. `ux-designer` and `tech-writer` review the strings against `ui/words.py`.

## Scope

- `Engine.buyability()`: a robustness rule that can fail (D1), the significance threshold (D3),
  verdict copy, docstring, and the TODO entry corrected.
- `backtest.run_symbol` / `summarise` / `_attention_buckets` / `timing`: the timeout policy and
  baseline (D2), `n_timeout`, and `implied_edge` / `expectancy_r` from the trial's own R:R.
- Tests above; TESTPLAN 7.5, README and `static/docs.html` statements that cite either check.

## Non-goals

- An R:R control in the Lab. This makes one possible later; it does not add one.
- Changing the 100-hour threshold (`SCORE_MIN_SAMPLE`) or the gate table.
- Changing what the engine trades, its edge gates, sizing or entry window.
- Changing the P(profit) shown on rows. It stays `1/(1+R:R)` (T1-1 decision). Only the backtest's
  *comparison* baseline is in scope.
- `replay.py`'s own TIMEOUT handling (`:92`) and the cross-symbol SE issue from P1-3. These are
  separate items; see open questions.

## Owner decisions

**D1 — Which robustness rule replaces the unreachable LOO?** Options:
(a) *The mean without its best hour must itself clear the significance threshold, with the
standard error recomputed on the remaining hours.* This can be reached: with one whale and
losers, the remainder fails. With two whales and losers, the remainder is a one-whale log and
also fails.
(b) Leave-top-k-out at the threshold, with k = max(1, ⌈1% of n⌉).
(c) A cap on `top_share` (for example, refuse if the best hour is over 25% of gross profit).
(d) Winsorise each per-stake return (cap at the payoff of a 20c buy) and test the capped mean.
(e) Smallest version: drop the LOO claim and the dead branch, and keep `top_share` as a
disclosure only.
**Recommend (a).** It is one sentence of copy ("the result still holds without its single best
hour"), it is what the current copy already promises, and it covers two whales. Show
`top_share` as a disclosure, not as a gate.

**D2 — What happens to TIMEOUT trials?** Options:
(a) Count them as losses. That is wrong on its own: the 3:1 bias gets worse unless the baseline
also becomes P(target first *within the window*).
(b) Keep excluding them, and compare against a **time-aware baseline per trial**: P(target first |
resolved within this trial's actual window), driftless. The window includes end-of-data
truncation.
(c) Report them separately as a third outcome against a predicted three-way split.
(d) Mark timeouts to market at the window end, which changes the metric to expectancy.
**Recommend (b) plus `n_timeout` disclosure.** The realised hit rate does not change, so the
shipped numbers stay put, and `timing`, attention buckets and attribution all inherit the honest
baseline. Whether that baseline is computed analytically or by simulation, and whether it also
absorbs the daily-bar / tie-as-STOP bias (P1-3: −0.3 to −0.9 pts), is for `architect` to decide.

**D3 — The significance threshold for a positive buyability claim.** It stays at 2 se, or moves
to `Z_CLAIM = 3.0` like calibration. **Recommend 3 se for the positive and negative claims.**
The verdict is checked again every hour, and T1-1 showed that 2 se on a repeatedly checked gate
is not 95%. The table can keep showing se.

**D4 — Does QA-11 ship before the 100th hour?** **Recommend yes, as its own small change ahead
of QA-13**, so the first verdict a user sees is an honest one. QA-13 can follow.

**D5 — The "LOST … the market being right" negative verdict** keeps the same threshold as the
positive one (D3). **Recommend symmetric.**

## Risks and open questions

- Under D1(a), a genuine edge built on cheap longshots can be refused. That error is acceptable:
  it says "not demonstrated", never "no edge".
- D3 at 3 se makes a positive verdict rarer. Given the app's stance, that is the intended
  direction.
- The time-aware baseline depends on the backtest's own σ estimate, so a mis-estimated σ moves
  the baseline. The driftless test with known σ is the check.
- Open: does `replay.py`'s TIMEOUT path need the same treatment? Should P1-3's cross-symbol SE
  and HAC concerns be handled here or in a separate spec? (Recommend separate.)

## Design  *(ux-designer)*

*Wording note from `architect`, 2026-10-11. This is a draft for `ux-designer` and `tech-writer` to
finalise against `ui/words.py`. There is no layout work. Tests match on the marked substrings, so
those must survive any rewording.*

**Buyability verdicts** (`sonar/engine.py`, one vocabulary, shown on hover at `ui/app.py:3533-3539`).
Placeholders: `{ev}` = `ev:+.1%`, `{n}` hours, `{gate}` such as `4c`, `{best}` = "best hour" or
"two best hours" (from `robust_drop`), `{rest}` = `robust_ev:+.1%`. No string may contain "edge",
"whale", "profit" or "leave-one-out".

| branch | copy (test marker in **bold**) |
|---|---|
| too few | unchanged: "`{n} of 100 qualifying hours at the {gate} gate` — **too few** to price…" |
| measured | "Buying the model's side at the touch measured {ev} per stake over {n} hours at the {gate} gate. That is more than **three standard errors** above zero, and it still is **without its {best}**. It is one past stretch of one market, before size limits: a measurement to watch, not a forecast." |
| carried | "{ev} per stake over {n} hours at the {gate} gate, but **without its {best}** it is {rest}, inside three standard errors. A result that rests on a couple of hours is **not demonstrated**." |
| lost | "Buying the model's side at the touch **LOST** {ev} per stake over {n} hours at the {gate} gate, more than three standard errors below zero. On these hours the market's price was the better one." |
| noise | "{ev} per stake over {n} hours at the {gate} gate, **within noise** of zero (three standard errors). Nothing buyable shown either way." |

The "carried" copy says "a couple of hours", not "one whale". The hours that carry a near-threshold
result are ordinary wins; see *Architecture → Where the architect disagrees*, point 2.

**Backtest** (`ui/app.py:2677-2690` Lab table, `:3380-3386` Terminal line, `sonar/backtest.py:338-349`):
- "Resolved setups": `"{n:,} across {symbols} instruments · {n_timeout:,} ran out of time ({timeout_share:.1%})"`.
  This meets success measure 6.
- "Predicted by the barrier maths" becomes "Predicted, for setups that resolved in time":
  `"{predicted:.2%} ({baseline_untimed:.0%} with unlimited time)"`. The 1/(1+R:R) identity stays
  on screen.
- "Expectancy": show `expectancy_vs_null_r`, labelled plain "Expectancy beyond a no-edge market" /
  expert "Excess expectancy". The raw `expectancy_r` reads negative on a market with nothing in it
  (owner decision D7 below).
- Terminal line: append `· {n_timeout} timed out`.
- `_verdict`, positive *(amended 2026-10-12, owner's round-5 decision; shipped string,
  `sonar/backtest.py` `_verdict`)*: "Hit rate beats the prediction by {d} points, outside its error
  bar (±{2se}). That bar is not a guarantee: in our tests on these prices, a direction picked at
  random for a whole asset class landed outside it about 1 run in 10. Before costs, from one replay
  of past prices: a reason to look closer, not a finding." This replaces "Momentum is doing
  something here". ~~"…more than two standard errors ({se})…"~~ was the round-1 draft.
- `_verdict`, negative *(amended 2026-10-12, as above)*: "Hit rate is {d} points below the
  prediction, outside its error bar (±{2se}). A direction picked at random can land this far below
  too, so this does not show the lean is worse than a coin flip. Before costs, from one replay of
  past prices." This replaces "would have lost money faster than a coin flip". ~~"…beyond two
  standard errors. Taking the lean at face value did worse than a coin flip…"~~ was the round-1
  draft.
- Lab "Difference" row *(amended 2026-10-12)*: `"{delta:+.2f} pts  (error bar ±{2se:.2f}; setups
  entered on the same day counted together)"`, replacing "(±{x} at 2 s.e.)".
- Attribution *(amended 2026-10-12, orchestrator polish after round 6)*: INVERTED ends "…this
  component would push the wrong instruments up the board. Worth testing with its sign flipped, or
  dropped. From one replay of past prices: a reason to look closer, not a finding." (was "Flip its
  sign or drop it."); KEEP gains "— from one replay of past prices". The Lab attention column is
  headed "vs setups with attention" and shows `vs_run`.
- Withheld runs, null attention *(amended 2026-10-12)*: "even a coin-flip direction can read above
  the prediction"; the null attention copy ends "no effect of a news spike was detected, which is
  not the same as none."

## Architecture  *(architect)*

*`architect`, 2026-10-11. The playbook `docs/playbooks/architect.md` is `status: baseline` and has
not yet been checked by a radar run, so it is stale by AGENTS.md's definition. Every number
below was measured with `.venv/bin/python` against the repo's own code. The scripts live in the
session scratchpad and are not committed. Anything not measured says "not verified".*

### Approach in one paragraph

QA-11 replaces `loo_ev > 0` with a significance re-test on the log without its best `k` hours,
and raises both claims to `calibration.Z_CLAIM` = 3. The rule can fail, and the constructed logs
below show it failing. QA-13 changes the backtest's per-trial `predicted` to
P(target first | resolved within this trial's own window) for a driftless Brownian motion. This
probability comes from a short closed-form image series, cached by window. Timeouts stay out of
n but are counted and shown, and the drift and expectancy figures use each trial's own k's. No
persisted state changes. The meaning of `predicted` does change, which is recorded in
`docs/adr/0001-backtest-baseline-conditional-on-resolution.md`.

### Where the architect disagrees with the Define section

1. **D1(a) as written is leave-*one*-out, and it does not cover "carried by two hours".** Take
   the log built in T11-2: t = 3.28 on the full sample, 3.10 without its best hour, and 2.90
   without its best two. D1(a) gives it the positive verdict. Success measure 1 asks for
   exactly this log to be refused. **Recommend k = 2: "still holds without its two best
   hours".** If the owner keeps k = 1, drop the two-hour clause from success measure 1.
2. **The rule does not catch whales; the 3-se gate does.** Suppose k big wins sit on a rest
   that sums to ≤ 0. Then the mean is at most kB/n and the se is at least about B√k/n, so
   t ≤ √k. Clearing 3 se that way needs at least nine such wins. The PM's own +21x example log
   reads t = 1.39, and two +20x wins on a base read t = 1.49. The significance gate refuses
   them before any robustness rule runs. What the rule does catch is a *near-threshold*
   result whose margin rests on a few ordinary wins. In T11-1 the carrying hour is a win
   bought at 20c, holding **4.95%** of gross profit. So:
   - the copy must not say "whale";
   - success measure 2's "no hour holds more than about 5% of gross profit ⇒ positive" is not
     a valid criterion. Restate it as a broad log that clears 3 se with and without its best
     `k` hours (T11-4: t = 3.32 / 3.23 / 3.14, top_share 1.3%).
3. **The 3:1 figure in the Problem table is a small-sample reading.** On 40 walks × 1,500 bars at
   h = 5 (n = 8,474), the resolved hit rate at 3:1 is **16.3%**. The untimed baseline is 25.0%
   and the time-aware one is 16.4%. So today's bias at 3:1 is −8.7 points, not −10.6. At 2:1
   the figures are 30.6% / 33.3% / 31.0%. The conclusion stands.
4. **`timing()` does not read `predicted`** (`backtest.py:633-691`). Its weekday table compares
   hit rates with each other. The consumers of `predicted` are `summarise` (`:301`),
   `_attention_buckets` (`:421`) and `_momentum_buckets` (`:706`). Attribution ranks outcomes
   only.
5. **Using each trial's own rr does not make `expectancy_r` honest.** Over resolved trials only,
   a market with nothing in it scores q·rr − (1−q): −0.014 R at 1.5:1 and −0.34 R at 3:1. Hence
   the added `expectancy_vs_null_r` (D7).
6. **Success measure 5 holds only at the Lab default.** The shipped `predicted` moves by −0.62
   points at h = 5 on 2y of bars (computed: 40.00 → 39.38). At h = 20 it moves −0.92, and longer
   horizons move it by more than 1 point. Those bigger moves are the old baseline being more
   wrong there, not a defect of the new one.

### QA-11 — buyability robustness and threshold

**Formulas** (per gate row; `rets` in scorelog/hour order, as today):

```
mean(x)      = Σx / n
plain(x)     = sqrt( Σ(x − mean)² / (n − 1) / n )
hac(x)       = stats.newey_west_t(x, lags=min(24, n − 1))[1]   if n ≥ 10 else 0.0
se(x)        = max(plain(x), hac(x))                          # unchanged rule
rest         = rets with its k largest values removed          # k = BUYABILITY_ROBUST_DROP (2; owner D1)
                (remove first occurrences of the max, k times; keep the order of the rest)
robust_ev    = mean(rest);   robust_se = se(rest)   with lags=min(24, len(rest) − 1)
Z            = calibration.Z_CLAIM                              # 3.0, one source of truth
claims_up    = ev > Z·se  and ev > 0
robust_up    = robust_ev > Z·robust_se and robust_ev > 0
claims_down  = ev < −Z·se and ev < 0
```

The verdict compares **unrounded** values. Today it compares the 4-dp rounded row values
(`engine.py:711-726`). Rows keep their rounding for display only. `se == 0` (identical returns)
is handled as it is today: `ev > 0 = Z·0` passes. No robustness test applies to the negative
claim, because a per-stake return is bounded below at −1 and so one hour cannot carry a loss.

**Fields added to each gate row** (all existing fields kept, `loo_ev` and `top_share` included,
now as disclosures only): `robust_drop` (k), `robust_n` (n − k), `robust_ev`, `robust_se`
(4 dp; `None` when n ≤ k + 1). Top level: `z_claim: 3.0`. All additions are additive. The
orchestrator's `loo_se` is `robust_se` when k = 1. A generic name is used so that the owner's
choice of k does not rename fields.

**Verdict branch order** (`engine.py:704-736`):
1. `n < SCORE_MIN_SAMPLE` → too few (unchanged).
2. `claims_up and robust_up` → measured.
3. `claims_up` → carried.
4. `claims_down` → lost.
5. otherwise → noise.

Copy is in *Design*.

**Verified constructions** (real `Engine.buyability()`, balanced profile, 4c gate). `W` is
`_priced(0.60, 0.49, 0.50, 1.0)` and returns +0.9802. `L` is the same row with outcome 0 and
returns −1. `M` is `_priced(0.30, 0.19, 0.20, 1.0)`: it buys UP at 0.205 and returns +3.878.
`base` is 76 W and 44 L, spread evenly: position i is W when `(i·76)//120 != ((i+1)·76)//120`.

| log | n | t full | t without best 1 | t without best 2 | top_share |
|---|---|---|---|---|---|
| T11-1 `base[:60] + [M] + base[60:]` | 121 | 3.095 | 2.905 | 2.818 | 0.0495 |
| T11-2 `base[:40] + [M] + base[40:80] + [M] + base[80:]` | 122 | 3.276 | 3.095 | 2.905 | 0.0471 |
| T11-3 `base` alone | 120 | 2.904 | — | — | 0.0132 |
| T11-4 78 W / 42 L, same spreading | 120 | 3.32 | 3.23 | 3.14 | 0.0128 |
| PM's whale (`test_engine.py:974-985`) | 122 | 1.39 | — | — | 0.247 |

All margins to the 3.0 bar are at least 0.09 t. Rounding errors are about 0.002 t, so the tests
are not fragile.

**Reachability, randomised** (success measure 3). The generator, seeded with `random.Random(1)`,
draws 3,000 logs with n ∈ [100, 160], a per-log edge e ~ U(0, 0.25), a price floor ∈
{0.05, 0.2, 0.4}, a per-hour price p ~ U(floor, 0.6) + 0.005, a win with probability p + e, and
a return of (1−p)/p or −1. 1,290 logs clear 3 se. Of those, **78 fail without their best hour**
and a **further 68 fail only without their best two**. The remaining 1,144 pass. Both outcomes
are well populated. The run took 0.7 s at the return level.

**Cost.** One extra Newey-West per gate row, under the engine lock, on each snapshot (polled about
every 4 s). Measured NW cost: 0.2 ms at n = 200, 1.7 ms at n = 2,000, 7.7 ms at n = 8,760 (a
year). The worst extra is about 50 ms per snapshot after a year. That is acceptable. If it
matters later, compute the robust fields only for rows with n ≥ `SCORE_MIN_SAMPLE`.

**Module boundary.** `buyability` imports `Z_CLAIM` from `.calibration` lazily, the same pattern
as its `.research.stats` import (`engine.py:640`). `calibration` imports only `scoring`, so there
is no cycle.

### QA-13 — time-aware baseline for the backtest

**Units.** `build_plan` (`scoring.py:118, 121-139`) puts the target and stop at k_t·σ_h and
k_s·σ_h from entry, where σ_h = price · σ̂_daily · √h. `_resolve` watches up to
`max_bars = 4h` bars (`backtest.py:250`), so `W = min(4h, len(bars) − i − 1)` bars
(`:226`). Measured in σ_h, with time in horizons, a trial is a Brownian motion that starts at
0 with barriers at +k_t and −k_s and a horizon of T = W / h. That gives T = 4 for every
full-window trial, whatever σ̂, price or h. The baseline therefore depends only on
(k_t, k_s, W, h).

**Formula** (driftless for `predicted`; the drift m, in horizon-σ per horizon, is used only by
the implied-drift solver). With L = k_t + k_s and Φ the standard normal cdf:

```
G(d, μ, T) = e^{−|μ|d} Φ((|μ|T − d)/√T) + e^{|μ|d} Φ((−|μ|T − d)/√T)        # μ = 0: erfc(d/√(2T))
U(x, μ, T) = e^{μ(L − x)} Σ_{j≥0} [ G((2j+1)L − x, μ, T) − G((2j+1)L + x, μ, T) ]
           = P(exit at L before 0, by time T | start x ∈ (0, L), drift μ toward L)
P_target(T, m) = U(k_s,  m, T)        P_stop(T, m) = U(k_t, −m, T)
q(T, m)        = P_target / (P_target + P_stop)
predicted_i    = q(W_i / h, 0)
```

- **Truncation.** Stop when `G((2j+1)L − x) < 1e−15`. For T ≤ 4 and L ≥ 2 that takes at most 6
  terms (3 at T = 4, 3:1).
- **Accuracy (verified).**
  - It agrees with an independent eigenfunction series to **2.5e−11** over k_t ∈
    {1, 1.5, 2, 3, 5}, k_s = 1, T ∈ {0.05, 0.25, 1, 2, 4} and m ∈ {−3, −0.5, 0, 0.5, 2}.
  - At T = 400 it equals `scoring.barrier_probability` exactly (m = 0.3: 0.580777…).
  - It matches Monte Carlo (20,000 paths × 4,000 steps) within MC plus step-discretisation
    error: 3:1, m = 0: P_t 0.1177 MC against 0.1212.
- **Values at T = 4.**

  | R:R | P_t | P_s | timeout | q |
  |---|---|---|---|---|
  | 1:1 | 0.4954 | 0.4954 | 0.9% | 0.5000 |
  | 1.5:1 | 0.3743 | 0.5743 | 5.2% | **0.3946** |
  | 2:1 | 0.2719 | 0.6051 | 12.3% | 0.3100 |
  | 3:1 | 0.1212 | 0.6166 | 26.2% | 0.1643 |

- **Why not the eigenfunction series:** it cancels catastrophically at small T and returned
  negative probabilities at T = 0.004, which a Lab horizon of 250 reaches with a 1-bar
  truncated window.
- **Underflow guard:** if `P_target + P_stop == 0`, return 0.0 when k_t > k_s, 1.0 when
  k_t < k_s, and 0.5 when they are equal. This is the short-time limit: the nearer barrier wins.
- **Cost:** 1,000 distinct windows in 4 ms uncached. Use `functools.lru_cache` on
  `(k_t, k_s, W, h)`, which makes each trial a dict lookup. A run has at most 4h + 1 distinct
  keys.

**New pure functions** in `sonar/scoring.py`, next to `barrier_probability` (`:85`):
`barrier_probabilities_within(k_target, k_stop, horizons, edge_sigma=0.0) -> (p_target, p_stop)`
and `resolved_hit_probability(k_target, k_stop, horizons, edge_sigma=0.0) -> float`.
`horizons=math.inf` returns `barrier_probability`. The row P(profit) is untouched; the T1-1
decision holds.

**Data-truncated trials** (end of series, not a real timeout). A trial that *resolved* inside a
cut window gets `predicted = q(W/h)` with its true W, so it keeps its place in n and the
realised hit rate does not change. A trial that did not resolve is a timeout flagged
`truncated: True` and counted in `n_timeout_data_end`. We rejected dropping every decision point
whose full window does not fit: it is simpler, but it changes the realised hit rate (success
measure 5) and discards resolved data.

**Contracts:**
- `run_symbol(..., keep_timeouts: bool = False)`. The default keeps today's behaviour (resolved
  rows only), so `tests/test_attribution.py`, `tests/test_earnings.py` and the research callers
  do not change.
- Every row gains `k_target`, `k_stop`, `window` (W), `horizons` (W/h) and `truncated`, and
  `predicted` becomes `q(W/h)`.
- With `keep_timeouts=True`, rows with `outcome: "TIMEOUT"` are also emitted, with
  `predicted: None`. A consumer that forgets to filter fails loudly rather than silently.
- `run()` (`backtest.py:383-399`) calls with `keep_timeouts=True` and splits the rows into
  `resolved` and `timeouts`. Every downstream function (`summarise`, buckets, `timing`,
  `attribute`) receives `resolved` only, which is unchanged from today.
- `summarise(trials, rr=None, step=1, timeouts=())`. `rr` is kept only as a fallback for a
  hand-built trial without `rr`.

**Summary fields** (additive unless marked):
- `n_timeout` and `n_timeout_data_end`.
- `timeout_share` = n_timeout / (n + n_timeout).
- `timeout_share_expected` = the mean over all decision rows of 1 − P_t − P_s. *(Amended
  2026-10-12, owner decision "Timeout monitor": an output field only, not shown on screen and not
  diagnostic — real prices time out about twice as often with the baseline still fine. The
  coin-flip/direction placebo is the check on σ̂ and the baseline.)*
- `baseline_untimed` = the mean of k_s/(k_t+k_s).
- `expectancy_vs_null_r` = (1/n) Σ (1 + rr_i)(1[TARGET] − predicted_i), which is 0 in
  expectation with no edge.
- **Changed:** `predicted`.
- **Changed:** `expectancy_r` = (1/n) Σ (rr_i if TARGET else −1). This is identical today at a
  single rr.
- **Changed:** `implied_edge_sigma` = the m̂ that solves (1/n) Σ q(T_i, m) = hit, by bisection
  on [−5, 5] over 60 iterations, grouped by distinct (k_t, k_s, T). q is monotone in m, and
  m̂ = 0 exactly when hit = predicted. A trial with no `horizons` (the hand-built tests) is
  treated as T = ∞, which reproduces `calibration.implied_edge`, so `test_backtest.py:63`
  keeps passing.
- `calibration.implied_edge` is left with no production caller. Fix its docstring
  (`calibration.py:22`); removing it can follow later.
- `significant` and `_verdict` stay at 2 se. A backtest run is a one-shot look, not an hourly
  re-check.

**Residual bias.** The baseline is continuous BM; `_resolve` reads daily highs and lows, with a
bar touching both barriers scored STOP. Measured with the time-aware baseline on
`_driftless_walk` (24 sub-steps, σ = 1%/day, estimated σ̂, step 5, 40 walks × 1,500 bars):

| h | 1:1 | 1.5:1 | 2:1 | 3:1 | binomial se |
|---|---|---|---|---|---|
| 5 (Lab default) | −0.24 | −0.08 | −0.31 | −0.10 | ≈0.45 pt |
| 5, three more seed sets | −0.06…+0.79 | +0.16…+1.22 | +0.33…+0.74 | +0.63…+1.26 | max \|d\|/HAC-se 2.47 |
| 1 | −0.47 | +0.76 | +0.81 | +0.64 | ≈0.47 |
| 2 | −0.51 | −0.48 | −0.20 | −0.25 | ≈0.47 |
| 20 | −0.69 | −1.18 | −1.51 | −1.71 | 0.47 binomial; HAC is much wider (holds overlap about 4×) |
| 5 with true σ (σ̂ replaced) | −0.63 | −0.49 | −0.38 | −0.63 | ≈0.46 |

With the old baseline, the h = 5 row reads 0 / −0.65 / −2.70 / −8.73 (1.3, 5.1 and 17.8 se).
The sources of the residual pull in different directions:
- the tie-as-STOP rule pushes it down, and matters at h = 1, where the barriers are only 2.5
  daily σ apart;
- 24-step sampling inside a bar misses some touches;
- lognormal prices against arithmetic barriers matter more as σ_h grows;
- σ̂ comes from 30 closes, so the true barriers sit at k·σ̂/σ.

The σ̂ noise partly cancels the monitoring bias. **Expected residual at the Lab default: within
about ±0.6 points (about 1.2 se).** The model-validator's P1-3 found −0.32 points at h = 5 against
the *untimed* 40%. Against 39.46% that becomes about +0.2, so most of P1-3's "always ≤ 0" bias
was the dropped timeouts, not the tie rule. **Absorbing the tie or daily-bar bias into the
baseline was rejected.** It is path- and granularity-dependent, needs a per-run simulation, and
is smaller than the test's error bar. CONFIDENCE.md states the residual instead. Real data adds
fat tails, vol clustering and gaps, which this model does not include; ~~`timeout_share` against
`timeout_share_expected` is the on-screen check for it~~ *(amended 2026-10-12: the coin-flip
placebo on real bars is the check; `timeout_share_expected` is an output field only)*. Success measure 4 tolerates the residual
because it runs at h = 5, where |residual| ≤ 0.6 se on seeds 0–39, against a 3-se bar of
1.4–1.6 points.

**What moves at the shipped 1.5:1:**
- realised hit rate: unchanged;
- trial `predicted`: 0.4000 → 0.3946 for full windows;
- run `predicted`, 2y at h = 5: about 0.3938 (−0.62 pt). This is computed with the window mix
  of a 500-bar series and is **not verified on live Yahoo data**, which needs the network;
- the CONFIDENCE.md:587 figure, 39.58% against 39.99%, becomes about 39.58% against 39.4%. QA
  re-measures it for tech-writer.

### State and compatibility

- **Persisted outputs.**
  - `research_results/*.json` (3 files) contain no `predicted` (grep: no match), and nothing
    reads backtest output back.
  - Summaries are transient: `BacktestThread` → `ui/app.py:_lab_done` (`:2665`) /
    `_backtest_done` (`:3375`).
  - There is no migration.
- **Lab rendering** (`ui/app.py:2677-2690`, `:3380-3386`). It must read the new fields with
  `.get(...)` defaults, because hand-built summary dicts in `tests/test_lab_tab.py:66-88` and
  `tests/test_plain_language.py:228` lack them.
- **Buyability.**
  - It is computed live (`core.py:1250`) and served on `GET /api/state` (`docs/api.md:7`). The
    new fields are additive, and the UI reads only `verdict`.
  - **In follow mode the GUI shows the agent's verdict.** The new copy therefore reaches users
    only once the headless agent runs the new build. That matters for D4: the agent restart is
    still pending in `TODO.md`.
- **`replay.py`** imports `_resolve` and `_vol` (`replay.py:38`). Their signatures are unchanged.
- **Concurrency.** No change, except the added work under the engine lock (see Cost).

### Touch points

- `sonar/engine.py:600-607`: add `BUYABILITY_ROBUST_DROP = 2`.
- `sonar/engine.py:609-639`: docstring, with the leave-one-out bullet at `:632-635` rewritten.
- `sonar/engine.py:640`: lazy import of `Z_CLAIM`.
- `sonar/engine.py:678-699`: robust fields.
- `sonar/engine.py:701-736`: unrounded comparisons, branch order and copy.
- `sonar/scoring.py:85-113`: add the two functions after `barrier_probability`.
- `sonar/backtest.py:209-226`: `_resolve` unchanged; W is its `min(...)`.
- `sonar/backtest.py:235-290`: `run_symbol`, with `keep_timeouts`, the new row fields and
  `predicted = q`.
- `sonar/backtest.py:293-335`: `summarise`, with the new fields, per-trial rr and the implied
  drift.
- `sonar/backtest.py:338-349`: `_verdict` copy.
- `sonar/backtest.py:383-399`: `run`, which splits rows and passes `timeouts`.
- `sonar/backtest.py:1-40` and `:402-408`: docstrings say "predicted, given it resolved in time".
- `sonar/calibration.py:22`: docstring.
- `ui/app.py:2677-2690` and `ui/app.py:3380-3386`: wording (see Design).
- Docs:
  - `TODO.md:246-253` (the leave-one-out claim);
  - `TESTPLAN.md:212` (7.5);
  - `CONFIDENCE.md:587-589`;
  - `static/docs.html:669-676` (add "three standard errors, and still so without its two best
    hours");
  - the `tests/test_backtest.py:171-182` docstring.

### Test plan (tests first; `engineer` writes these before the code)

QA-11, in `tests/test_engine.py`, building on `_priced` at `:849`:
- **T11-1** `test_a_result_resting_on_its_best_hour_is_refused`: the T11-1 log gives the carried
  verdict, contains "without its", and has no "measured". Kills: deleting `robust_up`.
- **T11-2** `test_a_result_resting_on_its_two_best_hours_is_refused`: the T11-2 log gives the
  carried verdict. Kills: k = 2 → 1. Only if the owner picks k = 2.
- **T11-3** `test_three_standard_errors_are_needed`: `base` alone (t = 2.904) gives "within
  noise". Kills: Z 3 → 2.
- **T11-4** `test_a_broad_result_is_measured`: 78 W / 42 L gives "measured" and "three standard
  errors", and every robust field is present and positive.
- **T11-5** `test_the_robustness_rule_can_go_either_way`: the seeded generator above, run at the
  return level through a module-level helper extracted from the gate loop (for example
  `_mean_se(rets)`), keeps runtime under 2 s. Among the logs that clear 3 se, both robust
  outcomes appear, at least 20 of each.
- **T11-6** `test_a_loss_needs_three_standard_errors_too`: a log with t between −3 and −2 gives
  "within noise". `test_a_wrong_model_loses_its_stake` (`:866`) keeps "LOST".
- **T11-7** Updates:
  - `:855-863` (identical returns: se = 0, robust se = 0, so "measured") changes its copy
    assertion;
  - `:974-985` keeps the +21x log, now asserting "within noise", with a docstring saying the
    3-se gate refuses it, not the robustness rule.
- **T11-8** Copy guard: across every branch, no verdict contains "edge", "whale", "profit" or
  "leave-one-out".

QA-13, in `tests/test_scoring.py` and `tests/test_backtest.py`:
- **T13-1** `barrier_probabilities_within`:
  - the T = 4 table above to 1e-4;
  - T = 400 equals `barrier_probability` for m ∈ {−1, 0, 0.3, 2};
  - P_t + P_s ≤ 1;
  - monotone in T;
  - T = 0.004 never goes negative;
  - q → 0 when k_t > k_s.
- **T13-2** Image series against the eigenfunction series (a few lines in the test) to 1e-9 at
  T ∈ [0.5, 4]. These are two independent derivations.
- **T13-3** (success measure 4) parametrised over k_t ∈ {1, 1.5, 2, 3}:
  - 40 walks `_driftless_walk(1500, seed)`, seeds 0–39, h = 5, step 5, `keep_timeouts=True`,
    split, `summarise(..., timeouts=...)`;
  - assert `abs(delta) < 3*std_error` and `3*std_error <= 0.02`;
  - this replaces `test_with_no_drift_the_hit_rate_is_one_over_one_plus_rr` (`:170-194`);
  - measured |d|/se is 0.51 / 0.16 / 0.58 / 0.20, and 3 se is 1.41–1.59 pt. Today's code fails at
    2:1 (5.1 se) and 3:1 (17.8 se);
  - about 0.5 s per ratio.
- **T13-4** `run_symbol` keeps its default output; `keep_timeouts=True` adds TIMEOUT rows with
  `window`, `truncated` and `predicted is None`.
- **T13-5** A trial that resolves in a truncated window gets `predicted == q(W/h) < q(4)`. Use
  bars whose last few days hit the target. Kills: T = 4 for all.
- **T13-6** `summarise` reports `n_timeout`, `n_timeout_data_end`, `timeout_share` and
  `timeout_share_expected`, and `hit_rate` is identical with and without `timeouts` passed.
  Kills: counting timeouts in n.
- **T13-7** `implied_edge_sigma` is 0 (to 1e−6) when hit equals the time-aware predicted, its
  sign follows delta, and hand-built trials reproduce `calibration.implied_edge`.
- **T13-8** At rr = 3, `expectancy_r == hit*3 − (1−hit)`, and `expectancy_vs_null_r` is within
  3·(1+rr)·se of 0 on the T13-3 walks. Kills: shipped-constant rr.
- **T13-9** Lab: `_lab_html` shows `n_timeout` and its share, and the old fixture dicts without
  the new fields still render (`tests/test_lab_tab.py`, `tests/test_plain_language.py`).
- **T13-10** (success measure 5; QA, needs the network): the Lab default run (2y, h = 5, step 3,
  all) shows an unchanged `hit_rate` and a `predicted` move of less than 1 pt (expected about
  −0.6). Not verified here.
- The full suite runs natively and under `QT_QPA_PLATFORM=offscreen`.

### Failure modes and risks

- **k = 2 refuses more genuine near-threshold results.** In the random set, 146 of 1,290 are
  refused against 78 at k = 1. It says "not demonstrated", never "nothing there", which is the
  direction the app wants.
- **A misspecified vol model moves the baseline.** Fat tails or a σ̂ that is biased within a run
  shift the timeout probability and so q. ~~The guard is `timeout_share_expected` on screen.~~
  *(Amended 2026-10-12: the guard is the coin-flip placebo; `timeout_share_expected` is an output
  field, not on screen and not diagnostic.)* If real runs show a large gap, the next step is a
  bootstrap baseline, not more maths.
- **Long Lab horizons.** At h ≥ 20, overlapping holds make the binomial se meaningless, and the
  HAC se is still optimistic (P1-3's cross-symbol point). The residual there could not be
  separated from noise at this sample.
- **Follow-mode skew** between the GUI and the agent versions: copy only, and the fields are
  additive.

### Open questions, answered

- **`replay.py` TIMEOUT path: out of scope.** Its baseline `1/(1+R:R)` (`replay.py:239`) carries
  the same −0.5 to −0.6 pt bias at 1.5:1. The scorecard speaks from n = 20, where se is at least
  10 points, so the bias cannot be seen there. File a P3 TODO to reuse
  `scoring.resolved_hit_probability` in `Session.scorecard` once this ships.
- **Cross-symbol / HAC se (P1-3: reported 0.99 against empirical 1.38 pts): out of scope**, for a
  separate spec (date-clustered se across symbols). Success measure 4 uses independent walks
  and is unaffected.
- **Noticed in passing, also out of scope.** `model_vs_market` still claims at 2 se on an hourly
  re-checked log (`engine.py:582-589`), which is the T1-1 problem again. `product-manager`
  should file it as a follow-up.

### Owner decisions added by architect

- **D1′:** k = 2, the recommended "without its two best hours", or k = 1 (the PM's), in which case
  success measure 1's two-hour clause goes.
- **D6:** accept ADR 0001, which changes the meaning of `predicted` in backtest output.
- **D7:** the Lab's "Expectancy" row shows `expectancy_vs_null_r` (recommended) or the raw
  `expectancy_r` with a caveat.

D3 and D5: agree with the PM, at 3 se and symmetric. D4: agree, with the follow-mode note above.

## Verification plan  *(qa-engineer)*
