# Spec: a write-once look ledger, and slow resolvers left without a price

- Status: **approved** by the owner 2026-10-12 (G1 yes, G2 (a), G3 manual). Define and Architect, 2026-10-12. Revised after the gate reviews:
  [`shadow-ledger-model-validator.md`](../audit/shadow-ledger-model-validator.md) and
  [`shadow-ledger-domain-finance.md`](../audit/shadow-ledger-domain-finance.md). Every P1 and P2 from
  them is taken in below; the one trade-off left is owner question G2.
- Parent: [`shadow-time-stop.md`](shadow-time-stop.md), Known limits, open owner questions 1 and 2
- Decision record: [ADR 0002, Amendment 1](../adr/0002-shadow-time-stop-grade.md#amendment-1-2026-10-12-accepted)
- Evidence: [`shadow-time-stop-model-validator.md`](../audit/shadow-time-stop-model-validator.md)
  P1-1 (option b) and P2-2; [`shadow-time-stop-sre-release.md`](../audit/shadow-time-stop-sre-release.md),
  owner question 2
- Deadline: the oldest protocol entry reaches T on **2026-10-20**. Look 1 (45 entries) is expected
  about 2026-11-06. Both changes must be live before look 1 can be evaluated, and should be live
  before 10-20, so that every decided outcome is recorded from the first one on.

## Problem
ADR 0002 promises two things that v2.260 does not deliver.

1. **"Each look is evaluated once."** It holds only within one process. The decided-outcome memo
   (Build note 6) is in memory, so the agent decides every outcome again after each restart, from
   whatever closes Yahoo returns that day. The agent restarts on every install. An outage, a split
   adjustment or a restamped bar at that moment can move an outcome. If that happens after a look
   has been shown, the look's z changes after it was published. On synthetic books, one failed fetch
   moved look 1 from z −0.36 to −0.98 (validator P1-1).
2. **`no_price` exclusions are selected by outcome speed** (P2-2). Only an entry the book did not
   settle before T needs a price, so only slow resolvers can be left out for want of one. Delisting,
   the likeliest permanent cause, is itself related to the outcome. Today a look goes ahead on the
   rest after a 7-day grace. That grace has as little as 0.27 days of margin under unconfirmed stamp
   conventions (Known limit 2). A ledger would make such a transient exclusion permanent, so (2) has
   to be fixed alongside (1).

## User and goal
The owner, reading the shadow grade at each of its three looks. The goal is a look result that
never changes once shown and does not rest on quietly excluded slow resolvers.

**Success measure** (each shown by a test on synthetic books with a scratch `SONAR_DATA`):
- S1. After a look is first evaluated and recorded, the holder is killed and restarted, with every
  fetch failing or with every old close rescaled 2:1. It shows the same look: the same members, z,
  crossing and recorded date.
- S2. A decided outcome survives a restart in the same way, before any look is due.
- S3. A recorded look or outcome is never rewritten. A later check that disagrees is shown as a
  flagged mismatch, and the recorded value is kept.
- S4. A look is shown as a result only once it is recorded. While the ledger cannot be read, written
  or found, no crossing and no "the test ends here" is shown.
- S5. A deleted or missing ledger is an error, never a fresh start.
- S6. A look with a member waiting for a price is not evaluated until that member is graded or both
  limits have passed: 28 days since its t_T, and fetches that could not decide it on at least 3
  distinct UTC days after t_T + 7 days.
- S7. A look evaluated with excluded members carries the z of the extreme fills, and counts as
  crossed only when every extreme fill also crosses on the same side.
- S8. Tests never touch the live data directory. No real time-stop outcome is printed or inspected
  during the work (pre-registration).

## Scope
- A ledger file, `shadow_ledger.json`, in the data directory, written by the holder only, and a
  marker in `portfolio.json` that says a ledger exists.
- Decided outcomes and evaluated looks, each written once and never rewritten. A small mutable
  section counts the failed price attempts.
- A longer, attempt-counted grace before `no_price` becomes final, and the extreme-fill check for any
  look evaluated with exclusions.
- A correction policy (errata), fixed now.
- The UI lines for "recorded", the extreme fills, the held look, a mismatch, a ledger error and an
  erratum.

## Non-goals
- No change to T, the looks (45 / 101 / 201), the gate statistic or the boundary (2.315).
- No change to the live exits, `report()`, `GRADED`, `Z_CLAIM` or row P(profit).
- `SH_FINAL_NONE` wording (open question 3), rule order (4), late fills (5) and the ADR's HC3
  figure (6) stay open and separate.
- No ledger for the closed-only grade.
- No fresh re-derivation of recorded outcomes from new closes. The check covers membership and
  constants only (validator P2-2).
- No in-app tool to write an erratum. Errata are added to the file by a person, under a written
  amendment.

## Recommendation on question 2: option (a), held with a limit, then (b) for what is left
The validator offered two options: (a) hold a look while any member has no price, or (b) show a
sensitivity bound. **Recommended: (a) with a fixed limit, then (b).** The validator agrees (its
report, Q2).

- **(a) removes the selection; (b) only measures it.** Most missing prices are transient: a failed
  fetch, a provider lag, a holiday stamp. Under (a) the member is graded once its closes arrive, so
  the look rests on all its members and nothing is selected. Under (b) the look is evaluated without
  that member, and the ledger then makes the exclusion permanent.
- **(a) alone cannot finish.** A delisted symbol never gets a price, so the cohort would never be
  final and the design could never close. The hold therefore needs a limit fixed in advance. After
  it, the member is a final exclusion, and (b) shows what it could have changed.
- **The limit is the grace.** `wait_price` already holds a look. The grace grows from 7 days to 28
  days after t_T (one more holding period), **and** the entry also needs fetches that could not
  decide it on at least 3 distinct UTC days after t_T + 7 days. The count is kept in the ledger, so a
  holder that was off for weeks cannot finalise an entry on one failed fetch after restarting
  (validator P2-5). This also removes Known limit 2: the worst stamp-convention wait measured is 6.73
  days.
- **Cost:** a look can be later, but only when a member has no price. Look 1 could slip from about
  11-06 to about 12-04 in the worst case.

### The extreme fills (b)
- **Each excluded member's R is bounded by its own barriers.** A member's R lies between its R at the
  stop, d·(stop − entry)/risk, and its R at the target, d·(target − entry)/risk. Both are known at
  fill. They equal −1 and +R:R only when the fill was the planned entry (domain P2-2, validator P3-1).
  A time exit lies between them, because the gap check catches any close beyond a barrier.
- **Enumerated, not guessed.** For k ≤ 12 excluded members, z is computed at all 2^k assignments of
  each member to its top or bottom value (at most 4,096 HC3 fits, once per look). For k > 12, only the
  two assignments that are exactly the slope's extremes are used: the high scorers at the top and the
  low scorers at the bottom, then the reverse, split at the mean confidence of all N members. On
  12,000 synthetic cohorts these were never more than 0.113 z from the full enumeration, and never
  gave a different decision (validator Q1b).
- **It is not a bound on z.** Interior values can lie up to 0.85 z beyond the far end. The decisive
  end is always at a vertex (validator Q1a), which is what the crossing rule needs. The UI never says
  "from … to".
- **Which exclusions:** `no_price` and `left`, both selected by outcome. `no_risk` has no R and is
  not selected by outcome, so it stays out (validator P2-4).
- **The robust rule:** a crossing counts only when z and every extreme fill are beyond the boundary
  on the same side. With no exclusions nothing changes.
- **The rule costs power, and the ADR says so** (validator P2-1). On synthetic books with about 3
  exclusions per 201, power at a correlation of 0.2 falls from 0.70 to 0.63 and the size from 5.5% to
  3.8%. With about 7 exclusions, power falls to 0.49. The hold above is what keeps exclusions rare.
  Owner question G2 offers the alternative.

### `no_risk`
A member whose signed stop distance d·(entry − stop) is zero or negative becomes `no_risk`, a final
exclusion decided at fill. Such a fill sits at or beyond its stop: R is undefined, or the barriers
are inverted. Today such entries are filed under `no_price`. It is latent: the internal broker fills
at the plan entry, and the book has none (not verified against the live book, by the pre-registration
rule).

### Correction policy, fixed now (validator P2-6)
A recorded look stays the design's result. If a recorded outcome is later found wrong (a bad tick, a
restated close), a person adds an **erratum** to the ledger under a written ADR note: the position id,
the reason, the corrected R and the date. The readout shows it beside the look: "Erratum {date}: one
result in this look was later found wrong ({reason}). The recorded result is kept, as fixed in
advance." An erratum never changes `crossed` or `design_closed`. Choosing the rule only after a wrong
grade is seen would be a forking path.

