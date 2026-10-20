# providers-wiring: code review (2026-10-19)

Reviewer: `code-reviewer` (read-only). Saved by the orchestrator. The playbook is stale (`status: baseline`).

**Verdict:** ready to merge, with no P0 or P1.
- No importer or code reference to providers is left. `SONAR.spec`, `build_app.sh`, `packaging/`, `main.py` and
  `check_app.sh` are clean.
- The data path is unchanged: the `git diff --stat` for assets, backtest and core is empty.
- `diag_priority.py:68` `BLANK_KEYS` is intact and tested (`tests/test_diag_priority.py:200`).
- The comments are accurate.
- `tests/test_providers_docs_truth.py`, `test_state_recovery.py` and `test_diag_priority.py`: 202 passed (offscreen
  only).

## P2
- **P2-1.** Generic banned phrases ("is the fix", "No code needed", "highest-value", "provider layer") are checked
  across all of `TODO.md` and `CONFIDENCE.md` (`tests/test_providers_docs_truth.py:97-99, 102-106`), so unrelated
  backlog lines would fail the suite. Fix: keep the vendor-specific phrases global, and check the generic ones only
  in the README data section, docs.html §3 and `.env.example`, or only in sentences that name a provider.

## P3
- **P3-1.** `SAID_IN_BOTH` pins outage prose that the spec doesn't mandate (`:133-143`). Fix: keep SOURCE and DELAY
  verbatim, and reduce the outage checks to their key tokens.
- **P3-2.** The README splits raise a bare IndexError if the heading changes (`:169-175`). Fix: use `partition` with
  an assert message.
- **P3-3.** `SEED_RETRY_EVERY > 0 and SEED_MAX_TRIES > 0` is always true (`:153-158`). Fix: drop it.
- **P3-4.** The record lookup in CONFIDENCE is fragile (`:197-204`). Fix: an anchored line-wise regex on the bullet.
- **P3-5.** `"providers.py" not in README` bans every future history mention (`:122-123`). Fix: scope it to the
  module map.
- **P3-6.** Rewrap the `diag_priority.py:64-67` comment and cite `docs/specs/providers-wiring.md`.
- **P3-7.** `docs/specs/starved-engine.md:225-226` cites the deleted `providers.py`. Fix: add a "superseded" note.
