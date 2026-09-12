"""The Lab tab: run the algorithm against history with the knobs exposed.

The point of this tab is falsification. The whole app rests on one identity —
`P(profit) = 1/(1+R:R)` — and the tab exists so that claim can be pointed at real
bars on demand rather than taken on trust.

The load-bearing test here is the last one. Every previous thread added to this
window was a crash on quit waiting to happen, because Qt aborts the process when
a running QThread is destroyed and `shutdown()` only stops the threads it is told
about. That has now happened twice.
"""

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from sonar.core import Live
from ui.app import MainWindow


@pytest.fixture(scope="module")
def window():
    app = QApplication.instance() or QApplication([])
    win = MainWindow(Live())
    win.poll.live.stop()
    win.poll.quit(); win.poll.wait(3000)
    yield win
    win.shutdown()


def test_the_tab_exists(window):
    assert "Lab" in [window.tabs.tabText(i) for i in range(window.tabs.count())]


def test_the_whole_watchlist_is_the_default_universe(window):
    from sonar.assets import WATCHLIST
    window.lab_universe.setCurrentIndex(0)
    assert len(window._lab_symbols()) == len(WATCHLIST)


def test_the_universe_can_be_narrowed_to_one_class(window):
    from sonar.assets import WATCHLIST
    window.lab_universe.setCurrentIndex(
        window.lab_universe.findData("Crypto"))
    syms = window._lab_symbols()
    expected = [s for s, _n, cls, _k in WATCHLIST if cls == "Crypto"]
    assert syms == expected and syms, "class filter returned the wrong set"
    window.lab_universe.setCurrentIndex(0)


def test_an_empty_result_renders_the_reason_not_a_crash(window):
    html = window._lab_html({"n": 0, "verdict": "no resolved trials"})
    assert "no resolved trials" in html


def test_a_result_inside_its_error_bar_is_reported_as_the_finding(window):
    """No edge is a result. The tab must not present it as a failure."""
    html = window._lab_html({
        "n": 500, "symbols": 10, "hit_rate": 0.393, "predicted": 0.400,
        "delta": -0.007, "std_error": 0.022, "significant": False,
        "expectancy_r": -0.017, "implied_edge_sigma": -0.004,
        "avg_bars_held": 6.1, "verdict": "no edge detected"})
    assert "no edge detected" in html
    assert "supposed to look like" in html


def test_the_predicted_rate_is_shown_next_to_the_realised_one(window):
    """The comparison is the entire point; a hit rate alone means nothing."""
    html = window._lab_html({
        "n": 100, "symbols": 5, "hit_rate": 0.40, "predicted": 0.40,
        "delta": 0.0, "std_error": 0.05, "significant": False,
        "expectancy_r": 0.0, "implied_edge_sigma": 0.0,
        "avg_bars_held": 5.0, "verdict": "ok"})
    assert "Realised hit rate" in html and "Predicted by the barrier maths" in html


def test_buckets_render_when_present(window):
    html = window._lab_html({
        "n": 100, "symbols": 5, "hit_rate": 0.4, "predicted": 0.4, "delta": 0.0,
        "std_error": 0.05, "significant": False, "expectancy_r": 0.0,
        "implied_edge_sigma": 0.0, "avg_bars_held": 5.0, "verdict": "ok",
        "buckets": [{"label": "0-2%", "n": 40, "hit_rate": 0.39, "delta": -0.01}]})
    assert "Momentum buckets" in html and "0-2%" in html


def test_the_lab_thread_is_in_the_shutdown_list(window):
    """A thread this window owns and shutdown() does not name is a SIGABRT on
    quit — the exact bug that shipped twice before."""
    import inspect
    src = inspect.getsource(MainWindow.shutdown)
    assert "_lab_thread" in src, \
        "the Lab tab's thread is not stopped at quit; Qt will abort the process"
