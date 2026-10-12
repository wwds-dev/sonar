"""The agent runs the installed app, so a checkout edit cannot reach it.

t2-1 part 2, owner decision option A: launchd runs
``/Applications/SONAR.app/Contents/MacOS/SONAR --headless`` instead of the
checkout's python and main.py. These tests drive the real installer scripts
against a fake bundle, with ``launchctl``, ``codesign`` and ``pgrep`` replaced
on PATH and HOME in a temp directory: nothing here touches the real agent.
"""
from __future__ import annotations

import plistlib
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
LABEL = "com.netrunner3000.sonar"

FAKE_LAUNCHCTL = """#!/bin/sh
# Like launchd: a disabled service cannot be bootstrapped until enabled again.
echo "$1 $(cat "$WATCH/Contents/marker" 2>/dev/null || echo none)" >> "$CALLS"
case "$1" in
  print) exit "${PRINT_RC:-1}" ;;
  disable) touch "$CALLS.disabled" ;;
  enable) rm -f "$CALLS.disabled" ;;
  bootstrap) [ -e "$CALLS.disabled" ] && exit 5 ;;
esac
exit 0
"""


def _write(path: Path, text: str, mode: int = 0o644) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    path.chmod(mode)
    return path


def _bundle(at: Path, *, dirty="false", stamp=True, selftest=0, marker="new",
            installed_selftest=None) -> Path:
    """``installed_selftest`` is the self-test's exit code once the bundle sits
    in an Applications folder, to fail it after the swap only."""
    app = at / "SONAR.app"
    _write(app / "Contents" / "MacOS" / "SONAR",
           "#!/bin/sh\n"
           "[ \"$1\" = --selftest ] || exit 0\n"
           "echo \"${LEAK:-none} $SONAR_DATA\" > \"$HOME/selftest.env\"\n"
           + (f"case \"$0\" in */Applications/*) exit {installed_selftest};; esac\n"
              if installed_selftest is not None else "") +
           f"exit {selftest}\n", 0o755)
    _write(app / "Contents" / "marker", marker)
    if stamp:
        body = '{\n  "build": 191,\n  "commit": "abc1234",\n'
        if dirty is not None:
            body += f'  "dirty": {dirty},\n'
        _write(app / "Contents" / "Resources" / "_build_info.json",
               body + '  "source": "baked"\n}\n')
    return app


@pytest.fixture
def env(tmp_path):
    """A scratch project with the two scripts and the plist template, a fake
    toolbox first on PATH, and HOME inside tmp."""
    proj = tmp_path / "proj"
    for rel in ("scripts/install_agent.sh", "scripts/install_app.sh",
                "scripts/check_app.sh", f"packaging/{LABEL}.plist"):
        (proj / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, proj / rel)
    fake = tmp_path / "fakebin"
    _write(fake / "launchctl", FAKE_LAUNCHCTL, 0o755)
    _write(fake / "codesign", '#!/bin/sh\nexit "${CODESIGN_RC:-0}"\n', 0o755)
    # pgrep -f PATTERN against a fake process list ($PROCS), extended regex
    # like macOS pgrep.
    _write(fake / "pgrep", '#!/bin/sh\nprintf "%s\\n" "$PROCS" | grep -Eq -- "$2"\n', 0o755)
    _write(fake / "curl", "#!/bin/sh\nexit 7\n", 0o755)
    apps = tmp_path / "Applications"
    apps.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    e = {"PATH": f"{fake}:/usr/bin:/bin:/usr/sbin:/usr/local/bin:/opt/homebrew/bin",
         "HOME": str(home), "CALLS": str(tmp_path / "calls"),
         "WATCH": str(apps / "SONAR.app"), "SONAR_SETTLE_S": "0",
         "SONAR_APP": str(apps / "SONAR.app"), "SONAR_APPS_DIR": str(apps),
         "SONAR_UNSAFE_PATHS": "1"}
    return {"proj": proj, "apps": apps, "home": home, "env": e,
            "calls": tmp_path / "calls", "tmp": tmp_path}


