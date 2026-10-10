# Spec: T0-1 — a lock takeover keeps the holder's book

- Status: built (branch `fix/t0-1-lock-takeover`)
- Owner approval: delegated in chat 2026-10-10 ("go on with T0-1, only pause when … you need
  my decision"); Define and Architect gates not held separately.
- Source: `docs/audit/code-review.md` P0-1 (reproduced), `docs/audit/architecture.md` P0-1, P1-1.

## Problem
`Live.__init__` loaded `Engine` and `Portfolio` before holding the engine lock. A window that
followed the launchd agent for hours kept that launch-time copy when it took the lock over, and
its first save (a settle, a scored hour, a mark) wrote it over every trade, scored hour and cash
move the agent had made. Two smaller paths broke the same rule, *only the lock holder writes*:
`--risk` saved `state.json` from `__init__`, and a second window with no holder URL to follow
could still trade, close, change risk or flip the protocol into the shared files.

## Success measure
- After a takeover, the in-memory engine and book equal what the holder left on disk, and a save
  preserves it (`test_a_takeover_keeps_what_the_holder_wrote`).
- No write between taking the lock and re-reading the book
  (`test_nothing_is_written_between_taking_the_lock_and_re_reading_the_book`).
- `--risk` is persisted only once the lock is held
  (`test_a_risk_asked_for_at_launch_is_saved_only_once_the_lock_is_ours`).
- A window with nothing to follow writes none of `state.json`, `portfolio.json`, `protocol.json`
  (`test_a_window_with_no_holder_to_follow_does_not_write_the_book`).
- Each test fails when its part of the fix is reverted (4 of 4 planted mutations caught).

## Non-goals
Thread locking of `Portfolio`/`Engine` (T0-2), stale-lock reclaim race and PID reuse
(architecture P1-3, code P3-8), state schema versioning.

## Architecture
- `Live._take_the_book()` runs in `run()` right after the lock is obtained, on both paths (first
  acquire and takeover). It rebuilds `Engine` and `Portfolio` from disk, reloads `protocol.json`,
  applies a pending `--risk` (now persisted under the lock), recomputes calibration and the
  positions payload (priced off the last board seen), and only then clears `read_only`.
- `_wait_for_lock` no longer clears `read_only` on acquire; it clears `following` so nothing is
  forwarded to a gone holder. Between acquire and re-read, actions refuse.
- `trade`, `close_position`, `configure`, `set_protocol` refuse while read-only with no holder to
  follow, with the sentence "another SONAR is driving this book, so this one is read-only until
  it stops".
- Rebinding `self.engine`/`self.book` is safe: nothing outside `core.py` holds them (grep).
- Decision taken without asking: a `--risk` passed to a process that waits still wins when it
  takes over (the pre-existing "command line wins" rule), it is just saved later.

## Residual risk
`Live()` constructed without `run()` (tests, a window before its engine thread starts) can still
write before any lock exists. Pre-existing, milliseconds wide in the app; left as is because
tests rely on driving a bare `Live()`.

## Review
`docs/audit/t0-1-lock-takeover-code-reviewer.md`: no P0/P1. P2-1, P2-2, P3-1, P3-2, P3-3 fixed
with tests (protocol day stamp re-read; UI knobs resync after a refusal or takeover; status line
reset on takeover; a failed re-read is shown and retried; `_forward` uses the URL the caller saw).
P3-4 deferred (see Residual risk). P3-5 decided by the owner (see Decided).

## Decided
`--risk` on a process that waited still wins when it takes over (owner, 2026-10-10: keep the
current rule). The launchd agent passes no `--risk`, so this only affects manual runs.

## Verification
Full suite 1,590 passed natively and under `QT_QPA_PLATFORM=offscreen`. 8 planted mutations, 8
caught. Docs test count 1,582 → 1,590; `static/testplan.html` rebuilt. Security phase skipped:
the change removes writes and touches no network, auth or untrusted input.

## CHANGELOG draft (add when a build with this is installed)
**A window taking over from the agent no longer overwrites the agent's book.** The window loaded
the book at launch and, after following the agent for hours, saved that copy over everything the
agent had done once it took over. It now re-reads the book the moment the lock is its own, and
nothing writes before that; `--risk` is saved only under the lock; a second window that cannot
follow refuses trades and settings instead of writing beside the engine that drives.
