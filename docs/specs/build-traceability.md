# Spec: Build traceability (nested-repo stamp, release identity)

- Status: Define approved 2026-10-19 (with changes from `docs/audit/build-traceability-domain-finance.md`)
- Owner approval: Define gate approved 2026-10-19
- Priority: **P1** (operations audit wave 2, P1-1, with P2-1 and prior P3-1; tier-3 item 3)
- Evidence: `foundry/audits/sonar/operations.md` (facts table lines 36-46, P1-1 lines 100-112, P2-1 lines 136-141,
  P3-1 line 70)
- Radar: light check below (no earlier note covers provenance or tags). Playbook `product-manager.md` is
  `status: baseline`.

## Problem
The owner cannot say which code the live agent runs. The playmaker and macro modules feed live scoring, and nothing ties them to a commit.
- **The gate passes untraceable code.** The installed v2.340 stamp has `"nested": {}` and `"dirty": false`, yet the bundle holds
  `sonar.macro` and 8 `sonar.playmaker.*` entries (audit table, archive listing). The chain:
  - `version._nested()` skips any nested dir without `.git` (`sonar/version.py:327-328`, `continue`).
  - `stamp_version.nested_state()` reads an empty dict as clean (`scripts/stamp_version.py:30-37`).
  - `check_app.sh` greps only the top-level `"dirty": false` (`scripts/check_app.sh:36`).
- **It is happening again now.** This worktree, where items 1 and 2 (v2.362, v2.363) were built, has `sonar/macro` and
  `sonar/playmaker` as plain copies with no `.git`. The main checkout has real repos (`sonar/{macro,playmaker}/.git/HEAD`).
  A worktree never contains the gitignored nested repos, so any release built from one repeats v2.340.
- **The docs claim otherwise.** RUNBOOK §1 (`docs/RUNBOOK.md:21`) promises a "clean stamp including `sonar/macro` and
  `sonar/playmaker`".
- **A build number names more than one commit.** BUILD is `git rev-list --count HEAD` (`version.py:124`, VERSIONING.md).
  It counts every ancestor, so two branches cut from the same base, each with k commits, both get base + k. Worktrees on
  different branches therefore each sit at "362" with different code. The audit counted 175 such numbers across all refs
  (v2.301 = `257d194` and `a634ce2`). VERSIONING.md:25 still says "a linear history, which this repo has". `git tag` lists 0 tags.
- **The shadow ledger records only the number (domain P1-2).** Each entry's `build` is `version` alone, capped at 64
  characters (`sonar/core.py:699-700`; `sonar/calibration.py:1195,1209`). The commit appears only in `/api/health`, which
  is not kept. A ledger entry therefore cannot be tied to the code that wrote it, outer or nested.
- **Nested repos cannot be cloned at a known state.** CI pins their SHAs (`.github/workflows/tests.yml:34-43`;
  `tests/test_ci_pins.py`). A release worktree has no such step, so it holds copies (prior P3-1, open).

## User and goal
**User:** the owner, as the release approver and the reader of `/api/health` during the 30-day paper run.
**Goal:** every bundle that passes `check_app.sh` names the exact commit of the outer repo **and** of both nested repos.
A release number points at exactly one commit. A bundle that cannot be named is refused.

## Success measures (all checkable on a built bundle, before install)
1. **Stamp test.** Two tests in `tests/test_version.py`, using a temporary tree:
   - When `sonar/<name>/` exists without `.git`, the stamp records `{"commit": "", "dirty": null}` for it, and top-level `dirty` is
     `true`.
   - With both nested repos clean, the stamp has both keys, each with a 7+ hex commit and `dirty: false`.
   Mutation check: restore the `continue` and the first test must fail.
2. **Gate test.** A test feeds fixture stamps to `check_app.sh`, with codesign and selftest faked as in
   `test_agent_from_bundle.py`. It refuses:
   - a stamp with `nested: {}`;
   - a stamp missing one name;
   - an empty commit;
   - nested `dirty` not `false`;
   - **outer dirty, nested clean** (domain P1-1). The dirty check is anchored to the top-level key, or the stamp is
     parsed with `python3 -I`; there is no bare grep for `"dirty": false`;
   - nested commits that differ from the `tests.yml` pins (owner Q1). The refusal text names each drift
     (`<repo>: stamp <sha>, CI pins <sha>`).
   It accepts a full clean stamp at the pins. `--allow-dirty` still overrides, with a warning that names the nested
   repo and any drift.
3. **Bootstrap.** In a fresh worktree, the bootstrap leaves both nested repos as real checkouts at the `tests.yml`
   pins. `tests/test_ci_pins.py::test_the_pin_is_the_commit_this_checkout_runs` then **passes for both, with no skip**.
4. **The built bundle (the shared items 1+2+3 build).** Before `--install`:
   - `scripts/check_app.sh dist/SONAR.app $(mktemp -d)` exits 0.
   - `dist/SONAR.app/Contents/Resources/_build_info.json` shows `nested.macro.commit` and `nested.playmaker.commit` equal
     to the `tests.yml` pins (as prefixes), with `dirty: false`.
   - The output is recorded in `docs/audit/build-traceability-verify.md`.
   - A negative run on a copy-only tree (this worktree as it is today) is refused by `check_app.sh`. QA confirms
     that the refusal leaves the running agent untouched: its pid and `/Applications/SONAR.app` are unchanged, and
     no staged bundle is left behind (domain P2-2).
5. **Release identity.** The build step prints one proposed command, `git tag -a v2.NNN <commit> -m "<summary>"`.
   - It refuses, with a message, if tag `v2.NNN` already exists on a different commit.
   - It warns when the commit is not on first-parent `master` (owner Q4).
   - The owner runs the command. After that, `git describe --exact-match <commit>` prints `v2.NNN`. That check is post-release, so it is not a gate.
