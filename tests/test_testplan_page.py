"""The in-app test plan page, and the thing that keeps it honest.

`static/testplan.html` is generated from `TESTPLAN.md`. A hand-maintained HTML
copy beside the markdown is exactly how `lab_hub/tools/convert` and
`toolbox/convert_epub` drifted apart — AGENTS.md says not to repeat it — so the
page is generated, `build_app.sh` regenerates it before packaging, and the first
test here fails if the two have fallen out of step.
"""

import pathlib
import re
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = ROOT / "TESTPLAN.md"
PAGE = ROOT / "static" / "testplan.html"


def test_the_page_is_up_to_date_with_the_markdown():
    """The whole point of generating it. Edit TESTPLAN.md, run
    `scripts/build_testplan.py`, commit both."""
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "build_testplan.py"), "--check"],
        capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_every_case_in_the_markdown_reaches_the_page():
    ids = set(re.findall(r'^\| (\d+\.\d+) ', SOURCE.read_text(), re.M))
    rendered = set(re.findall(r'data-case="([\d.]+)"', PAGE.read_text()))
    assert ids == rendered
    assert len(ids) >= 70


def test_the_regressions_are_still_marked():
    """Twenty cases carry a warning because each caught a real bug. Losing the
    marks would turn the plan into a flat list and lose its history."""
    assert PAGE.read_text().count('class="flag"') >= 15


def test_every_case_has_a_pass_and_a_fail_control():
    page = PAGE.read_text()
    cases = page.count('data-case="')
    # Named distinctly on purpose: `class="n"` is already the section-number
    # span, and the first version of this test counted 93 fail buttons against
    # 80 cases because of it.
    assert page.count('class="mark-pass"') == cases
    assert page.count('class="mark-fail"') == cases


def test_results_are_stored_per_browser_and_never_uploaded():
    """No network call anywhere on the page — the results are the user's."""
    page = PAGE.read_text()
    assert "localStorage" in page
    for forbidden in ("fetch(", "XMLHttpRequest", "navigator.sendBeacon", "http://", "https://"):
        assert forbidden not in page, f"the page reaches out via {forbidden}"


def test_the_page_says_so_when_it_cannot_save():
    """The app opens this as a file:// URL and some browsers refuse storage
    there. Failing silently would mean losing eighty cases of work without
    warning, so the page probes and says."""
    page = PAGE.read_text()
    assert "storage-note" in page
    assert "will not be saved" in page


def test_the_generated_page_warns_against_editing_it():
    assert "Do not edit" in PAGE.read_text()


# --------------------------------------------------------------------------- #
# Reachable from the app and from the daemon
# --------------------------------------------------------------------------- #
def test_the_app_has_a_button_for_it():
    app = (ROOT / "ui" / "app.py").read_text()
    assert 'QPushButton("Test plan")' in app
    assert "_open_testplan" in app


def test_the_button_reports_a_missing_page_rather_than_doing_nothing():
    """A frozen bundle that lost `static/` must say so, not look like a dead
    button — which is how the Assets read button once behaved."""
    app = (ROOT / "ui" / "app.py").read_text()
    body = app[app.index("def _open_page"):app.index("def _open_docs")]
    assert "not exists()" in body.replace("not page.exists()", "not exists()")
    assert "status.setText" in body


@pytest.mark.parametrize("route", ["/testplan", "/testplan/", "/testplan.html"])
def test_the_daemon_serves_it(route):
    server = (ROOT / "sonar" / "server.py").read_text()
    assert f'"{route}": "testplan.html"' in server


def test_the_build_regenerates_it_before_packaging():
    """Otherwise a bundle can ship a page that has drifted from the plan."""
    assert "build_testplan.py" in (ROOT / "build_app.sh").read_text()


def test_the_generator_terminates_on_every_heading_level():
    """It did not, once. A `###` subheading is not `## `, so it fell through to
    the paragraph branch — where `startswith('#')` stopped the loop before it
    consumed anything, and the cursor never advanced. The generator spun
    forever, which in a build script means a hung build with no error.
    """
    import subprocess
    import sys

    source = "\n".join([
        "# Title", "", "## 1. Section", "", "### A subheading", "",
        "Some prose.", "", "#### Deeper still", "", "| # | Steps | Expected |",
        "|---|---|---|", "| 1.1 | do a thing | it happens |", "",
    ])
    script = (
        "import pathlib, sys;"
        f"sys.path.insert(0, {str(ROOT / 'scripts')!r});"
        "import build_testplan as b;"
        f"b.SOURCE = pathlib.Path({str(ROOT)!r}) / '__probe__.md';"
        "b.SOURCE.write_text(sys.stdin.read());"
        "out = b.build();"
        "b.SOURCE.unlink();"
        "print(len(out))"
    )
    result = subprocess.run([sys.executable, "-c", script], input=source,
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    assert int(result.stdout.strip()) > 0


def test_subheadings_reach_the_page():
    assert "<h3>" in PAGE.read_text()


def test_the_paper_investment_loop_is_covered():
    """The question this section was added to answer: can you evaluate and hold
    positions, and find out whether they were worth taking, without real money."""
    md = SOURCE.read_text()
    for needed in ("closes **itself**", "calibration table", "cash at risk",
                   "excludes costs", "1.05"):
        assert needed in md, f"the paper loop no longer covers: {needed}"


def test_every_case_row_has_an_id_the_generator_recognises():
    """A malformed id is dropped in silence, which is worse than a crash.

    `build_testplan.py` matches case ids with `^\\d+\\.\\d+$`. A row numbered
    anything else — `1.10a`, say, which is the obvious way to insert a case
    between two others — still renders, but without a `data-case` attribute and
    without pass/fail buttons, and it is left out of the total. So the plan
    quietly loses a case, and the count at the top still looks right.

    That happened the moment a case was inserted. This fails instead.
    """
    import re

    rows = re.findall(r'^\| ([^|]+?) \|', SOURCE.read_text(), re.M)
    # Anything starting with a digit is meant to be a case id; the other tables
    # in this file (the header block) have words in that column.
    attempts = [r.strip() for r in rows if r.strip()[:1].isdigit()]
    bad = [i for i in attempts if not re.fullmatch(r'\d+\.\d+', i)]
    assert not bad, (
        f"case id(s) {bad} will be dropped from the generated page: the "
        r"generator only accepts ^\d+\.\d+$. Renumber the section instead of "
        "suffixing a letter.")