def _run(env, script, *args, **extra):
    return subprocess.run(["bash", f"scripts/{script}", *args], cwd=env["proj"],
                          env={**env["env"], **extra}, capture_output=True,
                          text=True, timeout=60)


def _calls(env) -> list[str]:
    return env["calls"].read_text().splitlines() if env["calls"].exists() else []


def _plist(env) -> dict:
    with open(env["home"] / "Library" / "LaunchAgents" / f"{LABEL}.plist", "rb") as f:
        return plistlib.load(f)


# --------------------------------------------------------------------------- #
# install_agent.sh: the installed app by default
# --------------------------------------------------------------------------- #
def test_the_agent_runs_the_installed_app_by_default(env):
    app = _bundle(env["apps"])
    r = _run(env, "install_agent.sh")
    assert r.returncode == 0, r.stdout + r.stderr
    p = _plist(env)
    assert p["ProgramArguments"][:2] == [str(app / "Contents/MacOS/SONAR"), "--headless"]
    assert not any("main.py" in a for a in p["ProgramArguments"])
    data = str(env["home"] / "Library/Application Support/SONAR")
    assert p["WorkingDirectory"] == data
    assert p["EnvironmentVariables"]["SONAR_DATA"] == data
    logs = str(env["home"] / "Library/Logs/SONAR")
    assert p["StandardErrorPath"] == f"{logs}/agent.err.log"
    assert not any("__" in str(v) for v in p.values()), "a placeholder was left in"
    assert [c.split()[0] for c in _calls(env)][:3] == ["bootout", "enable", "bootstrap"]
    assert '"build":191' in r.stdout and '"commit":"abc1234"' in r.stdout


def test_a_dirty_checkout_does_not_matter_to_the_bundle(env):
    # The point of option A: what is on disk here is not what the agent runs.
    subprocess.run(["git", "init", "-q"], cwd=env["proj"], check=True)
    _write(env["proj"] / "x.py", "edit\n")
    subprocess.run(["git", "add", "x.py"], cwd=env["proj"], check=True)
    _bundle(env["apps"])
    r = _run(env, "install_agent.sh")
    assert r.returncode == 0 and "WARNING" not in r.stdout


def test_no_installed_app_is_refused(env):
    r = _run(env, "install_agent.sh")
    assert r.returncode == 1 and "no installed app" in r.stdout
    assert _calls(env) == []


def test_an_app_that_does_not_verify_is_refused(env):
    _bundle(env["apps"])
    r = _run(env, "install_agent.sh", CODESIGN_RC="1")
    assert r.returncode == 1 and "does not verify" in r.stdout
    assert _calls(env) == []


def test_an_unstamped_app_is_refused(env):
    _bundle(env["apps"], stamp=False)
    r = _run(env, "install_agent.sh")
    assert r.returncode == 1 and "no build stamp" in r.stdout


@pytest.mark.parametrize("dirty", ["true", None])     # None: no "dirty" key at all
def test_an_app_built_from_a_dirty_tree_is_refused(env, dirty):
    _bundle(env["apps"], dirty=dirty)
    r = _run(env, "install_agent.sh")
    assert r.returncode == 1 and "Refusing" in r.stdout
    assert "built from a tree that has uncommitted changes" in r.stdout
    assert _calls(env) == []
    r = _run(env, "install_agent.sh", "--allow-dirty")
    assert r.returncode == 0 and "going on" in r.stdout


def test_an_app_that_fails_its_selftest_is_refused(env):
    _bundle(env["apps"], selftest=1)
    r = _run(env, "install_agent.sh")
    assert r.returncode == 1 and "--selftest failed" in r.stdout
    assert _calls(env) == []


def test_status_names_the_logs_from_the_plist(env):
    _bundle(env["apps"])
    _run(env, "install_agent.sh")
    r = _run(env, "install_agent.sh", "--status", PRINT_RC="0")
    assert f"logs:  {env['home']}/Library/Logs/SONAR/agent.err.log" in r.stdout


