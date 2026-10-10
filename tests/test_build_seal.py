"""The bundle is re-sealed after its Info.plist is edited.

`build_app.sh` edits the version keys after PyInstaller signs the bundle, which
broke the ad-hoc signature (`spctl`: "invalid Info.plist"): tampering with the
installed app went undetectable. The script now re-signs and verifies.
"""

from pathlib import Path

SCRIPT = (Path(__file__).resolve().parent.parent / "build_app.sh").read_text()


def test_the_bundle_is_resealed_after_the_plist_edits_and_verified():
    edit = SCRIPT.rindex("plutil -replace")
    sign = SCRIPT.index("codesign --force --deep --sign -")
    verify = SCRIPT.index("codesign --verify --deep --strict")
    selftest = SCRIPT.rindex("--selftest")
    assert edit < sign < verify < selftest


def test_the_script_stops_on_a_failed_step():
    assert "set -e" in SCRIPT, "a failed verify must stop the build, not install it"
