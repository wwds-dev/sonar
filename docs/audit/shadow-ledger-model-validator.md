# Model validation: the look ledger and slow resolvers (spec `shadow-ledger.md`, ADR 0002 Amendment 1)

- **Role:** model-validator, read-only, independent of the design, 2026-10-12, before the owner's gate.
- **Read:** `docs/specs/shadow-ledger.md`, ADR 0002 incl. Amendment 1 (:216-250), my earlier
  `shadow-time-stop-model-validator.md` (P1-1, P2-2), `sonar/calibration.py:262-620`, `sonar/core.py:570-636`,
  `sonar/portfolio.py:240-280,385-425`, `tests/test_calibration.py:929-938,1041-1376`.
- **Playbook:** `docs/playbooks/model-validator.md` is `status: baseline` (last-reviewed 2026-10-10): stale by the
  AGENTS.md rule; added nothing beyond the brief and app-context's model-risk checks.
- **Pre-registration:** synthetic books only (V-12 walk model, steep vol 1.3→0.5, no edge unless planted). Nothing
  under `~/Library/Application Support/SONAR`, no `portfolio.json`, no real time-stop outcome read or computed.
- **Scratch** (session scratchpad `mv2/`, nothing written to the repo but this file): `core.py` (V-12 walk copied
  from the tests; `Fill`, an exact HC3 z over fills of the k excluded members as linear / sqrt(quadratic), checked
  against production `calibration.hc3_z`: max difference **3.1e-15** over 1,000 random fills), `q1b.py`, `q1c.py`.
  No numpy in any interpreter here; everything is stdlib and production `sonar.calibration`.

**Verdict:** the design is sound and closes P1-1 and P2-3 for every decided outcome, and P2-2 for transient gaps.
Three gaps stay: a missing ledger restarts history silently (P1-1 below), the robust rule costs measurable power
(P2-1), and the "consistency check" cannot catch a mis-grade (P2-2). The corners are, in practice, the exact
extremes of z.

## Headline numbers reproduced

| Claim | Where | Reproduced | Result |
|---|---|---|---|
| Corners give the slope's exact extremes | spec :79-86, ADR :231-232 | b = Σ(x_i−x̄_N)y_i/Sxx is linear in each excluded y_j, the box is separable, so the max is y_j = top for x_j > x̄_N, −1 below | **supported**, given each member's own barrier R (P3-1) |
| With k = 0 nothing changes | spec :83-84 | k = 0: the corners are the full-cohort z; `full` = `naive` in the same books (q1c) | **supported** |
| Look 1 slips 11-06 → 12-04 at worst; first T on 10-20 | spec :9,77-78 | 2026-11-06 + 28 d = 12-04; 2026-09-22 + 28 d = 10-20 | **supported** |
| No-exclusion size about 6% | ADR :264-265 | q1c "full", 12,000 null books x 4 scenarios: **5.47–6.07%** | **supported** |
| Under 200 KB after a year | spec :161-162 | 912 entries at 330–400 B = **294–356 KB**; 100 look members are **5.9 KB**, not 1 KB | **unsupported** (harmless, P3-4) |

## Verdict per claim

| # | Claim | Verdict |
|---|---|---|
| 1 | The corners bound the slope exactly | Supported (P3-1 caveat: late fills) |
| 2 | For z they are natural extremes, not a proven bound | Supported, and in practice exact (Q1b) |
| 3 | The robust rule changes nothing at k = 0 | Supported; L-13 cannot see its effect at k > 0 (P2-1) |
| 4 | (a) with a limit removes the selection | Partly: removes transient gaps; permanent ones are bounded by the corners |
| 5 | The ledger makes "evaluated once" hold across restarts (S1–S3) | Supported while the file exists; **unsupported** when it goes missing or unreadable (P1-1, P2-3) |
| 6 | Recomputation is a consistency check | Overstated: it reuses the recorded outcomes (P2-2) |
| 7 | `no_risk` is known at entry and unrelated to the outcome | Supported for synchronous fills; P2-4 |

## Q1. The corners

**(a)** Yes for the **slope**, if the mean is over all N members (spec :81 says so; ADR :231 says "the cohort's", which
is the same thing). At x_j = x̄_N the slope does not depend on y_j, so ties do not matter for b.

