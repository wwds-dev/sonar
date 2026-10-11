# SONAR closing UX review: v2.180 (HEAD 001e0e4), 2026-10-11

Reviewer: `ux-designer`. Question: do the UI changes since `docs/audit/ux.md` (v2.149) fix its
findings, and does the UI match `docs/specs/v1-product.md`? No code was changed. Only this file was written.

## Playbook status
`docs/playbooks/ux-designer.md`: `status: baseline`, `last-reviewed: 2026-10-10`. It is a seed
with no current practice recorded, so it gave no standard beyond `AGENTS.md`. The review used
the audit's own checklist, WCAG-style checks (focus, timing, contrast, target size) and the
spec's honesty rule. Treat the playbook as stale.

## Method and evidence
- Read committed HEAD only (`git show HEAD:ui/app.py`, `ui/tabs.py`, `ui/words.py`,
  `sonar/calibration.py`, `sonar/engine.py`, `sonar/core.py`). Line numbers below are
  **HEAD:ui/app.py** unless a file is named. The worktree's uncommitted `ui/app.py` edits (27
  lines) were ignored, so working-tree line numbers can differ slightly.
- Exported HEAD with `git archive` into the session scratchpad (outside the repo) and rendered
  it offscreen with the real stylesheet, network blocked, empty data dir, at 1280x775 and
  1500x775: all 8 pages, a refused trade, a successful trade (stubbed `Live.trade`) to see the
  toast, an `AssetRow`, and the protocol checkbox. These are first-run states. Screenshots are
  in the scratchpad (`.../scratchpad/ux_closing/shots/`), not in the repo.
- Not verified: live-data states (stale rows, failed polls were read from code, not seen);
  native macOS font rendering (offscreen uses a fallback face, so clipping findings are
  hedged); VoiceOver; HiDPI; the 8 s toast timing by hand; whether `docs.html` still agrees
  with the rail after the Lab move.

## Scorecard against `ux.md`
| ID | Was | Now | Evidence |
|---|---|---|---|
| U-1 status line hidden | P0 | **Fixed**, with a gap (C-2) | `_set_status` mirrors to `statusBar()` when the rail is folded (`app.py:3924-3932`); seen at 1280: "starting - first poll can take a moment" at the foot |
| U-2 blank panes | P1 | **Fixed** for Screener, News, My trades. Not Big picture (C-9); no error state (C-1) | `ASSETS_LOADING` 1613, `BOOK_EMPTY` 1617, `HEADLINES_LOADING` 1619; seen in 1280 shots |
| U-3 no start here | P1 | **Fixed** (small gaps, C-15) | `_start_card` 2167-2195, dismissal in `onboarding.json` 2197-2214; seen |
| U-4 keyboard / AT | P1 | **Partly fixed**: Cmd-1..8 only (C-3) | shortcuts 1155-1158; `PlainTabBar` still `focusPolicy` 0 (measured), no `keyPressEvent`, zero `setAccessibleName`/`QAccessible` in `ui/` |
| U-5a practice-money cue | P1 | **Fixed** | "Practice money only" chip in the page header, every page (1262-1267) |
| U-5b edge cell | P1 | **Partly fixed** | edge value is MUTED until `model_better` (3507-3514); cell is still the biggest boxed figure (1533-1539) |
| U-6 one-click trade | P1 | **Partly fixed**: undo on success only (C-2) | `_toast` 3934-3945; refusal shows no toast (3406) |
| U-7 jargon | P2 | **Mostly fixed** in Screener, Lab, Sports, Macro captions; residue (C-13) | `STAT_WORDS` 382, `CONTROL_WORDS` 418, `PRACTICE_CAPTIONS` 430 |
| U-8 "129 markets" | P2 | **Not fixed, now in one more place** | 1129 subtitle, 1613 loading text |
| U-9 Practice subtitle clipped | P2 | **Not fixed**, seen clipped at 1280 (C-6) | `1280_6_Practice.png`; text at 1146-1150 |
| U-10 BTC model buried | P2 | **Resolved by design**: it is Lab now | rail group, `tabs.py:85-94` |
| U-11 tooltip-only | P2 | **Partly fixed**: Macro/Sports captions are words now; the Screener column explanations are still tooltip or heading links | 382-414 |
| U-12 8 pt text | P2 | **Not fixed**: 46 `text(8)`/`figure(8)` call sites; News paragraphs still 8 pt grey | 1667-1693, 1716-1740 |
| U-13 promise phrasing | P2 | **Partly fixed**: Sports renamed ("biggest price gap"); two remain (C-7) | 632, 762-763, 1686 |
| U-14 rail footer | P3 | **Not fixed**: button still reads "Wording: plain"; "Test plan" still on the rail | 3311, 1295-1304 |
| U-15 duplication | P3 | **Not fixed** (25,504 / 0.8 / 3.1 at 139 and 1689) | |
| U-16 efficiency | P3 | **Partly fixed**: undo yes; no Screener filter or sort | |

