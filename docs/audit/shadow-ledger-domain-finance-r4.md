# Domain review (finance), round 4: shadow-ledger fix loop 3 (a08e796..d84abd5)
Reviewer: domain-finance, read-only, 2026-10-13, HEAD d84abd5. Saved by the orchestrator from the agent's
report. Real book and Application Support not read. Playbook `status: baseline` (stale). Jurisdiction
UNVERIFIED; no regulation text checked; not a legal approval.

**Verdict: r3 P1-1 closed; P3-1, P3-2, P3-3 closed. No new P0, P1 or P2. One new optional P3.**

## Confirmations
- **P1-1 closed (G3 enforced).** A retire is refused while the book's own marker names the record
  (`retired = set(found) - {marker["ledger_id"]}`, sonar/core.py:763); the ten-minute rule cannot remake
  a retired id. The retire offer is dropped on the marker path (ui/app.py:1091-1094). Retired records
  always disclosed with count, date and "re-tests the same kind of entries" (ui/app.py:665-673,
  1055-1064; core.py:1028-1033). Tests: `test_cr3_g3_retiring_without_a_reset_is_not_honoured`
  (tests/test_shadow_ledger.py:1698), disclosure asserts 1689-1694. Docs agree: README.md:270-276,
  CHANGELOG.md:67-74, static/docs.html:1089-1100, ADR 0002. Hand-tamper risk disclosed as "not
  tamper-proof" (docs.html §10).
- **P3-1 closed** (ui/app.py:740-750). **P3-2 closed** (errata on looks first, then newest;
  ui/app.py:1124-1128, 770, 1144). **P3-3 closed** ("it has no usable R" / "R → none";
  ui/app.py:763-764, 1137-1139).
- **No implied edge, profit or certainty.** CHANGELOG Unreleased (CHANGELOG.md:13-74) and manual §10
  (static/docs.html:904-1127) keep the coin-flip, before-costs and "not a trading edge" framing.
- **Labelling.** No new performance figure; simulated power figures stay labelled with sample sizes
  (4,000 and 12,000 books; CHANGELOG.md:30-33).
- Tests: offscreen `tests/test_shadow_ui.py tests/test_shadow_ledger.py` 256 passed. Full suite not run
  by this role.

## New finding
**P3-1 (optional). The retired-record count stops at 50 without saying so.** sonar/core.py:879
(`names[:SHADOW_RETIRED_MAX]`, 50 at :162), count at :1033. With more than 50 retired files the line
says "50 earlier records" and the first date may be wrong. Unlikely in practice. Fix: "50 or more" at
the cap, or count all names before reading the first 50. *Orchestrator: deferred to TODO.md.*
