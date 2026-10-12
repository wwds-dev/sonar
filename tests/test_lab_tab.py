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
    """Under its plain name, with the name the docs use beneath it — see
    `ui/tabs.py` for why both are on the bar."""
    bar = window.tabs.tabBar()
    names = [(window.tabs.tabText(i), bar._subtitles.get(i, ""))
             for i in range(window.tabs.count())]
    assert ("Practice", "LAB") in names


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


_INSIDE = ("The difference sits inside its own error bar: not shown to differ "
           "from the prediction, which is not the same as no difference.")


def test_a_result_inside_its_error_bar_is_reported_as_the_finding(window):
    """A gap inside its bar is a result, not a failure — and not 'no edge'
    either: not shown, which is not the same as shown absent (measure 9)."""
    html = window._lab_html({
        "n": 500, "symbols": 10, "hit_rate": 0.393, "predicted": 0.400,
        "delta": -0.007, "std_error": 0.022, "significant": False,
        "expectancy_r": -0.017, "implied_edge_sigma": -0.004,
        "avg_bars_held": 6.1, "verdict": "within"})
    assert _INSIDE in html
    assert "no edge" not in html and "supposed to look like" not in html


def test_the_predicted_rate_is_shown_next_to_the_realised_one(window):
    """The comparison is the entire point; a hit rate alone means nothing."""
    html = window._lab_html({
        "n": 100, "symbols": 5, "hit_rate": 0.40, "predicted": 0.40,
        "delta": 0.0, "std_error": 0.05, "significant": False,
        "expectancy_r": 0.0, "implied_edge_sigma": 0.0,
        "avg_bars_held": 5.0, "verdict": "ok"})
    # QA-13: the prediction is for setups that resolved in time, and says so.
    assert "Realised hit rate" in html
    assert "Predicted, for setups that resolved in time" in html


def test_timeouts_and_the_untimed_baseline_are_on_screen(window, monkeypatch):
    """T13-9 (success measure 6). How many setups ran out of time sits next to
    n; the untimed 1/(1+R:R) stays visible beside the timed prediction; and
    the expectancy row is the part beyond a market with nothing in it (D7).
    Mutation it catches: the timeout count or share dropped from the row."""
    from ui import words
    monkeypatch.setattr(words, "plain", lambda: True)
    r = {"n": 9_000, "symbols": 12, "hit_rate": 0.3935, "predicted": 0.3943,
         "baseline_untimed": 0.40, "delta": -0.0008, "std_error": 0.005,
         "significant": False, "expectancy_r": -0.0162,
         "expectancy_vs_null_r": -0.0019, "implied_edge_sigma": -0.0013,
         "avg_bars_held": 6.1, "verdict": "no edge detected",
         "n_timeout": 912, "n_timeout_data_end": 40, "timeout_share": 0.0776,
         "timeout_share_expected": 0.0546}
    html = window._lab_html(r)
    assert "9,000 across 12 instruments · 912 ran out of time (7.8%)" in html
    assert "39.43% (40% with unlimited time)" in html
    assert "Expectancy beyond a no-edge market" in html and "-0.002 R" in html
    assert "-0.016" not in html                  # the raw, null-negative figure
    monkeypatch.setattr(words, "plain", lambda: False)
    assert "Excess expectancy" in window._lab_html(r)


def test_the_terminal_backtest_line_says_how_many_timed_out(window):
    """The Terminal's one-line backtest names the timeouts too (Design:
    'append · {n_timeout} timed out'), and an older summary still renders.
    Mutation it catches: the timeout clause dropped from the line."""
    r = {"n": 9_000, "symbols": 12, "range": "2y", "horizon_days": 5,
         "hit_rate": 0.3935, "predicted": 0.3943, "delta": -0.0008,
         "std_error": 0.005, "expectancy_r": -0.0162, "verdict": "ok",
         "n_timeout": 912}
    window._backtest_done(r)
    first = window.bt_result.text().splitlines()[0]
    assert first.endswith("5d horizon · 912 timed out"), first
    window._backtest_done({k: v for k, v in r.items() if k != "n_timeout"})
    assert "timed out" not in window.bt_result.text()


def test_setups_too_near_the_end_of_the_data_are_counted_on_screen(window):
    """P1-1 (window floor). Setups with under two horizons of data after them
    are not compared, so the Lab and the Terminal line say how many there
    were, next to the timeouts.
    Mutation it catches: the short-window count dropped from either surface."""
    r = {"n": 9_000, "symbols": 12, "range": "2y", "horizon_days": 5,
         "hit_rate": 0.3935, "predicted": 0.3943, "delta": -0.0008,
         "std_error": 0.005, "significant": False, "expectancy_r": -0.0162,
         "implied_edge_sigma": -0.0013, "avg_bars_held": 6.1, "verdict": "ok",
         "n_timeout": 912, "timeout_share": 0.0776, "n_short_window": 387}
    html = window._lab_html(r)
    assert ("912 ran out of time (7.8%) · 387 too near the end of the data"
            in html), html
    window._backtest_done(r)
    first = window.bt_result.text().splitlines()[0]
    assert first.endswith("912 timed out · 387 too near the end of the data"), first


