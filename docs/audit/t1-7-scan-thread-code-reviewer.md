# T1-7 review — code-reviewer, 2026-10-10

Read-only. Playbook `status: baseline`. All 5 initial new tests fail on HEAD. Locks: no new
acquisitions; order unchanged; the poll thread holds nothing while it joins. `_take_the_book` runs
before the thread starts. Follower unaffected. Qt shutdown: 1.5 s grace < 20 s join → hard exit
mid-fetch, same as before (inline scan). Headless never calls `stop()`.

**P0: none. P1: none.**

| ID | Finding | Outcome |
|---|---|---|
| P2-1 | Macro panel told a user on a long horizon to switch to it, until the first macro fetch | Fixed: "Loading…" when the horizon uses macro; warmup fetches macro first; test |
| P3-2 | Book could be written after lock release via `_seed_account_history`/protocol after a long seed fetch | Fixed: stop checks before each write |
| P3-3 | Background scan queued behind a settings-change scan ran a second full scan | Fixed: `_rescan_if_due` decides inside `_rescan_lock`; test |
| P3-4 | Signal and page could carry different σ values | Fixed: read once, passed to `_build` |
| P3-5 | `health()` blind to a dead/stuck background thread | Fixed: `scan` problem (dead, or 3× overdue); watchdog alarms after 10 min; test |
| P3-6 | No test for join-before-release or surviving a raising step | Fixed: two tests |
| P3-7 | (pre-existing) `{**last_prices}` could race the scan's inserts | Fixed: `.copy()` |
