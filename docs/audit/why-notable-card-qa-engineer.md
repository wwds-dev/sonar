# why-notable-card: Verify (qa-engineer)

- Date: 2026-11-18
- Final commit: a29df15 (HEAD moved during the runs: eac6600, then fb031b0, then a29df15)
- Machine: load average up to 220 on 8 cores, so the runs used TEST_BUDGET_S=3600

**Verdict: fail.** The full suite is not green in either mode, and there is one P1.

## Review fixes
Every P1 and P2 from the code-reviewer and domain-finance reports is fixed and has a test.
- Mutants planted: 19. Killed: 18. Survived: 1 (M2, see P3).
- The four CR P3s are fixed.
- Still open (P3): the card does not use the window the scan actually used; a non-share earnings value is logged but not forced to zero at the source; "momentum" is missing from BANNED; Design P3-5 and P3-6.
- Not verified: how the score cell looks in the native app, and real VoiceOver.

## Full suite

All three runs used `./run-tests.sh -q -p no:cacheprovider -rfE`.

| Mode | Commit | Failed | Passed |
|---|---|---|---|
| offscreen | eac6600 | 15 | 3346 |
| native | fb031b0 | 5 | 3356 |
| offscreen | a29df15 | 4 | 3357 |

- **Fixed by fb031b0..3dc8b76:** the `test_refused_action_message` FakeRow failures and the suite-size test. Both pass at a29df15.
- **Environment:** the `test_ci_pins` and `test_legal_copy` playmaker failures come from the nested repo pins in this worktree. The branch does not touch those files. Not checked against master.
- **P1-1:** `test_a_rebuild_keeps_scroll_and_focus` fails.

## Findings
- **P1-1:** `tests/test_why_card_ui.py:215` (`assert 0 == 40`) fails in 3 of 3 full runs but passes when run alone, so it depends on test order. The suspects are `ui/app.py:5144-5161` and the scroll-want window, which went from 500 ms to 3000 ms without explanation. This blocks merge.
- **P2-1:** the CR P3-4 fix causes a focus regression (`ui/app.py:5136-5140`, `:5167-5170`). When the open row leaves the board, focus lands on another row's score cell instead of the board header that Design requires. No test covers it.
- **P3:**
  - M2 survivor (`ui/why_card.py:226`): no test checks that a part with zero fraction never gets a point.
  - `test_the_payload_carries_the_calendar_coverage` only greps the source code.
  - The fixture's hand-added `earnings_calendar` is not noted in its provenance.
  - The 3000 ms scroll window is not explained.

## Success measures
1. Met.
2. Met.
3. Met.
4. Pending: needs five cards read by the owner.

Branch coverage: not verified, because coverage is not installed.
