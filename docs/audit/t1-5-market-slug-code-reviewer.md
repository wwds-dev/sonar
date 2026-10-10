# T1-5 review — code-reviewer, 2026-10-10

Read-only; one live GET of the series. Playbook `status: baseline`. New slug = C-locale `strftime`
for every hour of 2026–2027 (0 mismatches), real format confirmed (`october-10-2026-12pm-et`).
Spring-forward skips 2am as expected; fall-back second 1am now falls through; a next-hour market is
refused by `engine.py:295`; the series endpoint is not called in normal operation. Both new tests
fail with the old `feeds.py`.

**P0: none. P1: none. P2: none.**

| ID | Finding | Outcome |
|---|---|---|
| P3-1 | Series `limit=1` can still return the first, ended 1am in the second 1am's first minutes | Fixed: `limit=3`, first live event; test |
| P3-2 | `_midpoint` called before the ended check: a wasted CLOB call per fall-through poll | Fixed: end time checked first |
| P3-3 | A misaligned fallback market was cached and shown beside the stale signal (pre-existing) | Fixed: `_poll` drops it; test |
| P3-4 | Locale test reset to "C" not the original; no 0h/12h edge test; no test that the series is skipped | Fixed: all three |
