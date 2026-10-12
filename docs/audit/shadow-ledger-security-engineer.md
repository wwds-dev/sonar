# Security review: shadow ledger (ADR 0002 Amendment 1)
- Role: security-engineer, read-only. Diff `bdd8a2b..8c27183`, 2026-10-12. Saved by the orchestrator
  from the agent's report, condensed; findings and evidence unchanged.
- Playbook `docs/playbooks/security-engineer.md` is `status: baseline` (stale).
- Probes (scratch, not in the repo): session scratchpad `sec/probes/` — `test_sec_probe.py`
  (engine-level), `p1_asym.py`, `p2_nan.py`, `p3_size.py`, `p4_case.py`, `p5_ui.py`.
- Test run: `tests/test_shadow_ledger.py tests/test_shadow_ui.py tests/test_shadow_engine.py`,
  `TEST_BUDGET_S=900`: exit 0, 215 passed. Full suite not run by this role.
- Not touched: `~/Library/Application Support/SONAR`, any copy of the real book, the agent. No
  `SONAR*` environment variable is set.

**Summary.** No P0 or P1. Three P2s, all integrity problems with the write-once record, each
reproduced on a scratch `SONAR_DATA`. Seven P3s, mostly hardening. Parsing, markup safety,
follower and read-only gating, `/api/book` exposure and temp-file handling held up. No dependency
changed.

## Threat model
- Assets: the pre-registered record (entries, looks, errata); `portfolio.json` and its marker; the
  local and off-site backups; scan-thread availability; paper-book data on loopback.
- Boundaries: (a) disk → engine (the ledger and marker are hand-editable by design, so untrusted);
  (b) builds of different versions sharing one data directory (window vs agent, rollback);
  (c) holder → follower over `/api/book`; (d) Yahoo closes → outcomes persisted for good;
  (e) the test suite vs the live data directory.
- Entry points: `Live._shadow_ledger_open` (`sonar/core.py:639`), `_shadow_ledger_mark` (`:701`),
  `_shadow_ledger_record` (`:716`); `Portfolio._load`/`save` (`sonar/portfolio.py:223`, `:235-236`);
  `calibration.ledger_parse`/`ledger_marker_parse`/`ledger_merge`/`ledger_errata`
  (`sonar/calibration.py:997`, `:1045`, `:1057`, `:1126`); `GET /api/book` (`sonar/server.py:177-182`)
  → `_mirror_book` → `shadow_texts`/`_sh_ledger_lines` (`ui/app.py:864`, `:946`);
  `tests/conftest.py:52-82`.
- STRIDE: tampering P2-1, P2-2, P3-3, P3-7; denial of service P2-3, P3-1, P3-2; information
  disclosure none new; spoofing pre-existing (P3-7); repudiation accepted (not tamper-evident, spec
  Risks); elevation none.

## Findings
### P2-1. An erratum added by hand while the holder runs is silently overwritten
`sonar/core.py:653-654` reads the ledger once per tenure; `:725-733` merges into the in-memory copy
and rewrites the whole file. Probe `test_probe_hand_added_erratum_is_lost_while_holder_runs`: look 1
recorded → erratum appended on disk → new entry + `_shadow_pass(NOW + DAY)` → errata on disk `[]`.
The documented correction path loses the correction with no trace. **Fix:** before each write compare
the file with what this tenure last read or wrote (mtime_ns + size, or SHA-256); if changed, re-read
and re-parse, write only if the id matches, carrying its errata over; else `ledger_error: "read"`.
Document "stop the agent and the window before editing". Test: an erratum written mid-tenure
survives the next write.

### P2-2. An older build drops the marker; a lost file then starts a new ledger without a word
The pre-change `Portfolio.save` writes only `starting_cash`, `cash`, `open`, `closed`, `equity_log`
(`git show bdd8a2b:sonar/portfolio.py`), so any older build that saves the book strips
`shadow_ledger`. `sonar/core.py:674-680` then treats "no marker, no file" as a fresh start.
`sonar/portfolio.py:648-656` explicitly supports mixed versions (rollback, agent a commit behind).
Probe `test_probe_older_build_save_drops_marker_then_lost_file_restarts_silently`: `ledger.error is
None` and a new `ledger_id`. **Fix options:** (a) refuse a fresh start when the book shows history
(protocol entries decided long ago, or any `shadow_ledger.json.bak.*` locally or off-site); (b) keep
unknown top-level keys in `Portfolio._load`/`save` so future rollbacks cannot strip it; (c) a sidecar
marker that old builds do not rewrite. Test: an unknown top-level key survives a save.

### P2-3. The engine writes records its own parser rejects
`ledger_merge` (`sonar/calibration.py:1057-1090`) copies readout fields as they are; `_check_entry`
(`:962-975`) rejects an empty or >64-character symbol or id and a direction other than
`LONG`/`SHORT`. The write path (`sonar/core.py:731-733`) never parses what it writes. `p1_asym.py`:
write OK, parse `LedgerFormatError` for each of those. End to end
(`test_probe_write_ok_then_unreadable_after_restart`): first tenure fine, after restart
`{'error': 'read', 'reason': 'LedgerFormatError'}` for good. `p2_nan.py`: a NaN/inf `rr`, `stop` or
`confidence` makes `json.dumps` raise, so `ledger_error: "write"` on every pass (fails safe, but blocks
every good entry). **Fix:** validate each new entry and look in `ledger_merge`, leaving out and
counting any that fail; and run `ledger_parse` on the serialised text before `write_atomically`,
reporting `("write", reason)` instead of writing. Tests: 65-character symbol, lowercase direction,
NaN `rr`.