def test_a_run_where_everything_ran_out_says_how_many(window):
    """QA P3-5. When no setup resolved in a comparable window, 'no resolved
    trials' alone reads as if nothing happened. Both surfaces say how many ran
    out of time and of data, and both say what would leave room — the
    Terminal's line too, with the longest horizon the data could compare
    (code-review r2 P2-1, P3-1).
    Mutation it catches: the n = 0 early return dropping the counts, or the
    Terminal dropping the reason."""
    r = {"n": 0, "verdict": "nothing to compare", "n_timeout": 400,
         "n_timeout_data_end": 0, "n_short_window": 40,
         "longest_comparable_horizon": 166}
    html = window._lab_html(r)
    assert "nothing to compare" in html
    assert "400 ran out of time · 40 too near the end of the data" in html
    assert "two horizons" in html and "up to 166 days" in html
    window._backtest_done(r)
    text = window.bt_result.text()
    lines = text.splitlines()
    assert lines[0] == ("backtest: nothing to compare · 400 timed out · "
                        "40 too near the end of the data"), text
    assert "two horizons" in lines[1] and "up to 166 days" in lines[1], text
    # without the figure (an older summary) the reason still reads
    del r["longest_comparable_horizon"]
    assert "two horizons" in window._lab_html(r)
    assert "up to" not in window._lab_html(r)
    # nothing to count, nothing added
    assert window._lab_html({"n": 0, "verdict": "no resolved trials",
                             "n_timeout": 0}).count("<p") == 1


def test_the_terminal_line_reads_like_the_lab(window, monkeypatch):
    """QA P3-4 / code-review P3-3 (D7). The Terminal's prediction is the one
    for setups that resolved in time, and its expectancy is the part beyond a
    market with nothing in it — the raw figure reads negative on no edge, and
    the two can differ in sign. An older summary falls back to the raw one.
    Mutation it catches: the raw expectancy shown when the null one exists."""
    from ui import words
    monkeypatch.setattr(words, "plain", lambda: True)
    r = {"n": 9_000, "symbols": 12, "range": "2y", "horizon_days": 5,
         "hit_rate": 0.3935, "predicted": 0.3943, "delta": -0.0008,
         "std_error": 0.005, "expectancy_r": -0.0162,
         "expectancy_vs_null_r": 0.0067, "verdict": "ok", "n_timeout": 912}
    window._backtest_done(r)
    second = window.bt_result.text().splitlines()[1]
    assert "predicted 39.43% for setups that resolved in time" in second
    assert "expectancy beyond a no-edge market +0.007R" in second, second
    assert "-0.016" not in second
    monkeypatch.setattr(words, "plain", lambda: False)
    window._backtest_done(r)
    assert "excess expectancy +0.007R" in window.bt_result.text()
    old = {k: v for k, v in r.items() if k != "expectancy_vs_null_r"}
    window._backtest_done(old)
    assert "expectancy -0.016R" in window.bt_result.text()


def test_an_older_summary_without_the_new_fields_still_renders(window):
    """T13-9. Summaries built before QA-13 (and hand-built fixtures) lack the
    timeout and null-expectancy fields; the tab falls back, never raises."""
    html = window._lab_html({
        "n": 100, "symbols": 5, "hit_rate": 0.40, "predicted": 0.40,
        "delta": 0.0, "std_error": 0.05, "significant": False,
        "expectancy_r": 0.0, "implied_edge_sigma": 0.0,
        "avg_bars_held": 5.0, "verdict": "ok"})
    assert "ran out of time" not in html and "unlimited time" not in html
    assert "Expectancy" in html and "+0.000 R per setup" in html


def _walk(drift: float, n: int = 900, seed: int = 7, vol: float = 0.01):
    """A deterministic drifting walk, one bar a day (tests/test_backtest.py's
    `synthetic`), so the Lab is checked against what run() really returns."""
    import math
    from sonar import backtest
    bars = backtest.Bars(symbol="SYN")
    price, state = 100.0, seed
    for i in range(n):
        state = (1103515245 * state + 12345) % (2 ** 31)
        price *= math.exp(drift + ((state / (2 ** 31)) - 0.5) * 2 * vol)
        bars.time.append(i * 86400)
        bars.open.append(price)
        bars.high.append(price * (1 + vol))
        bars.low.append(price * (1 - vol))
        bars.close.append(price)
    return bars


