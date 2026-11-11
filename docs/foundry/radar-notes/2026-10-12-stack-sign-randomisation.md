# Radar check: stack: sign-randomisation verdicts

Date: 2026-10-12 · Scope: `stack` · Searches: 0 (reuses `2026-10-12-feature-sign-randomisation.md`, same day, same change).

Stack is unchanged: Python 3, stdlib only, PySide6 UI. The change adds no dependency, service or file format.

| Finding | Source | Impact | Recommendation | Approval |
|---|---|---|---|---|
| Implement with `random.Random(seed)` and `itertools.product` (enumeration). No numpy/scipy. | feature note | P3 | Adopt | none |

## Checked, nothing new
No stack-level advisory or deprecation applies. Nothing to install.