## Match with `v1-product.md`
- **Core path and rail order match the spec exactly.** My investments, Screener, News, My trades,
  Big picture, Learn; Practice and Sports follow under a LAB group (`app.py:1124-1154`,
  `tabs.py:85-94`). Seen at 1500 with a "LAB" label and a gap.
- **"Never says which way anything will go"** holds everywhere except one sentence. The Practice
  header says it is "the one place SONAR says which way something goes" (1146-1150) (C-6).
- **"Reports truthfully whether the score kept to its odds"** is on the first screen: "IS THE
  SCORE RIGHT?" with the verdict "Not enough resolved positions yet - no claim either way."
  (seen). That is the right sentence. It is not the primary figure (C-10).
- **"Others later" / first-run help** is met by the start card and the loading texts.
- **Honesty posture:** I found no copy that asserts edge, profit or certainty as a result. Phrases
  that can be read that way are listed in C-7. The wording of the verdicts is conservative.

## Findings (new or still open), ranked
No P0.

### P1
**C-1 (Visibility of system status / error messages): a failed poll reads as "loading", and it
freezes the Screener and Big picture.**
`refresh()` returns early unless the BTC snapshot is `live` (`app.py:3464-3474`), *before*
`_refresh_cards` and `_refresh_macro` (3477-3478). A poll exception sets
`snapshot = {"status": "error", "detail": ...}` (`sonar/core.py:858`). The UI then prints
`error - first poll can take a moment` (3473) and never shows `detail`. The Screener keeps its
placeholder "Fetching prices for 129 markets - the first scan takes about a minute." (1613)
indefinitely. The core path (notability scanner) is gated on an experiment's feed. Read-only
(second window, cannot follow) takes the same early return. The placeholder added for U-2 is
now a false statement when it lasts more than a minute, and nothing says the fetch failed.
Verified by reading code; the error branch was not run live. **Fix:** draw the Screener and
Macro from `assets` independent of `snap["status"]`; show `detail` for `error`; after N minutes
the placeholder becomes "Still no prices - [reason]".

**C-2 (Visibility / error recovery): a refused trade is invisible after one second, and gets no
toast.** `_trade` writes `"⚠ ..."` to the status line (3403) and creates a toast only on success
(3406). `refresh()` runs every `REFRESH_MS = 1000` (line 63) and overwrites the status line
(3488). Measured: after a refused trade the status was `⚠ unknown symbol AAPL - paper money
only`; after one `refresh()` it was `starting - first poll can take a moment`. A user who clicks
Buy and looks away sees nothing, which is the U-1/U-6 failure again for the failure path. The
same applies to a failed Close (3414) and to "applying - rescanning..." (3332).
**Fix:** a ⚠ toast (no Undo) held for the same 8 s, or a status line that is sticky for a few
seconds before `refresh()` may overwrite it.

### P2
**C-3 (Accessibility / Flexibility): the rail is still mouse-only, Undo is mouse-first, shortcuts
are undiscoverable.** `PlainTabBar` is a painted `QWidget` with mouse handlers only
(`tabs.py:50-176`); measured `focusPolicy() == 0`; no accessible names anywhere in `ui/`.
Cmd-1..8 (1155-1158) help, but nothing on screen, in `README.md` or in `static/docs.html` says
they exist. The collapsed rail is icons plus hover tooltips. Undo is a `QPushButton` at the end
of the tab order, with no Cmd-Z, on an 8 s timer (`TOAST_MS`, 3896) that is not paused by focus
or hover (WCAG 2.2.1 spirit). Heading links (`HelpHeading`, 232-267) are still clickable labels.
**Fix:** a focusable rail with arrow keys, an accessible name per item, a shortcuts line in
Learn and the tooltip, Cmd-Z bound to the toast while it is up, and a timer that pauses on
hover/focus.

