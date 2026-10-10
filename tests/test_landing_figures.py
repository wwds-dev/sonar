"""The landing page's figures, checked against each other rather than against
fixed numbers.

Every figure on the first screen comes from `Portfolio.stats()`, and several of
them are the same quantity reached two ways: account value is cash plus what is
held, and it is also the starting cash plus everything realised and unrealised.
Testing them against each other is how the lattice bug was found (TESTING.md
§1) — neither implementation looked wrong alone. The live book was checked the
same way on 2026-10-10 (28 open, 22 closed): every identity below held to the
cent.
"""

from __future__ import annotations

import random

import pytest

from sonar import calibration
from sonar.portfolio import Portfolio


def _row(symbol: str, price: float, vol: float = 0.02, conf: float = 50.0) -> dict:
    return {"symbol": symbol, "name": symbol, "price": price, "volatility": vol,
            "confidence": conf, "cls": "Equity"}


@pytest.fixture
def book(tmp_path):
    """Three longs, three shorts, two of them already resolved."""
    pf = Portfolio(tmp_path / "portfolio.json")
    for i, (sym, price, side) in enumerate([("AAA", 100.0, "LONG"),
                                            ("BBB", 50.0, "SHORT"),
                                            ("CCC", 20.0, "LONG"),
                                            ("DDD", 80.0, "SHORT"),
                                            ("EEE", 10.0, "LONG"),
                                            ("FFF", 5.0, "SHORT")]):
        pos, why = pf.enter(_row(sym, price, conf=10.0 + i * 15), side, 4, "week")
        assert pos, why
    won = pf.position_for("EEE")
    pf.close(won.id, won.target, "TARGET")
    lost = pf.position_for("FFF")
    pf.close(lost.id, lost.stop, "STOP")
    return pf


#: Prices that move every remaining position, some for and some against.
MARKS = {"AAA": 103.0, "BBB": 48.5, "CCC": 19.2, "DDD": 83.0}


@pytest.mark.parametrize("prices", [{}, MARKS], ids=["at entry", "marked"])
def test_account_value_is_the_start_plus_every_profit_and_loss(book, prices):
    """Two routes to one number: cash plus holdings, and starting cash plus
    realised plus unrealised. A cash leg booked twice, or a short's borrowed
    notional counted as cash, breaks this and nothing else on screen."""
    st = book.stats(prices)
    assert st["equity"] == pytest.approx(
        st["starting_cash"] + st["realised"] + st["unrealised"], abs=0.02)
    assert st["total_pnl"] == pytest.approx(st["realised"] + st["unrealised"], abs=0.02)


def test_invested_is_two_figures_not_one(book):
    """A long spends cash; a short borrows stock. The strip shows both and the
    two must each equal what their own positions committed at entry."""
    st = book.stats(MARKS)
    longs = [p for p in book.open if p.direction == "LONG"]
    shorts = [p for p in book.open if p.direction == "SHORT"]
    assert st["n_long"] == len(longs) == 2 and st["n_short"] == len(shorts) == 2
    assert st["long_cash"] == pytest.approx(sum(p.units * p.entry for p in longs), abs=0.01)
    assert st["short_notional"] == pytest.approx(
        sum(p.units * p.entry for p in shorts), abs=0.01)
    # Only the longs left the cash balance; the shorts never did.
    realised = sum(p.pnl for p in book.closed)
    assert st["cash"] == pytest.approx(
        book.starting_cash + realised - st["long_cash"], abs=0.02)


def test_the_cost_of_every_stop_is_the_distance_to_each_stop(book):
    """"What every stop hitting would cost" is the sum of each position's own
    entry-to-stop distance times its size — and marking the book at exactly
    its stops must lose exactly that much."""
    st = book.stats(MARKS)
    distance = sum(abs(p.entry - p.stop) * p.units for p in book.open)
    assert st["at_risk"] == pytest.approx(distance, abs=0.02)
    at_stops = {p.symbol: p.stop for p in book.open}
    assert book.stats(at_stops)["unrealised"] == pytest.approx(-distance, abs=0.02)


