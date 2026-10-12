---
description: Run a change through the Foundry pipeline (define, design, architect, build, review, verify, secure, document, release), stopping at each owner gate.
argument-hint: <feature or fix, in one or two sentences>
---

**App root:** if this repo has `docs/company/app-context.md`, it is the app; otherwise you are in the Foundry HQ: the first word of the arguments is a name from `apps.md` (resolve its path) and every repo-relative path below is relative to that app. Tell each agent the absolute app root and have it work only there.

Run the pipeline in `AGENTS.md` for: $ARGUMENTS

Anything after ` -- reason:` is the owner's reason for sending the app back (from the dashboard's
drag-to-dispatch). Put it in the spec under `## Why again` and brief every agent with it.

Rules for you, the orchestrator:
0. Check `last-reviewed` in `docs/playbooks/` for every role this change will use. If any is
   `status: baseline` or over 90 days old, tell the owner and offer to refresh the playbooks
   (run `/industry-radar` in the company repo, then `install.sh --update`); continue only if
   they say so.
0b. Run `/radar-check feature` before Define, `/radar-check stack` before Architect,
   `/radar-check security` before Secure (when required) and `/radar-check release` before Release,
   as AGENTS.md describes. A fresh note (under 30 days) is reused. Surface any tool it recommends
   to the owner; install nothing yourself.
1. Delegate each phase to its agent (Agent tool, `subagent_type` = the agent's name). Brief
   each with the goal, the spec path and what earlier phases decided; they have no context.
2. After **Define** and **Architect**, if a domain specialist is installed
   (`.claude/agents/domain-*.md`), run it on the spec (then on the architecture section) and save
   its report to `docs/audit/<slug>-domain-<key>.md` (append the Architect pass). Then stop and
   show the owner a 10-line summary, including its P0/P1, plus the file path. Wait for approval before Build. Do not proceed on silence.
3. Build with `engineer`. Then run `code-reviewer` and `qa-engineer` independently (in
   parallel), plus the domain specialist if installed; add `security-engineer` when AGENTS.md
   says it is required. Reviewers cannot
   write files: save their reports to `docs/audit/<slug>-<role>.md` yourself.
4. If any P0/P1 is found, send it back to `engineer`, then repeat Review and Verify. Stop
   after 3 loops and escalate to the owner.
5. Then `tech-writer`, then `sre-release` (a gate: ask before building or installing).
6. Finish with a table: phase, agent, artifact path, result, anything skipped and why. Do not
   commit or push unless the owner asked.
