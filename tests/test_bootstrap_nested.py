"""scripts/bootstrap_nested.sh puts the nested repos at the CI pins (spec A5).

Every case runs in a temporary main checkout with a worktree, against bare
"remote" repos reached by `file://` URLs: no network, and never this
checkout's own `sonar/macro` or `sonar/playmaker` (the script would move a copy
aside).
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t", "GIT_CONFIG_NOSYSTEM": "1"}
NAMES = ("macro", "playmaker")


def _env(home: Path) -> dict:
    return {**GIT_ENV, "HOME": str(home), "PATH": "/usr/bin:/bin:/usr/sbin:/opt/homebrew/bin",
            "GIT_TERMINAL_PROMPT": "0"}


def git(cwd, *args, home) -> str:
    return subprocess.run(["git", *args], cwd=cwd, env=_env(home), check=True,
                          capture_output=True, text=True).stdout.strip()


WORKFLOW = """jobs:
  t:
    steps:
      - uses: actions/checkout@v7
        with:
          fetch-depth: 0
      - uses: actions/checkout@v7
        with:
          repository: wwds-dev/sonar_macro
          ref: {macro}
          path: sonar/macro
      - uses: actions/checkout@v7
        with:
          repository: wwds-dev/sonar_playmaker
          ref: {playmaker}
          path: sonar/playmaker
"""


@pytest.fixture
def lab(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    remotes = tmp_path / "remotes" / "wwds-dev"
    remotes.mkdir(parents=True)
    pins, old = {}, {}
    for name in NAMES:
        work = tmp_path / f"seed_{name}"
        work.mkdir()
        git(work, "init", "-q", "-b", "master", home=home)
        (work / "__init__.py").write_text(f"{name} = 1\n")
        (work / "a.py").write_text("a = 1\n")
        git(work, "add", ".", home=home)
        git(work, "commit", "-qm", "one", home=home)
        old[name] = git(work, "rev-parse", "HEAD", home=home)
        (work / "a.py").write_text("a = 2\n")
        git(work, "commit", "-qam", "two", home=home)
        pins[name] = git(work, "rev-parse", "HEAD", home=home)
        git(tmp_path, "clone", "-q", "--bare", str(work),
            str(remotes / f"sonar_{name}.git"), home=home)

    main = tmp_path / "main"
    (main / "scripts").mkdir(parents=True)
    for f in ("bootstrap_nested.sh", "buildid.py"):
        shutil.copy2(ROOT / "scripts" / f, main / "scripts" / f)
    (main / ".github" / "workflows").mkdir(parents=True)
    (main / ".github" / "workflows" / "tests.yml").write_text(WORKFLOW.format(**pins))
    (main / ".gitignore").write_text("/sonar/macro/\n/sonar/playmaker/\n/.nested-bootstrap/\n")
    git(main, "init", "-q", "-b", "master", home=home)
    git(main, "add", ".", home=home)
    git(main, "commit", "-qm", "main", home=home)
    git(main, "remote", "add", "origin", f"file://{remotes}/sonar.git", home=home)
    for name in NAMES:          # the main checkout's own nested repos: the fallback
        git(main, "clone", "-q", f"file://{remotes}/sonar_{name}.git", f"sonar/{name}",
            home=home)
    wt = tmp_path / "wt"
    git(main, "worktree", "add", "-q", str(wt), "-b", "wt", home=home)
    return {"tmp": tmp_path, "home": home, "main": main, "wt": wt, "pins": pins, "old": old,
            "remotes": remotes}


def run(lab, *args, where="wt", fake=None, **extra):
    """``fake``: a directory put first on PATH (a fake git or mv)."""
    env = {**_env(lab["home"]), **extra}
    if fake:
        env["PATH"] = f"{fake}:{env['PATH']}"
    return subprocess.run(["bash", "scripts/bootstrap_nested.sh", *args], cwd=lab[where],
                          env=env, capture_output=True, text=True, timeout=120)


# A git that logs each call (and its network environment) and passes it on,
# except: FAKE_NOOP=<subcommand> succeeds without running it; FAKE_FAIL=<word>
# fails any call with that word; FAKE_DETACH_TO=<rev> checks that out instead
# of the sha a `checkout --detach` names.
FAKE_GIT = r"""#!/bin/bash
echo "$* | SSH=$GIT_SSH_COMMAND PROMPT=$GIT_TERMINAL_PROMPT" >> "$FAKE_LOG"
for a in "$@"; do
  [[ -n "${FAKE_NOOP:-}" && "$a" == "$FAKE_NOOP" ]] && exit 0
  [[ -n "${FAKE_FAIL:-}" && "$a" == "$FAKE_FAIL" ]] && exit 1
