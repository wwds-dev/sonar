"""One engine poll, with the feeds stubbed: what reaches the screen."""

from __future__ import annotations

from sonar import feeds
from sonar.core import Live

HOUR = 1_700_000_000 // 3600 * 3600


def _candle(open_time: int, price: float) -> feeds.Candle:
    return feeds.Candle(open=100.0, price=price, high=price, low=100.0,
                        open_time=open_time, source="Coinbase BTC-USD")


def test_a_candle_from_an_earlier_hour_never_reaches_the_screen(tmp_path, monkeypatch,
                                                                 real_poll):
    """The engine ignores a past hour's candle (a lagging fallback, a clock a
    few seconds behind the exchange); the terminal showed its price beside the
    current hour's signal and put it on the spark line anyway."""
    monkeypatch.setattr("sonar.paths.user_data_base", lambda: tmp_path)
    live = Live()
    live._sigma = lambda: 0.0045
    live._rescan = lambda: None
    monkeypatch.setattr(feeds, "current_market", lambda: None)
    monkeypatch.setattr(feeds, "hour_close", lambda t: None)
    monkeypatch.setattr(feeds, "hourly_candle", lambda symbol="BTCUSDT": _candle(HOUR, 101.0))
    real_poll(live)
    assert live.engine.current_hour == HOUR
    assert [p["p"] for p in live.spark] == [101.0]
    monkeypatch.setattr(feeds, "hourly_candle",
                        lambda symbol="BTCUSDT": _candle(HOUR - 3600, 55.0))
    real_poll(live)
    assert [p["p"] for p in live.spark] == [101.0], "an old price reached the spark line"
    assert live.snapshot.get("candle") is None, "an old candle reached the snapshot"
    assert live.engine.current_hour == HOUR


def test_another_hours_market_is_not_priced_on_screen(tmp_path, monkeypatch, real_poll):
    """The series fallback can return the next hour's market; the engine
    refuses it, and the snapshot must not show it beside this hour's candle."""
    monkeypatch.setattr("sonar.paths.user_data_base", lambda: tmp_path)
    live = Live()
    live._sigma = lambda: 0.0045
    live._rescan = lambda: None
    monkeypatch.setattr(feeds, "hour_close", lambda t: None)
    monkeypatch.setattr(feeds, "hourly_candle", lambda symbol="BTCUSDT": _candle(HOUR, 101.0))
    nxt = feeds.MarketBook(slug="next", title="next hour", implied_up=0.6, best_bid=0.59,
                           best_ask=0.61, end_time=HOUR + 7200, volume=0.0, up_token="")
    monkeypatch.setattr(feeds, "current_market", lambda: nxt)
    real_poll(live)
    assert live.snapshot.get("market") is None


# --------------------------------------------------------------------------- #
# The slow work runs beside the poll, never inside it (audit T1-7)
# --------------------------------------------------------------------------- #
def _bare(tmp_path, monkeypatch):
    monkeypatch.setattr("sonar.paths.user_data_base", lambda: tmp_path)
    live = Live()
    monkeypatch.setattr(feeds, "current_market", lambda: None)
    monkeypatch.setattr(feeds, "hour_close", lambda t: None)
    monkeypatch.setattr(feeds, "hourly_candle", lambda symbol="BTCUSDT": _candle(HOUR, 101.0))
    return live


def test_a_poll_never_runs_the_scan_or_the_sigma_fetch(tmp_path, monkeypatch, real_poll):
    """Inline, a scan of 26+ charts and 24 feeds stalled the price poll; the
    engine then ticked a stale candle against a fresh market."""
    live = _bare(tmp_path, monkeypatch)
    live._scan_at = live._vol_at = 0.0           # both long overdue
    live._rescan = lambda: (_ for _ in ()).throw(AssertionError("scan inside the poll"))
    live._sigma = lambda: (_ for _ in ()).throw(AssertionError("σ fetch inside the poll"))
    real_poll(live)
    assert live.engine.current_hour == HOUR


def test_the_background_step_does_what_is_due(tmp_path, monkeypatch, real_background_step):
    from sonar import horizon
    live = _bare(tmp_path, monkeypatch)
    calls = []
    live._rescan_once = lambda: calls.append("scan")
    live._sigma = lambda: calls.append("sigma") or 0.006
    live.horizon = next(h for h in horizon.HORIZONS.values() if h.macro)
    live.macro.get = lambda: calls.append("macro") or "snapshot"
    live._scan_at = live._vol_at = 0.0
    real_background_step(live, now=10_000.0)
    assert calls == ["sigma", "macro", "scan"] and live.sigma == 0.006
    assert live._macro_snap == "snapshot"
    calls.clear()
    live._scan_at = live._vol_at = 10_000.0
    real_background_step(live, now=10_001.0)
    assert calls == ["macro"], "nothing else was due"


