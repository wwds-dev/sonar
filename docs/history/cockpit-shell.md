# The Cockpit shell (GUI round 2)

Design record: why the tabs became a left rail, a page header and a hierarchy on the Terminal.

Moved verbatim from `README.md` on 2026-10-10 when the README was cut to what / how / where. Statements here are as of the commit they were written in; the README no longer repeats them.

Chosen 2026-09-29, from a mockup approved before any code moved. The Plain
Language direction fixed the vocabulary and the contrast; what remained was
structure, and the shell now has one:

- **A left rail carries the eight destinations** instead of a top tab bar —
  both names each, exactly as before (`ui/tabs.py` still paints them, and
  `PlainTabs.add(widget, plain, was)` is still the only way in, which is what
  the docs test greps). The old toolbar's wordmark, version badge and
  practice-money line sit at the rail's head; the Wording and Test plan
  buttons and the status line sit at its foot. `PlainTabs` is no longer a
  QTabWidget — a QTabBar docked West draws its text vertically — but it keeps
  the QTabWidget surface (`count`/`widget`/`tabText`/`setCurrentIndex`/
  `tabBar`) so nothing else had to learn a new API.
- **A page header names every screen**: the destination's plain name, the
  small-caps original, one sentence saying what the screen is (the same
  sentence the rail shows on hover), and — always visible, on every screen —
  the two question-captioned knobs, because risk and horizon shape everything.
  Expert wording drops the sentence, the same density trade the board makes.
- **The rail folds to icons below `RAIL_COLLAPSE_BELOW` (1420pt)** and unfolds
  above it, from `MainWindow.resizeEvent`. Two invariants hold it together,
  both in `tests/test_layout.py`: folded, the window's minimum fits 1280×775;
  expanded, the minimum stays *below* the threshold — Qt stops an interactive
  resize at the layout minimum, so a threshold under the expanded minimum
  would be unreachable and the rail could never fold by dragging. The first
  cut of this shell had exactly that deadlock. Fold state changes painting
  and chrome visibility, never wording or subtitles, and the tests assert the
  round trip. One quirk worth knowing: Qt delivers no resizeEvent to a hidden
  window, so tests drive the fold through `MainWindow._sync_rail()`.
- **The Terminal's six equal stat cells became a hierarchy.** The edge —
  model minus market, the only number in the app that is a disagreement — is
  the largest figure on the screen, in the one highlighted cell; the price
  anchors the left; tau is drawn as a filling hour-bar (`ui/charts.HourBar`)
  as well as printed. The bankroll strip and the model-vs-market Brier line
  share one ledger panel under the equity curve. Same keys, same tooltips,
  same `refresh()` — the arrangement changed, the readouts did not. (Since
  Oct 2026 this whole panel lives at the foot of Practice; see the next
  section.)

The rail's icons are inline SVG strokes tinted per state (`ui/icons.py`) —
not emoji, which bring their own colours and ignore the palette. The window
now prefers 1440×850 and lets `_fit_to_screen` clamp it, so a big display
opens with the names showing and a 13" laptop opens folded.
