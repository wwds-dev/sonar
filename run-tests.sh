#!/usr/bin/env bash
# Run the suite under an external watchdog.
#
# Three tests build a real MainWindow, and PySide6 occasionally leaves a
# pthread mutex orphaned when those windows are torn down — the main thread
# then blocks in PyThread_release_lock and the process is unkillable from
# inside itself. `faulthandler_timeout` in pyproject.toml catches an ordinary
# Python hang, but it cannot catch this one: the dump would need the very lock
# that is held. A run once sat wedged for five hours and fifty minutes.
#
# So the timeout lives outside the process, where it always works.
#
#   ./run-tests.sh                 # the suite, 300s budget
#   ./run-tests.sh -k playmaker    # anything after the script is passed through
#   TEST_BUDGET_S=60 ./run-tests.sh
set -uo pipefail
cd "$(dirname "$0")"

BUDGET="${TEST_BUDGET_S:-300}"
PYTHON="${PYTHON:-.venv/bin/python}"

"$PYTHON" -m pytest "$@" &
pid=$!

# The sleep runs in the watchdog's background and the trap reaps it. Killing
# only the subshell orphans the sleep, which keeps stdout open — so a piped
# invocation (`./run-tests.sh | tail`) used to block for the whole budget
# after a 10-second suite had already finished, and the late kill printed
# job-control noise into the results.
( trap 'kill "$napper" 2>/dev/null; exit 0' TERM
  sleep "$BUDGET" & napper=$!
  wait "$napper" 2>/dev/null || exit 0
  if kill -0 "$pid" 2>/dev/null; then
      echo ""
      echo "run-tests.sh: no result after ${BUDGET}s — sampling and killing $pid." >&2
      sample "$pid" 2 -mayDie 2>/dev/null | head -60 >&2 || true
      kill -9 "$pid" 2>/dev/null
  fi ) &
watchdog=$!

wait "$pid"; status=$?
kill "$watchdog" 2>/dev/null
wait "$watchdog" 2>/dev/null

if [ "$status" -ge 128 ]; then
    echo "run-tests.sh: the suite was killed (signal $((status - 128)))." >&2
    echo "  A wedged Qt teardown is the usual cause; the sample above says where." >&2
fi
exit "$status"
