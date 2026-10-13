# Domain review (finance): time-stop shadow readout, Review pass

- Scope: `git diff cf84642 HEAD` on branch `claude/zealous-mclaren-8985d0`. Reviewer: domain-finance
  (read-only), 2026-10-12. Saved verbatim by the orchestrator.
- Brief: `docs/company/app-context.md` `## Domain specialist` (lines 56-65) and the Invariants (45-54).
- Playbook: `docs/playbooks/domain-finance.md` is **`status: baseline`** (seeded, never radar-verified).
  Treat it as stale; rules cited as "playbook" are general practice no radar run has verified.
- User jurisdiction is **UNVERIFIED**. Every SEC/FINRA or ESMA/BaFin reference is a flag for a
  qualified human, not a legal opinion. No regulation text was checked.
- Pre-registration: nothing computed against the real book. The one render used a hand-built dict in a
  scratch `SONAR_DATA`.
- Evidence run: `QT_QPA_PLATFORM=offscreen ./run-tests.sh tests/test_shadow_ui.py tests/test_shadow_engine.py tests/test_calibration.py -q`
  gave **145 passed, 3 deselected** (the slow V-12 tests). Not run: native, `-m slow`.

## What holds (checked, no finding)
- **R arithmetic** (`sonar/calibration.py:385-393`): R = d·(exit − entry)/|entry − stop|. A barrier exit
  is exactly at `p.target`/`p.stop`; a time exit is the T-bar close (`:361`). The T bar counts only once
  a later bar exists (`:345-346`): no look-ahead, no in-progress close. The gap scan starts at the first
  bar stamped after entry and includes the T bar (`:357`), so a time-exit R lies strictly between −1 and
  +R:R. Zero stop distance gives no R and is never guessed (`:392-393`).
- "promised", "advertised" and "profit" do not appear in `SHADOW_WORDS` (`ui/app.py:471-577`). "edge"
  appears only in "what no edge would give" and the two negated caveats.
- `SH_NOTE` (R explanation, coin-flip caveat, "no costs") is added in every state, including loading,
  unavailable and error (`ui/app.py:757`, `:766`, `:805`). The crossed caveat is in the same INK
  `text(11)` sentence as the crossing (`:825-828`). The running row always starts "running, not a
  test" and ends "no costs" in both modes.
- No user-facing string states a 5% false-alarm rate (see P3-4).
- A "Practice money only" chip is on every page (`ui/app.py:1774-1776`).

## Findings

