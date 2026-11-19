# Spec: a "why is this notable" card per instrument on the Screener

- Status: approved (Define); Design done 2026-11-18; Architect done 2026-11-18 (gate not triggered, see A5),
  copy questions decided by the owner ("Yes, as recommended")
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
| Earnings date | 20 | equity with a date: `{Earnings label} ({date}): a date on the calendar, not a forecast.` · equity without: `No earnings date in the next {min(2d,14)} days of SONAR's calendar.` (calendar empty or never fetched: `Earnings calendar not available.`; see Review changes) · other classes: `SONAR only tracks company earnings dates, so {class plural} never score here.` |

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
  `Whether big swings belong in this score is an open question in SONAR's own research (Learn, section 11).` It states no measured result, because the result did not clear SONAR's own bar. When #10 is decided,
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
  own research (Learn, section 11).
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
| **Stale row** | The AGE column already turns gold at 20 min and red at 60 min (`AGE_WARN_S`, `AGE_BAD_S`). When the row is at or past 20 min, the card adds one line under the title, in the same colour. Every card also shows `As of the {HH:MM} scan.` under the title, and no relative time is used, so nothing can look current after the board stops updating: `The price and news for this row were fetched at {HH:MM}; every figure here is as of then.` (absolute time, so it cannot freeze; owner decision at Architect, copy decision 1) The score is shown unchanged and is not recomputed or hidden. |
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
|                                            score is an open question in SONAR's own research (Learn, section 11).|
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

## Architecture

Architect pass 2026-11-18 (`architect`), on branch `claude/architect-why-notable-card` from f551e53. The code was
read at that commit; line numbers below are from it. No ADR: every decision here can be undone in one small change.

### A1. Where the card-building function lives: a new `ui/why_card.py`

**Decision.** A new module `ui/why_card.py`. It is pure Python: it imports no Qt, does no I/O, reads no clock and has
no path to `sonar.llm`. It imports only `sonar.assets` (constants, see A3) and the standard library. The Qt widget
that draws the card (`WhyCard`, A2) lives in `ui/app.py` beside `AssetRow` and calls this module. It does not
compute anything itself.

Why `ui/` and not `sonar/`: the card is presentation copy in two wordings, and its only consumer is the Qt Screener.
The web dashboard is out of scope. `sonar/` holds the engine and data. `ui/` already holds the row's other reading
helpers (`_plain_read`, `_swing_words`, `ui/app.py:203-240`). A `sonar/` module would have to import
`_swing_words` from `ui/`, and nothing in `sonar/` imports `ui/` today (checked with `grep`). It would need to stay
that way.

Why not inside `ui/app.py`: that file is about 5,300 lines. The success-measure tests need to import the function
without building a `MainWindow`, and Build needs a module whose coverage and mutation score can be read on their
own.

**`_swing_words` moves** from `ui/app.py:203` into `ui/why_card.py` as `swing_words`. `ui/app.py` keeps the old name
with `from .why_card import swing_words as _swing_words`, so the row and `tests/test_plain_language.py:103` keep
working unchanged and the card and the row cannot drift.

**Signature.**

```python
def build_card(row: dict, board: dict, *, plain: bool, age_s: float) -> Card
```

- `row`: one element of `board["assets"]`, exactly as `/api/assets` serves it (`asdict(AssetSuggestion)`).
- `board`: the whole assets payload. The card reads `assets` (for ranks and N), `generated` (scan time), `risk`
  (profile name) and `horizon` (`momentum_days`, for the earnings window).
- `plain`: passed in, never read from `words.plain()`, so the function has no hidden global. The widget passes
  `words.plain()`.
- `age_s`: the row's data age at render time, computed by the caller from `AssetRow._fetched_at`. The function never
  calls `time.time()`. The `HH:MM` of `generated` is formatted with `time.localtime`, which depends on `TZ`, not on
  the clock. Tests pin `TZ`.
- `Card` is a frozen dataclass: `title`, `as_of`, `stale` (str or None), `unavailable` (str or None, for the
  empty-`comp` state), `lines: tuple[CardLine, ...]`, `rounding_note`, `footer`. `CardLine` holds `key`, `label`,
  `points` (int or None when missing), `max`, `text`, `expert_detail` (str or None), `muted` (bool). Plain data only,
  so the three success-measure tests assert on fields and not on widgets.
- Fixed strings sit at module level: the footer as `FOOTER`, the rounding note, and the W8 map as
  `UNDER_DISPUTE = {"volatility": "..."}`. #16 imports `FOOTER` verbatim (Non-goals) and the W8 test reads
  `UNDER_DISPUTE`.
