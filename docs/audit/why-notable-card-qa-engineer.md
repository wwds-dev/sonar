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

---

# Re-Verify (scoped, owner's choice), 2026-11-19, at 2132740

**Verdict: pass with notes.** P1-1, P2-1 and the four P3s from the first Verify are fixed. There are no P0, P1 or P2 findings.

## What changed
- **P1-1, scroll restore:** it no longer drops the wanted scroll position on a timer. It now restores on a scroll-range change (`ui/app.py:5156-5169`, `:5213-5217`) or when the reader scrolls (`:2799`). A 30 s timer remains only as a safety net.
- **P2-1, focus:** focus goes to the board header when the focused row leaves the board (`ui/app.py:5179-5181`). Covered by `tests/test_why_card_ui.py:461`.
- **P3s:**
  - zero-fraction test at `tests/test_why_card.py:720` (it kills the old M2 mutant)
  - real-payload calendar test at `:616`
  - fixture `_fixture_note`
  - "momentum" added to BANNED

## Test runs

| Run | Mode | Result |
|---|---|---|
| Card tests | offscreen | 108 passed |
| Card tests | native | 108 passed |
| Files `test_[a-v]*` + card tests | offscreen | 5 failed, 3312 passed |
| Files `test_[a-v]*` + card tests | native | 4 failed, 3313 passed |

No card test failed in either slice, so the order dependence is gone.

## Failures not caused by the branch

Checked on origin/master 71c078d, offscreen only. The nested repos were symlinked from the branch worktree for that check.
- `test_ci_pins[macro]` and `test_ci_pins[playmaker]`: this worktree's nested repos are stale.
- `test_legal_copy` playmaker notice: same cause.
- `test_shadow_ui::test_h3_a_look_number…`: depends on the date, and fails on master too.
- `test_health::test_the_topic_never_appears_in_any_output`: flakes under load. It passes when run alone.

## Mutants
- New restore and focus logic: 4 of 7 killed.
- Survivors:
  - mutant 4: `actionTriggered` hookup removed
  - mutant 5: `hi > target` boundary
  - mutant 6: wanted position not cleared
- All three are P3 test gaps, tracked in TODO.md.

## Not verified
- The builder's full-suite numbers (3,359 passed / 4 failed, both modes). QA did not re-run the full suite, by scope.
- Coverage.
- Native mode on master.
- Success measure 4, which is pending the owner.
