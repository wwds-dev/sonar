# build-traceability: model-validator review of A7 and ADR 0002 Amendment 2 (2026-10-19)

Reviewer: `model-validator` (read-only). Saved by the orchestrator. Checked by grep against 9aa9bd1; no tests were
run. The playbook is stale (`status: baseline`).

**Verdict:** sound, with no P0 or P1. The new build string for new records changes no pre-registered analysis,
grouping, look-1 readout or file already written.

**Checks:**
- Nothing that grades or checks the ledger reads `build`: `shadow_looks` (`sonar/calibration.py:664-674`),
  `ledger_check` (`:1246-1276`), `ledger_errata` (`:1278-1290`), member records (`:877`), and the readout drops it
  (`:768`).
- Old and new entries can be mixed, since validation is `_is_text` 1..500 (`:959-960, 1003, 1037, 1097`), so rollback
  is safe too.
- Nothing is rewritten: `ledger_merge` skips existing ids (`:1185, 1191, 1207`). `tests/test_shadow_ledger.py:307-313`
  already covers this.
- The architect's reader table holds up; only some test sites are missing from it (P3-3).

## P2
- **P2-1.** The forking-paths guard (`docs/adr/0002-shadow-time-stop-grade.md:299-301`) describes today's code but
  isn't a rule.
  - **Fix:** add to the ADR: "`build` is provenance only. It is never a grouping, filter or exclusion criterion for
    any look. A split by build is exploratory, reported as such, and outside the pre-registered family. A `~` or `?`
    entry is not excluded on that ground; a real code fault goes through errata."
  - Add a test that `shadow_looks` and `ledger_check` give the same output when `build` changes.

## P3
- **P3-1.** The `[:64]` cut can drop the trailing `~` dirty marker (`docs/specs/build-traceability.md:343-352`). Fix:
  put the flag right after the version (`v2.364~+…`), or shorten the commit fields, and add a test at the 64-char edge.
- **P3-2.** With no version, the fallback "unknown" throws away known commits. Fix: `unknown+<outer>/m:…`. Copy mode
  (`?`) still has no content digest; say so in the spec.
- **P3-3.** The reader table should also list the `created_by` tests (`tests/test_shadow_ledger.py:307, 2189-2193`),
  and note in one line that `self.build` is read once at start (`sonar/core.py:210`).
