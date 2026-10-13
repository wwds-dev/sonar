# Tech-writer, Document phase: time-stop shadow readout

2026-10-12, branch `claude/zealous-mclaren-8985d0`. Docs only; no code changed. Playbook
`docs/playbooks/tech-writer.md` is `status: baseline` (last-reviewed 2026-10-10), so it is stale and
added nothing beyond `AGENTS.md`. Nothing was computed for the real book; no time-stop outcome was
produced. The only maths run was `scoring.barrier_probabilities_within(1.5, 1.0, 4.0 / 5.6)`, which
needs no data.

## What changed
| File | Where | Change |
|---|---|---|
| `CHANGELOG.md` | :15 | Entry under "Unreleased (not installed)": why the closed-only grade leans on quick resolvers; the fixed-date result in R; three looks at 45 / 101 / 201 against ±2.315; "Not a test yet" and the running line; the entry-date row; exclusions counted; paper, coin-flip direction, before costs, fees and slippage, exact fills, not a trading edge; computed in memory on each scan, nothing on disk; a follower shows the agent's copy, an older agent gives "Not available from the running agent"; no exit, odds or existing-grade change. No version bump (VERSIONING.md). |
| `static/docs.html` | :941–1022 | Manual §10 sub-heading "A second grade: every entry at a fixed date" (Design D8): why closed-only grading leans on quick resolvers; the fixed-date rules in order; R defined; z, the three looks and the line at 2.315, "crossing the line" = a link strong enough that chance alone would rarely produce it; running line and rank-IC row; "what no edge would give" as a volatility check (37 / 57 / 5 at the target / stop / neither); exclusions and the "Note:" warning; the caveat callout (:1005) with model-validator P2-4's trending-instrument point; where it is computed (:1015). No false-alarm rate anywhere. |
| `README.md` | :49, :52 | The landing and My trades rows name the second grade (manual §10 pointer; by score band on My trades). |
| `docs/specs/shadow-time-stop.md` | :8–15 | Status/Next: Build, Review, Verify, Secure, Document done; Release (owner gate) next, with the slow suite, TESTPLAN 11.23 and the `SH_FINAL_NONE` call. |
| same | :21–23 | The "Dependency, not landed" note marked as landed in `231540b`, before Build (checked: `git merge-base --is-ancestor 231540b cca9428`). |
| same | :530–560 | Build note 16, code review r4 P3-A: "up to 3 days longer"; the 2.3 d grace scoped to session-start stamps on US bars; the last-trade US-holiday worst case (5.4 d, 5.7 d at 07:00, 1.3 d left) and ^N225/^KS11 with fetch-time stamps (a day more; Golden Week Friday T 6.73 d, 0.27 d left); why the margin matters (`no_price` final in a look, not memoised); ^N225 added to the live check. |
| same | :668–714 | New "Known limits": QA r4 P3-4 (crypto 00:00:00 restamp), the grace margin, the residual wrong close; owner questions MV P1-1 b (look ledger), P2-2 (`no_price`), P2-4 / domain P3-3 (`SH_FINAL_NONE`), P3-4 (rule 1 before 2), P3-6 (late fills), P3-7 (ADR §3 HC3 figure), each with its report. |
| `TESTPLAN.md`, `static/testplan.html` | 11.15, 11.21, 11.22, 11.23 | 11.15 covers the "first gets there on …" and "waiting for a closing price" states; 11.21 "how many", not "which", entries wait (the string gives a count); 11.22 adds the "(k with no readable date)" suffix; 11.23 adds ^N225 and replaces "either answer is safe" with the correct-but-slower wording (P3-A). Page regenerated with `scripts/build_testplan.py`. Count line (2,399) unchanged. |
| `TODO.md` | :79, :84–109 | P1 shadow item updated to "Release next". Added: `SH_FINAL_NONE` decision (P2 `@me`), live weekend stamp check incl. QA r4 P3-4 (P2 `@me`), first-look success measure 11.21 (P2 `@me`), security P3-1, P3-2 (P3 `@ai`), security P3-4 (P3 `performance`), domain r2 P3-5 to P3-7 (P3 `@ai`). Existing items for MV P1-1 b, P2-2, P3-4, P3-6, P3-7 left as they were (no duplicates). |

## What was checked
- Every manual and CHANGELOG claim against the code: `SHADOW_WORDS` (`ui/app.py:480-603`),
  `SHADOW_STALE_H` 26, `SHADOW_RUNNING_FROM` 20, `SHADOW_WARN_SHARE` 0.10 (`ui/app.py:604-610`);
  `SHADOW_T_HORIZONS`, `SHADOW_LOOKS`, `SHADOW_BOUNDARY`, `SHADOW_PRICE_GRACE_DAYS`
  (`sonar/calibration.py:262-267`), `shadow_t_days` (:291), zero stop distance → `no_price` (:448-455),
  the returned counts (:595-619); the pass runs on each scan (`sonar/core.py:355`); panel headings
  (`ui/app.py:2465`, `:2638`); ^N225 and ^KS11 in the universe (`sonar/assets.py:115`, `:121`);
  `test_r2_latency_*` exist (`tests/test_calibration.py:593`, `:608`).
- TESTPLAN 0.9 and 11.14–11.23 read against the shipped strings; 0.9's "22 passed" matches
  `pytest -m slow --collect-only` (22). 11.14, 11.16–11.20 needed no change (11.16's sum matches the
  states in `calibration.py:286-288`).
- Word scan of the new manual text and the CHANGELOG entry: none of will, should, buy, sell, expect,
  likely, going to, bullish, bearish, profit, certain, guarantee, promised, advertised; no "6%"; the only
  "5%" is the reference's "5% at neither". Markup of the new section balanced (html.parser).
- Tests (scratch `SONAR_DATA`): `tests/test_docs.py test_wording.py test_version.py test_shadow_ui.py
  test_learn_tab.py test_testplan_page.py test_landing_figures.py test_broker_docs_truth.py`, native
  **271 passed, 1 skipped, exit 0**; offscreen **271 passed, 1 skipped, exit 0**.

## Not verified
- The manual rendered by eye in the Learn tab (only `test_learn_tab` loaded it).
- The full suite (no code changed; the docs tests above are the ones these files feed).
- Whether Yahoo stamps ^N225 near 00:00 UTC (left to TESTPLAN 11.23).
