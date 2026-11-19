# Domain review (finance): why-notable-card, Design copy

Reviewer: domain-finance specialist, read-only, one pass, 2026-11-18. Spec: `docs/specs/why-notable-card.md`
(line numbers below are that file's). Playbook `domain-finance.md`: status current, last-reviewed 2026-11-11 (not stale).
App-context `## Domain specialist` present. Jurisdiction of users is UNVERIFIED, so nothing here is a ruling under
SEC/FINRA (e.g. FINRA Rule 2210 communications; Reg BI "recommendation" facts-and-circumstances test) or
ESMA/BaFin (MiFID II investment-recommendation and MAR Art. 20 definitions); those are flagged as concerns, not
verified against current text. Needs a qualified person: P0/P1 wording marked "lawyer" below.

No P0. Facts I checked against code: `_W` (assets.py:205) weights, `news_level` (assets.py:564) thresholds, `_swing_words`
(ui/app.py:203) 3.0%/1.5% cut-offs, `catalyst_score` (events.py:186), `standardise_raw` (crosssection.py:134, mix 0.6),
CONFIDENCE.md section 13 (25,504 setups), section 10a (volatility), section 9 (word list). Rank and example numbers
come from a live board I could not re-fetch: not verified.

## P1

### P1-1 Footer research sentence overstates the result
Copy (line 122-123, 376): "SONAR tested big moves and news spikes over 25,504 past setups: neither told which way prices went."
Evidence: CONFIDENCE.md s13: "Neither momentum nor news showed a detectable edge ... these studies can rule out large
effects, not small ones ... an effect of about 3 points on the hit rate ... would usually go undetected." The 25,504 setups
overlap (not independent); they are a replay of 113 instruments over 5 years (board is 129 today), gross of costs, and the
outcome is "touched target before stop", not "which way prices went". Spike result was +0.8 +/- 3.1 points.
Scenario: a reader without finance training reads "neither told" as proof that moves and news have no link to price
direction, or reads 25,504 as a large independent sample. Both are stronger than the evidence (performance figures must
carry period, sample, cost treatment, per app-context). It also states a simulated result with no "backtest" label.
Fix: "SONAR's own replay of past data (5 years, 113 markets, 25,504 overlapping setups, before costs) found no reliable
link between big moves or news spikes and what prices did next. A test this size could miss a small effect." Read
the number, years and instrument count from one constant with a date, never retyped (the "129" vs "113" difference
already shows the drift risk); a test should fail if CONFIDENCE.md's figure changes.

### P1-2 "Something is happening here" is a claim, and is false on low rows
Copy (line 121, 340): "This score says something is happening here." (footer on every card, including TRON at 7 / 100,
and VIX at 44 where the swing points are a property of the index).
Scenario: a 7 / 100 row, or a row high only because the asset is always volatile (VIX, crypto), is told something is
happening. That is an inference the score does not support and reads as an alert on a named instrument.
Fix: "This score adds up four measured facts: news, recent price move, usual daily swing and an earnings date. It does not
say which way the price goes next, or that a trade would make money." Same fix in the Learn paragraph ("it summarises
four measured facts about that market").

### P1-3 Scheduled-date line contradicts the score for earnings 6 to 10 days out
Copy (line 132): "No earnings date within the next {d} days." Code: `catalyst_score` is 1.0 inside the horizon but decays
linearly to 0 one horizon later (days 6 to 9 on a 5-day horizon score 0.8 to 0.2), so a row can show "6 of 20" beside
"No earnings date within the next 5 days". Also a provider failure or a missing calendar is indistinguishable from "none".
Scenario: the card states a false fact next to non-zero points; the reader loses trust in every other line.
Fix: three cases. Date inside horizon: current text. Date after horizon but scoring: "Earnings on {date}, {n} days away,
just after this window; it counts for part of the points." No date found: "No earnings date found in the data
SONAR has." (and the "Not available" state when the lookup failed). Add a fixture test with a date at d+2.

## P2

### P2-1 "Usually moves about X% a day" misdescribes a forecast
Copy (lines 131, 176 and all examples). `volatility.forecast` (volatility.py:337) is a GARCH or trailing-250 model forecast of
daily volatility (a standard deviation, not a typical absolute move, which is about 0.8 of it). "Usually moves" is
habitual wording that reads as a promise about the next days, against W2 (no forward wording) and W1.
Fix: "SONAR's estimate of its daily swing is about {v}% ({swing words})." Expert: "daily vol estimate {v}%".

### P2-2 Title "worth a look" and the rank read as a pick list
Copy (lines 117, 171 "1st of 129 on the board", 209 "129th of 129"). "Worth a look" invites action on a named instrument and
"1st of 129" reads as a league table or top pick; W3 does not ban "worth", "look", "top", "best". The rank also moves with the
risk profile and the filter (the board was "aggressive"), so "of 129" is not a universe.
Fix (lawyer to confirm the heading, which is existing UI): "{name} — notability score {score} / 100, ranked {rank} of
{n} by this score today (risk filter: {profile})". Add "ranked by how much is going on, not by expected result"
only if P1-2 wording is not enough.

### P2-3 Component ranks do not match what the score compares
Copy (lines 130-131): "the 5th-largest move of 50 shares", "The score compares it with other shares". `standardise_raw` blends 40%
absolute and 60% within-class (crosssection.py:156), so the score is not a rank. Reader may expect 5th of 50 and 5th of
50 to score the same across classes (Nvidia 5th of 50 gets 27 of 30; EUR/USD 7th of 20 gets 13).
Fix: "The score partly compares it with other {class plural} and partly with a fixed size." The rank must be computed
from the raw unclipped quantity, not from points; test it.

### P2-4 "More coverage than usual" is not what `news_level` measures
Copy (line 129). `news_level` counts fresh stories (>=1 in 6 h or >=3 in 24 h = Elevated; >=3 in 6 h = Spike); it has no
per-instrument baseline. Nvidia always having 4 stories would still read "than usual". Also "Quiet" in code maps to
"No matched news", which is right, but "Ordinary coverage" claims a normal.
Fix: Spike: "3 or more stories in the last 6 hours."; Elevated: "At least one story in the last 6 hours (or 3 in a day).";
Normal: "Stories exist but none in the last 24 hours (fewer than 3)." Take the thresholds from `news_level`, not typed.

### P2-5 Relative times freeze while the card stays open
Copy (line 129, 171 "newest 12 minutes ago", line 316). The card is rebuilt each scan (about 3 minutes) and "the 1 s age timer never
touches the card" (lines 258-260). If the agent stalls, "12 minutes ago" is shown for an hour. The stale-row line covers
price age only, and only from 20 minutes.
Fix: print an absolute scan time on every card ("as of 12:32 scan") and word ages as "newest 12 minutes before that scan";
extend the stale line to the news counts: "The price and news for this row are {age} old; every figure here is as of then."

### P2-6 W8 sentence: wrong subject, dangling pointer, under-disclosure
Copy (line 162): "Whether big swings belong in this score is an open question in SONAR's own research (Learn, section 5)."
(a) It says "big swings" on rows with "small swings" (EUR/USD, TRON). (b) The new Learn paragraph (lines 342-343) only repeats
"an open question"; it does not say what the question is, so the pointer is empty. (c) CONFIDENCE.md 10a: higher volatility
ranked down target-before-stop hit rate in 5 of 6 blocks (p 0.22, latest reversed); a neutral line hides that the
component may work against the reader's reading of "high score = good". Owner chose neutral (Define 2); this is for
the owner to reconsider, not a ruling.
Fix: "How much weight swing size should get is an open question in SONAR's research; in past data larger swings did not
go with better results (Learn, section 5)." and have section 5 state the 10a result with its caveat (45.3% to 34.5%, fails the
time-block test).

