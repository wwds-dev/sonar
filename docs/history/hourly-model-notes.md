# The hourly model: study notes and hard-won invariants

The parts of the model write-up that are history rather than description: the volatility study behind the EWMA × hour-of-day estimate, the bid/ask record, how the seeded curve and settlement gaps are handled, and the clock invariant.

Moved verbatim from `README.md` on 2026-10-10 when the README was cut to what / how / where. Statements here are as of the commit they were written in; the README no longer repeats them.

Since Sep 2026 that estimate is an **EWMA scaled by an hour-of-day profile** rather than a
flat 72-hour standard deviation. Measured first, wired second, per this project's standing
rule: over 16,078 held-out hours (two years of BTCUSDT) the combination beat the old
trailing window by **7.5% on QLIKE**, winning all six time blocks — clustering (+3.9%) and
diurnal seasonality (+3.5%) are separate, additive facts about the same hour. GARCH also
beat the incumbent but was passed over: its 720-hour anchor means part of its win is
effective sample size, the artefact the daily study's synthetic control caught — the same
control shows EWMA and the profile find nothing on constant-volatility data, so their win
can only be the two hypothesised effects. `sonar/research/hourlyvol.py` records the study
and its pre-registered expectations.


The equity curve is seeded with a **fair-odds backtest** over the last 36 real hours
(expected value ≈ 0 by construction — it illustrates variance, not profit), then extends
with live paper trades marked by a gold "LIVE" divider. The seeded rows stay out of the
displayed win rate and trade count, which grade live trades only — a fresh install shows
an honest zero, not a record built from trades nobody took.

Settlement survives gaps honestly too: if the app slept or restarted past the end of an
open position's hour, the next candle's open is a price from hours after that market
resolved, so the engine fetches the hour's own close and settles against that — or **voids**
the position when the close cannot be recovered, because a shorter record beats a corrupt one.

Entry is held to the same clock discipline, learned the expensive way: an hourly market must
end **exactly one hour after its candle opens** or the engine refuses the tick outright.
Without that invariant a stale candle meeting a fresh market — around wakes and feed hiccups
— once opened five positions up to 51 minutes *after* their own hour had settled, buying the
known outcome at longshot prices for 71% of a week's paper P&L. An adversarial review found
it, the phantom fills were scrubbed from the record, and the regression test replays the
wild case verbatim. It is the project's recurring lesson in one line: **one hour must never
price another.**