## Design *(orchestrator, revised for domain-finance; for the ux-designer's review at Build)*
The block keeps its layout. Plain wording comes first, expert second. Every new line sits under the
existing `SH_NOTE` (paper, before costs).

- **Record line** (always, once a ledger exists): "Record kept since {date}." / "Ledger since
  {date}". This makes a restarted record visible (domain P2-6).
- **Recorded look:** the date goes first. "Look {k} of 3, recorded {date}, first {N} entries ({used}
  with a result): …" / "Look {k}/3 (rec. {date}): …".
- **Extreme fills** (under a look with exclusions): "The {k} left out have no usable result. Filled in
  at the extremes for the score (each at its target or its stop), z would be {lo} at the lowest and
  {hi} at the highest. These are extreme cases, not estimates." / "{k} excl.: extreme z {lo} / {hi}
  (not a bound)".
- **Past the line but not robust** (`SH_LOOK_NOT_ROBUST`, new key): "Look {k} of 3, recorded {date},
  first {N} entries ({used} with a result): z = {z} is past the line, but not in every extreme case
  for the {k} left out. This look does not count as crossed; the test goes on." followed by
  `SH_CAVEAT_CROSSED`. Expert: "Look {k}/3: |z| ≥ 2.315, extremes not; not crossed ({k} excl.)".
- **Held for a price:** `SH_LOOK_WAITING_PRICE` gains: "… waits for them until {date}; any still
  without a price then are left out and the look goes ahead." / "… until {date}, then excluded".
  {date} is the latest t_T + 28 days among the waiting members. The look may come later than that if
  the price attempts are not yet used up or the agent is not running.
- **Worked out but not recorded** (a write failed, or the ledger is missing or unreadable): the look
  line reads "Look {k} of 3: worked out but not recorded yet, so it is not shown as a result." / "Look
  {k}/3: not recorded; no result shown". No z, no crossing and no "the test ends here".