### P3-1. Errata cost grows quadratically; errata, mismatch and look lists unbounded on screen
`ledger_errata` (`calibration.py:1126-1136`) scans errata × every member of every look on every pass;
`ui/app.py:960`, `:969`, `:892` do not slice. `p3_size.py`: 8,000 errata + an 8,000-member look
(1.4 MB) take 6.5 s per pass under `_rescan_lock`; `p5_ui.py`: 50,000 errata give 1.3 s and 6.8 MB
of label text at 1 Hz. **Fix:** index member ids per look; cap errata in `ledger_parse` (e.g. 1,000)
and members at `SHADOW_LOOKS[k-1]` (require `n == SHADOW_LOOKS[k-1]`); slice in `shadow_texts`.

### P3-2. The read path follows symlinks and special files
`sonar/core.py:666-668`: `stat().st_size` then `read_text()`, both following links, no type check. A
FIFO or a link to `/dev/zero` passes the size check (0) and then blocks or reads without end on the
scan thread. Not run. **Fix:** `os.open(O_RDONLY | O_NOFOLLOW | O_NONBLOCK)`, `fstat`, require
`S_ISREG` and size ≤ max, `read(max + 1)`.

### P3-3. Restoring the newest daily backup can drop recorded looks
`paths.daily_backup` copies before the first write of a day (`core.py:732`), so a look recorded by
that write is not in that day's `.bak`. A restored older file with the right id is accepted, and the
look is evaluated again with a new date. **Fix:** a monotonic summary in the marker (counts of
recorded looks and entries, or a hash of `looks`); a file behind it is a `read` error. Or back up
right after any write that adds a look.

### P3-4. The fixture guard can be bypassed with letter case on APFS
`tests/conftest.py:58-64` compares text, then `realpath`, which does not fold case. `p4_case.py`:
`…/LiveStandIn/x` refused, `…/livestandin/x` allowed. **Fix:** compare casefolded paths or
`(st_dev, st_ino)` of the nearest existing ancestor; add a mis-cased case to L-18.

### P3-5. `isolated_state` does not clear `SONAR_BACKUP_DIR` (pre-existing)
`tests/conftest.py:181-192`. With it exported, a test's `daily_backup` → `_copy_offsite`
(`sonar/paths.py:54-66`) can overwrite a real off-site copy of the same name and prune real ones.
Not verified (variable unset here). **Fix:** `monkeypatch.delenv` both `BACKUP_DIR_ENV` and
`DATA_ENV` in `isolated_state`.

### P3-6. No fsync before the atomic rename (pre-existing)
`sonar/paths.py:103-117`. After a power loss the renamed file can be empty (fails safe as `read`,
recovery then meets P3-3). **Fix:** flush + `F_FULLFSYNC` before `replace`, fsync the directory.

### P3-7. A recorded look's verdict is trusted as written
`_check_look` (`calibration.py:978-994`) checks types only; `shadow_looks` (`:664-674`) returns
`crossed`/`design_closed` as recorded; `ui/app.py` `_sh_look_status` tests `crossed` by truthiness.
A hand edit (`"crossed": true` with `z: 0.3`, or `n` not 45/101/201) shows "crossed … The test ends
here". **Fix:** in `ledger_parse` require `n == SHADOW_LOOKS[k-1]`, `crossed ⇒ |z| ≥ boundary` (and
the robust rule when `n_excluded > 0`), and `design_closed` consistent with earlier crossings; in the
UI require `is True`.

## Checked, no finding
- Text to the screen: only an erratum's `reason`, through `_clean(…, 80)`; `ledger.reason` is always
  an exception class name; symbols and ids are not shown; labels stay `Qt.PlainText`; no shadow data
  reaches `sonar/llm.py`.
- Parsing: NaN/Infinity rejected; oversized ints rejected; deep nesting caught; undecodable text
  caught; exact key sets; whole-file rejection; 64 MB cap; timestamps clamped in the UI; ledger
  entries join only when their id is in the book (`calibration.py:783`).
- Marker round trip: kept verbatim; a damaged marker is `read` and nothing is written; a failed
  marker save restores `None` (`core.py:707-711`); the rest of the book untouched.
- Follower and read-only: gated (`core.py:598`); reset in `_take_the_book` (`:1319-1325`); one writer
  by the engine lock; L-8 covers both roles.
- Files: per-writer temp names; sweep removes only old `shadow_ledger.json.*tmp`; `write_atomically`
  replaces a symlink rather than writing through it; own backup stem (7 local, 30 off-site); `read`
  and `missing` never write.
- `/api/book`: new fields are the user's own paper data and class-name reasons; nothing secret, no
  paths. Per-entry barriers for every protocol position add about 300 KB a year to the payload.
- Dependencies and packaging unchanged; no eval/exec/pickle/subprocess/rich text added. `pip-audit`
  not installed, no CVE scan.

## Not verified
P3-2's hang, P3-5 with a real `SONAR_BACKUP_DIR`, P3-6's power-loss behaviour, Qt layout cost of a very
large label, the full suite.

**Verdict:** no P0 or P1. Fix P2-1 and P2-3 before release. P2-2 needs a decision (a marker that
survives a rollback vs refusing a fresh start on a book with history). P3s to the backlog; P3-1 and
P3-4 are cheap.
