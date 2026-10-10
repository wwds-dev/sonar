# SONAR internal audit — summary (2026-10-10)

Eight read-only audits, run by role agents against commit `6424857`. Reports: `ux.md`,
`architecture.md`, `code-review.md`, `qa.md`, `security.md`, `model-validation.md`,
`operations.md`, `docs.md`. Findings come from agents; the ones marked **R** were reproduced by
running the repo's code, **2×/3×** were found independently by that many auditors. Nothing here has
been fixed. Owner approval is needed before any of it goes into `TODO.md`.

## Verdict by goal
| Goal | Verdict | Why |
|---|---|---|
| Keep running as a personal paper-trading tool | **Go, with the 5 fixes in Tier 0** | Suite green (1,582 tests, 80% branch), barrier math and research pipeline sound, no secret leaks, loopback-only. But the book can be silently overwritten or corrupted. |
| Public v1.0 | **No-go** | Tier 0 and Tier 1 open; model claims overstated; unsigned/un-notarized app; no monitoring; first-run UX has a P0. |
| Real money | **No-go, not in scope** | No edge shown (own Brier: model 0.1686 vs market 0.1639, t=0.84); execution guard fails open on NaN and on audit-log write failure; Alpaca broker unguarded and unfinished. |

## Cross-confirmed headline issues
1. **Lock hand-off overwrites the book (P0)** — architecture P0-1 + code P0-1 (**R, 2×**). Window takes
   over from the agent with the state it loaded at launch; first save wipes the agent's trades.
2. **Unlocked multi-thread writes to the book (P1)** — architecture P1-2 + code P1-3 (**R, 2×**):
   double-credited cash, `ValueError`, shared `.tmp` filename collisions.
3. **Silent engine/agent failure with no alarm (P0 ops)** — operations (code-read only). Engine on a
   daemon thread; staleness computed at snapshot time; errors swallowed; nothing alerts the owner.
4. **Calibration is statistically meaningless at n=20 and miscounts MANUAL closes** — code P1-5 (**R**)
   + model-validation P1-1b, 2×. 19 closed trades, 6 wins; the next close turns on a "measured edge" that
   rewrites P(profit) on all 129 rows. MANUAL exits count as target hits.
5. **Shipped hourly σ is not the validated estimator** — model-validation P1-1 + code P2-1, 2×. On real
   data the shipped form is significantly worse than the studied one (QLIKE +0.043, CI [0.020, 0.065])
   yet still beats the trailing-72 baseline by ~6.7%. The documented "+7.5%, 6/6" belongs to a different formula.
6. **Local API open to any web page** — security P1-1 (confirmed live), architecture P2, code P2-10, 3×.
7. **Nested repos `macro`/`playmaker` unpinned and gitignored; CI points at a different GitHub owner** —
   architecture P1-4 + operations, 2×.
8. **Stale-lock reclaim is a race** — architecture P1-3 + code P3-8, 2×.
9. **Docs contradict themselves and the evidence** — docs audit (6 P1) + model-validation: study count
   (5 vs 6), "6 of 6 blocks" (5 of 6 on fresh data), "thin statistical edge" (own Brier disagrees),
   "measured" costs (circular), "bps per side" (really 2×).

## Tier 0 — fix before anything else (data loss / money-shaped bugs)
| ID | Issue | Source |
|---|---|---|
| T0-1 | Reload engine+book after lock takeover; no saves without the lock; test it | code P0-1, arch P0-1 |
| T0-2 | Locking for `Portfolio`/`Engine` mutators and saves; unique tmp names | code P1-3, arch P1-2 |
| T0-3 | Warm-up P&L must not enter live bankroll/headline P&L/Kelly sizing | code P1-1 (R) |
| T0-4 | Stale/older candle must not void a live position or drop the snapshot | code P1-2 (R) |
| T0-5 | Forced close/equity on hidden symbols: use last known price, never entry | code P1-4 (R) |
| T0-6 | Engine health: restart on thread death, `/api/health`, log swallowed errors, an alarm | ops P0 |
| T0-7 | Host/Origin/content-type checks + token on POST routes; body-size cap; reject non-dict JSON | security P1-1 |

## Tier 1 — before any public release
- **Honesty of numbers:** calibration only grades TARGET/STOP, gated on a CI excluding baseline (T1-1);
  ship the validated σ formula or re-run the study on `forecast()` (T1-2); fix `version.info` KeyError
  (P2-11, unstamped bundle can fail to start) (T1-3); exclude UNCLEAR from LLM calibration (T1-4).
- **Feed correctness:** locale-independent slug and the DST fall-back fix **before 2026-11-01**
  (code P2-5/P2-6) (T1-5); partial/stale hourly history guard (P2-2) (T1-6); move `_rescan`/macro off
  the poll thread and `Live.lock` (P2-3/P2-4) (T1-7).
- **Security:** NaN/inf in execution guard + fail-closed audit write (security P1-2, P2-1); re-sign
  after `plutil` / notarize (P2-2); escape LLM output and headlines (P2-3/P2-4) (T1-8).
- **Ops:** off-machine backup and a tested restore; pin dependencies and nested repos; fix CI repo owner;
  macOS CI job; agent availability when logged out/asleep (T1-9).
- **UX:** status line hidden below 1420 px (UX P0); first-run "start here" and loading states; keyboard
  and accessible names; one-click Buy/Short/Close needs confirm/feedback (T1-10).
- **Docs:** reconcile study count, instrument count, stale "Docs" button, API table, Layout section;
  correct the overstated claims listed above (T1-11).
- **Tests:** `llm.py` reader paths (30%), flat-hour scoring boundary, buyability band edges, execution
  flatten error paths; fix the `MainWindow already deleted` teardown error (T1-12).

## Tier 2 — hardening / debt
Statistical-power rewording ("not detected; ≥~3 pts not excluded"); survivorship disclosure;
deterministic `random_control`; backtest SE/null bias; quintile tie-breaking; cost label ("per side");
~1,500 lines of unreachable code; oversized `ui/app.py` (3,698 lines) and `Live` (925 lines); state
schema version; news keyword false positives; Dixon-Coles neutral-site; remaining P3s in each report.

## Caveats
- Operations and architecture findings were read from code only; code review reproduced several (R).
- Not verified by anyone: whether CI is a required check; whether the existing gdrive-backup job covers
  the SONAR data dir; the CI owner mismatch (no GitHub access).
- Model-validation and code-review differ on magnitude of the σ gap (real data vs synthetic). Use the
  real-data number; either way the claim does not hold for the shipped code.
- The two auditors that could write files were told not to touch code; the other four reports were saved
  by me from their returned text.

## Proposed next step (needs your approval)
1. Approve this summary (or strike items).
2. I add Tier 0 and Tier 1 to `TODO.md` with P-levels and `@ai`/`@me` owners; `@me` items are
   Developer ID/notarization, backup destination, and legal/disclaimer review.
3. Run `/ship-feature` on **T0-1 through T0-5 first** (small, reproduced, testable), starting with T0-1.