- **Mismatch, members or z:** "Worked out again today, look {k} comes out differently ({why}). As
  fixed in advance, the result recorded on {date} is kept. Either one may rest on a data error." /
  "look {k}: check differs ({why}); recorded {date} kept by design". {why}, plain: "which entries it
  counts", "the z figure". Expert: "members", "z".
- **Mismatch, constants:** "The test's fixed settings have changed since look {k} was recorded on
  {date}. The recorded result belongs to the old settings, and the new ones need their own record." /
  "look {k}: constants changed since {date}; new settings need a new record".
- **Ledger error:**
  - read: "The record of results could not be read ({reason}), so it is left untouched for a person
    to check. Nothing new is recorded, and no look is shown as a result." / "ledger unreadable
    ({reason}); not recording".
  - missing: "The record of results is missing, though this book had one since {date}. It is not
    started again; restore it from the daily backup." / "ledger missing (since {date}); restore from
    backup".
  - write: "The latest results could not be recorded ({reason}); the next pass tries again." /
    "ledger write failed ({reason}); retrying".
  - {reason} is the exception's class name, through `llm._clean(…, 80)`, as in `SH_ERROR`.
- **Erratum:** as in the correction policy above. Expert: "erratum {date}: {reason}; recorded kept".
- **Left out:** the left-out row gains "{r} whose stop was at or past the fill price (no R can be
  worked out)" / "{r} risk ≤ 0".

## Architecture *(orchestrator as architect)*
ADR 0002 Amendment 1 holds the decision. This section gives the build shape.

### The file
`<SONAR_DATA>/shadow_ledger.json`, one JSON object:

```json
{"schema": 1, "ledger_id": "<uuid4>", "created_at": 1760000000.0, "created_by": "v2.261",
 "constants": {"rules": 1, "t_horizons": 4, "t_days": {"intraday": 5.6, "week": 28.0, "...": 0},
               "looks": [45, 101, 201], "boundary": 2.315, "grace_days": 28,
               "grace_tries": 3, "split_guard": 4.5, "vertex_k_max": 12},
 "entries": {"<position id>": {
     "state": "time", "source": "bar", "r": 0.42, "exit": 101.3,
     "entry": 100.0, "stop": 95.0, "target": 107.5, "r_stop": -1.0, "r_target": 1.5,
     "direction": "LONG", "symbol": "AAPL", "confidence": 0.71, "rr": 1.5,
     "opened_at": 1758500000.0, "closed_at": null, "t_due": 1760919200.0, "t_days": 28.0,
     "t_bar": 1760880600.0, "t_cut": 1760967000.0, "gap": false, "ref": [0.374, 0.574],
     "decided_at": 1761050000.0, "build": "v2.261"}},
 "looks": {"1": {"k": 1, "n": 45, "evaluated_at": 1762400000.0, "build": "v2.261",
                 "z": -0.36, "z_lo": null, "z_hi": null, "method": null, "crossed": false,
                 "design_closed": false, "used": 45, "n_excluded": 0,
                 "members": [{"id": "<id>", "state": "time", "r": 0.42, "confidence": 0.71,
                              "r_stop": -1.0, "r_target": 1.5}]}},
 "price_tries": {"<position id>": ["2026-10-28", "2026-10-29"]},
 "errata": []}
```

- `source` is `book` (rule 1), `gap` (rule 2), `bar` (rule 3), `hand` (left) or `fill` (no_risk).
- `price_tries` is the only mutable section: the distinct UTC days on which, after t_T + 7 days, the
  pass had fetched closes for the entry's symbol and still could not decide it. It is dropped for an
  entry once decided. `errata` is appended to by hand only; the code reads it and never writes it.
- **A final `no_price` member is not written as an entry.** It is final only relative to a look, so
  it appears in that look's members. It may still be graded later and count in a later look; that is
  specified and tested (validator P3-5).

### Write-once, enforced in one pure function
`calibration.ledger_merge(old, readout, now, build)` returns `(new, added)`. It adds an entry only
when its id is absent and its state is decided (graded, `left` or `no_risk`). It adds a look only
when its key is absent and the look is evaluated. It never changes or removes an existing entry,
look, constant or erratum; only `price_tries` changes. A property test pins this.

### Read side
- `ledger_parse(raw)` type-checks every field and returns `(ledger, error)`. A wrong type anywhere is
  a read error for the whole file, never a partial read.
- `shadow_time_stop(open, closed, bars, now, decided, ledger)`: the ledger's entries join `decided`
  (the in-memory memo stays, for speed and for a ledger that cannot be written). `price_tries`
  feeds the grace.
- `shadow_looks(entries, recorded)` returns a recorded look as recorded and adds `recorded_at`. It
  works out `design_closed` from recorded crossings first. A look that is evaluated but not recorded
  carries `recorded: false`, and the UI shows no result for it (S4).
- **Membership and constants check** (not a re-grade; validator P2-2): for each recorded look, the
  members it would have today and the file's constants are compared with the record. A z difference
  can appear only when a recorded `no_price` member has since been graded. Differences are listed in
  `mismatches`.

### Engine
- `_shadow_pass` loads the ledger once per holder tenure: on the first pass, and again after
  `_take_the_book`. It computes, merges and, when anything was added, writes with
  `paths.write_atomically`. Only then does it publish. Before the first write of a day it takes
  `paths.daily_backup` of the file, as for `portfolio.json`, with the off-site copy.
