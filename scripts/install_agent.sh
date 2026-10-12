#!/bin/bash
# Install (or remove) the launchd agent that keeps the SONAR engine running.
#
#   ./scripts/install_agent.sh              install and start, running the installed app
#   ./scripts/install_agent.sh --checkout   ...running this checkout's working tree instead
#   ./scripts/install_agent.sh --allow-dirty  (with either) accept uncommitted changes
#   ./scripts/install_agent.sh --status     is it running, and which build?
#   ./scripts/install_agent.sh --uninstall  stop and remove
#
# What it runs (docs/specs/t2-1-agent-provenance.md, owner decision option A):
# by default the installed bundle, /Applications/SONAR.app (or $SONAR_APP),
# with --headless. That is one tested, stamped build for the app and the agent,
# and an edit in this checkout cannot reach the running agent on a restart —
# which is what the working tree used to do. --checkout keeps the old way, for
# development, behind the same clean-tree check.
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
# installed app is frozen and keeps its state in Application Support; run from
# the checkout, the default is the checkout's own data/. So the plist sets
# SONAR_DATA to the app's directory either way (sonar/paths.py) — without it a
# checkout agent kept a second book beside the app's, for weeks before anyone
# noticed.
set -euo pipefail
cd "$(dirname "$0")/.."
PROJECT_DIR="$(pwd)"

LABEL="com.netrunner3000.sonar"
PLIST_SRC="packaging/$LABEL.plist"
PLIST_DST="$HOME/Library/LaunchAgents/$LABEL.plist"
DOMAIN="gui/$(id -u)"
DATA_DIR="$HOME/Library/Application Support/SONAR"
APP="${SONAR_APP:-/Applications/SONAR.app}"
APP="${APP%/}"
APP_EXEC="$APP/Contents/MacOS/SONAR"
# What launchd will run at every login is not left to a stray environment
# variable: only the two standard places, unless SONAR_UNSAFE_PATHS=1 (tests).
if [[ "$APP" != /Applications/SONAR.app && "$APP" != "$HOME/Applications/SONAR.app" \
      && "${SONAR_UNSAFE_PATHS:-0}" != 1 ]]; then
  echo "error: SONAR_APP=$APP is not /Applications/SONAR.app or ~/Applications/SONAR.app."
  exit 2
fi

# The value of a <string> after a key in the installed plist ("" if none).
plist_value() {
  [[ -f "$PLIST_DST" ]] || return 0
  sed -n "/<key>$1<\/key>/{n;s/.*<string>\(.*\)<\/string>.*/\1/p;}" "$PLIST_DST" | head -1
}

status() {
  if launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1; then
    echo "installed and loaded:"
    launchctl print "$DOMAIN/$LABEL" | grep -E "^\s+(state|pid|last exit code|program) " || true
    echo
    echo "state: $DATA_DIR  (the installed app's — one book)"
    echo "logs:  $(plist_value StandardErrorPath)"
    local py="$PROJECT_DIR/.venv/bin/python"
    [[ -x "$py" ]] || py=python3
    echo "build: $(curl -s -m 3 127.0.0.1:8787/api/health | \
      "$py" -c 'import json,sys; b=json.load(sys.stdin).get("build"); print(json.dumps(b) if b else "not reported (this agent predates the build field)")' 2>/dev/null \
      || echo "not answering")"
  else
    echo "not loaded."
    if [[ -f "$PLIST_DST" ]]; then
      echo "(plist present at $PLIST_DST but not loaded)"
    fi
  fi
}

uninstall() {
  launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
  rm -f "$PLIST_DST"
  echo "Removed $LABEL. The engine no longer runs in the background."
  echo "Your paper portfolio is untouched."
}

USAGE="usage: $0 [--checkout] [--allow-dirty] | --status | --uninstall"
ALLOW_DIRTY=0
FROM=bundle
case "${1:-}" in
  --status|--uninstall)
    [[ $# -eq 1 ]] || { echo "$USAGE"; exit 2; }
    if [[ "$1" == --status ]]; then status; else uninstall; fi
    exit 0 ;;
esac
for arg in "$@"; do
  case "$arg" in
    --checkout)    FROM=checkout ;;
    --allow-dirty) ALLOW_DIRTY=1 ;;
    *) echo "$USAGE"; exit 2 ;;
  esac