- `displayed_score(confidence: float) -> int` lives here too. The "Worth a look" cell (`ui/app.py:1610`) switches
  from `f'{a["confidence"]:.0f}'` to it, so "the score as displayed" (W5) has one definition. The caret and accessible
  name in that cell use it too.

### A2. Where the open symbol is remembered across `_rebuild`: on `MainWindow`, applied in `_refresh_cards`

**Decision.** `MainWindow._why_open: str | None`, set to `None` beside `_asset_rows` where the
Screener is built (`ui/app.py:2089`). It is ephemeral widget state: never persisted, never sent to the engine, gone at quit.

The board is rebuilt by `_refresh_cards` (`ui/app.py:4875-4896`) whenever `_assets_sig` changes. That covers a new
scan (`generated`), a trade or undo (`_assets_sig = None`, `4675`, `5326`) and the Wording switch (`_apply_wording`
clears `_assets_sig`, `4531`). One field on the window therefore covers all three cases. The shared static
`_rebuild(lay, widgets, msg)` (`4899`) is used by other boards too, so it stays unchanged. The card logic lives in
`_refresh_cards` only.

The card is a separate widget, `WhyCard(QFrame)`, inserted into the board's widget list right after its `AssetRow`.
It is not a second layout inside `AssetRow`. That keeps `AssetRow`'s structure, and the tests that walk it,
unchanged. Opening and closing a card insert or remove one widget with `insertWidget` / `removeWidget` +
`deleteLater` and do not rebuild the board.

Flow:

1. **Click, Enter or Space on the score cell** calls `MainWindow._toggle_why(symbol)`. That closes any open `WhyCard`,
   sets `_why_open` (or clears it if this card was the open one), inserts the new card after the row, and scrolls
   minimally with `QScrollArea.ensureWidgetVisible(card, 0, 0)`, which never scrolls if the card already fits.
   Esc or Hide calls the same method, then focuses the row's score cell.
2. **Rebuild** (`_refresh_cards`, when the signature changes):
   - *Before* the old widgets are dropped, record the scroll area's vertical value. Also record whether focus is inside
     the old open card or its score cell (`QApplication.focusWidget()` and `isAncestorOf`), and which of the two had it
     (cell or Hide).
   - Build the new `AssetRow`s. If `_why_open` is among the new rows, build its `WhyCard` from the *new* row dict and
     the new board, and put it after that row in the list given to `_rebuild`.
   - *After* `_rebuild`, call `self._assets_lay.activate()` so the geometry is final, put the scroll value back, and
     return focus to the same element (cell or Hide) in the new widgets. Focus is restored only if it was there
     before, so a scan never pulls focus from another tab or a line edit.
   - If focus was inside the card and the new layout has moved the card out of view, because ranks reorder every
     scan, scroll minimally to it. In every other case the scroll value is left as it was.
   - If `_why_open` is no longer on the board, set it to `None` and add no card. If focus was inside the card, move it
     to the board header (`self.asset_header`).
3. **The 1 s timer** (`update_age`, `4895`) never touches `WhyCard`.

Rows are rebuilt as new widgets each time, so the card holds no reference to a deleted object across a rebuild. This
is the same invariant the comment at `4886-4890` keeps for `_asset_rows`: `_why_card` is replaced at the same point
as the widgets it belongs to.

### A3. Ranks from raw quantities; weights, news levels and swing words read from code

- **Raw, unclipped rank keys** come from `sonar.assets.CROSS_SECTIONAL` (`assets.py:525`), the same table the score's
  within-class pass uses. Payload rows are dicts and the lambdas read attributes, so the card calls
  `CROSS_SECTIONAL[k](types.SimpleNamespace(**row))`. If the score's raw quantity changes, the card's rank changes
  with it. Payload `momentum` and `volatility` carry the same 4-decimal rounding as the values `standardise_raw` saw
  (`assets.py:470-472`, rounded before `_standardise_components`), so the ranks match the score's own inputs exactly.
- **Rank population** is the rows in `board["assets"]` with the same `cls`. This is the post-risk-filter set the score
  was standardised against. N is the count of that set.
- **Rank method**: competition rank, descending (1 + the number of same-class rows with a strictly larger key), so
  ties share a rank. Rank 1 gives "the largest". Rank N with N > 1 gives "the smallest". N = 1 gives "the only {class singular} on the board" (copy decision 2).
- **Board rank in the title** uses the same competition rank on `confidence` over all of `board["assets"]`. The
  payload is already sorted by it (`assets.py:499`), but the card does not rely on that order.
