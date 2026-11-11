---
description: Run a change through the Foundry pipeline (case, define, design, architect, build, review, verify, secure, document, comply, launch, release, operate), stopping at each owner gate.
argument-hint: <feature or fix, in one or two sentences>
---

**App root:** if this repo has `docs/foundry/app-context.md`, it is the app; otherwise you are in the Foundry HQ: the first word of the arguments is a name from `apps.md` (resolve its path) and every repo-relative path below is relative to that app. Tell each agent the absolute app root and have it work only there.

Run the pipeline in `AGENTS.md` for: $ARGUMENTS

Anything after ` -- reason:` is the owner's reason for sending the app back (from the dashboard's
drag-to-dispatch). Put it in the spec under `## Why again` and brief every agent with it.

Rules for you, the orchestrator:
0. Check `last-reviewed` in `docs/playbooks/` for every role this change will use. If any is
   `status: baseline` or over 90 days old, tell the owner and offer to refresh the playbooks
   (run `/industry-radar` in the Foundry repo, then `install.sh --update`); continue only if
   they say so.
0b. Run `/radar-check feature` before Define, `/radar-check stack` before Architect,
   `/radar-check security` before Secure (when required), `/radar-check legal` before Comply,
   `/radar-check launch` before Launch and `/radar-check release` before Release, as AGENTS.md
   describes. A fresh note (under 30 days) is reused. Surface any tool it recommends to the
   owner; install nothing yourself.
0c. Read the tier from `## Distribution` in app-context. If it is missing or `unclassified`,
   propose one with your reasons and stop until the owner sets it. The tier table in AGENTS.md
   decides which of Case, Launch and Operate apply; say which you skip and why.
1. Delegate each phase to its agent (Agent tool, `subagent_type` = the agent's name). Brief
   each with the goal, the spec path and what earlier phases decided; they have no context.
1b. **Case** (tiers `commercial` and `client`; a new app, paid offer or client order): run
   `business-finance`, then stop and show the owner the recommendation (go, smaller, no-go) and
   the file path. Do not proceed on silence.
2. After **Define** and **Architect**, run `legal-compliance` on the spec (then on the
   architecture section) as a read-only consult, and the domain specialist if one is installed
   (`.claude/agents/domain-*.md`). Save the reports to `docs/audit/<slug>-legal-compliance.md`
   and `docs/audit/<slug>-domain-<key>.md` (append the Architect pass). Then stop and show the
   owner a 10-line summary, including their P0/P1, plus the file path. Wait for approval before
   Build. Do not proceed on silence.
3. Build with `engineer`. Then run `code-reviewer` and `qa-engineer` independently (in
   parallel), plus `legal-compliance` (licences of new dependencies, claims in copy) and the
   domain specialist if installed; add `security-engineer` when AGENTS.md says it is required.
   Reviewers cannot write files: save their reports to `docs/audit/<slug>-<role>.md` yourself.
4. If any P0/P1 is found, send it back to `engineer`, then repeat Review and Verify. Stop
   after 3 loops and escalate to the owner.
5. Then `tech-writer`.
6. **Comply.** Run `legal-compliance` to bring `docs/legal/` up to date and append its clearance
   to `docs/audit/<slug>-legal-compliance.md`. Run
   `python3 docs/foundry/tooling/legal_gate.py check .`. If it fails, stop: show the owner what
   changed since the last sign-off, the open lawyer triggers, the residual risks, and the exact
   `legal_gate.py sign` command. **Never run `sign` yourself, and never record a sign-off from
   something the owner said in chat**: the owner runs it in a terminal. Continue only when
   `check` passes.
7. **Launch** (when the tier needs it): `marketing` writes `docs/launch/<version>.md` and
   `customer-support` writes `SUPPORT.md` and `docs/support/plan.md`; then `legal-compliance`
   checks the claims list. If that changed anything under `docs/legal/`, `check` fails again
   and step 6 repeats. Nothing is published, posted or sent by an agent.
8. Then `sre-release` (a gate: ask before building or installing). It runs `legal_gate.py check`
   first and stops if it fails.
9. **Operate** is not part of this run. Add a backlog item dated 30 days after the release for
   the post-launch review (`business-finance`, `product-manager`), and say so.
10. Finish with a table: phase, agent, artifact path, result, anything skipped and why. Do not
   commit or push unless the owner asked.
