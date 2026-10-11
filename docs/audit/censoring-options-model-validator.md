# Censoring: option 2 (cohort) vs option 3 (time stop), model-validator read (2026-10-11)

Read-only review of `calibration-censoring-by-score.md` against `calibration.py`, `portfolio.py` and ADR 0001
(main checkout, uncommitted). **Nothing was run; numbers are the audit note's.** Owner decides.

**Recommendation: option 3 (time stop, marked to market), shipped first as a shadow readout.** Option 2 is the
fallback for positions already open.

## Option 2, grade by entry cohort
- Removes the bias only if the cap is not binding. At the cap, still-open positions must be scored as something,
  which is option 3 in disguise; if only fully resolved cohorts count, slow cohorts resolve last and the sample is
  merely delayed and still selected.
- A position unresolved at the cap has no outcome under P(profit)=1/(1+R:R), so the 2σ/3σ gates ask about a
  conditional quantity, the problem ADR 0001 documents.
- Slower to a verdict, not faster. The cap (the note says 15 trading days) is a researcher degree of freedom unless
  fixed in advance. Applies retroactively; 60–80 (median open age 19.9 d) would mostly be excluded.

## Option 3, time stop
- Removes right-censoring by construction: every entry has an outcome by entry+T.
- The untimed 1/(1+R:R) is no longer the null. ADR 0001's within-window probability
  (`scoring.barrier_probabilities_within`, main checkout only) is the candidate; grade on a statistic whose
  expectation is 0 with no edge.
- Use the rank IC against realised R-multiple (continuous) rather than a 0/1 hit; re-derive the 3σ gate for it.
- Open positions: shadow replay only (virtual stop at opened_at+T; needs price history, not verified). Do not
  change the live exit rule, so comparability is kept.
- Risks: T is also a degree of freedom (fix it before looking); MTM at a poll price is noisy; fills at exactly the
  barrier (`portfolio.py:21-22`) flatter results; changing the live exit rule resets the sample.

## Proposal
- T = 4 horizons (the ADR's backtest cap); state it in calendar days. Per-preset horizon days not verified.
- Primary statistic: rank IC of confidence vs R-multiple. Secondary: target/stop/time split vs the within-T null.
- Gate: 3σ, once, pre-registered at n ≥ 45 entries all resolved to T. Keep the closed-only report, labelled provisional.
- **Smallest first step:** a read-only `calibration.shadow_time_stop(open, closed, prices, T)` shown beside the
  existing readout. If its IC and the closed-only IC differ materially, the bias is real. No change to the exit
  rule, `GRADED` or the verdict text.

## The ADR must record
1. T, and that it was fixed before any outcome was inspected.
2. The new null and what "advertised" means in the UI.
3. The primary statistic and gate: one look, or a corrected sequential gate (Z_CLAIM=3 was set for re-checking after every close).
4. Treatment of open and legacy positions (shadow replay vs excluded) and the comparability reset.
5. MTM price source, slippage and fill assumptions.
6. That it supersedes ADR 0001's rejection of mark-to-market (that was the Lab backtest, not the live book).
7. Reversal: drop the TIME outcome and fall back to closed-only.

Caveat: re-run the note's Reproduce script before citing its numbers; the live file has moved.
Route to the QA-11/QA-13 session, which has `calibration.py` and ADR 0001 open.
