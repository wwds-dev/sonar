# Code review, round 4: QA-11 / QA-13 honest baselines, loop 3 (uncommitted)

- Reviewer: `code-reviewer` (read-only), 2026-10-12. Saved by the orchestrator. Mutants and probes only in the session scratchpad `cr4/` (`mut.py`, `span.py`, `blend.py`, `oneclass.py`, `repo/`).
- Playbook `docs/playbooks/code-reviewer.md` `status: baseline` (stale per AGENTS.md).
- Loop 3 touched `sonar/backtest.py`, `sonar/core.py`, `ui/app.py`, `ui/worker.py`, `tests/test_backtest.py`, `tests/test_lab_tab.py`, `tests/test_follow.py`, count lines; not `engine.py`, `scoring.py`, `calibration.py`, the ADR or `CONFIDENCE.md`.

**Verdict: loop-3 code does what the owner decided. No P0, no P1.** The `sonar/core.py` follow guard is correct, cannot deadlock, and fixes QA's race (10/10 with the 100 ms delay). Universe passed explicitly on both production paths. Release blocked by Document (r3 P2-3); one new P2: a withheld run still says "the score as a whole is ranking the wrong way round".

## Evidence
- Suites: offscreen 1,861 passed, 30 deselected (197 s, exit 0); native 1,861 (57.6 s, exit 0). Known teardown traceback (`ui/app.py:3968`). Targeted (backtest, follow, lab_tab, scoring, engine): 259 passed.
- Follow flake: `tests/test_follow.py` ×25 separate processes offscreen, 0 failures (34 tests each).
- Race with delay (100 ms after every `Live._fetch`, scratch copy): protocol test 10/10; 14 knob/protocol follow tests 3/3.
- core.py mutants vs test_follow (8): 7 killed (`_settled_since` ignoring generation; `_mirror_mark` ignoring `_in_flight`; +1 bump not moving generation; `configure()` without bumps; book mirror unguarded; config mirror unguarded; `set_protocol` not setting `protocol_on` before forward); 1 survived — −1 step not moving the generation (equivalent, P3-5).
- Lock discipline: `self.lock` plain `threading.Lock` (`core.py:89`); new code takes it only at leaves, never nested, nothing under it but `risk.get`/`horizon.get`; no caller holds it when calling `set_protocol`, `configure`, `_forward`, `_mirror_*` (checked `core.py:519, 543, 575, 621-622, 643, 695, 1066-1067, 1161`, `server.py:122`, `worker.py:91`, `app.py:1874`); `book → self.lock → engine` order unaffected.
- Exceptions: `_forward` catches `Exception`; decrement in `finally` keeps `_in_flight` balanced even on `BaseException`; `configure`'s `_post` in try/finally; mirror failures hit the existing outer `except`.
- Design: QA's two-bump design had a hole (mark taken mid-flight, applied before the second bump); the `_in_flight` counter closes it.
- Takeover mid-flight: counters stay balanced (`finally` after `following` clears). Two pre-existing lost-update paths remain, not introduced here: `_load_protocol` in `_take_the_book` vs `set_protocol`; `configure`'s tail mirror vs a dying holder (not reproduced).
- Universe plumbing: only production caller of `backtest.run` is `ui/worker.py:71`; Lab passes `lab_universe.currentData()` (`app.py:2658-2663`); Terminal passes `backtest.WHOLE_WATCHLIST` (`app.py:3447-3449`); `summarise` only from `run()` (`backtest.py:758`, with horizon and universe); `research/panel.py` uses only `fetch_bars`/`fetch_attention`.
- Withheld gates: precedence horizon → single_class → too_few → span pinned by `test_why_a_verdict_is_withheld_has_one_fixed_order`; `min_verdict_span_days` 37 (h=5), 435 (60), 870 (120); boundary need−1/need tested.
- Static: ruff/pyflakes not installed (not verified); `py_compile` passes.

## Findings
**P2-1 — a withheld run still says the whole score ranks backwards** (`ui/app.py:2862-2871`): the blend line appends "a negative blend ranking skill means the score as a whole is ranking the wrong way round, not merely failing to rank" whenever `blend_ic <= 0`, with no significance test and no `withheld` check. Repro `cr4/blend.py`: single-class run, `blend_ic −0.013`, sentence rendered above "Not judged: this run gets no verdict…". An "INVERTED" claim from noise, contradicting the loop-3 rule; also untested on judged runs (pre-existing). Fix: when `a.get("withheld")` show only the number; otherwise say "ranks backwards" only if the blend IC clears a test (e.g. NW t at Z_CLAIM); add a negative-blend case to `test_a_run_without_a_verdict_shows_no_attention_or_attribution_finding`.

