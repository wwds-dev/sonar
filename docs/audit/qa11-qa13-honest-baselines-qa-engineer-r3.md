# QA round 3: QA-11 / QA-13 loop-2 changes (uncommitted)

- Verifier: `qa-engineer` (read-only), 2026-10-11. Saved by the orchestrator. Mutants and fixes only in the scratch copy `/tmp/qa_v3/repo`; `sonar/core.py` byte-identical to HEAD.
- Playbook `docs/playbooks/qa-engineer.md` `status: baseline` (stale per AGENTS.md).

**The code meets every new owner rule. Not ready to release:** a new P1 (model risk) — at h = 120 a coin-flip direction still gets "beats the prediction" on 2y Equity and Index; and the Document phase (round-2 P2-1) has not landed (`CONFIDENCE.md` unmodified). The protocol-switch flake is a real stale-mirror race in `sonar/core.py` (pre-existing), not a test race.

## 1. Suites, twice each — PASS
| run | exit | result |
|---|---|---|
| native 1 (`/tmp/qa3_n1.txt`) | 0 | 1839 passed, 30 deselected, 45.4 s |
| offscreen 1 (`/tmp/qa3_o1.txt`) | 0 | 1839 passed, 98.2 s |
| native 2 (`/tmp/qa3_n2.txt`) | 0 | 1839 passed, 56.7 s |
| offscreen 2 (`/tmp/qa3_o2.txt`) | 0 | 1839 passed, 122.3 s |
(Two other sessions running pytest concurrently. Noise as before: 3× `MainWindow already deleted`; offscreen `watchdog step failed ('StubLive' … '_stop')`.)

**LLM follow test — stable, PASS:** 25/25 separate processes offscreen; 125/125 in-process; 10/10 with the round-2 100 ms mirror delay.

**Protocol follow test — real code race.** `set_protocol` (`sonar/core.py:302-311`), when following, sets `protocol_on`, forwards, returns; the follow thread may already have fetched `/api/book` or `/api/config` with the old value, and `_mirror_book` (`:1071-1072`) / `_mirror_config` (`:1084-1085`) write the stale `True` over the user's `False`. Unchanged code: 2/100 and 2/300 in-process offscreen failures (`assert True is False`), plus once under coverage. With a 100 ms fetch→apply delay: 10/10 runs flipped back to True (24–33 of ~55 samples). User impact: `_sync_knobs` (`ui/app.py:3414`) resets the checkbox to "on" until the next slow mirror (`FOLLOW_SLOW_EVERY` = 10 s); holder state stays correct; same pattern for risk/horizon via `configure`. Fix belongs in code: a generation guard — bump `self._local_gen` before and after `_forward` in `set_protocol`; in `_mirror_book`/`_mirror_config` capture the generation before the fetch and apply `protocol_on` only if unchanged. In the scratch copy: 300/300 plain repeats, 20/20 delayed race runs, `tests/test_follow.py` all pass (373). The post-forward bump also discards a fetch begun before the holder took the change.

