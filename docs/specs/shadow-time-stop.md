# Spec: a time-stop shadow readout of the live score grade

- Status: **approved** (Define and Architect gates; see [ADR 0002](../adr/0002-shadow-time-stop-grade.md))
- Owner approval: 2026-10-12, "go on with your recommendation". All six recommendations in ADR 0002's
  open questions are accepted: shadow readout (cohort grading stays the fallback); T = 28 calendar days;
  gate on the HC3 slope of R on score, rank IC shown for comparison; Pocock 2.315 at 45 / 101 / 201;
  protocol entries only, hand-closed ones excluded and counted; build after the QA-11/QA-13 work lands.
- Next: **Release** (sre-release), an owner gate. Before or at release: the slow suite
  (`./run-tests.sh tests/ -m slow`), the owner's live weekend stamp check (TESTPLAN 11.23), and the
  owner's call on `SH_FINAL_NONE` (Known limits, below).
- Phases: Define (product-manager role) and Architect (architect role), written 2026-10-12 in one
  session. Design (ux-designer), 2026-10-12, below. Build, Review (code-reviewer, domain-finance,
  model-validator; four rounds), Verify (qa-engineer; four rounds), Secure (security-engineer) and
  Document (tech-writer) are **done**, all 2026-10-12 on branch `claude/zealous-mclaren-8985d0`;
  reports in `docs/audit/shadow-time-stop-*.md`. The playbooks are `status: baseline`, so no radar
  run has verified them yet. Treat them as stale.
- Sources: `docs/audit/calibration-censoring-by-score.md` (master; its status paragraph is on branch
  `claude/happy-visvesvaraya-84b4ef`), `docs/audit/censoring-options-model-validator.md` (that branch
  only). The evidence script is [`shadow-time-stop-sims.py`](shadow-time-stop-sims.py).

> **Landed since:** this dependency was committed in `231540b` (QA-11/QA-13) before Build, and
> `docs/adr/0001-…` and `scoring.barrier_probabilities_within` are on this branch. The note below is
> kept as the record at approval.
>
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

## Design *(ux-designer, 2026-10-12)*
Constraints for the designer:
- The block sits beside the existing grade. The existing verdict line keeps its words and position.
- "Promised" and "advertised" stay reserved for the row P(profit). For the shadow, use "what no edge
  would give": in 4 weeks, about 37% end at the target, 57% at the stop and 5% at neither, and the
  average result is 0R.
- Before the first look, it says "not a test yet" and gives the next look's date and the count still
  waiting. It must not read like a verdict.
- Counts of exclusions (hand-closed, no price, gaps) are always visible when they are non-zero.
- Wording follows `ui/words.py`. No edge, profit or certainty copy.

The design below meets those constraints. The ux-designer playbook is `status: baseline` (seeded
2026-10-10, not radar-verified), so it added nothing beyond `AGENTS.md`. Treat it as stale.

### D1. The user's question and the one primary figure
- **Question:** "Leaving out nothing, does a higher score go with a better result after a fixed
  time?" It is the panel's question, "Is the score right?", answered a second way. It is not a new
  question.
- **Primary figure:** the status sentence (`shadow_status`). Before the first look, it shows progress
  toward that look ("12 of the first 45 entries have a result"). Once a look has been evaluated, it
  shows that look's result: z against ±2.315, with the cohort size. Everything else in the block
  supports that sentence.
- **Hierarchy:** the existing verdict stays the panel's first and largest sentence (`text(12)`). The
  shadow status uses `text(11)`. This keeps TESTPLAN 11.9 true and makes the shadow read as the
  second answer, which is accurate until a look exists.

### D2. Placement
One widget, `ShadowGrade(QFrame)`, is used on both pages so that the two copies cannot drift apart.
It takes `detail: bool`. Landing uses `False`; My trades uses `True`, which adds the per-band lines.
It is appended **after** every existing widget of each grade panel, so no existing label changes
position, text or order:
- **Landing, "IS THE SCORE RIGHT?" panel** (`ui/app.py` ~2043–2049): after `self.grade_next` and
  before `lay.addWidget(grade)`, as `self.shadow_grade = ShadowGrade(detail=False)`.
- **My trades, "CALIBRATION — DOES A HIGH SCORE ACTUALLY WIN?" panel** (~1896–1904): after
  `self.bt_result`, as `self.book_shadow = ShadowGrade(detail=True)`.

"Beside" is built as **below, inside the same panel**, not as a second column. A side-by-side
pair would need a resize-driven reflow at the 1280 pt minimum width (the rail collapses below 1420,
`ui/app.py:76`). It would also give the two grades equal weight before the shadow has run a test.
Both pages scroll (landing: `_portfolio_tab` docstring; My trades: `QScrollArea`), so the extra
height costs no layout.

Contents of the widget, top to bottom:

| # | element | font, colour | content |
|---|---|---|---|
| 0 | hairline | 1 px `theme.BORDER`, with 6 px space above | `_hline()`: the horizontal twin of `_vline()` |
| 1 | header row | `HelpHeading(SH_HEAD, "grading", SH_TIP)` on the left; `shadow_count` `figure(8)` FAINT on the right | the heading links to §10 of the manual, where the tech-writer adds a sub-heading for this grade |
| 2 | `shadow_status` | `text(11)` INK, wrap | **the one primary sentence** (D3) |
| 3 | `shadow_rows` | `figure(10)` MUTED, wrap | split, waiting, reference, running, comparison, earlier looks, exclusions, gaps; on My trades also per band (D4) |
| 4 | `shadow_warn` | `figure(10)` GOLD, wrap; hidden when empty | the more-than-10%-excluded note, which always starts with "Note:" |
| 5 | `shadow_note` | `figure(9)` FAINT, wrap | the R explanation, the mandatory caveat, and when it was worked out (or the stale text) |

Exclusions go in row 3 (MUTED), not row 5 (FAINT), because the constraint requires them to stay
visible.

### D3. States and the status sentence
The UI reads `self.live.shadow`. The engine sets it on the holder; `_mirror_book` copies it from
`/api/book` on a follower. Precedence, first match wins:

