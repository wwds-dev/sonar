# T0-1 review — code-reviewer, 2026-10-10

Read-only review of the uncommitted diff on `fix/t0-1-lock-takeover`. Playbook
`docs/playbooks/code-reviewer.md` is `status: baseline`. `test_follow.py` 19/19 twice; reviewer's
own mutations (restore `read_only=False` on acquire; drop the Portfolio re-read) were caught.

**P0: none. P1: none.** No remaining path where a process not holding the lock writes
`state.json`/`portfolio.json`/`protocol.json` once `run()` entered `_wait_for_lock`; nothing
outside `core.py` holds the old `engine`/`book`.

| ID | Finding | Outcome |
|---|---|---|
| P2-1 | `_load_protocol()` in `_take_the_book` untested; the follower never mirrors `last_day`, so a regression places a second protocol batch the same day | Fixed: `test_a_takeover_keeps_the_protocols_day_stamp` |
| P2-2 | A second window shows settings it refused (protocol box ticked, risk combo changed); nothing resyncs | Fixed: `MainWindow._sync_knobs()` in `refresh()`; `test_a_refused_setting_does_not_stay_shown` |
| P3-1 | Dead holder's mirror stays on screen until warmup's first poll | Fixed: snapshot reset to `starting`; test added |
| P3-2 | If `_take_the_book` raises, the window is stuck read-only and silent | Fixed: error shown, retried every `LOCK_RETRY_EVERY`; test added |
| P3-3 | `_forward` re-read `self.following`; a takeover in between gave "engine at None … AttributeError" (pre-existing) | Fixed: callers pass the URL they saw |
| P3-4 | `Live()` starts `read_only=False`; actions before `run()` or mid-take on the free-lock path use launch-time objects | Deferred: ms-wide in the app; tests drive a bare `Live()`; recorded in the spec |
| P3-5 | A `--risk` agent that waited overwrites the user's later choice when it takes over | Owner: keep the current rule |

Mutation check of the fixes: removing each of the four (protocol reload, snapshot reset, retry,
knob sync) fails exactly one new test.
