# Document phase: QA-11 / QA-13 honest baselines (tech-writer, 2026-10-12)

- Docs only. No code or test file was edited; nothing was staged or committed.
- **Playbook:** `docs/playbooks/tech-writer.md` is `status: baseline` (last-reviewed 2026-10-10), so it is stale under AGENTS.md.
- **Activity log:** `log_activity.py . document start|done --spec qa11-qa13-honest-baselines`.
- **Copy checked against the code, not the spec.** The orchestrator's round-6 polish is in the code as the spec describes it:
  - INVERTED ends "Worth testing with its sign flipped, or dropped. From one replay of past prices: a reason to look closer, not a finding." (`sonar/backtest.py:1200-1206`)
  - KEEP ends "— from one replay of past prices" (`:1207-1209`)
  - the Lab attention column is headed "vs setups with attention" (`ui/app.py:2783`)

## Files changed
- **`static/docs.html`** (the Learn tab):
  - §7 Simulate (:538-543): the bar is now "its error bar", and runs that get no verdict point to §8.
  - §7 Attribute (:560-575):
    - UNCLEAR is added to the list of grades.
    - INVERTED is hedged ("would push").
    - The IC and spread use the same-day bar.
    - The grades are not calibrated: about 5–7% of runs on placebos.
    - DROP has no error bar.
    - A run with no verdict shows "not judged".
  - §8 headline table (:637-652):
    - Predicted rate is conditional on resolving in time: about 39.4%, and 39.44% on the default run, with 40% "with unlimited time".
    - The error-bar row uses the validator r5 text, plus a one-line definition of "standard error".
  - §8 data table (:659-694):
    - The table is relabelled as the narrowest bar possible: "if independent" at the shipped 2-se rule.
    - It shows 18,973 trials giving ±0.7 if independent against ±1.8 actual.
    - It explains overlap (Newey-West) and the date-clustered (Driscoll–Kraay) bar.
    - The Lab uses whichever bar is widest.
  - New "When a run gets no verdict" section (:696-722): the 120-day cap, single class, 100 setups or 20 dates, the 5-horizon span, and the 2-horizon window floor.
  - Buyability paragraph (:746-758):
    - A claim needs 3 se. A positive one must also hold without its 2 best hours.
    - Measured false "measured" is under 0.13%; false LOST is about 3–4% under repeated looks.
    - It has low power in the first few hundred hours.
  - §8 attribution and attention (:770-783):
    - INVERTED is hedged.
    - The attention table is read "vs setups with attention", with Benjamini–Hochberg across the levels.
    - "Not detected is not the same as none."
  - "A pass that would…" (:809-821): the "Change R:R" step is replaced, because no such control exists. The one-class step now says that run gets no verdict and no grades.
  - "Working well" (:830-832): the whole watchlist, plus the same result on another range.
- **`CONFIDENCE.md`** (:574-637):
  - The "±2 s.e." column is now "error bar (±)", with a note that the study's bars were binomial and too narrow by today's rule.
  - "10%+" is now "10–100%", with a note that larger moves fall in no bucket.
  - New re-measured paragraph with the r6 §4 figures.
  - Explanation of why the prediction moved; the old 39.58/39.99 is quoted as history.
  - New paragraph of measured false-verdict rates.
- **`docs/adr/0001-…`:**
  - The Decision states the window floor (:30-33).
  - `timeout_share_expected` is an output field, not a monitor (:40-42).
  - Consequences carry the re-measured figures (:69-77), and the placebo is now the check, not the timeout gap (:88-92).
  - New "Amendments, 2026-10-12" section (:96). It covers the window floor, the 120/100/20/5-horizon/single-class gates, the error-bar floor (widest of binomial with the Agresti–Coull floor, Newey–West and Driscoll–Kraay), and the timeout field.
- **`docs/specs/qa11-qa13-honest-baselines.md`:**
  - The old `_verdict` copy (:202-223) is replaced by the shipped strings, marked amended. The Lab Difference row, the round-6 attribution polish and the null-attention copy are added.
  - The timeout-monitor statements at :425, :473 and :600 are marked amended.
- **`TODO.md`:**
  - The QA-11 Done entry (:300-309) now has the leave-one-out claim struck through and the shipped rule stated.
  - The Lab Done entry (:549) gets a short note.
  - New Open section (:74-131) with 14 items: censoring (P1 @me); sign-randomisation (P2), which also covers attribution calibration and the IC lag; h=1 tie residual (P2 @me); `model_vs_market` still at 2 se (P2 @me); 2y h=60 single regime (P3 @me); DROP has no bar; same-day pageviews; replay.py untimed baseline; the single-class gate ignores `compared_by_class`; `universe` fails open; the momentum top bucket; the left-out P3 copy items; `_daily_vol`; the slow placebo test and the step-1 mutant.
- **`TESTPLAN.md`:**
  - New 2.10: the buyability hover.
  - 7.1, 7.2, 7.3 and 7.5 are rewritten. 7.5 says the two acceptance tests are regression guards fitted to their seeds.
  - New 7.10–7.12: horizon 150 withheld, 1y h60 withheld, and the attention column and null copy.
  - The case count in the prose changes from 145 to 149. The suite-count string is untouched.
  - `static/testplan.html` is regenerated: `scripts/build_testplan.py` printed "149 cases" and exited 0.
