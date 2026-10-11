"""The agent runs the checkout's working tree, so /api/health must say which.

closing-sre-release P1-2: the launchd agent executes ``<checkout>/main.py``;
a restart loads whatever is on disk. Health carried no commit, and
``install_agent.sh`` happily installed over uncommitted edits.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from sonar import version as app_version
from sonar.core import Live

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "install_agent.sh"


@pytest.fixture(autouse=True)
def _clear_cache():
    real, nested = app_version.info, app_version._nested   # monkeypatched below
    real.cache_clear(); nested.cache_clear()
    yield
    real.cache_clear(); nested.cache_clear()


def _live(tmp_path, monkeypatch, nested=None):
    monkeypatch.setattr("sonar.paths.user_data_base", lambda: tmp_path)
    monkeypatch.setattr(app_version, "_nested", lambda: nested or {})
    return Live()


def _fake(source="git", dirty=False, commit="abc1234"):
    return {"major": "2", "build": 7, "version": "v2.007", "commit": commit,
            "date": "", "source": source, "dirty": dirty}


# --------------------------------------------------------------------------- #
# health carries {version, commit, dirty}
# --------------------------------------------------------------------------- #
def test_health_reports_version_commit_and_dirty(tmp_path, monkeypatch):
    monkeypatch.setattr(app_version, "info", lambda: _fake(dirty=True))
    b = _live(tmp_path, monkeypatch).health()["build"]
    assert b == {"version": "v2.007", "commit": "abc1234", "dirty": True,
                 "source": "git", "nested": {}}


def test_a_clean_tree_reports_dirty_false(tmp_path, monkeypatch):
    monkeypatch.setattr(app_version, "info", lambda: _fake(dirty=False))
    assert _live(tmp_path, monkeypatch).health()["build"]["dirty"] is False


def test_an_unstamped_source_copy_is_unknown_not_clean(tmp_path, monkeypatch):
    # info() reports dirty False for "unknown"; health must not repeat that.
    monkeypatch.setattr(app_version, "info",
                        lambda: _fake(source="unknown", dirty=False, commit=""))
    assert _live(tmp_path, monkeypatch).health()["build"]["dirty"] is None


def test_a_stale_stamp_beside_a_checkout_is_unknown_not_clean(tmp_path, monkeypatch):
    # git failed at start; info() fell back to the last package's
    # _build_info.json. That names a build this process may not be running.
    monkeypatch.setattr("sonar.paths.is_frozen", lambda: False)
    monkeypatch.setattr(app_version, "info", lambda: _fake(source="baked"))
    assert _live(tmp_path, monkeypatch).health()["build"]["dirty"] is None


def test_a_frozen_bundle_trusts_its_own_stamp(tmp_path, monkeypatch):
    monkeypatch.setattr("sonar.paths.is_frozen", lambda: True)
    monkeypatch.setattr(app_version, "info", lambda: _fake(source="baked"))
    assert _live(tmp_path, monkeypatch).health()["build"]["dirty"] is False


@pytest.mark.parametrize("nested,want", [
    ({"macro": {"commit": "m", "dirty": False}}, False),
    ({"macro": {"commit": "m", "dirty": True}}, True),
    ({"macro": {"commit": "", "dirty": None}}, None),
    ({"macro": {"commit": "", "dirty": None},
      "playmaker": {"commit": "p", "dirty": True}}, True),
])
def test_a_nested_repo_folds_into_dirty(tmp_path, monkeypatch, nested, want):
    monkeypatch.setattr(app_version, "info", lambda: _fake(dirty=False))
    b = _live(tmp_path, monkeypatch, nested).health()["build"]
    assert b["dirty"] is want and b["nested"] == nested


def test_the_nested_repos_are_read_with_git(tmp_path, monkeypatch):
    (tmp_path / "sonar" / "macro" / ".git").mkdir(parents=True)
    (tmp_path / "sonar" / "playmaker").mkdir(parents=True)     # not a repo
    monkeypatch.setattr(app_version, "PROJECT_ROOT", tmp_path)
    seen = []
    monkeypatch.setattr(app_version, "_git_build",
                        lambda root: seen.append(root) or {"commit": "m", "dirty": True})
    assert app_version._nested() == {"macro": {"commit": "m", "dirty": True}}
    assert seen == [tmp_path / "sonar" / "macro"]


def test_the_build_is_read_at_start_not_per_request(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(app_version, "info", lambda: calls.append(1) or _fake())
    live = _live(tmp_path, monkeypatch)
    n = len(calls)
    live.health()
    live.health()
    assert len(calls) == n          # health() never shells out to git


def test_the_real_tree_reports_a_commit_and_a_bool():
    b = app_version.provenance()
    assert b["version"].startswith("v") and b["dirty"] in (True, False, None)
    assert b["commit"]


# --------------------------------------------------------------------------- #
# install_agent.sh refuses a dirty tree
# --------------------------------------------------------------------------- #
@pytest.fixture
def repo(tmp_path):
    """A scratch git checkout holding only the installer, with no .venv, so a
    run that gets past the dirty check stops at 'python not found' and never
    reaches launchctl."""
    (tmp_path / "scripts").mkdir()
    shutil.copy(SCRIPT, tmp_path / "scripts" / "install_agent.sh")
    (tmp_path / "tracked.txt").write_text("a\n")
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
           "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
           "HOME": str(tmp_path)}
    for cmd in (["init", "-q"], ["add", "."], ["commit", "-qm", "x"]):
        subprocess.run(["git", *cmd], cwd=tmp_path, env=env, check=True)
    return tmp_path, env


def _install(repo, *args):
    path, env = repo
    return subprocess.run(["bash", "scripts/install_agent.sh", *args], cwd=path,
                          env=env, capture_output=True, text=True, timeout=30)


def test_a_dirty_tree_is_refused(repo):
    (repo[0] / "tracked.txt").write_text("edited\n")
    r = _install(repo)
    assert r.returncode == 1
    assert "uncommitted" in r.stdout and "tracked.txt" in r.stdout
    assert "--allow-dirty" in r.stdout
    assert "not found" not in r.stdout          # stopped before the venv check


def test_allow_dirty_proceeds_loudly(repo):
    (repo[0] / "tracked.txt").write_text("edited\n")
    r = _install(repo, "--allow-dirty")
    assert "WARNING" in r.stdout and "installing anyway" in r.stdout
    assert ".venv/bin/python" in r.stdout        # got on to the next check


def test_a_clean_tree_is_not_warned(repo):
    r = _install(repo)
    assert "WARNING" not in r.stdout and ".venv/bin/python" in r.stdout


def test_untracked_files_do_not_count(repo):
    (repo[0] / "scratch.txt").write_text("x\n")
    assert "WARNING" not in _install(repo).stdout


def test_a_tree_git_cannot_read_is_treated_as_dirty(tmp_path):
    (tmp_path / "scripts").mkdir()
    shutil.copy(SCRIPT, tmp_path / "scripts" / "install_agent.sh")
    r = subprocess.run(["bash", "scripts/install_agent.sh"], cwd=tmp_path,
                       env={"PATH": "/usr/bin:/bin", "HOME": str(tmp_path),
                            "GIT_CEILING_DIRECTORIES": str(tmp_path.parent)},
                       capture_output=True, text=True, timeout=30)
    assert r.returncode == 1 and "git status failed" in r.stdout


def test_an_unknown_flag_is_a_usage_error(repo):
    r = _install(repo, "--bogus")
    assert r.returncode == 2 and "usage" in r.stdout


def test_two_flags_are_a_usage_error_not_an_install(repo):
    r = _install(repo, "--allow-dirty", "--uninstall")
    assert r.returncode == 2 and "usage" in r.stdout


def _nested_repo(path, env):
    nested = path / "sonar" / "macro"
    nested.mkdir(parents=True)
    (nested / "__init__.py").write_text("x = 1\n")
    for cmd in (["init", "-q"], ["add", "."], ["commit", "-qm", "x"]):
        subprocess.run(["git", *cmd], cwd=nested, env=env, check=True)
    return nested


def test_a_dirty_nested_repo_is_refused(repo):
    nested = _nested_repo(*repo)
    assert "WARNING" not in _install(repo).stdout       # clean nested: fine
    (nested / "__init__.py").write_text("x = 2\n")
    r = _install(repo)
    assert r.returncode == 1 and "sonar/macro:" in r.stdout and "__init__.py" in r.stdout


def test_a_long_list_still_says_why(repo):
    # echo | head under pipefail died of SIGPIPE (exit 141) past ~64 KB.
    path, env = repo
    for i in range(400):
        (path / f"{'f' * 200}{i}.txt").write_text("a\n")
    subprocess.run(["git", "add", "."], cwd=path, env=env, check=True)
    subprocess.run(["git", "commit", "-qm", "many"], cwd=path, env=env, check=True)
    for i in range(400):
        (path / f"{'f' * 200}{i}.txt").write_text("b\n")
    r = _install(repo)
    assert r.returncode == 1 and "Refusing" in r.stdout
    assert _install(repo, "--allow-dirty").stdout.count("installing anyway") == 1


def test_status_prints_the_running_build_as_json(repo):
    path, env = repo
    fake = path / "fakebin"
    fake.mkdir()
    (fake / "launchctl").write_text("#!/bin/sh\necho '    state = running'\n")
    (fake / "curl").write_text(
        "#!/bin/sh\necho '{\"ok\": true, \"build\": {\"commit\": \"abc\", \"dirty\": false}}'\n")
    for f in fake.iterdir():
        f.chmod(0o755)
    (path / ".venv" / "bin").mkdir(parents=True)
    os.symlink(sys.executable, path / ".venv" / "bin" / "python")
    r = subprocess.run(["bash", "scripts/install_agent.sh", "--status"], cwd=path,
                       env={**env, "PATH": f"{fake}:{env['PATH']}"},
                       capture_output=True, text=True, timeout=30)
    assert 'build: {"commit": "abc", "dirty": false}' in r.stdout
