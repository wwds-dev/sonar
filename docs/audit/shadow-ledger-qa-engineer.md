# QA report: shadow ledger (Verify phase), HEAD 4ada4d1
qa-engineer, read-only, 2026-10-13. Saved by the orchestrator from the agent's report, condensed.
Playbook `docs/playbooks/qa-engineer.md` is `status: baseline` (stale).

## Summary
1. **Conditional PASS.** All 8 success measures are shown by tests on synthetic books with a scratch
   `SONAR_DATA`. S4, S6 and S7 have unpinned edges. One latent code defect (P2-1). No P0 or P1.
2. **Suite:** native, offscreen and slow each exit 0; 2,520 passed, 3 skipped, 61 deselected
   (= the documented 2,523). Load 105–179. No flake.
3. **Mutation:** 65 own mutants; 38 killed, 27 survived (7 equivalent, 20 real test gaps). For the
   gaps checked, the code is right today (probes P1–P7), but a regression would go unseen.
4. **Coverage on changed lines (branch):** `calibration.py` 93.8%, `core.py` 87.8%, `ui/app.py`
   92.9%, `portfolio.py` 100%.

## Method
Synthetic books and pytest scratch directories only; the real book was never read. Mutants ran in a
scratch copy (`git archive HEAD` + nested repos, own git) under session scratchpad `qa/src`, each
undone with `git checkout`; tools `qa/tools/mut.py`, `covsum.py`; log `qa/mut_log.txt`. Each mutant
ran the four shadow test files (375 tests, offscreen, `-x`).

## Success measures mapped
| Item | Test(s) | Shows it? |
|---|---|---|
| S1 / L-1 | `test_l1_…every_fetch_failing…` | Yes (look dict, entries and file look equal after restart) |
| S1 / L-2 | `test_l2_…[rescaled 2:1, restated]` | Yes; asserts a recomputation would differ |
| S2 / L-3 | `test_l3_…` | Yes; also no refetch |
| S3 / L-4 | `test_l4_…` (300 random pairs) | Yes; strong |
| S3 / L-5 | `test_l5_…`, `test_cr_p3_4_…` | Yes |
| S4 / L-6 | `test_l6_…[6 damages]` | Yes (bytes and mtime) |
| S4 / L-7 | `test_l7_…` | Partial (P2-2) |
| S5 / L-15 | `test_l15_…`, `test_cr_p2_1_…`, `test_sec_p3_3_…` | Yes; halves of "behind" not separated |
| L-8 | `test_l8_…[follower, read-only]` | Yes |
| S6 / L-9, L-10 | `test_l9_…`, `test_l10_…` | Mostly; the 28-day edge not pinned |
| S7 / L-11 | `test_l11_…` | Mostly; "same side" not pinned (P2-4) |
| L-12 | `test_l12_…` (400 cohorts vs a v2.260 reimplementation) | Yes |
| L-13 | `test_l13_…` | Yes |
| S7 / L-14 | `test_calibration.py::test_l14_slow_*` | Yes; a regression pin to build seeds |
| L-16, L-17 | `test_l16_…`, `test_l17_…` | Yes |
| S8 / L-18 | `test_l18_…` + autouse `refuse_live_data` | Yes |

## Mutants that survived (real gaps unless marked E)
Q05 E; Q08 graded entry with `r: null` accepted; Q10 `used` not checked; Q11 E; Q12 negative marker
counts; Q15 E in practice; Q18 undefined vertex skipped (`calibration.py:467-468` uncovered); Q21 robust
rule ignores side; Q26 grace at 28.5 days; Q29 memo tries ignored; Q30 `price_until` min vs max; Q37
10-minute rule every pass; Q38 marker/sidecar id disagreement ignored; Q39/Q40 halves of "behind";
Q43 damaged sidecar ignored; Q44 E in practice; Q45 ownership skips entries; Q48 refresh takes whole
file; Q51 no refresh before write; Q55 E in practice; Q56 E; Q57 no `recorded` key counts; Q61 past-look
rows for unrecorded looks; Q63 E; Q64 mismatches/errata while blocked; Q65 "The test is finished" with
unrecorded looks. All other 38 of Q01–Q65 killed (full table in `qa/mut_log.txt`).

## Coverage (4 shadow files)
| File | Changed statements | Changed branches | Shadow section branches |
|---|---|---|---|
| `sonar/calibration.py` | 331/335 | 105/112 (93.8%) | 167/174 (96.0%) |
| `sonar/core.py` | 212/226 | 65/74 (87.8%) | 75/84 (89.3%) |
| `ui/app.py` | 83/86 | 39/42 (92.9%) | 111/116 (95.7%) |
| `sonar/portfolio.py` | 8/8 | 2/2 | n/a |

Uncovered that matter: `calibration.py:467-468`, `:1166-1167`; `core.py:736-737`, `:797-800`,
`:836-838`, `:914-915`.

## Findings
- **P2-1 (code).** `ledger_merge` (`calibration.py:1171-1174`) adds a `price_tries` day every failed
  day with no limit; `ledger_parse` (`:1078`) refuses more than 400. Probe `qa/probe/tries_cap.py`:
  after 401 days, `LedgerFormatError`; every later write then fails its read-back, so nothing more is
  recorded (visible as a write error). About 13 months after a never-priced entry's T. Fix: cap or
  trim once `no_price`; test.
- **P2-2 (tests).** S4 gating unpinned for Q57 (no `recorded` key, Build note 2's v2.260-holder case),
  Q61, Q65. Code right today (probes P1–P3).
- **P2-3 (test).** A reset before look 1 leaves a foreign ledger with entries only; untested (Q45). Code
  right (probe P4).
- **P2-4.** S7's "same side" unpinned (Q21): z ≥ 2.315 and z_hi ≥ 2.315 but z_lo ≤ −2.315 would be
  refused by `_check_look` while the readout still says crossed.
- **P3.** (1) grace edge Q26, `price_until` Q30, memo tries Q29; (2) parser holes Q08, Q10, Q12, Q18;
  (3) anchor edges Q37, Q38, Q43, Q39/Q40; (4) change detection Q48, Q51; (5) Q64; (6)
  `test_shadow_engine.py` `_today()` uses `date.today()` while passes use a fixed NOW (midnight flake);
  (7) L-14 is a regression pin; (8) offscreen `StubLive._stop` stderr noise from `test_server.py`
  (pre-existing); (9) stale playbook.

**Test quality: good.** Real `Live` holders on scratch dirs; only the fetch and `write_atomically`
stubbed; writes checked by bytes and mtime; preconditions asserted so tests can fail.