**C-4 (Consistency / label fit): the "AI note" button is clipped.** The button is fixed at 44 px
(`app.py:705`). "AI note" measures 41 px of text; it rendered as "l note" in the offscreen face
(`scratchpad/.../shots/row.png`). The code comment at 703-704 names this exact failure. Native
macOS rendering not verified, but the margin is 3 px. **Fix:** widen to about 56 px or make the
actions column 150 px.

**C-5 (Visibility): warnings and stale/error states have no visual weight.** The status line is
9 pt `faint` grey (`app.py:1311`, `_bar_status` 3906); "⚠ no successful price poll for 12 min"
looks identical to "starting...". The one stale-data warning in the app is the quietest text on
screen. **Fix:** colour ⚠ messages (`DOWN`/`GOLD`, with the glyph, not colour alone) and use
10 pt.

**C-6 (Honesty / Layout): the Practice header is clipped and contradicts the spec.** Seen at
1280: the header sentence (1146-1150) is cut off by the card below (carried over from U-9). It
ends "...the one place SONAR says which way something goes", while the spec says the app "never
says which way anything will go". The model is an experiment with a published Brier line;
the sentence should say that. **Fix:** "Test claims on real history, call setups blind, and watch
an hourly bitcoin model scored against Polymarket." One line.

**C-7 (Honesty): three phrases still read as outcomes or instructions.**
(a) Plain Screener cell "win 2x the risk" over "40% of the time" (632-634) sits in the column
people scan; it is a plan, not a result. Use "target 2x the stop" / "reaches target 40% of the
time". (b) News cards give "in 123.45 / target / stop" with Buy and Short under the heading "WHAT
THE NEWS IS POINTING AT" (1686) and tooltips "Sell here." / "Exit here if it goes wrong." (762-763)
in the imperative. Use "where the news is unusual today" and "a plan would look like...". (c) The
Start card says "pick a row marked 'worth a look'" (2178), but no row is marked; every row has a
score. Say "pick a market with a high Worth a look score".

**C-8 (Recognition): at the tested minimum the Lab demotion is not visible.** Collapsed, the rail
paints a hairline between groups and no heading (`tabs.py:185-187`), and two bare icons (flask,
trophy) (seen at 1280). The structure the spec asks for ("demoted, under LAB") exists, but a
new user at 1280 cannot tell the two icons from the main path. **Fix:** a tiny "LAB" caption
under the line, or a tooltip on the line.

**C-9 (Visibility): Big picture has no first-run state.** Before the engine is `live` the
page is dashes and an empty bar (seen). `_refresh_macro` (3606-3618) is the only place that says
"Loading the macro regime..." and it is reached only after the C-1 gate.

**C-10 (Information hierarchy): the biggest figure on the landing page is the one the page says
cannot answer the question.** Profit/loss now is 24 pt in the one highlighted cell
(2003-2005; comment at 1965 "the profit or loss is the biggest, because it is the question").
Four lines below, the grading panel says "profit cannot grade it, because a coin-flip position's
profit is luck" (2162-2164). With protocol mode on, the page opens on a coloured +$ or -$ figure
generated by coin flips. This does not state an edge, but the visual order invites reading the
P&L as the verdict. The spec's core job is the second. **Fix (design, not code):** make the
calibration verdict the primary figure (size and position), keep P&L at figure size but not
boxed, and caption the P&L "includes coin-flip trades" when protocol positions exist.

**C-11 (Accessibility): the unchecked checkbox is almost invisible.** `theme.py:197` styles
`QCheckBox` text but not `::indicator`; the unchecked box renders as a dark square on the panel
colour (seen on My trades "test the score automatically" and the Practice options). The
protocol switch changes what the book does (up to 10 paper trades a day) and its state is hard
to see. Native macOS rendering not verified. **Fix:** an explicit indicator with a 1 px MUTED
border and a filled UP state.

### P3
- **C-12 Toast and status bar.** At 1280 the message appears twice in the same bar (status plus
  toast) and the toast is truncated at the right edge with Undo flush against it (`toast_1280.png`).
  At 1500 the bar appearing and disappearing changes the window's content height, and the rail's
  status label is clipped at the bottom (`toast_1500.png`). The status text sits at x=0 with no
  padding. Suggest: toast replaces status while shown; reserve the bar's height; add padding.
