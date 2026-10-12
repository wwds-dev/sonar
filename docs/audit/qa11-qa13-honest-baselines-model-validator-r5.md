# Model validation, round 5: loop 4 on the uncommitted code, with live bars

- Validator: `model-validator` (read-only), 2026-10-12. Saved by the orchestrator.

**Overall: fit with caveats** for what loop 4 covered (the headline verdict and the attention verdict). Two conditions apply:
- The verdict copy has to change before release. "More than two standard errors" and "did worse than a coin flip" are not supported (P2-A, P2-B).
- The attribution panel still grades components on noise (P1-A). That is a pre-existing problem outside loop 4's authorisation, so it needs an owner decision. I rate it "not fit" as a graded claim.

**How I tested.**
- I fetched fresh Yahoo bars at 04:10 today: 129 of 129 instruments on 1y, 2y, 5y and 10y. 10y needed two refills after rate-limits.
- The model files had not changed since 01:04, before I started.
- Scripts and outputs are in `/private/tmp/claude-501/-Users-as-Documents-lab-active-sonar/a26ec703-42e8-43e7-ab51-f430c0bd1c34/scratchpad/r5/`. The main ones:
  - `sweep5.py` → `main.jsonl`: step 3, 4 ranges × 41 horizons, momentum plus 20 independent coins plus 20 clustered coins, 6,724 runs.
  - `step1.jsonl`, `step10.jsonl`, `step30.jsonl`: the same at other steps.
  - `e2e5.py`: the real `backtest.run`, with n, wins, Δ and the Driscoll–Kraay (DK) se recomputed independently from the raw trials.
  - `news5.py`: news-on-noise.
  - `attr5.py`: attribution placebo.
  - `an5.py`, `an5b.py`: analysis, including cluster-bootstrap intervals.
- I wrote nothing to the repo apart from gitignored `__pycache__`. The other changes in the worktree come from a concurrent session.

### (d) The DK port matches my reference
- On identical trials and lag, `backtest._dk_se` agrees with my `dk_se` (`r4/sweep.py`) to within 1.6e-16 across 9,522 runs.
- One convention differs, and the shipped one is better. It takes the lag from the unrounded average hold; my round-4 reference used the 1-decimal `avg_bars_held`. That changes L by one day in 295 of 6,724 runs and moves the se by at most 1.5% (2.4% at step 1).
- Another difference: the shipped code treats a trial without an entry time as its own cluster; my reference had no such case.

### Two headline numbers reproduced from raw data
- **Lab default, 2y h=5 (live):** n 18,973, 7,504 wins, Δ +0.11, se 0.88 (binomial alone 0.355), z 0.12 → "within 1.8 points". On the round-4 cached bars: n 18,958, 7,523 wins, Δ +0.24, se 0.88, as the engineer reported.
- **10y h=60 momentum (live):** n 94,213, 39,361 wins, Δ +2.36, se 1.86 (DK; binomial 0.161), z 1.27 → "no edge". Round 4 had z +4.6 and "beats".
- **Engineer's Terminal figures, matched exactly on the cached bars:** 1-day z −1.23, 20-day 0.67, 60-day 0.69. On live bars: −1.41, 0.57, 0.66, and 250-day withheld.

### (a) False verdicts from the coins, whole watchlist
Cells read "beats / below / judged runs". "w" counts withheld runs.

**Independent coin, step 3**

| Range | h 1–2 | 3–29 | 30–59 | 60–89 | 90–120 |
|---|---|---|---|---|---|
| 1y | 0/2/40 | 0/6/140 | 0/4/40 (80w) | all withheld | all withheld |
| 2y | 0/0/40 | 0/4/140 | 0/0/120 | 0/0/80 (100w) | all withheld |
| 5y | 0/2/40 | 0/4/140 | 0/0/120 | 0/7/180 | 0/1/240 |
| 10y | 0/0/40 | 1/2/140 | 0/0/120 | 0/0/180 | 0/0/240 |

- All judged runs, step 3: "beats" 1/2,040 (0.05%), "below" 32/2,040 (1.6% [0.9–2.3]). Round 4 had 5 and 379. Mean z² 0.80, so the DK bar is conservative for this coin.
- Other steps: any false verdict 3.5% at step 1, 2.8% at step 10, 4.4% at step 30.

**Clustered coin (one direction per class and ~h-day block), step 3**