done
args=("$@")
if [[ -n "${FAKE_DETACH_TO:-}" && " $* " == *" --detach "* ]]; then
  args[$((${#args[@]} - 1))]="$FAKE_DETACH_TO"
fi
exec /usr/bin/git "${args[@]}"
"""


@pytest.fixture
def fake_git(lab):
    d = lab["tmp"] / "fakegit"
    d.mkdir()
    (d / "git").write_text(FAKE_GIT)
    (d / "git").chmod(0o755)
    return d


def _fake_mv(lab, fail_glob: str):
    d = lab["tmp"] / "fakemv"
    d.mkdir()
    (d / "mv").write_text(f'#!/bin/bash\ncase "$1" in {fail_glob}) exit 1 ;; esac\n'
                          'exec /bin/mv "$@"\n')
    (d / "mv").chmod(0o755)
    return d


def head(lab, name, where="wt"):
    return git(lab[where] / "sonar" / name, "rev-parse", "HEAD", home=lab["home"])


def assert_at_pins(lab):
    for name in NAMES:
        repo = lab["wt"] / "sonar" / name
        assert (repo / ".git").exists(), name
        assert head(lab, name) == lab["pins"][name]
        assert git(repo, "status", "--porcelain", "--untracked-files=no", home=lab["home"]) == ""


def _copy(lab, name, files: dict):
    at = lab["wt"] / "sonar" / name
    at.mkdir(parents=True)
    for rel, text in files.items():
        (at / rel).write_text(text)
    return at


def test_absent_repos_are_cloned_at_the_pins(lab):
    r = run(lab)
    assert r.returncode == 0, r.stdout + r.stderr
    assert_at_pins(lab)
    url = git(lab["wt"] / "sonar" / "macro", "remote", "get-url", "origin", home=lab["home"])
    assert url == f"file://{lab['remotes']}/sonar_macro.git"
    assert "./run-tests.sh tests/test_ci_pins.py -q" in r.stdout
    assert not (lab["wt"] / ".nested-bootstrap" / "lock").exists(), "the lock is released"


def test_a_copy_is_moved_aside_with_its_diff_reported(lab):
    copy_ = _copy(lab, "macro", {"__init__.py": "macro = 1\n", "a.py": "a = 'local edit'\n",
                                 "extra.py": "x\n"})
    _copy(lab, "playmaker", {"__init__.py": "playmaker = 1\n", "a.py": "a = 2\n"})
    r = run(lab)
    assert r.returncode == 0, r.stdout + r.stderr
    assert_at_pins(lab)
    assert f"macro: the copy differed from the pin {lab['pins']['macro'][:9]} in 2 files:" \
        in r.stdout
    assert f"playmaker: the copy was identical to the pin {lab['pins']['playmaker'][:9]}" \
        in r.stdout
    aside = list((lab["wt"] / ".nested-bootstrap").glob("macro.copy-*"))
    assert len(aside) == 1, "moved aside, never deleted"
    assert (aside[0] / "a.py").read_text() == "a = 'local edit'\n"
    assert not copy_.joinpath("extra.py").exists()
    # Domain P2-2: the per-repo summary is saved for the verify note.
    (report,) = (lab["wt"] / ".nested-bootstrap").glob("report-*.txt")
    text = report.read_text()
    assert "macro: the copy differed from the pin" in text and "identical to the pin" in text
    assert f"Report saved: {report}" in r.stdout


def test_a_repo_with_uncommitted_work_is_refused_and_untouched(lab):
    repo = lab["wt"] / "sonar" / "macro"
    git(lab["wt"], "clone", "-q", f"file://{lab['remotes']}/sonar_macro.git", "sonar/macro",
        home=lab["home"])
    (repo / "a.py").write_text("a = 'work in progress'\n")
    before = (repo / "a.py").stat().st_mtime_ns
    r = run(lab)
    assert r.returncode == 1
    assert "macro has uncommitted work (or git cannot read it)" in r.stdout
    assert (repo / "a.py").read_text() == "a = 'work in progress'\n"
    assert (repo / "a.py").stat().st_mtime_ns == before
    assert head(lab, "macro") == lab["pins"]["macro"]
    assert not list((lab["wt"] / ".nested-bootstrap").glob("macro.copy-*"))


def test_a_clean_repo_off_its_pin_is_refused_then_moved_with_move(lab):
    for name in NAMES:
        git(lab["wt"], "clone", "-q", f"file://{lab['remotes']}/sonar_{name}.git",
            f"sonar/{name}", home=lab["home"])
    repo = lab["wt"] / "sonar" / "macro"
    git(repo, "checkout", "-q", "-b", "mine", lab["old"]["macro"], home=lab["home"])
    r = run(lab)
    assert r.returncode == 1
    assert f"macro is at {lab['old']['macro'][:9]} on mine, but CI pins " \
           f"{lab['pins']['macro'][:9]}" in r.stdout
    assert "playmaker: already at the pin" in r.stdout
    assert head(lab, "macro") == lab["old"]["macro"]
    r = run(lab, "--move")
    assert r.returncode == 0, r.stdout
    assert_at_pins(lab)
    assert "git -C sonar/macro checkout mine" in r.stdout


def test_an_unreachable_remote_falls_back_to_the_main_checkout(lab):
    git(lab["main"], "remote", "set-url", "origin", f"file://{lab['tmp']}/gone/wwds-dev/sonar.git",
        home=lab["home"])
    r = run(lab)
    assert r.returncode == 0, r.stdout + r.stderr
    assert_at_pins(lab)
    assert "WARNING: macro cloned from the main checkout's local repo" in r.stdout
    assert "may not be pushed" in r.stdout
    repo = lab["wt"] / "sonar" / "macro"
    assert git(repo, "remote", "get-url", "origin", home=lab["home"]) == \
        f"file://{lab['tmp']}/gone/wwds-dev/sonar_macro.git"
    # Its origin/* refs were the main checkout's branches: dropped, so the
    # gate's "on origin" check is not fooled.
    assert git(repo, "for-each-ref", "refs/remotes/origin", home=lab["home"]) == ""


def test_a_pin_missing_everywhere_fails_and_moves_nothing(lab):
    wf = lab["wt"] / ".github" / "workflows" / "tests.yml"
    wf.write_text(WORKFLOW.format(macro="e" * 40, playmaker=lab["pins"]["playmaker"]))
    copy_ = _copy(lab, "macro", {"__init__.py": "macro = 1\n"})
    r = run(lab)
    assert r.returncode == 1
    assert f"macro: pin {'e' * 9} is not in" in r.stdout
    assert copy_.joinpath("__init__.py").read_text() == "macro = 1\n"
    assert not (copy_ / ".git").exists()
    assert not list((lab["wt"] / ".nested-bootstrap").glob("macro.*"))
    assert head(lab, "playmaker") == lab["pins"]["playmaker"]


def test_a_held_lock_is_refused(lab):
    (lab["wt"] / ".nested-bootstrap" / "lock").mkdir(parents=True)
    r = run(lab)
    assert r.returncode == 1 and "another bootstrap holds" in r.stdout
    assert not (lab["wt"] / "sonar").exists()
    assert (lab["wt"] / ".nested-bootstrap" / "lock").exists(), "someone else's lock is kept"


def test_unreadable_pins_touch_nothing(lab):
    (lab["wt"] / ".github" / "workflows" / "tests.yml").write_text("steps: []\n")
    copy_ = _copy(lab, "macro", {"__init__.py": "macro = 1\n"})
    r = run(lab)
    assert r.returncode == 1 and "cannot read the CI pins" in r.stdout
    assert not (copy_ / ".git").exists()


def test_in_the_main_checkout_there_is_no_local_fallback(lab):
    # The "fallback" would be the target itself.
    for name in NAMES:
        shutil.rmtree(lab["main"] / "sonar" / name)
    git(lab["main"], "remote", "set-url", "origin", f"file://{lab['tmp']}/gone/wwds-dev/sonar.git",
        home=lab["home"])
    r = run(lab, where="main")
    assert r.returncode == 1 and "there is no local fallback" in r.stdout


def test_already_at_the_pins_is_a_no_op(lab):
    assert run(lab).returncode == 0
    r = run(lab)
    assert r.returncode == 0
    assert all(f"{n}: already at the pin" in r.stdout for n in NAMES)


def test_a_bad_argument_is_a_usage_error(lab):
    r = run(lab, "--bogus")
    assert r.returncode == 2 and "usage" in r.stdout
    assert not (lab["wt"] / ".nested-bootstrap").exists()


# --------------------------------------------------------------------------- #
# The fix round (docs/audit/build-traceability-{code-reviewer,security,qa}.md)
# --------------------------------------------------------------------------- #
def test_the_postcondition_catches_a_checkout_that_landed_elsewhere(lab, fake_git):
    # QA P3-1 (M25): checkout --detach "succeeds" on another commit; only the
    # postcondition's HEAD == pin check can see it.
    wf = lab["wt"] / ".github" / "workflows" / "tests.yml"
    wf.write_text(WORKFLOW.format(macro=lab["old"]["macro"], playmaker=lab["pins"]["playmaker"]))
    r = run(lab, fake=fake_git, FAKE_LOG=str(lab["tmp"] / "git.log"), FAKE_DETACH_TO="master")
    assert r.returncode == 1
    assert f"not done: sonar/macro is not a clean checkout at {lab['old']['macro'][:9]}" in r.stdout
    assert "Bootstrap incomplete" in r.stdout


def _unreachable(lab):
    git(lab["main"], "remote", "set-url", "origin", f"file://{lab['tmp']}/gone/wwds-dev/sonar.git",
        home=lab["home"])


def test_a_failed_ref_drop_in_the_fallback_stops_that_repo(lab, fake_git):
    # Code review P3-2: inside `if`, set -e is off; the step is checked by hand.
    _unreachable(lab)
    r = run(lab, fake=fake_git, FAKE_LOG=str(lab["tmp"] / "git.log"), FAKE_FAIL="update-ref")
    assert r.returncode == 1
    assert "macro: could not drop refs/remotes/origin/" in r.stdout
    assert not (lab["wt"] / "sonar" / "macro").exists(), "nothing moved"


def test_origin_refs_left_after_the_fallback_stop_that_repo(lab, fake_git):
    # Code review P3-2: a drop that "succeeds" but leaves the refs is caught
    # by the final assertion.
    _unreachable(lab)
    r = run(lab, fake=fake_git, FAKE_LOG=str(lab["tmp"] / "git.log"), FAKE_NOOP="update-ref")
    assert r.returncode == 1
    assert "macro: the clone still has origin refs from the main checkout" in r.stdout
    assert not (lab["wt"] / "sonar" / "macro").exists()


def test_git_runs_non_interactive_bounded_and_checked(lab, fake_git):
    # Security P3-3 (no prompt, no hang), P3-4 (re-hash a local clone),
    # P3-5 (`--` before the URL).
    log = lab["tmp"] / "git.log"
    _unreachable(lab)
    assert run(lab, fake=fake_git, FAKE_LOG=str(log)).returncode == 0
    clones = [ln for ln in log.read_text().splitlines() if " clone " in f" {ln} "]
    assert len(clones) == 4, clones                      # remote, then fallback, per repo
    for ln in clones:
        assert "credential.interactive=never" in ln and "http.lowSpeedTime=30" in ln
        assert "transfer.fsckObjects=true" in ln and " -- " in ln
        assert "SSH=ssh -o BatchMode=yes -o ConnectTimeout=10" in ln and "PROMPT=0" in ln
    fallback = [ln for ln in clones if f"{lab['main']}/sonar/" in ln]
    assert len(fallback) == 2 and all("--no-local" in ln for ln in fallback)


def test_a_credentialed_origin_is_refused_and_never_printed(lab):
    # Code review P3-4, security P3-2.
    git(lab["main"], "remote", "set-url", "origin",
        "https://ghp_tok3n@github.invalid/wwds-dev/sonar.git", home=lab["home"])
    r = run(lab)
    assert r.returncode == 1 and "carries credentials" in r.stdout
    reports = list((lab["wt"] / ".nested-bootstrap").glob("report-*.txt"))
    assert "tok3n" not in r.stdout + r.stderr + "".join(p.read_text() for p in reports)
    assert not (lab["wt"] / "sonar").exists()


def test_a_symlinked_nested_dir_is_refused_and_its_target_untouched(lab):
    # Security P3-6.
    target = lab["tmp"] / "elsewhere"
    target.mkdir()
    (target / "keep.py").write_text("keep\n")
    (lab["wt"] / "sonar").mkdir()
    (lab["wt"] / "sonar" / "macro").symlink_to(target)
    r = run(lab, "--move")
    assert r.returncode == 1 and "sonar/macro is a symlink" in r.stdout
    assert (lab["wt"] / "sonar" / "macro").is_symlink()
    assert sorted(p.name for p in target.iterdir()) == ["keep.py"]


def test_a_failed_second_move_puts_the_copy_back(lab):
    # Code review P3-6, security P3-8b.
    copy_ = _copy(lab, "macro", {"__init__.py": "mine\n"})
    r = run(lab, fake=_fake_mv(lab, "*.tmp.*"))
    assert r.returncode == 1
    assert "macro: copy moved to " in r.stdout, "the aside path is said before the second move"
    assert "the clone could not be put in place; the copy was moved back" in r.stdout
    assert copy_.joinpath("__init__.py").read_text() == "mine\n" and not (copy_ / ".git").exists()
    assert not list((lab["wt"] / ".nested-bootstrap").glob("macro.copy-*"))


def test_when_the_copy_cannot_go_back_its_place_is_said(lab):
    _copy(lab, "macro", {"__init__.py": "mine\n"})
    r = run(lab, fake=_fake_mv(lab, "*.tmp.*|*.copy-*"))
    assert r.returncode == 1
    (aside,) = (lab["wt"] / ".nested-bootstrap").glob("macro.copy-*")
    assert f"the copy stays at {aside}" in r.stdout
    assert (aside / "__init__.py").read_text() == "mine\n"
