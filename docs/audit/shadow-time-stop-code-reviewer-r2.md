# Code review, round 2: time-stop shadow readout (ADR 0002)

- **Reviewer:** code-reviewer, read-only, not the author. HEAD `52a715e`; whole change `82125df..HEAD`;
  fix loop `cca9428..5546cc5`. 2026-10-12. Saved by the orchestrator. Resumed once after a usage-limit
  cut-off; tree unchanged meanwhile.
- **Playbook stale:** `docs/playbooks/code-reviewer.md` still `status: baseline` (2026-10-10).
- **Pre-registration kept:** synthetic `Position`s and the pure function only, `SONAR_DATA` at the
  scratchpad, no `Live()` outside pytest, no network.

## Commands run
- `QT_QPA_PLATFORM=offscreen pytest tests/test_calibration.py tests/test_shadow_engine.py tests/test_shadow_ui.py tests/test_follow.py tests/test_server.py -q`
  → **300 passed, 22 deselected**.
- `QT_QPA_PLATFORM=offscreen pytest tests/ -q` → **2336 passed, 3 skipped, 52 deselected in 202.8 s**
  (2,339 collected). Native and slow not run by the reviewer (the orchestrator ran both on 52a715e: native
  2336 passed / 3 skipped, slow 22 passed, exit 0).
- Mutation spot-check on a `git archive HEAD` copy (baseline green first), each mutant alone: **6/6
  killed** — M11 (gap check skips the T bar), M14 (`shadow_needs_bars` ignores closes after t_T), U08
  (`SH_FINAL_NONE` after 2 looks), newest bar kept (`[:-1]` removed), split guard removed, `no_price`
  memoised.
- `mv/s1_instability.py` from a scratch cwd: part A at the pure-function level still drops to the quick
  resolvers (expected: the protection is in the engine); B1, B2, B3 now `wait_price`; part C crashes on
  `r=None` because the split guard now returns `wait_price`.
- Scratch `cr2/demo.py`, `cr2/latency.py` back P2-A, P2-B, P3-1.

