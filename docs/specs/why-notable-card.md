# Spec: a "why is this notable" card per instrument on the Screener

- Status: approved (Define); Design done 2026-11-18, awaiting owner review (not a gate: Design has none)
- Owner approval: 2026-11-18, Define ("go with recommendations"); recorded in `docs/foundry/approvals.jsonl`.
  Decisions under "Owner decisions at the Define gate" below.
- Source: `SUGGESTIONS.md` #23 (portfolio review 2026-11-18); `TODO.md` "Approachability — the app is unreadable
  without a finance background". Session-owned slug: `why-notable-card`.
- Skipped at Define: `/radar-check` (no new dependency, tool or data source; copy and one pure function only).
  Domain-finance consult not yet run: it runs once the Design copy is final (decision 6).

## Problem

`TODO.md` records that the owner "cannot read his own screener" and calls that a product defect. The Plain Language
work fixed the headings and added one phrase per row ("down hard, heavy news", `_plain_read`, `ui/app.py:214`). The
score itself is still not explained where it is shown:

- The "Worth a look" cell (`ui/app.py:1600-1621`) shows `75 / 100` and a coloured `ComponentBar`. The only
  explanation of the colours is the bar's hover text (`ui/charts.py:297`), which reads
  `momentum 0.88×0.30  volatility 0.89×0.15  news 1.00×0.35`: expert notation, and hover-only, which `TODO.md`
  already names as the thing a new reader cannot find.
- The column heading tooltip says "The bar underneath splits the score into what produced it" but never names the
  parts in words, their maximum share, or how this row compares with its neighbours.
- A reader cannot answer the question the score raises: "why is Nvidia at the top today and TRON at the bottom?"

## What the code says (premise check, 2026-11-18)

The row named `sonar/scoring.py` and `sonar/model.py`. Neither holds the score: `scoring.py` builds the trade plan
(barrier odds, `1/(1+R:R)`), and `model.py` is the hourly BTC up/down model. The "worth a look" score is
`AssetSuggestion.confidence` in **`sonar/assets.py`**:

| Component | Weight (`_W`, `assets.py:205`) | Raw quantity | Made into 0–1 by |
|---|---|---|---|
| news | 0.35 | matched headlines, recency-weighted (`news.news_signal`, `news.py:349`) | `min(1, cover/2)`: two fresh stories saturate; **absolute**, not standardised |
| momentum | 0.30 | `abs(price change over the horizon window)` (5 days on "This week") | `min(1, abs(mom)/scale)`, then blended 40/60 with a within-class z-score (`crosssection.standardise_raw`, `RELATIVE_MIX = 0.6`) |
| volatility | 0.15 | forecast daily volatility (`volatility.forecast`) | `min(1, vol/0.03)`, then the same within-class blend |
| catalyst | 0.20 | days to the next **earnings** date (`events.catalyst_score`) | 1.0 inside the horizon, decaying to 0 one horizon later; equities only |

`confidence = 100 × Σ weight × component` (`assets.py:552`), computed after the within-class pass, over the rows the
risk filter left on the board. Every input the card needs is already in the `/api/assets` row (`comp`, `momentum`,
`momentum_days`, `volatility`, `lean`, `headlines[].source/age_h`, `catalyst`, `cls`), and within-class ranks can be
computed from the same payload. **The base card needs no new data, no engine change and no model call.**

Differences from the row and related findings:

1. **Wrong files named** in the review (above). No effect on scope.
2. **The direction rule already has a precedent and a test**: `_plain_read` reports the past move with its sign in the
   past tense, and `tests/test_plain_language.py:93` asserts it never asserts a direction. The card extends that rule
   rather than inventing one.
3. **Momentum and volatility are relative to the asset class, news is not.** A card that says "small swings" for
   EUR/USD (0.38% a day, `_swing_words`) while the score gives it volatility points has to explain that the comparison
   is with other currency pairs. This is the single most useful thing the card can teach.
4. **Catalyst can only ever score for equities** (earnings dates are the only event source). For forex, crypto,
   commodities and indices the card must say the category does not apply, not "no event".
