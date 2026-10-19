#!/usr/bin/env python3
"""Whether a build can be named, in one place (docs/specs/build-traceability.md A1).

A release is the pair (number, commit) plus the commits of the two nested repos
(`sonar/macro`, `sonar/playmaker`) that feed live scoring. v2.340 was installed
with `"nested": {}` and passed the gate, because the stamp skipped copies, the
stamp read an empty dict as clean, and `check_app.sh` grepped for any
`"dirty": false`. Everything that judges a build's identity now lives here, so
there is one guard, not three.

Runs under ``python3 -I`` on the system Python (3.9): stdlib only, no `sonar`
import, nothing local on `sys.path`. `sonar/version.py` keeps its own copy of
:func:`build_id`, because a frozen bundle has no `scripts/`; the two are tested
against one fixture table.

    buildid.py check-stamp <stamp.json> [--repo <dir>]
        exit 0 traceable; 3 untraceable (reasons on stdout, one per line; the
        only code --allow-dirty may override); anything else refuses outright
    buildid.py pins [--shell] <tests.yml>
    buildid.py remote-url <origin-url> <owner/name>
    buildid.py tag-command <stamp.json> --repo <dir>
    buildid.py tag-command --retroactive <MAJOR.BUILD> <commit> --repo <dir>

The tag command is print-only: nothing here writes to git.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

#: Must equal `sonar.version.NESTED_REPOS` (a test holds them together).
NAMES = ("macro", "playmaker")
PIN_PATHS = tuple(f"sonar/{n}" for n in NAMES)
OWNER = "wwds-dev"

#: The ledger's text cap (`sonar/core.py` `_ledger_build`).
BUILD_ID_MAX = 64

EXIT_UNTRACEABLE = 3
EXIT_UNREADABLE = 2
GIT_TIMEOUT_S = 10

_SHA = re.compile(r"^[0-9a-f]{40}$")
_KEY = re.compile(r"^\s*(?:-\s+)?(uses|run|repository|ref|path)\s*:\s*(.*?)\s*$")
_ITEM = re.compile(r"^\s*-\s")
#: A line naming a nested repo or its remote. Outside a pin step, such a line
#: means CI may check the repo out some other way than the parser sees.
_MENTION = re.compile(r"sonar/(?:macro|playmaker)|sonar_(?:macro|playmaker)")
_FLOW = re.compile(r"\bwith\s*:\s*\{")


def _is_sha(value) -> bool:
    return isinstance(value, str) and bool(_SHA.match(value))


# --------------------------------------------------------------------------- #
# The CI pins (A3): one parser for CI's test, the stamp and the bootstrap
# --------------------------------------------------------------------------- #
def _scalar(raw: str) -> str:
    value = re.sub(r"\s+#.*$", "", raw).strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        value = value[1:-1]
    return value


def pins(text: str) -> dict:
    """``{"sonar/macro": (repository, sha40), "sonar/playmaker": (...)}`` from
    `.github/workflows/tests.yml`. Not a YAML parser: it finds the keys of each
    `actions/checkout` step, in any order, quoted or not, with or without a
    trailing comment. It refuses (ValueError, with the reason) any shape where
    CI could read the file differently: a flow mapping (`with: {…}`), a step
    naming a nested path that is not a plain checkout, a pin step with a key
    twice, a nested repo named on any other line, or two different pins for
    one path. The same pin in several jobs is allowed."""
    blocks: list[dict] = []
    current: dict | None = None
    for no, line in enumerate(text.splitlines(), start=1):
        if line.lstrip().startswith("#"):
            continue
        if _FLOW.search(line):
            raise ValueError(f"line {no}: a flow mapping (with: {{...}}) is not read here")
        if _ITEM.match(line):
            current = {"keys": {}, "lines": []}
            blocks.append(current)
        if current is None:
            if _MENTION.search(line):
                raise ValueError(f"line {no} names a nested repo outside any step")
            continue
        current["lines"].append((no, line))
        m = _KEY.match(line)
        if m:
            current["keys"].setdefault(m.group(1), []).append(_scalar(m.group(2)))
    found: dict = {}
    for block in blocks:
        keys = block["keys"]
        if not any(p in PIN_PATHS for p in keys.get("path", [])):
            for no, line in block["lines"]:
                if _MENTION.search(line):
                    raise ValueError(f"line {no} names a nested repo outside a pin step")
            continue
        for key, values in keys.items():
            if len(values) > 1:
                raise ValueError(f"a pin step names {key!r} twice")
        if not keys.get("uses", [""])[0].startswith("actions/checkout@") or "run" in keys:
            raise ValueError(f"the step for {keys['path'][0]} is not a plain actions/checkout")
        path = keys["path"][0]
        repo, ref = keys.get("repository", [""])[0], keys.get("ref", [""])[0]
        name = path.split("/", 1)[1]
        if repo != f"{OWNER}/sonar_{name}":
            raise ValueError(f"{path}: repository {repo!r} is not {OWNER}/sonar_{name}")
        if not _SHA.match(ref):
            raise ValueError(f"{path}: ref {ref!r} is not a full 40-hex commit")
        if path in found and found[path] != (repo, ref):
            raise ValueError(f"{path} is checked out twice, at different pins")
        found[path] = (repo, ref)
    missing = [p for p in PIN_PATHS if p not in found]
    if missing:
        raise ValueError(f"no pinned checkout step for {', '.join(missing)}")
    return found


# --------------------------------------------------------------------------- #
# The verdict (A4): the reasons a stamp cannot be traced
# --------------------------------------------------------------------------- #
def verdict(stamp: dict) -> list:
    """One line per reason, in a fixed order; ``[]`` means traceable. Read from
    the raw fields only: the stamp's own ``traceable`` is for people."""
    reasons = []
    # The outer tree's own state: `outer_dirty`, a top-level key of the parsed
    # object, so a nested "dirty": false cannot stand in for it (domain P1-1);
    # `dirty` (outer OR nested) for a stamp older than the key (domain P3-2).
    dirty = stamp.get("outer_dirty", stamp.get("dirty"))
    if dirty is True:
        reasons.append("outer: built from a tree with uncommitted changes")
    elif dirty is not False:
        reasons.append("outer: whether the tree was clean is unknown")
    commit, sha = stamp.get("commit"), stamp.get("sha")
    if not (isinstance(commit, str) and commit) or not _is_sha(sha):
        reasons.append("outer: no commit")
    elif not sha.startswith(commit):
        # Read at two moments: another session may have committed between.
        reasons.append(f"outer: commit {commit} is not sha {sha[:9]}")

    nested = stamp.get("nested")
    nested = nested if isinstance(nested, dict) else {}
    named = []
    for name in NAMES:
        if not isinstance(nested.get(name), dict):
            reasons.append(f"{name}: not in the stamp (sonar/{name} missing at build time, or skipped by an older stamper)")
    for name in NAMES:
        repo = nested.get(name)
        if isinstance(repo, dict) and not (isinstance(repo.get("commit"), str)
                                           and repo.get("commit")):
            reasons.append(f"{name}: a copy with no git history; its code cannot be named")
    for name in NAMES:
        repo = nested.get(name)
        if not isinstance(repo, dict) or not repo.get("commit"):
            continue
        if repo.get("dirty") is True:
            reasons.append(f"{name}: uncommitted changes")
        elif repo.get("dirty") is not False:
            reasons.append(f"{name}: whether it is clean is unknown")
        if _is_sha(repo.get("sha")) and not repo["sha"].startswith(repo["commit"]):
            reasons.append(f"{name}: commit {repo['commit']} is not sha {repo['sha'][:9]}")
        named.append(name)

    recorded = stamp.get("pins")
    error = stamp.get("pins_error")
    if isinstance(error, str) and error:
        reasons.append(f"pins: {error}")
    elif not isinstance(recorded, dict) or not recorded:
        reasons.append("pins: the stamp records no CI pins")
    else:
        bad = [n for n in NAMES if not _is_sha(recorded.get(n))]
        if bad:
            reasons.append(f"pins: no valid CI pin for {', '.join(bad)}")
        for name in named:
            pin, sha = recorded.get(name), nested[name].get("sha")
            if _is_sha(pin) and sha != pin:
                shown = sha[:9] if isinstance(sha, str) and sha else "(none)"
                reasons.append(f"{name}: stamp {shown}, CI pins {pin[:9]}")
    if not reasons and stamp.get("dirty") is not False:
        # A stamp whose summary says dirty but names no cause is not clean.
        reasons.append("dirty: the stamp says dirty or unknown but names no cause")
    return reasons