| Range | h 1–2 | 3–29 | 30–59 | 60–89 | 90–120 | Any false |
|---|---|---|---|---|---|---|
| 1y | 0/3/40 | 3/15/140 | 1/5/40 | – | – | 12.3% |
| 2y | 0/0/40 | 2/12/140 | 10/12/120 | 5/6/80 | – | 12.4% |
| 5y | 1/4/40 | 5/4/140 | 3/10/120 | 3/26/180 | 8/35/240 | 13.8% |
| 10y | 2/3/40 | 1/6/140 | 2/3/120 | 5/11/180 | 11/15/240 | 8.2% |

- **All judged runs, step 3: 11.4% [9.9–13.0], cluster-bootstrap over 102 (range, horizon) cells.**
  - "beats" 3.0% [2.3–3.9]
  - "below" 8.3% [7.0–9.9]
  - mean z² 1.63
- Other steps: 11.0% [8.7–13.5] at step 1 (beats 2.3%, below 8.7%); 7.8% at step 10; 10.6% at step 30 (beats 5.0%).
- This confirms the engineer's ~10.9%. The ≤ 5% target is not met.
- Where the excess comes from:
  - Across seeds, Δ spreads about 1.11 times the shown se on average (up to 1.7 at long horizons). That is DK running thin with few long blocks.
  - On top, each price path shifts Δ by about 0.3 se. At 5y h ≥ 60 it is −0.4 to −0.5 se: the daily-bar residual from round 4.

### (b) Real momentum under the new se
- No momentum verdict anywhere: 0 of 102 judged runs at step 3, 0/26 at step 1, 0/32 at steps 10 and 30.
- The largest |z| is 1.56 (10y h=40).
- Cost: under this bar the app cannot report a momentum effect at any setting it judges.

### (c) News on noise: fixed
- Random attention unrelated to prices, 35 judged runs per design. The designs are per-symbol (iid) noise and spike days shared across a class.
- "Shifts the odds" 0 of 70 (round 4: 9 of 21). Significant buckets 0 of 280. Bucket mean z² 0.35, which is conservative.

### Is "more than two standard errors" misleading at ~11%?
**Yes, moderately.** The arithmetic is literally true: Δ is more than twice the number shown. But the phrase claims a calibrated test, roughly a 1-in-20 false alarm (1 in 40 for "beats"). Measured on these prices:
- Overall, a meaningless correlated direction gets a verdict 1 run in 9. The rule behaves like a 1.6-se test, not a 2-se one.
- "beats" is 3.0% overall but 8.3% at 2y h 30–59 and 6.3% at 2y h 60–89.
- "below" is 8.3% overall, rising to 14–15% at 5y h 60–120.
- Readers without finance training take "two standard errors" as a precise guarantee.
- The "below" sentence ("did worse than a coin flip") is wrong for a coin flip one time in 12.

**Recommended strings for the tech-writer** (until a sign-randomisation test exists):
- `sonar/backtest.py:753-756` (beats): "Hit rate beats the prediction by {d} points, outside its error bar (±{2se}). That bar is not a guarantee: in our tests on these prices, a direction picked at random for a whole asset class landed outside it about 1 run in 10. Before costs, from one replay of past prices: a reason to look closer, not a finding."
  - If the owner does not want a measured rate in code: "…outside its error bar (±{2se}), but a direction picked at random can land outside this bar more often than the bar suggests. Before costs, …"
- `:757-759` (below): "Hit rate is {d} points below the prediction, outside its error bar (±{2se}). A direction picked at random can land this far below too, so this does not show the lean is worse than a coin flip. Before costs, from one replay of past prices."
- `:748-750` (within): keep as is. The bar is conservative for "no edge", with independent-coin z² 0.8.
- `ui/app.py:2750`: replace "(±{x} at 2 s.e.)" with "(error bar ±{x}; setups entered on the same day counted together)".
- `static/docs.html:623-624`: "Error bar — Two standard errors on the difference, with setups entered on the same day across instruments counted together, because instruments move together. Even so, a direction that means nothing lands outside it about 1 run in 10 on real prices (validator tests, 2026-10-12, 2,040 runs), not 1 in 20. This is the number that decides, and it is not a guarantee."

