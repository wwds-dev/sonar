# SONAR UX audit — 2026-10-10 (v2.149)

Auditor: `ux-designer`. Scope: all eight destinations, first run, hierarchy, language,
states, accessibility, honesty of wording. No code was changed.

## Method and evidence
- Read `ui/app.py`, `ui/tabs.py`, `ui/theme.py`, `ui/words.py`, the README tab table and
  `static/docs.html` (headings and tab table).
- Rendered every tab offscreen with the real stylesheet (`QT_QPA_PLATFORM=offscreen`, network
  blocked, an empty data directory, so these are **first-run, no-data** states) at 1280x775
  (the documented minimum) and 1500x775. Screenshots are in the session scratchpad
  (`.../scratchpad/shots/{1280,1500}_N_*.png`), not in the repo.
- Contrast computed from `ui/theme.py` hex values: INK 13-16:1, MUTED 7.7-9.8:1, FAINT
  4.7-6.0:1, UP/DOWN 6.3-8.1:1 on all panel backgrounds. All pass WCAG AA; contrast is **not**
  a problem. Size is (see U-12).
- Not verified: behaviour with live data (stale/failed fetch states were read from code, not
  seen), VoiceOver, high-DPI, real macOS font rendering (offscreen uses a fallback face).

## Summary
The honesty posture is strong and consistent: every direction-adjacent figure carries a
disclaimer, the board is "worth a look" not "will go up", `ui/words.py` gives a real plain mode.
The serious problems are structural, not copy: at the tested minimum width the rail folds and
**takes the only status line and the practice-money disclosure with it**, the first run is a
screen of dashes and blank panes with no guidance, and the navigation is mouse-only.

| ID | Pri | Heuristic | Finding |
|---|---|---|---|
| U-1 | P0 | Visibility of system status | Status line (trade confirmations, errors, read-only mode) is hidden below 1420px |
| U-2 | P1 | Visibility / Recognition | Blank panes on first run: Screener, News, My trades show nothing and no "loading" |
| U-3 | P1 | Help and documentation | First run has no "start here"; Learn is last on the rail |
| U-4 | P1 | Accessibility | Rail and help headings are mouse-only; no shortcuts, no focus, no accessible names |
| U-5 | P1 | Consistency / Honesty | "practice money only" disclosure vanishes with the rail; edge-ish emphasis on BTC "edge" cell |
| U-6 | P1 | Error prevention | Buy, Short, Close act in one click with feedback only in the hidden status line |
| U-7 | P2 | Match with real world | Jargon left in plain mode (Brier, coverage, voided, IC, quintile, protocol mode, EV, Kelly) |
| U-8 | P2 | Consistency | Hard-coded "129 markets" contradicts the risk filter and the status count |
| U-9 | P2 | Layout | Practice subtitle clipped at 1280 |
| U-10 | P2 | Info hierarchy | The one place SONAR states a direction is at the foot of a long scroll on "Practice" |
| U-11 | P2 | Recognition | Key explanations live only in tooltips (Macro, Sports, Screener columns) |
| U-12 | P2 | Accessibility | 8pt text is used for load-bearing content |
| U-13 | P2 | Honesty | "win 2x the risk" and "STAKE" / "best edge" phrasing |
| U-14 | P3 | Match with real world | Wording button names the current state, not the action; "Test plan" is a developer control |
| U-15 | P3 | Consistency | Copy duplicates research numbers in three places; README mentions a Docs button that no longer exists |
| U-16 | P3 | Flexibility | No undo/confirm for Close; no keyboard "next tab" |

## P0

### U-1 — The status line disappears at the documented minimum window  (Visibility of system status)
`ui/app.py:76` `RAIL_COLLAPSE_BELOW = 1420`; `ui/tabs.py:383-392` `set_collapsed` calls
`widget.setVisible(False)` on every rail chrome widget, which includes the footer that owns
`self.status` (`ui/app.py:1246`). 1280 is the tested minimum, so at the minimum — and on any
13-14" laptop at default size — the following are invisible: "starting…" / "first poll can
take a moment" (`app.py:3248`), `⚠ another engine is running` read-only notice (`app.py:3244`),
every trade result and failure (`app.py:3184`, `3192`: "✓ opened…", "⚠ no price"), the
"documentation not found" error (`app.py:1421`), and the "following the engine" line
(`app.py:3263`). Confirmed in `1280_*` screenshots: the rail is icons only, nothing at the foot.
A user who clicks Buy sees nothing happen on the Screener; in read-only mode the whole app looks
frozen with no explanation. This is exactly the failure `app.py:3197-3201` says it was written
to avoid.
**Fix:** move the status line out of the rail into a thin window-level status bar
(`QMainWindow.statusBar()` or a footer row under the stack) that never collapses; keep the
rail purely navigation. Interim: collapse hides everything *except* the status label, or show
an in-header toast for ⚠ results. Add a test that `status.isVisible()` at 1280.

