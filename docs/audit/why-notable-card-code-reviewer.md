# why-notable-card: code review

- Date: 2026-11-18
- Role: code-reviewer (read-only; not the author)
- Branch: claude/build-why-notable-card @ 3435566
- Reviewed against: docs/specs/why-notable-card.md (Design, Architect A1–A6, copy decisions) and the invariants in app-context
- Playbook: docs/playbooks/code-reviewer.md, status current, last reviewed 2026-10-14

Verdict: one P1 (a regression on the existing board), two P2, four P3. No P0.

## P1

### P1-1: every Screener score cell paints a dark box (`ui/app.py:1453-1468`)
- The old holder was `QWidget#cell`, which `ui/theme.py:138` makes transparent.
- `ScoreCell` is `QFrame#scorecell`, and its stylesheet sets only a border. It therefore inherits the app-wide `QWidget { background: BG }` rule (`ui/theme.py:127`). This is the same bug recorded at `ui/theme.py:131-136`.
- Measured offscreen under `theme.STYLESHEET` inside `QFrame#panel`: ScoreCell renders `#12171f` (BG); the old holder rendered `#1a212c` (PANEL).
- Result: all 129 rows show a dark rectangle behind the score and bar.
- The card's points holder `left = QWidget()` (`ui/app.py:1557`) has the same problem.
- Fix: add `background: transparent;` to the `QFrame#scorecell` rule, give `left` the object name `cell`, and add a pixel test.

## P2

### P2-1: the expert line's arithmetic often does not multiply out (`ui/why_card.py:335`)
- `comp` is printed to 2 dp, but the product uses the 3-dp value.
- In the fixture, 158 of 516 expert lines show wrong arithmetic. Example: BABA `0.97 × 0.30 = 29.2`.
- Fix: print `{c:.3f}`, or compute the product from the 2-dp value shown. Add a test that every expert line multiplies out.

### P2-2: the score cell is not announced as a control (`ui/app.py:1453`)
- Its accessible role is `Role.Border`, so VoiceOver reads it as a frame.
- Fix: give it the `QAccessible.Button` role through an accessible-interface factory, and add a test on the role.

## P3

- **P3-1, auto-repeat** (`ui/app.py:1482-1487`): holding Space or Enter toggles the card several times. Fix: ignore events where `ev.isAutoRepeat()` is true.
- **P3-2, share-only sentence next to non-zero points** (`ui/why_card.py:211,274-276`): a non-share row with catalyst 1.0 shows `20 of 20` beside "never score here". This cannot happen today. Fix: have the test (`tests/test_why_card.py:405`) assert that points are 0, and log a warning in that case. Domain-finance raised the same item.
- **P3-3, "Rose 0.0%"** (`ui/why_card.py:251`): the verb follows the unrounded sign. Fix: write "Moved" when the rounded value is 0. Domain-finance raised the same item.
- **P3-4, focus lost after a scan** (`ui/app.py:5118`): `_why_snapshot` restores focus only on rows whose card is open. Fix: record focus on any score cell by symbol.

## Checks with no finding

- **`sonar/assets.py`:** only literals are replaced by constants with the same values. Score and ranking are unchanged.
- **Largest-remainder bounds hold.** The fallback shows 1-dp points.
- **Ranks** are competition ranks on raw cross-sectional keys within the class. The sort order matches the spec.
- **Spec states are covered:** missing part, empty comp, absent catalyst, undated headlines, class of one, stale line.
- **No direction, profit or certainty wording.** There is no `sonar.llm` path. All text goes through `label()` (PlainText). Headline titles are never shown, and source names come from the fixed feed table.
- **Threading:** everything runs on the GUI thread from `_refresh_cards`. No new threads or cross-thread signals.
- **Test change:** `tests/test_poll_error_state.py` is not weakened. `FakeRow` takes `**kwargs` only for the new `on_why` and `why_open` arguments.
- **Test quality:** tests assert behaviour, but they miss the pixel (P1-1), role (P2-2) and arithmetic (P2-1) checks.
- **Learn paragraph** matches the spec text.

## Tests run

```
PYTHON=/Users/as/Documents/lab/active/sonar/.venv/bin/python QT_QPA_PLATFORM=offscreen TEST_BUDGET_S=300 ./run-tests.sh tests/test_why_card.py tests/test_why_card_ui.py tests/test_poll_error_state.py -q -p no:cacheprovider
```
- Offscreen: 111 passed in 35.47s.
- Native: 111 passed in 32.27s.

Not verified:
- the full suite
- coverage
- the "17 of 17 mutants killed" claim
- the native-build look of the score cell (the dark box was measured offscreen)
- real VoiceOver behaviour

## Combined with the domain-finance consult

See docs/audit/why-notable-card-review-domain-finance.md for P1-1 (the earnings-window wording) and P1-2 (the Learn page's "something is happening").

Before merge, these must be fixed or deferred by the owner: CR P1-1, DF P1-1 and DF P1-2.
