# Changelog

Versions follow `VERSIONING.md`: `v<MAJOR>.<BUILD>`, where BUILD is the commit
count. Every commit is therefore a version, so this file records the **builds
that were installed** and what changed in them — not every number that existed.
Newest first.

Builds before v2.103 predate the version number. Nothing has been
back-numbered: assigning versions to releases that never had them would make
this a worse record than the git log it was written from. `TODO.md`'s `## v2`
section lists what the v2 arc shipped.

## v2.340 — 2026-10-13

**Backtest verdicts: a check against random directions** (branch `sign-randomisation-verdicts`;
`docs/specs/sign-randomisation-verdicts.md`, `docs/adr/0003-sign-randomisation-gate.md`). Before
costs, from one replay of past prices, as before.

- **A verdict now needs two things.** The difference outside its error bar, as before, *and* the
  run's directions reading further from the prediction than directions swapped for the opposite one
  over whole stretches of time (a stretch is four holding periods, every asset class together). The
  p-value in the direction of Δ must be under 0.05. The check can only take a verdict away.
- **A third, grey reading.** Outside the bar without passing the check reads "not told apart from
  chance", never "within". Inside the bar now reads "not shown to differ from the prediction, which is
  not the same as no difference" (was "no edge detected. This is what no edge is supposed to look
  like.").
