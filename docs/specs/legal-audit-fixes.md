# Spec: legal audit code and copy fixes

- Status: merged to `master` (`f6acacc`, `d3ad14b`); the hourly-model note added on `master` 2026-11-11
- Source: Foundry's first legal audit of SONAR, `foundry/audits/sonar/legal.md` (findings 1, 3, 4, 5, 7, 8, 9);
  drafts D3, D4, D5, D2 in the legal pack (`docs/legal/terms.md`, untouched here).
- Owner approval: task given by the owner's orchestrating session 2026-11-10; commit and push are the owner's.
- Phases: Define (this note), Design/Architect skipped (copy and packaging only; no state, concurrency or
  module change), Build, Verify (suite in both Qt modes plus the rate pass; packaged build and `--selftest`),
  Secure (packaging touched: the bundle now loses a Qt plugin and gains static text files; no network,
  secrets or input), Document (README, Learn §13/§14, CHANGELOG, TESTING counts), Comply: the pack in
  `docs/legal/` is not edited here; the owner re-reads it and signs.

## Change
| Finding | Change |
|---|---|
| 3 | `words.PLAYMAKER_NOTICE` at the top of the Playmaker tab; "Not betting advice" in Learn §14 and `sonar/playmaker/README.md` |
| 4 | `words.STAKE_TIP` replaces the "without risking ruin" tooltip |
| 5 | `words.LLM_READ_TITLE`, `MODEL_READ_TITLE`, `AI_TAG`, `DIRECTION_NOTE`; plain and expert modes both carry "AI-GENERATED" |
| 5 (second half, 2026-11-11) | `words.HOURLY_MODEL_NOTE` under the Lab's hourly BTC figures (`_terminal_tab`): not a recommendation, disagreement with the market not shown to be an edge |
| 7, 8 | `build_app.sh` strips Qt Virtual Keyboard and ships `packaging/licenses/`; `main.py --selftest` checks both |
| 9 | `SUPPORT.md`, `SECURITY.md` |

## Non-goals
Lawyer triggers, the name, unofficial endpoints (11), the `.venv` (10), the helpline line in D3 (owner to source).