- **The marker** (validator P1-1). When the holder creates the ledger, it first records `ledger_id`
  and `created_at` in `portfolio.json` (a new top-level `shadow_ledger` key, saved under
  `book.lock`). Then it writes the file. If the marker is present and the file is missing, the pass
  sets `ledger_error: "missing"` and never starts a new file. Restoring from a backup clears it. A
  file whose `ledger_id` differs from the marker is a read error. Moving the file aside therefore
  leaves a trace (domain P2-6). Starting a new record for a reset book means removing the marker as
  well, which is a deliberate act. *(Fix loop 2: the deliberate act is now the retire step in the
  Failure modes table; it keeps the old record and its backups. See Build note 17.)*
- A follower and a read-only engine never read or write the file or the marker. The engine lock
  makes the holder the only writer.

### Failure modes
| Case | Behaviour |
|---|---|
| No marker, no file | Start a ledger (marker first, then file). |
| Marker, no file | `ledger_error: "missing"` ("this book had one since …"); nothing written; no look shown as a result. Restore the newest backup copy. Retiring is not offered and not honoured: the book was not reset (G3; fix loop 3). |
| Sidecar only, no file (fix loop 1) | `"missing"`, worded "this folder had one since …": the sidecar belongs to the data folder, not the book. Same two ways out. |
| Backups only, no file (fix loop 1) | `"missing"`, worded "backups of it exist". A backup is attributed by the `ledger_id` in its own JSON; one that cannot be read or names no id still anchors. |
| File behind the anchors (fix loop 1, fix loop 2) | Fewer recorded looks than the marker or sidecar counts: `"read"` (`LedgerBehindError`). Entries are not counted: lost ones are decided again from the closes then available, and are not part of any recorded look (each look keeps its own members). A copy is made, here and off-site, right after each write that records a look, so the newest copy holds every recorded look unless that copy failed (Known limit 3). |
| File unreadable, wrong schema or wrong id | `ledger_error: "read"`; the file is never overwritten, moved or repaired; no look shown as a result. |
| Another book's file (a reset, G3) | `"read"` (`LedgerIdError`). To start a new record, **retire** the old one: move `shadow_ledger.json` to `shadow_ledger.retired.<its ledger_id>.json` in the same folder. Its id then anchors nothing: the sidecar and every backup, here or off-site, that carries it no longer block a new record, and nothing is deleted. The new record's line always discloses the retired records (fix loop 3). |
| Retired (fix loops 2, 3) | A `shadow_ledger.retired.<id>.json` retires `<id>` only if its own `ledger_id` is `<id>`, **and only while `portfolio.json`'s marker is absent or names another id** (G3: retiring is for a reset book). While the marker names it, the retirement is not honoured: with no file the record is `"missing"` (reason `marker`), the 10-minute rule does not remake it, and no new record starts. Without such a marker, a `shadow_ledger.json` whose id is retired (a copy left in place of a moved one) is `"read"` (`LedgerRetiredError`), never used. |
| Write fails | `ledger_error: "write"`; the memo keeps outcomes stable in this process; looks not yet recorded show no result; the next pass retries. |
| Crash between marker and file | The next pass sees "marker, no file" and reports missing. To avoid this, the marker write and the first file write happen in one pass, and a marker whose `created_at` is under 10 minutes old with no file is retried once, not reported. |
| Crash between file write and publish | Harmless: the record is on disk, and the next pass shows it. |
| Crash mid-write | `write_atomically` leaves the old file. |

- **Size:** about 0.3–0.36 MB a year at 2.5 entries a day (validator P3-4). It is rewritten whole
  only when something is added, at most a few times a day.
- **Security surface:** a new file write under `SONAR_DATA` and a new key in `portfolio.json`
  (Secure phase required). The file is read as data only, every field type-checked; no text from it
  reaches the screen except through the existing clamps and `llm._clean`.

### Pure function changes in short
- The grace: 7 → 28 days, plus 3 attempt days (both pinned by a test).
- `_shadow_entry`: a signed distance ≤ 0 gives `no_risk` at once; `SHADOW_EXCLUDED` gains it.
  `_shadow_from_bars` also returns the T-bar stamp and the cut, for the record.
- `shadow_looks`: the extreme fills, the robust rule, and recorded looks honoured.
- New and pure: `ledger_parse`, `ledger_merge`, `ledger_check`, `extreme_z`.

## Owner questions at the gate
- **G1.** Approve Amendment 1 as written: the ledger, the marker, errata, a grace of 28 days plus 3
  attempt days, and `no_risk`? (Recommended.)
- **G2. The robust rule.** (a) A crossing counts only when every extreme fill crosses too
  (recommended). It is conservative, it removes a crossing that rests on the excluded members, and
  the hold keeps its power cost small. (b) Gate on the observed z as today, and show the extreme
  fills beside it as information only. This keeps the design's power with exclusions, but a crossing
  could rest on the slow resolvers that the exclusions select.
- **G3.** Paper-book reset: keep it manual (remove the marker and move the file aside, both on
  purpose)? (Recommended: resets are rare and deliberate.)

## Risks
- **The ledger freezes mistakes.** That is the point of pre-registration. The errata policy above is
  the only correction, and it never changes a result.
- **It is not tamper-evident.** A person can edit the file. The marker, the daily and off-site
  backups and the "Record kept since" line are the only cross-checks. The validator's optional
  SHA-256 of each look in CHANGELOG is left to the Document phase of each look.
