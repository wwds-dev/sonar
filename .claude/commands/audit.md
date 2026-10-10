---
description: Internal audit of this app as an outside engineering firm would do it. Writes reports to docs/audit/.
argument-hint: [all | ux | architecture | code | qa | security | model | ops | docs]
---

**App root:** if this repo has `docs/company/app-context.md`, it is the app; otherwise you are in the company HQ: the first argument is an app name from `apps.md`; resolve its path, tell each agent the absolute app root, and have it work only there.

Run the audit scope "$ARGUMENTS" (default `all`). Read-only on production code.

Spawn these agents in parallel (skip any not installed), each told to audit the whole repo
for its dimension and return findings ranked P0-P3 with file:line, scenario and fix:
`ux-designer` -> docs/audit/ux.md · `architect` -> architecture.md · `code-reviewer` ->
code-review.md · `qa-engineer` -> qa.md · `security-engineer` -> security.md (+ threat
model) · `model-validator` -> model-validation.md · `sre-release` -> operations.md ·
`tech-writer` -> docs.md.

Agents without Write tools return their report; you save it. Then write
`docs/audit/SUMMARY.md`: every P0/P1 across reports (deduped), a top-10 fix order, and what
could not be verified. Do not fix anything.
