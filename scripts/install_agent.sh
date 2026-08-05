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
# takes the lock, and the other opens read-only rather than double-settling the
# hour. You can safely run both — the app becomes a viewer onto the agent.
set -euo pipefail
cd "$(dirname "$0")/.."
PROJECT_DIR="$(pwd)"

LABEL="com.netrunner3000.sonar"
PLIST_SRC="packaging/$LABEL.plist"
PLIST_DST="$HOME/Library/LaunchAgents/$LABEL.plist"
DOMAIN="gui/$(id -u)"

status() {
  if launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1; then
    echo "installed and loaded:"
    launchctl print "$DOMAIN/$LABEL" | grep -E "^\s+(state|pid|last exit code) " || true
    echo
    echo "logs: $PROJECT_DIR/data/logs/agent.{out,err}.log"
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

if pgrep -f "main.py --headless" >/dev/null 2>&1; then
  echo "warning: a headless SONAR is already running outside launchd."
  echo "Stop it first, or you will have two engines writing one state file."
  exit 1
fi

mkdir -p "$HOME/Library/LaunchAgents" "$PROJECT_DIR/data/logs"

# launchd does not expand ~ or environment variables inside these keys, so the
# absolute paths are substituted in here rather than referenced.
sed -e "s|__PROJECT_DIR__|$PROJECT_DIR|g" \
    -e "s|__PYTHON_BIN__|$PYTHON_BIN|g" \
    "$PLIST_SRC" > "$PLIST_DST"

# bootout first so re-running is idempotent rather than an error.
launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
launchctl bootstrap "$DOMAIN" "$PLIST_DST"
launchctl enable "$DOMAIN/$LABEL"

echo "Installed: $PLIST_DST"
echo
sleep 2
status
echo
echo "The engine now runs at login and restarts if it dies."
echo "Opening the app on top of it is fine: the agent holds the engine lock,"
echo "so the app opens read-only and shows the agent's state instead of"
echo "settling the same hour a second time."
echo
echo "Remove with: $0 --uninstall"
