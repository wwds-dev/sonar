# 0002. Grade the live score on a 4-week time stop, marked to market, as a read-only shadow

- Status: **accepted** (owner, 2026-10-12; every recommendation under "Open questions" taken)
- Date: 2026-10-12
- Spec: [`docs/specs/shadow-time-stop.md`](../specs/shadow-time-stop.md)
- Numbering: the highest committed ADR on any branch is `0000-template`. `0001` belongs to the
  uncommitted QA-11/QA-13 work in the main checkout. If that work lands under another number, this
  one moves with it.
- Depends on: `scoring.barrier_probabilities_within` (uncommitted, owned by the session "SONAR
  testing plan"), for the no-edge reference split in §2 only.

## Context
`calibration.report()` grades only positions closed at a barrier, and the book has no time stop. On
2026-10-12, 14%, 38% and 52% of the 60–80, 40–60 and 0–20 bands had closed. The graded set is the
quick resolvers, so the per-band hit rates and the rank IC (−0.32, n = 21) cannot be read. The
spec's Problem section has the evidence. The model-validator compared grading by entry cohort with a
time stop (`docs/audit/censoring-options-model-validator.md`, branch
`claude/happy-visvesvaraya-84b4ef`). It recommended the time stop, introduced first as a read-only
shadow so the live experiment does not change, and listed seven points this ADR must record. They
are §1–§7 below.

## Decision
Add `calibration.shadow_time_stop(open, closed, bars, now)`. For every protocol entry, it gives the
outcome the entry would have had under a time stop at entry + T, marked to market. It is shown
beside the existing grade. Exits, `GRADED`, `Z_CLAIM`, the verdict text and row P(profit) do not
change.

### §1 T, fixed before any outcome is inspected
**T = 4 horizons of the entry's preset (ADR 0001's backtest cap), stated in calendar days:
T = 4 × `momentum_days` × 7/5.** The preset's `momentum_days` is the horizon, in daily bars, that
the plan's σ is scaled to (`core.py:341` passes it to `build_plan`; verified in `sonar/horizon.py`).

| preset | horizon (daily bars) | T (calendar days) | horizons in T, weekday instruments | horizons in T, crypto (7-day bars) |
|---|---|---|---|---|
| intraday | 1 | 5.6 | 4 | 5.6 |
| **week** (all 52 live entries) | 5 | **28** | 4 | 5.6 |
| month | 20 | 112 | 4 | 5.6 |
| quarter | 60 | 336 | 4 | 5.6 |
| year | 250 | 1,400 | 4 | 5.6 |

- One calendar clock gives every row one date ("4 weeks"). The primary statistic's no-edge value
  (§3) does not depend on T. Only the reference split depends on T, and it uses each entry's own
  horizons: bars in the window ÷ horizon bars, the `W/h` of ADR 0001. Holidays shorten that a
  little, and TRX-USD, the book's only crypto symbol, gets 5.6.
- **Pre-registration evidence.** At 2026-10-12 03:52 IST, the oldest entry (2026-09-22) was 20.1
  days old, so no entry had reached T, and no time outcome existed or had been computed. The value
  comes from ADR 0001 (2026-10-11), where it was set for another purpose. What had been inspected
  was the closed-only outcomes and the band ages. They show that censoring exists; they did not
  choose T.
- **Frozen.** T is a module constant pinned by a test. Changing it needs a new ADR and starts new
  cohorts from the date of the change. Looks already evaluated keep their T.

### §2 The new null, and what "advertised" means in the UI
- **The untimed 1/(1+R:R) is not the null for this grade.** It still means what it says on every
  row: P(profit) = 40% at 1.5:1, untimed, untouched (T1-1, ADR 0001). The word "promised" or
  "advertised" stays tied to that row figure only.
- **The primary null is E[R | score] = 0.** R is the result in units of initial risk:
  R = d·(exit − entry)/|entry − stop|, with d = +1 for LONG and −1 for SHORT. A target exit gives
  +1.5 and a stop exit −1. If the price is a martingale over the window and exits fill exactly, the
  optional-stopping theorem gives E[R] = 0 for any σ error, any T and any barrier placement. With
  the protocol's coin-flip direction, a drift also cancels to first order. This null needs no new
  maths.
- **Secondary reference ("what no edge would give"):** the target / stop / neither split by T from
  `scoring.barrier_probabilities_within(1.5, 1.0, horizons)`. At 4 horizons that is 37.4% / 57.4% /
  5.2%; at 5.6 horizons, 39.3% / 59.3% / 1.5% (computed 2026-10-12 from the uncommitted function).
  This split assumes σ̂ is right, so it checks the volatility estimate, not the score. It is shown
  per band next to the observed split and never gated. If ADR 0001 has not landed, this line ships
  later and the primary readout ships without it.