done

refuse_dirty() {   # $1: what is dirty, $2: the list
  echo "WARNING: $1 has uncommitted changes:"
  head -15 <<<"$2"     # not echo | head: SIGPIPE under pipefail on a long list
  if [[ "$ALLOW_DIRTY" != 1 ]]; then
    echo
    echo "Refusing to install. Commit or revert them (and rebuild), or knowingly run:"
    if [[ "$FROM" == checkout ]]; then
      echo "  $0 --checkout --allow-dirty"
    else
      echo "  $0 --allow-dirty"
    fi
    echo "(/api/health will then report \"dirty\": true.)"
    exit 1
  fi
  echo "--allow-dirty given: installing anyway."
  echo
}

# --- preflight: the installed app ------------------------------------------ #
# What a restart loads is fixed until the app is reinstalled. Checked here so a
# broken or unidentifiable bundle never becomes a launchd crash loop.
if [[ "$FROM" == bundle ]]; then
  if [[ ! -x "$APP_EXEC" ]]; then
    echo "error: no installed app at $APP."
    echo "Build and install it first:  ./build_app.sh --install"
    echo "(or run the agent from this checkout:  $0 --checkout)"
    exit 1
  fi
  args=("$APP" "$DATA_DIR")
  [[ "$ALLOW_DIRTY" == 1 ]] && args+=(--allow-dirty)
  ./scripts/check_app.sh "${args[@]}"
fi

# --- preflight: the checkout ----------------------------------------------- #
if [[ "$FROM" == checkout ]]; then
# The agent runs this working tree, not a build: whatever is on disk when
# launchd (re)starts it is what drives the paper book. A half-finished edit
# would crash-loop it or change the model mid-run, and /api/health could not
# say which commit that was. So a tree with uncommitted tracked changes (or
# one git cannot read) is refused unless --allow-dirty says it is meant.
# Untracked files do not count, same as sonar/version.py.
if ! DIRTY="$(git status --porcelain --untracked-files=no 2>/dev/null)"; then
  DIRTY="(git status failed: cannot tell whether the tree is clean)"
fi
# The nested repos are code the agent imports, and the outer status cannot
# see into them (sonar/version.py NESTED_REPOS).
for nested in sonar/macro sonar/playmaker; do
  [[ -e "$nested/.git" ]] || continue
  if ! more="$(git -C "$nested" status --porcelain --untracked-files=no 2>/dev/null)"; then
    more="(git status failed: cannot tell whether it is clean)"
  fi
  if [[ -n "$more" ]]; then
    NL=$'\n'
    DIRTY+="${DIRTY:+$NL}$(sed "s|^|$nested: |" <<<"$more")"
  fi
done
if [[ -n "$DIRTY" ]]; then
  refuse_dirty "the agent runs this working tree, and it" "$DIRTY"
fi

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
fi   # checkout
# A headless SONAR that launchd did not start would fight the agent for the
# lock. The one launchd *did* start is fine: re-running this script replaces
# it, which is how the agent picks up a new plist.
if pgrep -f "(main.py|MacOS/SONAR) --headless" >/dev/null 2>&1 \
    && ! launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1; then
  echo "warning: a headless SONAR is already running outside launchd."
  echo "Stop it first, or you will have two engines writing one state file."
  exit 1
fi

if [[ "$FROM" == bundle ]]; then
  # Logs leave the checkout with the code: nothing the agent needs lives here.
  LOG_DIR="$HOME/Library/Logs/SONAR"
  EXEC="$APP_EXEC"; MAIN_PY=""; WORK_DIR="$DATA_DIR"
else
  LOG_DIR="$PROJECT_DIR/data/logs"
  EXEC="$PYTHON_BIN"; MAIN_PY="$PROJECT_DIR/main.py"; WORK_DIR="$PROJECT_DIR"
