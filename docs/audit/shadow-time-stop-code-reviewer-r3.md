# Code review, round 3: time-stop shadow readout (ADR 0002)

- **Reviewer:** code-reviewer, read-only, not the author. HEAD `a23556e`; fix loop 2 `52a715e..c939b53`
  (the later master merge changed only docs). 2026-10-12. Saved by the orchestrator.
- **Playbook stale:** `docs/playbooks/code-reviewer.md` `status: baseline` (2026-10-10).
- **Pre-registration kept:** synthetic `Position`s, `SONAR_DATA` at the scratchpad, no network, never the
  real book. Scripts in the session scratchpad `cr3/`.

## Commands run
- Offscreen and native, `tests/test_calibration.py tests/test_shadow_engine.py tests/test_shadow_ui.py tests/test_follow.py tests/test_server.py`
  → **346 passed, 22 deselected** each.
- Slow `./run-tests.sh tests/test_calibration.py -m slow -rs` → **22 passed in 253 s, exit 0, nothing
  skipped** (final tree, after the window commit).
- Full suite: only on a scratch copy with the no-fetch-time mutant (P3-2): 2377 passed, 3 `test_version`
  failures (copy not a git checkout). Full native/offscreen not run on the real tree by the reviewer.
- `cr2/latency.py` (no fetch time passed) reproduces round 1 (Thu/Fri 4.4 d). `cr3/latency.py` with
  `fetched_at`:

  | Case | Days after t_T |
  |---|---|
  | Thursday T | 2.4 |
  | Friday T | 3.4 |
  | Thursday T, Friday holiday | 4.4 |
  | Friday T, Monday holiday | 4.4 |
  | Thursday T, first pass 07:00 | 2.7 |
  | Thursday T, Friday holiday, first pass 07:00 | 4.7 |

