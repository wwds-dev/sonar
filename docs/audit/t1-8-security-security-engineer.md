# T1-8 review — security-engineer, 2026-10-10

Read-only. Playbook `status: baseline`. 9 of the new tests fail on HEAD's sources. **P0: none. P1: none.**
Checked clean: `nan`, `inf`, `Decimal('NaN')`, `None`, `'nan'` rejected, `-0.0` by `> 0`, `1e308` by the
caps; `flatten`/`panic` do not depend on the audit write; the only `broker.place` calls are `submit` and
`flatten`; fsync costs milliseconds; the https URL is the 301 target.

| ID | Finding | Outcome |
|---|---|---|
| P2-1 | `subject`, `kind`, risk/horizon labels, `numbers` keys and non-float values reached the prompt unsanitised | Fixed: `_clean` on all; test |
| P2-2 | Feed titles drawn by `QLabel` AutoText as HTML (spoof, local image probe) | Fixed: plain-text on the card headline, headline rows, central-bank list; test |
| P3-1 | Fullwidth/lookalike brackets survive `_clean` | Fixed: NFKC first; test |
| P3-2 | `_sent` updated before the write: a refused intent can't be retried | Documented (fails closed) |
| P3-3 | String/Decimal quantity raised `TypeError`, not a rejection | Fixed: type check in `_finite`; `notional` tolerant; tests |
| P3-4 | 0600 only on creation | Fixed: `fchmod`; test |
| P3-5 | Gitignored nested packages: a clean clone can't import `sonar.core` | Known — T1-9 |
| weak test | `test_non_finite_venue_equity_fails_closed` passes on old code | Equivalent: `Guard.equity()` already returns None for NaN; kept as a pin |