def _bucket_cells(html: str, title: str) -> list[list[str]]:
    """The data rows of one bucket table, as lists of cell text."""
    import re
    table = html.split(f"{title}</h4>", 1)[1].split("</table>", 1)[0]
    return [re.findall(r"<td[^>]*>(.*?)</td>", row)
            for row in table.split("<tr>")[1:] if "<td" in row]


def test_momentum_buckets_render_their_label_and_gap_from_a_real_run(
        window, monkeypatch):
    """code-review r3 P2-2. The table read '?' for every momentum bucket and
    '+0.0 vs baseline' whatever the gap, because the renderer read keys the
    momentum buckets never carried. Now each row shows its band and its own
    hit rate minus its prediction — on run()'s real output. The attention
    table keeps its own names.
    Mutation it catches: the label or delta dropped from the buckets, or the
    renderer reading only `label`."""
    from sonar import backtest
    walks = {f"D{i}": _walk(0.004, seed=7 + i) for i in range(2)}
    monkeypatch.setattr(backtest, "fetch_bars", lambda sym, rng: walks[sym])
    r = backtest.run(list(walks), horizon_days=20, step=3)
    rows = _bucket_cells(window._lab_html(r), "Momentum buckets")
    assert len(rows) == len(r["buckets"]) > 0
    for cells, b in zip(rows, r["buckets"]):
        assert cells[0] == b["label"] and "?" not in cells[0]
        assert cells[3] == f"{b['delta'] * 100:+.1f}"
    assert any(c[3] != "+0.0" for c in rows), rows
    att = dict(r, attention_buckets=[{"name": "spike", "n": 40,
                                      "hit_rate": 0.5, "delta": 0.1}])
    assert _bucket_cells(window._lab_html(att), "Attention buckets")[0][0] == "spike"


def _thread_stub(made: list):
    class Stub:
        def __init__(self, symbols, horizon_days, parent=None, **kw):
            made.append(dict(kw, symbols=symbols, horizon_days=horizon_days))

        class _Sig:
            def connect(self, _fn):
                pass
        done = _Sig()
        progress = _Sig()

        def start(self):
            pass

        def isRunning(self):
            return False
    return Stub


def test_the_lab_tells_the_replay_which_universe_it_covers(window, monkeypatch):
    """P1-C. Only the whole watchlist gets a verdict, so the replay is told
    which universe the Lab picked — never left to guess it from the symbols.
    The Terminal's backtest is always the whole watchlist, and says so.
    Mutation it catches: the universe not passed (or passed as the class
    for the whole watchlist) from either surface."""
    import ui.app as app_mod
    made = []
    monkeypatch.setattr(app_mod, "BacktestThread", _thread_stub(made))
    monkeypatch.setattr(window, "_lab_thread", None)
    for data in ("all", "Crypto", "Equity"):
        window.lab_universe.setCurrentIndex(window.lab_universe.findData(data))
        window._lab_run()
        assert made[-1]["universe"] == data
        window._lab_thread = None
    window.lab_universe.setCurrentIndex(0)
    window.lab_btn.setEnabled(True)
    monkeypatch.setattr(window, "_bt_thread", None)
    window._run_backtest()
    assert made[-1]["universe"] == "all"
    window.bt_btn.setEnabled(True)


def test_the_backtest_thread_hands_the_universe_to_the_replay(monkeypatch):
    from sonar import backtest
    from ui.worker import BacktestThread
    seen = {}
    monkeypatch.setattr(backtest, "run",
                        lambda symbols, **kw: seen.update(kw) or {"n": 0})
    BacktestThread(["BTC-USD"], 5, universe="Crypto").run()
    assert seen["universe"] == "Crypto"
    BacktestThread(["BTC-USD"], 5).run()
    assert seen["universe"] == "all"


