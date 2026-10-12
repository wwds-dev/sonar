# Spec: a failed bitcoin poll is shown as a failure and freezes nothing else

- Status: built (branch `c1-poll-error-state`)
- Owner approval: task given by the owner 2026-10-11 (closing UX C-1); copy below for review

## Problem
`docs/audit/closing-ux-designer.md` C-1. `MainWindow.refresh()` returned before `_refresh_cards`
and `_refresh_macro` unless the hourly BTC snapshot was `live`. A poll exception set
`{"status": "error", "detail": ...}`; the UI printed "error — first poll can take a moment",
dropped the reason, and the Screener stayed on "Fetching prices for 129 markets — the first scan
takes about a minute." for as long as Binance and Coinbase were unreachable. The core path (the
notability scanner) was gated on an experiment's feed; read-only windows took the same early
return. The agent log shows one such burst of 91 failures on 2026-10-11.

## User and goal
Retail user on the Screener. Success measure (`tests/test_poll_error_state.py`):
1. With the poll in `error` or `read-only`, the Screener draws the engine's board and Big picture
   refreshes.
2. The status line starts with ⚠ and carries the poll's reason; it never says "first poll" for an
   error.
3. The empty Screener never claims "fetching" once that is false: a failed scan names its error
   (ahead of an older board's verdict); a scan that priced nothing says so; after 3 minutes with
   no board the placeholder says how long (counted from when the window may scan); a read-only
   window with no board says it cannot show one.
4. Big picture without a regime shows no old figures, and a read-only window says the regime is
   not available rather than "Loading…" or advice the engine would refuse.

## Scope / Non-goals
Non-goals: colour and size of warnings (C-5), Big picture's first-run state beyond the existing
"Loading the macro regime…" (C-9), the "129 markets" figure (U-8).

## Design (copy)
- Status, poll error: "⚠  [the engine at <host>: ]bitcoin price poll failed (<reason, ≤140
  chars>) — retrying. The Screener and Big picture do not depend on it." (prefix when following)
- Screener empty, last scan raised: "The last scan failed (<error>). Trying again shortly."
  (neutral: the failure may come after the prices arrived)
- Screener empty, scan ran, nothing priced: "No prices came back from the market data source on
  the last scan. Trying again shortly."
- Screener empty after 3 min, no scan yet: "Still no prices after N minutes: the first scan has
  not finished. It keeps trying."
- Read-only, no board: "No board in this window: it is read-only, and the status line says why."
- Big picture, read-only: "The macro regime is not available in this window: it is read-only, and
  the status line says why."
Empty-state labels wrap.
No copy implies edge, profit or certainty.

## Architecture
- `ui/app.py refresh()`: `_refresh_cards` and `_refresh_macro` run before the status branches.
  `_assets_empty_text()` picks the placeholder; the board's redraw signature includes it, so it
  changes once a minute at most.
- `sonar/core.py`: the error snapshot carries `horizon` (and `macro` when loaded), so Big picture
  can draw; a raised scan is kept on the board as `assets["error"]` until the next good scan
  replaces the dict (it used to be `except: pass`).
- `sonar/assets.py`: the payload carries `priced` (rows with any price, before the risk filter),
  so "nothing came back" differs from "the filter hid everything". An older agent without the
  key falls back to the filter message.
- No new threads, locks or state files. A following window gets the new keys from the agent's
  `/api/state` and `/api/assets` once the agent runs this code.

## Verification plan
`tests/test_poll_error_state.py` (26 tests); 25 mutants in a scratch copy over two rounds, all
killed (record: `docs/audit/t2-2-poll-error-state-code-reviewer.md`).
Deferred: a failed scan while the board still has rows shows only through the AGE column (no
banner); a ⚠ banner over a populated board is a design change for C-5. Not verified: the live error branch in a
running app (no feed outage was induced).