- **Weights.** `_W` is imported, as `ui/app.py:60` already does. Max points per line = `round(100 * _W[k])`. The
  Build test checks that every `_W[k] * 100` is a whole number, so `round` never hides a fraction. Tie order for
  sorting lines and for rounding is `_W` descending: news, recent move, earnings date, swing size. **Correction to
  Design**: the Card structure item 2 says "news, move, swings, date", which is not weight order. Build fixes that
  one line to match. The example cards do not show a tie between swings and date, so none of them changes.
- **News levels.** `news_level` (`assets.py:564`) keeps its thresholds as literals (6 h, 24 h, 3 stories). Build
  lifts them into module constants in `sonar/assets.py` (`NEWS_FRESH_H = 6`, `NEWS_DAY_H = 24`, `NEWS_SPIKE_N = 3`,
  `NEWS_DAY_N = 3`). `news_level` uses them unchanged, and the card's level sentences are formatted from them. This
  is a behaviour-neutral refactor of one `sonar/` function. The existing `news_level` tests plus one new test, "the
  sentences quote the constants", cover it. The level itself comes from the row's `lean`, never recomputed.
- **Story count, span and ages** come from `row["headlines"]`: count = `len`, newest and oldest = min/max of the
  `age_h` values that are not `None`. Undated headlines count towards *k* but not towards the span. This matches
  `news_level`, which counts only dated headlines towards levels. If every headline is undated, the span clause is
  left out: "{k} matched news stories (no dates given; {sources})". Decided: copy decision 3 below.
- **Swing words** come from `swing_words(row["volatility"])` (A1). Its thresholds stay where they are, in one place.
- **Earnings window** is `2 × board["horizon"]["momentum_days"]`. That is the horizon length `catalyst_score` is
  called with (`assets.py:460`, `days` = `hz.momentum_days`), and the score decays to zero at 2 horizons
  (`events.py:196-199`).
- **The catalyst key is often absent, and that means zero.** `comp["catalyst"]` is written only when an earnings date
  exists (`assets.py:452-458`). Every equity without a date and every non-equity row has no key, and the score counts
  it as 0 (`comp.get(k, 0.0)`, `assets.py:552`). So for `catalyst`, absent is **not** the "Component missing" state:
  it is 0 points with the equity or non-equity sentence from the templates. The "missing" state (`– of {max}`)
  applies only to `momentum`, `volatility` and `news`, which every scanned row carries today. It stays as a defensive
  path with its own test.

### A4. Largest-remainder rounding

Over the components that count in the score, K = { k ∈ `_W` : k in `comp`, or k = `catalyst` }. Catalyst is
included at 0 when absent (A3), which adds nothing to any sum.

1. `exact[k] = 100 * _W[k] * comp.get(k, 0.0)`. These use the same 3-decimal `comp` values the score was computed
   from (`assets.py:551-552`).
2. Target `T = displayed_score(row["confidence"])` (A1), the integer the cell shows.
3. `points[k] = floor(exact[k])`, `R = T − Σ points`.
4. Give +1 to the R components with the largest `exact[k] − floor(exact[k])`, ties in `_W` order, and only to
   components whose fractional part is above 0.

Bounds, which Build asserts in code: `confidence` is the exact sum rounded to 1 dp, then to 0 dp, so
`|T − Σexact| ≤ 0.55`. That gives `0 ≤ R ≤` (the number of components with a fractional part above 0). So no
component goes below its floor or above `ceil(exact[k]) ≤ max`. If the assertion ever fails, because the score
formula changed under the card, the card shows unrounded points to 1 dp, leaves out the rounding note and logs a
warning. That is honest and visible, and better than a sum that does not add up. A property test over the fixture,
plus a random-`comp` test, check Σ points = T and `0 ≤ points ≤ max`.

A missing `momentum`, `volatility` or `news` key (the defensive state) is left out of K. The score's own sum also
counts it as 0, so T still equals the sum of the lines shown, as the States table requires.

### A5. Does this touch state, concurrency or module boundaries?

- **State**: no persisted or engine state. `_why_open` is in-memory widget state on `MainWindow`, of the same kind as
  `_assets_sig` and `_asset_rows`.
- **Concurrency**: none. Everything runs on the GUI thread inside `_refresh_cards`, from the `assets` dict the refresh
  tick already holds. There is no new thread, timer, lock or signal across threads.
- **Module boundaries**: one new module inside `ui/`. `ui → sonar` imports stay in the direction they already go:
  `ui/app.py:56,60` already imports `sonar.assets` and `_W`. Two `sonar.assets` names newly become a shared contract:
  `CROSS_SECTIONAL` and the four news-level constants. `sonar.assets` gains nothing it imports. No `sonar → ui`
  edge, no server, payload or network change.

