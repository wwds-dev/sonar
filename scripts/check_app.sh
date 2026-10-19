#!/bin/bash
# Is this SONAR.app fit for the launchd agent to run?  Exit 0 if so.
#
#   scripts/check_app.sh <path/to/SONAR.app> <data-dir> [--allow-dirty]
#
# Shared by install_agent.sh (before writing the plist) and install_app.sh
# (before touching the installed copy), so a bundle is judged the same way on
# both paths. Checks, in order: it is a .app with an executable; its seal
# verifies; its build stamp names the code it runs; its own --selftest passes
# in an environment like launchd's.
#
# "Names the code" is scripts/buildid.py check-stamp, run with python3 -I: the
# outer tree clean (the top-level key, not any "dirty": false in the file), its
# commit, both nested repos as real checkouts, clean, at the CI pins the stamp
# recorded, and each commit on an origin ref as of the last fetch (local git
# only; docs/specs/build-traceability.md A4). Exit 3 lists the reasons, and
# only that can be overridden with --allow-dirty; a stamp that cannot be read,
# a crash or no python3 refuses outright.
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
set +e
REASONS="$(python3 -I "$(dirname "$0")/buildid.py" check-stamp "$STAMP" \
  --repo "$(cd "$(dirname "$0")/.." && pwd)" 2>&1)"; RC=$?
set -e
case "$RC" in
  0) ;;                                   # traceable
  3) echo "WARNING: $APP cannot be traced to the code it runs:"
     sed 's/^/  - /' <<<"$REASONS"
     if [[ "$ALLOW_DIRTY" != 1 ]]; then
       echo
       echo "Refusing: the agent would run code no commit names."
       echo "Fix: commit, scripts/bootstrap_nested.sh, push, rebuild;"
       echo "or knowingly pass --allow-dirty (ALLOW_DIRTY=1 ./build_app.sh --install)."
       exit 1
     fi
     echo "--allow-dirty given: going on. The stamp keeps the build's own reasons, and the"
     echo "ledger's build string marks them (~ dirty or unknown, ! off the CI pins); the"
     echo "origin reasons are stored nowhere: record them in the verify note." ;;
  *) echo "error: the build stamp in $APP cannot be read (python3 -I buildid.py exit $RC):"
     sed 's/^/  /' <<<"$REASONS"
     exit 1 ;;                            # never overridable
esac
# launchd gives the agent no shell environment: test it the same way.
if ! env -i HOME="$HOME" SONAR_DATA="$DATA_DIR" "$EXEC" --selftest >/dev/null 2>&1; then
  echo "error: $EXEC --selftest failed; run it by hand to see why."
  exit 1
fi
