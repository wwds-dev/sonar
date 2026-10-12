# Spec: a time-stop shadow readout of the live score grade

- Status: draft, **waiting for the owner** (GATE: user-visible and new; architecture touches state and
  the engine thread, see [ADR 0002](../adr/0002-shadow-time-stop-grade.md))
- Owner approval: pending
- Phases: Define (product-manager role) and Architect (architect role), written 2026-10-12 in one
  session. Design (ux-designer) is deferred until the owner approves the direction; constraints for it
  are below. Build, Review, Verify, Secure and Document come after the gate. Both playbooks are
  `status: baseline`, so no radar run has verified them yet. Treat them as stale.
- Sources: `docs/audit/calibration-censoring-by-score.md` (master; its status paragraph is on branch
  `claude/happy-visvesvaraya-84b4ef`), `docs/audit/censoring-options-model-validator.md` (that branch
  only). The evidence script is [`shadow-time-stop-sims.py`](shadow-time-stop-sims.py).

> **Dependency, not landed (checked 2026-10-12 03:52 IST).** `scoring.barrier_probabilities_within`,
> `resolved_hit_probability` and `docs/adr/0001-backtest-baseline-conditional-on-resolution.md` exist
> only as uncommitted work in the main checkout (`git status`: `M sonar/scoring.py`,
> `M sonar/calibration.py`, `?? docs/adr/0001-…`). Master is at `756917f`. They belong to the session
> "SONAR testing plan" (QA-11/QA-13, loop 4, unreviewed). The ADR file's header reads "accepted
> (owner, 2026-10-11)". This spec reads them and does not edit them. **What depends on them:** only
> the secondary readout (the target / stop / neither split against the no-edge reference). The
> primary statistic needs no new maths. The build should still wait until that work lands, because
> both changes edit `sonar/calibration.py`.

## Problem
`calibration.report()` grades closed positions only, and the paper book has no time stop. How long
a position takes to close depends on its score, so the graded set is not a sample of what was
entered. Re-run of the audit note's Reproduce script on the live book, 2026-10-12 03:52 IST
(`portfolio.json` written 03:10):

| score band | entered | closed | still open | closed % | median hold (closed) | median age (open) |
|---|---|---|---|---|---|---|
| 0–20 | 29 | 15 | 14 | 52% | 5.6 d | 4.6 d |
| 40–60 | 16 | 6 | 10 | 38% | 2.5 d | 8.7 d |
| 60–80 | 7 | 1 | 6 | 14% | 15.9 d | 20.1 d |

The book has 52 entries: 51 protocol entries and one manual META, which was closed by hand. 22 are
closed (10 TARGET, 11 STOP, 1 MANUAL) and 30 are open, all filled. Every entry uses the `week` preset
at 1.5:1 with P(profit) 0.40. `report()` shows 21 graded, 47.6% won against 40% promised, 95% range
28–68%, rank IC −0.32 (z = −1.45). The open positions in the upper bands are already older than the
closed ones ever got.

Two consequences:
- The per-band hit rates and the rank IC are computed on quick resolvers. Their sign and size cannot
  be read.
- The quick resolvers are not a neutral subset. A quick close favours the nearer barrier, which is
  the stop. In simulation with no edge but realised volatility that falls with score, the closed-only
  hit IC centres near −0.06 and trips a 2σ test 11–12.5% of the time at n ≈ 194, against about 5% for
  an unbiased test (sims, `null 400 400 1` and `null 400 400 1 5`).

The live bands fit that mechanism. In the 60–80 band, 6 of 7 positions are open at a median age of
20.1 days (about 2.9 horizons). A driftless walk at the planned σ would leave about 12% open at that
age. This is indicative only, at n = 7.

**Who is hurt:** the owner, and any user reading "Is the score right?". Today the readout cannot say
whether the score works, and its negative IC invites a wrong conclusion. The honesty rule in
`app-context.md` makes a misleading grade a bug.

## User and goal
**User:** the owner, deciding whether the score is worth keeping. Secondarily, users who read the
grade.

**Goal:** a grade in which every entry has an outcome by a fixed date, so that score cannot decide
which entries get graded. It is shown beside the existing grade, which stays unchanged.

**Success measure.** All four must hold:
1. **No censoring by construction.** In the test book, outcomes carry no edge but time to resolve
   depends on score. Every entry older than T has an outcome, or an exclusion that is counted and
   shown. The gate statistic rejects at its nominal rate (two-sided 5% overall, ±1.5 pt of
   Monte-Carlo error, at least 2,000 seeded books). The closed-only statistic, run on the same
   books, does not (test V-12).
2. **Live:** by the first look (cohort of 45, about 2026-11-06), each of the first 45 protocol
   entries shows an outcome (target / stop / time) or a counted exclusion in the readout. A
   screenshot of My trades and the landing panel, plus the readout's own counts, proves it.
3. **Read-only:** for the same inputs, `report()` output, `GRADED`, `Z_CLAIM`, every verdict string,
   every row's P(profit) and the exit rule are identical with the shadow present (tests V-11, V-15).
