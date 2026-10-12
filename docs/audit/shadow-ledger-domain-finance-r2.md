# Domain review (finance), Review stage r2: shadow ledger diff bdd8a2b..8c27183
Reviewer: domain-finance, read-only, 2026-10-12. Saved by the orchestrator from the agent's report.

Summary:
1. No P0 or P1. Two P2s and four P3s, all about wording. None of the new strings claims edge, profit, certainty or advice. Every look line carries N, the number used and the number left out. SH_NOTE (paper, before costs) still ends every readout.
2. Gating holds. `_sh_shown` (ui/app.py) shows z, a crossing, a past-look row or the extremes only when `recorded is True` and the record is not in the `read` or `missing` state. SH_FINAL_NONE needs every look to be recorded. Every path in `_sh_look_status` and `_sh_rows` was traced; no leak found.
3. Of the Define fixes: P2-2, P2-3, P2-4, P2-5, P3-2, P3-3, P3-4 and P3-6 are in place as accepted, or stronger. P2-6 is partly done (record date shown; restart refused while the marker exists). P3-5 is handled differently, and the handling is acceptable. P2-1 was reworded in a way that brings back the "proven range" reading.
4. "Record" instead of "ledger" is acceptable, and plainer for a lay user. One optional P3 on the "track record" connotation.
5. `tests/test_shadow_ui.py`: 89 passed (offscreen, at 8c27183). Playbook `docs/playbooks/domain-finance.md` is `status: baseline`, so it counts as stale. Jurisdiction is UNVERIFIED and no regulation text was checked (not verified); any advertising judgment needs a qualified human.

## What holds (evidence)
- P2-2: `r_stop`/`r_target` are per member and use the signed risk (sonar/calibration.py:354-360, 588-594). P3-4/P3-5: `no_risk` means risk ≤ 0, it is known at fill, and it is left out of the extremes with a reason (calibration.py:309-312). The copy "stop at or past the fill price" / "risk ≤ 0" matches the code.
- P2-3: SH_LOOK_NOT_ROBUST (ui/app.py:533) has its own key, puts the date first and shows z on its own side of the line. P2-4: SH_LEDGER_READ is stronger than asked, because no look at all is shown. P2-5/P3-2: SH_MISMATCH_CONSTANTS and SH_MISMATCH use the accepted text. P3-3: SH_LOOK_WAITING_UNTIL uses the accepted text. P3-6: "recorded {date}" comes before z on every result line.
- P2-6: SH_RECORD (ui/app.py:634, 940) and SH_LEDGER_MISSING stop a silent restart while the book's marker exists. Still open from P2-6: the ADR sentence saying the record is not tamper-evident, and the dated archive. ADR 0002 is outside this diff (not verified).

## Findings
**P2-1. SH_EXTREMES reads as a proven range again.** ui/app.py:542-545, used at 1079. Plain: "z would be {lo} at the lowest and {hi} at the highest" says no fill can go below {lo} or above {hi}. `extreme_z`'s own docstring (calibration.py:427-441) says "not a bound on z". Scenario: a lay user sees a crossing with "at the lowest 2.4" and reads the crossing as certain whatever the missing entries did.
Fix, plain: "The {x} left out have no usable result. Filled in at the extremes for the score (each at its target or its stop), the lowest z found was {lo} and the highest {hi}. These are extreme cases, not estimates and not limits."

**P2-2. An erratum line does not say which look it touches, and leaves out the corrected R.** ui/app.py:656-658 and 969-972. `ledger_errata` adds `looks` (calibration.py:1126-1136) and the erratum carries `r`, but the UI uses neither. Build note 12 and the spec say it is shown "beside the look". Scenario: a recorded crossing stays on screen while an erratum the reader cannot tie to it says "one result ... found wrong".
Fix: "Erratum {date}: a result counted in look {ks} was later found wrong ({reason}); corrected R {r}. As fixed in advance, the recorded look is kept, and it may rest on this error." Use "in no recorded look" when `looks` is empty. Expert: "erratum {date}, look {ks}: {reason}; R → {r}; recorded kept".

**P3-1. While the record is blocked, the status line says "not recorded yet".** ui/app.py:539, 1008. In the `read` or `missing` state the look may well have been recorded. Fix: a separate key when blocked. Plain: "Look {k} of 3: not shown as a result while the record cannot be used." Expert: "Look {k}/3: record unavailable; no result shown."

**P3-2. The crossing caveat after a look that did not count asserts that the score sorted the outcomes.** ui/app.py:1016-1018. Fix: SH_CAVEAT_NOT_ROBUST: "A z past the line would say at most that the score sorted these past coin-flip paper entries after {T}; here it does not hold once the left-out entries are counted. It does not show that trading by score would make money: one test on {used} entries, before costs, fees and slippage, with exact fills. It is not a trading edge."

**P3-3. "Not in every extreme case" is wrong when the extremes could not be worked out.** ui/app.py:533-536. `extreme_z` returns `(None, None, method)` when a member's barriers are unknown (calibration.py:440-441). Fix: when `z_lo` or `z_hi` is None, plain "... but the {x} left out could not be filled in, so it does not count as crossed; the test goes on." Expert "extremes n/a; not crossed ({x} excl.)".

**P3-4. "Record" next to results can read as "track record" (optional).** ui/app.py:634, 646-655. Optional fix: "Log of looks kept since {date}." / "Look log since {date}". Also note in the spec that the expert copy deliberately differs from the spec's "ledger".

## Verdict
No P0 or P1. P2-1 and P2-2 should be fixed before release, or the owner should defer them explicitly. The P3s are optional polish. The performance-advertising and jurisdiction questions stay with a qualified human.
