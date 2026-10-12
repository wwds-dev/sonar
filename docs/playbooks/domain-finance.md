---
role: domain-finance
domain: Finance (retail investing, trading and money figures)
last-reviewed: 2026-10-12
status: baseline   # baseline = seeded, not yet verified by a radar run; becomes current after first approved review
---

# Playbook: domain-finance

Canonical copy lives in the company repo; apps receive it via `install.sh --update`.
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

## Watch list
SEC Marketing Rule and FINRA communications rules (performance advertising); ESMA and BaFin
guidance on investment advice, finfluencers and retail trading; MiFID II suitability and
appropriateness; CFA Institute GIPS.

## Change log
- 2026-10-12: seeded (baseline).
