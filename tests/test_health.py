"""A silent engine failure is made loud.

The agent ran its engine on a daemon thread: if the loop ended, the HTTP
server kept the process up, launchd saw nothing wrong, and the last snapshot
kept saying all was well. Failed polls were swallowed without a log line, and
nothing reached the owner with the window closed.
"""

from __future__ import annotations

import datetime
import io
import json
import re
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request

import pytest

from alarm_fakes import (BUILD, NASTY, TOPIC, Opener, Run, assert_allowlisted, http_error,
                         notifier, timed_out, url_error)
from sonar import alarm, core, server
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
    assert len(sent) == 1 and sent[0][0] == "SONAR (paper) needs attention"
    dog.step(NOW + server.ALARM_AFTER_S["poll"] + 30)
    assert len(sent) == 1, "repeated while still broken"
    live.last_poll_ok_at = NOW + server.ALARM_AFTER_S["poll"] + 40
    dog.step(NOW + server.ALARM_AFTER_S["poll"] + 45)
    assert len(sent) == 2 and sent[1][0] == "SONAR (paper) is working again"


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


# --------------------------------------------------------------------------- #
# Alarm delivery: the watchdog through the notifier (docs/specs/alarm-delivery.md)
# --------------------------------------------------------------------------- #
# None of these touch a real Keychain, the network or osascript: the banner gets
# a fake `run`, ntfy a fake opener (tests/alarm_fakes.py).
_REAL_RUN = subprocess.run
_REAL_CREATE_CONNECTION = socket.create_connection
TS_LINE = re.compile(r"^SONAR (\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[+-]\d\d:\d\d): ")
#: 09:00 on NOW's date, read with time.gmtime as "local" (NOW is 08:00 UTC).
NINE = NOW + 3600


@pytest.fixture
def no_real_channels(monkeypatch):
    """An accidental real Keychain read, banner or connection fails the test."""
    def run(args, *a, **kw):
        if args and str(args[0]).rsplit("/", 1)[-1] in ("osascript", "security"):
            raise AssertionError(f"a test ran the real {args[0]}")
        return _REAL_RUN(args, *a, **kw)

    def connect(*a, **kw):
        raise AssertionError("a test opened a real connection")

    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr(socket, "create_connection", connect)


@pytest.fixture
def notifiers(no_real_channels):
    made = []

    def make(**kw):
        n = notifier(**kw)
        made.append(n)
        return n
    yield make
    for n in made:
        n.close()


class FakeLive:
    """A Live whose every problem text and last error is NASTY: whatever the
    push says, it must not be any of that."""

    def __init__(self, kinds=()):
        self.kinds = list(kinds)
        self._stop = threading.Event()
        self.build = {"version": BUILD}
        self.lock = threading.Lock()

    def health(self, now=None):
        problems = [{"kind": k, "text": NASTY} for k in self.kinds]
        return {"ok": not problems, "mode": "driving", "problems": problems,
                "last_poll_age_s": 1, "last_error": NASTY, "run": None, "build": self.build}


def _watch(live, n, thread=None, exits=None, logs=None, heartbeat=None):
    return server.Watchdog(live, thread or Thread(), notifier=n,
                           exit_fn=(exits if exits is not None else []).append,
                           log=(logs if logs is not None else []).append, heartbeat=heartbeat)


def _beat(path):
    return alarm.Heartbeat(path, localtime=time.gmtime)


def _titles(opener):
    return [r["headers"]["x-title"] for r in opener.requests]


def test_a_timed_out_banner_still_reaches_the_phone(live, notifiers):
    """Measure 1: the banner times out (as 45 of 47 did); the push goes."""
    opener = Opener(200)
    n = notifiers(opener=opener, banner_run=timed_out)
    dog = _watch(live, n)
    _driving(live, last_ok=NOW - 300.0)
    live.last_poll_error = NASTY
    dog.step(NOW)
    dog.step(NOW + server.ALARM_AFTER_S["poll"] + 1)
    assert n.drain(5)
    (req,) = opener.requests
    assert req["url"] == "https://ntfy.sh/" + TOPIC
    assert req["headers"]["x-title"].startswith("SONAR (paper)")
    assert req["headers"]["x-priority"] == "4"
    assert_allowlisted(req["headers"]["x-title"], req["body"])
    notify = server.agent_health(live, n, NOW + server.ALARM_AFTER_S["poll"] + 2)["notify"]
    assert notify["banner"]["failures"] == 1 and notify["banner"]["state"] == "failing"
    assert notify["ntfy"]["failures"] == 0 and notify["ntfy"]["state"] == "ok"