### Findings
**P1-A: attribution grades components on noise in judged runs.** This was round-4 P2-F; I'm raising it because it is now the only place real runs still make strong claims.
- **What the code does.** The IC p-value is Newey–West over the pooled list, with no clustering by date (`sonar/backtest.py:1014`, `_ic_t` `:1070`). The quintile spread uses a binomial se (`:954`). Benjamini–Hochberg runs at q=0.10 (`:1022`). The verdict rules at `:1110-1149` include "Flip its sign or drop it" (`:1137`). It is shown in the Lab (`ui/app.py:2807`; the "ranks backwards" sentence at `:2868`).
- **Placebo.** I put a meaningless `c_news` into real momentum trials on 6 judged settings, 20 seeds each. How often it was graded KEEP or INVERTED:

| Placebo design | KEEP / INVERTED | Survives FDR |
|---|---|---|
| iid per trial | 1/120 | 7/120 |
| Per symbol, persistent like volatility | 14/120 (12%) | 18/120 |
| Per (class, block) | 29/120 (24%) | 44/120 |

- **Real runs.** On "no edge" runs, volatility is "INVERTED" on 8 of 11. At 10y h=60 momentum reads "KEEP". At 2y h=1 both components read "INVERTED" and "blend ranks backwards" is True.
- **Fix options:** date-clustered DK on the IC products and the spread, or "not judged" everywhere until that is done.

**P2-A: verdict copy overstates the test** (`:754`, `:758`). Evidence and wording above.

**P2-B: "did worse than a coin flip"** (`:758-759`) is false for a coin 8.3% of the time.

**P2-C: the acceptance test pins the remaining error rather than meeting the target.**
- `tests/test_backtest.py:1207-1214` allows ≤ 7/60 (11.7%) and z² ≤ 1.5, about 2.5 times the nominal rate. It passed when I ran it.
- It covers synthetic h=5 and h=20 only, not the long horizons where the real excess is largest (5y h 60–120 "below" 14%).
- Label it a regression guard; the ≤ 5% target is still open, and closing it needs the sign-randomisation p-value.

**P2-D: docs are out of step with the new bar.**
- `static/docs.html:629-650` still describes Newey–West only and a binomial trials-to-band table. Whole-watchlist bars are now set by entry dates, not trials: 18,973 trials give ±1.8, not ±0.7.
- `docs/specs/qa11-qa13-honest-baselines.md:200-203` still has the old copy.
- CHANGELOG, CONFIDENCE and the ADR are not updated (the engineer flagged this).

**P3 items:**
- The null copy "Attention makes no difference … changed nothing" (`:912-916`) overclaims for a test this low-powered (z² 0.35). Suggest: "No attention level stood apart from the run as a whole … no effect of a news spike was detected, which is not the same as none."
- The Lab attention table is headed "vs baseline" and shows `delta`, while significance and the news text use `vs_run` (`ui/app.py:2773-2780`).
- Carried from round 4: "even a coin-flip direction reads above" (`:737`) should be "can read"; `run()` defaults `universe` to the whole watchlist, so it fails open (`:765`).
- New: same-day pageviews (`:257-277`) include hours after the US close. This is a minor look-ahead.

### Verdict per claim
| Claim | Verdict |
|---|---|
| DK port matches the reference | Supported (≤ 1.6e-16) |
| Headline se = max(binomial/Agresti–Coull, Newey–West, DK) | Supported (`:584-614`; reproduced) |
| Independent coin rarely gets a verdict | Supported (1.6% step 3, 3.5% step 1, "beats" 1/2,040) |
| Clustered coin ~10.9% on real bars | Supported (11.4% [9.9–13.0]) |
| Clustered coin ≤ 5% | Unsupported (open) |
| "More than two standard errors" as a 2-se test | Unsupported (about 2.4 times the nominal rate) |
| "Did worse than a coin flip" | Unsupported |
| Real momentum gets no verdict; Terminal figures | Supported (0/160 judged; engineer's numbers exact) |
| Lab default "no edge" | Supported |
| News "shifts the odds" fixed | Supported (0/70) |
| "Attention makes no difference" | Unsupported as worded ("not detected" is supported) |
| Attribution KEEP / INVERTED on judged runs | Unsupported (placebo 12–24%) |
| Acceptance test guards the DK floor | Supported as a regression guard only |

Relevant files:
- `/Users/as/Documents/lab/active/sonar/sonar/backtest.py`
- `/Users/as/Documents/lab/active/sonar/ui/app.py`
- `/Users/as/Documents/lab/active/sonar/tests/test_backtest.py`
- `/Users/as/Documents/lab/active/sonar/static/docs.html`
- `/Users/as/Documents/lab/active/sonar/docs/specs/qa11-qa13-honest-baselines.md`