fi
mkdir -p "$HOME/Library/LaunchAgents" "$LOG_DIR" "$DATA_DIR"

# The daily copies of the book also go somewhere a backup job covers — the
# .bak files beside it share its disk (sonar/paths.py, offsite_dir). Written
# once; edit "$DATA_DIR/backup-to" to change it, empty it to stop.
BACKUP_DIR="${SONAR_BACKUP_DIR:-$HOME/Documents/lab/backups/sonar-data}"
if [[ ! -f "$DATA_DIR/backup-to" ]]; then
  echo "$BACKUP_DIR" > "$DATA_DIR/backup-to"
fi

# launchd does not expand ~ or environment variables inside these keys, so the
# absolute paths are filled in here. With plistlib, not sed: a path with "&",
# "|" or "</string>" in it used to rewrite the plist silently, and a failed sed
# had already emptied the live one. Written aside, then moved into place.
TMP_PLIST="$(mktemp "$PLIST_DST.XXXXXX")"
if ! python3 -I - "$PLIST_SRC" "$TMP_PLIST" "$EXEC" "$MAIN_PY" "$WORK_DIR" "$LOG_DIR" \
    "$DATA_DIR" <<'PY'
import plistlib, sys
src, dst, exe, main_py, work, logs, data = sys.argv[1:]
with open(src, "rb") as f:
    p = plistlib.load(f)
# The template's first two arguments are __EXEC__ and __MAIN_PY__; the bundle
# takes no script argument, so that one is dropped rather than left empty.
p["ProgramArguments"] = [exe] + ([main_py] if main_py else []) + p["ProgramArguments"][2:]
p["WorkingDirectory"] = work
p["EnvironmentVariables"]["SONAR_DATA"] = data
p["StandardOutPath"] = f"{logs}/agent.out.log"
p["StandardErrorPath"] = f"{logs}/agent.err.log"
assert "__" not in repr(p), "a template placeholder was left in"
with open(dst, "wb") as f:
    plistlib.dump(p, f)
PY
then
  rm -f "$TMP_PLIST"
  echo "error: could not write the agent's plist; the installed one is unchanged."
  exit 1
fi
chmod 644 "$TMP_PLIST"
mv "$TMP_PLIST" "$PLIST_DST"

# bootout first so re-running is idempotent rather than an error. The bootout
# is asynchronous: launchd is still tearing the old instance down when the
# bootstrap arrives, and answers "Input/output error" (5) until it is done —
# which left the agent not running at all once, after a reinstall. So: retry.
launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
# Enabled before the bootstrap: install_app.sh disables the agent around a swap,
# and launchd refuses to bootstrap a disabled service.
launchctl enable "$DOMAIN/$LABEL"
booted=0
for attempt in 1 2 3 4 5 6; do
  if launchctl bootstrap "$DOMAIN" "$PLIST_DST" 2>/dev/null; then
    booted=1
    break
  fi
  sleep "${SONAR_SETTLE_S:-2}"
done
if [[ "$booted" != 1 ]]; then
  echo "error: launchctl bootstrap kept failing; the agent is NOT running."
  echo "Try again in a few seconds: $0"
  exit 1
fi

echo "Installed: $PLIST_DST"
if [[ "$FROM" == bundle ]]; then
  echo "Runs:      $APP_EXEC --headless"
  echo "           $(grep -E '"(build|commit)"' "$APP/Contents/Resources/_build_info.json" | tr -d ' \n' || true)"
  echo "A rebuild reaches the agent only through ./build_app.sh --install."
else
  echo "Runs:      this checkout's working tree ($PROJECT_DIR)"
fi
echo
sleep "${SONAR_SETTLE_S:-2}"
status
echo
echo "The engine now runs at login and restarts if it dies, on the installed"
echo "app's book ($DATA_DIR)."
echo "Opening the app on top of it is fine: the agent holds the engine lock,"
echo "so the app follows it — every page shows the agent's state, every"
echo "action goes to the agent — and takes over if the agent stops."
echo
echo "Remove with: $0 --uninstall"