def test_a_failing_push_is_counted_and_the_watchdog_carries_on(notifiers):
    """Measure 2: retried once, counted, a 503 problem, and the next kind
    still alarms."""
    opener = Opener(url_error(), 500)
    n = notifiers(opener=opener)
    live = FakeLive(["poll"])
    dog = _watch(live, n)
    dog.step(NOW)
    dog.step(NOW + 601)
    assert n.drain(5) and len(opener.requests) == 2
    h = server.agent_health(live, n, NOW + 602)
    assert h["notify"]["ntfy"]["state"] == "failing" and h["notify"]["ntfy"]["failures"] == 1
    assert {"kind": "notify", "text": "the ntfy alarm channel is failing (1 failures)"} \
        in h["problems"] and not h["ok"]
    live.kinds = ["poll", "settle"]
    dog.step(NOW + 610)
    dog.step(NOW + 610 + server.ALARM_AFTER_S["settle"])
    assert n.drain(5) and len(opener.requests) == 4
    assert opener.requests[-1]["body"].startswith("no hour settled for at least 1 h;")


def test_a_failing_alarm_channel_is_never_itself_alarmed(notifiers):
    """`notify` is health-only: alarming about the alarm channel through the
    alarm channels would loop and flap."""
    opener, banner = Opener(200), Run()
    n = notifiers(opener=opener, banner_run=banner)
    dog = _watch(FakeLive(["notify"]), n)         # an alarm channel failing, for hours
    for t in (NOW, NOW + 601, NOW + 3 * 3600):
        dog.step(t)
    assert n.drain(5) and opener.requests == [] and banner.calls == []


def test_an_alarm_that_reached_no_channel_is_a_health_problem(notifiers):
    n = notifiers(opener=Opener(500), banner_run=timed_out)
    live = FakeLive(["loop"])
    _watch(live, n).step(NOW)
    assert n.drain(5)
    texts = [p["text"] for p in server.agent_health(live, n, NOW)["problems"]]
    assert "an alarm did not reach the phone" in texts


def _get_health(monkeypatch, live, n):
    """GET /api/health from a real Handler on loopback: (status, body)."""
    monkeypatch.setattr(server.Handler, "live", live)
    monkeypatch.setattr(server.Handler, "notifier", n)
    monkeypatch.setattr(socket, "create_connection", _REAL_CREATE_CONNECTION)
    srv = server.PaperServer(("127.0.0.1", 0), server.Handler)
    t = threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    t.start()
    try:
        url = "http://%s:%d/api/health" % srv.server_address[:2]
        try:
            with urllib.request.urlopen(url, timeout=5) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())
    finally:
        srv.shutdown()
        srv.server_close()
        t.join(5)


def test_an_undelivered_alarm_clears_when_its_kinds_clear(notifiers, loopback, monkeypatch):
    """QA Q9 / CR P1-1: the push failed, then the problem cleared and the
    "working again" push failed too: health is 200 again, not red forever."""
    opener = Opener(500)
    n = notifiers(opener=opener)
    live = FakeLive(["poll"])
    dog = _watch(live, n)
    dog.step(NOW)
    dog.step(NOW + 601)
    assert n.drain(5) and n.undelivered
    live.kinds = []
    dog.step(NOW + 700)
    assert n.drain(5) and not n.undelivered
    n.clock = lambda: NOW + 700 + alarm.FAILING_DECAY_S   # the failure has aged out
    status, body = _get_health(monkeypatch, live, n)
    assert status == 200 and body["ok"] and body["notify"]["ntfy"]["failures"] == 2


def test_an_undelivered_alarm_clears_when_a_later_push_is_delivered(notifiers):
    """QA Q9: a later delivered event clears it while the kind is still open."""
    opener = Opener(500)
    n = notifiers(opener=opener)
    live = FakeLive(["poll"])
    dog = _watch(live, n)
    dog.step(NOW)
    dog.step(NOW + 601)
    assert n.drain(5) and n.undelivered
    opener.answers = [200]
    live.kinds = ["poll", "loop"]
    dog.step(NOW + 610)
    assert n.drain(5) and not n.undelivered
    problems = server.agent_health(live, n, NOW + 610)["problems"]
    assert "an alarm did not reach the phone" not in [p["text"] for p in problems]


