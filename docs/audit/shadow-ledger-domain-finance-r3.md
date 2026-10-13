# Domain review (finance), round 3: shadow-ledger copy, fix loops 1 and 2 (8c27183..aa3de64, ui/app.py and README.md)
Reviewer: domain-finance, read-only, 2026-10-13. Saved by the orchestrator from the agent's report.
The real book and Application Support were not read. Playbook `status: baseline` (stale). Jurisdiction
UNVERIFIED; no regulation text checked.

Summary:
1. All r2 fixes are in as accepted: P2-1 SH_EXTREMES (ui/app.py:566), P2-2 SH_ERRATUM with look and
   corrected R (735, 1074-1086), P3-1 SH_LOOK_BLOCKED (562, 1125), P3-2 SH_CAVEAT_NOT_ROBUST (549, 1138),
   P3-3 SH_LOOK_NOT_ROBUST_NA and its row (541, 631). Optional P3-4 not taken.
2. No new string claims edge, profit, certainty or advice. Gating is tighter: `crossed is True`
   (1120, 1222); `_sh_warnings` no longer shows an unrecorded look (1248-1258).
3. One P1: the retire step lets a new record start for the same book without a reset, and the
   readout then shows no trace of the earlier record.
4. `tests/test_shadow_ui.py`: 89 passed (offscreen, aa3de64).

## Findings
**P1-1. Retiring the record redoes the test for the same book, and the readout does not show it.**
README.md:268-276; ui/app.py:682 (SH_LEDGER_FOREIGN), 711 (SH_LEDGER_RESTORE, appended at 1053 to every
"missing" line, including "this book had one" at 1050); sonar/core.py:751-753 and table row 724. Test
`test_cr2_p2_n2_retiring_without_a_reset_starts_a_new_record_for_the_same_book`
(tests/test_shadow_ledger.py:1679) asserts a new id with the same entries. README calls the record
"write-once" and the looks "fixed in advance"; a retire with the book's own marker present starts a new
record that re-evaluates the same entries (possibly under new constants, which also clears the
constants mismatch). Afterwards only "Record kept since {new date}" shows. A lay reader sees a verdict
with no sign it is a second attempt: selective reporting.
Fix (code): count retired files and show them in SH_RECORD: "Record kept since {date}. {n} earlier
record(s) were retired in this folder, the first on {date0}. Their looks are not counted here, and this
record re-tests the same kind of entries." Expert: "Record since {date}; {n} retired (first {date0})."
Fix (copy): README:268 and SH_LEDGER_FOREIGN / SH_LEDGER_RESTORE must say retiring without a reset
re-tests the same entries; on the marker path drop the retire sentence or say "This book was not reset;
retiring here starts the test again on the same entries." If the owner accepts same-book retirement,
record it in ADR 0002 with the disclosure.

**P3-1. "Counted but not recorded" is ambiguous.** ui/app.py:719-724. Fix: "1 result could not be
written to the record: it did not pass the record's own checks. It is not in the record, so a look that
uses it cannot be fully checked against the record." Expert: "1 result refused by the record's checks;
not in record".

**P3-2. A hidden erratum may be the one that matters.** ui/app.py:742, 1075, 1088: only the first 5 in
file order are shown. Fix: errata touching a recorded look first, then newest; "{n} more errata are in
the record; {m} of them touch a recorded look." Expert "+{n} errata ({m} on looks)".

**P3-3. "Corrected R n/a" when the erratum carries no R.** ui/app.py:735, `_sh_r` (902-904); `r` is
optional (calibration.py:1114). Fix: "; it has no usable R" / "R → none".

## What holds
SH_EXTREMES "not estimates and not limits" (expert "not a bound"); SH_ERRATUM names the look or "no
recorded look" and says "may rest on this error"; SH_CAVEAT_NOT_ROBUST keeps costs and "not a trading
edge"; SH_LEDGER_BEHIND, SH_LEDGER_RETIRED and "It is not started again" are honest; "Nothing is
deleted" holds. Still open from r2 P2-6 (outside this diff): the dated archive.

## Verdict
P1-1 must be fixed, or explicitly deferred by the owner, before release. P3s are polish.