- **Before 2026-10-20 no time outcome exists**, so the ledger starts empty and nothing is migrated.
  If it ships later, outcomes decided since 10-20 are recorded at the first pass after install, from
  that day's closes.
- **Pre-registration, exactly.** No shadow look and no time-exit outcome has been computed. Book
  outcomes of entries closed before T, including hand closes, are visible in the paper book and were
  not consulted for this amendment. The owner alone can confirm the last clause (domain P3-1).

## Verification plan *(for the qa-engineer)*
| # | Test | Mutant it kills |
|---|---|---|
| L-1 | Look evaluated and recorded; a new engine on the same scratch dir, with all fetches failing, shows the same look and recorded date (S1). | ledger not read |
| L-2 | Same, with every close before the cut rescaled 2:1. | recomputing over the record |
| L-3 | A decided entry survives a restart with no bars (S2). | entries not persisted |
| L-4 | `ledger_merge` never changes an existing entry, look, constant or erratum: a property test over random old/new pairs (S3). | overwrite on merge |
| L-5 | A changed membership or constant is listed as a mismatch, and the recorded z is shown. | mismatch replaces the record |
| L-6 | Unreadable file, wrong schema or wrong id: never written (bytes and mtime unchanged), `ledger_error: "read"`, no look shown as a result (S4). | overwrite of a bad file; result shown |
| L-7 | A write failure leaves the readout up with `ledger_error: "write"` and no unrecorded result; the next pass writes. | publish blocked; unrecorded result shown |
| L-8 | Follower and read-only engines never create or touch the file or the marker. | a follower writes |
| L-9 | A member in `wait_price` holds the look until it is graded, or until 28 days and 3 attempt days have both passed (S6). Constants pinned. | grace left at 7; attempts ignored |
| L-10 | A holder off for 4 weeks, then one failed fetch: the member is still waiting. | calendar-only grace |
| L-11 | Extreme fills: a hand-built cohort with known vertex extremes; the crossing counts only when every vertex crosses; per-member barrier R with a fill away from the plan entry (S7). | corners at −1/+rr; one corner only |
| L-12 | With no exclusions, the extremes equal z and the looks equal v2.260's. | the rule changes the no-exclusion case |
| L-13 | Signed distance ≤ 0 is `no_risk` at once, final, outside the extremes; a LONG filled below its stop is `no_risk`. | `abs()` risk; old filing |
| L-14 | V-12 and the end-to-end null still hold their bars with no exclusions; a slow V-12 variant with about 3 seeded exclusions per 201 pins size ≤ the no-exclusion size and power about 0.63 ± 3 SE (validator P2-1). | the robust rule dropped or inverted |
| L-15 | Marker present, file deleted, restart: `ledger_error: "missing"`, no new file, no new records (S5). | silent fresh start |
| L-16 | An erratum in the file is shown and never changes `crossed` or `design_closed`. | erratum rewrites the result |
| L-17 | A `no_price` member final in look 1 is graded later and counts in look 2; look 1 is unchanged. | cross-look state leak |
| L-18 | The test fixture refuses a `SONAR_DATA` under `~/Library/Application Support/SONAR` (S8). | — |

## Build notes (shadow ledger)
*(engineer, 2026-10-12; choices the spec left open. Report: [`shadow-ledger-engineer.md`](../audit/shadow-ledger-engineer.md).)*

1. **Expert strings say "record", not "ledger".** "ledger" contains "edge", which U-1
   (`tests/test_shadow_ui.py`, `EDGE_ALLOWED`) allows only in fixed phrases. The test was not
   loosened: "Record since {date}", "record unreadable ({reason}); not recording", "record missing
   (since {date}); restore from backup", "record write failed ({reason}); retrying".
2. **A look is a result only when its payload says `recorded: true`** and the ledger is not in a
   `read` or `missing` state. A payload without the key (a v2.260 holder followed by this window)
   shows "worked out but not recorded yet". The window checks this itself, whatever the holder
   sends.
3. **The split for k > 12** is at the mean confidence of the regression's members (the graded and
   the filled-in ones), which is what makes the two fills the slope's exact extremes. `no_risk`
   members are not in the regression and not in the mean.
4. **Constants** stored: the spec's set plus `try_after_days: 7`; `rules` starts at 1. Any
   difference is a `constants` mismatch for every recorded look.
5. **What counts as a try.** A UTC day on which this holder asked for the entry's symbol (a request
   that failed, or one whose closes still could not decide it), on or after the UTC day of
   t_T + 7 days. Today's request counts in the same pass, so the third day finalises at once.
   Stored days earlier than that day are ignored. Days are only added; an entry's are dropped
   when it is decided (graded, `left`, `no_risk`), and kept while it is `no_price`, which is not
   written as an entry.
6. **A ledger that cannot be read or found is read again on each pass** (never written, moved or
   repaired), so putting the right file back clears the error without a restart. A good ledger is
   read once per holder tenure, as specified.
7. **A file with no marker** (for example a `portfolio.json` restored from before the marker) is
   taken as this book's record and the marker is written back from it. A damaged marker is a
   `read` error.
8. **The 10-minute rule.** At load, a marker under 600 s old with no file is taken for a crash
   between the two writes: the file is made with the marker's id and `created_at`, once per
   tenure. After that, a failed write is a `write` error and is retried every pass.
9. **Readout entries from the ledger** drop its `decided_at` and `build`, so an entry read from the
   ledger equals the one the memo held. `booked` is refreshed from the book, as before.