def _git(repo: str, *args: str):
    """(returncode, stdout) — or (None, why) when git cannot be run at all."""
    try:
        r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True,
                           timeout=GIT_TIMEOUT_S)
    except (OSError, subprocess.SubprocessError) as exc:
        return None, str(exc)
    return r.returncode, r.stdout.strip()


def _on_origin(repo: str, sha: str):
    """True / False, or None when it cannot be checked. Local refs only: no
    fetch, so "as of the last fetch". A directory without its own `.git` is
    not asked: git would walk up and answer for the repo around it."""
    if not os.path.exists(os.path.join(repo, ".git")):
        return None
    rc, _ = _git(repo, "cat-file", "-e", f"{sha}^{{commit}}")
    if rc is None:
        return None
    if rc != 0:
        return False
    rc, out = _git(repo, "for-each-ref", "--contains", sha, "--format=%(refname)",
                   "refs/remotes/origin")
    if rc != 0:
        return None
    return bool(out)


def _main_checkout(repo: str):
    """The main worktree of ``repo``'s repository (its first worktree record),
    or None."""
    rc, out = _git(repo, "worktree", "list", "--porcelain")
    if rc != 0 or not out.startswith("worktree "):
        return None
    return out.splitlines()[0][len("worktree "):]


def _nested_on_origin(repo: str, name: str, sha: str):
    """This checkout's `sonar/<name>`, then the main checkout's (code review
    P3-5: an installer run from a worktree that holds copies would otherwise
    refuse a bundle built correctly in the main checkout). True if either has
    it on origin; False if one was asked and neither has; None if neither
    could be asked."""
    places = [os.path.join(repo, "sonar", name)]
    main = _main_checkout(repo)
    if main and os.path.realpath(main) != os.path.realpath(repo):
        places.append(os.path.join(main, "sonar", name))
    answers = [_on_origin(p, sha) for p in places]
    if True in answers:
        return True
    return False if False in answers else None


