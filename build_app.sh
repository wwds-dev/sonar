#!/bin/bash
# Builds "SONAR.app" with PyInstaller into dist.noindex/.
# Pass --install to also copy it into /Applications.
#
# The output folder is named ".noindex" deliberately. It lives under
# ~/Documents, which Spotlight indexes, and a built .app sitting there shows up
# as a second "SONAR" next to the installed one — re-registered on every build,
# because each rebuild re-signs the bundle with a new ad-hoc identity. Spotlight
# skips any directory whose name ends in .noindex.
set -euo pipefail
cd "$(dirname "$0")"

APP_NAME="SONAR"
BUNDLE_ID="com.netrunner3000.sonar"
DIST="dist.noindex"

source .venv/bin/activate
uv pip install -q pyinstaller

# Regenerate the icon so the bundle never ships a stale one.
python assets/make_icon.py

rm -rf build dist "$DIST"

# QtWebEngine is excluded on purpose: every chart is QPainter (see ui/charts.py),
# so nothing needs it and it would add ~200MB to the bundle.
#
# The anthropic SDK is only imported lazily inside sonar/llm.py, which
# PyInstaller's static analysis cannot see — without the hidden-import the
# packaged app silently loses the LLM read even when the SDK is installed.
#
# sonar.execution and sonar.costs are named for a different reason: nothing
# imports them at all yet, so PyInstaller correctly leaves them out. They are
# forced in so that wiring the guard to a button later cannot produce a build
# where it is missing — a failure that would appear only once packaged, at the
# moment someone clicks buy. main.py --selftest asserts both are present.
pyinstaller --noconfirm --clean --windowed \
  --name "$APP_NAME" \
  --icon assets/icon.icns \
  --osx-bundle-identifier "$BUNDLE_ID" \
  --distpath "$DIST" \
  --add-data "assets/icon.icns:assets" \
  --add-data "static:static" \
  --hidden-import anthropic \
  --hidden-import sonar.execution \
  --hidden-import sonar.costs \
  --exclude-module PySide6.QtWebEngineCore \
  --exclude-module PySide6.QtWebEngineWidgets \
  --exclude-module PySide6.Qt3DCore \
  --exclude-module PySide6.QtCharts \
  --exclude-module PySide6.QtDataVisualization \
  --exclude-module PySide6.QtMultimedia \
  --exclude-module PySide6.QtQuick3D \
  --exclude-module tkinter \
  main.py

echo
echo "Built: $DIST/$APP_NAME.app ($(du -sh "$DIST/$APP_NAME.app" | cut -f1))"

# The self-test runs against the *built binary*, not the source tree — that is
# the whole point. It checks the two things a frozen bundle gets wrong: writable
# state escaping into the read-only .app, and lazily-imported modules vanishing.
echo
echo "Running self-test against the built binary…"
"$DIST/$APP_NAME.app/Contents/MacOS/$APP_NAME" --selftest

if [[ "${1:-}" == "--install" ]]; then
  rm -rf "/Applications/$APP_NAME.app"
  cp -R "$DIST/$APP_NAME.app" /Applications/
  touch "/Applications/$APP_NAME.app"  # nudge Finder/Dock to refresh the cached icon
  echo "Installed: /Applications/$APP_NAME.app"

  # Nothing left behind to be indexed or backed up.
  rm -rf build "$DIST"
  echo "Cleaned: build/ and $DIST/"
else
  echo
  echo "Run '$0 --install' to copy it into /Applications."
  echo "$DIST/ is skipped by Spotlight; --install removes it entirely."
fi