### §3 Primary statistic and gate
- **Recommended statistic:** the z of the OLS slope of R on confidence, with an HC3
  (heteroscedasticity-robust) standard error. It is two-sided. Its no-edge expectation is exactly 0
  because E[R | score] = 0.
- **This departs from the validator's proposal** (rank IC of confidence against R). R has a point
  mass at −1, a median of −1 and a mean of 0, so when the time-out share varies with score the ranks
  shift with no edge at all. Simulated with no edge and realised/planned σ falling from 1.3 to 0.5
  across scores (`docs/specs/shadow-time-stop-sims.py`), the results were:
  - Rank IC: mean +0.031 at n = 45, +0.026 at n = 400.
  - Two-sided rejection at 2σ, n = 400: rank IC 5.5–7.0% (seeds 1 and 5), HC3 slope 2.8–3.3%.
  - At n = 45: HC3 slope 4.3–5.9% across three volatility gradients.

  The rank IC stays on screen for one purpose: comparison with the closed-only rank IC on the same
  cohort. That comparison is descriptive, not a test.
- **Looks, answering the sequential question.** `Z_CLAIM = 3` was set because the closed-only grade
  is re-checked after every close. Here the test runs only at three looks fixed now:
  - Cohorts are the **first 45, 101 and 201 protocol entries by `opened_at`**. Membership is set by
    entry order and never by resolution.
  - Each look is evaluated **once**, when every member has an outcome or a final exclusion.
  - The boundary is **|z| ≥ 2.315 at every look** (Pocock). That holds the false-positive rate of
    the whole design at 5% two-sided (Monte Carlo, 400,000 paths).
  - The first crossing is the result. With no crossing by 201, the readout says "no evidence that
    the score ranks 4-week results, at the planned size". After the third look the design is closed.
  - Between looks the readout shows the running value, labelled "not a test".
  - At 2.54 protocol entries a day, the expected dates are about 2026-11-06, 2026-11-28 and
    2027-01-07. The 40-position cap can push them later.
  - If more than 10% of a cohort is excluded, the look's result carries that count.
- **Alternatives, for the owner** (power is for a true correlation of score with R; sims, `looks`):

