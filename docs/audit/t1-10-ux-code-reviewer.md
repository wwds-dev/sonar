# T1-10 review — code-reviewer, 2026-10-10

Read-only. Playbook `status: baseline`. Full suite green both modes; new tests fail on HEAD (missing
methods). Checked fine: cancel/reopen cash vs `enter`/`close` for longs and shorts; pending refused;
same-symbol reopen blocked; double-click safe; lock order; equity points value-neutral; status-bar
transitions; minimum window 1275×474 with the bar (31 px at 1280×775); ⌘1–8 no conflicts.

**P0: none.**

| ID | Finding | Outcome |
|---|---|---|
| P1 | An undone manual close could be re-marked TARGET/STOP at once if the price had moved past a barrier — a hand close turned into a graded hindsight win (reproduced) | Fixed: reopen only at the close price; test |
| P2 | `cancel` refunded at entry after the price moved — drop the trades that start badly (reproduced) | Fixed: cancel only at the entry price; test |
| P2 | `reopen` had no cash check: cash −10,000 via `/api/undo` (reproduced) | Fixed: a long's reopen needs the cash; test |
| P3 | Protocol entries and async-broker fills undoable | Fixed: refused; test (protocol) |
| P3 | "too late to undo" for a trade that hit a barrier | Fixed: "it already closed at its stop/target"; test |
| P3 | "Got it" didn't stick if the file couldn't be written; file read every refresh | Fixed: in-memory flag, read once; test |
