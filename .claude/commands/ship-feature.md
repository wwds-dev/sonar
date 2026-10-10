---
description: Run a change through the company pipeline (define, design, architect, build, review, verify, secure, document, release), stopping at each owner gate.
argument-hint: <feature or fix, in one or two sentences>
---

**App root:** if this repo has `docs/company/app-context.md`, it is the app; otherwise you are in the company HQ: the first word of the arguments is a name from `apps.md` (resolve its path) and every repo-relative path below is relative to that app. Tell each agent the absolute app root and have it work only there.

Run the pipeline in `AGENTS.md` for: $ARGUMENTS

Rules for you, the orchestrator:
0. Check `last-reviewed` in `docs/playbooks/` for every role this change will use. If any is
   `status: baseline` or over 90 days old, tell the owner and offer to refresh the playbooks
   (run `/industry-radar` in the company repo, then `install.sh --update`); continue only if
   they say so.
1. Delegate each phase to its agent (Agent tool, `subagent_type` = the agent's name). Brief
   each with the goal, the spec path and what earlier phases decided; they have no context.
2. After **Define** and **Architect**, stop and show the owner a 10-line summary plus the
   file path. Wait for approval before Build. Do not proceed on silence.
3. Build with `engineer`. Then run `code-reviewer` and `qa-engineer` independently (in
   parallel); add `security-engineer` when AGENTS.md says it is required. Reviewers cannot
   write files: save their reports to `docs/audit/<slug>-<role>.md` yourself.
4. If any P0/P1 is found, send it back to `engineer`, then repeat Review and Verify. Stop
   after 3 loops and escalate to the owner.
5. Then `tech-writer`, then `sre-release` (a gate: ask before building or installing).
6. Finish with a table: phase, agent, artifact path, result, anything skipped and why. Do not
   commit or push unless the owner asked.