| state | condition | `shadow_status` (string id) | rows shown |
|---|---|---|---|
| (e) not available | follower, and the holder's payload has **no `shadow` key** (kept as a sentinel distinct from `None`) | `SH_NOT_AVAILABLE` | none; the note keeps the caveat only |
| loading | key present, value `None`: the holder has not finished its first computation | `SH_LOADING` | none |
| error | dict with `error` set (the engine caught an exception; it keeps the last good dict alongside) | `SH_ERROR`; if a last good dict exists, render it below as usual | as for that dict |
| (a1) empty | `n_entered == 0` | `SH_EMPTY` | none |
| (a2) nothing at T | `n_reached == 0` | `SH_NONE_AT_T` | waiting, plus exclusions if non-zero |
| (a3/b) before look 1 | no look evaluated; look 1 not yet due | `SH_BEFORE_LOOK` (or `SH_BEFORE_LOOK_UNDATED` if the 45th entry does not exist yet) | all of D4 that applies |
| (f) look due, prices missing | a look is due, but members are still `wait_price` | `SH_LOOK_WAITING_PRICE` | all of D4 |
| (c) look evaluated, not crossed | latest evaluated look has \|z\| < 2.315 and looks remain | `SH_LOOK_NOT_CROSSED` + `SH_NEXT_LOOK` / `SH_NEXT_LOOK_UNDATED` | all of D4, with earlier looks under `SH_ROW_PAST_LOOK` |
| (c) crossed | any evaluated look has \|z\| ≥ 2.315 (the first crossing is the result, and the design is closed) | `SH_LOOK_CROSSED_UP` or `_DOWN` by the sign of z, then `SH_CAVEAT_CROSSED` | all of D4; the running line keeps its "not a test" label |
| (d) closed, no crossing | three looks evaluated, none crossed | `SH_FINAL_NONE` | all of D4 |

- **"Between looks" (b):** the running statistics line (`SH_ROW_RUNNING`) always starts with "running,
  not a test". It appears only once `n_reached ≥ 20`. Below that, `SH_ROW_RUNNING_WAIT` shows instead.
  20 matches the existing grade's minimum (manual §10), which keeps the shadow from showing a slope
  fitted on a handful of entries. This is a display rule only; it does not change the looks.
- **Next look date:** when the cohort's Nth entry (by `opened_at`) exists, the date is that entry's
  t_T, shown as "on or after {date}". Evaluation also needs a final bar and every member resolved, so
  "on or after" is literal. When the Nth entry does not exist yet, no date is projected. The text gives
  the number of entries still to be entered. On 2026-10-12, look 1 has a date (the book holds 51
  protocol entries) and looks 2 and 3 are undated.
- **Stale:** `shadow_note` always ends with `SH_WORKED_OUT`. When `computed_at` is more than 26 hours
  old (a daily-close readout, plus slack), `SH_STALE` replaces it. On a follower, this is also how a
  dead holder shows.
- **(f) No network:** a fetch failure never becomes a number. An entry past t_T with no final close
  counts in `n_wait_price` ("waiting for a closing price"). After 7 days without one it moves to
  `n_no_price` (ADR §4) and appears under "left out". So a network outage shows first as a rising
  waiting count and then as a counted exclusion.
- **(g) Exclusions:** `SH_ROW_LEFT_OUT` lists only its non-zero parts, and the row is hidden only
  when all three are zero. `n_gap` entries *are* graded (at the barrier), so they get their own row,
  `SH_ROW_GAP`, not a place under "left out". On 2026-10-12 the row reads "left out and counted: 1
  chosen by hand" (META).
- **(h) More than 10% of a cohort excluded:** when (`n_left` + `n_no_price` within the cohort) / N
  > 0.10 for an evaluated or due look, `shadow_warn` shows `SH_WARN` for that look. It stays visible
  for as long as the look's result is shown.

### D4. Numbers and formats
Rows in `shadow_rows`, in this order. Each row is omitted when its inputs are absent:
1. `SH_ROW_SPLIT`: entries with an outcome, as target / stop / time counts, each with its share of
   `n_reached` as a whole percent (they need not sum to 100).
2. `SH_ROW_WAITING`: `n_waiting` (not yet at T) with the next date an entry reaches T, and
   `n_wait_price`. Only non-zero parts are shown.
3. `SH_ROW_REF`: the no-edge reference split, as whole percents of the same entries
   (Σ per-entry `barrier_probabilities_within` ÷ `n_reached`), plus the conditioned 0R sentence ("with
   no edge, exact fills and randomly wandering prices, the average result would be about 0R";
   fix loop 2). If ADR 0001
   has not landed, this row and every per-band reference part are **omitted, not dashed**.
4. `SH_ROW_RUNNING` (or `_WAIT`): the mean R with its 95% range for the average, the gate
   statistic z (HC3 slope), "before costs" and "an average above 0 here is not a trading edge"
   (fix loop 2).
5. `SH_ROW_IC`: the rank IC on all graded entries, beside the closed-only rank IC **on the same
   entries** (ADR §3), labelled "for comparison only, not a test". It is shown with the running row,
   at `n_reached ≥ 20`.
6. `SH_ROW_PAST_LOOK`: one line for each evaluated look other than the one in the status sentence.
7. `SH_ROW_LEFT_OUT`, then `SH_ROW_GAP`.
8. My trades only (`detail=True`): `SH_ROW_BAND` for each score band with `n ≥ 1`, using the same
   bands and `_band_top` as the existing table. This puts the reference split per band (ADR §2).

**Formats** (ASCII hyphen-minus throughout, so the strings can be grepped):
- z: signed, 2 decimals (`+0.84`). If 2.305 ≤ |z| < 2.325, show 3 decimals so the shown value can
  never contradict the verdict, which is decided on the unrounded value. The boundary always shows
  as `2.315`.
