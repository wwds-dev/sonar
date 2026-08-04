"""SONAR — market scanner and paper-trading terminal.

    python main.py                run the app
    python main.py --selftest     check a build's wiring and exit
    python main.py --headless     run the HTTP daemon instead (no Qt)

The self-test exists because a packaged .app fails in ways the source tree
cannot. Two things bite every time in this lab: a frozen bundle is read-only and
code-signed, so anything writable must live in Application Support rather than
inside the .app; and PyInstaller's static analysis cannot see imports that are
resolved lazily. Running the self-test against the built binary catches both
before the app is trusted with a portfolio.
"""

from __future__ import annotations

import sys


def selftest() -> int:
    from sonar import horizon, llm, macro, paths, risk

    frozen = paths.is_frozen()
    icon = paths.asset_path("icon.icns")
    state = paths.state_file()

    print("SONAR self-test")
    print(f"  frozen bundle:   {frozen}")
    print(f"  resource base:   {paths.resource_base()}")
    print(f"  icon asset:      {icon} ({'found' if icon.exists() else 'MISSING'})")
    print(f"  state file:      {state}")
    print(f"  cache dir:       {paths.cache_dir()}")

    problems: list[str] = []
    if not icon.exists():
        problems.append("icon asset missing from the bundle")

    # The packaging landmine: writable state inside a signed bundle breaks the
    # signature, and a reinstall silently wipes the portfolio.
    if frozen and ".app/" in str(state):
        problems.append("state.json would be written inside the .app bundle")
    if frozen and "Application Support" not in str(state):
        problems.append("state.json is not under Application Support")

    try:
        paths.ensure_dirs()
        probe = paths.cache_dir() / "__selftest__"
        probe.write_text("ok")
        ok = probe.read_text() == "ok"
        probe.unlink()
        print(f"  writable state:  {'ok' if ok else 'FAILED'}")
        if not ok:
            problems.append("could not round-trip a file in the data directory")
    except OSError as exc:
        print(f"  writable state:  FAILED ({exc})")
        problems.append(f"data directory not writable: {exc}")

    # Qt must import, and specifically the widgets/gui modules the UI paints with.
    try:
        from PySide6 import QtGui, QtWidgets  # noqa: F401
        import PySide6
        print(f"  PySide6:         {PySide6.__version__}")
    except ImportError as exc:
        print(f"  PySide6:         MISSING ({exc})")
        problems.append("PySide6 not importable — the app cannot start")

    print(f"  risk profiles:   {', '.join(risk.PROFILES)}")
    print(f"  horizons:        {', '.join(horizon.HORIZONS)}")

    ok_llm, why = llm.available()
    print(f"  LLM read:        {'ready (' + llm.MODEL + ')' if ok_llm else 'off — ' + why}")

    # Macro is served from a cache and degrades to stale rather than failing;
    # report what it managed so a packaged build's network path is visible.
    snap = macro.snapshot()
    print(f"  macro regime:    {snap.regime}"
          + (f" ({snap.rationale})" if snap.rationale else ""))
    if snap.stale:
        print("                   (no data — network blocked or first run offline)")

    if problems:
        print("\nFAILED:")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("\nAll checks passed.")
    return 0


def headless() -> int:
    from sonar.server import main as serve
    serve()
    return 0


def run_app() -> int:
    from PySide6.QtWidgets import QApplication

    from sonar import paths
    from sonar.core import Live
    from ui import theme
    from ui.app import MainWindow

    paths.ensure_dirs()
    app = QApplication(sys.argv)
    app.setApplicationName("SONAR")
    app.setStyleSheet(theme.STYLESHEET)

    win = MainWindow(Live())
    win.show()
    return app.exec()


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    if "--headless" in sys.argv:
        sys.exit(headless())
    sys.exit(run_app())
