---
role: domain-finance
domain: Finance (retail investing, trading and money figures)
last-reviewed: 2026-11-11
status: current
---

# Playbook: domain-finance

Canonical copy lives in the Foundry repo; apps receive it via `install.sh --update`.
Changes come from `radar/reports/` and need owner approval. Domain practice only: facts about
one app belong in that app's `app-context.md` (`## Domain specialist`).

## Scope
What an app may claim about returns, risk and advice; correctness of money arithmetic;
disclosure, provenance and record-keeping of financial figures.

## Current practices
_Baseline: seeded from the agent prompt and general practice; not yet verified by a radar run._
- Simulated or paper results are labelled as such wherever they are shown, and never presented
  as returns a user could have achieved.
- A performance figure states its period, sample size and how costs, fees and slippage were
  treated; no cherry-picked windows; the past-performance caveat sits next to the number.
- No personalised advice or recommendation wording unless the app is authorised to give it:
  "should buy", "guaranteed", "risk-free", "edge", "beat the market" are red flags in copy.
- Money in decimal or integer minor units with an explicit rounding mode and a currency on
  every amount; time zones, trading calendars and corporate actions explicit.
- Every displayed figure is traceable to its source and timestamp; stale data is marked stale.
- Public posts, READMEs and screenshots about an app never show a direction, target or rating
  for a named instrument as the app's or the owner's view. Where a screen that asserts a
  direction is shown publicly, the instrument is anonymised or the post carries the model's
  measured skill, sample and 'not a recommendation; paper trading only'. In the EU a specific
  public view on an instrument can be an investment recommendation under the Market Abuse
  Regulation, with disclosure duties even for unlicensed persons.

## Watch list
SEC Marketing Rule and FINRA communications rules (performance advertising); ESMA and BaFin
guidance on investment advice, finfluencers and retail trading; MiFID II suitability and
appropriateness; CFA Institute GIPS.

## Change log
- 2026-10-12: seeded (baseline).
- 2026-11-11: first radar review (current), from `radar/reports/2026-11-11-rest.md`, owner-accepted row D1. P3 rows (D2, D3, D4) not applied.
