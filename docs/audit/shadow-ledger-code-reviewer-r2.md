# Code review r2: shadow ledger fix loop 1 (diff 3182ada..4ada4d1)
Reviewer: code-reviewer, read-only, 2026-10-13, HEAD 4ada4d1. Saved by the orchestrator from the
agent's report, condensed. Playbook `status: baseline` (stale). Synthetic data only.

## Summary
1. No P0 or P1. Every round-1 P1 and P2 from the three reports is fixed, and every P3 the loop
   claims; the round-1 probes now give the expected results.
2. Two new P2s in the new anchors. Both fail safe, but the recovery the UI gives leads nowhere:
   restoring the newest daily backup usually gives `LedgerBehindError`; a deliberate book reset cannot
   start a new record without deleting the old record's backups.
3. Three new P3s: merge and reader use different constants; a failed anchor save after adoption is
   not retried; copy nits.
4. Engineer notes accepted: the book check runs with no marker even with a sidecar (the sidecar
   belongs to the directory, not the book); the stop probe's marker and empty file are written at open,
   before the fetch, and nothing is recorded or published after the stop.
5. Targeted run (`test_shadow_ledger`, `_engine`, `_ui`, `test_calibration`, `test_portfolio`,
   `TEST_BUDGET_S=900`): exit 0, 399 passed, 31 deselected. Full suite, slow and ruff not run.

Evidence: scratchpad `cr2/probe/test_probe_cr2.py` (`cr2/probe.txt`), `cr2/probe/boundary.py`,
`cr2/probe/looks_const.py`; `cr2/t1.txt`.

## Prior findings
| Finding | Status | Evidence |
|---|---|---|
| CR P1-1 foreign marker-less ledger adopted | Fixed | `read`/`LedgerIdError`, no marker written; `ledger_belongs` `core.py:774`; `test_cr_p1_1_*` |
| CR P2-1 / SEC P2-2 marker dropped then file lost | Fixed | sidecar-only and backups-only anchors give `missing`; `Portfolio._other` keeps unknown keys (`portfolio.py:232,240`) |
| SEC P2-1 erratum overwritten mid-tenure | Fixed | `_shadow_ledger_refresh` (`core.py:841`) before each pass and write; residual few-ms window before `write_atomically` (`:884-886`), covered by "edit with agent stopped" |
| SEC P2-3 / CR P3-3 writes the reader refuses | Fixed | per-record checks in `ledger_merge`; read-back before write (`core.py:871`); `test_sec_p2_3_*`. Gap: P3-N1 |
| CR P3-1 write after stop | Fixed | `_may_write_shadow` (`core.py:689`) checks `EngineLock.held` |
| CR P3-2 marker/file crash window | Fixed | empty file right after anchors |
| CR P3-4 constants key change unreadable | Partly | keys added/removed → mismatch; a changed `looks` value is unreadable again (P3-N1) |
| CR P3-5 / domain P3-1 warning on blocked look | Fixed | probe |
| CR P3-6 / SEC P3-5 env vars in tests | Fixed | `conftest.py:209-210` |
| CR P3-7 Build note 14 | Fixed | |
| SEC P3-1 errata cost / screen size | Fixed | indexed, capped at 1,000; look sizes enforced; screen slices |
| SEC P3-2 symlinks / special files | Fixed | `_read_regular` with `O_NOFOLLOW\|O_NONBLOCK`, `S_ISREG`, bounded read; tests |
| SEC P3-3 restored backup drops looks | Fixed as asked; creates P2-N1 | `LedgerBehindError` (`core.py:782-784`) |
| SEC P3-4 case-sensitive guard | Fixed | `_folded` (NFD + casefold) |
| SEC P3-6 fsync | Deferred | `TODO.md:116` |
| SEC P3-7 recorded verdict trusted | Fixed | `_check_look`, `_check_looks_order`; UI `crossed is True` |
| Domain r2 P2-1, P2-2, P3-2, P3-3 | Fixed | new `SH_EXTREMES`, `SH_ERRATUM`, `SH_CAVEAT_NOT_ROBUST`, `SH_LOOK_NOT_ROBUST_NA`, `SH_ROW_PAST_LOOK_NA` |

