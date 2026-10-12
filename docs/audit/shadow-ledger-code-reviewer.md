# Code review: shadow ledger (diff bdd8a2b..8c27183)
Reviewer: code-reviewer (read-only), 2026-10-12. Saved by the orchestrator from the agent's report,
condensed; findings and evidence unchanged. Contract: `docs/specs/shadow-ledger.md` and ADR 0002
Amendment 1. Synthetic data only; nothing under `~/Library/Application Support/SONAR` was read.
Playbook `docs/playbooks/code-reviewer.md` is `status: baseline` (stale).

Evidence: `TEST_BUDGET_S=900 … ./run-tests.sh tests/test_shadow_ledger.py tests/test_shadow_engine.py
tests/test_shadow_ui.py tests/test_calibration.py -q` → exit 0, 335 passed, 31 deselected. Probes:
session scratchpad `cr/probe/test_probe_cr.py`, output `cr/probe.txt` (repo `scratch_data` fixture).
Full suite, slow and offscreen not re-run by this role.

## P0
None.

## P1-1. A ledger with no marker is adopted even when it belongs to another book
`sonar/core.py:693-695` (`_shadow_ledger_open`, "no marker, file present"; engineer Build note 7; no
row in the spec's Failure modes table). Probe `test_a_foreign_ledger_is_adopted_after_a_book_reset`:
book A records look 1 crossed (z +70.08); `portfolio.json` deleted (README:266's reset); book B with 45
new entries and flat closes; the next pass adopts the file, writes the marker back, and shows "Look 1
of 3, recorded 12 Oct … crossed the line … The test ends here", with one "members" mismatch line.
Looks 2 and 3 are `design_closed`; book B can never record a look. **Fix:** adopt a marker-less file
only when it is empty or matches this book (recorded look members and entry ids among this book's
protocol positions); otherwise `("read", "LedgerIdError")`, never adopted or written. Test it.

## P2-1. The marker can be dropped silently, and then a lost file is a fresh start (S5)
`sonar/portfolio.py:223,236` (only builds that know the key keep it); `sonar/core.py:675-679` (no
marker, no file → new ledger); `:693-695` (adoption hides that it was gone). Probe
`test_marker_erased_by_an_older_save_then_file_lost_is_a_fresh_start`: `error: None`, a new ledger,
look 1 from z +70.08 crossed to z +0.08 not crossed, `recorded: True`; "backups present: []" on the
first day. **Fix:** a second anchor no older build rewrites (a sidecar `shadow_ledger.id`, or any
`shadow_ledger.json.bak.*` local or off-site): "no marker, no file, anchor present" → `missing`. Test.

## P3
1. **A pass can write after stop or lock handoff.** `core.py:606`, `:677/:694`, `:733`; nothing checks
   `_stop` after the fetch; `_run_locked` waits only `BACKGROUND_JOIN = 20 s` (`core.py:95`). Probe
   `test_a_pass_still_writes_after_stop_was_set`: "stop set: True ledger written: True marker: True".
   **Fix:** before the marker save and before `write_atomically`, return without writing or publishing
   if `_stop` is set or the engine lock is no longer held.
2. **The crash window between marker and file is the whole fetch-and-compute** (`core.py:675-686` vs
   `:733`). A kill there (e.g. an install restart on the first pass) and a next pass > 600 s later gives
   `missing` for good. Code reading, not reproduced. **Fix:** write the empty file right after the
   marker save in `_shadow_ledger_open`; keep the 10-minute rule as a backstop.
3. **The writer never checks what it writes against its strict reader** (`core.py:729-733` vs
   `_check_entry`/`_check_look`). No production trigger found (ids are 12 hex characters); insurance.
   **Fix:** `ledger_parse(text)` before `write_atomically`; on refusal report `("write", reason)`.
4. **A constants key added or removed makes the ledger unreadable**, not a "constants" mismatch
   (`calibration.py:1012`; a ledger missing `vertex_k_max` → `LedgerFormatError`). ADR §7 promises a
   mismatch. **Fix:** type-check `constants` as a mapping without requiring today's key set.
5. **The warning line treats an unrecorded or blocked look as a result** (`ui/app.py:1132`,
   `_sh_warnings`). Probe `test_warn_line_for_an_unrecorded_or_blocked_look`: "Note: 5 of the first 45
   … This look rests on the other 40." beside "worked out but not recorded yet". **Fix:** pass `blocked`
   and use `_sh_shown(lk, blocked)`.
6. **Tests can copy synthetic backups to the real off-site directory** (`tests/conftest.py`:
   `isolated_state` does not clear `SONAR_BACKUP_DIR`; only `scratch_data` does, `:75`). **Fix:**
   `monkeypatch.delenv(paths.BACKUP_DIR_ENV, raising=False)` in `isolated_state`.
7. **Doc nit:** Build note 14 says the file is written when "this tenure has not yet written it";
   `_ledger_unsaved` is True only for a new ledger (`core.py:686`, `:697`). Correct the note.

## Engineer departures, judged
- No-marker ledger adopted (Build note 7): not acceptable as built (P1-1); acceptable with a check
  against the book.
- Unreadable or missing ledger re-read each pass (Build note 6): endorsed (never writes; L-6, L-15).
- Payload without `recorded: true` never shown as a result (Build note 2): endorsed
  (`ui/app.py:844-848`); the one leak is P3-5.
- k > 12 split at the regression members' mean confidence (Build note 3): correct, and better than the
  spec (it is the exact slope extreme; counting `no_risk` in the mean would not be).

## Checked and holding
- Write-once: `ledger_merge` deep-copies and adds only absent final entries and absent evaluated
  unrecorded looks; only `price_tries` changes; L-4 (300 random cases, with parse round-trip). The
  engine writes only merge output, recomputes looks against the new record before publishing
  (`core.py:735`), and keeps the old record on a failed write (`:734`).
- Ordering: marker saved under `book.lock` (RLock; `save` is `@_locked`); file in the same pass;
  publish after write; followers and read-only return first (`core.py:598`, L-8); `_take_the_book`
  resets ledger state.
- Robust rule: z > 0 needs z_lo ≥ 2.315, z < 0 needs z_hi ≤ −2.315; missing extremes never robust;
  unchanged with no filled members (L-12).
- `extreme_z`: per-member min/max of `r_stop`/`r_target`; vertex order matches `xs`; `no_risk` out;
  `_hc3_z_at` matches `hc3_z`; k = 12, n = 201 takes 0.52 s.
- Grace and tries: counted only when the symbol was in today's fetch cache and `now ≥ t_T + 7 d`;
  persisted; a same-day restart does not double-count (L-10).
- S4: no z or crossing for an unrecorded look; `read`/`missing` blocks every look result.
- Marker round trip and older-file load; damaged marker → `read`. `ledger_parse` rejects NaN,
  Infinity, `1e999`, huge ints, deep nesting.

## Test gaps
Foreign or reset-book ledger with no marker (P1-1); marker loss then file loss (P2-1); a pass stopped
mid-fetch writes nothing (P3-1); a written ledger always parses back on real engine output (P3-3);
warning line withheld for unrecorded or blocked looks (P3-5).