| design | false positives | correlation needed at 45 / 101 / 201 | power at IC 0.1 / 0.2 / 0.3 |
|---|---|---|---|
| **Pocock 2.315 at 45, 101, 201 (recommended)** | 5.0% | 0.35 / 0.23 / 0.16 | 0.23 / 0.73 / 0.98 |
| O'Brien–Fleming 4.18 / 2.79 / 1.98 | 5.0% | 0.63 / 0.28 / 0.14 | 0.29 / 0.80 / 0.99 |
| 3σ at each of the three looks (keeps `Z_CLAIM`) | 0.7% | 0.45 / 0.30 / 0.21 | 0.07 / 0.46 / 0.90 |
| 3σ once at 45 (validator's proposal) | 0.3% | 0.45 | 0.01 / 0.05 / 0.16 |

  Pocock lowers the bar for a single claim from 3σ to 2.3σ. That is the honest price of a test
  that can find a correlation of 0.2. A single look at 45 at 3σ cannot find one (power 5%). Stopping
  there and then looking again later is exactly the sequential trap that `Z_CLAIM` guards against.

### §4 Open and legacy positions; comparability
- All 51 protocol entries since 2026-09-22 are in scope, open or closed. The live exit rule does not
  change, so there is one experiment and **no comparability reset**. Nothing is excluded for being
  old.
- **"Shadow replay" means the live book's own record**, not a re-simulation. For each entry, let
  t_T = `opened_at` + T. The *T bar* is the last daily bar stamped at or before t_T. It counts only
  once a later bar exists. The cut, t_cut, is that later bar's timestamp. In order:
  1. **Barrier:** closed TARGET or STOP with `closed_at` < t_cut keeps the booked outcome, with R
     +1.5 or −1. No price is needed when `closed_at` ≤ t_T.
  2. **Gap:** otherwise, if a daily close after `opened_at` and up to the T bar lies at or beyond a
     barrier (the polls missed it, for example during an agent stall), the first such barrier is the
     outcome, with R at the barrier. It is counted in `n_gap`.
  3. **Time:** otherwise, once the T bar is final, R comes from the T bar's close.
  4. **Waiting:** otherwise, the entry is waiting. It is counted, together with the next date an
     entry reaches T.
- **Exclusions, always counted and shown:**
  - Non-protocol entries (a person chose them; META is the only one today).
  - Protocol entries closed by hand before t_cut (`n_left`, zero today).
  - Entries with no bars 7 days after t_T (`n_no_price`; before that they are waiting).
  - Unfilled orders were never positions.
- If the owner later makes the time stop live (a separate ADR), the comparability reset happens
  then: entries before the switch keep shadow grading, and the live grade's sample starts at the
  switch date.

### §5 Price source, resolution, slippage and fills
- **Source:** Yahoo chart daily closes through `assets.fetch_bars`. That is the same provider whose
  `regularMarketPrice` the scanner polls for the book's live marks.
- **Daily closes are enough, and intraday bars are not needed.** The barrier record up to T is the
  live book's own polled record. The shadow needs one price at T, plus a coarse check for missed
  crossings, which intraday bars would only sharpen. The validator's "needs price history from
  opened_at to now" is narrower in fact. It needs bars from `opened_at` to the T bar, which serve
  only the gap check; it does not need them to now.
- **Verified 2026-10-12** (the validator marked this "not verified"):
  - `fetch_bars(sym, "3mo")` returned 65–92 daily bars from 2026-07-10/12 for ^GSPC, META,
    EURCHF=X and TRX-USD. The earliest entry is 2026-09-22.
  - Timestamps mark the session start: 13:30 UTC for US, 00:00 UTC for crypto, 23:00 UTC the
    previous evening for FX.
  - The newest bar can be in progress (EURCHF=X was stamped 02:55 UTC at fetch). Hence the rule
    that the T bar counts only once a later bar exists.
  - Not verified: behaviour for a delisted or renamed symbol. That case falls under `n_no_price`.
- **Range:** request enough history to cover `opened_at`: "3mo" for week, "6mo" for month,
  "2y"/"5y" for longer presets. Fetch outside `book.lock`, at most once per symbol per day, and only
  for entries past t_T without an earlier barrier outcome.
- **Fills and costs:** a time exit fills at the T-bar close, and a barrier exit exactly at the
  barrier, as in the book (`portfolio.py:21-22`). There is no slippage and no cost. Both flatter the
  mean R. A constant cost per trade moves the mean R but not the slope or the IC. The readout says
  "no costs".

### §6 Scope of ADR 0001's rejection of marking to market
ADR 0001 rejected "mark timeouts to market at the window end" **for the Lab backtest**, because it
turns a hit-rate study into an expectancy study. For the live shadow, that change is the point. R
has a no-edge mean of 0 that survives σ error, which the hit rate does not. This ADR supersedes that
rejection **for the live book only**. ADR 0001's decision for the backtest (`predicted` conditional
on resolving) stands. ADR 0001 is uncommitted and owned by another session, so it is not edited
here. When it lands, its owner should add a line pointing to 0002.

### §7 Reversal
Drop the time outcome: remove `shadow_time_stop`, the payload's `shadow` key and the UI block, and
fall back to the closed-only `report()`, which this change never touched. Nothing is persisted, so
nothing needs migrating. Any look results already published stay in CHANGELOG as history. The cost
is small and contained to code.

## Alternatives considered
- **A live time stop** (option 3 proper). It removes censoring for new entries. But it changes the
  experiment, resets comparability with the 30 open positions, and changes what a row's P(profit)
  promises. Deferred: worth deciding only if the shadow shows the bias matters.
- **Grading by entry cohort** (option 2). At the cap, open entries must be excluded, which keeps
  the selection, or marked, which is this ADR. It is slower to a verdict, and the cap is a free
  parameter. **Kept as the fallback** if the owner rejects marking to market.
- **Making the censoring visible only** (option 1). It is built on `claude/happy-visvesvaraya-84b4ef`
  (v2.187, not merged). It warns but gives no usable grade. It complements this ADR and does not
  replace it.
- **Competing-risks survival by band** (Aalen–Johansen for P(target by T), open positions censored).
  It is valid here because the censoring is administrative, and it marks nothing to market. It lost
  because its comparison needs the σ̂-dependent reference split (§2), it estimates per band where n
  is 7–29, and it gives no single gate.
