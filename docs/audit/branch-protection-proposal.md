# Branch protection for `master`: proposal (tier-3 item 5, 2026-10-19)

This is an owner action under AGENTS.md: branch protection stays with the owner. The agent only proposes it and
changed nothing on GitHub.

## Facts (read-only, 2026-10-19)
- `gh api repos/wwds-dev/sonar/branches/master/protection` returns **404 "Branch not protected"**. The repo is
  public.
- The check-run names on master (from `be1b183`) are `tests`, `secrets`, `dependencies` and `Dependabot`.
  - `tests` and `secrets` are blocking jobs (`.github/workflows/tests.yml:17`, `security.yml:9`).
  - `dependencies` has `continue-on-error: true` (`security.yml:22`), so it isn't a useful required check.
- Audit finding: `foundry/audits/sonar/operations.md` P1-3. A red PR can be merged, so the DoD's "CI is green" is
  honour-system only.
- **Release rule (build-traceability, owner Q4):** releases are cut only from first-parent master. This makes master's
  history a release record, which raises the stakes of protecting it.

## Recommendation
Require the `tests` and `secrets` checks and a pull request for changes to master, and block force-pushes and
deletion. Keep `enforce_admins` off, so you can still push directly in an emergency; GitHub logs the bypass.

Run it yourself:

```bash
gh api -X PUT repos/wwds-dev/sonar/branches/master/protection --input - <<'JSON'
{
  "required_status_checks": { "strict": false, "contexts": ["tests", "secrets"] },
  "enforce_admins": false,
  "required_pull_request_reviews": { "required_approving_review_count": 0 },
  "restrictions": null,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "required_linear_history": false
}
JSON
```

Then check it:

```bash
gh api repos/wwds-dev/sonar/branches/master/protection --jq '.required_status_checks.contexts, .enforce_admins.enabled, .allow_force_pushes.enabled'
```

Expected output: `["tests","secrets"]`, `false`, `false`.

## Choices
- **`required_approving_review_count: 0`:** you're the only approver and GitHub doesn't let you approve your own PR,
  so this requires a PR without blocking on a review.
- **`strict: false`:** a PR doesn't have to be rebased on the latest master before merging. With `true`, every
  concurrent session's PR would need an update-and-rerun first, which is slow here.
- **`required_linear_history: false`:** merge commits are how the agent sessions' work arrives (`be1b183`, `7375810`).
  First-parent master stays well defined either way.
- **Effect on agents:** `git push origin master` from a session stops working for non-admins and is logged as a bypass
  for you. Agents already need your ask before pushing (AGENTS.md); with this, their work goes through PRs.
- **Effect on items 1–3:** branch `claude/pensive-benz-f395cc` reaches master through a PR, and `tests` and `secrets`
  must be green first. That is the merge the release step needs anyway.

## Not done
- Nothing was set on GitHub.
- Whether CI is green on this branch is unknown; it hasn't been pushed.