def origin_reasons(stamp: dict, repo: str) -> list:
    """Overridable reasons (domain P2-1): a commit the ledger names should
    still resolve after the branch that built it is gone."""
    reasons = []
    sha = stamp.get("sha")
    if _is_sha(sha):
        on = _on_origin(repo, sha)
        if on is False:
            reasons.append(f"outer {sha[:9]} is not on any origin ref as of the last fetch")
        elif on is None:
            reasons.append(f"outer {sha[:9]}: whether it is on origin cannot be checked "
                           f"here ({repo} is not a readable git repo)")
    nested = stamp.get("nested")
    nested = nested if isinstance(nested, dict) else {}
    for name in NAMES:
        entry = nested.get(name)
        sha = entry.get("sha") if isinstance(entry, dict) else None
        if not _is_sha(sha):
            continue
        on = _nested_on_origin(repo, name, sha)
        if on is False:
            reasons.append(f"{name} {sha[:9]} is not on any origin ref as of the last fetch")
        elif on is None:
            reasons.append(f"{name} {sha[:9]}: whether it is on origin cannot be checked "
                           f"here (sonar/{name} is not a git repo here or in the main checkout; "
                           "scripts/bootstrap_nested.sh)")
    return reasons


# --------------------------------------------------------------------------- #
# The ledger's build string (A7; sonar/version.py holds the frozen copy)
# --------------------------------------------------------------------------- #
def _off_pins(nested: dict, recorded) -> bool:
    if not isinstance(recorded, dict) or not recorded:
        return True
    for name in NAMES:
        entry = nested.get(name)
        if not isinstance(entry, dict) or entry.get("sha") != recorded.get(name):
            return True
    return False


def build_id(prov: dict, recorded_pins=None) -> str:
    """``<version>[~][!]+<outer>/m:<macro>/p:<playmaker>``, at most 64 ASCII.

    ``~``: the code was dirty or of unknown state. ``!``: the nested code is not
    shown to be the CI pins (drifted, a copy, absent, or no pins known). Both sit
    right after the version, so no cut can drop them. ``?`` is an unknown commit
    (a copy: there is no content digest), ``-`` an absent repo. Commits are at
    most 12 hex, shortened (to 7) rather than cut when a long version would pass
    the cap."""
    prov = prov or {}
    version = str(prov.get("version") or "unknown")
    nested = prov.get("nested")
    nested = nested if isinstance(nested, dict) else {}
    marks = ("~" if prov.get("dirty") is not False else "") + \
            ("!" if _off_pins(nested, recorded_pins) else "")

    def field(commit, width):
        commit = str(commit or "")
        return commit[:width] if commit else "?"

    def sub(name, width):
        entry = nested.get(name)
        return field(entry.get("commit"), width) if isinstance(entry, dict) else "-"

    text = ""
    for width in range(12, 6, -1):
        text = (f"{version}{marks}+{field(prov.get('commit'), width)}"
                f"/m:{sub('macro', width)}/p:{sub('playmaker', width)}")
        if len(text) <= BUILD_ID_MAX:
            return text
    return text[:BUILD_ID_MAX]