## New findings
### P2-N1. After a loss, the newest backup is usually "behind", so "restore the newest copy" leads nowhere
`core.py:884` (`daily_backup` runs before the write), `:782-784` (behind → `read`); anchors count
entries (`calibration.py:926`). Copy `ui/app.py:685`, `:688`. Probe
`test_new_restore_newest_backup_after_a_loss`: day D's first write backs up the 3-entry file, then
records a 4th (anchor 4); file lost; restoring `…bak.<D>` gives `LedgerBehindError` for good. Entries
are decided most days, so this is the normal case. **Fix:** count only `looks` in the anchors (lost
entries are re-decided from the same closes, L-2); copy the file locally and off-site right after any
write that adds a look; test "lose on day D, restore the newest copy".

### P2-N2. A deliberate reset cannot start a new record without deleting the old record's backups
Anchors `core.py:749-751` (backups), `:812` (sidecar); copy `SH_LEDGER_FOREIGN` (`ui/app.py:680`).
Probe `test_r1_p1_foreign_and_then_the_reset_path`: after deleting `portfolio.json`, book B gets
`LedgerIdError` (right); moving the file aside gives `missing` "though this book had one since 12 Oct"
(false: the sidecar anchors the directory); moving the sidecar too still gives `missing` because of
`shadow_ledger.json.bak.*`. A fresh start means deleting up to 7 local and 30 off-site backups, which
destroys the history G3 meant to keep. **Fix:** a documented retire step that keeps the old record
(e.g. `shadow_ledger.retired.<id>.json`, or `shadow_ledger.reset` naming the old id); anchors and
backups carrying a retired id do not block a new record. Name the steps in `SH_LEDGER_FOREIGN`, the
README reset paragraph and the spec's Failure modes table (which lacks rows for the sidecar, backups
and behind). End-to-end reset test.

### P3-N1. The merge and the reader use different constants
1. Boundary: the merge checks a new look against today's `SHADOW_BOUNDARY` (`calibration.py:1162`);
   the reader uses the file's `constants.boundary` (`:1067-1068`). Probe `boundary.py`: merge adds,
   read-back refuses → `("write", "LedgerFormatError")` on every pass, nothing recorded again.
2. Look sizes: `_check_look` requires `n == SHADOW_LOOKS[k-1]` from the module (`:1002-1003`). Probe
   `looks_const.py`: changing the module's looks makes a valid file unreadable instead of a constants
   mismatch (ADR §7).
**Fix:** take `boundary` and `looks` from the file's constants (when well-typed) in both places; tests.

### P3-N2. A failed anchor save after adoption is not retried
`core.py:790` ignores `_shadow_ledger_anchor`'s result; `_ledger_problem` clears next pass (`:643`).
Fails safe (the sidecar still anchors). **Fix:** a "needs anchor" flag retried each pass.

### P3-N3. Copy nits
`SH_LEDGER_REFUSED` (`ui/app.py:695`) says "1 results" and counts refused looks as "results"
(pinned at `test_shadow_ledger.py:1349`); expert `SH_ERRATUM` says "look none" and "look 1 and 2".
**Fix:** singular/plural keys; "no look" / "looks 1 and 2".

## Checked and holding
Refresh (symlink swap or unreadable → `read`; deleted → `missing`; other id never written over; same
id: errata carried; behind: the fuller copy written back). Anchors (marker/sidecar id disagreement →
`LedgerIdError`; counts take the larger; anchors written after the file; young-anchor retry only at 0/0
and once per tenure). `Portfolio._other` (known keys win). UI slices and `is True` checks; no new string
claims edge, profit or certainty.
