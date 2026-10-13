# Model validation: time-stop shadow readout (ADR 0002), build at cca9428

- **Role:** model-validator, read-only, independent of the build, 2026-10-12. Saved by the orchestrator
  from the agent's report.
- **Scope:** `git diff cf84642 HEAD`: `sonar/calibration.py:238-541`, `sonar/core.py:500-565`,
  `tests/test_calibration.py:179-818`, `ui/app.py` `SHADOW_WORDS` (from :476) and `shadow_texts` (from :766).
- **Playbook:** `docs/playbooks/model-validator.md` is `status: baseline` (2026-10-10): stale; added
  nothing beyond the brief and app-context's "Model-risk checks".
- **Pre-registration:** synthetic books only; nothing read the real `portfolio.json` or a copy; no
  time-stop outcome computed for the real book.
- **Network:** blocked in the sandbox (`assets.fetch_bars` → None for BTC-USD, EURCHF=X, ^GSPC, AAPL);
  live bar stamps not checked.
- **Scratch scripts** (import production `sonar.calibration`; nothing written to the repo): session
  scratchpad `mv/` — `s1_instability.py`, `s2_null.py`, `s3_calib.py`, `s4_mutants.py`, `s4b_slow.py`,
  `s5_geometry.py`, `s6_n400.py`, `s7_end2end.py`, `pocock.py`, `tdist.py`.

**Verdict:** the statistics are sound and faithful to ADR 0002, but two claims are not supported as
built: "5% false positives" (real size ≈ 6.0%) and "each look evaluated once" (looks are recomputed each
pass from re-fetched bars and can change after first shown). Both need owner decisions before release,
and in any case before the first entry reaches T (2026-10-20).

*Orchestrator notes:* the owner accepted the ~6% size and chose not to amend ADR 0002 (2026-10-12)
before this report arrived. P1-1 and P1-2 are in the engineer's fix loop 1 (keep last good bars, an
in-memory memo of decided outcomes, never decide from the newest bar, ignore future stamps); the
persisted ledger (P1-1 b) and the t(n−2) reference (P2-1) are owner decisions.

## Headline numbers reproduced from raw simulation

| Claim | Source | Reproduced | Result |
|---|---|---|---|
| Pocock 2.315 at 45/101/201 holds 5% overall | ADR §3 | 4,000,000 normal paths, rng 20261012: **5.019%** (2.289 → 5.36%, 2.33 → 4.84%) | supported for normal z |
| Quick V-12 null 6.5%; spec slow null 5.35%; closed-only 13.6% at n ≈ 194 | engineer | test helpers and seeds: **6.50%**, **5.35%**, **13.6%**; slow power 0.741 | supported (exact) |
| Design size ≈ 6.2% (20k books) | engineer | fresh numpy walks, 40,000 books, production `shadow_looks`/`hc3_z`: **6.02%** (SE 0.12; 95% 5.78–6.25) | supported |
| Power 0.73 at correlation 0.2 | ADR §3 | 10,000 books: **73.07%** | supported |
| Reference split at 4 horizons 37.4/57.4/5.2 | ADR §2 | function 0.3743/0.5743; MC with 500 marks/horizon 37.3/56.9/5.8 | supported for continuous monitoring (P3-2) |
| Rank IC not zero-centred; HC3 rejects 2.8–3.3% at 2σ, n = 400 | ADR §3 | sims script reproduces at 400 books; at 10,000 books rank IC mean +0.025 rejects **7.73%**, HC3 **4.58%** (nominal 4.55) | rank-IC bias supported (larger); the HC3 2.8–3.3% is 400-book noise |

## Verdict per claim

