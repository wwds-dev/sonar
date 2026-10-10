# T0-2 review — code-reviewer, 2026-10-10

Read-only review of the uncommitted diff on `fix/t0-2-book-locking`. Playbook still
`status: baseline`. The reviewer ran the new tests against HEAD (pre-fix): all 5 failed twice
(`list.remove`, `FileNotFoundError`, rescan overlap). With the fix the races are forced by the
broker gate, not timing.

**Lock order — no deadlock found:** `_rescan_lock` → `book.lock` → `Live.lock`; `Live.lock` →
`engine.lock`. `ui/app.py` and `server.py` only copy attributes under `live.lock`; the engine
never refers back to `Live`. No network under the book lock today (`default_broker()` unused).

**P0: none. P1: none.**

| ID | Finding | Outcome |
|---|---|---|
| P2-1 | Book state published after `book.lock` released: an older mark pass overwrote a newer trade's view (0 open shown, 1 held) until the next rescan (reproduced) | Fixed: publish inside `book.lock`; `test_an_older_mark_pass_never_hides_a_newer_trade` |
| P3-1 | Lock-order comment contradicted the code | Fixed: comment states book → `self.lock`, `self.lock` → engine |
| P3-2 | `trade`/`close_position` captured `book` but `_mark_book` re-read `self.book` | Fixed: `_mark_book(..., book=book)` |
| P3-3 | `test_engine.py:432` asserted a `state.tmp` that can no longer exist | Fixed: `glob("*.tmp")` |
| P3-4 | Per-writer temp names leave a new orphan per killed save; legacy `*.tmp` never cleaned | Fixed: `paths.sweep_temp_files` on load, files older than 10 min; test |
| P3-5 | `config()` counted `book.open` without the lock | Fixed: `_protocol_open()` under `book.lock` |
| P3-6 | `_trade` docstring said "nothing to wait on" | Fixed: says it can wait on a mark pass, and why a network broker would need a thread |
| P3-7 | No tests for protocol cap vs manual trade, `attach_llm_read` vs `tick`, ConfigThread rescan queued behind the engine's | Deferred: recorded in the spec's residual risk |
