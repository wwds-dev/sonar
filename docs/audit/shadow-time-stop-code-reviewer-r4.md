# Code review round 4: time-stop shadow, fix loop 3 (`a23556e..fa8d05c`)

No P0, P1 or P2. The session-pattern rule is correct under all three stamp conventions, and every new test
kills the mutant it claims to. Two P3s: a docs wording problem and a count a damaged date makes wrong.
Saved by the orchestrator, 2026-10-12.

**Setup:** read-only at HEAD `725f879` (code identical to `fa8d05c`; the last commit adds audit reports
only). Playbook `docs/playbooks/code-reviewer.md` `status: baseline` (stale). Synthetic data only, never
the real book. Main venv interpreter. Scratch scripts in the session scratchpad `cr4/` (`stamp.py`,
`latency.py`, `stamp_hol.py`, `intl.py`, `plug/mut4.py`).

## Runs
- Shadow files (`test_calibration`, `test_shadow_engine`, `test_shadow_ui`, `test_follow`, `test_server`):
  native 354 passed, 22 deselected; offscreen 354 passed.
- Slow `tests/test_calibration.py -m slow`: 22 passed in 232 s (the chunk helper does not break a full run).
- `--collect-only tests/`: 2393 of 2445, matching README, TESTING, TESTPLAN and testplan.html (2,393).
- Lint not checked (`ruff` not installed).

## Status of round-3 items
| r3 item | Status | Evidence |
|---|---|---|
| P2-1 newest-bar trust assumed a session-start stamp | **Fixed** | `calibration.py:351-358`, `:385-386`; `cr4/stamp.py` at HEAD (below) |
| P3-1 FX window | Moot | bounded cut removed; `test_v6_the_fx_sunday…` expects a wait on Tuesday, a grade on Wednesday at Monday's close |
| P3-2 engine wiring | **Fixed** | `test_r3_the_engine_decides_on_a_session_start_newest_bar` kills the engine stripping the newest bar (`b[:-1]` at `core.py:627`) |
| P3-3 boundaries | **Fixed** | pattern tested at 0 s and ±1 s; `closed_at <= t_cut` killed by `test_v3_the_cut_is_the_next_bars_stamp_exclusive` |
| P3-4 latency wording | **Mostly fixed** | session-start latencies 1.4, 3.4, 4.4, 4.4, 1.7, 4.7 d match; one wrong spec claim remains (P3-A) |
| P3-5 mean tests on a partial chunk run | **Fixed** | `_v12_all_chunks_or_skip` skips when no chunk ran, fails when only some did; a meta-test fails on a skip |

## Check 1: the rule under three stamp conventions (`cr4/stamp.py`, one fetch a day at 00:01)
| Case | Session-start stamps | Fetch-time stamps | Last-trade stamps |
|---|---|---|---|
| Thursday T | Saturday at 99.5 | Tuesday at 99.5 | Tuesday at 99.5 |
| Friday T | Tuesday at 100.5 | Wednesday at 100.5 | Wednesday at 100.5 |
| Thursday T, TARGET booked Friday 16:00 | TIME at 99.5 | not run | TIME at 99.5 (waits until then) |

- No flips: every entry waits, grades once and keeps it; nothing graded at Thursday's close for a Friday T;
  the booked TARGET never kept.
- Holidays (`cr4/stamp_hol.py`, all conventions): Thursday T before a Friday holiday and Friday T before a
  Monday holiday decide correctly, no flips.
- The newest close is never used: after the pattern check `i + 1 >= len(series)` returns None, so the T bar
  is at most second-newest; the gap loop runs only to `i`; the split guard's `before` can be the newest bar
  only when `opened_at >= stamps[-1]`, which returns None at `stamps[i] <= p.opened_at`.
- Only the newest bar needs the check: Yahoo gives an odd stamp only to a fetch's newest row; a kept series
  is still one fetch; rows after `now` removed first (`calibration.py:552`).
- DST/FX shifts only delay (`test_r3_a_dst_shift…` holds; the hour-loosened mutant killed).
- `fetch_bars` returns `int` stamps (`assets.py:295`), so `% DAY_S == 0` is exact.

