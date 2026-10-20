#!/usr/bin/env python3
"""Freeze the current build number into `_build_info.json`.

A packaged `.app` has no `.git`, so it cannot derive its own version at runtime.
`build_app.sh` calls this first, which is what lets a bundle say which build it
is — and, by comparison with the checkout, whether it is still the current one.

Safe to run by hand. Writes nothing and exits 0 when git is unavailable: a
missing stamp degrades to "no version stamp" in the UI, which is honest, whereas
a guessed number would not be.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import buildid  # noqa: E402
from sonar import version  # noqa: E402
from sonar.version import (BUILD_INFO_NAME, BUILD_DIGITS,  # noqa: E402
                           _git_build, _read_major)


def nested_state() -> tuple[dict, bool | None]:
    """The nested repos (sonar/macro, sonar/playmaker) are bundled code the
    outer `git status` cannot see. Their state, and whether any is dirty:
    True if one is, None if one cannot be read, else False."""
    nested = version._nested()
    dirty: bool | None = False
    for repo in nested.values():
        if repo["dirty"] is True:
            dirty = True
        elif repo["dirty"] is None and dirty is False:
            dirty = None
    return nested, dirty


def pinned_head(found: dict) -> tuple[dict, str]:
    """HEAD resolved once, and the count, short commit and date derived from
    that sha, so a commit landing mid-stamp (sessions share worktrees) cannot
    give a number of one commit and the sha of another (code review P3-1).
    Without a resolvable HEAD, ``found`` is kept and the sha is empty."""
    sha = version._git("rev-parse", "--verify", "-q", "HEAD^{commit}", cwd=PROJECT_ROOT) or ""
    if not sha:
        return found, ""
    count = version._git("rev-list", "--count", sha, cwd=PROJECT_ROOT) or ""
    if not count.isdigit():
        return found, ""
    return {**found, "build": int(count),
            "commit": version._git("rev-parse", "--short", sha, cwd=PROJECT_ROOT) or sha[:7],
            "date": version._git("log", "-1", "--format=%cI", sha, cwd=PROJECT_ROOT)
            or found.get("date", "")}, sha


def main() -> int:
    found = _git_build(PROJECT_ROOT)
    if not found:
        print("stamp_version: no git metadata available — leaving the build "
              "unstamped rather than inventing a number.", file=sys.stderr)
        return 0
    found, sha = pinned_head(found)

    major = _read_major()
    nested, nested_dirty = nested_state()
    # Unknown counts as dirty here: the stamp is a yes/no that install
    # scripts trust, and a bundle with an unreadable nested repo is not clean.
    dirty = bool(found.get("dirty")) or nested_dirty is not False
    if dirty:
        # Not refused: the build regenerates static/testplan.html before this
        # runs, so a legitimately edited TESTPLAN.md shows up here too. But
        # said loudly, and carried in the stamp, because a bundle stamped from
        # a modified tree names a commit it does not match — the v2.132 of
        # 2026-10-08 could not be traced to any commit afterwards.
        print("stamp_version: the checkout has uncommitted changes — this "
              "bundle will not match the commit it is stamped with.",
              file=sys.stderr)
    payload = {
        "major": major,
        "build": found["build"],
        "commit": found["commit"],
        # The full digest: the pins are full SHAs, and the stamp is the build's
        # SLSA L1-style resolvedDependencies (docs/specs/build-traceability.md A2).
        "sha": sha,
        "date": found["date"],
        "dirty": dirty,
        # The outer tree alone: the gate's outer reason reads this, so a dirty
        # nested repo is not also reported as a dirty outer tree (domain P3-2).
        "outer_dirty": bool(found.get("dirty")),
        "nested": nested,
        "source": "baked",
        # Where to look for the checkout later. A bundle has no .git, so this is
        # the only way staleness() can compare against anything. Git-ignored
        # generated metadata, checked for existence before it is trusted.
        "root": str(PROJECT_ROOT),
    }
    # The pins belong to this outer commit: once the gate knows the tree was
    # clean, these are the commits CI ran it with. Read now, not at install,
    # so a later pin bump cannot turn a correct bundle into a refused one.
    try:
        text = (PROJECT_ROOT / ".github" / "workflows" / "tests.yml").read_text(
            encoding="utf-8")
        payload["pins"] = {path.split("/", 1)[1]: sha
                           for path, (_repo, sha) in buildid.pins(text).items()}
    except (OSError, ValueError) as exc:
        payload["pins"] = {}
        payload["pins_error"] = f"cannot read the CI pins ({exc})"
    # For people reading the stamp only (/api/health does not carry them):
    # check_app.sh recomputes the verdict from the raw fields above and never
    # reads these two.
    reasons = buildid.verdict(payload)
    payload["traceable"] = not reasons
    payload["untraceable"] = reasons
    for reason in reasons:
        print(f"stamp_version: {reason} — check_app.sh will refuse this bundle.",
              file=sys.stderr)
    target = PROJECT_ROOT / BUILD_INFO_NAME
    target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Stamped v{major}.{found['build']:0{BUILD_DIGITS}d} "
          f"({found['commit']}) -> {target.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