6. **Ledger build field (domain P1-2, option b).** A test shows that a **new** ledger entry's `build` holds the
   version, the outer commit and the nested commits (or a short digest of them), within 64 characters. A second
   test shows that entries already in the ledger are byte-identical after a write.
7. **Docs.** These docs state, without the "linear history" claim, that only tagged builds are releases, and that a number alone does not identify a build:
   - RUNBOOK §1;
   - VERSIONING.md;
   - the `version.py` docstring.

## Scope
- **(a) Fail closed on copies.** In `_nested()`, record a dir that exists without `.git` as `{"commit": "", "dirty": None}`.
  It must not be skipped. A *missing* dir stays absent. `check_app.sh` must then require both `NESTED_REPOS` keys, each with a commit and `"dirty": false`.
  `check_app.sh` is bash with no `jq`. Either the stamp writes a precomputed top-level `"traceable": true` that the gate greps,
  or the gate runs `python3 -I -c`. The Architect decides.
- **(b) Bootstrap script** `scripts/bootstrap_nested.sh`, stdlib/shell only:
  - It reads the pins from `tests.yml` with the same regex as `test_ci_pins.py`.
  - It `git clone`s each nested repo from the `wwds-dev` remote. If that fails, it falls back to the main checkout's
    local nested repo and prints a warning (owner Q2).
  - It checks out the pinned SHA.
  - It refuses to overwrite a dir that has uncommitted work.
  - It replaces a copy-only dir only after moving it aside.
- **(c) Release identity: a tag, not a new number.** Keep `v<MAJOR>.<rev-list count>`. It is the lab-wide scheme, and
  the Lab Project Monitor derives the same string (VERSIONING.md:40-46, "do not add a second scheme"). A release is the
  pair (number, commit), which the stamp and `/api/health` already carry. The build proposes an annotated tag. Creating
  and pushing tags is an **owner action**: the agent only prints the command. Releases are cut only from
  first-parent `master` (owner Q4). The past install is tagged retroactively: the build proposes
  `git tag -a v2.340 8e7d024 -m "v2.340 (retroactive); nested code unknown"` (owner Q3).
- **(d)** Correct RUNBOOK §1, VERSIONING.md:25-30 and the `version.py` docstring. Document notes the v2.340 period as
  "nested code unknown" in the run and calibration notes (domain P3-1).
- **(e) Ledger `build` field** (domain P1-2, option b). New entries record the version, the outer commit and the nested
  commits (or a short digest), within the 64-character cap (`core.py:699-700`). Past entries are never rewritten: the
  ledger is write-once (ADR 0002 Amendment 1). This needs an Architect pass (with an ADR 0002 amendment if the field's
  meaning changes) and a `model-validator` check before Build.

## Non-goals
- Any change to scoring, trading, the book or alarms. Real money stays out of scope.
- No build, install or restart here, and no read or write of `~/Library/Application Support/SONAR*` or the live agent.
  The install is the shared one for items 1+2+3, with the owner's yes.
- A reserved monotonic release counter or a changed BUILD formula. It would be a second version scheme, and it would break the
  dashboard invariant.
- `git submodule` conversion. It is a module-boundary change for the lab's repo-per-module rule, so it would be its own ADR if wanted.
- Signed provenance (SLSA Build L2+), notarization, PyInstaller pinning (P2-3), `staleness()` across branches, and branch protection
  (P1-3, owner).

## Challenge to the request
The audit's "unique build identifier" options include a reserved monotonic number. That breaks a stated invariant
(VERSIONING.md "Why the dashboard cannot disagree") and answers no question that (number + commit + tag) leaves open.
The smaller version is a tag per release. Part (a) alone would block the next shared install, because this worktree
holds copies. So (a) cannot ship without (b), or without building the release in the main checkout.

