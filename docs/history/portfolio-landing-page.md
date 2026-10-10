# The portfolio landing page (GUI round 3)

Design record: why the app opens on the paper book, and how the page is built.

Moved verbatim from `README.md` on 2026-10-10 when the README was cut to what / how / where. Statements here are as of the commit they were written in; the README no longer repeats them.

Chosen 2026-10-08, from a mockup drawn with the real book (31 open, 19 closed)
and approved before any code moved. The app had opened on the hourly bitcoin
model since the day it existed, and the person it is for asked the right
question: why does the first screen show one asset the model trades, rather
than what *I* hold? So:

- **The first page is the paper book** (`_portfolio_tab`, "My investments /
  PORTFOLIO"), built from `Live.positions` alone, so it renders while the
  first poll is in flight. The strip is a hierarchy: the profit or loss now is
  the biggest figure, in the one highlighted cell, because it is the
  question; beside it the account value, what is invested, what every stop
  hitting would cost, and what has closed. Under it the **account value over
  time** (`ui/charts.AccountCurve` — time on the x-axis for real, so a gap in
  the log is a gap on the chart), every open position as a **tile**
  (`PositionTiles`, a squarified treemap) beside what resolved recently, and a
  **card per position** (`PositionCard`, with `PositionChart` drawing the
  entry, target and stop over sixty days of price). Cards update in place
  and keep their order; a page you look at every day should not reshuffle.
- **"Invested" is two numbers and the page says so.** A long spends cash; a
  short borrows stock. Summed blindly on the real book they came to $46k on a
  $10k account — which is not a bug, but a figure that looks like one. The
  strip shows the sum with the split under it (`Portfolio.stats()` gained
  `long_cash`, `short_notional`, `at_risk`, `realised`, `n_long`, `n_short`).
- **Tiles are sized by what a position can lose, not by what it is worth.**
  A currency short carries a notional thirty times an equity long's for the
  same risk budget; sized by notional the picture would be about leverage
  conventions. Sized by `cash_at_risk` it is about the bets, and under
  protocol mode — every position the same risk — it is an honest equal grid.
- **The account-value log** (`Portfolio.log_equity`, `equity_log` in
  `portfolio.json`): a point an hour, plus one at every entry, exit or barrier
  hit, written by whichever process marks the book — one, by the engine
  lock. A point is only written when every held position has a price, because
  marking a missing one at entry draws a dip that never happened. The weeks
  before the log existed are rebuilt once by `seed_equity_log` from the
  book's own records and real daily closes (`assets.fetch_bars`, on the
  engine thread, three tries at most) — the trades it made, valued at each
  day's close. Nothing invented; the curve starts where the book did.
- **The hourly model kept its readout and lost its page.** It is an
  experiment the engine runs, not something the reader holds, so
  `_terminal_tab()` — unchanged — is hosted at the foot of Practice, with
  the LLM read panel, which `_read()` now scrolls to. The engine keeps
  settling hours whether or not anything shows them; the Brier line is the
  only evidence that experiment produces, which is the argument for keeping
  the readout and the whole argument against keeping a page for one asset.
  Its ledger cells are captioned *model's practice cash* / *model's trades*
  now, because "practice cash" on the old landing page read as the reader's
  own account, and it never was.

- **"Is the score right?" sits under the figures** (added the same day, when
  the person this app is for pointed out that answering it is the whole
  purpose of the app). It is `calibration.report()` in the manual's words:
  the verdict sentence verbatim, one line per score band — closed, won, the
  rate the plan promised, and whether the band has the twenty it needs to
  count — and what the verdict still lacks: how many of the twenty closed
  positions exist, how many were protocol (coin-flip) entries so the table
  grades the score and not a picker, and whether protocol mode is on. The
  profit figures above it cannot answer the question, and the panel says so:
  a coin-flip position's profit is luck, and the score claims that something
  is happening, never which way. The same report My trades shows; the first
  screen now carries the conclusion, the Book tab keeps the full table.

What stayed: the Cockpit shell, both names on every destination (the docs
test still greps `PlainTabs.add`), the 1280×775 fold, and the rule that
nothing outside the hourly model asserts a direction — the new page describes
what you hold and never what to do with it.
