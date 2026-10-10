# T0-5 review — code-reviewer, 2026-10-10

Read-only. Playbook still `status: baseline`. All book paths price through `_book_prices`; no other
code in core.py, ui/app.py or server.py values the book from board-only prices. All 4 initial new
tests fail with the two source files reverted.

**P0: none. P1: none. P2: none.**

| ID | Finding | Outcome |
|---|---|---|
| P3-1 | `_mark_book` returned on an empty board before merging hidden prices: a crash that hides every row left stops unchecked | Fixed: merge first; test |
| P3-2 | Hidden positions' cards had no sparkline | Fixed: `AssetScanner.last_sparks`, `_book_sparks`; test |
| P3-3 | No test for `_take_the_book` pricing hidden positions | Fixed: test added |

Checked and set aside: staleness (`last_prices` refreshed from the same cache as the board; barrier
hits settle at the barrier), thread safety under the GIL, follower path, permanent refusal (only for
a symbol removed from the watchlist; none found).