## Radar (light, recommend only; no new dependencies)
- **SLSA v1.1.** Provenance should list resolved dependencies, for example the git commit a repo URI resolved to.
  At Build L1 it may be incomplete and unsigned ([provenance](https://slsa.dev/provenance/v1),
  [levels](https://slsa.dev/spec/v1.1/levels)). The stamp's `nested` block is SONAR's L1-style resolvedDependencies.
  Making it complete is this spec. Signing it is a non-goal.
- **git-tag.** "Annotated tags are meant for release while lightweight tags are meant for private or temporary object
  labels". `git describe` ignores lightweight tags by default ([git-tag](https://git-scm.com/docs/git-tag), read
  2026-10-19). Hence `-a`.

## Risks
- **The gate blocks the shared release.** If (b) is not run, the items 1+2+3 install is refused. That is intended, but
  the RUNBOOK must give the bootstrap step first. A refused install leaves the running agent and the 30-day run
  untouched: `check_app.sh` runs before any stop, so there is no stop and no partial bundle swap (domain P2-2;
  checked in measure 4's negative run).
- **Ledger readers.** A longer `build` string may break code that parses it as a bare version. The Architect checks
  every reader (`calibration.py:1195,1209`, `LEDGER_LOOK_FIELDS`).
- **Pins lag the local nested repos.** If the main checkout's nested HEAD is ahead of the pin, the bootstrap builds the
  pinned (CI-tested) code, not the local code. `test_ci_pins` already flags the drift. The owner chooses which side wins (Q2).
- **Tag left unpushed or never made.** A tag is only useful if the owner runs the command. Until then, the record is
  the stamp's commit.
- **v2.340's nested code stays unknown.** The release worktree is gone, and this does not recover it.

## Owner decisions (2026-10-19)
1. **Yes:** the nested commits must equal the `tests.yml` pins (measure 2).
2. **Remote first:** the bootstrap clones from `wwds-dev/sonar_*` and falls back to the main checkout's local repos
   with a warning (Scope b).
3. **Yes:** tag `v2.340` → `8e7d024` retroactively. The tag message says its nested code is unknown (Scope c).
4. **Yes:** releases are cut only from first-parent `master`. VERSIONING.md says so (Scope c, measure 5).

Creating and pushing tags stays an owner action; the build only prints the command.

## Architecture (architect, 2026-10-19)

Playbook `docs/playbooks/architect.md` is `status: baseline` (last-reviewed 2026-10-10): stale by the AGENTS.md rule;
the owner chose to continue. Radar: reuses the light note above (SLSA v1/v1.1, annotated tags). Stdlib and shell only;
no new dependency. Facts checked on 2026-10-19: `/usr/bin/python3` is 3.9.6, git is 2.56; the main checkout's nested
HEADs equal the `tests.yml` pins (`b3fa3e2…`, `1162ba5…`); `8e7d024` has `rev-list --count` 340 and is on first-parent
`master` and `origin/master`; this worktree's HEAD `9aa9bd1` is not on first-parent `origin/master`.

### A1. One decision module: `scripts/buildid.py` (new, stdlib only)
Everything that judges a build's identity lives in one file, so there is one guard, not two. It has no `sonar` import
and runs under `python3 -I` on Python 3.9 (no `match`, no runtime `X | Y`; `from __future__ import annotations`).
Under `-I`, the script's directory is not on `sys.path`, so it imports nothing local. It provides:
- `pins(text) -> {"sonar/macro": (repo, sha40), "sonar/playmaker": (repo, sha40)}`: the CI pin parser (A3).
- `verdict(stamp) -> list[str]`: the reasons a stamp cannot be traced. An empty list means traceable (A2, A4).
- `build_id(prov) -> str`: the ledger `build` string (A7). Pure. `sonar/version.py` re-exports it by loading the file
  (`importlib.util.spec_from_file_location`), because `sonar` must not import from `scripts/` when it is frozen. **Alternative
  (preferred if the reviewer objects to the cross-load):** put `build_id` in `sonar/version.py` and test both against
  one fixture table. It is a formatter, not a guard, so a second copy is acceptable there and nowhere else.
- CLI: `check-stamp <stamp.json>`, `pins [--shell] <tests.yml>`, `remote-url <origin-url> <owner/name>`,
  `tag-command <stamp.json> --repo <dir>`, `tag-command --retroactive <MAJOR.BUILD> <commit> --repo <dir>`.
Callers: `scripts/stamp_version.py` adds `Path(__file__).parent` to `sys.path` and imports it. `check_app.sh`,
`bootstrap_nested.sh` and `build_app.sh` run it with `python3 -I`. `tests/test_ci_pins.py` loads it with
`spec_from_file_location`, which `tests/test_agent_from_bundle.py:460` already does for `stamp_version`.

### A2. The stamp
**`sonar/version.py:320-332` `_nested()`.** Replace the `continue` at `:327-328` with three cases:
- `sonar/<name>` absent: no key. The code is not in the tree, and the gate refuses the missing key.
- present, no `.git` (a copy): `{"commit": "", "sha": "", "dirty": None}`.
- `.git` present: `{"commit": <short>, "sha": <git rev-parse HEAD or "">, "dirty": <_dirty>}`. If git fails, the
  existing `{"commit": "", "sha": "", "dirty": None}` (`:331`) applies.
`sha` is new because the pins are full SHAs. A 7-hex prefix match is enough against accidents, but the stamp is the
SLSA L1-style `resolvedDependencies`, and that wants the full digest. `commit` stays short, as `/api/health` shows it.
Side effect, intended: a checkout-mode agent on a copy now reports `dirty: null` in `/api/health` (`provenance()`,
`version.py:304-311`), where before it looked clean.

**`scripts/stamp_version.py:61-73` payload: new keys** (existing keys unchanged, so `_baked()` at `version.py:179-190`
and every current reader still work):
```json
{"major": "2", "build": 364, "commit": "abc1234", "sha": "<40 hex>", "date": "...",
 "dirty": false,
 "nested": {"macro":     {"commit": "b3fa3e2", "sha": "b3fa3e21…", "dirty": false},
            "playmaker": {"commit": "1162ba5", "sha": "1162ba5e…", "dirty": false}},
 "pins":   {"macro": "b3fa3e21af616e03ebbcb9b2813111fb5856a022",
            "playmaker": "1162ba5e46c737cebf1edc21c7f74beacb825d5c"},
 "traceable": true, "untraceable": [],
 "source": "baked", "root": "/…/sonar"}
```
- `dirty` keeps its meaning, which is an OR over the outer tree and the nested repos (`:51`). A copy has
  `dirty: None`, so `nested_state()` (`:26-37`) yields None and the top-level `dirty` becomes `true` (measure 1). A
  *missing* repo does not set `dirty`: nothing is uncommitted. `traceable: false` covers it.
- `pins` is parsed from the tree's `.github/workflows/tests.yml` at stamp time. If parsing fails, `pins` is `{}` and a
  reason is added. Why record the pins in the stamp rather than read the checkout at install time: the pins belong to
  the outer commit. Once the gate has established that the outer tree is clean, the stamped pins are the pins CI ran for
  that commit. Reading the checkout later would compare against whatever commit the checkout has moved to. It would
  also make `install_agent.sh` refuse an installed bundle that was correct when it was built, as soon as a pin is bumped.
- `traceable` / `untraceable` are `buildid.verdict(payload)`, written **for people and `/api/health`**. The gate does
  not trust them: it recomputes `verdict` from the raw fields (A4). A test feeds `traceable: true` with bad raw fields
  and expects a refusal. The stamp prints each reason to stderr with "check_app.sh will refuse this bundle". That is
  a warning, not a stop, as the stamp is today (`:52-60`).

### A3. The CI pins: one parser
`tests/test_ci_pins.py:21-24` uses a regex that needs `repository`, `ref` and `path` on adjacent lines in that order.
`buildid.pins()` replaces it, and `test_ci_pins._pins` becomes a call to it, so CI, the stamp, the gate (through the
stamp) and the bootstrap read one parser.
- Split the file into step blocks at lines matching `^\s*- ` (a YAML sequence item).
- Inside a block, collect the `repository:`, `ref:` and `path:` scalars in any order. Strip matching single or double
  quotes and a trailing ` #comment`.
- Keep blocks whose `path` is `sonar/macro` or `sonar/playmaker`.
- Fail closed (`ValueError`, with the reason) when: a path is missing or appears twice; a `ref` is not
  `^[0-9a-f]{40}$`; a `repository` is not `wwds-dev/<name>`.
- No YAML library: none is in the lockfile, and the radar note rules out new dependencies. The parser does not need to
  understand YAML in general, only find these three keys in this file's steps. The tests below pin that.

### A4. The gate: `scripts/check_app.sh:36-47`
Replace the grep block with:
```bash
set +e
REASONS="$(python3 -I "$(dirname "$0")/buildid.py" check-stamp "$STAMP" 2>&1)"; RC=$?
set -e
case "$RC" in
  0) ;;                                   # traceable
  3) echo "WARNING: $APP cannot be traced to the code it runs:"
     sed 's/^/  - /' <<<"$REASONS"
     if [[ "$ALLOW_DIRTY" != 1 ]]; then
       echo; echo "Refusing: …"; echo "Fix: commit, scripts/bootstrap_nested.sh, rebuild;"
       echo "or knowingly pass --allow-dirty (ALLOW_DIRTY=1 ./build_app.sh --install)."; exit 1
     fi
     echo "--allow-dirty given: going on. The reasons above stay in the stamp and in /api/health." ;;
  *) echo "error: the build stamp in $APP cannot be read (python3 -I buildid.py exit $RC):"
     sed 's/^/  /' <<<"$REASONS"; exit 1 ;;   # never overridable
esac
```
- **Exit codes.** 0 means traceable. 3 means untraceable, which `--allow-dirty` can override. Any other code refuses
  outright: unreadable or invalid JSON, a stamp that is not an object, an argparse error, a Python crash (exit 1), or
  no `python3` (127). The overridable code is a specific 3, so a crash cannot be overridden into an accept.
- **`verdict(stamp)` returns one line per reason, in a fixed order.** Each line names the drift:
  - `outer: built from a tree with uncommitted changes` (`dirty` is `true`), or `outer: whether the tree was clean is
    unknown` (key missing or `null`). The check is the top-level key of the parsed object, so a nested
    `"dirty": false` cannot satisfy it (domain P1-1).
  - `outer: no commit` (missing, empty, or `sha` not 40 hex).
  - `<name>: not in the stamp (sonar/<name> missing at build time, or skipped by an older stamper)`, for each name in `NESTED_REPOS`. The
    names are hardcoded in `buildid.py` as `("macro", "playmaker")`, and a test asserts that they equal
    `sonar.version.NESTED_REPOS`.
  - `<name>: a copy with no git history; its code cannot be named` (`commit` empty).
  - `<name>: uncommitted changes` / `<name>: whether it is clean is unknown` (`dirty` not `false`).
  - `pins: the stamp records no CI pins` (an old stamp, or the parse failed), or `pins: <reason>`.
  - `<name>: stamp <sha[:9]>, CI pins <pin[:9]>` (sha ≠ pin; owner Q1).
- **Order.** `install_app.sh:73-77` runs `check_app.sh` (step 1) before any `rm -rf "$STAGE"`, the copy (`:79-82`), the
  disable/bootout (`:89-96`) and the swap (`:99-102`). Because the new checks live inside `check_app.sh`, a refusal
  exits with the installed app, the agent's pid and launchd state as they were, and no `.SONAR.app.new` (domain P2-2).
  `install_agent.sh:124-134` uses the same gate before it writes the plist. `build_app.sh` runs `set -e`, so a refusal
  also skips its cleanup (`:105-107`). `dist.noindex/` stays in the checkout. That is harmless, because nothing was staged.
- **One override flag.** `--allow-dirty` / `ALLOW_DIRTY=1` already passes through `build_app.sh:102-103`,
  `install_app.sh:70-76,110` and `install_agent.sh:98,132`. A separate `--allow-untraced` would mean three more
  plumbing paths for the same decision. The warning lists each reason, so the override names what it accepts (measure 2).
- **The fixture tests can drive it.** `tests/test_agent_from_bundle.py:63-70` copies scripts into a scratch project;
  `buildid.py` joins that list. The fixture PATH puts `/usr/bin` before Homebrew, so the gate runs under Python 3.9
  there, and that is the version check.

### A5. Bootstrap: `scripts/bootstrap_nested.sh [--move]` (new)
`set -euo pipefail`; `cd "$(dirname "$0")/.."`. `TOP=$(git rev-parse --show-toplevel)`.
- **Lock.** `mkdir "$TOP/.nested-bootstrap/lock"`. It is atomic, and it refuses if the lock exists, since sessions
  share worktrees. A `trap` removes it. `/.nested-bootstrap/` is added to `.gitignore`. pytest's default
  `norecursedirs` skips `.*`, and ruff respects `.gitignore`.
- **Pins.** `python3 -I scripts/buildid.py pins --shell .github/workflows/tests.yml` prints
  `sonar/macro wwds-dev/sonar_macro <sha>` lines. A parse error aborts before anything is touched.
- **Remote URL.** `buildid.py remote-url "$(git remote get-url origin)" wwds-dev/sonar_macro` swaps the last two path
  parts of the outer origin. `https://github.com/wwds-dev/sonar.git` becomes `https://github.com/wwds-dev/sonar_macro.git`,
  and scp-style `git@github.com:wwds-dev/sonar.git` becomes `git@github.com:wwds-dev/sonar_macro.git`. With no
  origin, or an unrecognised shape, it uses `https://github.com/<repository>.git`, matching `actions/checkout`'s
  default host. This keeps the outer repo's transport and credentials (today https and the keychain helper; checked
  with `git remote -v`).
- **Main checkout.** The first `worktree <path>` record of `git worktree list --porcelain`, which is always the main
  worktree. It is cross-checked against `dirname "$(git rev-parse --path-format=absolute --git-common-dir)"`. If the
  two disagree, or the path has no `sonar/<name>/.git`, there is no local fallback. When `MAIN == TOP` the script is
  in the main checkout, and the "fallback" would be the target itself, so it is skipped.
- **Clone** into `"$TOP/.nested-bootstrap/<name>.tmp.$$"`:
  1. `GIT_TERMINAL_PROMPT=0 git clone --quiet --no-checkout "$URL" tmp`. With prompts off, missing auth fails fast
     instead of hanging.
  2. On failure: `git clone --quiet --no-checkout "$MAIN/sonar/<name>" tmp`, then
     `git -C tmp remote set-url origin "$URL"`, then print `WARNING: <name> cloned from the main checkout's local repo
     (<path>), not <URL>: the remote was unreachable; pin <sha9> may not be pushed.` (owner Q2).
  3. `git -C tmp cat-file -e "<sha>^{commit}"`, or fail with `<name>: pin <sha9> is not in <source>`.
  4. `git -C tmp -c advice.detachedHead=false checkout --quiet --detach <sha>`.
- **Per target `sonar/<name>`:**
  | State | Action |
  |---|---|
  | absent | clone (above), then `mv tmp sonar/<name>` after re-checking that the target is absent |
  | copy (exists, no `.git`) | clone first; `diff -rq -x __pycache__ -x '*.pyc' -x .DS_Store copy tmp` and print "identical to the pin" or "differs from the pin in N files" (first 15 listed); `mv copy .nested-bootstrap/<name>.copy-<UTC yyyymmddThhmmss>`; `mv tmp sonar/<name>`. The copy is never deleted. A failure before the first `mv` leaves it in place |
  | repo, `git status --porcelain --untracked-files=no` non-empty **or failing** | **refuse**: `<name> has uncommitted work (or git cannot read it); commit or set it aside yourself.` Nothing is touched |
  | repo, clean, HEAD = pin | `already at the pin`, no-op |
  | repo, clean, HEAD ≠ pin | refuse, printing HEAD, branch and the two commands to move it. With `--move`: fetch the pin if absent, `checkout --detach <pin>`, print the old branch/HEAD to return to. `--move` is opt-in because in the main checkout this is the owner's working repo |
- **Postcondition** (exit 1 otherwise): each `sonar/<name>` is a repo with `HEAD == pin` and a clean status. The
  script ends by printing `./run-tests.sh tests/test_ci_pins.py -q` as the check (measure 3).
- **Rejected.** `git worktree add` from the main checkout's nested repos: it shares refs and the object store, locks
  branches, and ties this tree to another repo's lifetime. Symlinks to the main checkout: the build would see the
  main checkout's HEAD and dirt, not the pin, and two trees would share mutable code. `git submodule`: a non-goal
  (module-boundary ADR).

### A6. Release identity (print-only)
`build_app.sh` calls `python3 -I scripts/buildid.py tag-command _build_info.json --repo .` at the end. That is after
`--install` succeeds (after `:107`), or after the self-test when there is no install (`:108-112`). It never runs git
write commands. Its logic:
1. If `verdict(stamp)` is non-empty, print `No release tag proposed: this build cannot be traced (…reasons)` and stop.
2. Tag name: `v{major}.{build:03d}`; target: stamp `sha`.
3. Existing tag: `git rev-parse -q --verify "refs/tags/<tag>^{commit}"`.
   - On a different commit: **refuse**, `tag <tag> already names <sha9>; this build is <sha9>: the number names two
     commits, so this build is not a release`.
   - On the same commit: `<tag> already tags this commit`, and no command.
   - The remote is not queried (no network in a print step). `git push` refuses to move an existing remote tag
     without `--force`, which is the backstop.
4. First-parent master. Is `sha` in `git rev-list --first-parent refs/remotes/origin/master`? If not, is it in
   `refs/heads/master`?
   - On neither: `WARNING: <sha9> is not on first-parent master, so it is not a release (VERSIONING.md). Merge to master and build there.`
   - Only on local `master`: `not on origin/master as of the last fetch; push master first`.
   - `origin/master` absent: say so, and use local `master`.
   - Why first-parent: along the first-parent chain, `rev-list --count` strictly increases. Each step adds the
     merged-in commits plus the merge, at least 1. So within first-parent `master`, the number maps to one commit.
     The 175 duplicate numbers all sit off that chain. `merge-base --is-ancestor` is not enough, because side-branch
     commits are ancestors too.
5. When a command is proposed, print (the owner runs both):
   `git tag -a v2.NNN <sha40> -m "v2.NNN; macro <sha9>, playmaker <sha9>"` and `git push origin v2.NNN`.
   The nested SHAs go in the tag message, so the record outlives the stamp.
- **Retroactive.** `buildid.py tag-command --retroactive 2.340 8e7d024 --repo .` checks that
  `git rev-list --count 8e7d024` is 340 (verified: 340), applies steps 3 and 4 (verified on first-parent master), and
  prints:
  `git tag -a v2.340 8e7d02460475aa8c4463f9932fed646d6a4be805 -m "v2.340 (retroactive); nested code unknown"`.
  It also prints: "the bundle's stamp had `nested: {}`; the macro and playmaker code it ran cannot be recovered".
  The Build phase runs it once and pastes the output into the verify note. It is not wired into `build_app.sh`.
- **Open point (owner Q-A1).** Measure 5 says "warns" off first-parent master. This design warns **and prints no tag
  command**, because a tagged branch commit would reintroduce a duplicate number. Install is not blocked.

### A7. Ledger `build` field (scope e)
**Writer.** `core.py:699-700` becomes `return buildid.build_id(self.build)[:64]` (via `version`, see A1). `self.build`
is `version.provenance()` (`core.py:210`), read once at start. Grammar, ASCII, at most 54 characters by construction:
```
<version>+<outer>/m:<macro>/p:<playmaker>[~]
  version  = provenance["version"] (unchanged leading token, e.g. v2.364), or "unknown" when absent (the old fallback,
             returned alone)
  outer    = provenance["commit"][:12], or "?" when empty
  macro,
  playmaker= nested[name]["commit"][:12]; "?" if present with an empty commit (a copy); "-" if absent
  ~        = provenance["dirty"] is not False (dirty or unknown): not exactly these commits
e.g.  v2.364+9aa9bd1/m:b3fa3e2/p:1162ba5          (34 chars)
      v2.340+8e7d024/m:-/p:-                        (what v2.340 would have written)
```
- **Why commits and not a digest:** `git show <commit>` reads a commit directly. A digest needs a lookup table that
  no one keeps. The length fits: with a version of up to 10 characters, 10 + 1 + 12 + 3 + 12 + 3 + 12 + 1 = 54 ≤ 64.
- **Why `+`:** it is semver's build-metadata separator. `build.split("+", 1)[0]` gives back the old value exactly.
- `ledger_new` (`calibration.py:924-929`) writes the same string to `created_by` for a **new** ledger only. The live
  ledger's header was written once and is never rewritten.

**Every reader, as of 9aa9bd1** (grep `"build"`, `_ledger_build`, `created_by`, `LEDGER_LOOK_FIELDS` over `sonar/`,
`ui/`, `main.py`, `scripts/`, `tests/`. There is no top-level `research/`, and `sonar/research/` has no reader):
| Site | Use | Old entries | New entries |
|---|---|---|---|
| `core.py:783,792` → `ledger_new` → `created_by` | writer | untouched | new format |
| `core.py:1004` → `ledger_merge` | writer | `copy.deepcopy(old)` (`calibration.py:1185`); skips ids and looks already present (`:1191`, `:1207`) | new format |
| `calibration.py:1194-1195`, `:1209` | sets `build` on a new record | none | as passed |
| `calibration.py:1003` `_check_entry`, `:1037` `_check_look`, `:1097` header | `_is_text`: str of length 1..500 (`:959-960`, `LEDGER_TEXT_MAX` `:880`) | pass (e.g. `"v2.261"`) | pass (≤ 64) |
| `calibration.py:768` readout | **drops** `decided_at` and `build` from ledger entries | not shown | not shown |
| `calibration.py:875-876` field tuples | names only | — | — |
| `ui/app.py` (`_sh_ledger*`, `:991-1110`) | reads `created_at`, `retired`, `error`; never `build` or `created_by` | — | — |
| `server.py:433` alarm | `self.build["version"]`, not the ledger | — | — |
| `tests/test_shadow_ledger.py:256` | asserts `rec["build"] == live.build["version"]` | — | **update** to `version.build_id(live.build)`. The spec changed; the test is not weakened |
| `tests/test_shadow_ledger.py:315`, `:1519`, `:2019` | pass literal builds | unaffected | unaffected |
| `tests/test_shadow_ledger.py:307` (L-4 property), `:2189-2193` (q48) | assert `created_by` is never rewritten | unaffected | unaffected (MV P3-3) |
`self.build` (`core.py:210`) and the pins beside it are read **once**, when `Live` is built; a later change on disk does
not reach the string mid-run (MV P3-3; tested).
Nothing parses `build` as a version, so old and new entries read the same. Mixed files are valid. Past entries are never
rewritten: `core.py:975` re-dumps the whole parsed dict with `indent=1`, and parse→dump of an unchanged dict gives
the same text for each old entry.

**ADR.** Yes: **ADR 0002 Amendment 2** (proposed, appended to `docs/adr/0002-shadow-time-stop-grade.md`). The
ledger spec (`docs/specs/shadow-ledger.md:375`) defines `build` and `created_by` as `provenance()["version"]`, and the
format is permanent in a write-once file. The amendment changes the meaning for new records only. `model-validator`
checks it before Build (scope e).

### A8. Migration of existing state
- **Installed v2.340 and the running agent.** Not touched. `check_app.sh` runs only on install. A launchd restart does
  not run it, so the 30-day run goes on. However, `install_agent.sh` in bundle mode (`:124-134`), re-run against the
  installed v2.340, will now refuse it (`nested: {}`, no pins). That is intended. The owner can override with
  `--allow-dirty`, which lists the reasons. Release notes must say so.
- **Old stamps** (no `sha`, `pins`, `traceable`) are still read by `_baked()` and `provenance()`, which only use
  `build`, `commit`, `dirty` and `nested`. The gate refuses them.
- **The ledger:** see A7. No rewrite and no schema bump (`LEDGER_SCHEMA` stays 1). The field set is unchanged; only
  the value of new records changes.
- **This worktree** holds copies. Run `scripts/bootstrap_nested.sh` before the items 1+2+3 build. The release build
  must come from first-parent `master` after the merge (A6), with the nested repos at the pins.
- **Same hole, checkout mode.** `install_agent.sh:150` (`[[ -e "$nested/.git" ]] || continue`) skips a copy in
  `--checkout` mode. Recommended in this change: treat a copy as a refusal reason that `--allow-dirty` can override
  (owner Q-A2).

### A9. Failure modes
| Failure | Effect | Handling |
|---|---|---|
| `python3` missing, or the Xcode CLT stub | exit 127 | refused, not overridable; the message names python3 |
| `python3` older than 3.9 | SyntaxError, exit 1 | refused; 3.9 is the floor (system python) and is tested in the fixture |
| stamp hand-edited to `traceable: true` | — | the gate ignores the flag; it is sealed in the bundle anyway (codesign is checked first, `:28`) |
| `tests.yml` reshaped (keys reordered, quoted, commented) | — | parser tests; any unparseable shape fails closed with `pins: <reason>` |
| pin bumped after a build | — | the stamp's own pins decide, so an installed bundle stays valid |
| remote unreachable, or auth prompt | `GIT_TERMINAL_PROMPT=0` fails fast | local fallback with a warning |
| pin not pushed and not local | — | bootstrap fails for that repo; nothing moved |
| two bootstraps at once | — | `mkdir` lock |
| copy holds real local edits | — | moved aside, never deleted; the diff is printed |
| build off first-parent master | — | installs if traceable; no tag proposed (Q-A1) |
| same number on two commits | — | the tag command refuses on an existing tag; first-parent rule |
| the 64-char cap | — | ≤ 54 by construction; `[:64]` kept as a backstop; a test covers the worst case |
| short-commit length grows (auto-abbrev) | — | capped at 12 in `build_id`; the gate uses `sha` |

### A10. Test strategy (tests first; all in the normal suite, native and offscreen)
- `tests/test_version.py`, measure 1:
  - In a tmp tree, a copy yields `{"commit": "", "sha": "", "dirty": None}` and a stamp with top-level
    `dirty: true` and `traceable: false`.
  - Two clean git repos (`git init` plus a commit in tmp) yield both keys with a 7+ hex `commit`, a 40-hex `sha`,
    `dirty: false`.
  - An absent dir yields no key and `traceable: false`.
  - Mutation: restore the `continue` at `:327-328`, and the copy test fails.
- `tests/test_agent_provenance.py:93-100` currently asserts a copy is skipped, which encodes the bug. Change it to
  expect the copy entry. Update `:78-90` and `tests/test_agent_from_bundle.py:466-485` for `sha`.
- `tests/test_buildid.py` (new):
  - `verdict` table: each A4 reason alone, plus "outer dirty, nested clean" (domain P1-1), `traceable: true` with bad
    raw fields, an old v2.340-shape stamp, and a full clean stamp → `[]`.
  - `pins`: the real `tests.yml`; reordered, quoted, commented; duplicate path; short ref; foreign owner.
  - `remote-url`: https, scp-style, no origin.
  - `build_id`: examples, `?`, `-`, `~`, `unknown`; worst-case length ≤ 64; `split("+")[0] == version`.
  - Names equal `sonar.version.NESTED_REPOS`.
  - `tag-command` against a tmp repo with a first-parent chain and a merged side branch:
    - first-parent commit → command printed;
    - side commit → warning, no command;
    - existing tag elsewhere → refusal;
    - same commit → "already tags";
    - `--retroactive` count mismatch → refusal.
- `tests/test_agent_from_bundle.py`, measure 2:
  - `_bundle()` (`:41-60`) writes a full clean stamp at fixture pins by default, with a `stamp=` dict override.
  - `buildid.py` is added to the copied scripts (`:65-66`).
  - Parametrized refusals over each A4 case, through both `install_agent.sh` and `install_app.sh`. Each asserts the
    reason text, `<repo>: stamp <sha>, CI pins <sha>` included.
  - `--allow-dirty` accepts exit-3 cases and prints the reasons. It does not accept a corrupt stamp (exit 2).
  - For every refusal via `install_app.sh`: no `.SONAR.app.new`, the installed marker is unchanged, and the fake
    `launchctl` recorded no `disable`/`bootout`. Extend `:239-246`; this is the scripted half of domain P2-2.
- `tests/test_ci_pins.py`: `_pins` → `buildid.pins`. The skip at `:36-37` stays for unbootstrapped trees. Measure 3
  is run in a fresh worktree after the bootstrap, and must pass with no skip.
- `tests/test_bootstrap_nested.py` (new):
  - Set-up: a tmp "remote" bare repo pair and a tmp main checkout with a worktree; `file://` URLs; no network.
  - Cases: absent → cloned at the pin; copy → moved aside, diff reported, cloned; dirty repo → refused and untouched
    (mtime and HEAD); clean off-pin → refused, and moved with `--move`; remote broken → local fallback with the
    warning; pin missing everywhere → fails, nothing moved; lock held → refused.
- `tests/test_shadow_ledger.py`: `:256` updated. New: a ledger holding `"v2.261"` entries, merged with a readout built
  under the new `build_id`, keeps each old entry and look byte-identical in the `indent=1` text. New records carry the
  new string. `ledger_parse` accepts the mixed file. The existing `:305-316` invariants stay.
- Mutation checks (QA): drop the top-level anchor (let any `dirty: false` pass); make exit 3 the crash code; drop the
  pin comparison; skip copies in `_nested`; drop the first-parent check. Each must turn a test red.
- Not in the suite: measure 4, the real-bundle build and the negative run on a copy-only tree with the live agent's
  pid and `/Applications/SONAR.app` checked. QA does this, owner-gated.

### A11. Gate
**GATE applies.** The change touches state (the write-once ledger's `build` meaning, the stamp format the installer
trusts), and the install path that guards the live agent. Owner approval is needed for this section and ADR 0002
Amendment 2 before Build; `domain-finance` reviews this section, and `model-validator` reviews A7.

### Owner questions (Architect)
- **Q-A1.** Off first-parent master, print **no** tag command (recommended) or warn and still print it (measure 5 as
  written)?
- **Q-A2.** Close the same hole in `install_agent.sh --checkout` (`:150`) in this change (recommended)?
- **Q-A3.** One override flag (`--allow-dirty`, now also covering untraceable or drifted nested repos; recommended) or a
  separate `--allow-untraced`?

## Build notes (engineer, 2026-10-19)

Playbook `docs/playbooks/engineer.md` is `status: baseline` (last-reviewed 2026-10-10): stale by the AGENTS.md rule.
Built as A1-A11 with the owner's Architect-gate answers (relayed by the orchestrator): Q-A1 no tag command off
first-parent master; Q-A2 the `--checkout` copy hole closed; Q-A3 one flag, `--allow-dirty`; re-running install on the
installed v2.340 is refused without `--allow-dirty`; the gate always runs in `install_app.sh`. Where the build departs
from or adds to the text above:

1. **`build_id` lives in `sonar/version.py`** (A1's alternative), with a copy in `scripts/buildid.py`, both held to one
   fixture table (`tests/test_buildid.py`). The cross-load would fail in a frozen bundle, which has no `scripts/`.
2. **Grammar, as built** (MV P3-1, P3-2; domain P3-2): `<version>[~][!]+<outer>/m:<macro>/p:<playmaker>`. The markers
   sit right after the version; `!` means the nested code is not shown to be the recorded CI pins (drift after
   `--allow-dirty`, a copy, absent, or no pins known). A version too long for 12-hex fields shortens them (to 7) before
   any cut; a test sits at the 64-character edge. No version gives `unknown+…` with the commits kept. A copy (`?`) has
   no content digest. `build_id(prov, pins)` takes the pins as a second argument: a bundle's come from its stamp, a
   checkout's from its own `tests.yml` through `buildid.pins` (`version.recorded_pins()`), read with `self.build`.
3. **Origin reasons** (domain P2-1), exit 3 so `--allow-dirty` can take them: `outer <sha9> is not on any origin ref as
   of the last fetch`, and the same for each nested sha in the checkout's `sonar/<name>` (or "cannot be checked here"
   when that is not a repo). Local refs only (`for-each-ref --contains … refs/remotes/origin`), no network.
   `check_app.sh` passes `--repo <project root>`; `verdict()` itself stays pure. The bootstrap's local fallback drops
   the clone's `refs/remotes/origin/*` (they are the main checkout's branches), so this check is not fooled.
4. **Stamp:** `pins_error` is written beside `pins: {}` when the pins cannot be parsed, so the gate's reason is
   `pins: <reason>`.
5. **Bootstrap report** (domain P2-2). Each run writes its per-repo lines ("the copy was identical to the pin" /
   "differed from the pin in N files" with up to 15 listed, "cloned", "already at the pin") to
   `.nested-bootstrap/report-<UTC>.txt` and prints its path. **Verify** pastes that report and the install time into
   `docs/audit/build-traceability-verify.md`; the model-validator decides from it whether look 1 needs a note or a
   split at that boundary.
6. **Gate always** (owner, domain P3-1): `install_app.sh` runs `check_app.sh` whether or not the agent is on the app.
   `test_without_the_agent_on_the_app_it_only_copies` now uses a clean bundle, and a new test shows a dirty one is
   refused there too; this is the third test changed by design (with `test_agent_provenance.py` nested reads and
   `test_shadow_ledger.py` L-3).
7. **Not done here:** measure 3 (a fresh worktree bootstrapped, `test_ci_pins` with no skip) and measure 4 (the real
   bundle, the negative run, the agent's pid) are QA's, owner-gated; this worktree's copies were not bootstrapped. The
   retroactive v2.340 command was run once against this checkout (output in the build report); no tag was created.

**Fix round (2026-10-19)**, on the P3s of `docs/audit/build-traceability-{code-reviewer,security,qa,domain-finance}.md`
(no P0, P1 or P2 in any):
- **Stamp:** HEAD is resolved once and the count, short commit and date come from that sha (CR P3-1). New key
  `outer_dirty` (the outer tree alone); the outer reason reads it, falling back to `dirty` for older stamps, so a dirty
  nested repo is not also a dirty outer tree (domain P3-2). A stamp whose `dirty` is not false with no cause named is
  refused (`dirty: … names no cause`). The comment no longer says `/api/health` carries `traceable` (CR P3-8).
- **Verdict:** `outer: commit X is not sha Y` and `<name>: commit X is not sha Y` (CR P3-1). `tag-command` refuses when
  `rev-list --count <sha>` is not the stamped build, and a major that is not digits (CR P3-1, Sec P3-8a).
- **Pin parser:** duplicate keys matter only in pin steps; the same pin in several jobs is allowed, different pins for
  one path refused (CR P3-3). Refused: a flow mapping (`with: {`), a pin step that is not a plain `actions/checkout`
  (e.g. fake keys in `run: |`), and any non-comment line outside the pin steps naming `sonar/macro`, `sonar/playmaker`
  or `sonar_<name>` (Sec P3-1).
- **Origin check:** a nested sha is looked for in this checkout's `sonar/<name>`, then in the main checkout's (CR P3-5).
  The `--allow-dirty` message now says the origin reasons are stored nowhere and must go in the verify note (domain
  P3-1).
- **Bootstrap:** every step in `clone_pin` is checked by hand, and the fallback clone must end with no
  `refs/remotes/origin` (CR P3-2); `remote-url` refuses an origin with credentials, a leading `-` or `::`, and printed
  URLs carry no userinfo (CR P3-4, Sec P3-2, P3-5); `git clone … --` with `credential.interactive=never`,
  `http.lowSpeedLimit/Time`, `transfer.fsckObjects=true`, `GIT_SSH_COMMAND` in batch mode with a connect timeout, and
  `--no-local` for the fallback (Sec P3-3, P3-4); a symlinked nested dir is refused (Sec P3-6); the aside path is
  printed between the two moves, and the copy is moved back if the second fails (CR P3-6, Sec P3-8b).
- **Tests:** the postcondition (QA P3-1, M25), `_checkout_pins` and the `[:64]` cut (QA P3-2), and the two weak tests
  (QA P3-4) now have real assertions.
- **Deferred (owner's call, TODO):** Sec P3-7, untracked importable files in a nested repo count as clean
  (`_dirty` uses `--untracked-files=no`; older than this change). QA P3-3, a test of the `build_app.sh` tag-command
  wiring.