def test_a_run_without_a_verdict_shows_no_attention_or_attribution_finding(
        window, monkeypatch):
    """P2-1 (code-review r3) on screen. A run over one class, on rows where
    momentum and an attention spike genuinely sort winners, shows its
    numbers, the attention sentence that there is no reading, and every
    measured component 'not judged' — no keep / drop / backwards in either
    wording, and none of their colours.
    Mutation it catches: the gates removed in run(), or the renderer
    printing each component's verdict line regardless."""
    import random
    from sonar import backtest
    from ui import words
    rng = random.Random(1)
    rows = []
    for i in range(1000):
        m, spike = rng.random(), i % 2 == 0
        p = 0.1 + 0.5 * m + (0.25 if spike else 0.0)
        rows.append({"symbol": "AAPL", "t": (i % 100) * 86400,
                     "direction": "LONG", "momentum": 0.2 * m, "vol": 0.01,
                     "outcome": "TARGET" if rng.random() < p else "STOP",
                     "bars_held": 3, "predicted": 0.4, "rr": 1.5,
                     "k_target": 1.5, "k_stop": 1.0, "window": 20,
                     "horizons": 4.0, "truncated": False,
                     "short_window": False,
                     "attention": 3.0 if spike else -1.0, "c_momentum": m,
                     "c_volatility": 0.3, "c_news": 1.0 if spike else 0.0,
                     "c_catalyst": None})
    # three days apart, so the judged run falls in ten 32-day stretches; each
    # row carries its opposite outcome, the mirror of its own (docs/adr/0003)
    flip = {"TARGET": "STOP", "STOP": "TARGET"}
    rows = [dict(r, t=r["t"] * 3, opp_outcome=flip[r["outcome"]],
                 opp_bars_held=3, opp_predicted=0.4) for r in rows]
    monkeypatch.setattr(backtest, "fetch_bars", lambda sym, rng_: _walk(0.0, n=60))
    monkeypatch.setattr(backtest, "run_symbol", lambda *a, **k: list(rows))
    judged = backtest.run(["AAPL"], horizon_days=5)
    one = backtest.run(["AAPL"], horizon_days=5, universe="Equity")
    assert judged["withheld"] is None and one["withheld"] == "single_class"
    for plain in (True, False):
        monkeypatch.setattr(words, "plain", lambda p=plain: p)
        control = window._lab_html(judged)
        assert "shifts the odds" in control and "#98c379" in control
        html = window._lab_html(one)
        assert "No verdict on Equity alone." in html
        assert "No reading on attention either" in html
        assert "shifts the odds" not in html
        assert html.count(backtest.NOT_JUDGED) == 1
        attribution = html.split("Component attribution", 1)[1]
        cells = [c.split("'>", 1)[1].split("<", 1)[0]
                 for c in attribution.split("<b style='color:")[1:]]
        assert "not judged" in cells, cells
        assert set(cells) <= {"not judged", "not measured", "—"}, cells
        for colour in ("#98c379", "#e06c75", "#e5c07b"):
            assert colour not in html, (plain, colour)
        assert "survives FDR" not in html and "push the wrong" not in html
        assert "Realised hit rate" in html and "Momentum buckets" in html


def _blend_rows(seed: int, backwards: bool) -> list[dict]:
    """1,500 setups whose blended score ranks backwards (high momentum and
    volatility lose), or is noise: seed 43's noise blend is negative (IC
    −0.068, Newey-West t −2.56), past two standard errors and inside the
    claim bar of three."""
    import random
    rng = random.Random(seed)
    rows = []
    for i in range(1500):
        m, v = rng.random(), rng.random()
        p = 0.75 - 0.5 * (0.3 * m + 0.15 * v) / 0.45 if backwards else 0.4
        rows.append({"outcome": "TARGET" if rng.random() < p else "STOP",
                     "predicted": 0.4, "bars_held": 5, "momentum": m, "vol": v,
                     "t": i * 86400, "c_momentum": m, "c_volatility": v,
                     "c_news": None, "c_catalyst": None})
    return rows


def test_the_score_ranks_backwards_only_on_a_judged_significant_blend(
        monkeypatch):
    """Code review r4 P2-1. 'The score as a whole is ranking the wrong way
    round' printed whenever the blend IC was ≤ 0 — above 'Not judged' on a
    withheld run, and on noise. Now it shows only on a judged run whose
    blend clears the claim bar; a negative blend on a withheld run, and a
    negative blend inside its noise on a judged one, show the number alone.
    Mutation it catches: the sentence keyed to the sign again, or shown on
    a withheld run."""
    from sonar import backtest
    from ui import words
    sentence = "ranking the wrong way round"
    strong = backtest.attribute(_blend_rows(1, backwards=True), gate=False)
    withheld = backtest.attribute(_blend_rows(1, backwards=True),
                                  withheld="single_class", gate=False)
    noise = backtest.attribute(_blend_rows(43, backwards=False), gate=False)
    assert strong["blend_ic"] < 0 and withheld["blend_ic"] < 0
    assert noise["blend_ic"] < 0 and not noise["blend_ranks_backwards"]
    for plain in (True, False):
        monkeypatch.setattr(words, "plain", lambda p=plain: p)
        assert sentence in MainWindow._attribution_html(strong)
        for a in (withheld, noise):
            html = MainWindow._attribution_html(a)
            assert sentence not in html, (plain, a["blend_ic"])
            assert f"<b>{a['blend_ic']:+.3f}</b>" in html        # the number stays
        # a flag on a withheld summary is still not shown; an older summary
        # without the flag never says it
        assert sentence not in MainWindow._attribution_html(
            dict(strong, withheld="span"))
        older = {k: v for k, v in strong.items() if k != "blend_ranks_backwards"}
        assert sentence not in MainWindow._attribution_html(older)


def test_the_lab_thread_is_in_the_shutdown_list(window):
    """A thread this window owns and shutdown() does not name is a SIGABRT on
    quit — the exact bug that shipped twice before."""
    import inspect
    src = inspect.getsource(MainWindow._owned_threads)
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


