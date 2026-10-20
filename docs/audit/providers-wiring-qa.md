# providers-wiring: QA verify (2026-10-19)

Reviewer: `qa-engineer` (read-only). Saved by the orchestrator. The playbook is stale (`status: baseline`).

**Verdict: pass.** All six measures hold, and 5 of 5 targeted mutants were killed.

| # | Measure | Result |
|---|---|---|
| 1 | No false claims: the phrase grep returns no hits; CoinGecko and Frankfurter appear only in "are not used" (README:194) | Pass |
| 2 | Finnhub status in one place (README:192-195) | Pass |
| 3 | Backlog true: TODO:98 P2 rewire, SUGGESTIONS #1 DEFERRED | Pass |
| 4 | Module gone; `grep -rn providers sonar ui main.py scripts` returns nothing | Pass |
| 5 | Run untouched: no diff to assets, backtest, core or plist | Pass for the code; the agent not being restarted is not verified |
| 6 | Result records name their source (v1-product:53-54, CONFIDENCE:357,359) | Pass |

## Mutation
- **Killed (5 of 5):** the "skipped provider" claim, the fallback row, a `providers` import, the outage clause removed,
  and the `FINNHUB_API_KEY` line.
- **Gap probe M6 survived, as expected:** a reworded claim ("switches to Finnhub automatically") passes the phrase list.
- All files were restored and checked with `shasum -c`.

## Suite
- Native (`./run-tests.sh -q`): 1 failed, 3212 passed, 3 skipped (241 s).
- Offscreen (`QT_QPA_PLATFORM=offscreen ./run-tests.sh -q`): same result (496 s).
- The only failure is the expected v2.366 newest-entry-ahead check.

## Findings
- **P3-1.** A reworded fallback claim gets past the phrase list (M6). This is a documented limit; the reviewer is still
  the guard.
- **P3-2.** "is the fix" and "highest-value" are checked in TODO.md, so an unrelated backlog line would fail the suite
  (same as code review P2-1).
- **P3-3.** The exact-sentence checks are brittle.
- **P3-4.** Weak checks: `SEED_* > 0` is always true, and the CoinGecko "not used" check is loose.
- **P3-5.** Not related to this change: the offscreen run took 496 s against the 600 s watchdog.