10. **Readout looks** add `n_filled`, `past_line`, `price_until`, `recorded` and `recorded_at`;
    `members` travels only on an evaluated look not yet recorded. The record keeps the spec's
    fields.
11. **Mismatch kinds.** `constants` (checked first), `members` (the first N ids in entry order
    differ), `z` (same ids, a member's state differs, and today's z differs by more than 1e-9).
12. **Errata** are `{id, reason, r, date}` with `date` as `YYYY-MM-DD`, checked like every other
    field, and shown with the looks that hold the id.
13. **Placement.** Ledger errors, mismatches and errata go in the existing gold warning label, the
    record line at the end of the note, the extremes row first in the rows of the look the
    sentence names. A recorded past look that was past the line but not robust gets its own row
    wording. A not-robust z is shown on its own side of the line. "Waits for them until" is
    added only when the due look has members waiting for a price.
14. **The file** is JSON with `indent=1` (errata are added by hand), written with
    `allow_nan=False`, refused above 64 MB on read, and stale temporary files beside it are swept
    at load. It is written when something was added or a try was counted, and, for a ledger this
    tenure has just started, at once with its anchors (fix loop 1; the first version said "when
    this tenure has not yet written it", which held only for a new ledger, code review P3-7).
    `created_by` and `build` are `version.provenance()["version"]`.
15. **Tests.** `scratch_data` (conftest) sets `SONAR_DATA` to the test's `tmp_path` after
    `refuse_live_data`. It also clears `SONAR_BACKUP_DIR`, so a scratch backup is never copied
    off-site. `isolated_state` now refuses a `tmp_path` under the live directory too. The check
    compares paths as text before resolving anything.
16. **Fix loop 1** (2026-10-13; reports `shadow-ledger-code-reviewer.md`,
    `shadow-ledger-security-engineer.md`, `shadow-ledger-domain-finance-r2.md`; orchestrator's
    decisions):
    - **Three anchors.** The marker in `portfolio.json`, a sidecar `shadow_ledger.id` beside the
      file (no older build writes or strips it), and any `shadow_ledger.json.bak.*` here or
      off-site. With any anchor and no file the record is `missing`. Marker and sidecar carry the
      id, the start and the counts of recorded looks and entries at the last write; the counts only
      grow, and a file with fewer is a `read` error (`LedgerBehindError`). The 10-minute rule
      applies only to an anchor that counts nothing. `Portfolio` keeps top-level keys it does not
      know, so a later build's key survives a save by this one.
    - **Build note 7 replaced.** With no marker in the book, a file is taken only if it is empty or
      every recorded entry and look member is a protocol position of this book; otherwise it is a
      `read` error (`LedgerIdError`), never adopted or written. The sidecar names the data
      directory's record, not the book's, so it does not lift this check. The read line says that
      after a reset the old record has to be moved aside on purpose (G3).
    - **The file can change under the holder.** Before each pass and each write, the file's inode,
      size and mtime are compared with what this tenure last read or wrote. If they differ it is
      read again: with the same id its errata are taken over (nothing else); gone, unreadable or
      another id stops the tenure's copy and nothing is written. Errata are still best added with
      the agent and the window stopped.
    - **What is written is what reads back.** `ledger_merge` checks each new entry and look with
      the reader's own checks and leaves out what fails (counted as `ledger.refused` and shown);
      the serialised text is parsed again before `write_atomically`.
    - **The empty file** is written right after the marker and the sidecar, before any fetch.
    - **No write after a stop or without the engine lock**, and no readout published then.
    - **Reading** uses `O_NOFOLLOW | O_NONBLOCK` and accepts only a regular file, read to at most
      64 MB + 1 byte. `constants` is a typed mapping (a key added or removed is a `constants`
      mismatch). Errata are capped at 1,000. A recorded look must have the size its key says, a
      crossing only past the line and, with members filled in, robust; `design_closed` is false
      and no look follows a crossing. The window shows at most 5 errata and 3 mismatches, and a
      crossing only when `crossed is True`.
    - **Wording** (domain r2): the extremes are "the lowest z found … not estimates and not
      limits"; an erratum names its look(s) and the corrected R; a blocked look says "not shown as
      a result while the record cannot be used"; a not-robust look carries its own caveat; and
      extremes that could not be worked out say so. The expert copy keeps "record" for the spec's
      "ledger" on purpose (Build note 1; domain r2 P3-4 not taken).
    - **Deferred:** an fsync before the atomic rename (security P3-6), as for every state file;
      in the backlog.
17. **Fix loop 2** (2026-10-13; reports `shadow-ledger-code-reviewer-r2.md` and
    `shadow-ledger-qa-engineer.md`; owner approved the loop):
    - **The anchors count looks only** (r2 P2-N1). Marker and sidecar carry the id, the start and
      the number of recorded looks; a file with fewer looks is `LedgerBehindError`. Entries are
      not counted: a lost entry is decided again from the closes then available, and is not part of
      any recorded look (each look keeps its own members; wording corrected in fix loop 3, code
      review r3 P3-4), and counting them made the newest daily backup "behind" on any day that
      decided one. A marker with an `entries`
      count (fix loop 1) is still read, and the count dropped. The 10-minute rule now applies to
      an anchor that counts no look.
    - **A copy after each look.** Right after a write that records a look, the file is copied to
      `shadow_ledger.json.bak.<date>.look<k>.<first 8 characters of its id>`, beside it and
      off-site (`paths.snapshot`, the daily backup's rotation and `_copy_offsite`). The name sorts
      after that day's daily backup, so "the newest copy" is the newest name, and it matches the
      anchors. The id in the name keeps a retired record's copy of the same day and look from being
      written over. The UI says "Put the newest backup copy in its place: the one with the latest
      date in its name, here or off-site", which is now true.
    - **Retiring a record** (r2 P2-N2, G3). Moving the file to
      `shadow_ledger.retired.<its ledger_id>.json` in the data folder retires that id: a marker,
      sidecar or backup naming it no longer anchors, so a reset book starts a new record and the
      old one and all its backups are kept. The retired file must hold that id itself; a backup is
      attributed by its own `ledger_id` (bounded `O_NOFOLLOW` reader, id-only parse); at most 50
      retired files are read. A live file whose id is retired is `LedgerRetiredError`. The same
      step started a new record for the same book (ADR §7: new settings need a new record) —
      **replaced in fix loop 3** (Build note 18): not while the book's marker names the record. The
      old backups then rotate as usual; the retired file is the copy kept for good.
    - **"Missing" says whose** (r2 P2-N2): the reason is `marker`, `sidecar` or `backup`; "this book
      had one since …" only for `marker`, "this folder had one since …" for the sidecar, "backups
      of it exist" otherwise. Every missing line ends with the restore and retire steps; the
      foreign line names the retire step. The file names are not spelled out on screen (they hold
      "edge", Build note 1); the README gives them.
    - **The file's own constants** (r2 P3-N1): the reader and the merge both check a look against
      the file's `boundary` and `looks` when well-typed (else today's), so a changed module constant
      is a `constants` mismatch, and a new look the file's constants do not support is refused, not
      written.
    - **An anchor save that failed after the file was read or written is retried** at the start of
      each pass (r2 P3-N2).
    - **Refused counts** (r2 P3-N3): `ledger.refused` counts results and `ledger.refused_looks`
      looks, each with singular and plural wording. The expert erratum line says "no look",
      "look 1", "looks 1 and 2".
    - **Tried days stop when no longer needed** (QA P2-1): a day is added to `price_tries` only
      while the entry waits for a price, or while fewer than 3 are recorded. Build note 5's "days
      are only added" holds; none is removed until the entry is decided.
    - **QA test gaps closed** (QA P2-2 to P3): S4 gating (Q57, Q61, Q65), a foreign record with
      entries only (Q45), "same side" (Q21; `shadow_looks` and `_check_look` already agreed), the
      grace edge (Q26), `price_until` (Q30), memo tries while writes fail (Q29), parser checks
      (Q08, Q10, Q12), an undefined vertex (Q18), anchor edges (Q37, Q38, Q43), each half of
      "behind" (Q39, Q40, adapted to looks only), change detection (Q48, Q51), blocked lines
      (Q64), and the engine test's backup date pinned to its NOW.
18. **Fix loop 3** (2026-10-13; reports `shadow-ledger-domain-finance-r3.md` and
    `shadow-ledger-code-reviewer-r3.md`; orchestrator's decisions, enforcing owner decision G3):
    - **Retiring is only for a reset book** (domain r3 P1-1). A retirement is not honoured while
      `portfolio.json`'s own marker names the retired id: the record is `"missing"` (reason
      `marker`), the 10-minute rule never remakes a retired id, and no new record starts. Only with
      no marker, or one naming another id, does a retired id stop anchoring. Without such a marker
      a live file whose id is retired is still `LedgerRetiredError`; with it, the retirement is
      ignored and the file read as before. This replaces Build note 17's "the same step starts a
      new record for the same book"; the test that pinned that now pins the refusal (a spec
      change, not a weakening).
    - **Retired records are always disclosed** (domain r3 P1-1). `ledger.retired` (how many retired
      records are in the folder, other than the one in use; present only when there is one) and
      `ledger.retired_first` (the earliest retired file's status-change time, `st_ctime`, which a
      rename or a copy sets) feed the record line: "Record kept since {date}. {n} earlier
      record(s) were retired in this folder, the first on {date0}. Their looks are not counted
      here, and this record re-tests the same kind of entries." (singular: "1 earlier record was
      retired in this folder, on {date0}. Its looks …") / "Record since {date}; {n} retired (first
      {date0})." At most 50 retired files are read (`SHADOW_RETIRED_MAX`).
    - **No retire step on the "this book" path.** `SH_LEDGER_RESTORE` names only the restore; the
      retire sentence (`SH_LEDGER_RESTORE_RETIRE`) follows only a sidecar- or backup-anchored
      "missing". The foreign line adds that the new record re-tests the same kind of entries.
    - **A copy after a record's first write** (code review r3 P3-2):
      `shadow_ledger.json.bak.<date>.created.<id8>`, here and off-site, right after a new record's
      first successful write (at open, or at the first record write if that one failed). "created"
      sorts before "look", so on a day with both, the look's copy is the last by name. The
      coordinator's suggested tag was `start`; it would sort after `look1` on the same day.
    - **Restore wording** (code review r3 P3-1, P3-2): "the last one by name, here or off-site (on a
      look's day, the one with .look in its name; after a reset, see the README)"; the README adds
      "the newest copy whose name ends in the first 8 characters of the id in `shadow_ledger.id`".
      Failure modes: "unless that copy failed".
    - **A file lost under the holder is "this book's" at once** (code review r3 P3-3): the refresh
      reports reason `marker` when the book's marker names the record.
    - **Copy** (domain r3 P3-1 to P3-3, code review r3 P3-5): refused results "could not be written
      to the record … It is not in the record, so a look that uses it cannot be fully checked
      against the record." / "not in record"; errata touching a recorded look first, then newest,
      and "{n} more errata are in the record; {m} of them touch a recorded look." / "+{n} errata ({m}
      on looks)"; an erratum with no corrected R says "it has no usable R" / "R → none"; "looks 1,
      2 and 3".
    - **Test race** (code review r3 P3-6): `test_two_processes` waits for `read_only` to clear
      rather than asserting it as soon as the lock is held.