def test_a_long_scaled_to_the_cash_left_still_risks_its_own_distance(tmp_path):
    """When cash runs out, `enter` scales a long down to what is left rather
    than refusing. Its recorded risk must be scaled with it, or the stop-cost
    figure overstates what the account can lose."""
    pf = Portfolio(tmp_path / "portfolio.json")
    pf.cash = 50.0          # far less than a full-sized position costs
    pos, why = pf.enter(_row("AAA", 100.0, vol=0.002), "LONG", 4, "week")
    assert pos, why
    assert pos.units * pos.entry == pytest.approx(50.0)
    assert pos.cash_at_risk == pytest.approx(abs(pos.entry - pos.stop) * pos.units)


def test_the_logged_curve_agrees_with_the_strip(book):
    """The account curve's latest point and the strip's account value are the
    same quantity, written at the same prices."""
    assert book.log_equity(MARKS, force=True)
    assert book.equity_log[-1]["v"] == pytest.approx(book.stats(MARKS)["equity"], abs=0.01)


def test_a_point_is_not_written_while_a_held_price_is_missing(book):
    """Marking a missing price at entry would draw a step that never happened.
    The hourly log waits; only a forced point (an entry or exit) goes ahead."""
    partial = {k: v for k, v in MARKS.items() if k != "DDD"}
    before = len(book.equity_log)
    assert book.log_equity(partial) is False
    assert len(book.equity_log) == before


# --------------------------------------------------------------------------- #
# the grade, at every state it can be in
# --------------------------------------------------------------------------- #
class _Closed:
    """The fields `calibration.report` reads from a closed position."""

    def __init__(self, confidence: float, won: bool, p_profit: float = 0.4):
        self.confidence = confidence
        self.pnl = 10.0 if won else -10.0
        self.p_profit = p_profit


def _closed(n: int, rate: float, scores=(10.0,), seed: int = 0) -> list[_Closed]:
    rng = random.Random(seed)
    wins = set(rng.sample(range(n), round(n * rate)))
    return [_Closed(scores[i % len(scores)], i in wins) for i in range(n)]


FORECAST_WORDS = ("will ", "should", "buy", "sell", "expect", "likely",
                  "going to", "bullish", "bearish")


@pytest.mark.parametrize("n", [calibration.MIN_SAMPLE - 1, calibration.MIN_SAMPLE,
                               calibration.MIN_SAMPLE + 1])
def test_the_grade_speaks_exactly_at_its_threshold(n):
    """Nineteen closed must refuse, twenty must speak. A threshold that moves
    by one, either way, is the easiest regression here to miss."""
    r = calibration.report(_closed(n, 0.4))
    assert r["n_settled"] == n
    assert r["calibrated"] is (n >= calibration.MIN_SAMPLE)
    if n < calibration.MIN_SAMPLE:
        assert r["verdict"].startswith("Not enough resolved positions yet")
        assert r["implied_edge_sigma"] == 0.0


@pytest.mark.parametrize("closed", [
    [],
    _closed(5, 1.0),
    _closed(40, 0.40),
    _closed(40, 0.65),
    _closed(40, 0.15),
    _closed(60, 0.45, scores=(10.0, 50.0, 90.0)),
], ids=["none", "lucky streak", "at the odds", "above", "below", "three bands"])
def test_no_verdict_reads_as_a_forecast(closed):
    """The verdict is printed verbatim on the first screen. Whatever the book
    holds, it describes what happened and never what to do next."""
    verdict = calibration.report(closed)["verdict"].lower()
    for word in FORECAST_WORDS:
        assert word not in verdict, f"{word!r} in {verdict!r}"


def test_a_band_is_never_printed_past_100():
    """The top band is stored as 80–101 so a score of exactly 100 falls inside
    a half-open range. It was printed that way on both the landing page and
    My trades: "scores 80–101"."""
    pytest.importorskip("PySide6")
    from ui.app import _band_top
    tops = [_band_top({"hi": hi}) for _lo, hi in calibration.BUCKETS]
    assert max(tops) == 100
    assert tops[:-1] == [hi for _lo, hi in calibration.BUCKETS[:-1]]