# --------------------------------------------------------------------------- #
# The nested repos' remote (A5)
# --------------------------------------------------------------------------- #
_URL = re.compile(r"^(?P<pre>[a-z][a-z0-9+.-]*://[^/]*/(?:.*/)?|[^@/:\s]+@[^:/\s]+:(?:.*/)?)"
                  r"(?P<owner>[^/]+)/(?P<name>[^/]+?)(?:\.git)?/?$")
_REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
#: userinfo in an http(s) URL, or a password in any scheme URL. An ssh user
#: name (`git@github.com:…`, `ssh://git@…`) is not a secret.
_CREDENTIALED = re.compile(r"^(?:https?://[^/@]+@|[a-z][a-z0-9+.-]*://[^/@:]+:[^/@]*@)", re.I)


def remote_url(origin: str, repository: str) -> str:
    """The outer origin with its last two path parts swapped for
    ``repository``, so the clone keeps the outer repo's transport and
    credentials; ``https://github.com/<repository>.git`` otherwise."""
    if not _REPOSITORY.match(repository):
        raise ValueError(f"not an owner/name: {repository!r}")
    origin = origin.strip()
    if origin.startswith("-") or "::" in origin:
        # An option to git, or a transport helper (`ext::…`): never reused.
        raise ValueError("the origin URL is not a plain URL; refusing to reuse it")
    if _CREDENTIALED.match(origin):
        # Not reused, and not printed: it would land in the saved report.
        raise ValueError("the origin URL carries credentials; refusing to reuse or print it")
    m = _URL.match(origin)
    if m:
        return f"{m.group('pre')}{repository}.git"
    return f"https://github.com/{repository}.git"


# --------------------------------------------------------------------------- #
# Release identity (A6): print-only
# --------------------------------------------------------------------------- #
def _first_parent(repo: str, sha: str) -> list:
    """Notes, and whether a command may be proposed (the last item, a bool)."""
    out = []
    rc, _ = _git(repo, "rev-parse", "-q", "--verify", "refs/remotes/origin/master")
    has_origin = rc == 0
    on_origin = on_local = False
    if has_origin:
        rc, chain = _git(repo, "rev-list", "--first-parent", "refs/remotes/origin/master")
        on_origin = rc == 0 and sha in chain.split()
    else:
        out.append("note: there is no origin/master here; checked local master only.")
    if not on_origin:
        rc, chain = _git(repo, "rev-list", "--first-parent", "refs/heads/master")
        on_local = rc == 0 and sha in chain.split()
    if on_origin:
        return out + [True]
    if on_local:
        if has_origin:
            out.append(f"note: {sha[:9]} is on first-parent master but not on origin/master "
                       "as of the last fetch; push master first.")
        return out + [True]
    out.append(f"WARNING: {sha[:9]} is not on first-parent master, so it is not a release "
               "(VERSIONING.md). Merge to master and build there.")
    out.append("No release tag proposed.")
    return out + [False]


def _existing_tag(repo: str, tag: str, sha: str):
    """None if free; a refusal line, or "same" when it already tags ``sha``."""
    rc, there = _git(repo, "rev-parse", "-q", "--verify", f"refs/tags/{tag}^{{commit}}")
    if rc != 0 or not there:
        return None
    if there == sha:
        return "same"
    return (f"Refusing: tag {tag} already names {there[:9]}; this build is {sha[:9]}: "
            "the number names two commits, so this build is not a release.")