# --------------------------------------------------------------------------- #
# install_agent.sh --checkout: the old way, for development
# --------------------------------------------------------------------------- #
def test_checkout_mode_runs_python_and_main_py(env):
    subprocess.run(["git", "init", "-q"], cwd=env["proj"], check=True)
    _write(env["proj"] / ".venv" / "bin" / "python", "#!/bin/sh\nexit 0\n", 0o755)
    r = _run(env, "install_agent.sh", "--checkout")
    assert r.returncode == 0, r.stdout + r.stderr
    p = _plist(env)
    proj = str(env["proj"])
    assert p["ProgramArguments"][:3] == [f"{proj}/.venv/bin/python", f"{proj}/main.py",
                                         "--headless"]
    assert p["WorkingDirectory"] == proj
    assert p["StandardErrorPath"] == f"{proj}/data/logs/agent.err.log"


@pytest.mark.parametrize("args", [["--bogus"], ["--status", "--checkout"],
                                  ["--uninstall", "--allow-dirty"]])
def test_bad_arguments_are_a_usage_error(env, args):
    r = _run(env, "install_agent.sh", *args)
    assert r.returncode == 2 and "usage" in r.stdout and _calls(env) == []


# --------------------------------------------------------------------------- #
# install_app.sh (./build_app.sh --install)
# --------------------------------------------------------------------------- #
def _agent_on_app(env):
    _bundle(env["apps"], marker="old")
    assert _run(env, "install_agent.sh").returncode == 0
    env["calls"].unlink()


def _marker(env) -> str:
    return (env["apps"] / "SONAR.app" / "Contents" / "marker").read_text()


def test_the_agent_is_disabled_and_stopped_around_the_swap(env):
    _agent_on_app(env)
    built = _bundle(env["tmp"] / "dist", marker="new")
    r = _run(env, "install_app.sh", str(built), PRINT_RC="0")      # running
    assert r.returncode == 0, r.stdout + r.stderr
    calls = [c for c in _calls(env) if not c.startswith("print")]
    assert calls[:2] == ["disable old", "bootout old"], "stopped before the swap"
    assert calls[-2:] == ["enable new", "bootstrap new"], "started on the new build"
    assert _marker(env) == "new"
    assert sorted(p.name for p in env["apps"].iterdir()) == ["SONAR.app"], "no leftovers"


def test_a_dirty_build_is_not_installed_under_the_agent(env):
    _agent_on_app(env)
    built = _bundle(env["tmp"] / "dist", dirty="true", marker="new")
    r = _run(env, "install_app.sh", str(built))
    assert r.returncode == 1 and "Refusing" in r.stdout
    assert [c for c in _calls(env) if not c.startswith("print")] == [], \
        "the agent was not stopped"
    assert _marker(env) == "old"


@pytest.mark.parametrize("bad", [{"selftest": 1}, {"stamp": False}])
def test_a_build_failing_its_checks_changes_nothing(env, bad):
    _agent_on_app(env)
    built = _bundle(env["tmp"] / "dist", marker="new", **bad)
    r = _run(env, "install_app.sh", str(built))
    assert r.returncode == 1 and _marker(env) == "old"
    assert [c for c in _calls(env) if not c.startswith("print")] == []


def test_a_failure_after_the_swap_leaves_the_agent_disabled_and_says_so(env):
    # The new build passes in dist/ but fails once installed: launchd must not
    # start it at the next login, which an enabled plist would.
    _agent_on_app(env)
    built = _bundle(env["tmp"] / "dist", marker="new", installed_selftest=1)
    r = _run(env, "install_app.sh", str(built), PRINT_RC="0")
    assert r.returncode != 0 and "STOPPED and DISABLED" in r.stdout
    assert (env["calls"].parent / "calls.disabled").exists()
    assert not any(c.startswith("bootstrap") for c in _calls(env))