def test_the_snapshot_never_fetches_macro_under_the_lock(tmp_path, monkeypatch, real_poll):
    """_build runs under self.lock, which the window takes every second; a FRED
    fetch there froze it for as long as FRED took."""
    from sonar import horizon
    live = _bare(tmp_path, monkeypatch)
    live.horizon = next(h for h in horizon.HORIZONS.values() if h.macro)
    live._sigma = lambda: 0.0045
    live.macro.get = lambda: (_ for _ in ()).throw(AssertionError("fetched under the lock"))

    class Snap:
        def as_dict(self):
            return {"regime": "cached"}
    live._macro_snap = Snap()
    monkeypatch.setattr(feeds, "current_market", lambda: feeds.MarketBook(
        slug="s", title="t", implied_up=0.5, best_bid=0.49, best_ask=0.51,
        end_time=HOUR + 3600, volume=0.0, up_token=""))
    real_poll(live)
    assert live.snapshot.get("macro") == {"regime": "cached"}


def test_a_slow_scan_does_not_slow_the_poll(tmp_path, monkeypatch):
    """The loop end to end: a background step that takes a second while the
    poll keeps its cadence."""
    import threading
    import time as _time
    from sonar import core
    monkeypatch.setattr("sonar.paths.user_data_base", lambda: tmp_path)
    monkeypatch.setattr(core, "PRICE_EVERY", 0.02)
    live = Live()
    polls = []
    started = threading.Event()

    def slow_step(now=None):
        started.set()
        _time.sleep(1.0)

    live._poll = lambda: polls.append(_time.monotonic())
    live._background_step = slow_step
    t = threading.Thread(target=live.run, args=("app",), daemon=True)
    t.start()
    try:
        assert started.wait(5)
        _time.sleep(0.4)
        assert len(polls) >= 5, f"only {len(polls)} polls while the scan ran"
    finally:
        live.stop()
        t.join(5)
    assert not t.is_alive()


def test_a_scan_finishing_after_quit_does_not_mark_the_book(tmp_path, monkeypatch):
    live = _bare(tmp_path, monkeypatch)
    marked = []
    live._mark_book = lambda *a, **k: marked.append(1)
    live.news.headlines = lambda: []
    live.events.payload = lambda: {}
    live.institutions.payload = lambda: None
    live.asset_scanner.payload = lambda *a, **k: (live.stop(), {"assets": []})[1]
    live._rescan()
    assert marked == [], "the lock may already belong to the next engine"


def test_the_background_thread_outlives_a_raising_step(tmp_path, monkeypatch, capsys):
    import threading
    import time as _time
    from sonar import core
    monkeypatch.setattr("sonar.paths.user_data_base", lambda: tmp_path)
    monkeypatch.setattr(core, "BACKGROUND_TICK", 0.01)
    live = Live()
    steps = []
    live._background_step = lambda now=None: (steps.append(1),
                                              (_ for _ in ()).throw(OSError("feed down")))
    t = threading.Thread(target=live._background, daemon=True)
    t.start()
    _time.sleep(0.2)
    live.stop()
    t.join(2)
    assert len(steps) > 3 and "background step failed" in capsys.readouterr().err


def test_a_dead_or_stale_background_scan_is_a_health_problem(tmp_path, monkeypatch):
    monkeypatch.setattr("sonar.paths.user_data_base", lambda: tmp_path)
    live = Live()
    now = 2_000_000_000.0
    live._running, live._driving_since, live.last_poll_ok_at = True, now - 600, now - 2

    class Dead:
        def is_alive(self):
            return False
    live._background_thread = Dead()
    assert [p["kind"] for p in live.health(now)["problems"]] == ["scan"]
    live._background_thread = None
    live._scan_at = now - 3600
    assert "not been rescanned" in live.health(now)["problems"][0]["text"]
    live._scan_at = now - 30
    assert live.health(now)["ok"]


def test_a_scan_queued_behind_another_does_not_run_again(tmp_path, monkeypatch):
    monkeypatch.setattr("sonar.paths.user_data_base", lambda: tmp_path)
    live = Live()
    ran = []
    live._rescan_once = lambda: ran.append(1)
    live._scan_at = 10**12                  # a scan just finished (far "future" stamp)
    live._rescan_if_due()
    assert ran == []
    live._scan_at = 0.0
    live._rescan_if_due()
    assert ran == [1]


def test_the_lock_is_released_only_after_the_background_scan_finishes(tmp_path, monkeypatch):
    import threading
    import time as _time
    from sonar import core
    monkeypatch.setattr("sonar.paths.user_data_base", lambda: tmp_path)
    monkeypatch.setattr(core, "PRICE_EVERY", 0.01)
    live = Live()
    order = []
    in_step = threading.Event()

    def step(now=None):
        in_step.set()
        _time.sleep(0.3)
        order.append(("step done", live.engine_lock.held))

    live._background_step = step
    real_release = None
    t = threading.Thread(target=live.run, args=("app",), daemon=True)
    t.start()
    assert in_step.wait(5)
    real_release = live.engine_lock.release
    live.engine_lock.release = lambda: (order.append(("released", None)), real_release())[1]
    live.stop()
    t.join(5)
    assert order and order[0] == ("step done", True) and order[-1][0] == "released"