**P2-2 — docs still not updated** (r3 P2-3; blocks release under D4): ADR 0001 `:31`, `:70`, `:83`; `CONFIDENCE.md:580-587` ("39.58% against a 39.99% prediction", "drops trials that time out", top bucket "10%+"). Nothing user-facing documents the 120-day cap, 100/20 gates, single-class rule, 5-horizon span, "not judged", or the Agresti–Coull floor. Fix: Document phase with QA r3's figures.

**P3-1 — horizon-withheld copy promises a verdict 2y/1y can't give** (`sonar/backtest.py:670-674` "Horizons up to 120 days get one."; docstring `:35-40`). With the span rule, a whole-watchlist 2y run gets a verdict only up to ~h=71 (`cr4/span.py`: h=70 verdict, span 516 vs 507 needed; h=72 `span` 513 vs 522; h=100, 120 `span`; h=121 `horizon`); 1y tops out ~h=35. Fix: "can get one, given enough range (see the span rule)", or compute the longest judgeable horizon for the range.

**P3-2 — single-class gate looks at the universe asked for, not instruments compared** (`sonar/backtest.py:561-562`): `compared_by_class` computed but unused. Repro `cr4/oneclass.py`: all 129 requested, only 21 crypto returned (as in a partial outage; `run()` skips `None` bars at `:735`), shared drift → `universe="all"`, `withheld=None`, "beats the prediction by 19.4 points". Not reproduced on real data. Fix: also withhold `single_class` when `compared_by_class` has < 2 classes; possibly when one class dominates (threshold: owner/model-validator).

**P3-3 — `universe` defaults fail open** (`sonar/backtest.py:700` `universe=WHOLE_WATCHLIST`; `ui/worker.py:62` `"all"`): latent (both callers pass it, tests pin it). Fix: required keyword in `run()` and `BacktestThread`; use `backtest.WHOLE_WATCHLIST` not `"all"` in `worker.py:62`, `app.py:2339`.

**P3-4 — top momentum bucket "10–100%" silently drops |momentum| ≥ 100%** (`sonar/backtest.py:1092` edges end `(0.10, 1.0)` half-open; label `:1103`): such trials are in n but no bucket; `CONFIDENCE.md` calls it "10%+". Pre-existing; the label makes it visible. Fix: top edge `math.inf`, label "10%+".

**P3-5 — two follow-test docstrings claim a mutant they don't kill; the −1 generation bump is redundant** (`tests/test_follow.py:295-297`, `:325-326`; `core.py:1088`): `_in_flight` alone rejects every mirror marked during a flight; mutant `self._local_gen += (step > 0)` passed all 34 tests (equivalent). Fix: drop the −1 bump and note it, or correct the docstrings. No behaviour change.

**P3-6 — still open from r3/QA r3 (left out by owner):** n=0 hint to a crypto-only verdict-less horizon (`ui/app.py:2677-2687`); Terminal "· 0 timed out" (`:3455-3456`); UTC entry dates (`backtest.py:557`); Terminal shows no class mix/span; `_daily_vol` (`sonar/assets.py:551-553`); step-1 `longest_comparable_horizon` test gap (`tests/test_backtest.py:686-692`); `std_error` 0.0000 display.

## Copy
New strings avoid edge/profit/certainty (`test_the_new_withheld_verdicts_promise_nothing_either`); withheld runs grey without the "no edge" paragraph; components "not judged" in both wordings without keep/drop colours. Remaining: blend-IC sentence (P2-1), "Horizons up to 120 days get one" (P3-1).

## Round-3 findings
| Source | # | Status |
|---|---|---|
| CR | P1-1 coin placebos h ≤ 120 | Resolved in code as decided (placebo re-run is model-validator's) |
| CR | P2-1 withheld findings | Resolved; residual blend-IC (P2-1) |
| CR | P2-2 momentum "?"/"+0.0" | Resolved; residual P3-4 |
| CR | P2-3 docs | Unresolved (P2-2) |
| CR | P3-1 overstated copy | Unresolved (left out); wider (P3-1) |
| CR | P3-2…P3-7 | Unresolved (left out) |
| MV | P1-C single-class | Resolved as decided |
| MV | P1-B span | Resolved as decided |
| MV | P2-E conservative false verdict | Not addressed; no owner ruling recorded |
| MV | P2-F attribution outside gates | Resolved (`backtest.py:939-956`) |
| MV | P3 copy/docs | Unresolved |
| QA | P1 single-class h=120 | Resolved as decided |
| QA | P2 core.py race | Resolved and verified |
| QA | P2 docs | Unresolved |
| QA | P2 momentum table | Resolved |
| QA | P3 G2 precedence | Resolved |
| QA | P3 "· 0 timed out", "243 days", 0.0000 | Unresolved (left out) |

## Recommendation
Code ready for correctness and concurrency. Hold release for: (1) Document (P2-2); (2) P2-1 (one-line guard + test). Owner: P3-2 worth taking with P2-1 if the single-class rule should cover partial fetches; MV P2-E still open.