- **The rate every verdict quotes.** Directions picked at random and held for up to eight holding
  periods "still got a verdict either way about 1 run in 10, and about 1 in 5 at some settings"; the
  rate is per run, and nearby settings can disagree. Figure: 9.11% [7.6–10.9] of 1,152 judged runs on
  a held-out set (the watchlist's daily bars, 2006-01-01 to 2016-09-30; manifest `404f5a77…`), 52.9%
  withheld; model validator r7, 2026-10-12. Its 7.5% target was **not met**; the owner chose to
  disclose it rather than redesign the stretches.
- **What the check cannot see, said on every reading outside the bar:** "A direction fixed per
  instrument, such as always long, can also land outside the bar, because each instrument keeps its
  own trend over the years and the list holds only today's survivors; this check cannot see that."
- **New reasons for no verdict.** Under 8 separate stretches ("A shorter horizon gives more, or a
  longer range up to five years"; on a five-year run only the horizon). A sample missing some setups'
  opposite direction, entry time, horizon or timeouts. Any ten-year Lab run (the Terminal never reads
  ten years): over ten years a direction fixed per instrument lands outside the bar more often than
  the quoted rate.
- **The Terminal's backtest range.** Two years for the day and week profiles, five for the month
  (was two), so they fall in enough stretches to be judged; the quarter and year profiles show the
  numbers without a verdict. The Lab and the Terminal show the survivorship line under every result.
- **Attribution.** KEEP and INVERTED also need the component's own randomisation p to survive
  Benjamini-Hochberg across the components measured. Otherwise a component reads "not told apart
  from chance", or "not tested" where the check could not run. The check does not cover traits fixed
  per instrument, such as volatility; the Lab says so in both wordings. KEEP and INVERTED say "before
  costs".
- **DROP is uncalibrated (deferred).** It still has no error bar; the owner deferred that to the P3
  backlog (`TODO.md`).
- **Expert wording** adds "p vs random directions, in the direction of Δ: {p} ({q} stretches)", and the
  IC's randomisation p "before the correction for the {n} components measured". Plain wording gets no
  new number.
- **Tests.** The two old acceptance tests become rate tests with bounds set in advance from the
  binomial distribution, marked `rate` (they run by default; `slow` is master's opt-in
  Monte-Carlo marker), each under pytest's 60 s per-test cap. The headline ones are a
  gate against the code before the check, not proof of 5%. **The attribution suite test is a
  regression guard**: the attribution size gate is the real-bar measurement (measure 3), not yet run at
  full size.
- **Suite budget 300 s → 600 s** (`run-tests.sh`), for the rate tests on a loaded machine; the 60 s
  per-test cap is unchanged. **Coverage is measured in two appended passes** under the watchdog, the
  rate one with the per-test cap lifted and a 1200 s budget (`TESTING.md` §7).
- **Docs.** Learn tab §7 and §8 explain the check, the readings and the rate with its source;
  `CONFIDENCE.md` records the r7 figures, the residuals and the clustered power figure; TESTPLAN 7.3,
  7.5 and a new 7.13; the glossary adds p-value and survivorship.

## v2.296 — 2026-10-13

Everything below is
about the time-stop shadow block (*Every entry, graded at a fixed date*, manual §10). Its figures
are paper entries with a coin-flip direction, before costs, fees and slippage, with exact fills; a
crossed line is not a trading edge. (ADR 0002 Amendment 1, `docs/specs/shadow-ledger.md`)

- **Results are recorded once and kept.** v2.260 worked the block out in memory, so every restart
  of the agent (one comes with every install) decided each result again from that day's closes, and
  a failed price request or a restated close could change a look after it had been shown. The agent
  now writes each decided result and each look to a record, `shadow_ledger.json` in the data folder,
  the first time it exists, and never changes either. **A look is shown as a result only once it is
  recorded**, and its line starts with that date ("Look 1 of 3, recorded …"). A look worked out but
  not recorded yet shows no z, no crossing and no "the test ends here". The block ends with "Record
  kept since {date}." Each pass checks the recorded looks against today's entries and the test's
  fixed settings; a difference is shown, and the recorded result is kept. Only the agent that holds
  the book writes the record.
- **A look waits up to 28 days for a missing price.** An entry with no usable closing price after
  its 4-week date was left out after 7 days. It is now left out only when 28 days have passed since
  that date **and** requests on at least 3 different days (UTC), from day 7 on, could not settle it.
  The tried days are kept in the record, so a restart does not skip them. The waiting line says
  until when. A missing price is usually brief, so the look is then usually graded on every entry;
  the cost is that a look can come up to about 4 weeks later.
- **Entries still left out are filled in at their extremes, and a crossing must survive them.**
  When a look goes ahead with entries left out for want of a price or closed by hand, each is filled
  in at its own target and at its own stop, and z is worked out for every combination (above 12
  left out: the two combinations that push the slope furthest each way). The block shows the lowest
  and highest z found: extreme cases, not estimates and not limits. A crossing counts only when z
  and every fill are past the line on the same side; otherwise the look says it is "past the line,
  but not in every extreme case" and the test goes on. **This costs power (simulated, synthetic
  books, no real data):** with about 3 of 201 entries left out, the chance of a crossing when a real
  link of correlation 0.2 exists fell from about 70% to about 63%, and with about 7 to about 49%
  (4,000 books per case); the false-alarm rate fell from 5.5% to 3.8% (12,000 books). **With nothing
  left out, nothing changes:** the same entries, the same z and the same line as v2.260.
- **`no_risk`.** An entry whose stop was at or past its fill price has no R. It is now left out at
  once and counted on its own ("whose stop was at or past the fill price"), instead of under "no
  closing price", and it is not filled in at the extremes. The app's paper broker fills at the
  planned entry, so none is expected.
- **Errata.** A recorded result is never changed. If one is later found wrong (a bad tick, a
  restated close), a person adds an erratum to the record by hand (position, reason, corrected R,
  date) under a written ADR note, with the agent and the app stopped. The block shows it with the
  look(s) that counted the result; it never changes whether a look crossed or the test ended. The
  app never writes errata. The five shown are those touching a recorded look, newest first; the
  rest are counted, with how many of them touch a look. An erratum with no corrected R says so.
- **A missing, unreadable or other book's record is an error, never a fresh start.** Nothing is
  recorded and no look is shown as a result until it is fixed, and the block says which case it is:
  unreadable; missing (this book had one, this folder had one, or backups of it exist); an older
  copy holding fewer looks; another book's record; or a copy of a retired one. The paper book
  (`portfolio.json`) and a file beside the record (`shadow_ledger.id`) note that a record exists. A
  copy is made right after a record's first write and right after each recorded look, here and
  off-site, besides the daily backup, so the newest backup copy holds every recorded look (unless
  that copy failed). The newest copy is the last one by name; on a look's day, the `.look<k>` copy;
  after a reset, the newest one whose name ends in the first 8 characters of the id in
  `shadow_ledger.id`. Putting the right file back clears the error on the next pass.
- **Retiring a record, only after a reset.** After a deliberate reset of the paper book, the old
  record is refused ("It does not belong to this book"). To start a new one, stop the agent and the
  app and rename `shadow_ledger.json` to `shadow_ledger.retired.<its ledger_id>.json` in the same
  folder. Nothing is deleted, and a new record starts. It re-tests the same kind of entries, so the
  block's last line always says how many records were retired in the folder and when the first was
  ("Record kept since … 1 earlier record was retired in this folder, on … Its looks are not
  counted here, and this record re-tests the same kind of entries."). A retirement is refused while
  the paper book's own note names the record: that book was not reset, so the record is reported
  missing and no new one starts. README, under the paper-book reset.
- Not fixed in this build (spec `shadow-ledger.md`, Known limits): no fsync before the file is
  renamed into place; the record is not tamper-evident; a copy after a look that fails is not
  reported; the old record's backups rotate out after a reset; the robust rule's power cost above;
  the extreme fills are not a bound on z; the date given for a retired record is when its file
  last changed status, which a restore from a backup moves.
## v2.266 — 2026-10-13

- **Plainer wording when the time-stop test ends without a crossing.** The closing line of the
  *Every entry, graded at a fixed date* block now says "not enough evidence that the score ranks
  4-week results" instead of "no evidence … at the planned size", and adds that with 201 entries
  a link of about 0.2 or more, if one existed, would be found about 3 times in 4, so a weaker one could have been
  missed. If fewer than the planned 201 entries had a result, it says how many and that the test
  was less sensitive than designed. "Planned size" could be read as position size; "no evidence" overstated a negative.
  ADR 0002 §3 amended. No behaviour change.

## v2.260 — 2026-10-12

Installed 2026-10-12 from the commit that carries this entry, built in a clean detached worktree
(stamp `dirty: false`). Release record: `docs/audit/shadow-time-stop-sre-release.md`.

- **A second score grade that leaves no entry out.** The existing grade (*Is the score right?* on
  the landing page, the calibration panel on My trades) counts only positions closed at their
  target or stop. The slow ones stay open and outside it, and a quick close is more often the
  nearer barrier, the stop, so that grade leaned on the quick resolvers. Under it, a new block,
  **Every entry, graded at a fixed date** (Expert: *Time-stop shadow*), gives every protocol entry
  a result 4 weeks after it opened (on the week profile): its target or stop if the book closed it
  there first, otherwise the close after those 4 weeks. The result is in **R**, the result in
  units of the amount risked. It is a test only at three looks fixed in advance, the first 45, 101
  and 201 protocol entries, each judged once against a line at ±2.315. Until a look is due it says
  *Not a test yet*, and from 20 results a line marked *running, not a test* shows the paper
  average. The first row names the entry dates the figures cover. Entries chosen by hand, closed by
  hand before the 4 weeks, or with no closing price 7 days after their date are left out and
  counted on screen. These are paper entries with a coin-flip direction, before costs, fees and
  slippage, with exact fills; even a crossed line is not a trading edge. The agent works it out on
  each scan, in memory, from the book and Yahoo daily closes; nothing is written to disk. A window
  that follows the agent shows the agent's copy, and with an older agent it says *Not available
  from the running agent*. No exit, no row's odds and nothing in the existing grade or its verdict
  changes. Manual §10 has the details. (ADR 0002, `docs/specs/shadow-time-stop.md`)
- CI: `actions/checkout` and `actions/setup-python` move to v7, which run on Node.js 24
  (GitHub is retiring Node.js 20 for actions). No change to the app.
- The launchd agent runs the installed `SONAR.app` headless instead of the checkout's working tree,
  so an edit in the checkout cannot reach it on a restart. `install_agent.sh` checks the app's
  signature, clean build stamp and self-test first; `./build_app.sh --install` stops the agent
  around the copy and starts it on the new build, and refuses a dirty build while the agent runs
  the app. Agent logs move to `~/Library/Logs/SONAR`. `--checkout` keeps the old way.
  (closing-sre-release P1-2, part 2, option A)

## v2.215 — 2026-10-12

Installed 2026-10-12 from `5b34235`, built in a clean detached worktree so the stamp reads
`dirty: false` (the main checkout always carries other sessions' tracked edits and the activity
log). The previous v2.190 is kept at `~/Library/Application Support/SONAR-rollback.noindex/`.
The agent was **not** restarted: it runs the checkout's working tree, so it still runs the code
it loaded at 10:56 (no `build` field in `/api/health`) until someone restarts it on a tree
they have checked.

- The suite no longer prints "MainWindow already deleted" tracebacks after its last test. The close
  button's confirm and hide timers outlived the window they were queued for; they now check it is
  still alive (`shiboken6.isValid`) before touching it. Exit code was always 0, which is why it
  went unnoticed.
- `/api/health` says which code the agent loaded: `build: {version, commit, dirty, source,
  nested}`, read at start, nested repos included; unknown is reported as `null`, not clean.
- `scripts/install_agent.sh` refuses a tree with uncommitted tracked changes (its own or a
  nested repo's) unless `--allow-dirty`; `--status` prints the running agent's build.
  (closing-sre-release P1-2, part 1; running the agent from a clean snapshot awaits the owner.)
- A failed bitcoin poll no longer freezes the app: the Screener and Big picture keep drawing,
  the status line says the poll failed and why, and the empty Screener says what is true (scan
  failed, nothing priced, still waiting after N minutes, read-only) instead of "Fetching prices…"
  forever. Big picture clears old figures when it has no regime. (closing UX C-1)
- A refused trade, a failed close or undo, and a setting that did not apply each get a ⚠ message
  in the window's bar for 8 seconds, and the status line keeps an action's result instead of being
  rewritten within a second; "applying — rescanning…" stays until the rescan is done, without
  hiding warnings. A setting a read-only window cannot change now says so.
  (closing UX C-2)

## Unreleased — 2026-10-12

**The time-stop shadow reads a damaged readout as unreadable.** A look counts as crossed
only when its flag is `true` and its z is a finite number; otherwise the block says "Could not
work it out this time (unreadable)" instead of a "crossed" line with z +0.00. Look numbers are
held to 1 to 3, and the looks, bands and entries it reads are cut to the lengths the engine writes.
New tests pin the mean-R range, the 7-day price grace and the T bar. ADR 0002 now records that the
whole design's false-alarm rate measures about 6%, not 5%; the bar stays 2.315 (owner's choice) and
no on-screen text changes.

**A window follows only an engine on this machine.** The engine lock names
the running engine's address; the window now follows it only if it is a plain
http address on this machine, and says so when it is not. Following never goes
through a configured proxy (macOS's system proxy does not exempt 127.0.0.1)
and never follows a redirect. An engine started with `--host ::1` now binds
and can be followed, and a lock with an unreadable start time no longer stops
the window's engine thread (`docs/specs/follow-url-localhost.md`).

**Text from outside the app is drawn as text.** Labels are plain text by
default, so a feed, the Nasdaq calendar or a followed engine cannot style or
reword the window with markup; the Playmaker and Lab panes escape pasted book
names, parse errors and backtest text, and no pane follows a link drawn in it.
Error messages shown in the window are one cleaned line of at most 160
characters; a failed setting change now names the error type. Books that
disagree on how many outcomes a market has get "Could not read the prices."
instead of nothing (`docs/specs/untrusted-text-sweep.md`).

**A followed engine's read answer stays with that engine; error text is never
markup.** While following another SONAR process, whether a read can run is that
process's answer; it was kept after the window moved to another holder or the
holder restarted, so the new one was shown the old one's "ready" or refusal. It
is now tied to the holder that gave it (`docs/specs/holder-llm-playmaker-plaintext.md`).
The Playmaker status line is plain text, and the Playmaker completion and the
read and prop workers show exception text cleaned and capped, as the LLM read
already did.

**The LLM read fails plainly, and its reply is drawn as text.** A refused,
truncated, unparseable or wrongly shaped reply, and every API error (one fixed
line per status, a timeout, a full context window), now becomes a plain error
line in the read panel instead of a half-answer or an exception; the server's
raw error body is never shown (`docs/specs/llm-read-hardening.md`). The panel's
subject, verdict and body are plain text, so a reply steered by a headline
cannot draw its own link or image (security S1).

**Tests for what the closing QA found unpinned** (`docs/specs/closing-qa-fixes.md`):
an hour closing at its open is scored UP (M7); fills outside the 0.02-0.98
buyability band are excluded and counted, the edges included (M4); a second
warm-up correction never overwrites the kept original record (X6, replacing a
test that could not fail); the calibrated grade labels (M5, unreachable today);
and the follow tests wait for the holder's whole first round, which removes a
flake on a loaded machine.

**The docs say what broker the book actually uses.** README, the Learn tab,
`GOING_LIVE.md` and `.env.example` said that adding Alpaca paper keys made the
book use Alpaca, and that Alpaca was the more honest mode. No code path did
that: the book always uses the built-in simulator. They now say so, keep the
cost disclosure (no spread, slippage or fees, polled prices, so an optimistic
bound, not a forecast), and call the Alpaca adapter "not connected yet". A new
test reads the source of `sonar/`, `ui/` and `main.py` and fails on a
`Portfolio(` call given a broker, any reference to `default_broker` (aliased
imports resolved), an `AlpacaPaperBroker(` built outside `default_broker`, or a
`broker` attribute assigned outside the book's and the order guard's
constructors, so the docs have to change with the code. It is a source scan,
not a runtime check (`docs/specs/book-broker-truth.md`).

**Honest baselines for the backtest and the buyability verdict (QA-11, QA-13).**
The buyability line's "survives leave-one-out" check could never fail. A claim
either way now needs the mean return per stake beyond three standard errors,
and a positive one the same again without its two best hours; otherwise it reads
"not demonstrated". The backtest compares each setup with the chance of the
target first *given it resolved in time* (39.44% on the default run, not the
untimed 40%), counts and shows setups that ran out of time, and leaves out
setups with under two horizons of data after them. Its error bar is the widest of
the binomial, Newey-West and a bar that counts setups entered on the same day
together; attention and attribution use the same bar. No verdict above a
120-day horizon, on one asset class, under 100 setups or 20 entry dates, or on
entries spanning under five horizons. Re-measured default run (2y, h = 5, 129
instruments): 39.55% against 39.44%, +0.11 points, error bar ±1.8, n 18,973.
The bar is not a calibrated 5% test: a random direction per asset class still
got a verdict on about 1 run in 10 (11.4%), and the verdict copy says so. The
Learn tab §7–§8, `CONFIDENCE.md`, ADR 0001, `TESTPLAN.md` §2 and §7 and the
backlog are restated (`docs/specs/qa11-qa13-honest-baselines.md`).

## v2.187 — 2026-10-11

**"Is the score right?" says how much of the book it could not grade.** The
calibration report grades closed positions only, and the paper book has no
time stop, so how long a position takes to close depends on its score and the
closed set is the quick ones: on the live book 54% / 40% / 14% of the entries
had closed across the 0–20 / 40–60 / 60–80 bands
(`docs/audit/calibration-censoring-by-score.md`). Each band's line on the
first screen now says how many positions were entered, how many are still open
and their median age, and how many closed; when 40% or more of a band's
entries are still open, the panel adds that the verdict is provisional because
slow positions are missing from the grade. My trades' calibration table
carries the same open counts and caveat. Only the readout changed:
`calibration.report()`, its verdict text and the book are as they were, and the
grade-by-cohort and time-stop options in the audit note remain the owner's
call.


## v2.180 — 2026-10-10

**One day of review, then the fixes.** Builds v2.132 to v2.180 were all made
on 2026-10-10 and are recorded here as one entry, by theme, not build by build.
The first internal audit (eight roles, `docs/audit/`) found no money-path
defect and a list of ways the paper record could be wrong or silent. Every P0
and P1 finding is fixed; the product was defined; most P2 items are done.

**The record cannot silently go wrong**
- The paper book and the engine are written whole from any thread (locks and
  per-writer temp files), and a window taking over from the agent no longer
  writes its launch-time book over the agent's. The engine lock survives
  races, reused pids and malformed files.
- The fair-odds warm-up is chart history, not money: the book's P&L is
  corrected on load and the old figure is kept beside the file.
- A past hour's candle no longer voids a live position. A position the risk
  filter hides is still priced, watched and closed at its own price.
- The hourly market is found in any locale and on the night the clocks go
  back. The hourly σ is the estimator the study measured, on whole and fresh
  history.
- Calibration is a report, never an input: the track record no longer moves
  P(profit). Research claims say "not detected", not "absent".

**The agent says when it stops**
- A health check (`/api/health`, 503 when unhealthy), a watchdog that exits so
  launchd restarts a dead engine loop, and a macOS notification when polling or
  settling stalls. Failed polls are logged and counted instead of swallowed.
- The price poll never waits on the scan, the σ fetch or FRED.
- The local API answers only this machine's own requests (Host, Origin and
  JSON content-type checks, a body-size cap, a socket timeout).
- The order guard fails closed on NaN and on an unwritable audit log; untrusted
  feed and model text stays text.

**Backups and build**
- A second copy of the book goes off its own disk (`SONAR_BACKUP_DIR` or a
  `backup-to` file, 30 kept). A restore from it was drilled once.
- CI installs from a hashed `requirements.lock` and checks out the nested
  repos at pinned commits. The built app's ad-hoc seal survives its version
  stamp, and a build whose git check fails is stamped dirty, not clean.

**What you see**
- The product is defined (`docs/specs/v1-product.md`): a notability scanner
  and an honest paper book, for the owner. The two experiments sit under a
  **Lab** heading at the foot of the rail.
- Status at any window width, a 30-second **undo** after a trade or close, and
  a first-run **Start here** card. The Screener says it is loading; practice
  money is always said; "edge" waits for proof. My trades and News say what
  they are waiting for; Practice, Sports and Macro use plain wording.
- The README is 386 lines (was 1,105); the HTTP API table is `docs/api.md`;
  MIT licence.

**Not done:** no signed or notarized build, no second-machine install, and
the Google Drive leg of the backup was never tested. The closing review of
2026-10-11 (`docs/audit/closing-*.md`) lists what remains.

## v2.131 — 2026-10-08

**"Is the score right?" on the first screen.** The question the app exists
to answer was two clicks away, in a table on My trades. The landing page now
carries the calibration verdict directly under the figures — the sentence
`calibration.report()` reaches, verbatim; one line per score band with how
many closed, how many won, the rate the plan promised, and whether the band
has the twenty it needs to count; and what the verdict still lacks: how many
of the twenty closed positions exist, how many were coin-flip protocol
entries so the table grades the score and not a picker, and whether protocol
mode is on. It also says why the profit figures above it cannot answer the
question: a coin-flip position's profit is luck, and the score claims that
something is happening, never which way. The heading links to the manual's
grading section.

## v2.130 — 2026-10-08

**The agent and the installed app share one book — they never had.** A frozen
app keeps its state in `~/Library/Application Support/SONAR`; the launchd
agent runs `main.py` from the checkout, whose default is `data/`. Two
directories, two locks, two experiments: for weeks the "agent that keeps the
run going while the window is closed" was running a second run nobody looked
at, and the follow mode of v2.128 had nothing to connect. `SONAR_DATA` now
overrides the state directory (`paths.user_data_base`), the agent's launchd
plist sets it to the app's directory, and `install_agent.sh` no longer
refuses to reinstall over the agent it manages. The app's run (the one on
screen) is the one that continues; the agent's `data/` run stays on disk,
untouched, for a checkout run from source.

## v2.128 — 2026-10-08

**A window beside the agent follows it instead of going blank.** The launchd
agent and the window share one book, and the engine lock lets only one of
them drive. The one without the lock used to sit there read-only: a window
with an empty book, an agent that never drove once the window quit. Now it
follows. The agent writes its address into the lock; a window that loses the
race mirrors the agent's snapshot, board, book, alerts and knobs over
localhost, and hands it every action that writes the book — buy, short,
close, the knobs, protocol mode, an LLM read — so there is still exactly one
writer. The status line says *following the engine at 127.0.0.1:8787*. Whoever
waits re-tries the lock every fifteen seconds and takes over the moment it is
free, in either direction, without a restart. New routes on the daemon:
`/api/book`, `/api/wire`, `/api/trade`, `/api/close`.

## v2.127 — 2026-10-08

**The app opens on your money, not on bitcoin.** The first screen had been
the hourly BTC model since the app existed — one asset, traded by the model
with its own practice cash, captioned "practice cash" as if it were yours. It
never was. The landing page is now **My investments**: profit or loss now as
the biggest figure, the account value, what is invested — split into cash
spent on longs and stock borrowed for shorts, because summed blindly the real
book read $46k on a $10k account — what every stop hitting would cost, and
what has closed; the **account's value over time**; every open position as a
tile sized by what it can lose and coloured by how it is doing; what resolved
recently; and a card per position with its entry, target and stop drawn over
sixty days of price. The whole page scrolls; a short screen sees the figures
and the curve first.

The account-value curve is new data, not just a new picture. The book now
logs its value hourly and at every entry, exit or barrier hit
(`equity_log` in `portfolio.json`), and on first run rebuilds the weeks
before the log existed from its own records and real daily closes — the
trades it made, valued at each day's close — so the curve starts where the
book did. A point is only written when every held position has a price.

The hourly model kept its readout and lost its page: it lives at the foot of
Practice now, unchanged, with the LLM read panel. README §"The portfolio
landing page".

## v2.118 — 2026-09-29

**The close button, and the menu bar's manners.** Two reports from the same
session, both about the window doing something other than what was asked.

Closing from full screen left the window on screen, blank, and a second press
of the red X did nothing at all — the app had to be quit from the Dock. The
deferred hide waited 350ms for the Space to collapse and the animation takes
longer than that; AppKit drops a hide aimed at a window still animating out of
full screen, while Qt records it as hidden anyway. That mismatch explains both
halves: a window nobody could see hidden, and a close button with nothing left
to hide. The hide now waits until the window has actually left full screen,
confirms against the platform window that it landed, and a close arriving at a
window Qt already thinks is hidden shows it before hiding it again.

Clicking the menu-bar icon dragged the whole app to the front over whatever the
user was working in. It opens the menu now, and nothing else — which is what
every other Mac menu-bar item does. "Open SONAR" is the item that opens SONAR.
Because macOS activates the app to show the menu, and `main.py` reads an
activation as a Dock click, the click is recorded so the Dock handler can tell
the two apart.

## v2.116 — 2026-09-29

**The Cockpit shell.** The second design round, from a mockup approved before
any code moved (the first round, v2.108, fixed vocabulary and contrast; this
one fixes structure). The eight top tabs became a **left rail** — both names
per destination, exactly as before, folding to icons below 1420pt of window
width and unfolding above it; the toolbar's wordmark, version badge and
practice-money line moved to the rail's head, the Wording and Test plan
buttons and the status line to its foot. A **page header** names every screen
in one sentence and keeps the risk and horizon knobs visible everywhere. The
Terminal's six equal stat cells became a hierarchy: the edge — the only
number in the app that is a disagreement with a market — is the largest
figure on screen in the one highlighted cell, tau is drawn as a filling
hour-bar as well as printed, and the bankroll strip and the model-vs-market
Brier line share one ledger panel under the equity curve. Same readouts, same
tooltips, same wording rules; `tests/test_layout.py` gained the two shell
invariants (folded fits 1280×775; expanded minimum stays below the fold
threshold, or the fold could never be reached by dragging). For the record:
two sessions shared this checkout on the day, so the shell's code landed
split across the v2.115 and v2.116 commits rather than under its own message.

## v2.115 — 2026-09-29

**The engine can no longer trade an hour that has already settled.** `tick()`
never checked that the market belongs to the candle, so around wakes and feed
hiccups a stale candle could meet a fresh market and buy the known outcome —
five live fills entered 22–51 minutes after their own hour closed were 71% of
the first week's paper P&L. One invariant now guards signal, scoring and entry
alike: an hourly market ends exactly one hour after its candle opens, or the
tick is refused. The phantom fills were scrubbed and the equity curve rebuilt.
`Engine.buyability()` also lands in this build, rebuilt after adversarial
review to price the strategy the engine actually trades — entry-window hours
only, side chosen as the entry path chooses it, settlement-state books
excluded and counted, Newey-West-widened errors, and a positive verdict that
must survive leave-one-out of its best hour.

## v2.114 — 2026-09-28

**CI survives a machine that is not this one.** The dashboard-consistency
test skips on an `exists()` check instead of trusting a spec for a missing
file, the AGE column widened 66→72 so DejaVu's metrics fit as well as SF's,
and the checkout fetches full history because the version *is* the commit
count. A four-lens adversarial audit found nothing further real.

## v2.113 — 2026-09-23

**The catalyst weight faced attribution — the first component ever to come
back KEEP** (IC +0.040 surviving FDR, +5.0-point quintile spread, 6/6 time
blocks, and the phase-shift control inverts rather than shrugs), measured
against a historical earnings calendar built from EDGAR Item-2.02 8-K
filings; a volatility effect, not a direction, and P(profit) stays pinned.
The Lab gained the earnings-history checkbox and the SPORTS MODELS panel, so
both studies re-run from inside the app; the Playmaker KEEP bar became a
measured bootstrap interval; `universe.py`, `charts.py` and `tray.py` got
their tests; and the score log stopped booking snapshots against
already-ended markets.

## v2.112 — 2026-09-22

**SONAR no longer aborts when its menu bar menu opens.** macOS 27 made
`-[NSEvent clickCount]` raise for an event that has no click count, and Qt's
cocoa plugin asks for it whenever a menu begins tracking — the Objective-C
exception unwinds through C++ frames that catch nothing, into `terminate()`.
PySide6 6.11.2 is the newest release, so there was nothing to upgrade to.
`ui/appkit_guard.py` is Lab Hub's guard, ported: it replaces that one selector
with an implementation answering 0 for the event types that have no click count
and calling through for the ten that do, installed before `QApplication` is
built. `--selftest` fails without it. This matters more here than in most apps —
the close button hides to the menu bar, so that menu is the way back in. Both
copies of the guard should be deleted once Qt ships a fixed cocoa plugin.

## v2.108 — 2026-09-22

The build a person without a finance background can read.

**The Plain Language direction.** Picked from three mockups. The complaint was
specific — the font, the contrast, the dropdowns — and the diagnosis underneath
it was that the board was five abbreviations in a row with no way in. `MOM` is
now "Recent move" over *over 5 days*; `VOL` is "Swing size" over *big swings*;
`R:R` and `P(PROF)` are one column reading "win 1.5× the risk / 40% of the
time"; `CONF` is "Worth a look", with the score drawn as a meter whose segments
are still the component breakdown. Every row carries one plain sentence built
from numbers already on it, and a test asserts that sentence can never acquire a
direction — it is the easiest place in the app to break the rule the project
rests on, and it would do it in a friendly voice.

**Type and contrast.** `ui/theme.py` splits one font helper into three: `text`
for words, `figure` for numbers (same face, tabular digits), `code` for actual
monospace, which survives in the two places that take a pasted table. `MUTED`
and `FAINT` both clear 4.5:1 against the panel they sit on; `FAINT` measured
1.9:1. Raising it exposed a latent bug: every `QLabel` inherited the blanket
`QWidget { background }` rule and painted the window colour over whatever panel
it sat on — invisible while the two colours were three points apart on the same
near-black, a dark box behind every cell once they were not.

**Plain or expert.** A `Wording` button switches the whole app between the two
vocabularies, and `ui/words.py` remembers the choice. Expert restores MOM, VOL,
`R:R · P(PROF)` and CONF, puts the ticker back, drops the second lines and the
banner, and shows one line per tab — about a third less row height. It changes
the vocabulary and the density, **never the layout**: `ASSET_COLS` carries both
headings and one width, so the header re-captions in place and there is only
ever one board to keep correct.

**The manual is a tab.** `static/docs.html` — the primer, the 24-term glossary
and §8 on judging a result — now renders inside the window, with contents on the
left and a search box that takes one unfamiliar word. It was a button that opened
a web browser, which is the wrong place for it: someone looking at a number they
do not understand is exactly the person who will not go and find a second
window. The HTML stays the single source; `ui/learn.py` strips the CSS Qt cannot
parse and injects the anchors Qt needs. Headings that name something non-obvious
link into it, and a test checks every anchor resolves.

**How old is this price?** An `Updated` column on every Screener row. The board
refetches only the 26 stalest of 129 markets per scan, so a row is routinely
minutes old by design — defensible until the screen shows the age as nothing at
all, at which point a fifteen-minute-old number reads exactly like a live one.
It is anchored to the scan's own timestamp so it keeps counting between scans.

**Both names on every tab**, painted by the new `ui/tabs.py`: the plain one over
the one the manual uses. Qt draws a `\n` in a tab label on one line and clips it.
The Practice and Sports tabs moved into scroll areas — a `QTabWidget`'s minimum
height is its tallest page's, so those two decided how short the window could be,
which was survivable in 9pt monospace and is not in the interface font.

1,339 tests. `TESTPLAN.md` is 117 manual cases.

## v2.103 — 2026-09-22

The first build that can say what it is, and whether it is current.

**Versioning.** `VERSION` holds the arc (`2`); the build number is
`git rev-list --count HEAD`. The window title, the header badge beside the name,
the menu-bar menu, `--selftest` and the bundle's `Info.plist` all read it from
`sonar/version.py`. Frozen builds carry `_build_info.json`, stamped by
`scripts/stamp_version.py` before packaging; `--selftest` now fails for a frozen
bundle without one. Hovering the badge reports the commit, the date, whether
this is a checkout or a package, and — by comparing against the checkout —
whether a newer build exists. When that cannot be known it says so instead of
claiming "up to date". A packaged bundle has no `.git` inside it, so the stamp
also records where the checkout was and the staleness check looks there — a
bundle copied to another machine finds nothing and goes back to saying it cannot
know. Same scheme and same two inputs as the Lab Project Monitor, so the
dashboard and the app cannot disagree. See `VERSIONING.md`.

**Quitting no longer freezes the app.** `shutdown()`'s last resort for a thread
that would not stop was `QThread.terminate()`, which kills a thread wherever it
stands; one running Python holds the GIL and never returns it, so every thread
blocked forever — the event loop included. The window stopped repainting and
macOS showed its empty backing store: the blank white window reported four
times, in an app themed `#080b11`. It fired routinely, because `live.stop()`
only lands between fetches, so any quit during a request had to outlast an 8–30s
socket timeout. The process now ends with `os._exit` instead, which skips the
QThread destructors whose `qFatal()` was the only reason terminate was wanted.
Nothing is lost: the engine writes through on every change, and the engine lock
is a PID file the next launch reclaims. The per-thread 4s wait became a 1.5s
budget shared across all six threads — six waits on the UI thread was up to 24s
of the same unpainted window.

**The local server answers bursts.** `PaperServer` sets a listen backlog of 64.
`socketserver`'s default of 5 is how many connections the kernel holds before
`accept()` reaches them, so past it a connection is refused with an RST before
any application code runs. Measured at twelve simultaneous requests, one was
reset every run.

**Build order fixed.** `build_app.sh` regenerated `static/testplan.html` *after*
packaging and installing, so an edited `TESTPLAN.md` shipped as the previous
build's page and was only corrected in time for the next one. It now runs before
PyInstaller, as its comment always claimed.

**Tests.** The suite's teardown had the same `terminate()` deadlock, which is
why it wedged about one run in three: the conftest guards were `autouse` at
*function* scope, and pytest builds fixtures highest-scope-first, so none of
them was in force when the module-scoped window fixtures built a window — those
tests were running the real engine against the real application directory and
the real network. Guards are session-scoped now. Deterministic, 9.3s.
