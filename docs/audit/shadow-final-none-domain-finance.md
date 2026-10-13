# Domain review (finance): SH_FINAL_NONE rewording (ui/app.py:549-554)
Playbook domain-finance: status baseline, last-reviewed 2026-10-12 (not yet verified by a radar run). Not legal advice; jurisdiction UNVERIFIED.

## Verdict
Safe on domain terms (no edge, profit, forecast or certainty claim; no size/return reading of "201 entries"). Fixes the r2 "planned size" and validator P2-4 points. Three small items remain; none blocks.

## Findings
- P2-1 "201" is hard-coded (:551, :554). ADR 0002 §3 notes a 40-position cap and exclusions (>10% excluded is flagged), so the entries actually used can differ. A fixed "201" could then misstate the sample. Fix: pass the last look's `n` (or `used`) as `{N}` into `_sh_word("SH_FINAL_NONE", ...)` (ui/app.py:875) and word it "planned 201" only if n matches.
- P2-2 "a fairly strong link (about 0.2 or more)": 0.2 is conventionally a weak correlation, so "fairly strong" can mislead the other way (user thinks a "weak" link means near nothing, or that 0.2 is large). Also "usually" hides the number: ADR §3 power is 0.73 at 0.2 (about 3 in 4), 0.23 at 0.1. Fix: drop "fairly strong"; say "about 3 times in 4".
- P3-1 "ranks" (here, :549/:553) vs "sorts" (:598 "asks only whether the score sorts"). r2 flagged this; still inconsistent. Pick one; "sorts" matches the explainer.
- P3-2 "correlation" is jargon for a retail audience in the plain line. Say "link" plain and keep "correlation" only in the expert string (:553 already does the short form).
- P3-3 Add that it is paper results, before costs? Already stated in the SH explainer lines (:546-548); not needed here.

## Suggested wording
Plain: "Three looks, no crossing: not enough evidence that the score sorts {T_adj} results. With {N} entries, this test finds a link of about 0.2 or more (on a scale where 1 is perfect) about 3 times in 4, and a weaker link only rarely, so a weaker one could have been missed. The test is finished."
Expert: "Looks 1-3 not crossed: not enough evidence that the score sorts {T_adj} results. Power at {N} entries: 0.73 at correlation 0.2, 0.23 at 0.1. Design closed."
(0.23 and 0.73 are ADR 0002 §3 Pocock simulations, sample-size dependent; quote them only when N is the planned 201. Otherwise omit the figures.)

Not verified: actual runtime n in a closed test; sim figures not re-run.

## Re-review of final wording (commit 14af453, 2026-10-12)
Playbook domain-finance: status baseline (last-reviewed 2026-10-12). Not legal advice.

**Verdict: no P0/P1. Acceptable to ship.** No edge, profit, forecast or certainty claim in either form of SH_FINAL_NONE or SH_FINAL_NONE_FEWER (ui/app.py:549-565). P2-1 and P2-2 are resolved: "fairly strong"/"usually" are gone, the figure "about 3 times in 4" matches ADR 0002 §3 power 0.73 at correlation 0.2, and the entry count is the real one.

- P2-3 (conditional on config) SH_FINAL_NONE hard-codes "0.2" and "3 times in 4" against `{used}` (ui/app.py:550-551, 553-554), and the branch is `used >= planned` (:887). The 0.73 power holds only for the planned 201 design (ADR §3 table). It is true as long as the planned final n is 201 (the only value found in code/ADR). If the look schedule or planned n is ever changed, or `used` exceeds `planned`, the sentence silently misstates power. Fix: store the power with the look (or a constant tied to the ADR design) and add a test that fails when the last look's `n` != 201; or say "{planned}" only when it equals 201.
- P3-4 FEWER power claim is honest in form: it states the 3-in-4 figure only "at {N} entries" / "designed to ... at {N}" (:558-564), and says the test was "less sensitive than designed". It does not state the reduced power, so a user could still read it as near 3 in 4. ADR §3 gives correlation needed 0.35 at 45 and 0.23 at 101 (power 0.23 at IC 0.1 / 0.73 at 0.2 only for 201). Optional: add "a link of 0.2 may well have been missed" or the correlation needed at the actual `used`. Not required.
- P3-5 Edge: `_sh_int` returns 0 for a missing value (:708-710), so missing `n` and `used` gives used 0 >= planned 0 and the plain form reads "With 0 entries, this test finds ... 3 times in 4", which is false. Guard: if planned <= 0 or used <= 0, use FEWER or a neutral line.
- P3-6 "3 times in 4" is read by some retail users as "75% chance the score has no link". It means: if a link of 0.2 existed, the test would catch it about 75% of the time. Consider "if a link of 0.2 or more existed, this test would find it about 3 times in 4". Phrase in the plain form is acceptable but ambiguous.
- Earlier P3-1 (ranks vs sorts) and P3-2 (correlation jargon in plain text; the plain string still says "correlation" nowhere, now "link": P3-2 effectively resolved in plain form) are deliberately left; unchanged.

Readability: plain forms are one-sentence-per-point and readable; the FEWER plain form is long (3 clauses in one sentence) but clear. Expert forms are terse and fine.

Not verified: ADR power figures not re-simulated; runtime values of `used`/`n` in a closed test; tests for the new branch not run.
