# The Plain Language direction

Design record and rules: type, contrast, the plain and expert vocabularies. The rules are enforced by `tests/test_plain_language.py` and `tests/test_wording.py`.

Moved verbatim from `README.md` on 2026-10-10 when the README was cut to what / how / where. Statements here are as of the commit they were written in; the README no longer repeats them.

Chosen 2026-09-22, after the person this app is for said he could not read his
own screener. Three changes, each a rule rather than a taste:

- **Proportional type carries words; monospace carries only code.** Menlo was
  drawing English prose, which it is bad at. `theme.text` is the interface font,
  `theme.figure` is the same face with tabular numerals so a column of prices
  still lines up, and `theme.code` is the real monospace — used in exactly two
  places, both of which take a pasted table whose columns are made of spaces.
- **Contrast is a floor.** `MUTED` and `FAINT` now clear 4.5:1 against the panel
  they sit on; `FAINT` used to measure 1.9:1, which is decoration, not text.
  Raising it exposed a latent bug worth knowing about: every `QLabel` inherited
  the window background from the blanket `QWidget` rule and painted it over the
  panel beneath, which was invisible while the two colours were three points
  apart and became a dark box behind every cell once they were not.
- **The board is written in English.** `MOM` is "Recent move", `VOL` is "Swing
  size" over the words *big swings*, `R:R` and `P(PROF)` are one column reading
  "win 1.5× the risk / 40% of the time", and `CONF` is "Worth a look" with the
  score as a meter whose segments are still the component breakdown. Every row
  carries one plain sentence — "up hard, heavy news" — generated from numbers
  already on the row, and `tests/test_plain_language.py` asserts that sentence
  can never acquire a direction.

**Both vocabularies are available.** The `Wording` button switches between
**plain** (the default, described above) and **expert**, where the columns are
`MOM`, `VOL`, `R:R · P(PROF)` and `CONF`, the ticker is back under each name,
the second lines are gone and the rail shows only the original names — about
a third shorter per row. `ui/words.py` holds the mode and remembers it between
launches. It changes the **vocabulary and the density, never the layout**: same
columns, same widths, same order, which is why the header can be re-captioned in
place and why there is only ever one board to keep correct. A test asserts that
invariant directly.

Headings that name something non-obvious are links: clicking one opens the Learn
tab at the section explaining it, and a test checks every one of those anchors
resolves to a section that exists. The two knobs in the page header are
captioned with the question they answer ("How much risk are you willing to
take?") rather than with the word `risk` in 9pt grey.
