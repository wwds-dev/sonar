# Domain review (finance), round 2: time-stop shadow readout after fix loop 1

- **Scope:** fix loop 1 (`564515c`, `1c34432`, `5546cc5`) and the merge `52a715e`; strings in
  `SHADOW_WORDS` (`ui/app.py:477-593`) rendered through `shadow_texts`, `_sh_look_status`, `_sh_rows`
  (`ui/app.py:772-938`). Reviewer: domain-finance, read-only, 2026-10-12. Saved by the orchestrator.
- **Brief:** `docs/company/app-context.md` `## Domain specialist` (lines 56-65).
- **Playbook:** `docs/playbooks/domain-finance.md` is `status: baseline` (never radar-verified): stale.
- **Jurisdiction UNVERIFIED:** SEC Marketing Rule, FINRA 2210, ESMA/BaFin cited as flags only; no
  regulation text checked; not a legal opinion.
- **Evidence:** `QT_QPA_PLATFORM=offscreen ./run-tests.sh tests/test_shadow_ui.py tests/test_shadow_engine.py tests/test_calibration.py -q`
  → **191 passed, 22 deselected** (native and `-m slow` not run). Renders via `shadow_texts` on the
  hand-built `STATES` dicts of `tests/test_shadow_ui.py`, both modes, `SONAR_DATA` at a scratch dir; one
  crossed state given `n_gap=3` and mean R +0.25 [+0.02, +0.48]. Nothing computed against the real book.

## Status of round-1 findings

### P1-1 (crossed state and running mean read as "trade high scores"): RESOLVED for the crossed state; residual in the running row (N-1)
- `SH_LOOK_CROSSED_UP`/`_DOWN` (`ui/app.py:522-531`): "crossed the line. On these paper entries, higher
  scores went with higher R on average. z = +2.61; the line is ±2.315. The test ends here." (`_DOWN`:
  "lower R").
- `SH_CAVEAT_CROSSED` plain (`:532-537`): "This says only that the score sorted how these past coin-flip
  paper entries ended after 4 weeks. It does not show that trading high scores would make money: it is
  one test on 45 entries, before costs, fees and slippage, with exact fills, and a test like this can
  cross by chance even when there is no link. It is not a trading edge."; expert (`:538-540`): "Ranks
  past random-direction paper outcomes at T only; before costs, exact fills, one test with a by-design
  false-alarm rate; not a tradeable edge."
- `SH_NOTE` plain (`:584-588`): "…These are paper entries with a random direction, before costs, fees and
  slippage. Even a crossed line is not a trading edge and says nothing about how future entries end."
- Past, paper, pre-cost, exact fills and crossing by chance are now stated; the misleading reason is
  gone; no rate stated (`test_domain_p1_…` enforces no "%" in the crossed status); caveat beside the
  crossing. Unchanged: `SH_ROW_RUNNING` (`:559-562`) "running, not a test: average result +0.25R (95%
  range +0.02 to +0.48R) · link z = … · no costs" (N-1, P2-1).

### P1-2 ("what no edge would give" is a volatility check): RESOLVED
- `SH_ROW_REF` plain (`:553-556`): "what no edge would give after 4 weeks, if the volatility estimate was
  right: about 37% at the target · 57% at the stop · 5% at neither. A different split mostly means the
  volatility estimate was off. With no edge the average result is 0R whatever the volatility."; expert:
  "what no edge would give at planned σ: 37% / 57% / 5% (a σ̂ check); mean 0R at any σ".
- `SH_ROW_BAND`: "…what no edge would give if the volatility estimate was right: 37% / 57% / 5%"
  (expert "no edge @σ̂ 37/57/5%").
