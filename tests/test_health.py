"""A silent engine failure is made loud.

The agent ran its engine on a daemon thread: if the loop ended, the HTTP
server kept the process up, launchd saw nothing wrong, and the last snapshot
kept saying all was well. Failed polls were swallowed without a log line, and
nothing reached the owner with the window closed.
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request

import pytest

from sonar import core, server
from sonar.core import Live

NOW = 1_800_000_000.0


@pytest.fixture
def live(tmp_path, monkeypatch):
    monkeypatch.setattr("sonar.paths.user_data_base", lambda: tmp_path)
    return Live()


def _driving(live, since=NOW - 600.0, last_ok=NOW - 5.0):
    live._running, live._driving_since, live.last_poll_ok_at = True, since, last_ok
    return live


# --------------------------------------------------------------------------- #
# Live.health — judged now, not when a snapshot was built
# --------------------------------------------------------------------------- #
def test_a_driving_engine_that_polls_is_healthy(live):
    h = _driving(live).health(NOW)
    assert h["ok"] and h["mode"] == "driving" and h["last_poll_age_s"] == 5


def test_no_successful_poll_for_minutes_is_a_problem(live):
    _driving(live, last_ok=NOW - 300.0)
    live.last_poll_error = "OSError: network down"
    h = live.health(NOW)
    assert not h["ok"]
    (p,) = h["problems"]
    assert p["kind"] == "poll" and "5 min" in p["text"] and "network down" in p["text"]


def test_the_first_poll_gets_a_grace_period(live):
    assert _driving(live, since=NOW - 60.0, last_ok=None).health(NOW)["ok"]
    assert not _driving(live, since=NOW - 600.0, last_ok=None).health(NOW)["ok"]


def test_a_loop_that_ended_without_being_asked_is_a_problem(live):
    live.engine_lock = object()          # it did run
    live._running = False
    h = live.health(NOW)
    assert h["mode"] == "stopped" and h["problems"][0]["kind"] == "loop"
    live.stop()                          # asked to: not a problem
    assert live.health(NOW)["ok"]


def test_no_settled_hour_for_hours_is_a_problem(live):
    _driving(live)
    live.engine.score_started = NOW - 5 * 3600
    live.engine.last_settled_at = NOW - 3 * 3600
    kinds = [p["kind"] for p in live.health(NOW)["problems"]]
    assert kinds == ["settle"]


def test_waiting_or_following_is_not_this_engines_problem(live):
    live.read_only = True
    assert live.health(NOW)["ok"] and live.health(NOW)["mode"] == "waiting"
    live.following = "http://127.0.0.1:1"
    assert live.health(NOW)["mode"] == "following"


def test_a_failed_poll_is_logged_not_swallowed(live, capsys):
    for _ in range(core.POLL_ERROR_LOG_EVERY + 1):
        live._poll_failed(OSError("feed down"))
    err = capsys.readouterr().err
    assert err.count("poll failed") == 2, "first failure, then once per batch"
    assert "feed down" in err and live.last_poll_error == "OSError: feed down"


# --------------------------------------------------------------------------- #
# The watchdog
# --------------------------------------------------------------------------- #
class Thread:
    def __init__(self, alive=True):
        self.alive = alive

    def is_alive(self):
        return self.alive


def _dog(live, thread=None):
    sent, exits, logs = [], [], []
    dog = server.Watchdog(live, thread or Thread(), notify=lambda t, b: sent.append((t, b)),
                          exit_fn=exits.append, log=logs.append)
    return dog, sent, exits


def test_an_ended_engine_thread_exits_the_process_for_launchd(live):
    dog, sent, exits = _dog(live, Thread(alive=False))
    dog.step(NOW)
    assert exits == [3] and sent and "restarting" in sent[0][1]


def test_a_stopping_agent_is_not_restarted(live):
    live.stop()
    dog, sent, exits = _dog(live, Thread(alive=False))
    dog.step(NOW)
    assert exits == [] and sent == []


def test_a_stalled_poll_notifies_once_after_ten_minutes_then_on_recovery(live):
    dog, sent, _ = _dog(live)
    _driving(live, last_ok=NOW - 300.0)
    dog.step(NOW)
    assert sent == [], "not before the problem has lasted"
    dog.step(NOW + server.ALARM_AFTER_S["poll"] + 1)
    assert len(sent) == 1 and sent[0][0] == "SONAR needs attention"
    dog.step(NOW + server.ALARM_AFTER_S["poll"] + 30)
    assert len(sent) == 1, "repeated while still broken"
    live.last_poll_ok_at = NOW + server.ALARM_AFTER_S["poll"] + 40
    dog.step(NOW + server.ALARM_AFTER_S["poll"] + 45)
    assert len(sent) == 2 and sent[1][0] == "SONAR is working again"


def test_no_settled_hour_waits_out_a_wake_from_sleep(live):
    """After a night asleep, 'no hour settled' stays true until the next hour
    settles. That is not a fault and must not wake anyone."""
    dog, sent, _ = _dog(live)
    _driving(live)
    live.engine.score_started = NOW - 10 * 3600
    live.engine.last_settled_at = NOW - 8 * 3600
    dog.step(NOW)
    live.last_poll_ok_at = NOW + 1800
    dog.step(NOW + 1800)
    assert sent == []
    live.last_poll_ok_at = NOW + server.ALARM_AFTER_S["settle"] + 5
    dog.step(NOW + server.ALARM_AFTER_S["settle"] + 10)
    assert len(sent) == 1


def test_the_notification_text_never_enters_the_script(monkeypatch):
    """Passed as arguments: exception text from the network can carry quotes
    or control characters, and a control character made AppleScript refuse."""
    calls = []
    monkeypatch.setattr(server.sys, "platform", "darwin")
    monkeypatch.setattr(server.subprocess, "run",
                        lambda args, **kw: calls.append(args) or type("R", (), {"returncode": 0})())
    server.notify_macos('SONAR "x"', 'a "quoted"\x01 body\nsecond line')
    args = calls[0]
    script = " ".join(args[1:args.index("--")])
    assert "quoted" not in script and "SONAR" not in script
    assert args[args.index("--") + 1:] == ['a "quoted" body second line', 'SONAR "x"']


def test_a_refused_notification_is_logged(monkeypatch, capsys):
    monkeypatch.setattr(server.sys, "platform", "darwin")
    monkeypatch.setattr(server.subprocess, "run", lambda args, **kw: type(
        "R", (), {"returncode": 1, "stderr": "execution error -2741"})())
    server.notify_macos("t", "b")
    assert "notification refused" in capsys.readouterr().err


def test_a_crash_loop_says_stopped_once_an_hour(live):
    """Each restart is a new process; the notice's last time is kept on disk."""
    sent_total = 0
    for minute in range(3):                         # three restarts, a minute apart
        dog, sent, exits = _dog(live, Thread(alive=False))
        dog.step(NOW + 60 * minute)
        sent_total += len(sent)
        assert exits == [3]
    assert sent_total == 1
    dog, sent, _ = _dog(live, Thread(alive=False))
    dog.step(NOW + server.STOPPED_NOTICE_EVERY + 1)
    assert len(sent) == 1