## Known limits *(tech-writer, 2026-10-13, from the review reports and Build notes 16-17; limit 9 replaced in fix loop 3)*
What ships unfixed. Each was checked against the code at `aa3de64`; figures are simulated on synthetic
books (no real data), with the sample size given.

1. **No fsync before the rename** (security P3-6, `shadow-ledger-security-engineer.md`; backlog,
   `TODO.md` P3 security). `paths.write_atomically` (`sonar/paths.py:131-145`) writes a temporary
   file and renames it, with no flush to disk in between. After a power loss the renamed file can be
   empty. That fails safe: it is a `read` error, nothing is written, and the record is restored from
   the newest backup copy. Pre-existing for every state file.
2. **Not tamper-evident** (Risks; ADR 0002 Amendment 1). A person can edit the file. The cross-checks
   are the anchors (marker and sidecar count recorded looks, so a file with fewer is refused), the
   daily, per-look and off-site copies, and the "Record kept since" line. Nothing detects an edit
   that keeps the id and the look count. The validator's optional SHA-256 of each recorded look in
   CHANGELOG is left to the Document phase of each look; no look is recorded yet.
3. **A failed copy after a look is silent** (engineer report, fix loop 2, "Not done"). `paths.snapshot`
   (`sonar/paths.py:107-127`) returns `None` on an `OSError`, and a failed off-site copy only prints
   a line to the agent's log (`_copy_offsite`). Nothing is shown on screen. The newest copy is then
   one look behind until the next daily backup, which is taken before the first write of a day on
   which something is written.