### P2-7 Expert title "CONF" abbreviates a banned word
Copy (line 303): "NVDA — CONF 75". W3 bans "confidence", "confident", "sure"; whole-word matching lets "CONF" pass, but it is
the same word and signals certainty. Existing UI label, but the card spreads it.
Fix: "NVDA — NOTABILITY 75 (1st of 129)" or "NOTAB 75"; add `conf` to the banned list for the card, and rename in `docs` section 5 later.

### P2-8 W3 list gaps (whole-word matching lets inflections and synonyms through)
Banned-term scan of every template, example, state string and the docs paragraph (lines 118-123, 129-132, 162, 171-215,
293-294, 316-317, 327-345): no listed word found. The list itself has gaps:
- Inflections and forms: buys, sells, bought, sold, buying, selling, shorts, longs, gains, gained, wins, winning, expects, signals, targets, likelihood, unlikely, probably, possible, possibly, potential, might, must, would (allowed only inside the footer), can, going, "'ll", "won't".
- Advice and endorsement: recommend, recommended, advice, advise, pick, top, best, worst, winner, loser, favourite, attractive, promising, interesting, hot, trending, bet, invest, hold, avoid, accumulate, outperform, underperform, beat, bottom.
- Direction and event drivers: rally, surge, soar, plunge, crash, dip, rise-to-come, catalyst (see below), trigger, driver, poised, due, set to, about to, next (only in the footer's negated sentence), returns, yield, income, opportunity-like "worth", "look".
- Certainty: certain, definitely, proven, reliable, clear, obvious, confirmed, validated.
- Time: tomorrow, soon, imminent used in forward sense (the "Earnings tomorrow" label is a date fact; allow it by exact string only).
Fix: match stems (`re.search(r"\b(buy|bought|buys|buying)\b")`, or lower-case prefix list), add the groups above, add an
allow-list for the exact footer and the earnings label, and run the test over the Learn paragraph, the W8 sentence,
the state strings and the tooltips (`Click to see why this row scores {score}`), not only card lines.
Also: the label "Scheduled date" is fine, but the expert label CAT and any "catalyst" text imply a price-moving event; CONFIDENCE.md 13 says the
catalyst effect is volatility-shaped, not a direction. Prefer "Earnings date" (plain) and "EARN" (expert).

### P2-9 Hard-coded numbers in the Learn paragraph
Copy (lines 331-335): "news, up to 35; recent move, up to 30; scheduled date, up to 20; swing size, up to 15". Spec Risks says
read from `_W`, but `static/docs.html` is static. Add a test comparing the paragraph's numbers to `_W` x 100. Section 5 table
(docs.html:474-475) already carries 0.35/0.30/0.20/0.15; the two will drift together or apart.

### P2-10 Paper wording next to the card
Mockup (line 355): the row shows `[Buy][Short]` directly above a card that explains a notability score; ui/app.py:1639 and 1644 label them
"Buy"/"Short" (plain). Not new, but the card makes the row look like a rationale for the trade. Fix: "Paper buy" /
"Paper short" in the row, or a one-line "Paper trades only" under the title. Not verified whether the row says paper elsewhere.

## P3

- P3-1 "129th of 129" on a 7 / 100 row (line 209) is a ranking of the weakest instrument; W4 is respected, but state the lowest rank in the same neutral
  form ("ranked 129 of 129 by this score"), no "bottom"/"smallest" adjectives on the title. "the smallest of 21 cryptocurrencies" is fine as a fact.
- P3-2 Rounding (lines 293, 308): largest-remainder shows 27 for 26.4 and 13 for 13.35 (Nvidia: 35 + 26.4 + 13.35 = 74.75, shown 75). The rounding note is accurate; add the
  unrounded product in the plain card too, or accept the 0.6 point distortion (a line can differ from its own nearest rounding by up to 0.99). Confirm the
  displayed score equals `round(confidence)`, not the 1-decimal value (assets.py:552 rounds to 1 decimal), in a test.
- P3-3 Missing-component state (line 317): the engine treats a missing key as 0.0 (assets.py:552), so "the displayed score is the sum of the lines
  shown" holds only if the missing line contributed 0; say so in the code comment and test.
- P3-4 "Recent move ... over the last 5 days" (line 130): `momentum_days` is a window of bars, so 5 trading days for shares and 5 calendar days for
  crypto; not verified which. If bars, write "5 trading days" or "5 sessions" for non-24/7 classes.
- P3-5 "a date on the calendar, not a forecast" (line 132): earnings dates can be provider estimates that move; add "dates can change" (note "may" is banned).
- P3-6 Source names (line 129, "MarketWatch, Financial Times"): naming publishers next to a score may read as endorsement; label "matched news sources".

## Checked and found sound

- Weights 35/30/20/15 equal `_W` x 100 (assets.py:205); 25,504 appears in CONFIDENCE.md s13 as stated (but see P1-1).
- `_swing_words` bands (big >= 3.0%, medium >= 1.5%, small otherwise) match the examples: 3.5, 3.3, 14.4 big; 1.6 medium; 0.4 small.
- Catalyst applies to equities only; the non-equity sentence is accurate; no card text uses the word-list tone (CONFIDENCE.md s9).
- Example point sums equal the stated scores (75, 66, 54, 44, 7).
- Past-tense "Rose/Fell" with "size counts, not the direction" is consistent with the `_plain_read` rule; no future tense in templates.
- GOING_LIVE not mentioned; no model output on the card.

## Summary

No P0. Three P1 items need a spec change before Architect: the footer's research sentence overstates a null result that
CONFIDENCE.md says can rule out only large effects (and omits that it is a before-cost, overlapping, 113-instrument replay), "something is happening here"
is a claim shown even on a 7 / 100 row, and the scheduled-date line says "no earnings date" while the catalyst decays and can still score. P2 items
are mostly precision: "usually moves" describes a GARCH forecast, "more coverage than usual" has no baseline in `news_level`, "worth a look" with "1st of 129" reads as a pick list, frozen
"ago" times, the dangling Learn pointer for the volatility note, the "CONF" label, and a W3 list that whole-word matching lets inflections and advice synonyms
(recommend, best, top, bought, gains) slip past. No banned word from the current list appears in the templates, examples or docs paragraph. The
SEC/FINRA and ESMA/BaFin wording questions (heading "worth a look", ranking, Buy/Short beside the card) are flagged for a qualified person, not ruled on.