- **`README.md`** (:284-286): "at 20 trials the band is ±21.5" is replaced by the verdict floor and the ±1.8 against ±0.7 figure. Nothing else in the README is false about the backtest or buyability.
- **`CHANGELOG.md`** (:28-45): a new paragraph under the existing "## Unreleased — 2026-10-12", after the book-broker-truth paragraph, which is untouched.

## Figures used and their source
- **Lab default (2y, h5, step 3, whole watchlist, bars to 2026-10-12):**
  - n 18,973 across 129 instruments: 50 Equity, 21 Crypto, 20 Forex, 20 Index, 18 Commodity
  - hit rate 39.55%; predicted 39.44% (40% untimed); Δ +0.11
  - se 0.88 (Driscoll–Kraay, 11-day lag), so the bar is ±1.76, shown as ±1.8
  - 2,574 timed out (11.95%); 373 too near the end of the data
  - 572 entry dates, 2024-11-11 to 2026-09-29
  - momentum buckets: n 9,313 / 5,392 / 2,772 / 1,493, Δ +0.49 / +0.14 / −0.45 / −1.20. That leaves 3 setups in no bucket.
  - timeout_share_expected 5.31%
  - Sources: QA r6 §4, and `scratchpad/qa6/live/lab_summary.pkl`, which I read directly. Reproduced in validator r6 (d).
- **Clustered coin:** 11.4% [9.9–13.0] of 2,040 judged runs; beats 3.0%, below 8.3%; up to about 18% per setting. Sources: validator r5 (a), r6 (d)(e).
- **Independent coin:** 1.6%. **Real momentum:** 0 verdicts in 102 judged runs. Source: validator r5.
- **Attribution placebo:** 4.6–7.1% graded KEEP/INVERTED (clustered and persistent placebos), 0.4% for an independent one. Source: validator r6 (a).
- **Buyability:**
  - false LOST 2.9–3.5% over looks 100→300, and 4.0% over 100→1,500
  - false "measured" at most 0.13%
  - low power (P3-1)
  - Source: validator round 1, P2-2.
- **Full-window baseline:** 39.46% (spec T = 4 table; `backtest.py` docstring). Residual within about ±0.6 pt at h5 (spec, ADR).
- **Old timeout gap:** 12.9% realised against 6.1% expected (validator round 1, P2-3).

## The 20-trial figure (orchestrator's question): ±21.9 is right for the shipped rule
- `summarise` uses se = max(binomial, Agresti–Coull); Newey–West and Driscoll–Kraay only widen it.
- The verdict is |Δ| > 2·se.
- At 40% with 8 wins out of 20:
  - binomial √(0.4·0.6/20) = 0.10954
  - Agresti–Coull, p = 10/24, √(0.4167·0.5833/24) = 0.10063
  - 2 × 0.10954 = **0.2191, so ±21.9 points**
- The old ±21.5 is 1.96 × 0.10954 = 0.2147: the textbook 95% band, not the app's rule. The old 13.6, 9.6, 4.8 and 2.1 were also 1.96-based.
- The table now shows the shipped-rule values: 21.9, 13.9, 9.8, 4.9 and 2.2.
- The caption also says, truthfully, that the textbook 1.96 band reads ±21.5 at 20 trials.
- Because of that caption, `tests/test_docs.py::test_it_states_how_much_data_a_number_needs` (which looks for "21.5") passes as it is.
- I did **not** edit the test, because this role is docs-only. Recommendation for the engineer: derive the expected figure from the code (2 × √(0.24/20)) and assert "21.9", then drop the textbook clause if wanted.

## Verification
- Docs tests: `test_testplan_page`, `test_docs`, `test_broker_docs_truth`, `test_learn_tab`, `test_plain_language` and `test_wording`. 170 passed, before the final 21.9 change.
- After the change, `test_docs` alone: 48 passed.
- Full suite after the last edit. Logs are in `scratchpad/tw/`:
  - offscreen: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`, **exit 0**, 1916 passed, 30 deselected, 48.0 s
  - native: `./run-tests.sh tests/ -q`, **exit 0**, 1916 passed, 30 deselected, 50.7 s
- The usual `libshiboken … MainWindow already deleted` teardown traceback appears in both runs. It predates this change.

## Left as is, or open
- **Stale-claim grep.** Excluding `docs/audit` and `.claude/worktrees`, the remaining hits are intentional:
  - attribution's own "leave-one-out" readings (`static/docs.html`, CONFIDENCE :385/:755, GOING_LIVE :433, `ui/app.py`)
  - the historical CHANGELOG :227 and the dated TESTING.md :26-30 QA-pass blockquote ("buyability's leave-one-out branch", "driftless `1/(1+R:R)` identity"), which is a record of 2026-10-10 and was not rewritten
  - the quoted old line at CONFIDENCE :611
  - negations in the new copy and tests
- **"Two standard errors on the difference"** stays in the Learn tab's error-bar row on purpose. It is the validator r5 text, and it explicitly denies a 1-in-20 guarantee.
- **Glossary count.** The README's "25-term glossary" is stale (§1 has 30 term rows). This was already known from earlier audits and is not changed here.
- **Model-vs-market.** The Learn tab does not describe the `model_vs_market` 2-se claim rule. It is recorded as a backlog item instead.
- **Live state.** None of the figures need the agent restarted. The new buyability copy reaches follow-mode users only once the agent runs the new build (spec, State and compatibility).