def test_a_trailing_slash_installs_the_app_not_its_contents(env):
    built = _bundle(env["tmp"] / "dist", marker="new")
    r = _run(env, "install_app.sh", str(built) + "/")
    assert r.returncode == 0 and _marker(env) == "new"
    assert not (env["apps"] / "Contents").exists()


@pytest.mark.parametrize("src", ["/", "missing/SONAR.app", "dist/Other.app"])
def test_a_source_that_is_not_a_built_app_changes_nothing(env, src):
    _bundle(env["apps"], marker="old")
    (env["proj"] / "dist" / "Other.app").mkdir(parents=True)
    r = _run(env, "install_app.sh", src)
    assert r.returncode == 1 and "nothing was changed" in r.stdout
    assert _marker(env) == "old"


def test_the_apps_dir_override_is_for_tests_only(env):
    built = _bundle(env["tmp"] / "dist")
    r = _run(env, "install_app.sh", str(built), SONAR_UNSAFE_PATHS="0")
    assert r.returncode == 2 and "for tests" in r.stdout


def test_the_app_path_is_limited_to_the_standard_places(env):
    _bundle(env["apps"])
    r = _run(env, "install_agent.sh", SONAR_UNSAFE_PATHS="0")
    assert r.returncode == 2 and "is not /Applications/SONAR.app" in r.stdout
    assert _calls(env) == []


def test_paths_with_special_characters_reach_the_plist_intact(env):
    odd = env["tmp"] / "a&b|c </string>"
    app = _bundle(odd)
    r = _run(env, "install_agent.sh", SONAR_APP=str(app), WATCH=str(app))
    assert r.returncode == 0, r.stdout + r.stderr
    assert _plist(env)["ProgramArguments"][0] == str(app / "Contents/MacOS/SONAR")


def test_the_selftest_runs_without_the_installers_environment(env):
    _bundle(env["apps"])
    _run(env, "install_agent.sh", LEAK="from-the-shell")
    leak, data = (env["home"] / "selftest.env").read_text().strip().split(" ", 1)
    assert leak == "none", "the installer's environment reached the self-test"
    assert data.endswith("Library/Application Support/SONAR")


def test_allow_dirty_installs_under_the_agent(env):
    _agent_on_app(env)
    built = _bundle(env["tmp"] / "dist", dirty="true", marker="new")
    r = _run(env, "install_app.sh", str(built), "--allow-dirty", PRINT_RC="0")
    assert r.returncode == 0 and "bootstrap new" in _calls(env)


def test_without_the_agent_on_the_app_it_only_copies(env):
    built = _bundle(env["tmp"] / "dist", dirty="true", marker="new")
    r = _run(env, "install_app.sh", str(built))
    assert r.returncode == 0 and _calls(env) == []
    assert (env["apps"] / "SONAR.app" / "Contents" / "marker").read_text() == "new"


def test_a_failed_copy_changes_nothing_and_leaves_nothing(env):
    _agent_on_app(env)
    built = _bundle(env["tmp"] / "dist", marker="new")
    unreadable = built / "Contents" / "locked"
    unreadable.write_text("x")
    unreadable.chmod(0)                          # cp -R fails part-way
    try:
        r = _run(env, "install_app.sh", str(built))
    finally:
        unreadable.chmod(0o644)
    assert r.returncode != 0
    assert [c for c in _calls(env) if not c.startswith("print")] == [], \
        "the agent was never stopped"
    assert _marker(env) == "old"
    assert sorted(p.name for p in env["apps"].iterdir()) == ["SONAR.app"]


def test_the_plist_template_is_strict_xml():
    # "--" inside an XML comment is invalid; plutil -lint lets it through.
    import xml.dom.minidom
    xml.dom.minidom.parse(str(ROOT / "packaging" / f"{LABEL}.plist"))


def test_build_app_installs_through_install_app():
    text = (ROOT / "build_app.sh").read_text()
    install = text.split('if [[ "${1:-}" == "--install" ]]; then', 1)[1]
    assert "./scripts/install_app.sh" in install
    assert "rm -rf \"/Applications" not in install