| # | Claim | Verdict |
|---|---|---|
| 1 | T = 28 d on week, frozen and pinned | **Supported** (`calibration.py:261,275-278`, V-14) |
| 2 | §4 order, T bar, cut | **Supported** as written (`calibration.py:335-400`); see P3-4 |
| 3 | No look-ahead | **Partly**: holds only if bars are stamped at session start; fails when the in-progress bar carries the fetch time (P1-2) |
| 4 | No censoring by construction | **Supported with full data**; Build note 1 correct. **Unsupported** once exclusions occur (P1-1, P2-2) |
| 5 | Gate = HC3 slope z, as the sims | **Supported** (`calibration.py:307-332`; identity test `test_calibration.py:540`) |
| 6 | Pocock 2.315 keeps the design at 5% | **Unsupported for HC3 as built**: ≈ 6.0% (P2-1) |
| 7 | Each look evaluated once | **Unsupported** (P1-1, P1-2, P2-3) |
| 8 | Power 0.73 at 0.2 | **Supported** |
| 9 | Read-only (V-11, V-15) | Not run; code reading agrees (pure function; engine passes copies, `core.py:513-516`) |
| 10 | V-12 kills rank IC, naive SE, T = ∞, 1.96 per look | **Partly**: only 1.96 by V-12's size check (P3-1) |
| 11 | Wording statistically accurate | **Partly** (P2-4) |

## Findings

### P1-1. A single failed daily fetch rewrites an evaluated look
- **Mechanism:** `_shadow_fetch` caches a failed fetch for the UTC day as None (`core.py:550-556`);
  `_shadow_entry` (`calibration.py:378-385`) then marks every member with `now ≥ t_T + 7 d` not settled
  before T as `no_price` at once; graded entries never stop needing bars (`shadow_needs_bars`,
  `calibration.py:295-304`); younger members fall back to `wait_price` and the look reverts to "Not a
  test yet".
- **Evidence** (`s1_instability.py` A, 45 entries, seed 1):

  | Fetch state | evaluated | used / excluded | z |
  |---|---|---|---|
  | All succeed | True | 45 / 0 | −0.361 |
  | All fail today | True | **22 / 23** | **−0.977** |
  | One symbol in three fails | True | 38 / 7 | −0.521 |

  The 22 left are exactly the quick resolvers — the censored sample the ADR removes — and the look still
  says "evaluated". Near ±2.3 the UI could show "crossed … The test ends here" one day and not the next.
- **Options** (owner): (a) keep last good bars on failure — fixes the in-run case, not a restart;
  (b) **recommended:** a write-once look ledger under `SONAR_DATA` (k, time, z, used, n_excluded, member
  ids with state and R, build version), shown from then on, recomputation as a flagged consistency check
  — the only way "evaluated once" becomes true; covers P1-2 and P2-3; **needs an ADR 0002 amendment**
  (§7, "nothing persisted"); (c) the owner records each look in CHANGELOG when first shown — weak.

### P1-2. An in-progress bar stamped at fetch time moves the T bar
- "The T bar counts only once a later bar exists" (`calibration.py:346-349`) assumes session-start
  stamps; ADR §5 recorded EURCHF=X's in-progress bar stamped at fetch time (02:55 UTC); Yahoo is known to
  return a separate "live" row beside the session row (not checked live).
