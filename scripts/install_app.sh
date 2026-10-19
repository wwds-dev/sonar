#!/bin/bash
# Put a built SONAR.app in /Applications — and, when the launchd agent runs
# that app (scripts/install_agent.sh, the default since t2-1 option A), stop
# the agent around the swap and start it again on the new build.
#
#   scripts/install_app.sh <path/to/SONAR.app> [--allow-dirty]
#
# Called by ./build_app.sh --install. Split out so it can be tested without
# PyInstaller. $SONAR_APPS_DIR overrides /Applications, only together with
# SONAR_UNSAFE_PATHS=1 (tests).
#
# Order, and why:
#  1. Check the source (scripts/check_app.sh) before anything is touched,
#     always (owner, 2026-10-19; the agent may be put on the app later): a
#     build that cannot be traced, unsealed or failing its self-test is refused
#     with the installed app and the agent as they were.
#  2. Copy it beside the installed one (.SONAR.app.new) and check the copy.
#  3. Disable, then stop, the agent. Disabled matters: a stopped agent whose
#     plist is still enabled starts again at the next login, on whatever is in
#     /Applications by then — half a swap, or a bundle that failed its checks.
#  4. Swap with two renames, so the installed path is never half-copied.
#  5. install_agent.sh checks the installed app again, re-enables and starts.
# Any failure after step 3 leaves the agent stopped AND disabled, and says so.
set -euo pipefail

USAGE="usage: $0 <path/to/SONAR.app> [--allow-dirty]"
SRC="${1:?$USAGE}"
SRC="${SRC%/}"                      # "SONAR.app/" copied its contents, not itself
# Relative to where it was typed, not to the project root this cd's into.
[[ -d "$SRC" ]] && SRC="$(cd "$SRC" && pwd)"
cd "$(dirname "$0")/.."
ALLOW_DIRTY=0
case "${2:-}" in
  --allow-dirty) ALLOW_DIRTY=1 ;;
  "") ;;
  *) echo "$USAGE"; exit 2 ;;
esac
NAME="$(basename "$SRC")"
if [[ ! -d "$SRC" || "$NAME" != SONAR.app ]]; then
  echo "error: $SRC is not a built SONAR.app; nothing was changed."
  exit 1
fi

DEST_DIR="/Applications"
if [[ -n "${SONAR_APPS_DIR:-}" ]]; then
  [[ "${SONAR_UNSAFE_PATHS:-0}" == 1 ]] || { echo "error: SONAR_APPS_DIR is for tests"; exit 2; }
  DEST_DIR="$SONAR_APPS_DIR"
fi
DEST="$DEST_DIR/$NAME"
STAGE="$DEST_DIR/.$NAME.new"
OLD="$DEST_DIR/.$NAME.old"
LABEL="com.netrunner3000.sonar"
AGENT_PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
DOMAIN="gui/$(id -u)"
DATA_DIR="$HOME/Library/Application Support/SONAR"

agent_on_app=0
if [[ -f "$AGENT_PLIST" ]] && grep -qF "$DEST/Contents/MacOS/" "$AGENT_PLIST"; then
  agent_on_app=1
fi
# Restarted only if it is running now: an agent stopped on purpose (a restore,
# RUNBOOK section 4) stays stopped through an install.
agent_running=0
if [[ "$agent_on_app" == 1 ]] && launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1; then
  agent_running=1
fi
if pgrep -f "^$DEST/Contents/MacOS/SONAR\$" >/dev/null 2>&1; then
  echo "warning: the SONAR window is open from $DEST. It keeps running the old build"
  echo "(and may take the engine while the agent is stopped); quit and reopen it after."
fi
check_args=()
[[ "$ALLOW_DIRTY" == 1 ]] && check_args+=(--allow-dirty)

# 1. the source, before anything is touched — whether or not the agent runs
# the app: the installed app is what install_agent.sh will put under it.
if [[ "$agent_on_app" == 1 ]]; then
  echo "The agent runs $DEST: checking the new build first…"
else
  echo "Checking the new build first…"
fi
./scripts/check_app.sh "$SRC" "$DATA_DIR" "${check_args[@]+"${check_args[@]}"}"

# 2. a copy beside the installed one (removed again if anything below fails)
rm -rf "$STAGE" "$OLD"
trap 'rm -rf "$STAGE"' EXIT
cp -R "$SRC" "$STAGE"
if [[ "$agent_on_app" == 1 ]] && ! codesign --verify --deep --strict "$STAGE" 2>/dev/null; then
  rm -rf "$STAGE"
  echo "error: the copy at $STAGE does not verify; nothing was changed."
  exit 1
fi

# 3. the agent, disabled and stopped
if [[ "$agent_on_app" == 1 ]]; then
  echo "Stopping the agent for the swap…"
  launchctl disable "$DOMAIN/$LABEL"
  launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
  trap 'echo; echo "error: the install did not finish. The agent is STOPPED and DISABLED"
        echo "(it will not start at login). Fix the cause, then: ./build_app.sh --install"
        echo "or ./scripts/install_agent.sh"' ERR
fi

# 4. the swap
[[ -e "$DEST" ]] && mv "$DEST" "$OLD"
mv "$STAGE" "$DEST"
rm -rf "$OLD"
touch "$DEST"  # nudge Finder/Dock to refresh the cached icon
echo "Installed: $DEST"

# 5. the agent, on the new build — if it was running
if [[ "$agent_running" == 1 ]]; then
  echo
  echo "Starting the agent on the new build…"
  SONAR_APP="$DEST" ./scripts/install_agent.sh "${check_args[@]+"${check_args[@]}"}"
elif [[ "$agent_on_app" == 1 ]]; then
  trap - ERR
  echo
  echo "The agent was not running before the install, so it is left stopped (and"
  echo "disabled). Start it on this build with: ./scripts/install_agent.sh"
fi
