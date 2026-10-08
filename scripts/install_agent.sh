#!/bin/bash
# Install (or remove) the launchd agent that keeps the SONAR engine running.
#
#   ./scripts/install_agent.sh            install and start
#   ./scripts/install_agent.sh --status   is it running?
#   ./scripts/install_agent.sh --uninstall stop and remove
#
# Why this exists: SONAR's equity curve and calibration table only mean
# something if positions settle on the hours they were priced for. The app's
# tray keeps the engine alive while you are logged in; this keeps it alive when
# you are not, and brings it back after a reboot.
#
# The agent and the app share one state file, so only one of them may drive the
# engine. That is enforced in code by sonar/enginelock.py: whoever starts first
# takes the lock, and the other follows it — mirrors its state and hands it
# every action — and takes over the moment it stops. You can safely run both.
#
# "Share one state file" is only true if both look in the same place. The
# installed app is frozen and keeps its state in Application Support; this
# agent runs from the checkout, whose default is the checkout's own data/. So
# the plist sets SONAR_DATA to the app's directory (sonar/paths.py) — without
# it the agent keeps a second book beside the app's, which is what it did for
# weeks before anyone noticed.
set -euo pipefail
cd "$(dirname "$0")/.."
PROJECT_DIR="$(pwd)"

LABEL="com.netrunner3000.sonar"
PLIST_SRC="packaging/$LABEL.plist"
PLIST_DST="$HOME/Library/LaunchAgents/$LABEL.plist"
DOMAIN="gui/$(id -u)"
DATA_DIR="$HOME/Library/Application Support/SONAR"

status() {
  if launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1; then
    echo "installed and loaded:"
    launchctl print "$DOMAIN/$LABEL" | grep -E "^\s+(state|pid|last exit code) " || true
    echo
    echo "state: $DATA_DIR  (the installed app's — one book)"
    echo "logs:  $PROJECT_DIR/data/logs/agent.{out,err}.log"
  else
    echo "not loaded."
    [[ -f "$PLIST_DST" ]] && echo "(plist present at $PLIST_DST but not loaded)"
  fi
}

uninstall() {
  launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
  rm -f "$PLIST_DST"
  echo "Removed $LABEL. The engine no longer runs in the background."
  echo "Your paper portfolio is untouched."
}

case "${1:-}" in
  --status)    status; exit 0 ;;
  --uninstall) uninstall; exit 0 ;;
esac

# --- preflight ------------------------------------------------------------- #
PYTHON_BIN="$PROJECT_DIR/.venv/bin/python"
if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "error: $PYTHON_BIN not found."
  echo "Create the environment first:  uv venv .venv && uv pip install -r requirements.txt"
  exit 1
fi

# Headless mode needs no GUI packages, but it does need the project importable.
if ! "$PYTHON_BIN" -c "import sonar.core" 2>/dev/null; then
  echo "error: 'import sonar.core' failed with $PYTHON_BIN"
  exit 1
fi

# A headless SONAR that launchd did not start would fight the agent for the
# lock. The one launchd *did* start is fine: re-running this script replaces
# it, which is how the agent picks up a new plist.
if pgrep -f "main.py --headless" >/dev/null 2>&1 \
    && ! launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1; then
  echo "warning: a headless SONAR is already running outside launchd."
  echo "Stop it first, or you will have two engines writing one state file."
  exit 1
fi

mkdir -p "$HOME/Library/LaunchAgents" "$PROJECT_DIR/data/logs" "$DATA_DIR"

# launchd does not expand ~ or environment variables inside these keys, so the
# absolute paths are substituted in here rather than referenced.
sed -e "s|__PROJECT_DIR__|$PROJECT_DIR|g" \
    -e "s|__PYTHON_BIN__|$PYTHON_BIN|g" \
    -e "s|__DATA_DIR__|$DATA_DIR|g" \
    "$PLIST_SRC" > "$PLIST_DST"

# bootout first so re-running is idempotent rather than an error. The bootout
# is asynchronous: launchd is still tearing the old instance down when the
# bootstrap arrives, and answers "Input/output error" (5) until it is done —
# which left the agent not running at all once, after a reinstall. So: retry.
launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
booted=0
for attempt in 1 2 3 4 5 6; do
  if launchctl bootstrap "$DOMAIN" "$PLIST_DST" 2>/dev/null; then
    booted=1
    break
  fi
  sleep 2
done
if [[ "$booted" != 1 ]]; then
  echo "error: launchctl bootstrap kept failing; the agent is NOT running."
  echo "Try again in a few seconds: $0"
  exit 1
fi
launchctl enable "$DOMAIN/$LABEL"

echo "Installed: $PLIST_DST"
echo
sleep 2
status
echo
echo "The engine now runs at login and restarts if it dies, on the installed"
echo "app's book ($DATA_DIR)."
echo "Opening the app on top of it is fine: the agent holds the engine lock,"
echo "so the app follows it — every page shows the agent's state, every"
echo "action goes to the agent — and takes over if the agent stops."
echo
echo "Remove with: $0 --uninstall"