- **Evidence** (`s1` B, t_T = day 28 15:00): B1 day-28 bar in progress stamped 16:00 → T bar day 27,
  cut 16:00 → `time`, exit 99.0, R −0.50 (a close from before t_T); B2 next day restamped 13:30 → `time`,
  exit 101.0, R +0.50 — flips; B3 session row plus separate live row → the in-progress session row taken
  as final, exit 101.2 (V-6's mutant via data shape).
- **Option (code, no ADR change):** ignore bars stamped within ~24 h of `now`, or whose time of day
  differs from the series' usual stamp; require the bar after the T bar to be a completed session.

### P2-1. Real design size ≈ 6.0%, robust across live-like features
Production `hc3_z`/`shadow_looks`; scenarios A–I 40,000 books each (seeds 7000+); end-to-end 12,000
books each (seeds 4242–4249, 4342–4349).

| Scenario | Design | Per look | t(n−2) reference | Look 1 at 2.45 / 2.50 |
|---|---|---|---|---|
| A. Steep 1.3→0.5, 20 marks/h | **6.02%** | 2.70/2.36/2.26 | 5.38% | 5.46 / 5.31 |
| B. Flat vol | 5.99% | 2.77/2.37/2.16 | 5.41% | 5.44 / 5.26 |
| C. Mild 1.0→0.6 | 5.88% | | 5.36% | |
| D. Daily marks (5/h) | 6.05% | | 5.50% | |
| E. Crypto (5/h, 5.6 h) | 5.73% | | 5.17% | |
| F. Live score mix (29/16/7) | 6.02% | | 5.47% | |
| G. Daily marks, t3 increments | 6.12% | | 5.47% | |
| H. Composite (daily, t3, live mix, 15% crypto) | 5.78% | | 5.12% | 5.18 / 5.04 |
| I. Rising vol | 6.02% | | 5.41% | |
| **End-to-end through `shadow_time_stop`**, steep (30-min polls, 5% stalled days, overnight gaps, weekends, Yahoo-style stamps, gap check) | **6.13%** (95% 5.70–6.56) | 2.83/2.33/2.22 | 5.48% | |
| End-to-end, flat | 6.06% | | 5.45% | |
| Gaussian homoscedastic y, uniform x | **5.65%** | 2.48/2.16/2.11 | **5.02%** | |

- **Cause:** mostly generic (an estimated SE compared with the normal line; Gaussian errors alone give
  5.65%); R's point masses and skew add ~0.4 pt. First-crossing rates 2.7/1.9/1.4% vs 2.06/1.57/1.40%
  for exact normal z: about two-thirds of the excess at look 1, one-third at look 2.
- **Options** (each changes the boundary → ADR amendment):

  | Option | Size | Power at 0.2 | Comment |
  |---|---|---|---|
  | Accept and disclose | ≈ 6% | 73.1% | ADR table, code comment, spec and manual say "about 6% in simulation" |
  | **t(n−2) reference: lines 2.404 / 2.353 / 2.334** (same per-look p = 0.0206) | 5.0% Gaussian; 5.1–5.5% all scenarios | 72.2% | standard, not tuned to a sim. **Recommended by the validator** |
  | Look 1 only at 2.45 (2.50), later 2.315 | 5.0–5.6% | 72.8% (72.7%) | simple, ad hoc |
  | Wild bootstrap (Rademacher, 499) at look 1 | look 1 exact; overall 5.0–5.4% | not measured | adds randomness and code; not worth it |
  | A constant calibrated to these sims | 2.35–2.41 by scenario | 71.5% at 2.36 | lets the sim pick the line; not recommended |

- The validator recommends adopting t(n−2) by amendment now, while no outcome exists (first entry
  reaches T 2026-10-20; running z values appear from 20 results; a later change would be made after
  looking). UI strings hard-code "±2.315". V-12's precision band would need teeth (≤ 6.0% now, ≤ 5.75%
  after an amendment). *Owner decision taken 2026-10-12: accept ≈ 6%, no amendment.*

### P2-2. Exclusions select by outcome speed
`no_price` can only hit entries not settled before T (slow resolvers); barrier hits before T need no
price (`calibration.py:369-377`); delisting, the likeliest permanent cause, is outcome-related. The count
and a > 10% warning are shown, but a look still declares on the rest. **Options:** a look with any
`no_price` member is not evaluated until resolved; or show a sensitivity bound (z with excluded members
at R = −1 and at R = +1.5). The `risk ≤ 0` case is also filed under `no_price` (`calibration.py:392-393`).

### P2-3. A split restates history and rewrites graded entries
`fetch_bars` uses Yahoo's `close` (`assets.py:292`), believed split-adjusted (not verified). `s1` C: a
2:1 restatement after T turns a LONG from `time` R +0.25 into a gap `stop` R −1.00, and a SHORT from
−0.25 into a gap `target` +1.50. **Option:** if the close nearest `opened_at` differs from `p.entry`
beyond a tolerance, or Yahoo reports a split, call it `no_price` (labelled); combine with the ledger.

### P2-4. Wording (`ui/app.py` `SHADOW_WORDS`)
- **`SH_FINAL_NONE`** "no evidence that the score ranks 4-week results, at the planned size" overstates a
  negative (the final z could be +2.2; the design misses a correlation of 0.1 with probability 0.77).
  Suggest: "not enough evidence that the score ranks {T_adj} results. At the planned size the test could
  reliably find only a link of about 0.2 or more."
- **`SH_LOOK_NOT_CROSSED`** "no clear link between score and result" reads as absence (look 1's line ↔ a
  correlation of 0.35). Suggest "no link strong enough to cross the line yet".
