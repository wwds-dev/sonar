# build-traceability: domain-finance review, Define pass (2026-10-19)

Reviewer: `domain-finance` (read-only). Saved by the orchestrator. The playbook is stale (`status: baseline`).

**Verdict:** sound for finance after two P1 changes.

- **P1-1.** Fix (a) opens a hole in the dirty-tree gate.
  - `scripts/check_app.sh:36` greps for any `"dirty": false`. Once the nested entries carry `"dirty": false`, a stamp
    with a dirty top-level tree but clean nested repos passes.
  - **Fix:** add "outer dirty, nested clean" as a required refusal in measure 2, and anchor the check to the top-level
    key (or parse the stamp with `python3 -I`).
- **P1-2.** Ledger entries carry only the build number (`sonar/core.py:699-700`, `sonar/calibration.py:1195, 1209`;
  `LEDGER_LOOK_FIELDS` `:876`), and the number isn't unique. The commit lives only in `/api/health`, and the tag is
  optional.
  - **Fix, either of:**
    - (a) the tag must exist on the commit before install, for any build that writes the ledger;
    - (b) record the commit and nested digest in the ledger `build` field (64-char cap). This touches the write-once
      ledger (ADR 0002 Amendment 1), so it needs the Architect and model-validator, and must not rewrite past entries.
  - Name the gap in the spec's Problem section.
- **P2-1.** Adopt Q1 (nested commits must equal the CI pins) as a success measure, with override text that names the
  drift.
- **P2-2.** State in Risks that a refused install leaves the running agent and the 30-day run untouched, and have QA
  check it in measure 4's negative run.
- **P3-1.** Annotate the v2.340 period as "nested code unknown" in the run and calibration notes.

Not verified: the suite was not run, and no built stamp or ledger ADR text was read.

---

# Architect pass (2026-10-19)

**Verdict:** sound for finance. All five Define findings are carried (spec A4 :245-261, A7 :342-378, ADR 0002
Amendment 2, scope d), with no P0 or P1. Two P2s need settling before the gate.

## P2
- **P2-1. The ledger can name a commit that later disappears.**
  - **Where:** A9 :412 (an off-master build installs if traceable); A6 :321-325 (checked only after install).
  - **Scenario:** a branch is installed, never pushed, then deleted. Its `build` shas stop resolving, as happened with
    the v2.340 worktree.
  - **Fix:** an overridable (exit 3) reason, "outer <sha> is not on any origin ref as of the last fetch", checked
    locally. Or run the A6 check before install. Record in the verify note that the commit and both pins are on origin.
- **P2-2. The shared install changes the nested code partway through the protocol, before look 1 (about
  2026-11-06).**
  - **Fix:** save the bootstrap's copy-vs-pin diff summary per repo, plus the install time, in
    `docs/audit/build-traceability-verify.md`. The model-validator decides whether look 1 needs a note or a split at
    that boundary.

## P3
- **P3-1.** `install_app.sh:73-77` runs the gate only when the agent runs from the app. Fix: state the condition in
  A4 and test both branches, or always gate (owner's choice).
- **P3-2.** The `build` string doesn't show pin drift after `--allow-dirty`. Fix: a marker such as `!`, or explain in
  Amendment 2 how to derive drift.
- **P3-3.** The look-1 note should carry "nested code unknown" for member entries with a bare version (no `+`).

---

# Review pass on the diff (2026-10-19)

**Verdict:** sound for finance, with no P0 or P1 and two P3s.
- Every Define, Architect and model-validator fold-in is in the code or docs: anchored dirty refusal
  (`scripts/buildid.py:112-118`, `check_app.sh:43-63`); pin equality (`buildid.py:144-158`); origin refs, checked
  locally (`:172-215`); the boundary report (`bootstrap_nested.sh:69,129-132`, RUNBOOK:36-39); `~`/`!` markers before
  `+` with commit shortening at 64 chars; the look-1 TODO; ADR "provenance only" plus an identical-output test;
  new-entries-only writing with byte-identical old records; the v2.340 notes.
- Ran `.venv/bin/python -m pytest tests/test_buildid.py tests/test_shadow_ledger.py tests/test_version.py
  tests/test_agent_provenance.py tests/test_agent_from_bundle.py tests/test_bootstrap_nested.py`: 418 passed, 1
  skipped, 1 failed. The failure is the expected v2.365 newest-entry-ahead check, which clears only if this work
  lands as exactly one commit on 7a08185.

## P3
- **P3-1.** After `--allow-dirty` overrides an origin-only refusal, the ledger keeps no record of it. The origin
  reasons (`buildid.py:415`) are not stored in the stamp and have no marker, but `check_app.sh:57-58` claims the
  reasons "stay in the stamp". Fix: correct the message (record them in the verify note), or log them, or add a
  marker.
- **P3-2.** A dirty nested repo is also reported as a dirty outer tree (`stamp_version.py:50`, `buildid.py:113-114`).
  The refusal is still correct. Fix: store `outer_dirty` separately and keep the P1-1 test.
