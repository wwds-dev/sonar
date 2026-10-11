# T2-3 review — code-reviewer, 2026-10-11

Spec `docs/specs/t2-3-refused-action-message.md` (closing UX C-2). Read-only review by a separate
`code-reviewer` agent with probe tests in a scratch copy. Playbook `status: baseline` (stale).
Reviewer ran `test_refused_action_message.py` and `test_undo_and_onboarding.py` natively and
offscreen (30/30 each). Checked fine: `_sync_status_bar` following the toast label is right at both
widths; Undo can never act on something other than what the toast shows; `ConfigThread` always
emits `done` and no path leaves a hold stuck; monotonic clock; copy implies no edge, profit or
certainty; test counts.

**P0/P1: none.**

| ID | Finding | Outcome |
|---|---|---|
| P2-1 | "applying — rescanning…" held without limit hid refresh's ⚠ (read-only, failed poll, health) for a whole rescan (probe: read-only + 60 s, still "applying") | Fixed: no unbounded hold; a pending flag swaps only refresh's ordinary line; warnings get through after the action's 8 s; test |
| P2-2 | "a setting that did not apply" never fired: `configure` swallowed refusals and follow failures and returned a plain config | Fixed: `configure` returns `refused` (read-only) and `error` (followed engine did not confirm); tests through the real `configure`. The pre-existing stale horizon box is resynced too; test |
| P3-1 | A finished setting released any hold, cutting a newer refusal short (probe) | Fixed: `_config_done` no longer touches the hold; test |
| P3-2 | An action during a rescan ended "applying" early | Fixed by P2-1's design: "applying" is a state, not a hold; test |
| P3-3 | A setting's failure removed an unrelated trade's live Undo (probe) | Fixed: status held, toast only when no Undo toast is up; test |
| P3-4 | Removing the warning's timer start passed every test | Fixed: test asserts the timer is running near `TOAST_MS` |
| P3-5 | "documentation not found" still overwritten within 1 s | Fixed: held; test |
| P3-6 | Test patched `time.monotonic` process-wide | Fixed: module seam `ui.app._now` |

The record this spec cited did not exist at review time; it is this file.

## Mutation check (author, scratch copy outside the repo)
Round 1, 13 mutants: 12 killed, 1 survivor (a warning not clearing the previous toast's Undo
target) — test added, killed. Round 2 (after the fixes), 20 mutants, all killed: no warn on trade;
trade not held; hold ignored; hold forever; bar tied to undo target; warn keeps target; warn timer
not started; close not warned; undo not warned; pending not shown (live, starting); pending never
cleared; apply holds forever; done clears the hold; `refused` ignored; warn over a live Undo; horizon
not resynced; missing page not held; core refusal silent; core follow error silent.

## Not verified
By hand in a running app; native rendering of the ⚠ toast at 1280 (C-12 duplication is a
stated non-goal).
