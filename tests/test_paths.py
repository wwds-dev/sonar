"""Where the writable state lives — and the override that makes two SONARs
share it.

A frozen app keeps its state in Application Support; a checkout keeps it in
its own `data/`. The launchd agent runs from the checkout, so for weeks it ran
a second experiment beside the installed app's instead of keeping the app's
going. `SONAR_DATA` is how the agent is pointed at the app's directory.

The suite's conftest stubs `sonar.paths.user_data_base` for the whole session
so no test can reach the real data directory — which is right, and means the
real function has to be tested on a private copy of the module.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from sonar import paths as installed


@pytest.fixture
def paths():
    """A fresh, unpatched copy of `sonar/paths.py`."""
    spec = importlib.util.spec_from_file_location("sonar_paths_copy", installed.__file__)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_override_wins_frozen_or_not(paths, monkeypatch, tmp_path):
    monkeypatch.setenv(paths.DATA_ENV, str(tmp_path))
    monkeypatch.setattr(paths, "is_frozen", lambda: True)
    assert paths.user_data_base() == tmp_path.resolve()
    monkeypatch.setattr(paths, "is_frozen", lambda: False)
    assert paths.user_data_base() == tmp_path.resolve()
    assert paths.state_file() == tmp_path.resolve() / "state.json"
    assert paths.cache_dir() == tmp_path.resolve() / "cache"


def test_a_tilde_in_the_override_is_the_home_directory(paths, monkeypatch):
    monkeypatch.setenv(paths.DATA_ENV, "~/Library/Application Support/SONAR")
    assert paths.user_data_base() == (
        Path.home() / "Library" / "Application Support" / "SONAR").resolve()


def test_without_the_override_the_defaults_stand(paths, monkeypatch):
    monkeypatch.delenv(paths.DATA_ENV, raising=False)
    monkeypatch.setattr(paths, "is_frozen", lambda: True)
    assert paths.user_data_base() == Path.home() / "Library" / "Application Support" / "SONAR"
    monkeypatch.setattr(paths, "is_frozen", lambda: False)
    assert paths.user_data_base() == Path(installed.__file__).resolve().parent.parent / "data"


def test_an_empty_override_is_no_override(paths, monkeypatch):
    monkeypatch.setenv(paths.DATA_ENV, "   ")
    monkeypatch.setattr(paths, "is_frozen", lambda: False)
    assert paths.user_data_base().name == "data"


def test_the_agents_plist_points_at_the_apps_directory():
    """The template carries the variable, and the installer fills it with the
    installed app's directory — the whole point of the override."""
    root = Path(installed.__file__).resolve().parent.parent
    plist = (root / "packaging" / "com.netrunner3000.sonar.plist").read_text()
    assert "<key>SONAR_DATA</key>" in plist and "__DATA_DIR__" in plist
    script = (root / "scripts" / "install_agent.sh").read_text()
    assert 'DATA_DIR="$HOME/Library/Application Support/SONAR"' in script
    assert "s|__DATA_DIR__|$DATA_DIR|g" in script