def test_not_configured_ntfy_leaves_health_200(no_real_channels, loopback, monkeypatch):
    """QA Q15: no topic and a banner that times out on every alarm: still 200."""
    n = alarm.from_keychain(build=BUILD, read=lambda: (None, "absent"), log=lambda m: None,
                            banner=alarm.BannerChannel(run=timed_out, platform="darwin"))
    try:
        live = FakeLive(["loop"])
        _watch(live, n).step(NOW)
        assert n.drain(5)
        live.kinds = []
        h = server.agent_health(live, n, NOW + 1)
        assert h["ok"] and h["notify"]["ntfy"]["state"] == "not configured"
        assert h["notify"]["banner"]["failures"] == 1
        status, body = _get_health(monkeypatch, live, n)
        assert status == 200 and body["ok"] and body["problems"] == []
    finally:
        n.close()


def test_the_watchdog_takes_its_notifier_by_keyword_only(live):
    """CR P3-1: a callable passed positionally used to become the notifier."""
    with pytest.raises(TypeError):
        server.Watchdog(live, Thread(), lambda t, b: None)


def test_two_kinds_due_at_once_each_carry_their_own_duration(notifiers):
    """Domain P3-B: poll has lasted 15 min and scan 10 min when both fall due."""
    opener = Opener(200)
    n = notifiers(opener=opener)
    live = FakeLive(["poll"])
    dog = _watch(live, n)
    dog.step(NOW)
    live.kinds = ["poll", "scan"]
    dog.step(NOW + 300)
    dog.step(NOW + 900)
    assert n.drain(5)
    (req,) = opener.requests
    assert req["body"].startswith("no successful price poll for at least 15 min; "
                                  "the board scan stalled for at least 10 min; ")
    assert_allowlisted(req["headers"]["x-title"], req["body"])


EVERY_PUSH = [*server.ALARM_AFTER_S, "notify", "stopped", "recovery", "heartbeat", "test",
              "guard_halted"]


@pytest.mark.parametrize("kind", EVERY_PUSH)
def test_every_push_says_only_what_the_allowlist_allows(kind, notifiers, tmp_path):
    """Domain P1-1/P2-1: every problem text and error is a symbol, a price, a
    path, a URL and exception text; none of it may reach the push."""
    opener = Opener(200)
    n = notifiers(opener=opener)
    live = FakeLive()
    if kind == "test":
        assert alarm.test_alarm([], read=lambda: (TOPIC, "ok"), opener=opener,
                                banner=alarm.BannerChannel(run=Run(), platform="darwin"),
                                build=BUILD, out=io.StringIO()) == 0
    elif kind == "stopped":
        _watch(live, n, Thread(alive=False)).step(NOW)
    elif kind == "heartbeat":
        live.kinds = [*server.ALARM_AFTER_S, "notify", "guard_halted"]
        _watch(live, n, heartbeat=_beat(tmp_path / "hb.json")).step(NINE)
    elif kind == "notify":
        live.kinds = ["notify"]
        dog = _watch(live, n)
        dog.step(NOW)
        dog.step(NOW + 3 * 3600)
        assert n.drain(5) and opener.requests == [], "health-only"
        title, body, _ = alarm.render(alarm.Event("notify"), BUILD, n.states())
        assert_allowlisted(title, body)
        return
    else:
        live.kinds = ["poll" if kind == "recovery" else kind]
        dog = _watch(live, n)
        dog.step(NOW)
        dog.step(NOW + server.ALARM_AFTER_S.get(live.kinds[0], 600.0) + 1)
        if kind == "recovery":
            live.kinds = []
            dog.step(NOW + 3600)
    assert n.drain(5) and opener.requests
    for req in opener.requests:
        assert_allowlisted(req["headers"]["x-title"], req["body"])
    if kind == "heartbeat":
        assert "open problems: loop, poll, scan, settle, notify, other;" in req["body"]
    if kind == "recovery":
        assert _titles(opener)[-1] == "SONAR (paper) working again"


