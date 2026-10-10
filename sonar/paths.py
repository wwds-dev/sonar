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

import datetime as _dt
import json
import os
import shutil
import sys
import threading
import time
from pathlib import Path

APP_NAME = "SONAR"

#: Days of daily state-file backups kept beside the file.
BACKUP_KEEP = 7


BACKUP_DIR_ENV = "SONAR_BACKUP_DIR"
OFFSITE_KEEP = 30


def offsite_dir() -> Path | None:
    """Where the daily copies also go, off this folder — or None.

    The daily ``.bak`` files sit beside the state on the same disk, so they
    survive a corrupt write but not a lost disk or a deleted folder. Set
    ``$SONAR_BACKUP_DIR``, or put a path in ``<data>/backup-to`` (what
    ``scripts/install_agent.sh`` writes, so the window and the agent, whichever
    is driving, both copy): somewhere a backup job already covers.
    """
    raw = os.environ.get(BACKUP_DIR_ENV, "").strip()
    if not raw:
        try:
            raw = (user_data_base() / "backup-to").read_text().strip().splitlines()[0]
        except (OSError, IndexError):
            return None
    return Path(raw).expanduser() if raw else None


def _copy_offsite(bak: Path) -> None:
    dest = offsite_dir()
    if dest is None:
        return
    try:
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copy2(bak, dest / bak.name)
        stem = bak.name.rsplit(".bak.", 1)[0]
        for old in sorted(dest.glob(f"{stem}.bak.*"))[:-OFFSITE_KEEP]:
            old.unlink()
    except OSError as exc:            # must never block the save it protects
        print(f"SONAR: could not copy {bak.name} to {dest} ({exc})",
              file=sys.stderr, flush=True)


def daily_backup(path: Path, keep: int = BACKUP_KEEP,
                 today: str | None = None) -> Path | None:
    """Copy ``path`` aside once per day, before its first overwrite.

    The state files *are* the experiment's output, they live outside git, and
    the writer overwrites them on every change — so one corrupt write or
    stray delete loses weeks of record with no way back. This keeps the last
    :data:`BACKUP_KEEP` days as ``<name>.bak.<date>`` next to the file: the
    first save of a day snapshots yesterday's last known-good copy, and every
    later save that day sees the stamp already there and costs one
    ``exists()`` check. A backup that cannot be written must never block the
    save it protects, so failures are swallowed.
    """
    p = Path(path)
    if not p.exists():
        return None
    stamp = today or _dt.date.today().isoformat()
    bak = p.with_name(f"{p.name}.bak.{stamp}")
    if bak.exists():
        return None
    try:
        shutil.copy2(p, bak)
    except OSError:
        return None
    # ISO dates sort lexically, so the oldest backups are simply the first.
    for old in sorted(p.parent.glob(f"{p.name}.bak.*"))[:-keep]:
        try:
            old.unlink()
        except OSError:
            pass
    _copy_offsite(bak)
    return bak


def write_atomically(path: Path, text: str) -> None:
    """Replace a file's contents in one step: a crash mid-write leaves the old
    file, never half of the new one."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    # One temporary name per writer. A shared `<name>.tmp` let two threads
    # saving the same file at once rename each other's file away, and the
    # second `replace` raised FileNotFoundError mid-save.
    tmp = p.with_name(f"{p.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        tmp.write_text(text)
        tmp.replace(p)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


TEMP_FILE_MAX_AGE = 600.0     # seconds; no save takes anywhere near this long


def sweep_temp_files(path: Path, now: float | None = None) -> int:
    """Remove temporary files a killed save left beside ``path``.

    Each writer has its own temporary name (see :func:`write_atomically`), so
    a save cut off between write and rename leaves a new orphan every time
    rather than reusing one. Only files older than ``TEMP_FILE_MAX_AGE`` go:
    a younger one may be another process's save in flight. Older single
    names (``state.tmp``, ``protocol.json.tmp``) are swept the same way.
    Returns how many were removed."""
    p = Path(path)
    now = time.time() if now is None else now
    removed = 0
    for tmp in {*p.parent.glob(f"{p.name}.*tmp"), p.with_suffix(".tmp")}:
        try:
            if tmp.is_file() and now - tmp.stat().st_mtime > TEMP_FILE_MAX_AGE:
                tmp.unlink()
                removed += 1
        except OSError:
            pass
    return removed


def read_preferences(path: Path) -> dict:
    """A small preference file as a dict, or ``{}`` for anything else.

    These are files a person may open in an editor. A missing file, a
    truncated one, and one holding valid JSON that is not an object (``[]``,
    ``null``, ``7``) all mean "use the defaults" — the last of those used to
    reach ``.get`` on a list and stop the app starting (protocol.json) or
    every provider lookup (providers.json).
    """
    try:
        data = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def read_state(path: Path) -> dict | None:
    """A state file's contents, recovering from a file that cannot be read.

    ``None`` means *no file*: a first run, start clean. A file that exists but
    does not parse to an object — a truncated write, a disk error, a hand edit
    gone wrong — used to mean the same thing, and that is the worst answer
    available: the engine started on a blank $10,000, and its first save
    overwrote the only copy of weeks of record with it. So the unreadable file
    is moved aside (``<name>.unreadable.<unix time>``, never overwritten or
    rotated away) and the newest daily backup that does parse is loaded in its
    place, with a line on stderr saying so. Only when no backup parses either
    does this start clean — and even then the original bytes are kept.
    """
    p = Path(path)
    sweep_temp_files(p)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text())
        if isinstance(data, dict):
            return data
    except (OSError, ValueError):
        pass
    aside = p.with_name(f"{p.name}.unreadable.{int(time.time())}")
    try:
        p.replace(aside)
    except OSError:
        aside = p
    for bak in sorted(p.parent.glob(f"{p.name}.bak.*"), reverse=True):
        try:
            data = json.loads(bak.read_text())
        except (OSError, ValueError):
            continue
        if isinstance(data, dict):
            print(f"SONAR: {p.name} could not be read; kept it as {aside.name} "
                  f"and loaded {bak.name} instead.", file=sys.stderr, flush=True)
            return data
    print(f"SONAR: {p.name} could not be read and no backup parses; kept it as "
          f"{aside.name} and started clean.", file=sys.stderr, flush=True)
    return None


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


#: Overrides where the writable state lives, frozen or not. The launchd agent
#: runs from the checkout, whose default is ``data/``, while the installed app
#: is frozen and defaults to Application Support — two directories, two locks,
#: two books, and for weeks the "agent that keeps the run going" was running a
#: second run nobody looked at. The agent's plist sets this to the app's
#: directory (`scripts/install_agent.sh`), so the two meet in one book.
DATA_ENV = "SONAR_DATA"


def user_data_base() -> Path:
    """Writable state. Never inside the bundle.

    ``$SONAR_DATA`` wins when set (``~`` expanded); otherwise a frozen app
    uses Application Support and a checkout uses its own ``data/``.
    """
    override = os.environ.get(DATA_ENV, "").strip()
    if override:
        return Path(override).expanduser().resolve()
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
