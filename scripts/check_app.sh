#!/bin/bash
# Is this SONAR.app fit for the launchd agent to run?  Exit 0 if so.
#
#   scripts/check_app.sh <path/to/SONAR.app> <data-dir> [--allow-dirty]
#
# Shared by install_agent.sh (before writing the plist) and install_app.sh
# (before touching the installed copy), so a bundle is judged the same way on
# both paths. Checks, in order: it is a .app with an executable; its seal
# verifies; it carries a build stamp that says it was built from a clean tree
# (no "dirty" key is unknown, which is not clean; --allow-dirty overrides with
# a warning); its own --selftest passes in an environment like launchd's.
#
# What the seal proves: the bundle is intact as signed. It is ad hoc signed, so
# it does not prove who built it (closing security review, t2-1 part 2 P3-1).
set -euo pipefail

APP="${1:?usage: $0 <app> <data-dir> [--allow-dirty]}"
DATA_DIR="${2:?usage: $0 <app> <data-dir> [--allow-dirty]}"
ALLOW_DIRTY=0
[[ "${3:-}" == --allow-dirty ]] && ALLOW_DIRTY=1
EXEC="$APP/Contents/MacOS/SONAR"
STAMP="$APP/Contents/Resources/_build_info.json"

if [[ "$APP" != *.app || ! -x "$EXEC" ]]; then
  echo "error: no SONAR app at $APP."
  exit 1
fi
if ! codesign --verify --deep --strict "$APP" 2>/dev/null; then
  echo "error: $APP does not verify (codesign --verify --deep --strict)."
  exit 1
fi
if [[ ! -f "$STAMP" ]]; then
  echo "error: $APP carries no build stamp, so the agent's code cannot be named."
  exit 1
fi
if ! grep -Eq '"dirty": *false' "$STAMP"; then
  echo "WARNING: $APP was built from a tree that has uncommitted changes:"
  grep -E '"(build|commit|dirty)"' "$STAMP" || echo '  (no "dirty" key: unknown)'
  if [[ "$ALLOW_DIRTY" != 1 ]]; then
    echo
    echo "Refusing: the agent would run code its commit does not name."
    echo "Commit and rebuild, or knowingly pass --allow-dirty"
    echo "(ALLOW_DIRTY=1 ./build_app.sh --install from the build)."
    exit 1
  fi
  echo "--allow-dirty given: going on."
fi
# launchd gives the agent no shell environment: test it the same way.
if ! env -i HOME="$HOME" SONAR_DATA="$DATA_DIR" "$EXEC" --selftest >/dev/null 2>&1; then
  echo "error: $EXEC --selftest failed; run it by hand to see why."
  exit 1
fi