5. **A word-list "tone" still exists.** `_rationale` (`assets.py:588`) writes "tone positive/negative/mixed" into the
   payload, and `Live.read` passes `news_sentiment` to the optional LLM read (`core.py:1373`). The Qt UI does not
   display either. The card must not use them (`CONFIDENCE.md` §9 calls the word list unfit). Removing them is out of
   scope (question 5).
6. **Suggestion #10 (volatility component inverted for ranking) is BLOCKED, not decided.** `CONFIDENCE.md` §10a: the
   negative gradient fails the time-block test (5/6, p = 0.22, latest block reversed), so the weight is unchanged, and
   the stated conclusion is that high volatility is right for notability and wrong for ranking winners. The card
   treats it as a component under dispute (wording rule W8).
7. **Catalyst is the only component that passed attribution** (IC +0.040, `CONFIDENCE.md` §13, "sixth study"),
   and the effect is volatility-shaped, before costs, not a direction. The card must not present that as "the proven
   part" (W7).

## User and goal

A retail investor without finance training, the owner first, looking at the Screener and wanting to know why a row
is ranked where it is, without hovering, without the Learn tab, and without being told what to do.

Goal: for any row, one card says in plain words which of the four things put the row where it is, how much each
counted out of its maximum, how the row compares with others of its kind, and what the score does not say.

### Success measure

1. **Test, no model call.** For every row of a recorded `/api/assets` payload (fixture: the 129-row board of
   2026-11-18 12:32, captured in Build), the card is built with the LLM module made to raise if touched; it has one
   line per component (four), its points are whole numbers summing exactly to the score as displayed (largest
   remainder rounding), and every line's facts match the row's numbers.
2. **Test, no direction.** Flipping the sign of `momentum` on any row changes the card in exactly one place, the
   past-tense verb ("rose" / "fell"); every other word is identical. No card on the fixture contains a banned term
   (W3), in plain or expert wording.
3. **Test, wording parity.** Plain and expert cards carry the same numbers and the same footer; only vocabulary
   differs (mirrors the existing column-parity test for the Wording switch).
4. **Owner check (Verify).** The owner opens the card on five rows the QA engineer picks at random on the live board
   and, without opening Learn, says in one sentence each why that row is where it is. Recorded with a screenshot and
   the owner's words. Pass: five of five correct against the card's own numbers.

## Scope / Non-goals

In:
- A pure, templated function from one board row (plus the board, for ranks) to the card's lines. No I/O, no clock,
  no model call.
- The card on the Screener (Assets tab), reachable by a click on the "Worth a look" cell, in plain and expert wording.
- A Learn (`static/docs.html` §5 "The three numbers") paragraph saying the card exists and what it leaves out.
- Tests per the success measure.