def test_the_heartbeat_goes_once_a_day_even_in_a_crash_loop(notifiers, tmp_path):
    """09:00 local, with the open kinds; persisted when queued, so a restart
    the same day (here after a failed push) does not send another."""
    path = tmp_path / "alarm.json"
    first = Opener(500)
    live = FakeLive(["poll"])
    dog = _watch(live, notifiers(opener=first), heartbeat=_beat(path))
    dog.step(NINE - 60)
    assert dog.notifier.drain(5) and first.requests == []
    dog.step(NINE)
    dog.step(NINE + 60)
    assert dog.notifier.drain(5)
    beats = [r for r in first.requests if r["headers"]["x-title"] == "SONAR (paper) alive"]
    assert len(beats) == 2, "one heartbeat, failed, and its one retry"
    req = beats[0]
    assert "open problems: poll;" in req["body"] and req["headers"]["x-priority"] == "2"
    second = Opener(200)
    n2 = notifiers(opener=second)
    dog2 = _watch(FakeLive(), n2, heartbeat=_beat(path))     # a restart
    dog2.step(NINE + 120)
    assert n2.drain(5) and second.requests == []
    dog2.step(NINE + 86400)
    assert n2.drain(5) and _titles(second) == ["SONAR (paper) alive"]
    assert "open problems: none;" in second.requests[0]["body"]


def test_the_stopped_notice_keeps_the_heartbeat_day_and_the_reverse(live, notifiers):
    path = server._alarm_file()
    _beat(path).mark(NINE)
    assert server._stopped_notice_due(NINE + 5)
    server._stopped_notice_sent(NINE + 5)
    assert json.loads(path.read_text()) == {
        "heartbeat_day": "2027-01-15", "heartbeat_at": NINE, "stopped_at": NINE + 5}
    _beat(path).mark(NINE + 86400)
    assert json.loads(path.read_text())["stopped_at"] == NINE + 5


def test_a_hung_banner_never_delays_the_watchdog_or_the_push(notifiers):
    release = threading.Event()
    opener = Opener(200)
    n = notifiers(opener=opener, banner_run=Run(block=release))
    live = FakeLive(["poll"])
    banner = n._lanes["banner"].channel._run
    dog = _watch(live, n)
    dog.step(NOW)
    try:
        # The step finishes and the push is sent while the banner is still
        # stuck inside osascript: no wall-clock bound, only the order.
        dog.step(NOW + 601)
        assert opener.called.wait(10) and banner.called.wait(10)
        assert not banner.returned.is_set(), "the banner was still hung throughout"
    finally:
        release.set()
    assert n.drain(5) and len(opener.requests) == 1


def test_a_hung_push_delays_the_exit_by_at_most_the_flush(notifiers, monkeypatch):
    monkeypatch.setattr(server, "STOP_FLUSH_S", 0.5)
    release = threading.Event()
    opener = Opener(200, block=release)
    exits = []
    dog = _watch(FakeLive(), notifiers(opener=opener), Thread(alive=False), exits=exits)
    try:
        t0 = time.monotonic()
        dog.step(NOW)
        took = time.monotonic() - t0
    finally:
        release.set()
    assert exits == [3] and took < server.STOP_FLUSH_S + 1 and opener.called.is_set()


class _SlowOpener(Opener):
    """Answers 200 after a short delay; ``done`` is set once it has answered."""

    def __init__(self):
        super().__init__(200)
        self.done = threading.Event()

    def open(self, req, timeout=None):
        r = super().open(req, timeout)
        time.sleep(0.2)
        self.done.set()
        return r


def test_the_exit_path_waits_for_the_stopped_push(notifiers):
    """QA N11: exit 3 comes only after the "stopped" push has been answered."""
    opener = _SlowOpener()
    seen = []

    def exit_fn(code):
        seen.append((code, opener.done.is_set()))
    dog = server.Watchdog(FakeLive(), Thread(alive=False), notifier=notifiers(opener=opener),
                          exit_fn=exit_fn, log=[].append)
    dog.step(NOW)
    assert seen == [(3, True)]
    assert json.loads(server._alarm_file().read_text())["stopped_at"] == NOW


def test_a_stopped_notice_that_reached_nobody_is_tried_again_next_restart(notifiers):
    """CR P2-b: network down at the first exit, so the second exit sends; a
    crash loop still gets at most one delivered notice an hour."""
    down = Opener(url_error())
    n1 = notifiers(opener=down, banner_run=timed_out)
    exits = []
    _watch(FakeLive(), n1, Thread(alive=False), exits=exits).step(NOW)
    assert exits == [3] and len(down.requests) == 1, "urgent: one attempt"
    path = server._alarm_file()
    assert not path.exists() or "stopped_at" not in json.loads(path.read_text())
    up = Opener(200)
    for minute in (1, 2, 3):
        _watch(FakeLive(), notifiers(opener=up), Thread(alive=False)).step(NOW + 60 * minute)
    assert _titles(up) == ["SONAR (paper) stopped"]
    assert json.loads(server._alarm_file().read_text())["stopped_at"] == NOW + 60