## Check 2: what loop 3 removed
Grep of `.py`, `.md`, `.html` for `SHADOW_FINAL_AFTER_S`, `fetched_at`, `cut_lo`, `cut_hi`, "bounded cut":
only audit history and the spec's account of loop 2; no code, constant, test or caller. Every caller uses
the new signatures. The engine-cache comment (`core.py:239`) is accurate. ADR 0002 §5 needs no change. The
kept series still works (`core.py:627`); two mutants (store `(day, b)` without the kept series; strip the
newest bar) killed by `test_a_failed_request_keeps_the_series_already_held`. The memo is unchanged.

## Check 3: mutation check of the new tests (in-memory patching via a pytest plugin)
| Mutant | Killed by |
|---|---|
| Newest bar always kept | 10 tests (both Friday-T stamp variants, booked TARGET, DST, the engine's off-pattern case) |
| Newest bar always dropped | pattern test at 0 s |
| Pattern loosened to ±1 h | pattern test at ±1 s, DST test |
| M20 check removed | `test_qa_r3_m20…` |
| Newest close usable (`t_cut = inf`) | `test_v6_a_t_bar_still_trading_is_not_a_result` |
| Rule 1 `<` → `<=` | `test_v3…exclusive` |
| Engine strips the newest bar | engine test, session-start case |
| W02 any bad date blanks the window | `test_qa_r3_w02…` |
| Window count uses all rows | `test_window_names_the_period…` |

## Check 4: copy and spec for N-5 to N-7
N-5: spec D4/D5 match the copy (`ui/app.py:560-571`). N-6: `SH_ROW_WINDOW`/`SH_ROW_WINDOW_NONE` match D6,
Build note 26, TESTPLAN 11.22; `{n}` uses the same graded filter as `n_reached`. N-7: `SH_ROW_GAP` matches.

## New findings
- **P3-A. Build note 16 understates the delay under the other stamp conventions and leaves the grace claim
  unscoped** (`docs/specs/shadow-time-stop.md:520-527`; the docstring `sonar/calibration.py:377-382` is
  correctly scoped). The note says fetch-time and last-trade stamps take "up to two days longer" and "the
  worst … leaves 2.3 days before the 7-day grace"; TESTPLAN 11.23 says "either answer is safe". Measured:
  Thursday T decided Saturday (session-start) vs Tuesday (fetch-time / last-trade) — **3 days** longer; a US
  holiday under last-trade stamps (Thursday T before a Friday holiday) decided at the Wednesday 00:01 fetch,
  5.4 d after t_T, 5.7 d with a 07:00 first pass, leaving **1.3 days**; markets whose session starts near
  00:00 UTC (^N225, ^KS11, in the universe) with fetch-time in-progress stamps drop the newest bar at every
  00:01 fetch, so every T waits a day more (Monday T 0.7 → 1.7 d), and in Golden Week 2026 a Friday T is
  decided 6.73 d after t_T, leaving 0.27 d. Outcomes stay correct, but `shadow_looks` counts `no_price` as a
  final exclusion while the memo does not keep it, so crossing the grace limit can evaluate a look on an
  entry graded the next day (pre-existing; loop 3 only narrows the margin under unconfirmed conventions).
  **Fix:** "up to 3 days longer"; scope 2.3 d to session-start stamps on US bars; add the last-trade worst
  case (5.7 d, 1.3 left) and Golden Week; optionally add ^N225 to TESTPLAN 11.23.
- **P3-B. With a damaged entry date the window row counts an entry its dates do not cover**
  (`ui/app.py:913-923`; pinned by `tests/test_shadow_ui.py:687-696`): three graded entries, one with
  `opened_at` `"x"`, `1e18` or `None`, read "the 3 with a result opened 22 Sep to 3 Oct". Low impact
  (corrupted payload only). Fix: `{n}` = `len(good)` when some dates are bad, or add "(k with no readable date)".

**Verdict:** ready to release from the code-review side; the P3s can be deferred. Still between this branch
and release: the owner's live weekend check (TESTPLAN 11.23), the Document phase (no CHANGELOG entry yet)
and the Release gate.