- `mv/s1_instability.py`: B1 `wait_price`; B2 `time` at 101.0 (day 28's close, correct); B3 `wait_price`;
  part C still crashes on `r=None` (the script's fault). `fx_stamp.py`: Monday 00:05 waits, Tuesday 00:05
  `time` at Monday's close 0.997.
- Mutants on a `git archive HEAD` copy, each alone: **3/6 killed** (window without its 24 h margin, guard
  without √, `booked` refresh dropped); **3 survived** (P3-2, P3-3). Lint not run (ruff not in the venv).

## Status of r2 items
| Item | Status | Evidence |
|---|---|---|
| P2-A split guard grew with the preset | **Fixed** | `calibration.py:393-395`: 4.5·\|entry−stop\|/√momentum_days = exactly 4.5 daily σ on every preset (`build_plan` k_stop = 1, `horizon_sigma` = vol·√max(1, days), `scoring.py:229-252`); catches 2:1 below 11.1%/day and 3:2 below 7.4%; a false alarm needs a 4.5σ move inside one session (counted, never guessed); `>` so exactly 4.5σ stays usable (`test_qa_n14…`); 5-preset × 3-ratio test kills the old form |
| P2-B up to ~3 days extra wait | **Fixed as measured; see new P2-1** | latencies as above under ADR stamp convention; a failed day keeps its own fetch time (`core.py:630-633`); `test_r2_a_kept_series_is_judged_at_its_own_fetch_time` kills "judge against now" and "store now"; a kept series cannot turn final |
| P3-1 memo freezes `booked` | Fixed | `calibration.py:583-585`; mutant killed |
| P3-2 memo shares dicts | Fixed | deep copies both ways (`core.py:589-591`, `calibration.py:583`) |
| P3-3 `_take_the_book` keeps memo | Fixed | cleared while still read-only; `_shadow_pass` returns early when read-only; tested |
| P3-4 implicit lock contract | Documented, not asserted | acceptable |
| P3-5 `SH_ERROR` not cleaned | Fixed | `ui/app.py:797` |

**Round-1 P1-2 tests not weakened:** B1 still asserts `wait_price` (round 1: `time` at 99.0); the B3
live-row test asserts `wait_price` (round 1: 101.2); FX Monday 00:05 asserts `wait_price` (round 1:
Friday's 1.001). All fail on round-1 code. New expectations (B2 `time` at 101.0; FX Tuesday 1.004) are the
correct closes under ADR §5's convention.

## New findings
### P0: none. P1: none (see the condition on P2-1).

### P2-1. Newest-bar trust and the bounded cut assume the newest stamp falls inside its session; if Yahoo's weekend stamp breaks that, round-1 P1-2 comes back
- **Where:** `sonar/calibration.py:385` (trust test), `:396` (T-bar pick over a trusted newest stamp), `:400`
  (that stamp as the exact cut), `:401-403` (window `(stamp−24h, stamp]`); spec Build note 16.
- **Assumption:** the newest stamp S′ satisfies `start ≤ S′ < start + 24h`, and on the trusted path S′ *is*
  the session start. Evidence for it: an in-progress bar during trading (EURCHF=X 02:55 / 11:17 on a
  Monday); finished US bars Monday 02:55 UTC. **Not verified:** a finished newest bar fetched 24–55 h after
  its session — exactly the Saturday/Sunday 00:01 fetch (and the day after a holiday), when trust first
  applies.
- **Reproduced** (`cr3/stamp.py`, US bars 13:30, one fetch a day at 00:01 UTC, Thu close 99.5, Fri close
  100.5) under a *last-trade stamp* (Friday 20:00 until Monday's bar) and a *fetch-time stamp* on the
  closed weekend: a Friday t_T (15:00) gives `time` at **99.5 (Thursday's close, before t_T)** on Sunday and
  Monday, then 100.5 from Tuesday — the round-1 flip; a Thursday t_T with TARGET booked Friday 16:00
  (last-trade model) gives `target` Sunday/Monday, then `time` at 99.5 from Tuesday. The memo freezes the
  first answer within a process; a restart gives the other.
- Round-2 code (52a715e, `cr3/stamp_r2.py`) is right under all three conventions; with session-start
  stamps the new code is correct and faster.
- **Exposure:** any t_T inside the last session before a weekend or holiday — on week, every US entry opened
  in a Friday session, plus FX Friday sessions.
- **Severity:** P2 now; **P1 if a weekend fetch shows a newest stamp other than the session start.**
- **Fix:** (1) verify with Saturday/Sunday ~01:00 UTC fetches of ^GSPC, META, EURCHF=X, TRX-USD and record
  the newest stamps in ADR §5; (2) independently, use the newest bar's *stamp* only when its time of day
  equals the previous bar's (`(s[-1]−s[-2]) % 86400 == 0`): then it is an exact cut whatever its age and its
  close is never needed; otherwise drop it as in round 2. Prototype `cr3/proto.py` is right under all three
  conventions (Thu T 1.4 d, Fri T 3.4 d under ADR §5; round-2 latency otherwise); DST or 23:00/00:00 FX
  shifts cost only a day. Add tests with a finished newest bar stamped 20:00 and at fetch time on a Sunday.

### P3
1. **The FX window path does not run in production:** `_shadow_pass` takes `now` before the request
   (`core.py:578`) and rows stamped after `now` are dropped (`calibration.py:570`), so a fetch-time live row
   is always dropped. `cr3/fx_future.py`: live row 0.5 s after `now` → Tuesday `wait_price`, Wednesday `time`
   at 1.004; stamped exactly at `now` → Tuesday. Correct but a day later than note 16
   (`shadow-time-stop.md:515`) and `test_v6_the_fx_sunday…` imply. Fix the docs, or moot if P2-1 drops the window.
2. **The engine's fetch-time wiring is untested:** `core.py:587` calling `shadow_time_stop(held, done,
   bars, now, decided)` without `fetched` survives every shadow test (the kept-series test asserts
   `wait_price` both days, which also holds when nothing is trusted). Fix: an engine test where a ≥ 24 h old
   newest bar decides (`n_reached == 1`), and does not without the fetch time.
3. **Two boundary mutants survive:** trust `>` → `>=` at exactly 24 h (`calibration.py:385`); `closed_at <=
   cut_lo` → `<` (`:409`; at equality the answer is "before the cut"). Add equality tests.
4. **Latency wording:** "A holiday after T adds a day" (`calibration.py:381`, spec `:511-514`) is wrong for
   Thursday T with a Friday holiday (2.4 → 4.4 d); with a 07:00 first pass 4.7 d, leaving 2.3 d of grace,
   not "at least 2.6". Say "up to two days" with the first-pass caveat.
5. **Slow mean tests' skip:** in a full `-m slow` run nothing skips (verified) and a broken chunk fails on
   its own. A partial selection exits 0 with skips (`-k "fifth_of_a_point or holds_the_measured_size or
   (size_chunk and 3)"` → 1 passed, 2 skipped, exit 0; a `--lf` rerun would do the same). Docstring at
   `tests/test_calibration.py:1157` stale ("alone … takes about a minute"). Fix the docstring; optionally fail
   when 0 < chunks run < N.

### No findings
- **Entry-date window** (`ui/app.py:838`, `:905-918`): the follower gets `entries` in the mirrored dict
  (`server.py:181`, `_mirror_book`); graded if any else all; pending never in `entries`; clamped; "n/a"
  never raises; an empty row filtered at `:839`.
- **Copy:** strings match the code (gap exits at the barrier, 95% range = mean ± 1.96·sd/√n, no costs).

## Verdict
Not ready to release until P2-1 is resolved — either a weekend fetch confirms the session-start convention
(recorded in ADR §5) or the time-of-day check goes in. Everything from r2 is fixed with tests; shadow files
green offscreen, native and slow; no P0/P1. P3-2 (an untested fix) is worth doing with it.