def test_a_second_kind_of_problem_is_still_told(live):
    dog, sent, _ = _dog(live)
    _driving(live, last_ok=NOW - 300.0)
    dog.step(NOW)
    dog.step(NOW + server.ALARM_AFTER_S["poll"] + 1)
    assert len(sent) == 1
    live.engine.score_started = NOW - 5 * 3600
    live.engine.last_settled_at = NOW - 3 * 3600
    t = NOW + server.ALARM_AFTER_S["poll"] + 2
    dog.step(t)
    dog.step(t + server.ALARM_AFTER_S["settle"] + 1)
    assert len(sent) == 2 and "settled" in sent[1][1]


# --------------------------------------------------------------------------- #
# The loop's own bookkeeping, through a real poll
# --------------------------------------------------------------------------- #
def test_a_full_feed_outage_is_a_failed_poll(live, monkeypatch, real_poll, capsys):
    """The fetchers turn network errors into None, so with the network down
    every poll used to look successful: no log, no 503, no alarm."""
    from sonar import feeds
    live._sigma = lambda: 0.0045
    live._rescan = lambda: None
    live._poll = lambda: real_poll(live)
    monkeypatch.setattr(feeds, "_get", lambda *a, **k: None)
    live._poll_once()
    assert live.last_poll_ok_at is None and live._poll_failures == 1
    assert "no fresh BTC price" in live.last_poll_error
    assert "poll failed" in capsys.readouterr().err


def test_a_poll_with_a_price_counts_as_successful(live, monkeypatch, real_poll):
    from sonar import feeds
    live._sigma = lambda: 0.0045
    live._rescan = lambda: None
    live._poll = lambda: real_poll(live)
    monkeypatch.setattr(feeds, "current_market", lambda: None)
    monkeypatch.setattr(feeds, "hourly_candle", lambda symbol="BTCUSDT": feeds.Candle(
        open=100.0, price=101.0, high=101.0, low=100.0,
        open_time=int(NOW) // 3600 * 3600, source="test"))
    live._poll_failures = 4
    live._poll_once()
    assert live.last_poll_ok_at is not None and live._poll_failures == 0


def test_a_raising_poll_is_recorded_and_shown(live):
    live._poll = lambda: (_ for _ in ()).throw(ValueError("bad\npayload"))
    live._poll_once()
    assert live.last_poll_error == "ValueError: bad payload", "one line, for the log"
    assert live.snapshot["status"] == "error"


# --------------------------------------------------------------------------- #
# /api/health
# --------------------------------------------------------------------------- #
class HealthLive:
    lock = threading.Lock()

    def __init__(self, ok):
        self.ok = ok

    def health(self):
        return {"ok": self.ok, "mode": "driving",
                "problems": [] if self.ok else [{"kind": "poll", "text": "x"}]}


@pytest.mark.parametrize("ok,code", [(True, 200), (False, 503)])
def test_the_health_endpoint_answers_with_a_status_code(loopback, monkeypatch, ok, code):
    monkeypatch.setattr(server.Handler, "live", HealthLive(ok))
    srv = server.PaperServer(("127.0.0.1", 0), server.Handler)
    t = threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    t.start()
    try:
        url = "http://%s:%d/api/health" % srv.server_address[:2]
        try:
            with urllib.request.urlopen(url, timeout=5) as r:
                status, body = r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            status, body = e.code, json.loads(e.read())
        assert status == code and body["ok"] is ok
    finally:
        srv.shutdown()
        srv.server_close()
        t.join(5)
