# Spec: a "why is this notable" card per instrument on the Screener

- Status: approved (Define)
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

## Design (Define-level; the ux-designer owns layout)

### Card structure (fixed order, every row)

1. **Title line**: `{name} — worth a look {score} / 100 ({rank} of {n} on the board)`.
2. **"What put it here"**: four lines, sorted by points (ties in weight order news, move, swings, date), zero lines
   last and greyed. Each line: plain label, `{points} of {max}`, one or two sentences of fact.
3. **"What this does not say"**: the fixed footer, always visible, not collapsible, identical on every card:
   > This score says something is happening here. It does not say which way the price goes next, or that a trade
   > would make money. SONAR tested big moves and news spikes over 25,504 past setups: neither told which way prices
   > went.

### Line templates (plain wording)

| Component | Max | Template |
|---|---|---|
| News | 35 | `{k} matched news stor{y/ies} in the last {span} (newest {age} ago; {sources}).` + level sentence: Spike → `That counts as a news spike.` · Elevated → `More coverage than usual.` · Normal → `Ordinary coverage.` · none → `No matched news.` |
| Recent move | 30 | `{Rose/Fell} {x}% over the last {d} days, the {ordinal}-largest move of {N} {class plural} on the board. The size counts, not the direction: a fall scores the same as a rise.` |
| Swing size | 15 | `Usually moves about {v}% a day ({swing words}), the {ordinal}-largest of {N} {class plural} ("the largest" / "the smallest" at the ends). The score compares it with other {class plural}, not with every market.` + W8 note |
| Scheduled date | 20 | equity with a date: `{Earnings label} ({date}): a date on the calendar, not a forecast.` · equity without: `No earnings date within the next {d} days.` · other classes: `SONAR only tracks company earnings dates, so {class plural} never score here.` |

Class plurals: Equity → shares, Index → indices, Forex → currency pairs, Crypto → cryptocurrencies, Commodity →
commodities. Ranks and N are among rows currently on the board (after the risk filter), which is the set the score
was standardised against.

Expert wording: the same lines with the component value and weight appended (`0.88 × 0.30 = 26.4`), ticker in place
of the name, labels MOM / VOL / NEWS / CAT. Same footer.

### Wording rules

- **W1 Facts only.** Every clause is a number on the row, a rank computed from the board, or a fixed sentence from
  this spec. Nothing is inferred, and no headline text is paraphrased.
- **W2 Tense.** Price movement in the past tense only. No future tense anywhere in the templates (no "will").
- **W3 Banned terms** (test-enforced, whole words, case-insensitive, both wordings): buy, sell, short, long, bullish,
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
  `Whether big swings should add to this score is an open question in SONAR's own research (Learn: the volatility
  component).` It states no measured result, because the result did not clear SONAR's own bar. When #10 is decided,
  the map entry is removed or rewritten in that change, not here.
- **W9 No model output.** The card text is the same whether or not an Anthropic key is configured.

### Five example cards (live board, 2026-11-18 12:32, horizon "This week", risk profile aggressive)

No scan with components is cached on disk (`SONAR_DATA` holds state, ledgers and FRED caches only), so these come
from the running agent's loopback `/api/assets` at 12:32 (129 rows). Points use the largest-remainder rule.

**1. Nvidia — worth a look 75 / 100 (1st of 129 on the board)**
- News 35 of 35: 4 matched news stories in the last 3 hours (newest 12 minutes ago; MarketWatch, Financial Times,
  Times of India ×2). That counts as a news spike.
- Recent move 27 of 30: Fell 8.0% over the last 5 days, the 5th-largest move of 50 shares on the board. The size
  counts, not the direction: a fall scores the same as a rise.
- Swing size 13 of 15: Usually moves about 3.5% a day (big swings), the 9th-largest of 50 shares. The score compares it with
  other shares, not with every market. Whether big swings should add to this score is an open question in SONAR's
  own research.
- Scheduled date 0 of 20: No earnings date within the next 5 days.
- *Footer.*

**2. Alibaba — worth a look 66 / 100 (2nd of 129)**
- Recent move 29 of 30: Fell 15.6% over the last 5 days, the largest move of 50 shares on the board. The size
  counts, not the direction: a fall scores the same as a rise.
- Scheduled date 20 of 20: Earnings tomorrow (pre-market) (2026-11-19): a date on the calendar, not a
  forecast.
- Swing size 13 of 15: Usually moves about 3.3% a day (big swings), the 12th-largest of 50 shares. … *(W8 note)*
- News 4 of 35: 1 matched news story in the last 7 days (newest 7 days ago; CNBC Markets). Ordinary coverage.
- *Footer.*

**3. EUR/USD — worth a look 54 / 100 (6th of 129)**
- News 35 of 35: 2 matched news stories in the last 4 hours (newest 3 hours ago; Reuters, Financial Times). More
  coverage than usual.
- Recent move 13 of 30: Fell 1.8% over the last 5 days, the 7th-largest move of 20 currency pairs on the board. The
  size counts, not the direction: a fall scores the same as a rise.
- Swing size 6 of 15: Usually moves about 0.4% a day (small swings), the 9th-largest of 20 currency pairs. The score compares it
  with other currency pairs, not with every market. … *(W8 note)*
- Scheduled date 0 of 20: SONAR only tracks company earnings dates, so currency pairs never score here.
- *Footer.*

**4. VIX — worth a look 44 / 100 (10th of 129)**
- Recent move 29 of 30: Rose 39.1% over the last 5 days, the largest move of 20 indices on the board. The size
  counts, not the direction: a fall scores the same as a rise.
- Swing size 15 of 15: Usually moves about 14.4% a day (big swings), the largest of 20 indices. … *(W8 note)*
- News 0 of 35: No matched news.
- Scheduled date 0 of 20: SONAR only tracks company earnings dates, so indices never score here.
- *Footer.*

**5. TRON — worth a look 7 / 100 (129th of 129)**
- Swing size 4 of 15: Usually moves about 1.6% a day (medium), the smallest of 21 cryptocurrencies. … *(W8 note)*
- Recent move 3 of 30: Fell 0.7% over the last 5 days, the 20th-largest move of 21 cryptocurrencies on the board.
  The size counts, not the direction: a fall scores the same as a rise.
- News 0 of 35: No matched news.
- Scheduled date 0 of 20: SONAR only tracks company earnings dates, so cryptocurrencies never score here.
- *Footer.*

What the examples show: EUR/USD (3) is the case the card exists for: "small swings" in absolute terms and still
mid-table, because the comparison is within currency pairs. Alibaba (2) is near the top with almost no news.
VIX (4) is a volatility index, so its "swing size" is large by construction; the card states the number and does not
editorialise.

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
