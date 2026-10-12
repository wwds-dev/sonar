# Spec: a refused trade gets a visible, durable message

- Status: built (branch `c2-refused-trade-toast`)
- Owner approval: task given by the owner 2026-10-11 (closing UX C-2); copy below for review

## Problem
`docs/audit/closing-ux-designer.md` C-2. `_trade` wrote "⚠ ..." to the status line and created a
toast only on success; `refresh()` runs every `REFRESH_MS = 1000` and rewrote the status line, so
a refused trade's warning lasted under a second (measured by the reviewer: "⚠ unknown symbol AAPL
- paper money only" became "starting - first poll can take a moment" after one refresh). A user
who clicked Buy and looked away saw nothing. Same for a failed Close and for "applying —
rescanning…".

## User and goal
Retail user placing a paper trade. Success measure (`tests/test_refused_action_message.py`):
1. A refused trade, a failed close, a failed undo and a failed setting each show a ⚠ toast in the
   window's bar at any width, with no Undo, for the toast's 8 s.
2. The status line keeps the action's message for 8 s against `refresh()`. While a setting is
   being applied, refresh's ordinary line reads "applying — rescanning…" until the rescan reports
   back, but its warnings (read-only, failed poll, health) still get through. A newer action's
   message replaces an older one at once; a finished setting does not cut one short.
3. A setting the engine refuses (read-only window) or that a followed engine did not confirm says
   so; the risk and horizon boxes go back to what the engine runs.

## Scope / Non-goals
Non-goals: colour/size of warnings (C-5), pausing the toast timer on hover/focus and Cmd-Z (C-3),
the toast/status duplication in the bar at 1280 (C-12).

## Design (copy)
Toasts: "⚠  Not traded: <engine's reason>", "⚠  Not closed: <reason>", "⚠  Not undone: <reason>",
"⚠  Setting not applied: <reason>" (e.g. "this window is read-only while another SONAR runs the
engine"). Status line unchanged in wording ("⚠  <reason>  ·  paper money
only" for trades), now held. Successes keep "✓ … — paper money only" with Undo. No copy implies
edge, profit or certainty.

## Architecture
`ui/app.py`: `_set_status(text, hold_s=False)`: `hold_s=True` holds for `TOAST_MS`, a number
for that many seconds; an unheld write (refresh's) is dropped while a hold lasts (monotonic clock
through the module seam `_now`). `_warn(text)` reuses the toast label and timer with Undo hidden and the undo
target cleared, so Undo can only ever act on what the toast shows. The bar's visibility follows the
toast label, not the undo target. `_apply_config` sets `_config_pending` (and an 8 s hold);
refresh's ordinary line becomes "applying — rescanning…" while it is set; `_config_done` clears it
and, on `refused`/`error`, holds a ⚠ status and shows a ⚠ toast unless a live Undo toast is up.
`_sync_knobs` now resyncs the horizon box as well as the risk box.
`sonar/core.py configure()`: returns `refused` when a read-only window cannot change settings, and
`error` when the followed engine did not confirm the change (both used to return a plain config).
`ConfigThread` always emits `done`.

## Verification plan
`tests/test_refused_action_message.py` (20 tests); 33 mutants over two rounds in a scratch copy,
all killed (one round-1 survivor got a test) (record: `docs/audit/t2-3-refused-action-message-code-reviewer.md`).
Not verified: by hand in a running app; native rendering of the ⚠ toast at 1280.