- R: signed, 2 decimals, with an `R` suffix (`+0.12R`). Range: `{lo:+.2f} to {hi:+.2f}R`.
- IC: signed, 2 decimals (the existing grade's `:+.2f`).
- Percentages: whole numbers. Counts: integers.
- Dates: `_day_text` (`%-d %b`, e.g. "6 Nov"), with ` %Y` added when the year differs from now
  ("7 Jan 2027"). `computed_at`: `%-d %b %H:%M`, local time.
- {T}: from the entries' `t_days`. 28 gives "4 weeks" and `{T_adj}` "4-week"; 112 gives "16 weeks";
  5.6 gives "5.6 days"; other values give "{d:g} days". If one readout mixes values of T, use
  "4 holding periods" and `{T_adj}` = "fixed-time". All 51 live entries are 28 days.
- {rr}: the plan's R:R as `:g` (1.5).

**Fields the design reads from the shadow dict.** The names are proposed; the meaning is what
matters. They are all counts or statistics inside the dict that the architecture already returns, so
they add no new persisted state:
`n_entered, n_reached, n_target, n_stop, n_time, n_waiting, next_t, n_wait_price, n_nonprotocol,
n_left, n_no_price, n_gap, z, ic, ic_closed, mean_r, mean_r_lo, mean_r_hi, ref{target,stop,neither}
| None, t_days, rr, looks[3]{n, due | None, n_missing, evaluated, z, n_excluded}, bands[], computed_at,
error`. Two of these, `n_wait_price` and `ic_closed` on the same entries, are not named in the
Architecture section. The engineer should add them to the function's return value, or ask the
architect.

### D5. Accessibility and narrow widths
- **Colour is never the only signal.** Crossed or not is stated in words ("crossed the line" / "did
  not cross"). A crossing gets **no** green or red, because that would read as good or bad money. The
  GOLD warning always starts with the word "Note:". Nothing in the block uses `theme.UP`/`DOWN`
  except the heading's existing link colour.
- **Contrast** on `PANEL` #1a212c, measured with the WCAG formula on `ui/theme.py` values: INK 14.4:1,
  MUTED 8.5:1, GOLD 10.2:1, FAINT 5.2:1. All pass AA for body text (4.5:1). FAINT carries only
  secondary text (the count, R, caveat and time); no exclusion or result is FAINT.
- **Sizes:** the existing panel's sizes are reused (8/9/10/11 pt); nothing is new or smaller.
- **Keyboard:** the block is read-only text with no new controls. The one link is the existing
  `HelpHeading` pattern, which is mouse-only today, as it is for every heading. The manual stays
  reachable from the Learn tab by keyboard. This is an existing gap, out of scope here; it is a
  candidate for the next UX audit. Set `setAccessibleName("Second grade, every entry at a fixed
  date")` on the frame so VoiceOver announces the block.
- **Narrow:** every label except `shadow_count` is `wrap=True`. Per the `label()` docstring, an
  unwrapped long row would set the window's minimum width. At the 1280×775 minimum, rows wrap rather
  than clip. The header count elides nothing: it is at most about 20 characters, beside a stretch.
  The block adds about 7 lines on landing and about 10 on My trades with three bands. Both pages
  scroll.
- **Wording modes:** each string is a `(plain, expert)` pair picked with `words.pick`, as
  `ATTRIBUTION_HEADS` is. Both modes keep the same rows and the same order (`ui/words.py`
  docstring). The mandatory caveat and "before costs" appear in **both** modes (fix loop 2; it read
  "no costs" until domain review r2 P2-1).

### D6. The strings (one place: `SHADOW_WORDS` in `ui/app.py`, beside `ATTRIBUTION_HEADS`)
Placeholders are in `{braces}`. "·" separates optional parts; each part is dropped when its count is
zero.

| id | plain (default) | expert |
|---|---|---|
| `SH_HEAD` | EVERY ENTRY, GRADED AT A FIXED DATE | TIME-STOP SHADOW |
| `SH_TIP` | A second grade, beside the one above, which counts only closed positions. Here every protocol entry gets a result a fixed time after it opened (4 weeks on the week profile): at the target, at the stop, or at that day's close if it reached neither. Slow entries count too. It is tested only at three looks fixed in advance: the first 45, 101 and 201 entries. | *(same)* |
| `SH_COUNT` | {reached} of {entered} at {T} | {reached}/{entered} past T |
| `SH_ROW_WINDOW` | the {n} with a result opened {first} to {last} | {n} graded: opened {first} to {last} |
| `SH_ROW_WINDOW_NONE` | entries opened {first} to {last} (none has a result yet) | opened {first} to {last} (none graded yet) |
| `SH_ROW_WINDOW_UNDATED` | ({k} with no readable date) | ({k} undated) |
| `SH_NOT_AVAILABLE` | Not available from the running agent. It is an older version than this window. | Not available from the running agent (older version). |
| `SH_LOADING` | Working it out: this needs a scan and a few daily closes. | Computing: waits for a scan and daily closes. |
| `SH_ERROR` | Could not work it out this time ({reason}). Nothing is guessed; the next scan tries again. | Error: {reason}. Nothing guessed; retried next scan. |
| `SH_EMPTY` | Not a test yet: there are no protocol entries. Protocol mode on My trades makes them. | Not a test yet: no protocol entries. |
| `SH_NONE_AT_T` | Not a test yet. None of the {entered} entries has had {T} yet; the first gets there on {next_t}. | Not a test yet. 0/{entered} past T; first on {next_t}. |
| `SH_BEFORE_LOOK` | Not a test yet. {have} of the first {N} entries have a result; the {ordinal} look is on or after {due}. | Not a test yet. {have}/{N} graded for look {k}; due on or after {due}. |
| `SH_BEFORE_LOOK_UNDATED` | Not a test yet. {have} of the first {N} entries have a result; {missing} of them are not entered yet. | Not a test yet. {have}/{N} graded for look {k}; {missing} not yet entered. |
| `SH_LOOK_WAITING_PRICE` | Not a test yet. The {ordinal} look is due; {w} of its {N} entries are still waiting for a closing price. | Not a test yet. Look {k} due; {w} of {N} awaiting a final close. |
| `SH_LOOK_NOT_CROSSED` | Look {k} of 3, first {N} entries ({used} with a result): no link strong enough to cross the line yet. z = {z}; the line is ±2.315. | Look {k}/3, n = {N} ({used} graded): HC3 slope z {z}, \|z\| < 2.315, not crossed. |
| `SH_NEXT_LOOK` | Next look: the first {N2} entries, on or after {due}. | Next: n = {N2}, due on or after {due}. |
| `SH_NEXT_LOOK_UNDATED` | Next look: the first {N2} entries, after {missing} more are entered. | Next: n = {N2}, {missing} not yet entered. |
| `SH_LOOK_CROSSED_UP` | Look {k} of 3, first {N} entries ({used} with a result): crossed the line. On these paper entries, higher scores went with higher R on average. z = {z}; the line is ±2.315. The test ends here. | Look {k}/3, n = {N} ({used} graded): HC3 slope z {z}, \|z\| ≥ 2.315, crossed. Design closed. |
| `SH_LOOK_CROSSED_DOWN` | *(as above, with "lower R on average")* | *(same as UP)* |
| `SH_CAVEAT_CROSSED` | This says only that the score sorted how these past coin-flip paper entries ended after {T}. It does not show that trading by score would make money: it is one test on {used} entries, before costs, fees and slippage, with exact fills, and a test like this can cross by chance even when there is no link. It is not a trading edge. | Ranks past random-direction paper outcomes at T only; before costs, exact fills, one test with a by-design false-alarm rate; not a tradeable edge. |
| `SH_FINAL_NONE` | Three looks, no crossing: no evidence that the score ranks {T_adj} results, at the planned size. The test is finished. | Looks 1-3 not crossed: no evidence that the score ranks {T_adj} results, at the planned size. Design closed. |
| `SH_ROW_SPLIT` | {reached} with a result: {t} at the target ({tp}%) · {s} at the stop ({sp}%) · {x} at neither, valued at the close after {T} ({xp}%) | {reached} graded: target {t} ({tp}%) · stop {s} ({sp}%) · time {x} ({xp}%) |
| `SH_ROW_WAITING` | still waiting: {w} not yet at {T} (the next on {next_t}) · {wp} waiting for a closing price | waiting: {w} before T (next {next_t}) · {wp} awaiting a final close |
| `SH_ROW_REF` | what no edge would give after {T}, if the volatility estimate was right: about {a}% at the target · {b}% at the stop · {c}% at neither. A different split can mean the volatility estimate was off. With no edge, exact fills and randomly wandering prices, the average result would be about 0R. | what no edge would give at planned σ: {a}% / {b}% / {c}% (a σ̂ check); mean ≈0R at any σ (exact fills) |
| `SH_ROW_RUNNING` | running, not a test: paper average {m}R (95% range for the average {lo} to {hi}R) · link z = {z} · before costs; an average above 0 here is not a trading edge | running, not a test: mean R {m} [{lo}, {hi}] · HC3 slope z {z} · pre-cost; mean > 0 is not a tradeable edge |
| `SH_ROW_RUNNING_WAIT` | running figures start at 20 results; {k} to go | running stats from n = 20; {k} to go |
| `SH_ROW_IC` | for comparison only, not a test: rank correlation {ic} on these entries at {T}, {icc} on the closed ones alone | descriptive only: rank IC {ic} (all at T) vs {icc} (closed only) |
| `SH_ROW_PAST_LOOK` | look {k}, first {N}: z = {z}, did not cross the line | look {k}, n = {N}: z {z}, not crossed |
| `SH_ROW_LEFT_OUT` | left out and counted: {m} chosen by hand · {l} closed by hand before {T} · {p} with no closing price | excluded: {m} non-protocol · {l} hand-closed before T · {p} no price |
| `SH_ROW_GAP` | {g} counted at the target or stop price because a daily close went past it between checks (a real fill could have been different, often worse at a stop) | {g} gap exits, filled at the barrier, not the close beyond it |
| `SH_ROW_BAND` | scores {lo}-{hi}: {n} with a result · {t} target · {s} stop · {x} neither · what no edge would give if the volatility estimate was right: {a}% / {b}% / {c}% | score {lo}-{hi}  n={n}  T/S/N {t}/{s}/{x}  no edge @σ̂ {a}/{b}/{c}% |
| `SH_WARN` | Note: {x} of the first {N} entries were left out ({pct}%). This look rests on the other {used}. | Note: {x}/{N} excluded ({pct}%) at look {k}. |
| `SH_NOTE` | R is the result in units of the amount risked: -1R lost the amount risked, +{rr}R reached the target. This grade asks only whether the score sorts how coin-flip entries end after {T}. These are paper entries with a random direction, before costs, fees and slippage. Even a crossed line is not a trading edge and says nothing about how future entries end. | R = result / initial risk. Ranks random-direction outcomes at T only; not a tradeable edge. Paper; before costs, fees and slippage; exact fills. |
| `SH_WORKED_OUT` | Worked out {when}. | As of {when}. |
| `SH_STALE` | Not updated for {h} hours: the agent may be stopped. | Stale: {h} h old. |

Build changes to this table (engineer, 2026-10-12): `SH_ROW_SPLIT` plain read "valued at the {T}
close", which renders as "the 4 weeks close"; it now reads "valued at the close after {T}".
`SH_LOOK_WAITING_PRICE` used `{k}` twice (the look and the count) in both modes; the count is now
`{w}`, the members of that look not yet final.

Fix loop 1 (engineer, 2026-10-12, from `docs/audit/shadow-time-stop-domain-finance.md` P1-1 and
P1-2): `SH_LOOK_CROSSED_UP`/`_DOWN` (plain), `SH_CAVEAT_CROSSED` (both modes), the last sentence of
`SH_NOTE` (plain), `SH_ROW_REF` and the `SH_ROW_BAND` tail (both modes) take the reviewer's wording,
with three departures:
- The `SH_NOTE` sentence ends "says nothing about how future entries end", not "will end", because
  "will " is a banned forecast word (U-1).
- `SH_ROW_REF` expert keeps the owner-mandated phrase "what no edge would give" ("…at planned σ"),
  where the reviewer wrote "no-edge split".
- The plain `SH_ROW_BAND` tail keeps "what no edge would give" with the condition after it ("…if the
  volatility estimate was right"), so the phrase and U-6's omission rule both hold.

No copy states a false-alarm rate. The caveat says only that a test like this "can cross by chance".

`{ordinal}` is first / second / third. The word "edge" appears only in the mandated reference
phrase "what no edge would give" (band form "no edge @σ̂"), in the reference's condition "with no
edge, exact fills and randomly wandering prices", and in negations ("not a trading edge", "not a
tradeable edge"). `EDGE_ALLOWED` in `tests/test_shadow_ui.py` lists exactly these (fix loop 2,
domain r2 N-4).

Fix loop 2 (domain r2 P2-1, N-1, N-2, N-3):
- The running row says "paper average", "95% range for the average", "before costs" (expert:
  "pre-cost") and "an average above 0 here is not a trading edge".
- The expert note replaces "No costs." with "Paper; before costs, fees and slippage; exact fills."
- `SH_ROW_GAP` says gap exits are counted at the barrier price.
- `SH_ROW_REF` states the conditions for its 0R ("with no edge, exact fills and randomly wandering
  prices … about 0R"), and its "mostly means" is now "can mean".
- The crossed caveat negates "trading by score", which covers a downward crossing too.

### D7. Tests the design adds (for the qa-engineer's plan)
- **U-1.** Every `SHADOW_WORDS` string, in both modes, plus the rendered text of `shadow_status`,
  `shadow_rows`, `shadow_warn` and `shadow_note` in every D3 state, contains none of `FORECAST_WORDS`
  (`tests/test_landing_figures.py:136`). It also contains none of "promised", "advertised", "profit",
  "certain" or "guarantee". Note that the existing tests match substrings, so "buy" inside
  "buyability" or "expect" inside "expected" would fail them.
- **U-2.** With the shadow present, in every state, the text of `grade_verdict`, `grade_rows`,
  `grade_next`, `grade_count`, `cal_verdict` and `cal_table` is identical to the text without it.
  This extends V-11/V-15, and TESTPLAN 11.9 still holds.
- **U-3 (new TESTPLAN 11.9b).** The landing `shadow_status` text equals the My trades
  `shadow_status` text, word for word.
- **U-4.** One test per D3 row, each asserting its string id's text. This includes: a payload
  without the `shadow` key renders `SH_NOT_AVAILABLE`; "not a test yet" is present until a look is
  evaluated; "not a test" stays on the running row in every state; and `SH_FINAL_NONE` contains
  "no evidence that the score ranks 4-week results, at the planned size".
- **U-5.** A non-zero `n_nonprotocol`, `n_left`, `n_no_price` or `n_gap` each appears in
  `shadow_rows`. With 5 of 45 excluded (11%), `shadow_warn` is visible and starts with "Note:"; with
  4 of 45 (8.9%) it is hidden.
- **U-6.** If `ref` is `None`, the text contains no "what no edge would give" and no dash in its
  place.
- **U-7.** z = 2.3149 shows 3 decimals and reads "not crossed"; z = 2.3151 reads "crossed".
- **U-8.** At the 1280×775 minimum window, the landing page's minimum width does not grow with the
  shadow block present (`test_layout`).

### D8. For the tech-writer (Document phase)
Add a sub-heading to manual §10 (`static/docs.html`, `id="grading"`). It should cover: why closed-only
grading leans on quick resolvers; the fixed-date result and R; the three looks and the line at
2.315; "what no edge would give"; and the caveat. The heading links to `grading`, because
`_show_learn` selects a contents row, and sub-anchors are not verified to work.

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

### Build notes *(engineer, 2026-10-12)*
Decisions taken where the spec or ADR left a choice, each read as close to ADR 0002 as possible.
Code: `sonar/calibration.py` (the shadow section), `sonar/core.py` (`_shadow_pass`,
`_shadow_fetch`, `_shadow_range`, `_mirror_book`), `sonar/server.py` (`/api/book`), `ui/app.py`
(`SHADOW_WORDS`, `shadow_texts`, `ShadowGrade`). Report: `docs/audit/shadow-time-stop-engineer.md`.

1. **An entry is graded only from its t_T.** A barrier hit on day 10 is final, but it counts from
   t_T on, like every other entry. Counting it earlier would let the running figures lean on the
   quick resolvers again. The looks are unaffected: a look waits for all its members anyway.
2. **Which bars the gap check reads.** Bars stamped after `opened_at`, up to and including the T bar.
   A bar is stamped at its session's start, so only those bars' closes are certainly after the
   entry. The entry day's own close may come before the entry, and the live polls watched that
   session anyway. Any decision that needs bars waits until the T bar is final, because an open
   position can still hit a barrier in the T session before the cut, which rule 1 would grade.
3. **Coverage and range.** The series must start at or before `opened_at`; otherwise the gap check
   is incomplete and the entry waits for a price (`n_wait_price`, then `n_no_price` after 7 days).
   The engine asks for the shortest Yahoo range whose reach is at least the age of the symbol's
   oldest entry that needs bars, plus 7 days: 3mo (90 days), 6mo (182), 1y (365), 2y (730),
   5y (1,826).
4. **Hand closes.** A protocol entry closed by hand before the cut is excluded (`n_left`) before
   the gap check, so no hand-closed entry is ever graded. One closed by hand after the cut is
   graded like an open one. A hand close at or before t_T is counted as soon as it happens.
5. **R** = d·(exit − entry)/|entry − stop|, with the exit at the barrier for barrier and gap
   outcomes. This equals +R:R and −1 whenever the fill was at the planned entry, which is always
   true on the internal paper book. A worse broker fill moves the entry, not the barriers.
6. **Decided outcomes, and what can still move** (rewritten in fix loop 1; the first version was
   wrong). Before the fix, the readout was recomputed from that day's bars on every pass. **One
   failed request on any day was enough** to take away every graded entry of a symbol and
   re-evaluate a look on a different subset (code review P1-1), not "an outage of more than a week".
   Rewritten old closes, for example Yahoo's split adjustment, could likewise re-grade an entry. Now:
   - A failed request keeps the series already held, instead of replacing it with nothing.
   - The engine keeps each entry's outcome in memory once it is decided (`calibration.
     shadow_decided`: target, stop, time, or left), keyed by position id. It hands the outcome back on
     every later pass, and the pure function copies it instead of recomputing.
   - Decided entries need no more bars, so they are no longer fetched.

   Within one process, a decided outcome and an evaluated look therefore never change. Two exposures
   remain, both by design:
   - **"No price" is not memoised**, because closes may still come. A look that counted a member as
     no price changes if that member's closes arrive later.
   - **The memo is in memory only** (ADR §7 unchanged): a holder restart decides again from the book
     and fresh closes, so an outage or a split at restart time can still move an outcome.

   **Owner question, not built:** whether to persist decided outcomes and evaluated looks across
   restarts.
7. **Looks.** `due` is the latest t_T among the N members, which is the Nth entry's t_T when T is
   the same for all. `n_missing` is the number of members not yet entered. A look also reports
   `entered`, `used` (graded), `n_excluded`, `n_waiting`, `n_wait_price`, `crossed` and
   `design_closed`.
8. **The closed-only rank IC on the same entries** (`ic_closed`) is report()'s statistic
   (confidence against TARGET = 1 / STOP = 0) over the graded entries that the book closed at a
   barrier, at any time. Their count is `n_closed_same`.
9. **Reference horizons.** Each entry uses `barrier_probabilities_within(rr, 1.0, h)` with h = 4 on
   weekday instruments and h = 4 × 7/5 = 5.6 when the asset class is `Crypto`.
10. **`t_days` and `rr`** are the value all entries share, or None when they differ. The UI then
    says "4 holding periods" and uses the default R:R.
11. **The gate.** `hc3_z` is the sims' `hc3_z`, except that it returns None, not 0.0, when the
    residual variance is zero or a point's leverage reaches 1. The dict never holds NaN or infinity.
12. **The engine** copies every filled position under `book.lock`. It needs the manual ones only to
    count `n_nonprotocol`. An error keeps the last good dict and adds `error`, which holds the
    exception's class name only, so no long or untrusted text reaches the screen. `Live.shadow`
    starts as None (loading). A follower whose holder sends no `shadow` key holds the string
    `"unavailable"`. Any other non-dict value is ignored. Taking the book resets the value to None.
13. **UI states.** (a2) "nothing at T" applies only while no entry is past T (no `wait_price` and no
    `no_price`). Otherwise the look states apply. The waiting and left-out rows drop zero parts but
    keep their lead-in. The split row always shows all three counts. Within [2.305, 2.325) z is cut
    to three decimals and clamped to the verdict's side, so 2.3149 shows as 2.314.
14. **TESTPLAN.** The landing-equals-My-trades case is **11.14**, not 11.9b, because the page
    generator accepts only `N.N` ids. Cases 11.15–11.21 are new manual cases for the QA plan.
15. **V-12, as built.** The walk model is the sims' model, made fast by scale invariance. A walk of
    vol s against (+1.5, −1) is a unit walk against (+1.5/s, −1/s), so a library of unit paths,
    each stored as running-maximum and running-minimum records, answers any s with two bisections.
    A test checks the library against a direct step-by-step walk. The design runs through the
    production `shadow_looks`. Always on: 1,000 null books and 500 power books (about 3 s).
    Marked `slow` and deselected by default (`./run-tests.sh tests/ -m slow`): the spec's 2,000
    books, with the closed-only comparison; 20,000 null books; and 10,000 power books.
    **Measured** (steep gradient, s = 1.3 → 0.5; seeds in the tests):
    - Null size at 2,000 books (seed 20261012, 50,000-path library): 5.35%. On the same books,
      the closed-only rank IC at 2σ rejected 13.6% (n ≈ 194 closed).
    - Null size at 20,000 books over ten libraries: 6.19% (Monte-Carlo SE 0.17 pt) with
      20,000-path libraries, and 5.95% with 50,000-path libraries. Independent checks gave 5.9%
      (20,000 books, flat vol) and 5.8% (6,000 books, fresh walks, no library).
    - Power at a planted correlation of 0.2: 0.741 at 2,000 books, 0.739 at 10,000 books, against
      the design calculation of 0.73.

    The real size is about **6%, inside 5 ± 1.5 but above 5**. The HC3 z has slightly heavy tails
    at n = 45: look 1 alone rejects 2.7%, against Pocock's 2.06%.

    **Owner decision 2026-10-12:** the measured size (5.9–6.2% over 20,000 null books, the excess
    from look 1) is accepted. ADR 0002 is not amended, and the boundary stays 2.315 with the looks at
    45 / 101 / 201. The 2,000-book test
    (`test_v12_the_design_holds_its_size_where_the_closed_only_grade_does_not`) keeps the spec's
    5% ± 1.5 pt bar. The 20,000-book precision mean is held to the measured 5.7–6.7% (note 24). No user-facing copy states a
    false-alarm rate.
16. **The newest bar's close is never used, and its stamp only on the session pattern** (fix loop
    1, code review P1-2; fix loop 2, r2 P2-B; rewritten in fix loop 3 for code review r3 P2-1).
    - Yahoo can stamp the in-progress bar with the fetch time (EURCHF=X read `10-12 11:17`). A
      finished newest bar fetched over a weekend may also carry a last-trade or fetch-time stamp;
      that is not verified.
    - Fix loop 2 trusted the newest bar when its stamp was ≥ 24 h before its fetch, and otherwise
      bounded the cut by `stamp − 24 h`. Both assume the stamp lies in its session, and the trusted
      path assumes the stamp *is* the session start. Under a last-trade or fetch-time weekend stamp,
      a Friday t_T was graded at Thursday's close and flipped on Tuesday: the round-1 bug back. Fix
      loop 3 removes the fetch-time trust, the bounded cut and the engine's stored fetch times.
    - **Now** (`_shadow_newest_is_a_session_start`): the newest bar's stamp is used only when its
      time of day equals the bar before it, `(s[-1] − s[-2]) % 86 400 == 0`, which is the
      session-start pattern. Then it is the exact cut, whatever its age. Its close is never used:
      it can be neither the T bar with a cut after it, nor a gap-checked close.
    - Off the pattern, the newest bar is dropped, as in fix loop 2. A DST change or a shifted FX
      stamp breaks the pattern for one day and costs one day of waiting (tested).
    - **Checked** against the reviewer's three conventions (session start, fetch time, last trade;
      `cr3/stamp.py` run on this tree): no outcome flips, and nothing is graded at a close before
      t_T.
      - Session-start stamps decide a Thursday T on Saturday and a Friday T on Tuesday.
      - Fetch-time and last-trade stamps take **up to 3 days longer**: a Thursday T is decided on
        Tuesday, not Saturday (code review r4 P3-A; this note said "two days" until the Document
        phase).
      - A booked TARGET after the cut is never moved before it.
    - **Measured** (`test_r2_latency_*`, US-session bars with **session-start stamps**, one fetch a
      day at 00:01 UTC):
      - A Monday–Thursday T is decided **1.4 days** after t_T, and a Friday T **3.4 days** after.
      - A holiday can stretch this to **4.4 days** (a Thursday T before a Friday holiday, or a
        Friday T before a Monday holiday).
      - A first pass later than 00:01 adds its delay (07:00: **4.7 days**).
      - The worst of these leaves **2.3 days** before the 7-day grace makes an entry "no price".
        That margin holds for session-start stamps on US bars only.
    - **Worst cases under the other conventions** (code review r4 P3-A, the reviewer's `cr4/`
      scripts on synthetic bars; not in the suite):
      - A US holiday under **last-trade** stamps (a Thursday T before a Friday holiday) is decided
        at the Wednesday 00:01 fetch, **5.4 days** after t_T, or **5.7 days** with a 07:00 first
        pass. That leaves **1.3 days** of grace.
      - Markets whose session starts near 00:00 UTC, such as **^N225** and **^KS11** (both in the
        universe), with **fetch-time** stamps on the in-progress bar: the newest bar is off the
        pattern at every 00:01 fetch and is dropped, so every T waits a day more (a Monday T, 0.7 →
        1.7 days). In Golden Week 2026 a Friday T is decided **6.73 days** after t_T, leaving
        **0.27 days** of grace.
      - Outcomes stay correct in every case. The risk is the grace limit: `shadow_looks` counts
        `no_price` as a final exclusion, and the memo does not keep it, so an entry that passes the
        limit can let a look be evaluated without it, and then be graded a day later. This is older
        than fix loop 3, which only narrows the margin under the unconfirmed conventions. See Known
        limits.
    - The FX Sunday case is graded at Wednesday's read at Monday's close, never at Friday's. In
      production the live row is also stamped after `now`, because the pass takes `now` before it
      fetches (code review r3 P3-1), so it is dropped either way. B1, B2 and B3 wait, then grade at
      day 28's close.
    - **Open, for the owner:** verify the weekend stamp live with a Saturday or Sunday fetch after
      00:00 UTC of ^GSPC, META, EURCHF=X, TRX-USD and ^N225, and record the newest stamps in ADR §5
      (TESTPLAN 11.23). The rule above grades correctly under any of the conventions, so this is a
      confirmation, not a dependency; what the answer changes is the waiting time and the grace
      margin above.
17. **Bars stamped after `now` are ignored** (security P2-2), so a future stamp cannot make an
    in-progress bar look final.
18. **Payload timestamps** (security P2-1, code review P2-2). The UI reads a timestamp only within
    0 to 4e10 seconds (1970 to about 3237); outside that range it shows n/a. `ShadowGrade.render`
    also catches `OSError`. Both pages refresh the shadow block after the existing grade, so nothing
    in the block can hold that grade up.
19. **Wrong closes, not only missing ones** (security P2-2 and P3-3, code review P2-1).
    - Bars are validated row by row: a row that cannot be read (a stamp of 10**400, a missing field) is
      dropped on its own, so it no longer fails the whole readout.
    - Closes at or below zero are dropped, as non-finite ones already were.
    - **Split guard,** `SHADOW_SPLIT_GUARD = 4.5` **daily σ**, pinned by a test, including the
      comparison at exactly the bound. A series is unusable for an entry when its last close at or
      before `opened_at` is more than 4.5 · |entry − stop| / √momentum_days from `p.entry`. Yahoo
      split-adjusts old closes after the fact, so a split at any time after the entry rescales that
      close.
      - Why daily σ: fix loop 1 used 2 stop distances. A stop distance is daily σ × √momentum_days,
        so that bound grew with the preset, to 31.6 daily σ on year. It missed a 2:1 split on quarter
        at 3.5% a day (code review r2 P2-A), and on intraday it was only about 2 daily σ (QA r2 P3-6).
      - Why 4.5: it equals week's former 2 stop distances (2√5 ≈ 4.47). The entry is at most a
        session from that close, so a false alarm needs a rare gap, and a false alarm is counted.
      - On every preset it catches a 2:1 split below about 11% daily σ and a 3:2 split below about
        7%. This is tested for all five presets at 3.5%.
      - Why not a ratio band: a band such as [0.5, 2] would let 3:2 through, and even an exact 2:1.
      - `events=split` is not requested: `fetch_bars` does not support it and its other callers stay
        unchanged.
    - An entry with an unusable series is `wait_price` and then `no_price`: counted, never guessed. An
      entry decided before a split keeps its outcome through the memo of note 6.
    - **Residual:** a single wrong close mid-series that stays positive and plausible, such as a bad
      tick through a barrier, still grades a gap exit. It cannot be told from a real move.
    - **Free side effect:** decided entries are no longer fetched (note 6), so the daily request count
      no longer grows with every entry graded. This eases security P3-4 but does not cap it.
20. **Checked against the model-validator's cases** (`docs/audit/shadow-time-stop-model-validator.md`,
    P1-1 and P1-2; its script `mv/s1_instability.py`, run on this tree).
    - **Part A** (all of today's fetches fail, or one symbol in three): look 1 keeps its 45 members and
      its z through the engine, because of the memo and the kept series. Covered by
      `test_mv_s1a_failed_fetches_leave_look_1_as_evaluated[all, every third]`. The pure function
      called with no bars and no memo still drops to the quick resolvers, as the script shows. That
      is expected: the protection is in the engine.
    - **B1 and B2** (an in-progress day-28 bar stamped 16:00, then restamped 13:30): the entry waits
      on both days, then is graded at day 28's close. There is no flip.
    - **B3** (a session row plus a separate live row for the same day): the live row is the newest
      and is dropped. The session row is then the newest left, so nothing makes it final, and no second
      dedup rule is needed.
    - **Open owner question, not built:** the validator recommends a persisted write-once ledger of
      evaluated looks. It would make "evaluated once" hold across restarts, but needs an ADR 0002 §7
      amendment. See note 6 and TODO.
21. **Wording** (model-validator P2-4). `SH_LOOK_NOT_CROSSED` plain now reads "no link strong enough to
    cross the line yet", and `SH_LOOK_CROSSED_UP`/`_DOWN` add "on average". `SH_CAVEAT_CROSSED` keeps
    the domain review's "can cross by chance even when there is no link". `SH_FINAL_NONE` is
    unchanged: ADR 0002 §3 fixes that sentence, so it is the owner's call.
22. **End-to-end null** (model-validator P3-1). Slow tests now run whole synthetic books through
    `shadow_time_stop` itself: Positions marked at 4 polls a day, with stalled days, overnight gaps,
    weekends and session-start stamps. It is a stdlib port of `mv/s7_end2end.py`, in 8 chunks of 500
    books, about 7 s each.
    - Measured: **6.095%** over 40,000 books (seeds 9000–9039, SE 0.12 pt), with every look evaluated.
      The test holds the chunks to that value ± 3 SE.
    - Naive (homoscedastic) OLS SE survives V-12, as the validator found. It is killed by
      `test_the_gate_is_the_hc3_slope_of_the_evidence_script`, which I planted and confirmed in fix
      loop 1.
23. **Not done: grading barrier-before-T entries from the cut** (model-validator P3-5). The cut is a
    bar's stamp, so these entries would then need bars. That contradicts ADR §4 rule 1 ("no price is
    needed when closed_at ≤ t_T"). It would also expose already-final outcomes to `wait_price` and
    `no_price`, which is the selection the validator's P2-2 warns about. It affects only the running
    line, which is labelled "not a test", for the 1–7 days an open entry waits for its final bar.
    Looks are unaffected.
24. **QA and code review P2-3.**
    - The 20,000-book precision run is split into 10 chunk tests of a few seconds each; the 59 s
      single test sat against the 60 s hang guard.
    - Its bar is tightened to the measured value ± 3 SE, 5.7–6.7% (QA P1-1), so a regression either
      way shows. The spec's 2,000-book test keeps 5% ± 1.5 pt.
    - New tests kill QA's surviving mutants M11–M14, C03, C06, U01, U04, U05, U08 and U09. None was
      equivalent, and none showed a spec rule to be wrong.
    - U-2 now also covers an existing grade with a verdict (25 graded).
25. **Fix loop 2, the rest** (code review r2 P3s, QA r2).
    - A memo entry is deep-copied when it is stored and when it is handed back. Its `booked` field
      is refreshed from the position, so `ic_closed` and `n_closed_same` read the book as it is now.
    - `_take_the_book` clears the memo and the bar cache.
    - `_shadow_pass` documents that it runs only under `_rescan_lock`, which serialises it. It does
      not assert this, because tests call it directly.
    - `SH_ERROR` shows the reason through `llm._clean(…, 80)`, as the untrusted-text sweep does.
    - The two slow mean tests skip, with a reason, unless all their chunks ran in the session. Run
      alone, they used to recompute every chunk and hit the 60 s hang guard (QA r2 P2-A).
    - New tests cover:
      - a malformed bar in the middle of a series (QA r2 N17);
      - the guard at exactly its bound (N14);
      - a negative payload timestamp reading n/a (N20);
      - a full listing of the data directory, with every file's size and mtime, being unchanged by
        a pass (P3-4).
26. **The entry-date window** (domain r2 P2-2; owner decision 2026-10-12: ship it in this branch).
    - `SH_ROW_WINDOW` is the first row on both pages, in both wordings. Fix loop 3 (domain r3 N-6)
      makes it name what it covers: "the {n} with a result opened {first} to {last}" (expert "{n}
      graded: opened …") once any entry is graded, and `SH_ROW_WINDOW_NONE`, "entries opened {first}
      to {last} (none has a result yet)" (expert "… (none graded yet)"), before that. Fix loop 4
      (code review r4 P3-B): when some of those entries have no readable date, the row adds
      `SH_ROW_WINDOW_UNDATED`, "({k} with no readable date)" (expert "({k} undated)"), so the
      period is not read as covering them.
    - The UI computes it from the readout's `entries[*].opened_at`, so a follower shows the holder's
      period. It counts the graded protocol entries when there are any, and otherwise every protocol
      entry entered. It is hidden when there are no entries.
    - Dates go through `_sh_date` (with the year when it differs from now) and the payload clamp. A
      bad value reads n/a and never raises.

### Known limits *(tech-writer, 2026-10-12, from the review reports; updated 2026-10-13)*
What ships with this build and is not fixed in it. Limits 1 and 2 and every owner question have a
backlog entry in `TODO.md`. *2026-10-13:* owner questions 1 and 2 are answered by ADR 0002
Amendment 1 and built in [`shadow-ledger.md`](shadow-ledger.md), which also removes limit 2; that
spec has its own Known limits.

**Limits, recorded, no code change planned:**
1. **A crypto bar restamped at exactly 00:00:00 UTC** (QA r4 P3-4,
   `docs/audit/shadow-time-stop-qa-engineer-r4.md` §4). On a 24-hour market a session's end is the
   next session's start, so a finished bar restamped at its end lands on the session pattern
   (Build note 16). If the newest finished crypto row carries exactly 00:00:00 UTC and the next row
   is missing (provider lag around midnight), that stamp is taken as the cut a day late. A close the
   book booked inside that day then keeps its booked outcome, and the memo freezes it. It needs an
   exact-second stamp: with 23:59:59, QA's property harness found no failure in 2,000 books.
2. **The grace margin under other stamp conventions** (code review r4 P3-A,
   `docs/audit/shadow-time-stop-code-reviewer-r4.md`). With last-trade or fetch-time stamps, waits
   reach 5.7 days (US holiday) and 6.73 days (^N225 in Golden Week), leaving 1.3 and 0.27 days before
   the 7-day grace (Build note 16). An entry that passes the limit counts as `no_price`, which a look
   treats as final but the memo does not keep. TESTPLAN 11.23 settles which convention Yahoo uses.
   *Resolved by the shadow ledger (2026-10-13, not yet released):* the grace is now 28 days after
   t_T plus tries on 3 distinct UTC days from t_T + 7 days (`calibration.py`
   `SHADOW_PRICE_GRACE_DAYS`, `SHADOW_PRICE_TRIES`, `SHADOW_TRY_AFTER_DAYS`), far beyond the
   6.73-day worst wait.
3. **One wrong but plausible close mid-series** still grades a gap exit; it cannot be told from a
   real move (Build note 19).

**Open owner questions, not built** (each needs an owner decision; some need an ADR 0002 change):
1. ~~**A persisted, write-once look ledger**~~ (model-validator P1-1 option b,
   `docs/audit/shadow-time-stop-model-validator.md`). Without it, "each look is evaluated once" holds
   within one process only; a restart decides again from fresh closes (Build notes 6 and 20). Needs
   an ADR 0002 §7 amendment. **Answered 2026-10-12** (owner, G1): ADR 0002 Amendment 1 adds a
   write-once ledger, `shadow_ledger.json`, anchored in `portfolio.json`; a look is shown as a result
   only once recorded. Built (spec [`shadow-ledger.md`](shadow-ledger.md)), not yet released.
2. ~~**`no_price` selects slow resolvers**~~ (model-validator P2-2). Only entries not settled before T
   can lack a price, and delisting is related to the outcome. Options: hold a look with any
   `no_price` member unevaluated, or show a sensitivity bound (excluded members at R = −1 and at
   +1.5). **Answered 2026-10-12** (owner, G2 (a)): both, in order. A look is held for up to 28 days
   plus 3 tried days; what is still left out (`no_price` or `left`) is filled in at each member's own
   barrier R, and a crossing counts only when every fill crosses on the same side. Built (spec
   [`shadow-ledger.md`](shadow-ledger.md)), not yet released.
3. **The `SH_FINAL_NONE` wording** (model-validator P2-4; domain-finance P3-3,
   `docs/audit/shadow-time-stop-domain-finance-r2.md` and `-r3.md`). ADR 0002 §3 fixes the sentence
   "no evidence that the score ranks 4-week results, at the planned size". The validator finds it
   overstates a negative and suggests "not enough evidence … At the planned size the test could
   reliably find only a link of about 0.2 or more"; the domain review notes "planned size" can read
   as position size and suggests "… with the 201 entries planned". Domain r3 asks for the owner's
   call before Release.
4. **Rule 1 before rule 2 is not a stopping rule** (model-validator P3-4). A missed stop-crossing
   daily close is overridden if the book later books a TARGET before the cut, and kept if not. Tiny
   bias; a fix changes ADR 0002 §4.
5. **Late fills** (model-validator P3-6). A pending order keeps its acceptance `opened_at`, so a late
   fill could join an evaluated cohort. Latent: the internal paper broker fills at once.
6. **ADR 0002 §3's HC3 figure** (model-validator P3-7). "HC3 slope 2.8–3.3%" at n = 400 reads about
   4.6% at 10,000 books, and the rank-IC bias is stronger than stated (7.7%). The ADR is the owner's
   to amend.

Also deferred, in `TODO.md`: security P3-1, P3-2 and P3-4
(`docs/audit/shadow-time-stop-security-engineer.md`), and domain r2 P3-5 to P3-7.

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
