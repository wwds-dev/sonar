# Code review: time-stop shadow readout (ADR 0002)

- Reviewer: code-reviewer, read-only. Diff `cf84642..cca9428`, 2026-10-12. Saved by the orchestrator
  from the agent's report.
- Playbook `docs/playbooks/code-reviewer.md` is `status: baseline` (2026-10-10): stale; added nothing
  beyond AGENTS.md and the brief.
- Pre-registration: nothing run against the real book. Reproductions use synthetic positions with
  `SONAR_DATA` at the session scratchpad and no `Live()` built. One network call:
  `assets.fetch_bars(sym, "5d")` for AAPL, EURCHF=X, BTC-USD and ^GSPC, to see how Yahoo stamps bars.

## Commands run
- `QT_QPA_PLATFORM=offscreen pytest tests/test_calibration.py tests/test_shadow_engine.py tests/test_shadow_ui.py -q`: **145 passed**.
- `pytest tests/test_calibration.py -m slow --durations=5`: **3 passed in 95.9 s**; the precision test
  alone **59.29 s** (P2-3). An earlier run under load was killed by faulthandler.
- `uvx --offline ruff check` on the changed files: 7 findings, the same 7 rules as the base files — no
  new lint findings.
- `git diff --stat cf84642 HEAD`: `sonar/portfolio.py` and `sonar/scoring.py` untouched; `calibration.py`
  only adds code plus a docstring paragraph and the `bisect`/`horizon` imports; `report()`, `GRADED`,
  `Z_CLAIM`, `MIN_SAMPLE`, `_verdict` unchanged.

## P0
None.

## P1 (must fix before release)

### P1-1. One failed daily fetch throws away the good bars, so graded entries become ungraded and evaluated looks change
- **Where:** `sonar/core.py:553` `cache[s] = (day, b or None)` and `:555`; then `sonar/calibration.py:382`
  (no_price after 7 days) and `:421` (`final` counts no_price as excluded).
- **Mechanism:** a failed request (`fetch_bars` → None, `assets.py:288-296`) overwrites yesterday's good
  series; the symbol drops out of `bars` until the next UTC day. Every TIME/gap entry of that symbol
  becomes `wait_price` or `no_price`. Past-T entries need bars every day forever (`shadow_needs_bars`),
  so the exposure never ends.
- **Reproduced** (45 synthetic entries): one symbol, fetch OK on 10-24 and failed on 10-25: `reached 45,
  look1 evaluated True, z -0.355` → `reached 0, wait_price 8, no_price 37, look1 evaluated False`. Two
  symbols, one failing for a day: look 1 stays evaluated on a different subset: `used 45, z +0.318` →
  `used 22, excluded 23, z -0.125` → `used 45, z +0.318`. A crossing could appear and vanish ("The test
  ends here" for a day).
- **Against ADR 0002 §3:** "each look is evaluated once", "a final exclusion", "a look depends only on
  its members". Build note 6 understates it ("needs an outage of more than a week"): one failed request
  on any day is enough, both ways.
- **Fix:** on failure keep the previous series (`cache[s] = (day, b or prev_bars)`); memoise each
  entry's decided outcome in memory by position id once decided (barrier, gap, TIME with a final T bar,
  left) — still "nothing persisted"; ask the owner whether ADR §7 should persist decided outcomes and
  look results (a holder restart during an outage has the same exposure); test: a good day, then a
  failed day, readout unchanged.