- **Rank IC as the gate** (the validator's proposal). It is not zero-centred under no edge when the
  time-out share varies with score (§3).
- **Replaying whole paths from daily bars** instead of the book's record. That is coarser than the
  live polls and would disagree with the book's own exits.

## Consequences
- **Easier:** a grade in which score cannot decide which entries get graded, with a no-edge null
  that does not depend on the volatility model. Its first look comes about 2026-11-06.
- **Harder:**
  - Two grades sit side by side and must not be confused. The ux-designer owns that, and "promised"
    stays with the row figure.
  - The holder engine makes a few more daily-bar requests.
  - The verdict wording must say that random-direction entries cannot show a tradeable edge.
- **Monitor:** `n_gap`, `n_left` and `n_no_price` (any non-zero value is shown), and the time-out
  share by band against the reference split (a σ̂ check).
- **Migration:** none.

## Open questions for the owner (answered 2026-10-12: the recommended option in each)
1. Approve the shadow readout as the direction (recommended), or take cohort grading as the
   fallback?
2. T = 28 calendar days for every instrument (recommended), or 20 bars each, which gives crypto 20
   days?
3. Gate statistic: the HC3 slope of R on score (recommended), or the validator's rank IC?
4. Gate design: Pocock 2.315 at 45 / 101 / 201 (recommended), 3σ at the same looks, or 3σ once at
   45?
5. Population: protocol entries only, with protocol entries closed by hand excluded and counted
   (recommended)?
6. Build after the QA-11/QA-13 work lands (recommended, because both edit `calibration.py`), or
   build the primary readout now without the reference split?

## Amendment 1 (2026-10-12, accepted)
- Status: **accepted** (owner, 2026-10-12: "Yes" to G1, G2 (a) the robust rule, G3 manual reset,
  and the pre-registration statement below). Spec: [`docs/specs/shadow-ledger.md`](../specs/shadow-ledger.md).
  Gate reviews: `docs/audit/shadow-ledger-model-validator.md`, `docs/audit/shadow-ledger-domain-finance.md`.
- Answers the spec's open owner questions 1 and 2 (model-validator P1-1 option b, P2-2).
- **Pre-registration.** No shadow look and no time-exit outcome had been computed when this was
  written; the first entry reaches T on 2026-10-20. Book outcomes of entries closed before T,
  including hand closes, are visible in the paper book and were not consulted.

**§3, "each look is evaluated once", now holds across restarts.**
- The holder writes each decided outcome and each evaluated look to `<SONAR_DATA>/shadow_ledger.json`
  the first time it exists, and never rewrites either. A look is shown as a result only once it is
  recorded, and then as recorded, with the date it was first evaluated.
- A marker in `portfolio.json` records that a ledger exists. A missing, unreadable or foreign ledger
  is an error, never a fresh start: nothing is written and no look is shown as a result.
- A check compares each recorded look's membership and the constants with today's. It is not a
  re-grade. A difference is shown, and the recorded value is kept.
- **Corrections:** a recorded result is never changed. A wrong outcome found later gets an erratum
  (id, reason, corrected R, date), added by a person under a written note and shown beside the look.
  It never changes `crossed` or `design_closed`.
- The ledger is not tamper-evident; the marker and the daily and off-site backups are the cross-checks.

**§3, a crossing must survive the excluded members.**
- When a look is evaluated with k > 0 members excluded for `no_price` or `left`, each such member is
  filled in at its own R at the stop and at the target (both known at fill). For k ≤ 12, z is computed
  at all 2^k fills; for larger k, at the two fills that give the slope's exact extremes.
- A crossing counts only when z and every fill are beyond the boundary on the same side. With k = 0
  nothing changes.
- **Cost, stated:** the rule lowers power when exclusions occur. On synthetic books with about 3
  exclusions per 201, power at a correlation of 0.2 is about 0.63 instead of 0.70, and the size is
  3.8% instead of 5.5%; with about 7, power is 0.49. The power table in §3 holds for no exclusions.

**§4, `no_price` is final only after 28 days and 3 tries.**
- An entry past t_T with no usable closes stays `wait_price`, which holds its looks. It becomes
  `no_price` only when 28 days have passed since t_T **and** fetches on at least 3 distinct UTC days
  after t_T + 7 days could not decide it. The tries are counted in the ledger, so a restart cannot
  skip them.
- A missing price is usually transient, so a held look is then graded on every member, and the
  selection by outcome speed disappears rather than being measured. The limit exists because a
  delisted symbol never gets a price.
- An entry whose signed stop distance d·(entry − stop) is ≤ 0 is `no_risk`: a final exclusion,
  decided at fill, kept out of the fills above (it has no R).

**§7, reversal, replaced.** State is now persisted: the ledger and its marker. Reverting means
removing the ledger code and stopping the writes. The file stays as the record of what was shown,
and must not be edited. Changing T, the looks, the boundary, the grace or the rules needs a new ADR.
The ledger stores those constants, and a ledger written under other constants shows a "constants"
mismatch.

**Unchanged:** T, the cohorts, the gate statistic, the boundary, the rule order, the population and
the live book.
