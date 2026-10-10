# T0-3 review — code-reviewer, 2026-10-10

Read-only. Playbook still `status: baseline`. The diff changed mid-review (flag-based →
number-based correction, prompted by the older installed app dropping the flag); the review
covers the number-based version. On a scratch copy of the real book: correction −285.42,
68,430.43 → 68,715.85 = 10,000 + 58,715.85 live P&L over 283 live trades; backup written; a
second load does not correct again. 3 new tests fail against HEAD's `engine.py`.

**P0: none. P1: none.**

| ID | Finding | Outcome |
|---|---|---|
| P2-1 | The chart plots by index; the start point stayed at 10,000 while the redrawn warm-up began at 10,296.80 — a jump at the left edge | Fixed: start point redrawn too; `test_the_warm_up_curve_is_continuous` |
| P2-2 | `static/index.html:291` Total P&L tooltip said "backtest seed plus live trades" | Fixed: "live paper trades only" |
| P3-3 | A warm-up netting within ±0.05 of zero could be corrected on an already-corrected book | Fixed: also skip when `abs(carried) <= 0.05`; test |
| P3-4 | `warmup_outside_bankroll` written but never read | Fixed: removed |
| P3-5 | `shutil.copy2` not atomic, its errors aborted the save | Fixed: `paths.write_atomically`, OSError logged |
