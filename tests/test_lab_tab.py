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


# --- replay: the same history, but the user makes the calls ---------------- #
def test_the_replay_controls_start_disabled(window):
    """Nothing to call until history is loaded; live buttons would be a lie."""
    assert not window.rep_long.isEnabled()
    assert not window.rep_short.isEnabled()


def test_every_watchlist_instrument_is_replayable(window):
    from sonar.assets import WATCHLIST
    assert window.rep_symbol.count() == len(WATCHLIST)


def test_the_scorecard_renders_an_empty_session(window):
    html = window._scorecard_html({
        "n_setups": 0, "n_taken": 0, "n_skipped": 0, "n_resolved": 0,
        "your_hit_rate": None, "your_std_error": None, "model_hit_rate": None,
        "predicted": 0.4, "your_pnl": 0.0, "model_pnl": 0.0, "stake": 100.0,
        "agreed_with_model": 0, "verdict": "0 resolved calls — too few"})
    assert "too few" in html and "Barrier baseline" in html


def test_the_scorecard_shows_your_pnl_against_the_model_s(window):
    """The monetary answer: what the calls actually won or lost, next to what
    the algorithm would have done on identical setups."""
    html = window._scorecard_html({
        "n_setups": 30, "n_taken": 25, "n_skipped": 5, "n_resolved": 25,
        "your_hit_rate": 0.44, "your_std_error": 0.099, "model_hit_rate": 0.40,
        "predicted": 0.4, "your_pnl": 350.0, "model_pnl": -100.0, "stake": 100.0,
        "agreed_with_model": 18, "verdict": "inside the bar"})
    assert "+350.00" in html and "-100.00" in html
    assert "Model P&amp;L" in html


def test_the_setup_line_does_not_reveal_the_model_s_call(window):
    """Showing the algorithm's direction before yours turns this into a test of
    whether you agree with it — a different, duller question.

    Checked on the rendered text rather than the source, because the first
    version of this test grepped the method body and matched the comment
    explaining the rule.
    """
    import random

    from sonar.backtest import Bars
    from sonar.replay import Session

    rng = random.Random(5)
    p, close, high, low, t = 100.0, [], [], [], []
    for i in range(300):
        p *= 1 + rng.gauss(0, 0.01)
        close.append(p); high.append(p * 1.01); low.append(p * 0.99)
        t.append(1_600_000_000 + i * 86400)
    # Keyword args: Bars is (symbol, time, open, high, low, close), and
    # passing positionally puts the closes in `open` — which renders as an
    # exhausted session rather than an error.
    bars = Bars(symbol="TEST", time=t, open=close, high=high, low=low,
                close=close)
    window._replay = Session(bars, horizon_days=5, step=3, stake=100.0)
    window._replay_render()

    shown = window.rep_setup.text()
    assert shown, "nothing rendered"
    assert "LONG" not in shown.upper().split("(LONG)")[0].replace("(LONG)", "")
    assert "SHORT" not in shown.upper()
    # The plan and the score are shown; the model's side is not.
    assert "score" in shown and "R:R" in shown
    window._replay = None
