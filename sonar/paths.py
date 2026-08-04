"""Where SONAR reads and writes.

In development everything resolves inside the project, exactly as before. Once
PyInstaller freezes the app the bundle is **read-only and code-signed**, so
anything writable has to move out of it: writing inside the .app breaks the
signature, and a reinstall wipes whatever was there. Writable state therefore
goes to ``~/Library/Application Support/SONAR/``.

This is the lab's standard shape (see ``services/runtime_paths.py`` in
sentinel_ai and the note in CLAUDE.md) and the single reason ``main.py
--selftest`` exists: a frozen build can fail here in a way the source tree
never does.
"""

from __future__ import annotations

import sys
from pathlib import Path

APP_NAME = "SONAR"


def is_frozen() -> bool:
    """True when running inside a PyInstaller bundle."""
    return getattr(sys, "frozen", False)


def resource_base() -> Path:
    """Read-only bundled resources (icons, docs, static/).

    Frozen: PyInstaller extracts ``--add-data`` payloads and exposes the root
    via ``sys._MEIPASS``. Dev: the project root.
    """
    if is_frozen():
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def user_data_base() -> Path:
    """Writable state. Never inside the bundle."""
    if is_frozen():
        return Path.home() / "Library" / "Application Support" / APP_NAME
    return Path(__file__).resolve().parent.parent / "data"


def state_file() -> Path:
    """The paper portfolio. Survives reinstalls when frozen."""
    return user_data_base() / "state.json"


def cache_dir() -> Path:
    """Cached third-party responses (macro series, fundamentals)."""
    return user_data_base() / "cache"


def asset_path(name: str) -> Path:
    return resource_base() / "assets" / name


def ensure_dirs() -> None:
    for p in (user_data_base(), cache_dir()):
        p.mkdir(parents=True, exist_ok=True)
