# Spec: T1-11 — the docs agree with each other and with the app

- Status: built (branch `fix/t1-11-docs`). Owner approval: delegated in chat ("go on").
- Source: `docs/audit/docs.md` P1 1–6, P2 7–8, P3 15, 18. Docs only; no code. Independent review
  skipped (every claim edited was checked against the code or the study JSON as it was written);
  suite unchanged at 1,666 tests, green natively and offscreen.

## What changed
- **Study count:** README, the in-app manual, CONFIDENCE-adjacent text and GOING_LIVE now say the
  same thing: five directional nulls and one volatility-shaped survivor (the catalyst), not "five,
  all negative" in some places and "six, the first survivor" in others.
- **"6 of 6 blocks" corrected:** the catalyst effect was positive in 6/6 when first run and 5/6 on a
  re-run with fresh data (2026-10-10; the earliest block was slightly negative). The pooled effect
  survives cluster bootstrap; the claim now says both (model validation P1-2).
- **Stale references:** the "Docs button" (it is the Learn tab); "113 instruments" now says it is the
  set the study ran on and the board lists 129; the "next gaps" list in the testing section.
- **API table** lists every route, with the Host/Origin rule; **Layout** lists the real modules
  (`macro/`, `playmaker/*`, `research/*`), `tests/`, `scripts/`, `packaging/`, `docs/`, the study outputs.
- **Onboarding:** a "What you do first" block; setup says Python ≥ 3.11, `uv`, macOS only, where keys go.
- **GOING_LIVE** closing rewritten from first-person assistant prose to a neutral status.
- **SUGGESTIONS** ids made unique (the Interface table's repeats are `I-9`, `I-10`, `I-15`).

## Not done (recorded in the audit, P3)
README sprawl (1,100 lines; design history to move out), jargon glossary at first use, `TODO.md` open/done
split, Finnhub status in three files, `.env.example` and a LICENSE, the "Revolut" aside, a v2.103
example label. The `docs/audit/docs.md` list stays the checklist.