- **C-13 Jargon residue in plain mode.** News header: "the blended score's measured IC is
  negative" (1674). Landing verdict: "rank IC +0.21, 3.4 sigma" and "rank correlation"
  (`calibration.py:205-207`, `app.py:2137`). My trades table: `n=`, `hit`, `advertised`
  (1942-1943) while the landing page says "closed / won / the plan promised" for the same data.
  Backtest output (3380-3394). "Protocol mode is on/off" (2154-2161) in the landing grade
  panel; the checkbox itself says "test the score automatically" but does not say it opens up
  to 10 random paper trades a day.
- **C-14 Literal markup.** `*when*` shows with its asterisks (`app.py:1739`, seen) and so does
  `Hit rate *falls* as the score rises` (`calibration.py:207`).
- **C-15 Start card.** Plain-only (not part of wording flow), cannot be brought back after "Got it",
  no button to the Learn guide (U-3 asked for one); the bankroll is shown, but only below it
  ("started with $10,000"). First-run News header shows "0 headlines - 0 sources - 0 press blocs
  - 0% state-directed" (1808), which reads as data.
- **C-16 Naming.** The rail shows "Practice / LAB" under a "LAB" heading (duplicate), and "Practice"
  collides with "Practice money" (the whole app's mode). Suggest renaming the tab "Hourly
  model" and dropping the second name "Lab".
- **C-17 Knobs on pages they do not touch.** "How much risk" and "How long would you hold it?" are
  shown on Learn, Sports and Practice (header slot, `tabs.py:340-342`), where they do nothing.
- **C-18 Verdict wording.** "Results match the advertised odds almost exactly, which is what no
  edge looks like" (`calibration.py:213-214`, `engine.py:593-594`) is a claim of absence from n >=
  20 with a 5-point band. The wording elsewhere is "not detected, not absent". Also the edge
  cell turns coloured whenever `model_better` (2 standard errors, `engine.py:581`) is true on any
  tick; a repeated look at an accumulating sample will cross 2 SE by chance. For
  `model-validator`; flagged here because it is the UI's only colour-coded disagreement.

## What works (keep)
- Status at any width with a window bar; "Practice money only" chip on every page.
- Loading and empty texts that say what the thing is waiting for (Screener, News, My trades),
  and the "IS THE SCORE RIGHT?" empty state: "no claim either way".
- Start card: three steps, plain, honest first sentence; dismissal persists with a memory fallback.
- Undo toast logic: refused after price moves, never touches the graded record (spec t1-10).
- Plain captions for Macro and Sports (`STAT_WORDS`); `lab_captions` hidden in expert mode.
- Edge value held at MUTED until it is earned; "AI note" instead of "Read"; "Buy/Short" tooltips
  say practice money.
- Contrast unchanged from the initial audit (AA or better); signs and words, not colour alone, in
  rows. Not re-measured; `theme.py` values at HEAD are the same hex as audited (INK `#edf2f7`,
  MUTED `#b0bdca`, FAINT `#8494a3` on `#12171f`/`#1a212c`).

## Suggested order
1. C-1 and C-2 (state bugs on the core path; small).
2. C-4, C-5, C-11 (visible defects).
3. C-6, C-7, C-10 (copy and hierarchy, spec first with `product-manager` for C-10).
4. C-3 (accessibility pass).

## Verdict
The change set does what the owner approved: the status line no longer vanishes, a first launch
says where to start and what each page is waiting for, a misclick can be undone, the rail follows
the v1 core path with Practice and Sports demoted under LAB, and the plain wording now reaches the
Screener, Lab, Sports and Macro. I found no P0 and no copy that claims an edge, a profit or a
certainty; the wording of the verdicts is conservative and the edge cell is muted until it earns
its colour. It is not yet closed as a UX fix: two P1 state problems remain on the core path (a
failed poll is shown as "first poll can take a moment" while the Screener reads "Fetching prices"
forever, and a refused trade's warning disappears within a second with no toast), keyboard and
accessibility work is still one shortcut set, and U-9, U-12, U-13 (partly), U-14 and U-8 are
untouched. The landing page's largest figure is still profit and loss, which the page itself
says cannot answer the question the product exists for. I would accept the build for the 30-day
run if C-1 and C-2 are fixed or deferred in writing by the owner; none of the rest blocks it.
