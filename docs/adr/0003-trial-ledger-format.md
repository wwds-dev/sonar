# 0003. Trial ledger: hash-chained JSON Lines in git, fail closed

- Status: proposed (Architect gate)
- Date: 2026-10-13

## Context
Research needs a count of trials tried (for DSR). The file is committed history; its format and
chain are hard to change once records exist. See `docs/specs/trial-ledger-dsr-pbo.md`.

## Decision
`docs/research/trial-ledger.jsonl`, canonical JSON per line, `seq` + `prev_sha256` + `sha256`,
`schema: 1`. Append under `flock(LOCK_EX)` on the file, read-tail inside the lock, fsync. Any
inconsistency raises and blocks reporting; no auto-repair. Deleted tails are detectable only
against a head recorded elsewhere in the same repo (not external: an editor of the repo can edit
it too). Output says "internally consistent", never "verified". `trial_key` includes a feature
source hash and every computation argument; N and V are defined by `seq`, controls included.
`kind` is `logged_live`|`reconstructed`, since nothing proves a record preceded the result.
Ledger is research-only and never in `SONAR_DATA`. Details: spec Architecture section.

## Alternatives considered
- Skip-bad-lines reader like `execution_audit.jsonl`: silently drops trials from N. Rejected.
- Side lock file: one more artefact to lose or commit. Rejected.
- SQLite: binary, poor diffs in git, heavier. Rejected.
- Signed records: needs key management for a no-edge internal tool. Rejected.

## Consequences
Unix only. Merging two branches that both append conflicts and must be re-appended. A schema change
needs `schema: 2` with a reader for both; old lines are never rewritten. Chain gives order and
consistency, not completeness.