## Status of round-1 items
| Item | Status | Evidence |
|---|---|---|
| CR P1-1 / MV P1-1 (failed fetch rewrote evaluated looks) | **Fixed** within one process | detail 1 |
| CR P1-2 / MV P1-2 (newest bar's fetch-time stamp) | **Fixed** | detail 2 |
| Security P2-1 / CR P2-2 (out-of-range timestamps) | **Fixed** | detail 3 |
| Security P2-2 / CR P2-1 / MV P2-3 (bad closes, splits) | **Partly fixed** | closes ≤ 0 and per-row validation fixed (`calibration.py:518-525`); the split guard is sound against false alarms but **misses 2:1 and 3:2 splits on wide-stop presets** (P2-A); a decided entry survives a later split via the memo (`test_rewritten_closes_do_not_regrade_a_decided_entry`) |
| Domain P1-1 / P1-2, validator P2-4 copy | **Strings changed as described** | detail 4 |
| QA survivors | **Killing tests exist** | M11, M14, U08 and three new-logic mutants spot-checked, all killed |
| CR P2-3 slow-test flake | Fixed as described (10 chunks + mean check) | not re-run here |

1. **Failed fetch:** a failed request keeps the series held (`core.py:617`
   `cache[s] = (day, b or cache.get(s, (None, None))[1])`); decided outcomes memoised by position id
   (`core.py:576-581`; `calibration.py:387-396`, `:536-538`); decided ids not refetched (`core.py:577`).
   Tests `test_a_failed_day_after_a_good_one_changes_nothing`,
   `test_mv_s1a_failed_fetches_leave_look_1_as_evaluated[all, every third]` pass; memo mutants killed.
   Key: ids are `uuid4().hex[:12]` (`portfolio.py:271`); no book-reset path; only protocol, filled
   positions looked up (`:530-538`). Thread: `_shadow_pass` has one call site (`core.py:354`) inside
   `_rescan_once`, always under `_rescan_lock` (taken by the engine, background and settings-change
   threads) — serialised (P3-4). Wrong decisions it could freeze: a hand close never (`close()` stamps
   `time.time()`, `portfolio.py:301`, so a close after a TIME decision is after the cut; protocol entries
   cannot be undone, `portfolio.py:313`); pending skipped before the memo, so pending→filled is safe; a
   decision from a bad close (a split the guard misses, P2-A, or a plausible bad tick, the engineer's
   acknowledged residual) is frozen for the process. Takeover: `_take_the_book` resets `shadow` but not
   the memo — harmless today (P3-3).
2. **Newest bar:** `calibration.py:359` drops the newest bar before the T bar or cut is picked; bars after
   `now` dropped at `:524`. B3 traced by hand: the in-progress session row can only be the T bar if a later
   non-newest bar exists, else `i + 1 >= len` → None; never in the gap range. Tests
   `test_v6_a_newest_bar_stamped_mid_session_decides_nothing`, `test_a_bar_stamped_after_now_is_ignored`.
   Side effect: up to ~3 days of extra wait (P2-B).
3. **Timestamps:** `_sh_ts` bounds to 0..4e10 (`ui/app.py:701-711`) for `_sh_date` and `computed_at`;
   `render` catches `OSError` (`:992-995`); both pages render the shadow after the existing grade
   (`_refresh_book` ~`:2499`, `_refresh_portfolio` ~`:2813-2816`). Tests
   `test_an_impossible_date_reads_as_n_a_not_as_a_failure`,
   `test_the_existing_grade_is_refreshed_before_the_shadow`.
4. **Copy:** crossed UP/DOWN "On these paper entries … on average"; `SH_CAVEAT_CROSSED` names costs, fees,
   slippage, exact fills, "can cross by chance" (expert: "a by-design false-alarm rate", no number);
   `SH_ROW_REF`/`SH_ROW_BAND` conditional on the volatility estimate; `SH_NOTE` "direction was random"
   replaced; `SH_LOOK_NOT_CROSSED` "no link strong enough to cross the line yet"; `SH_FINAL_NONE`
   unchanged per the owner.

**Master merge and follower path intact:** `82125df` changed only how the follower opens connections
(`_FOLLOW_OPENER`, `_loopback_url`); `_mirror_book`'s shadow handling (`core.py:1306-1312`) and
`/api/book`'s `shadow` (`server.py:181`) unchanged; the real-HTTP follower test and the server test pass;
shadow labels stay `Qt.PlainText`.

## New findings
### P0 — none. P1 — none.

### P2-A. The split guard scales with the horizon, so it misses ordinary splits on month, quarter and year presets
- `sonar/calibration.py:366` (check), `:267-276` (comment); spec Build note 19.
- The bound is in stop distances, and a stop distance is `σ_daily·√momentum_days·entry`
  (`scoring.build_plan`, `assets.py:466`). The comment's "2 is over four daily σ" holds only for week.
  Bound per preset: week 2√5 ≈ 4.5 daily σ; month 2√20 ≈ 8.9; quarter 2√60 ≈ 15.5; year 2√250 ≈ 31.6.
- Reproduced (`cr2/demo.py`, flat at 100, 2:1 split after entry so closes read 50): week and month at
  1.5–3.5% daily σ and quarter at 1.5–2% rejected (`wait_price`); **quarter at 3.5%/day (stop 27%, guard
  54%) graded `stop`, R −1.0, gap** (true: TIME ≈ 0R). Also: month at 4%/day misses a 3:2 split; year at
  2%/day misses a 2:1. The memo then freezes the wrong grade.
- The false-alarm side is sound for every preset (a gap over 2 stop distances in the "before" session
  means a barrier was crossed in it; the book would have settled the entry before T).
- Exposure: non-default presets only (quarter T = 336 days).
- **Fix:** state the bound in daily σ, independent of preset, e.g. reject when
  `|before − entry| > G·|entry − stop|/√momentum_days` with G ≈ 4.5 (today's week value; catches 2:1 and
  3:2 below ~7%/day on every preset); better, request `events=split` in a shadow-only fetch and treat any
  split after `opened_at` as unusable. Correct the comment and Build note 19; add a test parametrised over
  presets (quarter at 3.5% is the failing case).

### P2-B. Dropping the newest bar adds up to ~3 days of waiting, not "at most one"; the 7-day grace keeps ~1.3–2.6 days of slack
- `calibration.py:354-359` ("at most a day more of waiting"), spec Build note 16; interacts with the
  once-per-UTC-day fetch (`core.py:602-604`) and `SHADOW_PRICE_GRACE_DAYS = 7` (`:266`).
- The first pass of each UTC day (~00:01) fetches a US equity whose newest bar is the previous completed
  session — dropped; over a weekend three fetches see the same Friday bar as newest.
- Measured (`cr2/latency.py`): t_due Thu/Fri, no holiday → decided at t_due + 4.4 d; holiday the day after
  T or the Monday after → + 5.4 d; same with the first pass at 07:00 UTC (laptop asleep) → + 5.7 d. Round 1
  decided about 3 days earlier in weekend cases.
- Consequence: two missed fetch days around a weekend/holiday make the entry `no_price` (excluded), so a
  look can become final and evaluated; `no_price` is reversible (`calibration.py:414-416`) and not
  memoised, so the look's members and z change when closes arrive. Spec note 6 accepts the exposure, but
  the fix made it more likely and the docs understate it.
- **Fix (one of):** (1) store the fetch time in the cache and treat the newest bar as final when its stamp
  is ≥ 24 h before *that fetch* (not `now`: a kept series from a failed day would look final); (2) re-fetch
  symbols with `wait_price` entries more than once a day; (3) correct the docstring and note 16 to "up to
  ~3 days (weekends, holidays)" and tell the owner the remaining slack. Add a Thu/Fri t_due latency test.

### P3
1. **The memo freezes `booked`**, so `ic_closed`/`n_closed_same` depend on timing and restarts
   (`calibration.py:536-538`, `:553`): an entry decided TIME while open, then closed TARGET 3 days later →
   memo `booked=None, n_closed_same=0`; recomputed `booked=TARGET, n_closed_same=1` (R and state equal).
   Fix: refresh `e["booked"]` from the current position after copying the memo entry.
2. **The memo shares dicts with the published readout** (`core.py:579-581`; nested `ref` lists). No reader
   mutates them today. Fix: store `copy.deepcopy(v)` (or `dict(v)` with `ref` as a tuple).
3. **`_take_the_book` resets `self.shadow` (`core.py:1156`) but not `_shadow_decided`/`_shadow_bars`.**
   Unreachable today. Fix: clear both there.
4. **The memo's thread-safety is implicit** (relies on `_rescan_lock`, `core.py:302`, `:308`, `:354`).
   Fix: document it or assert the lock is held.
5. **`SH_ERROR` shows `str(d["error"])[:80]`** (`ui/app.py:791`), not `_clean(...)` as the untrusted-text
   sweep does elsewhere. `PlainText`, so only control characters/newlines matter. Fix: `_clean(d["error"], 80)`.

## Verdict
Ready for release once P2-A is fixed and P2-B is fixed or its docs corrected with the owner told. The
round-1 P1s are fixed with tests and killed mutants; no new P0/P1; the follower path survived the merge;
offscreen green (2336 passed, 3 skipped).
