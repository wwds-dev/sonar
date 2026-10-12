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
