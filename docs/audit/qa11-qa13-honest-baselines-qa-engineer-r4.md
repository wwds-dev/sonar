# QA round 4: QA-11 / QA-13 loop-3 changes (uncommitted)

- Verifier: `qa-engineer` (read-only), 2026-10-12. Saved by the orchestrator. Harness and mutants only in the scratch copy `scratchpad/repo`; real `sonar/`, `ui/`, `tests/` byte-identical to the start snapshot. Other sessions changed `AGENTS.md`, `.claude/commands/harden.md`, `docs/company/tooling*`, and committed 756917f (none of `sonar/`, `ui/`, `tests/`).
- Playbook `docs/playbooks/qa-engineer.md` `status: baseline` (stale per AGENTS.md).

**Verdict: PASS on every loop-3 check. No P0/P1 against this change.** Release waits on Document (unchanged since round 2). Two pre-existing model-risk readings on real bars for the owner (P2-A, P2-B).

## 1. Suites, twice each — PASS
| run | exit | result |
|---|---|---|
| native 1 | 0 | 1861 passed, 30 deselected, 43.4 s |
| offscreen 1 | 0 | 1861 passed, 40.7 s |
| native 2 | 0 | 1861 passed, 45.9 s |
| offscreen 2 | 0 | 1861 passed, 189.4 s (contended) |
Noise as before. Docs count 1861 matches.

## 2. Follow-mode race — PASS
- `test_the_protocol_switch_is_handed_to_the_holder` 300/300 in-process offscreen (round 3: 2/300 failed).
- Round-3 delay injection (100 ms between fetch and apply): 20/20 runs, 0 stale `True` samples (~50/run); round 3 flipped back 10/10.
- The two-bump hole is real: rebuilt by making `_mirror_mark` ignore in-flight, main thread's `_post` delayed 200 ms → 10/10 runs `during_forward=[True]` and `True` right after `set_protocol(False)` (lasts up to 10 s in production). New in-flight guard: 10/10 `False`/`False`. The suite's `[/api/config-during-after]` case kills this mutant (C1).
- `_forward` raising (`RuntimeError` after 50 ms): propagates, `_in_flight` back to 0, holder's `True` mirrored back (correct — holder never took it), later holder knob changes arrive; without `finally` `_in_flight` sticks at 1. `configure()` with `_post` raising `OSError`: `_in_flight` 0, local risk unchanged, mirroring resumes.

## 3. Loop-3 rules at boundaries — PASS
- Single class through `run()`: on a rigged drift significant over `"all"`, each of Equity/Index/Forex/Crypto/Commodity → `withheld="single_class"`, `significant=False`, same n and delta; attribution "not judged" + `NOT_JUDGED`. Fails safe: anything but exactly `"all"` withholds ("Whole watchlist", "ALL", ""). Lab passes `lab_universe.currentData()`, Terminal `WHOLE_WATCHLIST`; worker the only production caller. Live 2y h=120: Equity (n=1,956), Index (n=793) → "No verdict on Equity/Index alone." (the round-3 P1).
- Span need−1 / need (need = ⌈5·h·365/252⌉, 40 dates, entries 23:30 UTC): h=5 37; h=20 145; h=60 435; h=120 870 — need−1 `span`, need verdict. Copy floors the ratio (36 days → "4.9 times"; 869 at h=120 → "4.9"). At h ≤ 2 the span gate can't bind (20 dates span ≥ 19 days).
- Precedence: all 16 combinations of {h 121, "Index", n 99, span 50 days} resolve to the first of horizon → single_class → too_few → span, `significant` False whenever any applies; 19 dates `too_few`, 20 verdict.
- Gating: strong-spike log judged → spike +31 pt significant, "A news spike shifts the odds", momentum and news KEEP, volatility DROP; for each of horizon/single_class/too_few/span → no bucket significant, "No reading on attention either", all "not judged", none survives FDR.
- Momentum table in `MainWindow._lab_html` on real `run()`: `0–2% | 958 | 54.9% | +15.5`, `2–5% | 475 | 64.2% | +24.8`, `5–10% | 2 | 100.0% | +60.5`. Live 2y h=5: `0–2% +0.56`, `2–5% −0.23`, `5–10% +0.21`, `10–100% +0.10`.

