# T2-2 review — code-reviewer, 2026-10-11

Spec `docs/specs/t2-2-poll-error-state.md` (closing UX C-1). Read-only review by a separate
`code-reviewer` agent. Playbook `status: baseline` (stale). Reviewer ran `test_poll_error_state.py`
and `test_refresh.py` (38 passed native; the first offscreen too). Checked fine: thread safety (the
error snapshot reads `horizon`/`_macro_snap` as `_build` does; the `assets` merge is under
`self.lock`; `_rescan_once` is serialised and never runs while following); `_refresh_macro` cannot
raise on a non-live snapshot; a good scan replaces the dict and drops `error`; the board's redraw
signature is stable while rows exist; mixed agent/window versions fall back safely; no copy implies
edge, profit or certainty.

**P0/P1: none.**

| ID | Finding | Outcome |
|---|---|---|
| P2-1 | Big picture now drawn in read-only: "Loading…" that never loads, or "Switch to…" advice the engine refuses; after a followed agent stops answering, old 10y/VIX/… stay beside "—" | Fixed: read-only says the regime is not available here; figures and bar cleared without a regime; tests |
| P2-2 | A failed scan was hidden behind an older board's "filtered" verdict | Fixed: the error is checked first; test. Error beside a populated board deferred (spec) |
| P3-1 | "Still no prices" can be false: the try also covers marking the book and alerts | Fixed: "The last scan failed (…)" |
| P3-2 | Read-only placeholder blamed another SONAR; read-only also means "could not read the book" | Fixed: neutral "it is read-only, and the status line says why" |
| P3-3 | "after N minutes" counted from window launch, including read-only time | Fixed: the clock restarts while read-only; test |
| P3-4 | A long error placeholder did not wrap (a label sets the window's minimum width) | Fixed: empty-state labels wrap; test |
| P3-5 | Following: the failure read as this window's | Fixed: "the engine at <host>:" prefix; test |
| P3-6 | Test gaps: steady-state rebuild, error cleared by a good scan, error snapshot without macro | Fixed: tests for each |
| P3-7 | Spec cited this record before it existed | Fixed: this file |

Also found by the author's full-suite run: `tests/test_portfolio_tab.py`'s fixture fed partial
board rows that only survived because the Screener was skipped outside `live` (13 errors,
`KeyError: 'momentum'`). Fixed by giving the fixture the fields a real row has (`SCREEN`), with a
lean that does not put them on the News page; the tests' assertions are unchanged.

## Mutation check (author, scratch copy outside the repo)
Round 1, 13 mutants, all killed: Screener gated, macro gated, old error text, no whitespace
collapse, `priced` ignored, scan error ignored, read-only text gone, never late, signature ignores
text, macro default gone, error snapshot bare, scan error swallowed, `priced` constant.
Round 2 (after the fixes), 12 mutants, all killed: error not first, read-only text gone, read-only
clock not reset, no wrap, no following prefix, read-only macro note gone, stats not cleared, bar not
cleared, error survives a good scan, Screener gated, rebuild every tick, error snapshot bare.

## Not verified
The error branch in a running app with a real feed outage; native font rendering of the wrapped
placeholder.