def test_an_agent_stopped_on_purpose_stays_stopped(env):
    # RUNBOOK section 4: a restore boots the agent out and leaves its plist.
    _agent_on_app(env)
    built = _bundle(env["tmp"] / "dist", marker="new")
    r = _run(env, "install_app.sh", str(built), PRINT_RC="1")      # not loaded
    assert r.returncode == 0 and "left stopped" in r.stdout
    assert not any(c.startswith("bootstrap") for c in _calls(env))
    assert _marker(env) == "new"


def test_a_relative_source_is_read_from_where_it_was_typed(env):
    _bundle(env["tmp"] / "dist", marker="new")
    r = subprocess.run(["bash", str(env["proj"] / "scripts/install_app.sh"), "dist/SONAR.app"],
                       cwd=env["tmp"], env=env["env"], capture_output=True, text=True,
                       timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
    assert _marker(env) == "new"


def test_an_open_window_on_the_app_is_warned_about(env):
    built = _bundle(env["tmp"] / "dist", marker="new")
    r = _run(env, "install_app.sh", str(built),
             PROCS=f"{env['apps']}/SONAR.app/Contents/MacOS/SONAR")
    assert "window is open" in r.stdout


@pytest.mark.parametrize("proc", ["/x/.venv/bin/python /x/main.py --headless",
                                  "/Applications/SONAR.app/Contents/MacOS/SONAR --headless"])
def test_a_headless_sonar_outside_launchd_is_refused(env, proc):
    _bundle(env["apps"])
    r = _run(env, "install_agent.sh", PROCS=proc, PRINT_RC="1")
    assert r.returncode == 1 and "outside launchd" in r.stdout


def test_status_with_nothing_installed_does_not_uninstall(env):
    r = _run(env, "install_agent.sh", "--status")
    assert r.returncode == 0 and "not loaded" in r.stdout
    assert "Removed" not in r.stdout
    assert not any(c.startswith("bootout") for c in _calls(env))


# --------------------------------------------------------------------------- #
# the stamp names the nested repos (a bundle cannot ask them later)
# --------------------------------------------------------------------------- #
def _stamp_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location("stamp_version",
                                                  ROOT / "scripts" / "stamp_version.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("nested,want", [
    ({}, False),
    ({"macro": {"commit": "m", "dirty": False}}, False),
    ({"playmaker": {"commit": "p", "dirty": True}}, True),
    ({"macro": {"commit": "", "dirty": None}}, None),
])
def test_the_stamp_folds_the_nested_repos(monkeypatch, nested, want):
    mod = _stamp_module()
    monkeypatch.setattr(mod.version, "_nested", lambda: nested)
    assert mod.nested_state() == (nested, want)


def test_a_dirty_nested_repo_stamps_the_build_dirty(monkeypatch, tmp_path):
    mod = _stamp_module()
    monkeypatch.setattr(mod, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(mod, "_git_build", lambda root: {
        "build": 9, "commit": "abc", "date": "", "dirty": False})
    nested = {"playmaker": {"commit": "p", "dirty": True}}
    monkeypatch.setattr(mod.version, "_nested", lambda: nested)
    assert mod.main() == 0
    import json
    stamp = json.loads((tmp_path / "_build_info.json").read_text())
    assert stamp["dirty"] is True and stamp["nested"] == nested


def test_a_bundle_reports_the_nested_repos_from_its_stamp(monkeypatch):
    from sonar import version
    nested = {"macro": {"commit": "m", "dirty": False}}
    monkeypatch.setattr(version, "info", lambda: {
        "major": "2", "build": 9, "version": "v2.009", "commit": "abc", "date": "",
        "source": "baked", "dirty": False})
    monkeypatch.setattr(version, "_baked", lambda: {"build": 9, "nested": nested})
    monkeypatch.setattr("sonar.paths.is_frozen", lambda: True)
    b = version.provenance()
    assert b["nested"] == nested and b["dirty"] is False