## 4. Live Yahoo
- **Lab default unchanged:** loop-2 and loop-3 `backtest.py` agree on every shared field on three bar sets; `run_symbol` byte-identical. Round-2 bars reproduce: n 18,975, 39.69% vs 39.44%, Δ +0.25, se 0.42, 2,608 timeouts (84 data end), 360 too near the end. **Today's bars (129/129): n 18,958; 39.68% realised vs 39.44% predicted (40% with unlimited time); Δ +0.24 pt, se 0.42; "no edge detected"; 2,610 timeouts (12.10%, 89 data end); 354 too near the end; expectancy beyond a no-edge market +0.0061 R; raw −0.0079 R; drift +0.0041σ; 566 entry dates 2024-11-10 to 2026-10-01.**
- Terminal profiles, whole watchlist, today:

| profile | range | n | span | verdict |
|---|---|---|---|---|
| h=1 | 2y | 18,691 | — | "0.8 points below … did worse than a coin flip" (z −2.4) |
| h=5 | 2y | 18,958 | — | no edge |
| h=20 | 2y | 17,958 | — | no edge |
| h=60 | 2y | 13,656 | 6.32 horizons | "beats the prediction by 3.2 points" (z 2.4) |
| h=250 | 5y | 22,414 | — | withheld: horizon |

- Horizon scan: 2y h=40, 60, 70 "beats"; from h=80 2y withheld for span (4.22 horizons at 80; 2.12 at 120). 5y every h 20–120 "no edge" (|z| ≤ 1.44).

## 5. Mutation — 19 mutants, 16 killed, 3 survived
Killed — core: C1 mirror ignores in-flight (two-bump); C4 no generation bump; C5 book mark after fetch; C6 protocol unguarded in `_mirror_config`. backtest: span `<`→`<=`; floor instead of ceil; span as distinct dates; span gate skipped at h > 60; single class only for Equity; too_few before single_class; attention ignores `withheld`; attribution gated only for too_few; momentum delta vs 40%. ui: Lab doesn't pass universe; worker doesn't; `NOT_JUDGED` line dropped.
Survived — **C2** no `finally` in `set_protocol` (harness kills it); **C3** no `finally` in `configure()` (holder unreachable during a knob change → follower stops mirroring protocol/knobs for the session; code correct, suite has no test); **B5** single class applied only to the five listed names (unknown string would get a verdict; untested).
Changed-line branch coverage (84% total): loop 3 — backtest 37/37 st, 14/14 br; core 36/36, 9/10 (`1129→1131`: holder config without a `protocol` key); ui/app 3/3, 4/4; worker 1/1. Whole diff — backtest 138/138, 47/48 (`323→329` unreachable); scoring 15/16 (`163→168`); engine, ui/app full. Tests pin both sides of every boundary with exact strings; race tests event-driven.

## Defects
- **P0/P1:** none against this change.
- **P2-A (model risk, pre-existing, improved):** h=1 Terminal profile says "did worse than a coin flip" on real bars; a coin gets the same in 11/38 seeds (mean Δ −0.51 pt, ~−1.4 se); momentum −0.85 only ~1 se worse than a coin. HEAD: 6/8 coin seeds. Likely tie-as-STOP on daily bars at h=1. Follow-up: placebo baseline or no verdict at h=1.
- **P2-B (model risk, information):** h=60 on 2y "beats" not confirmed by 5y; coin clean (8/8, |z| ≤ 1.41); long-only +8.7 pt → single-regime momentum reading, not a baseline artifact; copy ("a reason to look closer, not a finding") within the rules. Option: Terminal uses 5y at h ≥ 40.
- **P2-C:** Document not landed (`CONFIDENCE.md:587` 39.58/39.99; `TODO.md:251` leave-one-out; `static/docs.html` unmodified). Figures above ready.
- **P3:** C2/C3 `finally` paths and B5 fail-safe untested; `entry_span_horizons` rounds 4.9997 to 5.0 on a span-withheld run (field only; copy floors to 4.9); round-3 P3 copy items remain (owner's choice).

## Release recommendation
Loop-3 code release-ready. Hold for Document (P2-C; D4 ships QA-11 and QA-13 together). Record P2-A and P2-B as follow-ups (not regressions; P2-A better than HEAD). Optionally add the `configure()` post-failure test (C3) before merging.

Scripts in `scratchpad/scripts/`: `rules.py`, `mutate.py`, `c3.py`, `live.py`, `coin4.py`, `coin5.py`, `headh1.py`, `chcov.py`; race harness `scratchpad/repo/tests/test_qa4_race.py`; bars `scratchpad/live/bars_{2y,5y}.pkl`.