# --------------------------------------------------------------------------- #
# The sports models, measurable from inside the app
# --------------------------------------------------------------------------- #
def test_the_sports_measure_panel_offers_only_measurable_sports(window):
    """A model needs a rating *and* a results feed. Golf has no model by
    design and cycling has no feed — offering either would be a button that
    can only fail."""
    from sonar import playmaker
    offered = {window.sm_sport.itemData(i)
               for i in range(window.sm_sport.count())}
    expected = {s.key for s in playmaker.list_sports()
                if s.has_model and s.has_results}
    assert offered == expected and offered, "every measurable sport, only those"


def test_a_measurement_result_is_rendered_with_its_verdict(window):
    window._sports_measured({
        "sport": "nba", "n_games": 1200, "verdict": "KEEP", "untuned": False,
        "summary": "KEEP: Brier 0.2100 beats the base-rate baseline 0.2300 "
                   "(skill +0.087).",
        "buckets": [{"low": 0.6, "high": 0.7, "n": 300,
                     "predicted": 0.648, "realised": 0.655}]})
    assert "KEEP" in window.sm_result.text()
    assert "said 65%, got 66%" in window.sm_result.text()
    assert window.sm_btn.isEnabled()


def test_an_untuned_sport_says_its_settings_are_a_stand_in(window):
    window._sports_measured({
        "sport": "mma", "n_games": 400, "verdict": "WEAK", "untuned": True,
        "summary": "WEAK: …", "buckets": []})
    assert "stand-in" in window.sm_result.text()


def test_the_sports_thread_is_on_the_shutdown_list(window):
    """The trap that has shipped twice: a thread missing from shutdown() is a
    SIGABRT on quit whenever that feature happens to be mid-flight."""
    assert "sports_measure" in dict(window._owned_threads())


def test_the_catalyst_series_is_one_checkbox_away(window):
    """The component that was untested until Sep 2026 must stay re-measurable
    from inside the app, not only from the script that first measured it."""
    from ui.worker import BacktestThread
    assert not window.lab_catalyst.isChecked(), "off by default — it fetches"
    t = BacktestThread(["AAPL"], 5, with_catalyst=True)
    assert t.with_catalyst is True


def _judged(**over) -> dict:
    """A whole-watchlist summary as run() returns it."""
    r = {"n": 9_000, "symbols": 129, "range": "2y", "horizon_days": 5,
         "hit_rate": 0.3935, "predicted": 0.3943, "delta": -0.0008,
         "std_error": 0.005, "significant": False, "expectancy_r": -0.0162,
         "implied_edge_sigma": -0.0013, "avg_bars_held": 6.1,
         "verdict": "no edge detected", "n_timeout": 912,
         "timeout_share": 0.0776, "n_short_window": 387,
         "symbols_compared": 129,
         "compared_by_class": {"Equity": 50, "Crypto": 21, "Index": 20,
                               "Forex": 20, "Commodity": 18},
         "n_entry_dates": 481, "first_entry": "2024-10-14",
         "last_entry": "2026-09-29", "withheld": None}
    r.update(over)
    return r


def test_a_run_without_a_verdict_shows_the_numbers_and_why(window):
    """P1-A / P1-B. A withheld verdict is not 'no edge': the Lab keeps every
    number, prints the reason, and does not add 'that is what no edge looks
    like' even when the difference sits inside its bar; the Terminal prints
    the same reason.
    Mutation it catches: the 'no edge' paragraph or the finding colour on a
    withheld run."""
    why = ("No verdict at a 250-day horizon. At horizons this long an "
           "instrument's own trend dominates the comparison")
    r = _judged(horizon_days=250, range="5y", withheld="horizon",
                verdict=why + ".", delta=0.0237, std_error=0.006)
    html = window._lab_html(r)
    assert why in html
    assert "Realised hit rate" in html and "+2.37 pts" in html
    assert "#e5c07b" not in html                  # not coloured as a finding
    inside = _judged(withheld="too_few", verdict="Too few to judge: 60 ...")
    assert _INSIDE not in window._lab_html(inside)
    assert _INSIDE in window._lab_html(_judged())
    window._backtest_done(r)
    assert f"  {why}." in window.bt_result.text().splitlines()


def test_the_lab_names_the_error_bar_not_standard_errors(window):
    """Loop 5 (validator r5): the difference line says what the bar is —
    setups entered on the same day counted together — not '2 s.e.'.
    Mutation it catches: the old '(± x at 2 s.e.)' back."""
    html = window._lab_html(_judged(delta=0.0031, std_error=0.0088))
    assert ("+0.31 pts  (error bar ±1.76; setups entered on the same day "
            "counted together)") in html, html
    assert "s.e." not in html