## 2. New owner rules — PASS as specified
- Horizon cap: h=119, 120 verdict; 121, 250 `withheld="horizon"`, `significant=False`, reason shown; `None` not capped.
- Minimum trials: 99 `too_few`; 100, 101 verdict. Minimum dates: 19 `too_few`; 20, 21 verdict; undated rows count no date.
- Live 1y all symbols h=114/117/120 (n=65/39/15, all stops): "Too few to judge: 65 compared setups from 8 entry dates …". Live Index 2y h=150, 168 (validator's "+53 pt"): "No verdict at a 168-day horizon".
- se never 0: n=1/15/100/10,000 all wins or all losses → se 0.2191/0.0704/0.0135/0.0001; the P1-B case (210 stops) now se 0.0066 with a verdict. Display edge: `std_error` rounded to 4 dp can show 0.0000 only at n > ~28k with zero wins (P3).
- Compared count and span (live 2y): h=170 "1,229 across 34 instruments (of 129 fetched)", "21 Crypto · 13 Forex", "Entry dates 2025-03-31 to 2025-11-05 · 76 dates"; h=240 19 Crypto only over 4 dates.
- 10y CL=F: HEAD crashes (`ValueError math domain error`); now `run(["CL=F"], horizon_days=5, rng="10y")` → n=734, 38.15% vs 39.46%, Δ −1.31, se 2.1, "no edge detected", 91 timeouts, 3 short, entries 2016-11-23 to 2026-09-21. 10y Commodity class: n=13,066 across 18, Δ −0.2, no crash.
- Terminal "This year" (h=250): `range_for_horizon` → `5y`; live line "BACKTEST · 22,413 resolved trials across 129 instruments, 5y … · 3,584 timed out · 21,411 too near the end of the data … No verdict at a 250-day horizon. At horizons this long an instrument's own trend dominates …" (2y would say "nothing to compare" + reason).

## 3. Lab default (2y, h=5, step 3, all 129) — PASS, unchanged
Round-2 `backtest.py` rebuilt exactly (hash matches `36c577f`) and run beside current code on round-2 bars: every shared field identical; additions `symbols_compared` 129, by class {Equity 50, Crypto 21, Forex 20, Index 20, Commodity 18}, `n_entry_dates` 566, entries 2024-11-10 to 2026-10-01, `withheld` None, `longest_comparable_horizon` 243. **Docs figures (round-2 bars): 39.69% realised vs 39.44% predicted (40% with unlimited time); n = 18,975 across 129 instruments; 2,608 ran out of time (12.08%; 84 at data end); 360 too near the end of the data (1.64% of 21,943); Δ +0.25 pt, se 0.42; "within 0.8 points … no edge detected"; expectancy beyond a no-edge market +0.0064 R; raw −0.0076 R; implied drift +0.0043σ.** Fresh bars tonight: n 18,977; 39.70%; 39.44%; 2,613 timeouts (89 data end); 353 short (only crypto bars moved).

## 4. Mutation — 27 mutants, 26 killed, 1 survived
Killed: cap `>`→`>=`, removed, `run()` not passing horizon; trials `<`→`<=`, 100→50; dates `<`→`<=`, dropped, per-timestamp; first/last swapped; se floor removed, Laplace +1/+2, floor always used; `significant` ignoring `withheld`; compared over every symbol; classes all "other"; `_vol` guard reverted; non-positive-price guard removed; `range_for_horizon` without +1; `longest_comparable_horizon` off by one; data-end including short; UI — Terminal always 2y, Terminal fetched count, Lab "no edge" on withheld, Lab entry-dates row dropped, Lab compared = fetched, Terminal no-result line without reason. **Survived G2:** horizon vs too-few check order swapped — when both apply (2y h=240: n=64 from 4 dates) the user would get "Too few" instead of the horizon reason; untested (P3).

Changed-line branch coverage: backtest 101 st / 34 br, only `294→300` missed (unreachable); ui/app 52/28 none; scoring 46/16 `163→168`; engine 48/16 none. New tests pin both sides of each boundary and exact se values; synthetic, no network.

## Defects
- **P0:** none.
- **P1 (new, model risk; not against the rule as written):** the h ≤ 120 cap does not stop a coin false positive on single-class universes at 2y. h=120 Equity: "beats … more than two standard errors" 7/8 seeds (+2.1 to +5.4 pt, z +2.1 to +3.3), n ≈ 1,930 from 47 dates, all entered 2025-04-04 to 2025-10-22 (one regime). Index: 3/4 (+5.4 to +6.6), n ≈ 790 from 150 dates. Clean: whole watchlist 2y h=120; Index 2y h=60, 90; Index 5y h=120. Likely drift convexity + understated cross-symbol se; the 20-date minimum doesn't catch a single-regime span. Options: lower cap for class universes or 2y; minimum entry span in months; date-clustered se; both-directions placebo baseline. Scripts `/tmp/qa_v3/live/coin.py`, `coin2.py`, `coin3.py`.
- **P2:** the `core.py` stale-mirror race (CI flaky offscreen ~0.7–2%/run; briefly wrong protocol state; pre-existing; fix in code as above). Round-2 P2-1 docs/ADR pending. Pre-existing since 246ec36, out of scope: Lab momentum bucket table shows "?" and a made-up "+0.0" (rows have `lo`/`hi`/`predicted`; renderer `ui/app.py:2702-2716` reads `label`/`delta`).
- **P3:** G2 precedence untested; Terminal no-result line prints "· 0 timed out"; "up to 243 days" hint points to a crypto-only verdict-less horizon (could respect `MAX_VERDICT_HORIZON`); rounded `std_error` 0.0000 at n > 28k zero wins; `294→300` unreachable.

## Release recommendation
**Hold.** Passes QA against every owner rule (suites green, 26/27 mutants killed, changed lines covered bar two unreachable branches). Release after: (1) model-validator and owner rule on the new P1; (2) Document lands (P2-1, figures above); (3) preferably the `core.py` generation guard so the follow flake stops reddening CI.