- Matches ADR 0002 §2. U-6 still holds (`ui/app.py:936` strips the tail when a band has no reference).
  The last sentence of `SH_ROW_REF` (the reviewer's own round-1 suggestion) causes N-1.

### P2-1 (cost and fill treatment understated): PARTLY RESOLVED
- Fixed: plain `SH_NOTE` (every state) and the crossed caveat say "before costs, fees and slippage"; the
  caveat adds "with exact fills".
- Open: the plain running row (`:560`) ends "· no costs"; the expert note (`:589-590`) ends "No costs."
  and the expert running row "· no costs" ("no costs" can read as "trading this costs nothing");
  `SH_ROW_GAP` (`:574-576`) does not say a gap exit is counted at the barrier price, not the close beyond
  it ("3 graded at the target or stop because a daily close went past it between checks"); no
  non-crossed string says fills are exact. TESTPLAN 11.15 (`static/testplan.html:311`) pins the running
  row to end in *no costs* — update it with the wording.
- Suggested: running row tail "· before costs" (expert "· pre-cost"); `SH_ROW_GAP` plain "{g} counted at
  the target or stop price because a daily close went past it between checks (a real fill there could
  have been worse)", expert "{g} gap exits, filled at the barrier, not the close beyond it". Stays P2.

### P2-2 (no calendar period beside the figures): NOT ADDRESSED; deferral acceptable with a date
`SH_COUNT` and the rows give n but no window of entry dates; "past" and "Worked out {when}" only partly
cover it. Acceptable to defer until before look 1 (≥ ~2026-11-06), the owner's call. The running row
appears from 20 results (~2026-10-20), so the cheapest safe option is to ship "entries opened {first} to
{last}" (from `entries[*].opened_at`) with this branch.

### P3 items
| Round-1 | Status | Defer? |
|---|---|---|
| P3-1 "95% range" ambiguous (`:559`) | Unchanged | Yes; one line: "95% range for the average" |
| P3-2 "the line"/z unexplained in plain mode (`_SH_TIP` `:477-481`) | Unchanged | Yes until look 1; belongs in the manual, which must not quote "5%" |
| P3-3 "at the planned size" (`SH_FINAL_NONE` `:541-544`) | Unchanged, owner's call | see below |
| P3-4 "5%" stated internally | **Resolved** (`sonar/calibration.py:263` "Nominal 5% (Pocock); measured ~6%…"; TESTPLAN 0.9 states ~6%, owner-accepted; no user-facing rate) | n/a |
| P3-5 zero stop distance as "with no closing price" (`calibration.py:424-425`, `ui/app.py:571`) | Unchanged | Yes (rare) |
| P3-6 "at that day's close" on a weekend/holiday T (`_SH_TIP`) | Unchanged | Yes |
| P3-7 "+{rr}R reached the target" exact only at planned entry (`:585`) | Unchanged | Yes |
| P3-8 a barrier keeps its outcome after an opposite close | Tracked as validator P3-4 (TODO.md:99) | Yes |

**`SH_FINAL_NONE` (owner's call, no rank):** makes no edge, profit or forecast claim, so safe in domain
terms. "planned size" can read as position size, and "ranks" differs from the "sorts" used elsewhere.
Suggestion: "…no evidence that the score sorts 4-week results, with the 201 entries planned."

## New findings

### N-1 (P2). "With no edge the average result is 0R whatever the volatility" sits above a running mean whose range can exclude 0
- **Where:** `SH_ROW_REF` plain (`ui/app.py:555-556`), expert "mean 0R at any σ" (`:558`), followed by
  `SH_ROW_RUNNING` (`:559-562`). Crossed render: "With no edge the average result is 0R whatever the
  volatility." then "running, not a test: average result +0.25R (95% range +0.02 to +0.48R) · … · no
  costs".
- **Rule:** app-context invariant (no implied edge); playbook (figures carry their assumptions); ADR 0002
  §2 (`docs/adr/0002-shadow-time-stop-grade.md:57-62`): E[R] = 0 only "if the price is a martingale over
  the window and exits fill exactly", drift cancels only "to first order"; spec Risks "Fill flattery".
- **Scenario:** from ~2026-10-20 a user reads "no edge gives 0R", then a positive average whose range
  excludes 0, and concludes an edge. The mean is pre-cost with gap exits at the barrier; at 1.5:1 the
  nearer stop gaps more often, so the mean can sit above 0 from the fill rule alone (direction reasoned,
  size not measured); non-martingale paths can move it. The note's "Even a crossed line is not a trading
  edge" does not address the running mean.
- **Self-correction:** the sentence follows the reviewer's own round-1 suggestion, without its conditions.
- **Suggested (model-validator to confirm):** `SH_ROW_REF` plain last sentence "With no edge, exact fills
  and randomly wandering prices, the average result would be about 0R."; expert "mean ≈0R at any σ
  (exact fills)"; running row "running, not a test: paper average {m}R (95% range for the average {lo} to
  {hi}R) · link z = {z} · before costs; an average above 0 here is not a trading edge". Or drop the 0R
  sentence from `SH_ROW_REF`.

### N-2 (P3). The down-crossing caveat only negates "trading high scores"
`SH_CAVEAT_CROSSED` (`:533-534`) is shared by UP and DOWN; after "lower R" it leaves "so trade low scores"
un-negated. Fix: "It does not show that trading by score would make money".

### N-3 (P3). "A different split mostly means the volatility estimate was off" — strength of "mostly" unverified
`:554-555`. The split also depends on path shape (fat tails, jumps, trend or mean reversion, the
daily-close gap rule). Low domain risk. Ask the model-validator to confirm or soften to "can mean".

### N-4 (P3). The comment on allowed "edge" phrases is out of date
`ui/app.py:474-476` (and spec line 338) say "edge" appears only in "what no edge would give" and the two
negated caveats; it now also appears in "With no edge the average result…" and "no edge @σ̂". U-1 accepts
both via the broad `"no edge "` entry in `EDGE_ALLOWED` (`tests/test_shadow_ui.py:38-39`, present since
`9b4752e`, not loosened here). Fix: update the comment and spec, or narrow the allow-list.

## Words check (both modes, every `STATES` render plus the crossed and gap variant)
No will / should / buy / sell / expect / likely / going to / bullish / bearish, no promised / advertised /
profit / certain / guarantee; U-1 passes in both modes. "edge" only in negations or the reference phrase
(N-4). "make money" only inside a negation (awareness, not a finding). Nothing reads as advice; the
remaining performance-advertising risk is the running mean beside a 0R benchmark (N-1) — for a qualified
human; jurisdiction UNVERIFIED.

## Verdict
Both round-1 P1s are resolved in the crossed state and the reference row. No new P0 or P1. P2-1 is partly
open ("no costs" and the gap fill) and N-1 is a new P2 (the unconditioned "no edge gives 0R" beside a
running mean live from ~2026-10-20); both are cheap copy fixes best made before Release. P2-2 can wait
until before look 1 (~2026-11-06) if the owner agrees; the P3s can be deferred.