def test_a_stopped_notice_seen_only_on_the_banner_is_tried_again(notifiers):
    """Round 3, CR P3-1: the banner posted it but the phone did not get it,
    so it does not count, and the next restart tries again."""
    down = Opener(url_error())
    banner = Run()
    _watch(FakeLive(), notifiers(opener=down, banner_run=banner), Thread(alive=False)).step(NOW)
    assert banner.calls and len(down.requests) == 1
    path = server._alarm_file()
    assert not path.exists() or "stopped_at" not in json.loads(path.read_text())
    up = Opener(200)
    _watch(FakeLive(), notifiers(opener=up), Thread(alive=False)).step(NOW + 60)
    assert _titles(up) == ["SONAR (paper) stopped"]
    assert json.loads(path.read_text())["stopped_at"] == NOW + 60


def test_with_no_topic_a_banner_stopped_notice_counts(no_real_channels):
    n = alarm.Notifier([alarm.BannerChannel(run=Run(), platform="darwin"),
                        alarm.NtfyChannel(None, Opener(200), "absent")], log=lambda m: None)
    try:
        _watch(FakeLive(), n, Thread(alive=False)).step(NOW)
        assert json.loads(server._alarm_file().read_text())["stopped_at"] == NOW
    finally:
        n.close()


def test_the_process_exits_even_if_logging_fails(notifiers):
    """CR P3-c: exit_fn(3) runs whatever raises on the way out."""
    def boom(msg):
        raise RuntimeError("log disk full")
    exits = []
    dog = server.Watchdog(FakeLive(), Thread(alive=False), notifier=notifiers(),
                          exit_fn=exits.append, log=boom)
    with pytest.raises(RuntimeError):
        dog.step(NOW)
    assert exits == [3]


def test_an_undelivered_alarm_clears_when_its_own_kinds_clear(notifiers):
    """CR P2-a: the failed alarm was about poll. Poll clears while scan stays
    open: the alarm is moot, even though not every kind has cleared."""
    n = notifiers(opener=Opener(500))
    live = FakeLive(["poll"])
    dog = _watch(live, n)
    dog.step(NOW)
    dog.step(NOW + 601)
    assert n.drain(5) and n.undelivered
    live.kinds = ["poll", "scan"]
    dog.step(NOW + 610)
    assert n.undelivered, "poll is still open"
    live.kinds = ["scan"]
    dog.step(NOW + 620)
    assert not n.undelivered
    texts = [p["text"] for p in server.agent_health(live, n, NOW + 620)["problems"]]
    assert "an alarm did not reach the phone" not in texts
    assert "the ntfy alarm channel is failing (1 failures)" in texts, "decision (b): still failing"


class _HangRetry(Opener):
    """Every answer is 500; the second request (the retry) waits for ``release``."""

    def __init__(self):
        super().__init__(500)
        self.release, self.retrying = threading.Event(), threading.Event()

    def open(self, req, timeout=None):
        if len(self.requests) == 1:
            self.retrying.set()
            self.release.wait(30)
        return super().open(req, timeout)


def test_a_late_retry_failure_does_not_mark_an_alarm_whose_kinds_cleared(notifiers):
    """CR P2-a: the retry fails after poll has cleared; nothing is marked."""
    opener = _HangRetry()
    n = notifiers(opener=opener)
    n.set_open_kinds({"poll", "scan"})
    n.send(alarm.Event("poll", (("poll", 700.0),)))
    try:
        assert opener.retrying.wait(10)
        n.set_open_kinds({"scan"})                # poll cleared while the retry was out
    finally:
        opener.release.set()
    assert n.drain(5) and len(opener.requests) == 2
    assert not n.undelivered
    n.send(alarm.Event("scan", (("scan", 700.0),)))   # an alarm on a kind still open
    assert n.drain(5) and n.undelivered


def test_a_crash_loop_pushes_stopped_once_an_hour(notifiers):
    opener = Opener(200)
    for minute in range(3):
        n = notifiers(opener=opener)
        exits = []
        _watch(FakeLive(), n, Thread(alive=False), exits=exits).step(NOW + 60 * minute)
        assert exits == [3]
    assert _titles(opener) == ["SONAR (paper) stopped"]
    assert opener.requests[0]["headers"]["x-priority"] == "4"