**Conclusion: the Architect gate is not triggered.** One judgement call is the owner's to overrule:
`CROSS_SECTIONAL` and the news constants change from private details of `sonar/assets.py` to names the UI depends on.
A later change to the score now has to keep them, or update the card in the same change. The card's tests fail if
it does not, which is the intent.

### A6. Test seams for Build

- Success measure 1: `build_card` over every row of the fixture, with `sonar.llm` replaced in `sys.modules` by a
  module whose attribute access raises. Only `ui.why_card` is imported, not `ui.app`, so no window is built.
- Success measure 2: momentum sign flip, then a diff of the `Card` fields. Exactly one token differs ("Rose" or
  "Fell"). The W3 stem matcher runs over every string field in both wordings, over `UNDER_DISPUTE`, the state strings,
  the cell tooltip and accessible name, and the Learn paragraph.
- Success measure 3: plain and expert `Card`s have equal `points`, `max`, numbers in the text, `footer` and
  `rounding_note`.
- Qt tests (offscreen and native): rebuild keeps `_why_open`, scroll value and focus; a symbol that leaves the board
  closes the card and moves focus to the header; the Wording switch re-renders the card; the card fits in the viewport
  at 1280×775 (Design).
- Mutation targets: the rounding (A4), competition rank and its key (A3), the sign verb, the catalyst-absent branch.

### Copy decisions (owner, 2026-11-18: "Yes, as recommended")

The three copy questions raised at Architect were decided as recommended. The W3 banned-term test covers the new
strings.

1. **Stale line is absolute.** `The price and news for this row were fetched at {HH:MM}; every figure here is as of
   then.` `{HH:MM}` is `board["generated"] - row["data_age_s"]`, formatted like the `As of` line. `age_s` still
   decides whether the line shows (at or past `AGE_WARN_S`) and its colour, when the card renders. The 1 s timer still
   never touches the card. The Design States table is updated to match.
2. **Only one of its kind** (N = 1 in a class): `the only {class singular} on the board`. Class singulars sit beside
   the plurals in `ui/why_card.py`: Equity → share, Index → index, Forex → currency pair, Crypto → cryptocurrency,
   Commodity → commodity.
3. **All matched headlines undated:** `{k} matched news stor{y/ies}, with no publication time given ({sources}).`

### Changes at Review (2026-11-18, owner: "Yes, send fixes")

Fixes for `docs/audit/why-notable-card-code-reviewer.md` and `docs/audit/why-notable-card-review-domain-finance.md`.
Copy that departs from the text approved above (the approved text in Design and the examples is kept as history;
this list wins where they differ):

1. **Earnings line (DF P1-1).** `No earnings date in the next {min(2d,14)} days of SONAR's calendar.`: the calendar
   looks 14 days ahead (`sonar/events.py` `LOOKAHEAD_DAYS`), so a longer window claimed more than was checked. When
   the calendar holds nothing, or was never fetched: `Earnings calendar not available.` To know that, the
   `/api/assets` payload gains `earnings_calendar: {"n": <earnings held>, "days": 14}` (read from
   `EventsCache.cached_payload()`, no fetch). This changes A5's "no payload change": one added field, no change to the score.
2. **Learn (DF P1-2, P2-1, P3).** "it says something is happening in that market" is gone; the paragraph now says the
   card says what the score does not tell you. "how much it usually moves in a day" became "SONAR's estimate of its
   daily swing". Move and swing are "partly compared with other markets of the same kind ... and partly with a fixed
   size".
3. **W8 pointer** now reads `(Learn, section 11)`, the section that holds the evidence (Learn §5 only repeated the
   question). Neutral wording is unchanged.
4. **Expert arithmetic (CR P2-1).** The component value is printed to three decimals (`0.971 × 0.35 = 34.0`), the
   precision the score uses, so the line multiplies out as printed.
5. **Wording of the window.** Shares count trading days: `over the last 5 trading days`; `1 day` / `1 trading day`
   in the singular (`over the last day`); a move that rounds to 0.0% reads `Moved 0.0%`, not `Rose`/`Fell`.
6. **Board rank** is taken from the score as displayed, so two rows that both show 75 share a rank.
7. **Fallback** (points that cannot be rounded to the score) shows `Points are shown unrounded here, so their sum can
   differ from the score.` in place of the rounding note.
8. Not a copy change: the score cell announces itself as a button, ignores key auto-repeat, and is transparent
   (CR P1-1); focus on any score cell survives a scan (CR P3-4).

Not done: P3 `pass in the window actually used` (needs the shortened window in the payload), and the open Design P3-5
and P3-6.

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
- No state, persistence, engine, thread or network change: confirmed at Architect (A5). The pure function lives in a
  new `ui/why_card.py` (A1).

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