def test_the_lab_colour_follows_the_verdict_not_the_rounded_figures(window):
    """Code review r5 P3-5. summarise decides on unrounded figures; the
    colour re-derived from the rounded delta and se could disagree at the
    boundary. Here the rounded figures sit exactly on 2 se: the colour
    follows `significant` either way. A hand-built summary without the flag
    falls back to the figures.
    Mutation it catches: the colour from |delta| <= 2 se again."""
    edge = dict(delta=0.01, std_error=0.005)
    finding = window._lab_html(_judged(significant=True, **edge))
    assert "<p style='color:#e5c07b'><b>" in finding
    assert _INSIDE not in finding
    inside = window._lab_html(_judged(significant=False, **edge))
    assert "#e5c07b" not in inside and _INSIDE in inside
    older = {k: v for k, v in _judged(delta=0.02, std_error=0.005).items()
             if k != "significant"}
    assert "<p style='color:#e5c07b'><b>" in window._lab_html(older)


def test_attention_buckets_show_the_figure_they_are_judged_on(window):
    """Code review r5 P3-1. Attention buckets are judged against the run
    (`vs_run`); the table showed `delta` under 'vs baseline', so a run 3
    points above the prediction everywhere read '+3.0' on every row above
    'no attention level stood apart'. Now that column is `vs_run`, headed
    'vs setups with attention' (code review r6 P3-1: 'the run as a whole'
    read as every setup, as in the momentum table above it); momentum
    buckets keep 'vs baseline', and an older summary without `vs_run` shows
    the gap under 'vs baseline'.
    Mutation it catches: the attention column back on `delta`, or headed
    against the whole run."""
    att = [{"name": "normal", "n": 400, "hit_rate": 0.43, "delta": 0.03,
            "vs_run": 0.002}, {"name": "spike", "n": 120, "hit_rate": 0.42,
                               "delta": 0.03, "vs_run": -0.004}]
    mom = [{"label": "0–2%", "n": 500, "hit_rate": 0.43, "delta": 0.03}]
    html = window._lab_html(_judged(attention_buckets=att, buckets=mom))
    assert [c[3] for c in _bucket_cells(html, "Attention buckets")] == [
        "+0.2", "-0.4"]
    assert _bucket_cells(html, "Momentum buckets")[0][3] == "+3.0"
    att_table = html.split("Attention buckets</h4>", 1)[1].split("</table>")[0]
    mom_table = html.split("Momentum buckets</h4>", 1)[1].split("</table>")[0]
    assert "vs setups with attention" in att_table
    assert "vs baseline" not in att_table and "as a whole" not in att_table
    assert "vs baseline" in mom_table
    older = [{k: v for k, v in b.items() if k != "vs_run"} for b in att]
    html = window._lab_html(_judged(attention_buckets=older))
    assert [c[3] for c in _bucket_cells(html, "Attention buckets")] == [
        "+3.0", "+3.0"]


def test_the_instruments_and_dates_actually_compared_are_on_screen(window):
    """Disclosure (model-validator r2 P2-A, P2-C). 'Across N instruments' is
    the instruments that reached the comparison, not those fetched; the Lab
    names them by class and gives the span of entry dates; the Terminal line
    carries the compared count.
    Mutation it catches: the fetched count shown as the compared one."""
    r = _judged(horizon_days=120, symbols_compared=21,
                compared_by_class={"Crypto": 21}, n_entry_dates=170,
                first_entry="2024-10-14", last_entry="2025-04-02")
    html = window._lab_html(r)
    assert "9,000 across 21 instruments (of 129 fetched)" in html, html
    assert "21 Crypto" in html
    assert "2024-10-14 to 2025-04-02 · 170 dates" in html
    window._backtest_done(r)
    first = window.bt_result.text().splitlines()[0]
    assert "9,000 resolved trials across 21 instruments" in first, first
    full = window._lab_html(_judged())
    assert "9,000 across 129 instruments ·" in full and "fetched" not in full
    # in the order the summary gives (largest class first)
    assert "50 Equity · 21 Crypto · 20 Index · 20 Forex · 18 Commodity" in full


def test_no_setups_too_near_the_end_says_nothing_about_them(window):
    """QA r2 P3 / code-review r2 P3-2: at h = 1 the count is always 0, and
    '· 0 too near the end of the data' on every Intraday line is noise.
    Mutation it catches: the clause back on `is not None`."""
    r = _judged(n_short_window=0)
    assert "too near the end" not in window._lab_html(r)
    window._backtest_done(r)
    assert "too near the end" not in window.bt_result.text()