4. **Pre-registered:** T, the cohort sizes, the statistic and the boundary are constants in code,
   pinned by a test, and match ADR 0002. When the readout first appears, no outcome under T has been
   computed. On 2026-10-12 none could be: the oldest entry was 20.1 days old.

## Scope
- A pure function `calibration.shadow_time_stop(open, closed, bars, now)`. For every protocol entry,
  it gives the outcome it would have had under a time stop at `opened_at + T`, marked to market
  (rules: ADR 0002 §1–§5).
- A readout beside the existing grade on My trades and the landing panel. It shows how many entries
  have reached T, the target / stop / time counts, the gate statistic, the rank IC next to the
  closed-only rank IC, the mean R with its range, and the date of the next look. Until a look is due,
  it says it is not a test yet.
- Three pre-registered looks at the first 45, 101 and 201 protocol entries. Each is evaluated once.
- Daily closes from `assets.fetch_bars`, fetched by the holder engine for entries that have passed
  T, kept in memory only.

## Non-goals
- **No live time stop.** Exits stay prices, not dates. `portfolio.mark`, `Position.hit` and the
  protocol are untouched.
- No change to `report()`, `GRADED`, `Z_CLAIM`, `MIN_SAMPLE` or any verdict text. Row P(profit)
  stays the untimed 1/(1+R:R) (T1-1, ADR 0001).
- No new persisted state: no file and no field on `Position`.
- No grading of manual (non-protocol) entries. No cohort grading, which is the fallback below. No
  change to the Lab backtest, where ADR 0001 stands.
- No claim of edge. A significant result says the score ranks how random-direction entries end
  within 4 weeks. It does not show a tradeable edge (Risks).

## Recommendation and fallback
**Recommended (model-validator, 2026-10-11; not approved by the owner):** the shadow readout above.
It removes right-censoring by construction, leaves the live experiment untouched (so no
comparability reset), covers every entry made so far, and can be dropped without migration.

**Fallback, if the owner rejects marking to market:** grade by entry cohort (option 2 of the audit
note). A cohort counts only when all its entries have closed at a barrier, or once it is older than
a cap fixed in advance (20 bars). This is weaker and slower. At the cap, still-open entries must
either be excluded, which keeps the selection, or marked, which is this spec under another name. The
60–80 band would mostly drop out (validator). It remains the option that marks nothing to market.

## Design *(ux-designer, after the gate)*
Constraints for the designer:
- The block sits beside the existing grade. The existing verdict line keeps its words and position.
- "Promised" and "advertised" stay reserved for the row P(profit). For the shadow, use "what no edge
  would give": in 4 weeks, about 37% end at the target, 57% at the stop and 5% at neither, and the
  average result is 0R.
- Before the first look, it says "not a test yet" and gives the next look's date and the count still
  waiting. It must not read like a verdict.
- Counts of exclusions (hand-closed, no price, gaps) are always visible when they are non-zero.
- Wording follows `ui/words.py`. No edge, profit or certainty copy.

## Architecture *(architect)*
See [ADR 0002](../adr/0002-shadow-time-stop-grade.md) for the decision record. In short:
- **Function:** `calibration.shadow_time_stop(open, closed, bars, now)`. It is pure, never mutates
  its inputs, and imports `horizon` for T. `bars` maps a symbol to its `(timestamp, close)` daily
  bars, as `assets.fetch_bars` returns them. It returns a dict with the per-entry outcomes and R, the
  counts, the statistics and the looks.
- **Engine:** only the holder computes it. Each scan, under `book.lock`, it copies the protocol
  positions. It releases the lock, then fetches bars only for entries past T that do not already
  have a barrier outcome before T. That is at most one request per symbol per day, using the
  thread-pool pattern of `core.py:444`. It then calls the pure function. The result travels in the
  payload next to `calibration` (`core.py:406`, `server.py:179`). A follower displays the holder's
  copy and never fetches. If an older holder's payload has no `shadow` key, the follower shows "not
  available from the running agent".
- **State:** none persisted. A restart recomputes the readout from the book and fresh bars, and the
  result is the same because it depends only on the book and final daily closes.
- **Failure modes:** with no network or no bars, entries are counted under `n_no_price` and never
  guessed. An in-progress daily bar is never used as an exit (ADR §3). An agent stall that missed a
  barrier crossing is caught by the daily-close check (ADR §4).

## Risks and open questions
- **The rank IC is not exactly zero-centred under no edge.** Barrier R-multiples are skewed: the
  median is −1 while the mean is 0. When the time-out share varies with score, ranks shift. In
  simulation the rank IC's mean is +0.015 to +0.031 with no edge, and that does not shrink with n.
  At n = 400 it rejects 5.5–7.0% at 2σ (two seeds, 400 books each), while the HC3 slope rejects
  2.8–3.3% (sims, `null 45 2000`, `null 400 400 1` and `null 400 400 1 5`). Hence the recommendation to gate on the
  linear slope and show the rank IC only for comparison (ADR §3).