## P1

### U-2 — First run: three destinations are empty rectangles  (Visibility of system status)
Screenshots `1280_1_Screener`, `1280_2_News`, `1280_3_My_trades`: the Screener list is a blank
bordered box under column headings; News has three empty boxes ("nothing yet" for alerts);
My trades shows dashes and an empty table. `_rebuild` (`app.py:3333`) only writes an empty
message after the first snapshot, so before it there is no loading text, and nothing says
"loading 129 markets, first scan takes about a minute". A blank list is indistinguishable from
a broken one, and first impressions are formed here. The landing page does it better
("no account history yet — the first scan writes the first point").
**Fix:** each list gets an initial placeholder ("Fetching prices — the first scan takes about
a minute. 12 of 129 so far."), driven from `snap["status"]`; My trades gets "No trades yet —
open one from the Screener."; News columns "Waiting for the first headlines…". Also replace
the bare em-dash figures with "—" plus a muted "no data yet" caption on the landing strip.

### U-3 — No "start here" on first run  (Help and documentation)
The app opens on My investments, a page of dashes whose only guidance is "buy or short on the
Screener". Nothing says: this is paper money, how much you start with, what to do first, that
a manual exists. Learn is the last rail item and has no second name (`app.py:1097`); its
subtitle ("start at §1") is only visible on that tab. The rail's collapsed state removes even the
masthead. Nothing on the landing page states the starting bankroll, so "Profit / loss now" has no
reference.
**Fix:** a dismissible first-run card at the top of My investments (3 lines: "This is practice
money — you start with $X. 1) open Screener, 2) press Buy or Short on anything, 3) come back in a
few days and check 'Is the score right?'" plus a "Read the 2-minute guide" button to `§1`).
Persist dismissal next to `wording.json`. Show the starting bankroll under "Account value".

### U-4 — Keyboard and assistive-technology access is essentially absent  (Accessibility / Flexibility and efficiency)
- `PlainTabBar` (`ui/tabs.py:49`) is a bare `QWidget` with only mouse handlers
  (`mousePressEvent` `tabs.py:125`); no `setFocusPolicy`, no `keyPressEvent`, so the entire
  navigation cannot be reached by Tab or arrows. No accessible role/name: a screen reader sees
  an unnamed widget, and the painted icons-only collapsed rail has no text at all (tooltips
  need hover).
- `grep` finds zero `setAccessibleName`, `setShortcut`, `QShortcut`, `setBuddy`, `setTabOrder`
  in `ui/`. No Cmd-1..8 to switch tabs, no Cmd-F in Learn, no shortcut for the wording toggle.
- `HelpHeading` (`app.py:231`) and the Screener column headings are clickable `QLabel`s
  (`mousePressEvent` `app.py:263`): mouse-only, and styled as links only by colour.
- Painted widgets (tiles, curves, lattice, depth, equity, ComponentBar) in `ui/charts.py` expose
  one tooltip in total (`grep -c setToolTip ui/charts.py` = 1); their numbers are not available
  as text.
**Fix:** make the rail a focusable list (arrow keys, Enter, `setAccessibleName("Navigation")`,
per-item names via `QAccessible` or replace with a `QListWidget`/`QToolButton` group);
add Cmd-1..8 and Cmd-[ / Cmd-]; make heading links `QPushButton` flat or give them
`Qt.StrongFocus` + key handling; set accessible names/descriptions on every Stat (caption +
value) and on each painted chart summarising its data in words.