def test_the_terminal_backtest_reads_far_enough_back_for_its_horizon(window, monkeypatch):
    """code-review r2 P2-1. On the 'This year' profile two years of bars
    compared nothing; the Terminal now reads five, and says which."""
    from sonar import horizon
    import ui.app as app_mod
    made = []

    class Stub:
        def __init__(self, symbols, horizon_days, parent=None, **kw):
            made.append((horizon_days, kw.get("rng")))

        class _Sig:
            def connect(self, _fn):
                pass
        done = _Sig()

        def start(self):
            pass

        def isRunning(self):
            return False

    monkeypatch.setattr(app_mod, "BacktestThread", Stub)
    monkeypatch.setattr(window, "_bt_thread", None)
    for hz, rng, words_ in ((horizon.YEAR, "5y", "five years"),
                            (horizon.WEEK, "2y", "two years")):
        monkeypatch.setattr(window.live, "horizon", hz)
        window._run_backtest()
        assert made[-1] == (hz.momentum_days, rng)
        assert window.bt_result.text() == f"replaying {words_} of bars…"
        window._bt_thread = None
    assert "five" in window.bt_btn.toolTip()
    window.bt_btn.setEnabled(True)


# --------------------------------------------------------------------------- #
# The direction randomisation on screen (docs/adr/0003)
# --------------------------------------------------------------------------- #
def _rand(p_tail: float, q: int = 22, p: float | None = None) -> dict:
    return {"p": p_tail if p is None else p, "p_tail": p_tail, "q": q,
            "draws": 11_999, "method": "monte_carlo", "block_days": 32,
            "seed": 1}


def test_not_told_apart_from_chance_is_grey_and_never_within(window, monkeypatch):
    """Measure 11 on screen. A run outside its bar that the randomisation
    does not confirm is grey, never the finding colour, and never gets the
    'inside its own error bar' paragraph, which shows for 'within' only; in
    neither wording does the page say 'unconfirmed'. The mirror, outside
    the bar and confirmed, is a finding.
    Mutation it catches: the state read as 'within', or coloured from
    `outside_bar`."""
    from sonar import backtest
    from ui import words
    grey = _judged(delta=0.031, std_error=0.014, significant=False,
                   outside_bar=True, verdict_state="unconfirmed",
                   randomisation=_rand(0.31),
                   verdict=backtest._verdict(0.031, 0.014, "unconfirmed"))
    beats = dict(grey, significant=True, verdict_state="beats",
                 randomisation=_rand(0.004),
                 verdict=backtest._verdict(0.031, 0.014, "beats"))
    within = _judged(verdict_state="within", outside_bar=False,
                     randomisation=_rand(0.6),
                     verdict=backtest._verdict(-0.0008, 0.005, "within"))
    for plain in (True, False):
        monkeypatch.setattr(words, "plain", lambda p=plain: p)
        html = window._lab_html(grey)
        assert "<p style='color:#7c8798'><b>" in html and "#e5c07b" not in html
        assert "not told apart from chance" in html
        assert _INSIDE not in html and "unconfirmed" not in html.lower()
        assert "<p style='color:#e5c07b'><b>" in window._lab_html(beats)
        inside = window._lab_html(within)
        assert _INSIDE in inside and "#e5c07b" not in inside


def test_every_headline_reading_names_the_fixed_direction_residual(
        window, monkeypatch):
    """Owner, after validator r7 P1-2: beats, below and not told apart from
    chance each name the residual the randomisation cannot see — a direction
    fixed per instrument, such as always long on today's list — in both
    wordings, on the Lab and the Terminal line. 'within' makes no reading
    of a direction, so it does not.
    Mutation it catches: the residual dropped from any one sentence or
    surface."""
    from sonar import backtest
    from ui import words
    residual = ("A direction fixed per instrument, such as always long on "
                "today's list, can beat the bar too.")
    for state, delta in (("beats", 0.031), ("below", -0.031),
                         ("unconfirmed", 0.031)):
        r = _judged(delta=delta, std_error=0.014, verdict_state=state,
                    significant=state != "unconfirmed", outside_bar=True,
                    randomisation=_rand(0.004 if state != "unconfirmed"
                                        else 0.31),
                    verdict=backtest._verdict(delta, 0.014, state))
        for plain in (True, False):
            monkeypatch.setattr(words, "plain", lambda p=plain: p)
            assert residual in window._lab_html(r), (state, plain)
            window._backtest_done(r)
            assert residual in window.bt_result.text(), (state, plain)
    assert "fixed per instrument" not in backtest._verdict(0.001, 0.014,
                                                           "within")


