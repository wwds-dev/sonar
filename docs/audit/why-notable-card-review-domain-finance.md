# why-notable-card: Review-phase domain-finance consult

- Date: 2026-11-18
- Role: domain-finance (read-only consult)
- Branch: claude/build-why-notable-card @ 3435566
- Prior review: docs/audit/why-notable-card-domain-finance.md (Design)
- Method: read the diff, and ran `build_card` directly on the recorded fixture to reproduce the edge cases. The test suite was not run by this consult (not verified here).
- Jurisdiction: unverified. Nothing here is a legal ruling.

Verdict: the built copy matches the agreed wording, with two exceptions that must be fixed before release (P1). There is no P0.

## P1

### P1-1: the earnings line says more than SONAR checked (`ui/why_card.py:283`)
- String: `"No earnings date within the next {2 * days} days."`
- The earnings calendar looks only 14 days ahead (`sonar/events.py:43`, refresh at `:107-124`), but the window in the sentence grows with the horizon. On the 20-, 60- and 250-day horizons the card says "within the next 40 / 120 / 500 days" (reproduced).
- If the calendar fetch failed and nothing is cached, every share shows this same sentence.
- Rules broken: W1 (facts only), W4 (a low score is not reassurance), and the data-provenance duty in app-context. Only part of Design P1-3 was carried through.
- Fix: write "No earnings date in the next {min(2d, 14)} days of SONAR's calendar." When the calendar is empty or was never fetched, write "Earnings calendar not available."

### P1-2: Learn still says "something is happening" (`static/docs.html:496-497`, from spec line 338)
- String: "The card says what the score leaves out, on every row: it says something is happening in that market."
- Design P1-2 asked for this phrase to be removed. Only the footer was fixed.
- The sentence makes a claim the score cannot support, even on a 7 / 100 row. It also contradicts the footer, which says the score "counts what was found".
- Fix: "On every row the card also says what the score does not tell you: it does not say which way the price goes next…"

## P2

### P2-1: Learn keeps "how much it usually moves in a day" (`static/docs.html:491`)
- Design P2-1 was not carried into Learn. The card itself says "SONAR's estimate of its daily swing".
- Fix: use the card's wording.

### P2-2: the 25,504 figure is hard-coded and nothing checks it (`ui/why_card.py:33-34`)
- The figure is correct today (`CONFIDENCE.md:580`), but no test ties it to CONFIDENCE.md §13 (Design P1-1).
- Fix: add a test that "25,504 setups" appears in CONFIDENCE.md §13, and that `FOOTER` equals the quote in the spec.

## P3

- **Sign on a zero move** (`why_card.py:251-253`): "Rose 0.0% …" appears for any move under 0.05%. Fix: pick the verb from the rounded figure.
- **"Days" wording** (`why_card.py:253`): the 1-day horizon reads "over the last 1 days". For shares the window counts trading days (`sonar/assets.py:418`). When the price feed is cut short, the code uses a shorter window (`assets.py:420-424`) but the card still prints `{days}`. Fix: write "1 day", say "trading days" for shares, and pass in the window actually used.
- **Fallback points** (`why_card.py:313-319`): one-decimal points are shown with no note, so they may not add up to the score (W5). Fix: add the note "Points shown unrounded; they may not add to the score."
- **Non-share rows with an earnings value** (`why_card.py:211`, `:275`): if such a row ever carries a value, its points show next to "never score here". Fix: force the value to zero where the data is produced, and test the points too (test at `tests/test_why_card.py:405` checks only the text).
- **Title rank** (`why_card.py:289`): the rank is taken from the one-decimal score, so two rows that both show "75" can be ranked 1st and 2nd. Fix: rank on `displayed_score`.
- **Learn on comparisons** (`docs.html:492-494`): "compared with other markets of the same kind" leaves out the fixed-size part of the score. Fix: write "partly compared with …".
- **W8 pointer**: the volatility sentence points to Learn section 5, but section 5 only repeats "open question". The evidence is in §11 and in CONFIDENCE.md §10a. Pointing to §11 would keep the sentence neutral.
- **Banned-word test gap**: "momentum" is missing from the list at `tests/test_why_card.py:25-33`. No plain card text uses it today.
- **Open from Design**: P3-5 (earnings dates can move, and the card does not say so) and P3-6 (news sources have no label).

## Checked and sound

- Footer and the W8 sentence match the approved text exactly.
- The 25,504-setups claim is worded as approved.
- Owner decision 3 is followed: Rose/Fell plus "size counts, not the direction", and "Moved" at zero.
- Expert title shows NOTABILITY, and the labels say EARN / "Earnings date".
- News-level sentences use the constants from `sonar/assets.py`.
- Move and swing ranks use the same quantities as the score. Ties get a shared rank. Missing values show "Not available" with no rank.
- The stale-row line shows an absolute time.
- The card is identical with or without an Anthropic key.
- The banned-word check catches word forms and covers Learn, the tooltip and the accessible name.
- P2-10 (Buy/Short labels) is parked in TODO.md. Whether "Worth a look" plus the rank reads as a pick list still needs a qualified person.