**(b)** z = (S + c·u)/sqrt(v0 + 2g·u + u'Qu) over the box u ∈ [−1, top]^k. Where the whole box has z > 0, z is
quasi-concave (its upper level sets are second-order cones). So the **minimum** (the side that decides a robust
up-crossing) is at a vertex, and the same holds for the maximum of a negative z. Enumerating the 2^k vertices is
therefore **exact for the robust rule**. The interior only matters for the other end of the displayed range.
`q1b.py`, 150 cohorts × 2 seeds per cell, k = 1..10, n = 45 and 101, excluded = slow resolvers, null and
near-boundary (planted correlation 0.35 at 45, 0.23 at 101), 12,000 cohorts in all:

| | n = 45 | n = 101 |
|---|---|---|
| z below the lower corner at some vertex: median / p95 / max | 0 / ≤ 0.002 / **0.113** (k = 9, null) | 0 / ≤ 0.001 / 0.009 |
| z above the upper corner at some vertex: max | 0.112 (k = 3) | 0.027 |
| Decisions where the corners said "robust" and a vertex did not | **0** of 6,000 | **0** of 6,000 |
| Interior z beyond the best vertex, on the irrelevant side | up to **0.85** (k = 9, planted) | ≤ 0.001 |

The mechanism of the rare gap: a member near the mean confidence barely moves the slope, but its fill shifts the
intercept and with it every residual in the SE. "The corners" is a fair label for **the slope's** extremes. For
the gate, recommend **enumerating all vertices up to k = 12** (a k×k quadratic form, ≤ 4,096 evaluations, cheap)
and falling back to the corners above that. That makes S5 exact at no cost. Without it, state "measured, not
proven" with these numbers. The UI range "z from {lo} to {hi}" understates the far end by up to 0.85 (P3-2).

**(c)** Yes, measurably. `q1c.py`: paired books; exclusions hit slow resolvers only (state `time`, 20.2% of entries),
"random" = independent of R, "loser" = only those with R < 0 (delisting-like). Null 12,000 books, power (corr 0.2)
4,000 books per row. "Full" = the same books with nothing excluded.

| Scenario (mean k at 45 / 101 / 201) | Size: full / declare on rest / corners / vertices | Power: full / rest / corners / vertices |
|---|---|---|
| random, 0.68 / 1.52 / 3.0 | 5.47 / 5.48 / **3.78** / 3.78 % | 72.3 / 70.2 / **62.5** / 62.5 % |
| random, 1.49 / 3.35 / 6.7 | 5.97 / 6.17 / **2.35** / 2.35 % | 72.4 / 67.2 / **48.8** / 48.8 % |
| loser, 0.49 / 1.09 / 2.2 | 6.07 / 6.05 / **4.49** / 4.49 % | 74.0 / 74.6 / **70.5** / 70.5 % |
| loser, 1.11 / 2.45 / 4.9 | 5.83 / 5.93 / **3.10** / 3.10 % | 73.4 / 74.6 / **65.5** / 65.5 % |

Paired Monte Carlo SE of the size drop is about 0.12 pt. The robust rule can only remove rejections, so the size
never rises. At about 3 exclusions per 201 it costs **about 8 points of power** (0.70 → 0.63), and with 6–7 it costs
**18**. Exclusions are cumulative across looks, so look 3 pays the most. Corners and vertices gave identical decisions
in all 64,000 books. A useful property: a hand close (`left`) can now only block a crossing, never make one.

## Q2. Grace 7 → 28 days
- **No statistical downside to the gate.** Membership is fixed by entry order, and the look's z is a function of
  final states only. A hold changes the date, not the value, and no look is evaluated during a hold
  (`shadow_looks` `final`, `calibration.py:483`; look 2 contains look 1, so it holds too). No new look-ahead: a late
  grade still uses the T bar and the cut (`calibration.py:395-411`). A hand close during the hold falls after the cut
  and is graded at T, so it gives no lever. The fetch range still reaches back: week 56 + 7 d → "3mo"; month 147 →
  "6mo" (`core.py:141,630-636`).
- **(a)-with-limit-then-(b) is better than (b) alone.** Under (b) alone, with the ledger, every transient gap becomes
  a permanent, outcome-speed-selected exclusion. It then also costs power under the robust rule (Q1c).
- **28 is acceptable. The real gap is that the limit counts calendar days, not attempts (P2-5).**

## Q3 and Q4
- **Ledger:** it closes P1-1 and P2-3 for decided outcomes. The gaps are P1-1, P2-2, P2-3, P2-6 and P3-3 below.
- **`no_risk`:** sound. It is known at fill, does not depend on the outcome, and is decided at once, so it adds no
  selection. P2-4 has two corrections.

## Findings

### P1-1. A missing ledger silently restarts the record
Spec :153: "File missing: start empty". A moved `SONAR_DATA` (it moved once already, v2.130), a new Mac, a restore
without the file, or a deletion: the holder re-decides every outcome from that day's closes and re-evaluates every
look. It records the new values with a **new** "Recorded {date}", and nothing is flagged. That is exactly the P1-1
failure the ledger exists to stop, and S1 ("same date it was first evaluated") breaks without a trace.
**Fix:** write a marker the first time the ledger is created (for example `shadow_ledger_id` + `created_at` in
`portfolio.json` or the settings file). "Marker present, file missing" is `ledger_error: "missing"`, never a fresh
start. Also point recovery at `daily_backup`. Add a test (an L-15: delete the file, restart, expect an error, not new
records).

### P2-1. The robust rule costs power. The ADR should state it, and a test should pin it
See Q1(c). This is the honest price of a worst-case bound on [−1, top], and I recommend keeping the rule. But the
ADR's power table (0.73 at 0.2, ADR :101) holds only with **no** exclusions. Add to Amendment 1: "each exclusion
lowers power; about 3 per 201 → about 0.63". L-13 runs V-12 with k = 0 and so cannot see the rule. Add a V-12
variant with seeded exclusions (q1c "random, 3 per 201") that pins size ≤ the no-exclusion size and power ≈ 0.62 ± 3 SE.

### P2-2. The consistency check cannot catch a mis-grade
Spec :141-146: ledger entries join `decided`, and `shadow_time_stop` deep-copies decided entries without
recomputing (`calibration.py:565-569`). So "recomputing" a recorded look reuses the recorded R values. It can only
find changed membership, changed constants, or a `no_price` member that has since been graded. A wrong T bar, a bad
tick or a restated close is never found. ADR :224-225 ("Recomputation continues as a consistency check") overstates
this. Either call it a "membership and constants check", or add an opt-in fresh re-derivation that bypasses
`decided`. That costs a fetch per symbol and needs the P1-2/P2-3 guards.

### P2-3. Ledger read failure shows recomputed looks as results
Spec :154-156: on `ledger_error: "read"` the pass "runs as v2.260 does". It then shows evaluated looks, and possibly
"crossed … the test ends here", computed from today's closes. That is the P1-1 behaviour, precisely when the record
is unavailable. The same applies to a look evaluated in a pass whose write fails (:157). **Fix:** a look is shown as
a result only once it is recorded. Otherwise show "worked out, not recorded" and suppress the crossing and
design-closed wording.

### P2-4. `no_risk`: keep it out of the corners, and test signed risk
- The ADR amendment puts `no_risk` into the corners (:230: "`no_price`, `left`, `no_risk`"). The spec gives the
  corner set as `no_price` and `left` only (:87). These contradict each other. A `no_risk` member has no R, so a
  fill of +top / −1 has no meaning, and it is not outcome-selected. Including it only costs power (Q1c). Exclude it
  from the corners.
- `risk = abs(p.entry - p.stop)` (`calibration.py:448`) is 0 only when the fill equals the stop exactly. An async
  fill rewrites `entry` and keeps the stop (`portfolio.py:391-420`). A fill **beyond** the stop gives risk > 0 with
  inverted barriers (LONG entry 99, stop 100: R at the stop = +1). Define `no_risk` on the signed distance,
  d·(entry − stop) ≤ 0. It is equally known at fill. This is latent while the broker is synchronous.

### P2-5. The grace counts calendar days, not attempts
`no_price` is decided when `now ≥ t_T + grace` and that pass's bars cannot decide (`calibration.py:440-447`). After a
restart the bar cache is empty, and a failed fetch is cached as failed for the UTC day (`core.py:608-626`). Holder
off for 4 weeks, then one failed fetch on restart, and the member is a final exclusion frozen into the look. Make it
final only when **both** 28 days have passed **and** fetches on at least 3 distinct UTC days after t_T + 7 d failed
to decide. That needs a per-entry attempt count in the ledger. Keep the limit at 28: the cost is a delay of at most
21 days, only for a permanently missing price.

### P2-6. Pre-register the correction policy now
Spec :179-181 defers a correction to "a written amendment and a new ledger entry type". Choosing the rule after an
outcome is seen is a forking path. Decide it now: the recorded look stays the design's result. An erratum (id,
reason, corrected R, date) is shown beside it and never changes `crossed` or `design_closed`.