def test_the_topic_never_appears_in_any_output(notifiers, loopback, monkeypatch, capsys,
                                               tmp_path):
    """Measure 4: alarm, recovery, stopped, heartbeat and the test alarm,
    through failures whose exceptions carry the full URL."""
    logs = []
    opener = Opener(url_error(), http_error(404))
    n = notifiers(opener=opener, log=logs.append)
    live = FakeLive(["poll"])
    dog = server.Watchdog(live, Thread(), notifier=n, exit_fn=[].append,
                          heartbeat=_beat(tmp_path / "hb.json"))   # default log: stderr
    dog.step(NOW)
    dog.step(NOW + 601)
    live.kinds = []
    dog.step(NOW + 700)
    dog.step(NINE)
    server.Watchdog(live, Thread(alive=False), notifier=n, exit_fn=[].append).step(NINE + 1)
    n.say(f"stray {TOPIC}")
    assert alarm.test_alarm([], read=lambda: (TOPIC, "ok"), opener=opener,
                            banner=alarm.BannerChannel(run=timed_out, platform="darwin"),
                            build=BUILD, retry_after_s=0.0) == 1
    assert n.drain(5) and len(opener.requests) >= 8
    health = server.agent_health(live, n, NINE + 2)

    monkeypatch.setattr(server.Handler, "live", live)
    monkeypatch.setattr(server.Handler, "notifier", n)
    # Every alarm is sent; this test's own server on 127.0.0.1 may be reached.
    monkeypatch.setattr(socket, "create_connection", _REAL_CREATE_CONNECTION)
    srv = server.PaperServer(("127.0.0.1", 0), server.Handler)
    t = threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    t.start()
    try:
        url = "http://%s:%d/api/health" % srv.server_address[:2]
        try:
            with urllib.request.urlopen(url, timeout=5) as r:
                status, body = r.status, r.read().decode()
        except urllib.error.HTTPError as e:
            status, body = e.code, e.read().decode()
    finally:
        srv.shutdown()
        srv.server_close()
        t.join(5)
    assert status == 503 and json.loads(body)["notify"]["ntfy"]["state"] == "failing"

    out = capsys.readouterr()
    for text in (out.out, out.err, "\n".join(logs), json.dumps(health), body,
                 repr(n._lanes["ntfy"].channel)):
        assert TOPIC not in text
    assert "[topic]" in "\n".join(logs)


def test_every_watchdog_and_notifier_line_is_timestamped(notifiers, capsys, monkeypatch):
    """Measure 5: the default logs, from stderr, each start with a local ISO time."""
    n = alarm.from_keychain(build=BUILD, read=lambda: (TOPIC, "ok"), opener=Opener(500),
                            banner=alarm.BannerChannel(run=timed_out, platform="darwin"))
    try:
        n._lanes["ntfy"].retry_after_s = 0.0
        live = FakeLive(["poll"])
        dog = server.Watchdog(live, Thread(), notifier=n, exit_fn=[].append)
        dog.step(NOW)
        dog.step(NOW + 601)
        assert n.drain(5)
        live.kinds = []
        dog.step(NOW + 700)
        assert n.drain(5)
        server.Watchdog(live, Thread(alive=False), notifier=n, exit_fn=[].append).step(NOW)
        monkeypatch.setattr(server, "WATCH_EVERY", 0.001)
        stop = threading.Event()

        def boom(now=None):
            stop.set()
            raise ValueError("bad\nstep")
        dog.step = boom
        dog.run(stop)
    finally:
        n.close()
    lines = [ln for ln in capsys.readouterr().err.splitlines() if ln]
    assert len(lines) >= 8
    for line in lines:
        m = TS_LINE.match(line)
        assert m, line
        datetime.datetime.fromisoformat(m.group(1))
    joined = "\n".join(lines)
    for said in ("push alarms: ntfy configured", "needs attention: " + NASTY,
                 "ntfy alarm not delivered (HTTP 500)", "banner alarm not delivered",
                 "working again", "the engine thread ended", "watchdog step failed"):
        assert said in joined, said


def test_the_old_notify_hook_still_sees_the_local_text(live):
    """The `notify=` adapter keeps today's banner text for older callers."""
    sent = []
    dog = server.Watchdog(live, Thread(), notify=lambda t, b: sent.append((t, b)),
                          exit_fn=[].append, log=[].append)
    assert server.agent_health(live, dog.notifier, NOW) == live.health(NOW)
    _driving(live, last_ok=NOW - 300.0)
    dog.step(NOW)
    dog.step(NOW + 601)
    assert sent and sent[0][0] == "SONAR (paper) needs attention" and "price poll" in sent[0][1]