def test_the_terminal_says_what_its_backtest_cannot_judge(window, monkeypatch):
    """Domain P2-3 and P3-5, A15 as amended after validator r7: the
    Terminal footer says the instruments are today's list, survivors only,
    which favours long trades over long ranges; too few stretches names the
    fix the Terminal's reader has (a shorter profile, not a range); and the
    button's tooltip does not imply the quarter or year profiles are judged.
    Mutation it catches: the survivorship line dropped, the Lab's range
    advice shown in the Terminal, or the tooltip claiming ten years."""
    from sonar import backtest
    from ui import words
    monkeypatch.setattr(words, "plain", lambda: False)
    few = _judged(horizon_days=60, withheld="few_clusters",
                  verdict_state="withheld",
                  randomisation={"p": None, "p_tail": None, "q": 2,
                                 "draws": 0, "method": None,
                                 "block_days": 348, "seed": None},
                  verdict=backtest.few_clusters_verdict(2, 60))
    window._backtest_done(few)
    text = window.bt_result.text()
    assert backtest.few_clusters_verdict(2, 60, terminal=True) in text, text
    assert "A shorter profile gives more." in text
    assert "A longer range" not in text
    assert ("  The instruments are today's list; ones that fell away are "
            "missing, which favours long trades over long ranges."
            in text.splitlines()), text
    # the Lab keeps the range advice: its reader picks the range
    assert "A longer range or a shorter horizon gives more." in (
        window._lab_html(few))
    tip = window.bt_btn.toolTip()
    assert "five for the month" in tip
    assert "The quarter and year profiles show the\nnumbers without a verdict" in tip
    assert "ten for" not in tip and "ten years" not in tip
    assert "and the year" not in tip and "quarter —" not in tip


def test_the_expert_view_shows_the_randomisation_p_in_the_direction_of_delta(
        window, monkeypatch):
    """[A3] (domain pass 2 P2-C): expert wording shows p_tail, labelled 'in
    the direction of Δ', with the stretch count — never the equal-tailed p,
    which is a field only — on the Lab and the Terminal line. Plain wording
    shows no new number.
    Mutation it catches: the line reading `p`, or shown in plain wording."""
    from ui import words
    r = _judged(randomisation=_rand(0.0123, q=9, p=0.9))
    monkeypatch.setattr(words, "plain", lambda: False)
    html = window._lab_html(r)
    assert ("p vs random directions, in the direction of Δ</td><td "
            "style='padding:2px 0'><b>0.0123  (9 stretches)</b>") in html, html
    assert "0.9000" not in html
    # twice the one-sided share, as direction_p computes it (domain P3-1)
    assert ("twice the share of random-direction reshuffles of whole "
            "stretches that read at least this far in the direction of Δ, "
            "at most 1") in html
    window._backtest_done(r)
    assert ("  p vs random directions, in the direction of Δ: 0.0123 "
            "(9 stretches)") in window.bt_result.text().splitlines()
    monkeypatch.setattr(words, "plain", lambda: True)
    assert "random directions" not in window._lab_html(r)
    assert "0.0123" not in window._lab_html(r)
    window._backtest_done(r)
    assert "random directions" not in window.bt_result.text()


def test_a_component_not_told_apart_from_chance_reads_so_in_grey(monkeypatch):
    """Measure 11 for attribution, on screen: 'UNCONFIRMED' is an internal
    name. Both wordings show 'not told apart from chance', in grey, with the
    sentence; never 'survives FDR' or the internal name. Expert wording puts
    the IC's p and the randomisation's p by the IC.
    Mutation it catches: the raw name shown in expert wording, or the
    keep colour on it."""
    from ui import words
    why = ("IC +0.137: it looks like it ranks setups on this replay, but a "
           "meaningless reading held for stretches of time ranked them this "
           "well often enough that this is not told apart from chance. Before "
           "costs, from one replay of past prices.")
    a = {"n": 3200, "fdr_q": 0.1, "withheld": None, "blend_ic": None,
         "randomisation": {"q": 8, "draws": 256, "block_days": 32},
         "components": [{"component": "momentum", "n": 3200, "ic": 0.137,
                         "p": 0.0022, "p_rand": 0.2109, "weight": 0.3,
                         "spread": {"spread": 0.2031, "se": 0.0643},
                         "blend_ic_without": None, "survives_fdr": True,
                         "confirmed": False, "verdict": "UNCONFIRMED",
                         "why": why}]}
    for plain in (True, False):
        monkeypatch.setattr(words, "plain", lambda p=plain: p)
        html = MainWindow._attribution_html(a)
        assert ("<b style='color:#7c8798'>not told apart from chance</b>"
                in html), html
        assert "unconfirmed" not in html.lower() and "survives FDR" not in html
        assert "#98c379" not in html and why in html
        assert ("vs random stretches 0.2109" in html) is (not plain)
        # the randomisation's p is shown raw, beside BH-based grades
        # (domain P3-2)
        assert ("vs random stretches 0.2109, before the correction for "
                "testing four components" in html) is (not plain)
        # in both wordings: what the check cannot see (domain P2-2)
        assert ("The check against random stretches does not cover traits "
                "fixed per instrument, such as volatility.") in html
        assert html.count("fixed per instrument") == 1
    # a run not held to the randomisation does not claim the check ran
    assert "fixed per instrument" not in MainWindow._attribution_html(
        dict(a, randomisation=None))