### P1-1. The crossed state and the running mean-R row together read as a profitable rule ("trade high scores, any direction"); the caveat's stated reason makes that reading stronger
- **Where:** `ui/app.py:516-519` `SH_LOOK_CROSSED_UP` ("crossed the line. Entries with higher scores had
  larger results."); `:526-529` `SH_CAVEAT_CROSSED` ("This means only that the score sorts how coin-flip
  entries end after {T}. It is not a trading edge."); `:569-572` `SH_NOTE` ("Even a crossed line is not a
  trading edge: the direction was random, and there are no costs."); `:545-546` `SH_ROW_RUNNING`
  ("average result {m}R (95% range {lo} to {hi}R)").
- **Rendered from a synthetic crossed dict:** "crossed the line. Entries with higher scores had larger
  results. z = +2.60 … It is not a trading edge." with "running, not a test: average result +0.25R (95%
  range +0.02 to +0.48R)", "scores 60-80: … 7 target · 3 stop" and "the direction was random".
- **Rule:** app-context invariant "No copy that implies edge, profit or certainty"; playbook (baseline):
  simulated results are never presented as returns a user could have achieved, and the past-performance
  caveat sits next to the number; SEC Marketing Rule (hypothetical performance), FINRA 2210, ESMA/BaFin
  retail-communication guidance — flag only.
- **Scenario:** a retail user reads "higher scores had larger results", sees a positive average R whose
  range excludes 0, then "the direction was random", and concludes "a random long/short bracket on high
  scores makes +0.25R". The caveat denies an edge but gives a reason that supports the reading it
  should block. Nothing says the figure is from past paper entries, before costs, from one test that can
  cross by chance.
- **Needs a qualified human (model-validator, spec Risks):** with random direction a positive slope
  means higher-score coin-flip brackets had higher mean R before costs; "the direction was random" does
  not by itself show it is not exploitable. Keep the denial, base it on true reasons.
- **Suggested wording:**
  - `SH_LOOK_CROSSED_UP` plain: "Look {k} of 3, first {N} entries ({used} with a result): crossed the
    line. On these paper entries, higher scores went with higher R. z = {z}; the line is ±2.315. The test
    ends here." (`_DOWN`: "lower R".)
  - `SH_CAVEAT_CROSSED` plain: "This says only that the score sorted how these past coin-flip paper
    entries ended after {T}. It does not show that trading high scores would make money: it is one test
    on {used} entries, before costs, fees and slippage, with exact fills, and a test like this can cross
    by chance even when there is no link. It is not a trading edge."
  - `SH_CAVEAT_CROSSED` expert: "Ranks past random-direction paper outcomes at T only; before costs,
    exact fills, one test with a by-design false-alarm rate; not a tradeable edge."
  - `SH_NOTE` plain, last sentence: "These are paper entries with a random direction, before costs, fees
    and slippage. Even a crossed line is not a trading edge and says nothing about how future entries
    will end."
- **Timing:** the running row appears at 20 results (oldest entries reach 28 days about 2026-10-20);
  the crossed state cannot appear before look 1 (about 2026-11-06).

### P1-2. "What no edge would give" misstates the reference split: it checks the volatility estimate, not the score
- **Where:** `ui/app.py:542-544` `SH_ROW_REF`; `:563-565` `SH_ROW_BAND` (expert "no edge {a}/{b}/{c}%").
- **Rule:** ADR 0002 §2 (`docs/adr/0002-shadow-time-stop-grade.md:63-68`): "This split assumes σ̂ is
  right, so it checks the volatility estimate, not the score." The code agrees
  (`scoring.barrier_probabilities_within(p.rr, 1.0, h)` at planned σ, `sonar/calibration.py:394-395`).
  Only the 0R average holds whatever the σ error. Playbook: every figure traceable to what it measures.
- **Scenario:** "scores 60-80: 7 target · 3 stop · 0 neither · what no edge would give 37% / 57% / 5%" —
  the gap reads as the score beating "no edge"; a band with more time-outs reads as the score failing,
  when either can come from σ̂ alone. Shown from the first result, so live within days.
- **Note:** the phrase was an owner constraint (spec), so amending it is the owner's call. The fix keeps
  the phrase and adds the missing condition.
- **Suggested wording:** `SH_ROW_REF` plain: "what no edge would give after {T}, if the volatility
  estimate was right: about {a}% at the target · {b}% at the stop · {c}% at neither. A different split
  mostly means the volatility estimate was off. With no edge the average result is 0R whatever the
  volatility." Expert: "no-edge split at planned σ: {a}% / {b}% / {c}% (a σ̂ check); mean 0R at any σ".
  `SH_ROW_BAND` plain tail: "· if volatility was as planned, no edge would give {a}% / {b}% / {c}%";
  expert "no edge @σ̂ {a}/{b}/{c}%". U-6 keeps working if the phrase stays.

### P2-1. Cost and fill treatment is understated, and the mean R depends on it
- **Where:** `ui/app.py:572` ("and there are no costs"); `:560-562` `SH_ROW_GAP`; gaps are recorded at
  the barrier price, not the close beyond it (`sonar/calibration.py:357-360`).
- **Rule:** playbook: a performance figure states cost, fee and slippage treatment; spec Risks "Fill
  flattery"; the no-edge 0R mean needs exact fills (ADR §2).
- **Scenario:** "there are no costs" can read as "trading this has no costs"; a stop gap at −1R hides a
  loss larger than the amount risked (contradicting "-1R lost the amount risked"); at 1.5:1 the nearer
  stop gaps more often, so the average leans up from fill assumptions alone.
- **Suggested wording:** `SH_NOTE`: "… before costs, fees and slippage, with every target and stop filled
  at exactly its price." `SH_ROW_GAP` plain: "{g} counted at the target or stop price because a daily
  close went past it between checks (a real fill there could have been worse or better)"; expert "{g}
  gap exits, filled at the barrier, not at the close beyond it".

### P2-2. No calendar period and no past-results caveat beside the figures
- **Where:** `SH_COUNT` (`ui/app.py:479`) and rows (`:534-565`): sample sizes but no window of entry
  dates; the only time shown is when the readout was computed.
- **Rule:** app-context Domain specialist: figures carry period, sample size and cost/slippage treatment.
- **Fix:** a row or suffix "entries opened {first} to {last}", from `entries[*].opened_at`.

### P3-1. "95% range" for the mean R is ambiguous
- `ui/app.py:545`; the interval uses normal 1.96 (`sonar/calibration.py:70`, `:503-506`), about 6% narrow
  at n = 20. Fix: "95% range for the average: {lo} to {hi}R"; optionally a t quantile below n = 30.

### P3-2. "The line" and z are never explained in plain mode
- `ui/app.py:506-509`, `:516-525`; `SH_TIP` explains the looks, not the line. Fix: add to `SH_TIP` "A
  look 'crosses the line' when the link between score and result is strong enough that chance alone
  would rarely produce it (|z| of at least 2.315)." Do not put "5%" here (P3-4).

### P3-3. "at the planned size" can be read as position size
- `ui/app.py:530-533` `SH_FINAL_NONE`. Fix: "… with the 201 entries planned."

### P3-4. "5%" is stated where the measured rate is about 6% (internal only, but it sets up the manual)
- `sonar/calibration.py:263` comment "5% two-sided overall"; TESTPLAN 0.9 / `static/testplan.html` "5% ±
  1.5 pt" (accurate as a band). Measured 5.9–6.2% over 20,000 null books (Build note 15, engineer report).
- Risk: the manual §10 (Design D8) would turn "a 5% chance of a false alarm" user-facing and wrong.
- Fix: comment "nominal 5% (Pocock); measured ~6% at these sizes (V-12)"; the manual quotes "about 6%
  (roughly 1 in 16)" or no rate, pending the owner's decision. Never "5%".

### P3-5. A zero-stop-distance entry is reported as "with no closing price"
- `sonar/calibration.py:392-393` sets `no_price` when `risk == 0`; labelled "with no closing price"
  (`ui/app.py:556-558`). Fix: count separately, or "with no closing price or no stop distance".

### P3-6. "at that day's close" is not always that day's close
- `ui/app.py:473` (`SH_TIP`); on a weekend/holiday T the previous session's close is used
  (`sonar/calibration.py:345`). Fix: "…or at the last daily close on or before that date"; `SH_ROW_SPLIT`
  "valued at the last daily close at {T}".

### P3-7. "+{rr}R reached the target" is exact only for fills at the planned entry
- `ui/app.py:569-570`; Build note 5: a worse fill moves the entry, not the barriers. Fix: "about +{rr}R".

### P3-8. For the model-validator: a book barrier keeps its outcome even when an earlier daily close had crossed the opposite barrier
- `sonar/calibration.py:376-383` and `:348-352`. Follows ADR rule 1 (Barrier before Gap). A Mac that
  slept through a stop-crossing close and later recovered to the target is graded TARGET. Frequency
  unknown.

## Verdict
R arithmetic, fills, the time exit and the no-look-ahead rules are correct; the copy avoids
"promised", "advertised", profit and edge claims, never states "5%", and shows the coin-flip caveat in
every state. **P1-2** (the reference split presented as a no-edge benchmark, live within days) and
**P1-1** (crossed and running-mean wording plus "the direction was random" invite "trade high scores";
not past-period or cost-qualified) should be fixed or explicitly deferred by the owner before Release.
Neither is a legal ruling.
