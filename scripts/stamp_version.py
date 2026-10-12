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


def main() -> int:
    found = _git_build(PROJECT_ROOT)
    if not found:
        print("stamp_version: no git metadata available — leaving the build "
              "unstamped rather than inventing a number.", file=sys.stderr)
        return 0

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
        "date": found["date"],
        "dirty": dirty,
        "nested": nested,
        "source": "baked",
        # Where to look for the checkout later. A bundle has no .git, so this is
        # the only way staleness() can compare against anything. Git-ignored
        # generated metadata, checked for existence before it is trusted.
        "root": str(PROJECT_ROOT),
    }
    target = PROJECT_ROOT / BUILD_INFO_NAME
    target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Stamped v{major}.{found['build']:0{BUILD_DIGITS}d} "
          f"({found['commit']}) -> {target.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