Not in:
- Any change to the score, its weights, components or standardisation (#7, #10, `CONFIDENCE.md` §3–§6).
- Any forward-looking statement, forecast, probability, or "what to do". The trade plan column stays where it is.
- The optional LLM read: unchanged, still off by default and button-only. The card never calls it, never shows its
  output, and no model percentage ever sizes a position.
- Headline titles on the card (slice 2, question 4). Slice 1 shows count, sources and ages only.
- The web dashboard (`static/index.html`), the Terminal, Practice, Sports and Lab tabs. Guided Lab (I-15), first-run
  cards (#16) and "what would change an unproven" (#17) stay separate; #16's "notability is not direction" card should
  reuse this card's footer sentence verbatim so the two cannot drift.
- Removing `_rationale`'s tone or `news_sentiment` from the LLM prompt (question 5).

## Design

Designed 2026-11-18 by the `ux-designer`. The card copy (structure, templates, W1–W9, examples) was set at
Define and is kept; this phase fixed two copy conflicts found while checking it (see "Copy fixes at Design") and
adds layout, interaction, states and the Learn text below.

### Card structure (fixed order, every row)

1. **Title line**: `{name} — notability score {score} / 100, ranked {rank} of {n} by this score today (risk filter: {profile})`.
2. **"What put it here"**: four lines, sorted by points (ties in weight order news, move, swings, date), zero lines
   last and greyed. Each line: plain label, `{points} of {max}`, one or two sentences of fact.
3. **"What this does not say"**: the fixed footer, always visible, not collapsible, identical on every card:
   > This score counts what was found in news and price data. It does not say which way the price goes next, or that a
   > trade would make money. In SONAR's own simulated replay of 25,504 past setups, before costs, big moves and news
   > spikes showed no clear link to which way prices went; that test can only rule out large effects.

### Line templates (plain wording)

| Component | Max | Template |
|---|---|---|
| News | 35 | `{k} matched news stor{y/ies} in the last {span} (newest {age} before the scan; {sources}).` + level sentence: Spike → `3 or more stories in the last 6 hours.` · Elevated → `At least one story in the last 6 hours, or 3 in the last day.` · Normal → `No story in the last 6 hours and fewer than 3 in the last day.` · none → `No matched news.` The numbers come from `news_level`, never typed. |
| Recent move | 30 | `{Rose/Fell} {x}% over the last {d} days, the {ordinal}-largest move of {N} {class plural} on the board; the score partly compares moves within the kind and partly with a fixed size. The size counts, not the direction: a fall scores the same as a rise.` |
| Swing size | 15 | `SONAR's estimate of its daily swing is about {v}% ({swing words}), the {ordinal}-largest of {N} {class plural} ("the largest" / "the smallest" at the ends). The score partly compares it with other {class plural} and partly with a fixed size.` + W8 note |
| Earnings date | 20 | equity with a date: `{Earnings label} ({date}): a date on the calendar, not a forecast.` · equity without: `No earnings date within the next {2d} days.` · other classes: `SONAR only tracks company earnings dates, so {class plural} never score here.` |

Class plurals: Equity → shares, Index → indices, Forex → currency pairs, Crypto → cryptocurrencies, Commodity →
commodities. Ranks and N are among rows currently on the board (after the risk filter), which is the set the score
was standardised against.

Expert wording: the same lines with the component value and weight appended (`0.88 × 0.30 = 26.4`), ticker in place
of the name, labels MOM / VOL / NEWS / EARN. Same footer.

### Wording rules

- **W1 Facts only.** Every clause is a number on the row, a rank computed from the board, or a fixed sentence from
  this spec. Nothing is inferred, and no headline text is paraphrased.
- **W2 Tense.** Price movement in the past tense only. No future tense anywhere in the templates (no "will").
- **W3 Banned terms** (test-enforced, matched by stem so inflections are caught, case-insensitive, both wordings, run over every card string, the W8 sentence, the state strings, tooltips and the Learn paragraph; exact allow-list: the footer, the earnings label, the column name "Worth a look"). Added at Design: recommend, advice, advise, pick, top, best, worst, winner, loser, favourite, attractive, promising, hot, trending, bet, invest, hold, avoid, accumulate, outperform, underperform, beat, bottom, rally, surge, soar, plunge, crash, dip, trigger, driver, poised, due, soon, imminent, certain, definitely, proven, reliable, obvious, confirmed, validated, probably, possible, potential, might, must, conf, catalyst. Original list: buy, sell, short, long, bullish,
  bearish, upside, downside, opportunity, signal, edge, profit, gain, win, likely, expect, expected, will, should,
  could, may, breakout, rebound, recover, bounce, oversold, overbought, cheap, expensive, undervalued, overvalued,
  target, chance, odds, probability, confident, confidence, sure, guaranteed, safe, risky, strong, weak, positive,
  negative, tone, sentiment, momentum (plain wording only; it is the expert label). The footer's "make money" is the
  one allowed money phrase and appears only in the negated footer sentence.
- **W4 Low scores are not reassurance.** A low-score card never says calm, stable, safe or quiet as a quality; it
  says what was not measured as happening ("No matched news").
- **W5 Numbers** use the row's own rounding (move and swing to one decimal of a percent; points whole). Points sum to
  the displayed score.
- **W6 Reading level.** Sentences of at most 25 words; any term not in Learn's glossary is not used.
- **W7 No evidence ranking between components.** The card never says one component is "proven", "tested", "the
  reliable one" or similar. The only research claims allowed are the footer and the two null results already shown
  in the column tooltips (moves and news spikes did not predict direction).
- **W8 Components under dispute.** A component with an open research row whose result could change its weight or sign
  carries one fixed neutral sentence, from a static map in code with a test that #10 is in it: volatility →
  `Whether big swings belong in this score is an open question in SONAR's own research (Learn, section 5).` It states no measured result, because the result did not clear SONAR's own bar. When #10 is decided,
  the map entry is removed or rewritten in that change, not here.
- **W9 No model output.** The card text is the same whether or not an Anthropic key is configured.

### Five example cards (live board, 2026-11-18 12:32, horizon "This week", risk profile aggressive)

No scan with components is cached on disk (`SONAR_DATA` holds state, ledgers and FRED caches only), so these come
from the running agent's loopback `/api/assets` at 12:32 (129 rows). Points use the largest-remainder rule.

**1. Nvidia — notability score 75 / 100, ranked 1st of 129 by this score today (risk filter: aggressive)**
- News 35 of 35: 4 matched news stories in the last 3 hours (newest 12 minutes before the scan; MarketWatch, Financial Times,
  Times of India ×2). 3 or more stories in the last 6 hours.
- Recent move 27 of 30: Fell 8.0% over the last 5 days, the 5th-largest move of 50 shares on the board. The size
  counts, not the direction: a fall scores the same as a rise.
- Swing size 13 of 15: SONAR's estimate of its daily swing is about 3.5% (big swings), the 9th-largest of 50 shares. The score partly compares it with other shares and partly with a fixed size. Whether big swings belong in this score is an open question in SONAR's
  own research (Learn, section 5).
- Earnings date 0 of 20: No earnings date within the next 10 days.
- *Footer.*

**2. Alibaba — notability score 66 / 100, ranked 2nd of 129 by this score today (risk filter: aggressive)**
- Recent move 29 of 30: Fell 15.6% over the last 5 days, the largest move of 50 shares on the board. The size
  counts, not the direction: a fall scores the same as a rise.
- Earnings date 20 of 20: Earnings tomorrow (pre-market) (2026-11-19): a date on the calendar, not a
  forecast.
- Swing size 13 of 15: SONAR's estimate of its daily swing is about 3.3% (big swings), the 12th-largest of 50 shares. … *(W8 note)*
- News 4 of 35: 1 matched news story in the last 7 days (newest 7 days before the scan; CNBC Markets). No story in the last 6 hours and fewer than 3 in the last day.
- *Footer.*

**3. EUR/USD — notability score 54 / 100, ranked 6th of 129 by this score today (risk filter: aggressive)**
- News 35 of 35: 2 matched news stories in the last 4 hours (newest 3 hours before the scan; Reuters, Financial Times). At least one story in the last 6 hours.
- Recent move 13 of 30: Fell 1.8% over the last 5 days, the 7th-largest move of 20 currency pairs on the board. The
  size counts, not the direction: a fall scores the same as a rise.
- Swing size 6 of 15: SONAR's estimate of its daily swing is about 0.4% (small swings), the 9th-largest of 20 currency pairs. The score partly compares it with other currency pairs and partly with a fixed size. … *(W8 note)*
- Earnings date 0 of 20: SONAR only tracks company earnings dates, so currency pairs never score here.
- *Footer.*

**4. VIX — notability score 44 / 100, ranked 10th of 129 by this score today (risk filter: aggressive)**
- Recent move 29 of 30: Rose 39.1% over the last 5 days, the largest move of 20 indices on the board. The size
  counts, not the direction: a fall scores the same as a rise.
- Swing size 15 of 15: SONAR's estimate of its daily swing is about 14.4% (big swings), the largest of 20 indices. … *(W8 note)*
- News 0 of 35: No matched news.
- Earnings date 0 of 20: SONAR only tracks company earnings dates, so indices never score here.
- *Footer.*

**5. TRON — notability score 7 / 100, ranked 129th of 129 by this score today (risk filter: aggressive)**
- Swing size 4 of 15: SONAR's estimate of its daily swing is about 1.6% (medium), the smallest of 21 cryptocurrencies. … *(W8 note)*
- Recent move 3 of 30: Fell 0.7% over the last 5 days, the 20th-largest move of 21 cryptocurrencies on the board.
  The size counts, not the direction: a fall scores the same as a rise.
- News 0 of 35: No matched news.
- Earnings date 0 of 20: SONAR only tracks company earnings dates, so cryptocurrencies never score here.
- *Footer.*

What the examples show: EUR/USD (3) is the case the card exists for: "small swings" in absolute terms and still
mid-table, because the comparison is within currency pairs. Alibaba (2) is near the top with almost no news.
VIX (4) is a volatility index, so its "swing size" is large by construction; the card states the number and does not
editorialise.

### Copy fixes at Design

- **W3 contradicted W8.** The Define W8 sentence used "should", which W3 bans. Reworded to "belong in this score" and
  its pointer changed to "Learn, section 5", because Learn has no "volatility component" section (checked
  `static/docs.html`; §5 now carries the explanation, text below). The wording tests must run W3 over this sentence
  too, so the two can never disagree again.
- **No other W3 term appears** in the five examples, the footer or the new strings below (checked by hand against
  the whole list; Build turns that into the test).

### Opening the card: inline expand, not a popover

The card opens **inline, as a second line of the same Screener row**, pushing the rows below it down. Reasons:

1. It stays in the layout, so it is reachable by Tab, readable by a screen reader in order, and not tied to the
   mouse, which is the exact complaint about the hover-only bar tooltip. A popover is a separate top-level window
   that must be focus-trapped and positioned near the screen edge.
2. The reader compares a row with its neighbours ("why Nvidia above TRON"). A popover covers those rows; inline
   keeps the open row's own figures visible directly above its explanation.
3. The board is already a scroll area of rows (`_rebuild`, `ui/app.py:4903`); inline adds no new window type.

**Trigger.** The whole "Worth a look" cell (`ui/app.py:1600-1621`) is the control: pointing-hand cursor, focus
policy StrongFocus, a visible focus ring (`theme.UP`, 2px, like the line edits in `ui/theme.py:196`), tooltip
"Click to see why this row scores {score}". A caret shows that it opens: plain `75 / 100 ▸`, expert `75 ▸`; `▾`
while open (the caret is `FAINT`, 4.6:1, and is not the only cue: cursor, tooltip and focus ring carry it too). The
cell's accessible name is "Why {name} is worth a look, {score} of 100; {shown|hidden}". The column heading still
links to Learn §5 and its tooltip gains one line: "Click a score to see why." The `ComponentBar`'s hover text
stays as it is.

**Closing, keyboard, one at a time.**
- Click the cell again, press Enter or Space on the focused cell, press **Esc** with focus anywhere inside the open
  card, or press the card's "Hide" button (top right, in the tab order).
- Tab order: cell → (card) Hide → next row's controls. Esc returns focus to the cell that opened the card.
- **Only one card is open.** Opening a card closes any other first; the board remembers one symbol, not a set.
- The card is **not** an event for the board's rebuild: `_rebuild` runs on every scan (about every 3 minutes,
  `ui/app.py:4885-4896`) and replaces every `AssetRow`. The open symbol is kept by the board and re-opened on the new
  row; the card text is rebuilt from the new numbers in place, without moving focus or the scroll position. If the
  symbol is no longer on the board (the risk filter dropped it), the card closes and focus moves to the board's
  header. Wording switch: the card stays open and is re-rendered in the new wording. The 1 s age timer
  (`update_age`) never touches the card. The Architect decides where that remembered symbol lives.
- No animation (also keeps the offscreen tests deterministic). On opening, the board scrolls only as much as is
  needed for the whole card to be visible; it never scrolls if the card already fits.

### Layout at the 1280×775 minimum window

Numbers measured from the code, not guessed: the columns total 1,050pt (`ASSET_COLS`), plus ten 12pt gaps and 12pt
margins either side, so a row is **1,194pt** wide, and below `RAIL_COLLAPSE_BELOW` (1,420pt) the rail is collapsed, so
nothing else takes width from it at 1,280.

- The card spans the row's inner width (1,170pt) and adds **no width**: every label is built with `wrap=True`
  (`label()`, `ui/app.py:353`), so `test_long_prose_labels_wrap` and `test_no_single_tab_forces_the_window_wide`
  (`tests/test_layout.py:65-85`) keep passing.
- Two columns: a **points column** 200pt wide (swatch, label, "27 of 30", mini bar) and a **text column** capped at
  760pt (about 85 characters at 10pt, the readable limit; it does not stretch to the right edge, the rest stays
  empty). The footer spans both and wraps at the same 760pt.
- Height budget: title 22 + heading 18 + four lines of at most three wrapped text lines each (about 4 × 50) + rounding
  note 16 + footer 36 + padding 24 ≈ **290pt**, with a stale-row line 310pt. The board viewport at 775pt high is about
  560pt, so one open card plus its own row always fits. Build test: at 1280×775, open the card on the tallest fixture
  row (Alibaba-like: W8 note, earnings label) and assert the card is fully inside the scroll viewport.
- Type: facts in `theme.text(10)` / `INK`; labels `theme.text(10, True)` / `INK`; secondary text and zero lines
  `MUTED` (6.4:1 on `PANEL`); the "of {max}" and rounding note `FAINT` (4.6:1). Nothing below `FAINT` is text.
  Points figures in `theme.figure(11, True)` (tabular numerals, so the column lines up).

### Points beside the component colours

Each of the four lines starts with a swatch 10×10pt in `theme.COMP[key]` (momentum violet, news orange, volatility
red-orange, catalyst green; same colours as the bar, so the two read as one legend), then the label, then
**`27 of 30`**, then a mini bar of `points / max` on `GRID`. **Colour never carries the meaning alone**: the label
and the number do. Contrast: swatches and bars are non-text (3:1 needed; all four `COMP` colours are light on the
dark `PANEL`, well above), and every text colour is `INK`, `MUTED` or `FAINT`, which clear 4.5:1 (`ui/theme.py:42`).
Build adds a test that the Learn paragraph's four maxima equal `_W` × 100, and a test that every colour the card paints text with is one of those three and that the measured ratio
against `PANEL` is at least 4.5. Catalyst and edge share a green in `COMP`; edge is not on this board, so no clash.
A fixed rounding note sits under the four lines in both wordings: "Points are rounded to whole numbers so they add up
to the score." (W5).

### Plain and expert variants

Same layout, same lines, same order; only vocabulary and one detail differ (the Wording rule in `ui/words.py`:
never the layout).

| | Plain | Expert |
|---|---|---|
| Title | `Nvidia — notability score 75 / 100, ranked 1st of 129 by this score today (risk filter: aggressive)` | `NVDA — NOTABILITY 75, ranked 1st of 129 (risk filter: aggressive)` |
| Line labels | News · Recent move · Swing size · Earnings date | NEWS · MOM · VOL · EARN |
| Line detail | the template sentences | the template sentences' numbers, then `0.88 × 0.30 = 26.4` in `MUTED` |
| Footer, rounding note | identical | identical |

The expert detail shows the unrounded product next to the whole points figure, so `26.4` beside `27` is explained by
the rounding note rather than looking like an error.

### States

| State | What the reader sees |
|---|---|
| **No rows** | Nothing to open: the board shows its existing empty message (`_assets_empty_text`). No card, no card placeholder. |
| **Stale row** | The AGE column already turns gold at 20 min and red at 60 min (`AGE_WARN_S`, `AGE_BAD_S`). When the row is at or past 20 min, the card adds one line under the title, in the same colour. Every card also shows `As of the {HH:MM} scan.` under the title, so no relative time can look current after the board stops updating: `The price and news for this row are {age} old; every figure here is as of then.` The score is shown unchanged and is not recomputed or hidden. |
| **Component missing from `comp`** | A key absent from `comp` is not a zero. The line shows `– of {max}` in `FAINT` and `Not available for this row.`; the other three lines are unaffected. The points rounding runs over the components that exist, so the displayed score is still the sum of the lines shown, and the rounding note stays. If `comp` is missing or empty, the card shows the title, `The parts of this score are not available for this row.`, and the footer. |
| **Non-equity catalyst** | Always the fixed "never score here" sentence, even if `comp` carries a catalyst key. |
| **Open card, row leaves the board** | Closes, focus to the board header (above). |
| **Expert wording** | As the variants table. |

### Learn: the new paragraph for `static/docs.html` §5

Insert after the table that ends at `</table>` (line 482), before the "R:R and P(profit)" callout:

```html
<h3 id="why-card">Why a row has the score it has</h3>
<p>Click the score in the <b>Worth a look</b> column (or press Tab to it, then
  Enter) and a card opens under that row. It lists the four things the score is
  made of and how many points each one added: news, up to 35; recent move, up
  to 30; earnings date, up to 20; and swing size, up to 15. The points add up
  to the score. Under each one is the plain fact behind it: how many matching
  news stories there were and how fresh, how far the price moved and how that
  size ranks among markets of the same kind, how much it usually moves in a
  day, and whether a company earnings date is coming up.</p>
<p>Two things are worth knowing. The recent move and swing size are compared
  with other markets of the same kind (shares with shares, currency pairs with
  currency pairs); news is not. And only company earnings dates are tracked, so
  only shares can score for the earnings date.</p>
<p>The card says what the score leaves out, on every row: it says something is
  happening in that market. It does not say which way the price goes next, and
  a fall counts the same as a rise. Whether big swings belong in the score at
  all is an open question in SONAR's own research; the card says so instead of
  hiding it. One card is open at a time; press Esc or click the score again to
  close it.</p>
```

### Mockup: Nvidia at real width (1,194pt row, 1280×775, plain wording, card open)

Characters stand in for pixels (one column is about 9.5pt at 1280); the card spans the row's inner width, and the
text column stops at 760pt.

```
+------------------------------------------------------------------------------------------------------------+
|  Nvidia — notability score 75 / 100, ranked 1st of 129 by this score today (risk filter: aggressive)   [ Hide ]|
|  As of the 12:32 scan.                                                                                     |
|                                                                                                            |
|  What put it here                                                                                          |
|  [#] News            35 of 35 [==========] 4 matched news stories in the last 3 hours (newest 12 minutes before|
|                                            the scan; MarketWatch, Financial Times, Times of India ×2).     |
|                                            3 or more stories in the last 6 hours.                          |
|  [#] Recent move     27 of 30 [=========-] Fell 8.0% over the last 5 days, the 5th-largest move of 50 shares on|
|                                            the board; the score partly compares moves within the kind and partly|
|                                            with a fixed size. The size counts, not the direction: a fall scores|
|                                            the same as a rise.                                             |
|  [#] Swing size      13 of 15 [========--] SONAR's estimate of its daily swing is about 3.5% (big swings), the|
|                                            9th-largest of 50 shares. The score partly compares it with other|
|                                            shares and partly with a fixed size. Whether big swings belong in this|
|                                            score is an open question in SONAR's own research (Learn, section 5).|
|  [#] Earnings date    0 of 20 [----------] No earnings date within the next 10 days.                    (muted)|
|      Points are rounded to whole numbers so they add up to the score.                                   (faint)|
|                                                                                                            |
|  What this does not say                                                                                    |
|  This score counts what was found in news and price data. It does not say which way the price goes next, or that|
|  a trade would make money. In SONAR's own simulated replay of 25,504 past setups, before costs, big moves and news|
|  spikes showed no clear link to which way prices went; that test can only rule out large effects.          |
+------------------------------------------------------------------------------------------------------------+
```

`[#]` is the colour swatch (`theme.COMP`). The card sits directly under its row (not drawn), which is the existing row unchanged apart from the caret.

### Domain-finance review (2026-11-18, `docs/audit/why-notable-card-domain-finance.md`)

No P0. The three P1s are fixed above: (1) the footer's research sentence now says simulated, before costs, and that
the test only rules out large effects (CONFIDENCE.md §13); (2) "something is happening here" is gone from the footer;
(3) the no-date sentence now looks 2 horizons ahead (`catalyst_score` decays to zero one horizon after the first), so
it can no longer sit beside points from a date 6-9 days out. P2-1 to 5 and 7 to 9 were applied on the owner's "apply as recommended" (swing wording, within-class note, story-count levels, "as of the scan" time, "notability score" title, expert "NOTABILITY", "Earnings date"/EARN, stem-matched W3, Learn-maxima test). **Decided:** P2-6 (the volatility sentence): the owner said "keep neutral" on 2026-11-18, so W8 stands and Define decision 2 is unchanged. **Parked:** P2-10 (Buy/Short labels) is in `TODO.md`; whether the column heading "Worth a look" and the rank read as a pick list goes to a qualified person. Six P3 items remain in the audit file. The ones that change copy ("Usually moves", "More coverage than usual", ranks within class vs the 60/40 blend, frozen
"ago" times, extra W3 words such as recommend/best/top/pick/avoid, Learn maxima drifting from `_W`) go to the owner
before Build. Not re-verified: live board ranks and numbers in the examples. Whether "worth a look" plus "1st of 129"
reads as a pick list, and Buy/Short beside the card, are flagged for a qualified person, not ruled on.