### P1-2. The newest bar's stamp is the fetch time, not the session start; the code uses it to pick the T bar and the cut
- **Where:** `sonar/calibration.py:346-349` (`bisect_right(stamps, t_due)`, `t_cut = stamps[i+1]`).
- **Evidence, live fetch 2026-10-12 11:17 UTC:** EURCHF=X's last stamps were `10-06 23:00, 10-07 23:00,
  10-08 23:00, 10-12 11:17` — the in-progress bar carries the fetch time. ADR §5 recorded this (02:55
  UTC) but guarded only the close, not the stamp. BTC-USD (00:00) and AAPL/^GSPC (13:30, market shut)
  looked normal; US equities in/just after the session not verified.
- **Reproduced:** an FX LONG opened Sunday 23:30 UTC (t_T inside Monday's session four weeks later).
  Fetched Mon 00:05: graded **TIME at Friday's close, R +0.40**, treated as final; next day **TIME at
  Monday's close, R −0.30**. ADR §4's T bar is Monday's (true stamp Sun 23:00 ≤ t_T), final only once
  Tuesday's exists. The same stamp as t_cut grades a booked barrier close between the true session start
  and the fetch time as a barrier for a day, then as TIME.
- **Exposure:** FX is 20 of 130 symbols; the window runs from session start to the first successful
  fetch of the UTC day, wider after a mid-day restart, a wake from sleep, or a failed fetch.
- **Fix:** never trust the newest bar — decide only from `series[:-1]` so the T bar and the cut bar are
  both older than the newest (at most one more day of waiting); or snap stamps to session start. Add a
  V-6 variant whose last stamp is mid-session.

## P2

### P2-1. Yahoo's split adjustment can re-grade decided entries
- `assets.py:292` reads `indicators.quote.close`, split-adjusted retroactively (documented Yahoo
  behaviour; not verified against a live split). After a 2:1 split, a LONG at 100 (stop 98) graded TIME
  sees closes near 50 and the gap check grades it STOP −1 (a SHORT becomes TARGET +1.5). Evaluated looks
  change.
- **Fix:** the P1-1 memo covers entries decided before the split; also treat a series whose bar at or
  before entry is far from `p.entry` as unusable (wait, then no_price), counted.

### P2-2. An out-of-range date in a mirrored payload breaks the existing grade's refresh
- `ui/app.py:696`, `:811` call `time.localtime` on payload numbers; `render` (`:970`) does not catch
  `OSError`. `shadow_texts({'n_entered':3,'n_reached':0,'n_waiting':3,'next_t':1e17,'looks':[]}, …)`
  raises `OSError [Errno 22]`. `render` runs before `_refresh_grade` (`:2787` vs `:2791`) and before the
  stats in `_refresh_book` (`:2436`), so every tick aborts and the existing grade stops updating —
  breaking U-2 and the untrusted-payload rule.
- **Fix:** bound timestamps in `_sh_date` and `computed_at`, or catch `OSError`/`Exception` in `render`;
  call `render` after the existing grade's refresh; add `1e17` to `test_a_damaged_readout_is_never_a_crash`.

### P2-3. The release-time slow suite is flaky against the faulthandler limit
- `pyproject.toml:32-33` (`faulthandler_timeout = 60`, `exit_on_timeout = true`);
  `test_v12_slow_the_design_size_to_a_fifth_of_a_point` took **59.29 s** alone (engineer measured 33 s);
  killed under load.
- **Fix:** parametrize the ten chunks as separate tests (~6 s each) and average in a final check, or
  shrink the libraries.

### P2-4. Carried: the design's real size is about 6%, not ADR §3's 5.0%
- Passes inside 3.5–6.5%. Owner and model-validator to decide before look 1 (~2026-11-06).

## P3
1. **Build note 2** (gap check skips the entry-session bar) is narrower than ADR §4's "a daily close
   after opened_at" (`calibration.py:357`): for an entry opened mid-session that session's close comes
   after entry; for FX/crypto the first day is never gap-checked. Small; record as an owner-approved
   deviation, or include the entry bar when its successor's stamp is after `opened_at` plus the session
   length.
2. **`ic_closed` shown without its n, from n ≥ 5** (`calibration.py:505-507`; `SH_ROW_IC`,
   `ui/app.py:551`, `:885`). `report()` withholds its IC below 20. Show the n or withhold below 20.
3. **The daily fetch runs between `_mark_book` and `_protocol_scan`/`self.assets`** (`core.py:302-305`)
   under `_rescan_lock`; a slow Yahoo can stall the first scan of each UTC day up to ceil(symbols/8) × 8 s,
   delaying the board, rescans and protocol entries. Move it after the protocol scan and the
   `self.assets` assignment.
4. **Mislabel:** zero stop distance → `no_price` ("with no closing price") (`calibration.py:393`);
   unreachable for plans the app builds today.
5. **`_shadow_range` caps at 5y:** after ~1,819 days a graded entry turns `no_price`. Far beyond the
   design; the P1-1 memo covers it.

## Engineer's judgement calls, against ADR 0002
| Build note | Faithful? |
|---|---|
| 1. Graded only from t_T even when the barrier was hit earlier | **Yes.** ADR silent on timing; keeps running figures off the quick resolvers; looks untouched. Hand closes count at once (exclusions, harmless). |
| 2. Gap check from bars starting after entry | **Narrower than the ADR's wording** (P3-1). Acceptable with owner sign-off. |
| 3. Range, plus 7 days slack | Yes (3mo reaches back 89 days; slack caps age at 83). |
| 4. Hand close before the cut excluded before the gap check | Yes (ADR §4 `n_left`; V-9 ×3). |
| 5. R formula, exit at the barrier | Yes (`portfolio.mark` fills at the barrier). |
| 6. `n_no_price` not sticky | **Not faithful** to "final exclusion" and "evaluated once"; risk much larger than stated (P1-1). |
| 11. `hc3_z` returns None, never NaN | Yes; equals the sims to `rel=1e-12`; variance checked by hand. |
| 12. Error keeps the last good dict plus the class name | Yes (`core.py:519-523`, test). |

## Checked and found correct
- ADR §4 order (barrier `closed_at < t_cut`, `≤ t_T` needs no price; gap; time; waiting).
- T bar = last bar ≤ t_T (`bisect_right − 1`), never the newest; holiday takes the session before (V-7).
- Exclusions `n_nonprotocol`, `n_left`, `n_no_price`, `n_wait_price` as specified.
- Looks: cohort by `(opened_at, id)`; `final` requires all members; `|z| ≥ 2.315` inclusive; after the
  first crossing later looks are `design_closed`, unevaluated; z uses members only.
- Purity: `dataclasses.replace` copies under `book.lock`; deep-compare test passes.
- Locks: fetch outside both locks, `self.lock` only for the assignment, no nesting, never `book.lock`
  under `self.lock`; the engine lock tests are valid (`Live.lock` is a plain `Lock`; `book.lock`, an
  `RLock`, probed from a worker thread).
- Follower: never fetches; missing key → `"unavailable"`; non-dict ignored; takeover resets to None;
  every label `Qt.PlainText`; error text cut to 80 characters.
- JSON: no NaN/inf from finite inputs.
- Test quality: the named mutants map to tests that can kill them. Gaps: a fetch failure after a success
  (P1-1), a mid-session newest-bar stamp (P1-2), an out-of-range date (P2-2).

**Verdict: not ready for release.** Pure rules, gate maths, locking and the read-only invariant are
sound, but P1-1 (a single failed fetch changes evaluated looks) and P1-2 (the newest bar's fetch-time
stamp picks the wrong T bar) break ADR 0002's "evaluated once" and must be fixed before release.