def tag_command(stamp: dict, repo: str) -> tuple:
    reasons = verdict(stamp)
    if reasons:
        return 0, ["No release tag proposed: this build cannot be traced ("
                   + "; ".join(reasons) + ")."]
    major, build = str(stamp.get("major", "")), stamp.get("build")
    if not re.match(r"^\d+$", major) or not isinstance(build, int) or isinstance(build, bool):
        return EXIT_UNREADABLE, ["error: the stamp has no valid major/build."]
    tag = f"v{major}.{build:03d}"
    sha = stamp["sha"]
    rc, count = _git(repo, "rev-list", "--count", sha)
    if rc != 0 or count != str(build):
        return 1, [f"Refusing: {sha[:9]} has rev-list --count {count or '?'}, but the stamp "
                   f"says build {build}: this build is not a release."]
    existing = _existing_tag(repo, tag, sha)
    if existing == "same":
        return 0, [f"{tag} already tags this commit."]
    if existing:
        return 1, [existing]
    *notes, ok = _first_parent(repo, sha)
    if not ok:
        return 0, notes
    nested = stamp["nested"]
    msg = f"{tag}; macro {nested['macro']['sha'][:9]}, playmaker {nested['playmaker']['sha'][:9]}"
    return 0, notes + ["Proposed release tag (the owner runs both):",
                       f'  git tag -a {tag} {sha} -m "{msg}"',
                       f"  git push origin {tag}"]


def tag_retroactive(version: str, commit: str, repo: str) -> tuple:
    m = re.match(r"^v?(\d+)\.(\d+)$", version)
    if not m or not re.match(r"^[0-9a-f]{4,40}$", commit):
        return EXIT_UNREADABLE, ["error: expected <MAJOR.BUILD> <hex commit>."]
    major, build = m.group(1), int(m.group(2))
    rc, sha = _git(repo, "rev-parse", "--verify", "-q", f"{commit}^{{commit}}")
    if rc != 0 or not _is_sha(sha):
        return 1, [f"Refusing: {commit} is not a commit in {repo}."]
    rc, count = _git(repo, "rev-list", "--count", sha)
    if rc != 0 or count != str(build):
        return 1, [f"Refusing: {sha[:9]} has rev-list --count {count}, not {build}."]
    tag = f"v{major}.{build:03d}"
    existing = _existing_tag(repo, tag, sha)
    if existing == "same":
        return 0, [f"{tag} already tags this commit."]
    if existing:
        return 1, [existing]
    *notes, ok = _first_parent(repo, sha)
    if not ok:
        return 0, notes
    return 0, notes + [
        "Proposed retroactive tag (the owner runs both):",
        f'  git tag -a {tag} {sha} -m "{tag} (retroactive); nested code unknown"',
        f"  git push origin {tag}",
        "The bundle's stamp had `nested: {}`; the macro and playmaker code it ran cannot be "
        "recovered."]


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _read_stamp(path: str):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as exc:
        return None, f"cannot read {path}: {exc}"
    if not isinstance(data, dict):
        return None, f"{path} is not a JSON object"
    return data, None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="buildid.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("check-stamp")
    p.add_argument("stamp")
    p.add_argument("--repo")
    p = sub.add_parser("pins")
    p.add_argument("--shell", action="store_true")
    p.add_argument("workflow")
    p = sub.add_parser("remote-url")
    p.add_argument("origin")
    p.add_argument("repository")
    p = sub.add_parser("tag-command")
    p.add_argument("stamp", nargs="?")
    p.add_argument("--retroactive", nargs=2, metavar=("MAJOR.BUILD", "COMMIT"))
    p.add_argument("--repo", required=True)
    args = ap.parse_args(argv)

    if args.cmd == "check-stamp":
        stamp, err = _read_stamp(args.stamp)
        if err:
            print(err)
            return EXIT_UNREADABLE
        reasons = verdict(stamp) + (origin_reasons(stamp, args.repo) if args.repo else [])
        for line in reasons:
            print(line)
        return EXIT_UNTRACEABLE if reasons else 0
    if args.cmd == "pins":
        try:
            with open(args.workflow, encoding="utf-8") as f:
                found = pins(f.read())
        except (OSError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        if args.shell:
            for path in PIN_PATHS:
                print(path, *found[path])
        else:
            print(json.dumps({p: list(v) for p, v in found.items()}))
        return 0
    if args.cmd == "remote-url":
        try:
            print(remote_url(args.origin, args.repository))
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        return 0
    # tag-command
    if args.retroactive:
        if args.stamp:
            ap.error("tag-command takes a stamp or --retroactive, not both")
        rc, lines = tag_retroactive(*args.retroactive, args.repo)
    else:
        if not args.stamp:
            ap.error("tag-command needs a stamp")
        stamp, err = _read_stamp(args.stamp)
        if err:
            print(err)
            return EXIT_UNREADABLE
        rc, lines = tag_command(stamp, args.repo)
    for line in lines:
        print(line)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