## Smallest first slice

Plain and expert cards for the four components and the footer, opened by clicking "Worth a look" on a Screener row;
counts, sources and ages for news but no headline titles; the W8 note for volatility; the fixture tests for success
measures 1–3. Slice 2 (after the owner check): headline titles rendered as plain text (Secure phase), and #16 reusing
the footer.

## Invariants touched

- **No copy that implies edge, profit or certainty** (`app-context.md`): the whole card is copy; W1–W9 and the banned
  term test are the guard.
- **No direction without evidence** (`assets.py` module docstring; `_plain_read`'s test): extended by success
  measure 2.
- **LLM read stays optional and off by default; a model percentage never sizes a bet**: the card has no model path
  (W9, success measure 1).
- **Untrusted text** (`untrusted-text-sweep`, `label()` is PlainText by default): slice 1 shows only source names
  from the feed; slice 2's titles need the Secure phase.
- **Plain/expert parity** (`ui/words.py`): success measure 3.
- **Test bar**: 80% branch coverage; new logic mutation-checked (the rounding, the ranks, the sign flip).
- No state, persistence, engine, thread or network change is expected, so the Architect gate should not be triggered;
  the architect confirms where the pure function lives (`ui/` or a new `sonar/` module).

## Risks and open questions

Risks:
- **A friendlier explanation raises trust in the score.** A card that explains the score well can read as a reason to
  act. Mitigation: the footer on every card, W3, W7.
- **Advice-like wording.** Jurisdiction is `UNVERIFIED` (`app-context.md`); a domain reviewer should check the
  templates against "recommendation" wording under ESMA/BaFin and SEC/FINRA (question 6).
- **Drift.** The card restates weights and thresholds; Build must read them from `_W`, `news_level` and
  `_swing_words`, never retype them.

Questions for the owner at the Define gate:
1. **Approve the problem, scope and first slice** as written (Screener only, four component lines plus footer, no
   headline titles, no model call)?
2. **Volatility under dispute (#10):** the neutral "open question" sentence (W8, recommended); or state the measured
   gradient with its caveat (45.3% → 34.5%, fails the time-block test); or no note?
3. **Past move sign:** keep "Rose / Fell 8.0%" with the "size counts, not the direction" sentence (recommended; the
   row already shows the sign), or show the size only?
4. **Headline titles** on the card in slice 2: yes (adds a Secure pass) or never (sources and ages only)?
5. **Word-list tone:** `_rationale`'s "tone positive/negative" and the `news_sentiment` field passed to the LLM read
   are unused by the UI but still produced. Add a TODO row to remove them, or leave them?
6. **Domain-finance review** of the templates before you approve (read-only, one pass), or after Design?
7. **Owner check:** are you the reader for success measure 4, and is "five of five" the bar?

### Owner decisions at the Define gate (2026-11-18)

The owner answered "go with recommendations". Questions 1–3 had a stated recommendation. Questions 4–7 had none, so
the agent took the defaults below, which the owner may still overturn before Design:

1. Approved as written: Screener only, four component lines plus footer, no headline titles, no model call.
2. W8 stands: the neutral "open question" sentence for volatility; no measured result on the card.
3. The past move keeps its sign ("Rose / Fell"), with the "size counts, not the direction" sentence.
4. Default: headline titles stay planned for slice 2, behind a Secure pass; slice 1 shows sources and ages only.
5. Default: a `TODO.md` row records removing the word-list tone (`_rationale`, `news_sentiment` in the LLM read).
   Out of scope here.
6. Default: the domain-finance review runs once the Design copy is final, before Architect and Build.
7. Default: the owner is the reader for success measure 4, and the bar is five of five.

## Verification plan *(qa-engineer, to be completed in Verify)*

Fixture tests for measures 1–3 in both wordings; mutation check on rounding, ranking and the sign flip; the owner
check (measure 4) with screenshot; full suite native and offscreen.
