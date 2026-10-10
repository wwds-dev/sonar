# SONAR roadmap to v1.0

Goal of v1.0: a **trustworthy, installable macOS app** that scans markets, paper-trades, and
tells the truth about its own accuracy. Real money is out of scope (see `AGENTS.md`).
The owner approves each phase exit. Dates are intentionally absent; order is the commitment.

## Phase 0 — Foundation *(done by scaffolding)*
`AGENTS.md`, agents, `/ship-feature`, `/audit`, `docs/` layout.
Exit: owner has read the process and changed what they disagree with.

## Phase 1 — Internal audit
Run `/audit all`. Exit: `docs/audit/SUMMARY.md` approved; P0/P1 findings become `TODO.md`
items.

## Phase 2 — Define the product
Through `product-manager`: who SONAR is for, the one question each tab answers, the success
measures for v1.0 (e.g. "a new user understands their book in 30 s", "calibration published
with intervals"), explicit non-goals, and what to cut or merge from the 8 tabs.
Output: `docs/specs/v1-product.md`. Exit: owner approves scope.

## Phase 3 — Remediate
All audit P0, then P1, each via `/ship-feature`. Order: security and data-loss first, then
model-honesty wording, then operational blind spots (no monitoring today), then UX.
Exit: no open P0/P1; suite green native + offscreen.

## Phase 4 — UX and onboarding
First-run experience, empty/stale/error states, plain-language pass, accessibility.
Exit: `ux-designer` re-audit has no P0/P1.

## Phase 5 — Release readiness
Signed and notarized build, update path, state backup/restore, monitoring plus runbook
(`docs/RUNBOOK.md`), legal/disclaimer text reviewed by the owner (agents cannot give legal
advice), third-party data-source terms listed with a fallback for each.
Exit: `sre-release` clean install → use → upgrade → restore drill passes.

## Phase 6 — v1.0 launch
Version bump, CHANGELOG, tagged release, short landing page / README front-page rewrite,
feedback channel. Exit: shipped; support and analytics loop begins (post-launch roadmap).

## Standing, every phase
Backlog hygiene in `TODO.md`; ADRs for hard decisions; re-run `/audit security` after any
change to network, secrets, server, or packaging.
