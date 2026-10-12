# Domain review (finance), round 3: time-stop shadow readout after fix loop 2

- **Scope:** fix loop 2 (`ed52c04`, `0de1afc`, `c939b53`; `git diff 52a715e c939b53 -- ui/app.py docs/specs/shadow-time-stop.md TESTPLAN.md static/testplan.html`)
  at HEAD `a23556e`. Reviewer: domain-finance, read-only, 2026-10-12. Saved by the orchestrator.
- **Brief:** `docs/company/app-context.md` `## Domain specialist` (lines 56-65).
- **Playbook stale:** `docs/playbooks/domain-finance.md` `status: baseline` (never radar-verified).
- **Jurisdiction UNVERIFIED:** wording flagged against SEC Marketing Rule, FINRA 2210, ESMA/BaFin practice;
  no regulation text checked; not a legal opinion.
- **Evidence:** `SONAR_DATA=<scratch> QT_QPA_PLATFORM=offscreen ./run-tests.sh tests/test_shadow_ui.py tests/test_shadow_engine.py tests/test_calibration.py -q`
  → **237 passed, 22 deselected** (native and `-m slow` not run). Every `STATES` dict rendered through
  `shadow_texts` in both modes (mode set in memory), plus three hand-built states: (a) crossed up with
  `n_gap=3`, mean +0.25 [+0.02, +0.48], graded and left entries; (b) none graded, entries spanning a year;
  (c) a bad `opened_at`. Nothing touched the real book.

## Status of round-2 findings
| r2 | Status | Evidence (new strings) |
|---|---|---|
| **P2-1** "no costs" and gap fill | **RESOLVED** | Running row plain: "running, not a test: paper average +0.25R (95% range for the average +0.02 to +0.48R) · link z = … · before costs; an average above 0 here is not a trading edge"; expert "… · pre-cost; mean > 0 is not a tradeable edge". Expert note "…not a tradeable edge. Paper; before costs, fees and slippage; exact fills." Gap row plain "3 counted at the target or stop price because a daily close went past it between checks (a real fill there could have been worse)"; expert "3 gap exits, filled at the barrier, not the close beyond it". TESTPLAN 11.15 and 11.18 updated (.md and .html). No rendered string says "no costs". |
| **N-1** unconditioned 0R beside the running mean | **RESOLVED** | `SH_ROW_REF` plain "With no edge, exact fills and randomly wandering prices, the average result would be about 0R."; expert "mean ≈0R at any σ (exact fills)"; the running row carries its own "not a trading edge" clause. |
| **P2-2** entry-date window | **RESOLVED** (owner decision) | First row "entries opened 13 Aug to 2 Sep" (expert "opened 13 Aug to 2 Sep"); year added when it differs ("7 Sep 2025 to 9 Oct"); a bad date "n/a to n/a"; absent with no entries. `_sh_window` (`ui/app.py:902-917`) uses the same graded protocol set as the mean, counts and IC (`sonar/calibration.py:592`). Tests `tests/test_shadow_ui.py:625-677`. |
| N-2 down crossing negated only high scores | **RESOLVED** | "It does not show that trading by score would make money" |
| N-3 "mostly" | **RESOLVED** | "A different split can mean the volatility estimate was off." |
| N-4 out-of-date "edge" comment | **RESOLVED** | comment `ui/app.py:475-479` updated; `EDGE_ALLOWED` narrowed to five exact phrases (`tests/test_shadow_ui.py:38-40`); spec matches (~line 339) |
| P3-1 "95% range" | **RESOLVED** | "95% range for the average" |
| P3-2, P3-5, P3-6, P3-7, P3-8 | Unchanged, deferred | as in r2 |
| `SH_FINAL_NONE` | Unchanged; owner decides | "no evidence that the score ranks 4-week results, at the planned size." No edge, profit or forecast claim; r2 note stands |

**Period, sample size and costs beside the figures** — present in every state that shows figures: period
(window row, first under the status); sample size (the count "45 of 60 at 4 weeks", "45 with a result",
"first 45 entries"); costs (running row, crossed caveat, note).

## Words check (both modes, all renders incl. the three extra states)
None of will, should, buy, sell, expect, likely, going to, bullish, bearish, promised, advertised, profit,
certain, guarantee. "edge" only in the five allowed phrases; "make money" only inside the negation.
Nothing reads as advice or performance advertising (for a qualified human; jurisdiction UNVERIFIED).

## New findings
- **N-5 (P3).** The spec still requires "no costs" and an unconditioned "average result 0R"
  (`docs/specs/shadow-time-stop.md:222`, `:224-225`, `:279` "The mandatory caveat and \"no costs\" appear
  in both modes"). An engineer restoring copy to the spec would bring back r2 P2-1 and N-1; it also
  contradicts TESTPLAN 11.15/11.18. Fix: "before costs" and the conditioned 0R sentence.
- **N-7 (P3).** "a real fill there could have been worse" (`SH_ROW_GAP` plain, `ui/app.py:580-581`) is true
  only at the stop; through the target a fill would be at the target or better. Cannot flatter results.
  Optional fix: "(a real fill could have been different, often worse at a stop)".
- **N-6 (P3).** The window row changes what it covers (`ui/app.py:908-913`): graded entries once any are
  graded, all protocol entries (incl. excluded) before; the plain wording is the same. Beside "45 of 60 at
  4 weeks" a reader can take the window to cover all 60. Fix: plain "the 45 with a result opened {first}
  to {last}", or "entries opened … (none has a result yet)" before any is graded.

## Verdict
Every round-2 finding resolved (P2-1, N-1, P2-2, N-2, N-3, N-4, P3-1). No new P0, P1 or P2; three
deferrable copy/doc P3s (N-5 to N-7). Nothing blocks Review in the finance domain. Before Release the
owner decides `SH_FINAL_NONE`; the jurisdiction question needs a qualified human.