4. **Old backups rotate out after a reset** (engineer report, fix loop 2). Retired and new records
   share the stem `shadow_ledger.json.bak.*`; rotation keeps the 7 newest names here (`BACKUP_KEEP`,
   daily and per-look copies together) and 30 off-site (`OFFSITE_KEEP`). The retired file
   `shadow_ledger.retired.<id>.json` is the copy kept for good. A reset on a day that already has a
   daily backup of the old record costs the new record that day's daily backup (the name is taken;
   `daily_backup` skips it).
5. **The robust rule costs power** (validator P2-1; ADR 0002 Amendment 1, "Cost, stated").
   Validator `q1c` (synthetic books, exclusions on slow resolvers only, independent of R; size from
   12,000 null books, power at a correlation of 0.2 from 4,000 books per row): with about 3
   exclusions per 201, size 5.48% → 3.78% and power 70.2% → 62.5% against gating on the rest; with
   about 6.7, power 67.2% → 48.8%. Against no exclusions at all the power is 72.3%. L-14
   (`tests/test_calibration.py`, slow, 2,000 books) measured 0.729 → 0.632 and 5.75% → 4.05% at
   build. The rule can only remove crossings. The 28-day hold is what keeps exclusions rare.
6. **The extreme fills are not a bound on z** (validator Q1a, Q1b). A point between the fills can
   lie beyond them: up to 0.85 z beyond the far end in validator `q1b` (12,000 synthetic cohorts,
   k = 1 to 10, n = 45 and 101). The validator's analysis (Q1, b) puts the side that decides a robust
   crossing at a fill (a vertex), so enumerating every vertex, as is done for k ≤ 12, decides it
   exactly. For k > 12 only the two
   slope-extreme fills are used; they were within 0.113 z of the full enumeration and gave no
   different decision in those 12,000 cohorts, which reached k = 10 only, so the k > 12 shortcut is
   measured below the range it is used in, not in it. The UI says "not estimates and not limits" /
   "(not a bound)" and never "from … to".
7. **The check is not a re-grade** (validator P2-2). Recorded outcomes are never derived again from
   new closes; the check compares membership and constants only. A wrong recorded outcome is found
   only by a person, and corrected only by an erratum.
8. **The retire step has been tested on scratch directories only** (engineer report, fix loop 2);
   nobody has walked through it by hand.
9. **A retirement after a reset re-tests the same kind of entries** (domain r3 P1-1, fixed in fix
   loop 3, Build note 18). Retiring is honoured only when `portfolio.json`'s marker does not name
   the record, so a book that was not reset cannot start over by retiring
   (`test_cr3_g3_retiring_without_a_reset_is_not_honoured`). After a reset it can, and the new
   record re-tests the same kind of entries; the record line then always says how many records were
   retired in the folder and when the first was (`test_cr3_domain_p1_1_…`). What is left: that date
   is the retired file's status-change time, which a later metadata change (a restore from a
   backup, a permission change) moves; and someone who also deletes the marker by hand, or the
   retired file, defeats both the refusal and the disclosure (Known limit 2: not tamper-evident).