### P3
1. **The barrier values are per member.** Use each member's own barrier R in the corners: d·(target − entry)/risk
   and d·(stop − entry)/risk. These equal +rr and −1 only when the fill equals the plan entry (`portfolio.py:418`).
   Store both in the entry.
2. **Wording.** "If the {k} left out had all gone the other way" is wrong: the corners are the best and worst cases
   for the score, not "the other way". Suggest: "If the {k} left out had come out as well or as badly as they could
   for the score: z {lo} and {hi}". Do not use "from … to": the far end is not a bound (Q1b, up to 0.85).
3. **What to store.** Per entry, add `entry`, `stop`, `target`, the T-bar stamp, `t_cut`, the source (book / gap /
   bar), `closed_at`, and the attempt count (P2-5). Without entry and stop a stored R cannot be audited. Per look
   member, add the barrier values and the corner fill. To `constants`, add `SHADOW_SPLIT_GUARD`, the per-preset T in
   days (from `horizon.momentum_days`, not covered by `t_horizons`), and a `rules` version (rule order, HC3, robust
   rule, corner or vertex method). Optional: a SHA-256 of each look record in the CHANGELOG, as tamper evidence.
4. **Size.** About 0.3–0.36 MB a year, and look members about 6 KB per 100 (spec :161). Correct the figure. The size
   itself is no concern.
5. **Specify cross-look states.** A `no_price` member stored only inside look k (spec :138-139) can be graded in a
   later look. That is acceptable, but specify it and test it.
