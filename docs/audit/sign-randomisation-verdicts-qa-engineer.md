# QA Verify: sign-randomisation verdicts (HEAD 6423c56)

`qa-engineer`, read-only. Saved by the orchestrator, 2026-10-12. Playbook `status: baseline`; the owner chose to continue on it. Mutations were made only in a scratch copy. Evidence is in the session scratchpad `qa/`.

**Overall: PASS with gaps.** 4/4 suite runs green. 44/45 mutants killed. Measures 8 and 11 met; measure 9 partly met.

## Suite runs
| Run | Exit | Result | Wall | Load |
|---|---|---|---|---|
| native 1 | 0 | 2191 passed, 3 skipped, 30 deselected | 165 s | 54→67 |
| offscreen 1 | 0 | 2191 passed, 3 skipped | 445 s | 73→118 |
| native 2 | 0 | 2191 passed, 3 skipped | 231 s | 167→113 |
| offscreen 2 | 0 | 2191 passed, 3 skipped | 534 s | 113→102 |

## Findings
- **P2-1. Mutant R4 survives: "p_tail = the smaller tail".** (`randomisation.py:164` → `2*min(p_hi,p_lo)`)
  - Every test passes with it, because in the existing fixtures the tail in Δ's direction is always the smaller one.
  - It is a real failure: Δ +0.246, p_hi 0.984, p_lo 0.0176 should read "not told apart", but the mutant reads "beats". 126/3,000 synthetic 9-cluster runs flip this way.
  - Fix: a fixture with Δ > 0 and p_lo < p_hi that asserts `p_tail == min(1, 2·p_hi)` and `verdict_state == "unconfirmed"` (spec §11 test 3).
- **P2-2. The rate tests are tight under the 60 s cap, and the faulthandler abort kills the whole session.**
  - The exactness test takes 52.2 s alone (load ~140).
  - Under the documented coverage command at load ~128, `test_a_correlated_coin_rarely_gets_a_verdict` hit the cap and aborted the run; uncapped, the rate tests take 69–139 s under coverage.
  - The tooling-baseline coverage step (`docs/company/tooling-baseline.md:29`) will not complete under load.
  - Fix: share worlds through a session fixture, and/or keep slow tests out of the coverage run.
- **P2-3. Measure 9 is incomplete in this build.**
  - Open hits:
    - `static/docs.html:650`, `:654-656`, `:665`
    - `CONFIDENCE.md:600`, `:625`
    - `static/testplan.html:246`
  - The `{measured}` placeholder is still in the code (`backtest.py:159`).
  - These are tracked as tech-writer/validator items. The code strings are done and pinned.
- **P2-4. The headline tests catch today's code only narrowly.**
  - With the gate removed, set 1 reads 24, exactly at its ≤24 bound (passes); set 2 reads 31 (fails).
  - The beats bound never catches today's code (10 and 14 against ≤14).
  - The true ungated rate on these worlds is 9.2% (10 sets: 7.7–12.8%). P(at least one fails) = 0.925, not the 0.997 claimed in the docstring. Correct the docstring.
- **P3-1.** The exactness count of 33 is deterministic (enumerated at q = 8). Across 10 other world sets it ran 22–32, and none of the 11 left 13–37. Expect about a 1-in-20 chance that a reseed trips it. If the worlds change, re-centre on the theoretical maximum of 4.69%.
- **P3-2.** The attribution guard at h15 does not test the gate: B18, B20 and a skipped BH all pass it. The UNCONFIRMED fast fixture catches all three. Only the spread z² ≤ 2.2 bound and "real component still KEEP" have teeth. It is honestly labelled.
- **P3-3.** The spec calls the market-wide 4h coin nested, but the test uses an 87-day block, not 88. The guards assert `judged == 300` but not `q == 8`.
- **P3-4.** Changed-branch coverage in `backtest.py` is 45/46. Missed: `:1398→1399` (`_ic_rand_p` returning None when a setup has no entry time).
- **P3-5.** Design copy:
  - The `few_clusters` sentence, the "inside its own error bar" paragraph and the attribution legend lack "before costs" / "one replay of past prices".
  - The Terminal uses the full sentence, not the short form Design asks for.
- **P3-6.** The suite budget raise from 300 s to 600 s is **justified**: offscreen runs took 445 s and 534 s, and CI's 900 s still sits above it. Record it as a deviation, and update `tooling-baseline.md` ("cap 300 s").

## Rate tests against today's code (gate removed)
| Test | Bound | Gated | Today | Fails on today? |
|---|---|---|---|---|
| headline 1 | ≤24 verdicts / ≤14 beats | 11 / 5 | 24 / 10 | No (at the bound) |
| headline 2 | same | 9 / 5 | 31 / 14 | Yes |
| exactness | 13–37 | 33 | 33 | not designed to |
| 8h per-class guard | ≤34 | 21 | 63 | Yes |
| market-wide h guard | ≤34 | 14 | 30 | No |
| market-wide 4h guard | ≤34 | 24 | 58 | Yes |
| attribution guard | ≤4/24 | 0.8% | 2.5% | No |

The 8h coin reads 7–8% gated across seed sets, close to measure 2's 7.5% bar. The validator should look at it closely.

## Mutation table
45 mutants: R1–R11 (randomisation), B1–B22 (backtest composition, clusters, A15, attribution), C1–C12 (copy and UI). **44 killed; R4 survived.**
- B3 (alpha 0.10) is caught only by the guards.
- B18, B20 and B22 are caught only by the UNCONFIRMED fast fixture.

## Verdict
- Measure 8: met (thin margin; tight against the time cap).
- Measure 9: partly met (docs and placeholder open; do not release).
- Measure 11: met. Add the R4 test before merge.