### U-5 — Honesty cues are layout-dependent, and one emphasis can read as edge  (Consistency and standards)
(a) "practice money only — nothing here places a real order" lives only in the rail header
(`app.py:1114`), hidden whenever the rail folds. Per-row tooltips repeat it but tooltips are
undiscoverable. The page header, which is always present, does not say it.
(b) On the hourly model (Practice, foot) the "edge" cell is deliberately the largest, boxed
figure on the screen (`app.py:1466-1473`, comment "the only number in the app that is a
disagreement with a market"), formatted `+3.2¢` and coloured by side (`app.py:3278`). The caption
is softened to "we disagree by" in plain mode, but a bold, coloured, signed cents figure beside
"our odds it rises" reads as "this is worth 3.2 cents". The model-vs-market Brier line that
actually says whether to trust it is a small 10pt grey line below the fold of that panel.
**Fix:** (a) put a permanent "Practice money" chip in the page header next to the two knobs, or in
the new window status bar from U-1. (b) Pair the edge figure with its verdict in the same cell
("model has not yet beaten the market: 0.2491 vs 0.2503, 214 hrs"); colour the figure neutral
until the Brier verdict is significant; promote the verdict line to the same size as the figures.

### U-6 — One-click Buy/Short/Close with feedback in a hidden place  (Error prevention / Visibility)
`_trade` and `_close_position` (`app.py:3179-3194`) execute immediately; the only feedback is
the status text (see U-1) plus a redraw of the board. Practice money lowers the stakes, but a
mis-click on a 44px "Short" button next to "Buy" and "Read" (`app.py:752`, fixed width 44,
adjacent, same style) is easy, and with U-1 the user may not realise a position opened, or
opened twice. The tile on My investments is the only other evidence.
**Fix:** after Buy/Short show a transient confirmation on the row itself ("Bought AAPL —
see My investments" with an Undo for 10 s), and separate Read from Buy/Short visually
(spacing or a divider); Close asks nothing today — add undo rather than a modal.

## P2

### U-7 — Jargon survives in plain mode  (Match between system and the real world)
Plain wording covers the Screener, headers and `STAT_WORDS` (`app.py:381`), but not:
- `app.py:3314-3322` model-vs-market line: "Brier 0.2491 vs 0.2503", "coverage 98%",
  "voided", "STALLED", "last settle". Not in `STAT_WORDS` either: "win rate", "profile".
- Practice: "IC", "quintile spread", "leave-one-out", "KEEP / WEAK / DROP / INVERTED",
  "Implied drift σ" (`app.py:2534`), "include attention", "include earnings history (US equities,
  via EDGAR)", "Step (bars)", "Horizon (days)" with no explanation next to the control.
- My trades: "protocol mode" checkbox (`app.py:1776`) and "run backtest"; the term "protocol"
  is never defined where the checkbox sits.
- Sports: "margin", "fair", "book spread", "best edge", "EV / unit", "stake" captions
  (`app.py:2740-2775`) are not in the wording map; "Kelly" appears in a tooltip only.
- Macro: "10Y", "CURVE", "FED FUNDS", "VIX", "REAL 10Y", "CPI Y/Y" are captions with the
  explanation in the tooltip only (see U-11).
- "Short" and "Read" as button labels: "Short" is unexplained to a newcomer (tooltip only);
  "Read" is ambiguous (a language-model commentary).
**Fix:** extend the plain/expert pair to every caption (expert keeps the term); each Practice
control gets a one-line caption beneath; rename "Read" to "AI commentary"; rename "Short" to
"Short (bet it falls)" or keep word and add the gloss as secondary line like the columns do.

### U-8 — "129 markets" is hard-coded and wrong under the default profile  (Consistency)
`app.py:1077` subtitle, `app.py:153` tooltip. The Moderate profile hides markets above
`max_daily_vol=0.04` (`sonar/risk.py:81`), and an empty-result message exists
(`app.py:3333`), so the visible count is usually below 129; the status line reports the real
`assets["n"]` (`app.py:3265`), which U-1 hides. A user counting rows will conclude something is
missing.
**Fix:** subtitle generated from the live count: "112 of 129 markets shown for 'calmest only';
change risk to see all". Show the number of hidden markets on the board.

### U-9 — Practice subtitle is clipped at 1280  (Aesthetic and minimalist design / layout)
`1280_5_Practice.png`: the header sentence (`app.py:1089-1093`, 26 words) wraps to three
lines in a header sized for two; the third line is cut ("...says which way something goes" is
partly overdrawn by the card below). The sentence is also the only place the page says it holds
the direction-asserting model.
**Fix:** shorten to one sentence ("Test the app's claims on real history, make your own calls
blind, and watch the hourly BTC model."), and give `_header` a layout that grows with
`heightForWidth`.

### U-10 — The one directional model is buried  (Information hierarchy)
README: Practice is the only tab that "asserts a direction: yes", yet it sits last-but-two on
the rail, mixed with two simulation forms, and the hourly model is at the foot of a scroll
area (`app.py:1089`, `_terminal_tab`). It was the landing page until Oct 2026 and users who
wanted it must now know to scroll. Conversely a first-time user sees the heavy research tooling
(IC, quintiles) before anything simple.
**Fix:** in Practice add a segmented top control "Test history | Make my own calls | Hourly BTC
model" (or three collapsible sections, closed by default) so each starts with its figure; add a
"Hourly BTC model" shortcut to the landing page card.

### U-11 — Key explanations are tooltip-only  (Recognition rather than recall)
The macro, Sports and Screener-cell explanations are good prose but sit in tooltips (e.g.
`app.py:3025-3100`, `2740-2775`, `ASSET_COLS` tooltips `app.py:113-170`). The code comment at
`app.py:113-118` itself notes that hover text "cannot be found by someone who does not know there
is something to hover". Tooltips also do not work with keyboard or touch, and in collapsed rail
mode the rail is tooltip-only too.
**Fix:** a persistent one-line plain gloss beneath each Macro figure ("what the US pays to borrow
for 10 years"), keep tooltip for depth; visible "?" affordance on captions that have a tooltip.

### U-12 — Small type carries real content  (Accessibility)
8pt uppercase `faint` captions (`Stat.cap` `app.py:440`, rail subtitle `tabs.py:182`
`theme.text(8)`, `MacroNote`, News `faint 8` explanations `app.py:1590-1610`, Macro
`faint, figure(8)`). The News "What changed" and "What the news is pointing at" paragraphs —
which carry the research caveats ("over 25,504 setups... no edge") — are 8pt grey, five lines
long (`2_News.png`). Contrast passes but at 8pt on a Retina Mac they are hard to read, and Qt text
does not follow the system text-size setting.
**Fix:** raise the floor to 10pt for any sentence-length text; reserve 8pt for single-word
captions; add a "Larger text" preference alongside wording.

### U-13 — Phrases that can be read as a promise  (Honesty)
- Plain Screener cell: "win 2x the risk" with "40% of the time" below (`app.py:576-583`).
  Out of context "win 2x the risk" reads as an outcome. It is a plan ("target is 2x as far as
  the stop"). Suggest "target 2x the stop" / "reaches target 40% of the time".
- Sports: stat captions "BEST EDGE", "EV / unit", "STAKE" (`app.py:2756-2775`) put an edge and
  a bet size on screen from three books' prices. The tooltip says "0 is the normal answer", the
  caption does not. Suggest "biggest price gap" and "stake (usually 0)".
- News "What the news is pointing at" cards show `in 123.45 / target / stop` with Buy and Short
  buttons (`app.py:690-722`) — a complete trade ticket under a heading that reads as a
  recommendation list, even though the buttons' tooltip says direction is yours. Suggest the
  heading "Where the news is unusual today" and the label "what a plan would look like".
- Landing "IS THE SCORE RIGHT?" is a fair question; keep.
These are mild: the app does disclaim, but the disclaimers are in tooltips/paragraphs and the
captions are what people scan.

## P3

### U-14 — Rail footer controls  (Match with the real world / Consistency)
`app.py:3121` button reads "Wording: plain" — a state, not an action; it is unclear whether
clicking changes it to expert. "Test plan" (`app.py:1231`) is a QA checklist ("acceptance
checklist for signing off a build") in the end-user navigation. **Fix:** "Switch to expert
wording" / "Switch to plain wording"; move Test plan under a Help or developer menu.

### U-15 — Documentation drift and copy duplication  (Help and documentation)
- README:768 says the Test plan button is "next to *Docs*"; the Docs button was removed
  (app.py:1226 comment). `README` row for Learn lists no second name while the rail shows none —
  consistent, fine.
- The figure "25,504 historical setups ... +0.8 ... 3.1" is hard-coded in three user-visible
  places (`app.py:137`, `1607`, plus docs) — if the study is re-run the UI lies. Drive it from
  one constant in `sonar/` shared with the docs build.
- `static/docs.html` heading for §14 is "Playmaker — sports bets" in the contents list
  (`docs.html:99`) and "pricing a sports bet" in the section (`:934`); the tab is called
  "Sports". Align names.

### U-16 — Efficiency and recovery  (Flexibility and efficiency / Error recovery)
No Cmd-1..8; no way to search the Screener (129 rows, no filter, no sort other than score);
Close has no confirmation or undo; the Learn search is a good model (wraps, reports no match).
Add a filter box and sort headers to the Screener.

## What works well (keep)
- Page header with the screen's name, original name and one sentence (`ui/tabs.py:395-415`).
- Plain/expert switch changes vocabulary only, never layout (`ui/words.py`).
- Knobs phrased as questions with tooltips stating what changes and that risk never alters a
  score (`app.py:1160-1190`).
- Age column with colour and a tooltip explaining rotation, `age` never rounds to "0m"
  (`app.py:169-181`); explicit "price that is quietly out of date is unacceptable" stance.
- The Screener banner and its three chips ("Why is it always 40%?") answer the exact first
  questions (`app.py:1275-1285`).
- Empty states on the landing page and replay are specific and tell the next step.
- Colour is never the only carrier: signs (+/-), words ("big swings", "Spike") accompany it.
  Contrast is AA-or-better throughout.
- Learn: manual in-app, search that wraps and reports misses, glossary table in §1.

## Suggested order of work
1. U-1 (status line independent of the rail) — one change that also resolves U-5a and most of U-6.
2. U-2 + U-3 (first-run placeholders and start card) — together the first-run experience.
3. U-4 (rail keyboard/accessibility) and U-12 type floor.
4. U-7/U-11/U-13 copy pass through `ui/words.py`/`STAT_WORDS` (spec first: `product-manager` for
   the first-run card, `tech-writer` for docs).
