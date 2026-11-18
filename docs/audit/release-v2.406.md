# Release record: v2.406 (written after the fact, 2026-11-18)

Role: `sre-release`, records only (spec `docs/specs/readiness-h3-h4.md`, H4 of
`docs/audit/code-readiness-2026-11-18.md`). Nothing was built, installed or restarted for this note.

## What happened

- **Installed:** `/Applications/SONAR.app` written 2026-11-17 21:01:56; the launchd agent `com.netrunner3000.sonar`
  restarted onto it at 21:02:48 (`~/Library/Logs/SONAR/agent.err.log`: "push alarms: ntfy configured").
- **By whom:** the owner, deliberately, through Lab Hub's "Update now" (owner's answer 2026-11-18: "Yes,
  deliberate"). No release report or CHANGELOG entry was written at the time; this file is that record.
- **Build:** v2.406, commit `c2d96dd` (2026-11-17 18:42 UTC), stamp `traceable: true`, `dirty: false`, nested
  macro `811bf7b`, playmaker `c322aef` (the CI pins at that commit). Read from
  `/Applications/SONAR.app/Contents/Resources/_build_info.json` and `/api/health` `build`.
- **Previous recorded install:** v2.340 (`8e7d024`, sign-randomisation verdicts). Any install between v2.340 and
  v2.406 left no record; `alarm-delivery-sre-release.md` built v2.362 and stopped at the install gate.

## What v2.406 contains over v2.340

30 first-parent commits (`git log --first-parent 8e7d024..c2d96dd`). The behaviour changes:

| Change | Spec / source | Last phase recorded before install |
|---|---|---|
| ntfy phone push, daily heartbeat, `notify` in `/api/health`, `--test-alarm` | `alarm-delivery` (PR #11) | release blocked 2026-10-19 (install gate) |
| Agent at `ProcessType Standard`, no `Nice`; `SONAR_ALARM` switch; priority harness | `starved-engine` (PR #11) | document done 2026-10-19; the measured hour (RUNBOOK §7) not run |
| Nested commits in the stamp, parsed install gate, pinned bootstrap | `build-traceability` (PR #11) | verify done 2026-10-19 (`build-traceability-qa.md`) |
| Docs say Yahoo is the only Screener source; `providers.py` deleted | `providers-wiring` (PR #11) | review started 2026-10-19, never finished |
| Betting and AI notices, Kelly wording, bundle licences, SUPPORT/SECURITY, hourly-model notice | `legal-audit-fixes` | not in the activity log |
| Shadow ledger follow-up, closing-QA fixes, Playmaker plaintext for the holder LLM, untrusted-text sweep, two `claude/*` branches | Lab Hub merges 2026-11-17 ("conflicts resolved by Claude Code") | per-branch reviews in `docs/audit/`; the merges themselves unreviewed |
| Foundry v6-v12 template updates | Foundry HQ | n/a (process files) |

## State after install (read 2026-11-18, read-only)

- `/api/health`: `ok: true`, mode `driving`, answered in 15 ms; `notify`: banner 3/3 and ntfy 3/3 sends OK since the
  restart, heartbeat queued 09:14. Run: 975 hours scored, coverage 71.5%.
- Live verdict: model vs market "market better calibrated" (2.5 se at n = 975; under the 3-se rule built since, in
  `readiness-h1-h2`, that reads "within noise").

## Smoke test

**Not run.** The owner will run it (owner's answer 2026-11-18: "Skip, I'll run it"). Steps, from
`docs/foundry/app-context.md`:
1. Open `/Applications/SONAR.app`; check About shows v2.406 (`c2d96dd`).
2. Wait for one Screener scan (about a minute); rows carry prices and Updated times.
3. Place one paper trade on a fresh row; Undo it within the toast if you do not want it in the book.
4. Quit from the menu (not the close button), relaunch, check the book and settings are as left.
5. `./scripts/install_agent.sh --status`: the agent runs `/Applications/SONAR.app` and `/api/health` says
   `ok: true` with build v2.406.
6. Phone: confirm the 2026-11-18 heartbeat arrived (ntfy counters show HTTP success, not receipt).

## Gaps this install leaves open

- `providers-wiring` was installed mid-review (docs-only change and deleted dead code; no data-path change).
- `alarm-delivery` measures 6 and 7 (phone evidence) and the `starved-engine` measured hour are still the owner's.
- The Lab Hub merges were resolved by an agent and installed in the same session, without a review of the merge
  results. A future install should go through the release gate (`build_app.sh --install` with a release note), not
  only "Update now".