- **`SH_LOOK_CROSSED_UP/_DOWN`**: suggest "on average, …".
- **`SH_CAVEAT_CROSSED`** omits that a crossing happens under no edge at the design's false-positive
  rate. Suggest "This is evidence, not proof, that…".
- **"Not a trading edge"** is correct and needed: coin-flip direction cancels drift only to first order.
  `s5_geometry.py` (seed 5, 400k paths each): mean R +0.023 / +0.036 / +0.076 / +0.163 at drift 0 / 0.25 /
  0.5 / 1.0 σ per horizon — a score that picks trending instruments, in either direction, can cross
  upward with no directional skill. The manual §10 should say so (tech-writer).
- "no costs", "running, not a test" and "for comparison only, not a test" are accurate.

### P3
1. **What V-12 tests:** production `shadow_looks`/`hc3_z` on hand-built `{state, r}` dicts; never
   `shadow_time_stop`, `_shadow_entry`, `_shadow_from_bars`. Mutants (`s4_mutants.py`, `s4b_slow.py`):
   rank IC as gate — null 5.6% (passes), power 0.998 (fails, incidental); naive OLS SE — 4.60% / 4.65%,
   power 0.710 / 0.731, **survives V-12**; HC0 — quick 7.30% passes, slow 6.70% kills; 1.96 per look —
   14.1%, killed; T = ∞ — out of V-12's reach (V-14, V-2 see it). As a suite all die (identity test,
   V-14), but the spec's V-12 kill list is overstated. Suggest an end-to-end null through
   `shadow_time_stop` (as `s7_end2end.py`), slow-marked.
2. **Reference split assumes continuous monitoring and a correct σ̂:** under no edge the "neither" share
   is 9.1% at 20 marks/horizon and 13.7% with daily marks (vs 5%); discrete-mark barrier fills give a
   no-edge mean R of +0.021 / +0.039 / +0.047 at s = 0.5 / 0.9 / 1.3 (daily marks) — ~0.1 z at n = 201,
   negligible for the gate. `SH_ROW_REF` should say "if the volatility estimate is right".
3. **Costs:** "a constant cost moves mean R, not the slope" holds only for a cost constant in R units; a
   spread in bp costs ~1/σ̂ in R, so if score correlates with σ̂ costs tilt the slope. Interpretation only.
4. **Rule 1 before rule 2 is not a stopping rule:** a missed stop-crossing daily close is overridden if
   the book later books TARGET before T, kept if not — depends on the future. Tiny bias (stall plus a
   2.5σ reversal). Fix would be an ADR change (earlier of book barrier time and first daily-close crossing).
5. **Running figures lean briefly on quick resolvers:** barrier-before-T entries graded at t_T, open ones
   wait 1–7 days for a final bar; looks unaffected. Fix: grade everything from the cut.
6. **Pending fills keep their acceptance `opened_at`** (`portfolio.py:414-421`): a late fill could insert
   into an evaluated cohort. Latent (the internal broker is synchronous).
7. **ADR §3's "HC3 2.8–3.3% at n = 400"** should read ≈ 4.6% (10,000 books); the rank-IC bias is
   stronger than stated (7.7%).
8. **Sample-size context:** at look 1 (n = 45) the 95% interval on mean R is about ±0.32R (sd ≈ 1.1), and
   the correlation needed to cross is 0.35.

## Q1: faithfulness to ADR 0002 §1–§5
T, rule order, T bar and cut, exclusions and R match the ADR (`calibration.py:261-400`). Build note 1
(grade only from t_T) is correct. The gap window is right and conservative. No look-ahead to the next
bar with regular stamps (V-7). Look-ahead and finality fail under fetch-time stamps (P1-2); survivorship
and censoring come back through `no_price`, transient (P1-1) and permanent (P2-2).

## Q3
Serious for the pre-registration claim, more than reported: one routine failed fetch suffices; splits and
restamped bars also rewrite results. Recommend the write-once look ledger (ADR amendment) plus keeping
last good bars, both as a condition of release.

**Verdict:** the gate statistic and design are implemented faithfully and reproduce, but the false-positive
rate is ≈ 6%, not 5%, and "each look evaluated once" does not hold as built. Fix P1-1 and P1-2 and have
the owner decide P2-1 before release and before 2026-10-20.