- **"The ICs differ materially, so the bias is real" is weak evidence at these sizes.** The two
  statistics overlap in sample and differ in kind. In simulation the closed-only bias is about −0.06,
  below one null SE at n ≈ 22. The comparison stays descriptive. The shadow's value is that it does
  not depend on the comparison.
- **Coin-flip direction.** Protocol entries take a random direction, so neither grade can see
  directional skill. With no edge, E[R] = 0 for any σ error, T or barrier placement (optional
  stopping, exact fills), and drift cancels to first order. A positive slope therefore means the
  score predicts how random-direction trades end (path geometry). That is not a tradeable edge, and
  the copy must say so. This is inherited from T1-1 and out of scope here. A model-validator should
  confirm the wording at the gate.
- **Fill flattery.** Barrier exits fill exactly at the barrier and time exits at the daily close,
  with no costs. A constant cost shifts the mean R but not the slope or the IC. Gaps through a
  barrier are recorded at the barrier, as in the live book.
- **Hand-closed protocol positions** are excluded and counted. There are none today. Hand closes
  after a loss would bias the result, so the count is always shown.
- **The protocol cap** (`PROTOCOL_MAX_OPEN = 40`, 30 open now) can delay entries. It blocks top and
  bottom rows alike, so it slows the cohort without selecting by score. The look dates move with it.
- **Open questions for the gate:** see the end of ADR 0002.

## Verification plan *(qa-engineer)*
New tests in `tests/test_calibration.py`, plus engine and UI tests. The suite runs natively and
under `QT_QPA_PLATFORM=offscreen`. Each test names the mutant it must kill.

| # | Test | Mutant it kills |
|---|---|---|
| V-1 | A TARGET close at day 10 (T = 28 d) keeps TARGET, R = +1.5. A STOP close keeps R = −1. | grading a barrier close as TIME |
| V-2 | A TARGET close at day 30 becomes TIME, with R from the T-bar close. | ignoring `closed_at` against T |
| V-3 | Barrier precedence at the cut. `closed_at` one second before the next bar's timestamp counts as the barrier; at that timestamp it is TIME. | `<` / `<=` swap at the cut |
| V-4 | Open past T, LONG and SHORT with the same move, give opposite R. | dropping the direction sign |
| V-5 | R uses \|entry − stop\|: a mark halfway to the target gives +0.75. | dividing by the target distance |
| V-6 | When the T bar is the latest bar (in progress), the entry is waiting, not TIME. | using a non-final close |
| V-7 | With no bar on T's day (holiday), the previous session's close is used, never the next. | look-ahead to the next bar |
| V-8 | A daily close beyond the stop before T, while the book still shows it open, gives STOP and `n_gap = 1`. | skipping the gap check |
| V-9 | A non-protocol entry is excluded and counted. A protocol entry hand-closed before T counts in `n_left`. | grading MANUAL by P&L sign |
| V-10 | With no bars for a symbol, the entry counts in `n_no_price` with no R. | treating a missing price as R = 0 |
| V-11 | Read-only: `report()` output, `GRADED`, `Z_CLAIM` and verdict strings are identical with the shadow present, and the inputs are unchanged (deepcopy compare). | writing `pos.outcome` or `pos.exit` |
| V-12 | Null size, seeded, at least 2,000 books. With score-dependent volatility and no edge, the whole three-look design rejects 5% ± 1.5 pt, while the closed-only snapshot statistic, run on the same books at n ≈ 200, rejects measurably more. With a planted edge (R shifted in proportion to score), power matches the design calculation (0.73 at IC 0.2) within Monte-Carlo error. | rank IC as the gate; naive SE; T = ∞; a boundary per look of 1.96 |
| V-13 | A cohort is the first N entries by `opened_at`. A look is computed once, after its last member resolves, and does not change when later entries resolve. | cohort = the first N to *resolve* (re-selects quick resolvers) |
| V-14 | Pins T per preset (week 28 d, month 112 d, intraday 5.6 d), the looks (45, 101, 201) and the boundary. | silently changing T |
| V-15 | Engine: the holder computes the readout outside `book.lock`; a follower shows the holder's copy; a payload with no `shadow` key renders "not available". | a fetch under the lock; a follower fetching |
| V-16 | The no-edge reference split equals `barrier_probabilities_within(1.5, 1, horizons)` per entry (weekday 4.0, crypto 5.6 horizons). | the untimed 40/60 split |

Mutation-check `shadow_time_stop` and the gate. Run V-12 at release and on any change to the gate
code, marked slow if it exceeds the suite budget.

## CHANGELOG draft (for the Document phase)
**A second grade that waits for no one.** The score grade counts only positions that have closed,
and the slow ones (mostly high scores) were still open, so the grade leaned on quick resolvers. A
second readout now marks every protocol entry at its price four weeks after entry, so every entry
counts. It changes no exit and no odds, and it is tested only at three dates fixed in advance.
