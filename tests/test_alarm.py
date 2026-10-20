"""Alarms that reach the owner away from this Mac (docs/specs/alarm-delivery.md).

The agent's only alarm was an ``osascript`` banner, and 45 of its 47 attempts
timed out: nobody was told about 12-24 min poll outages. These pin down the
parts of ``sonar/alarm.py`` that do not need the watchdog: what a push may say,
the channels, the Keychain read, the sender threads, the heartbeat schedule and
``--test-alarm``. The watchdog's use of them is in tests/test_health.py.

No test here touches a real Keychain, the network or ``osascript``.
"""

from __future__ import annotations

import datetime
import io
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

import pytest

from alarm_fakes import (BUILD, NASTY, TOPIC, Opener, Run, assert_allowlisted, http_error,
                         notifier, timed_out, url_error)
from sonar import alarm, server

ROOT = Path(__file__).resolve().parent.parent
_REAL_RUN = subprocess.run
TS_LINE = re.compile(r"^SONAR (\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[+-]\d\d:\d\d): ")


@pytest.fixture(autouse=True)
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
def notifiers():
    made = []

    def make(**kw):
        n = notifier(**kw)
        made.append(n)
        return n
    yield make
    for n in made:
        n.close()


# --------------------------------------------------------------------------- #
# What a push may say (domain P1-1, P2-1, P3-A, P3-B)
# --------------------------------------------------------------------------- #
#: Every kind ``core.Live.health`` can emit. test_core_kinds_are_in_sync keeps
#: this honest against core.py's source.
CORE_KINDS = {"loop", "poll", "scan", "settle"}

STATES = {"banner": {"state": "failing"}, "ntfy": {"state": "ok"}}


def test_core_kinds_are_in_sync_and_every_kind_has_a_phrase():
    source = (ROOT / "sonar" / "core.py").read_text()
    assert set(re.findall(r'"kind": "(\w+)"', source)) == CORE_KINDS
    assert CORE_KINDS <= set(alarm.PHRASES)
    assert set(server.ALARM_AFTER_S) <= set(alarm.PHRASES)
    assert "notify" in alarm.PHRASES


def test_the_fixed_phrases_carry_nothing_but_words():
    for text, unit in alarm.PHRASES.values():
        assert re.fullmatch(r"[a-z ]+", text) and unit in (None, "min", "h")
    for suffix, text, priority in alarm.NOTICES.values():
        assert re.fullmatch(r"[a-z ]+", suffix)
        assert text is None or re.fullmatch(r"[a-z ,]+", text)
        assert priority in (alarm.PRIORITY_ALARM, alarm.PRIORITY_INFO)


@pytest.mark.parametrize("event,title,priority", [
    (alarm.Event("poll", (("poll", 725.0),)), "SONAR (paper) needs attention", 4),
    (alarm.Event("loop", (("loop", 0.0),)), "SONAR (paper) needs attention", 4),
    (alarm.Event("stopped", urgent=True), "SONAR (paper) stopped", 4),
    (alarm.Event("recovery"), "SONAR (paper) working again", 2),
    (alarm.Event("heartbeat", (("poll", None),)), "SONAR (paper) alive", 2),
    (alarm.Event("test"), "SONAR (paper) test alarm", 2),
])
def test_titles_and_priorities(event, title, priority):
    """Owner decision 7: 4 for alarms and "stopped", 2 for the rest."""
    t, body, p = alarm.render(event, BUILD, STATES)
    assert (t, p) == (title, priority)
    assert_allowlisted(t, body)


def test_an_alarm_says_what_is_wrong_and_for_how_long_in_whole_units():
    _, body, _ = alarm.render(alarm.Event("poll", (("poll", 725.9),)), BUILD, STATES)
    assert body == ("no successful price poll for at least 12 min; build v2.340; "
                    "channels: banner failing, ntfy ok")
    _, body, _ = alarm.render(alarm.Event("settle", (("settle", 2 * 3600 + 3599),)),
                              BUILD, STATES)
    assert body.startswith("no hour settled for at least 2 h;")


def test_two_kinds_in_one_push_each_keep_their_own_duration():
    """Domain P3-B: one duration per kind, never one beside the wrong kind."""
    event = alarm.Event("poll", (("poll", 900.0), ("scan", 600.0)))
    _, body, _ = alarm.render(event, BUILD, STATES)
    assert body.startswith("no successful price poll for at least 15 min; "
                           "the board scan stalled for at least 10 min; ")


def test_an_unknown_kind_is_other_problem_and_a_bad_build_is_unknown():
    _, body, _ = alarm.render(alarm.Event("guard halted, $187 AAPL"), "v2.???", None)
    assert body == "other problem; build unknown; channels: banner unknown, ntfy unknown"
    _, body, _ = alarm.render(alarm.Event("poll", (("poll", float("nan")),)),
                              "v2.340 /Users/x", {"ntfy": {"state": NASTY}})
    assert_allowlisted("SONAR (paper) needs attention", body)
    assert "build unknown" in body and "ntfy unknown" in body


def test_the_heartbeat_lists_open_kinds_in_the_closed_vocabulary():
    event = alarm.Event("heartbeat", (("poll", None), ("settle", None), ("$AAPL", None),
                                      ("notify", None), ("x/y", None)))
    _, body, _ = alarm.render(event, BUILD, STATES)
    assert body == ("SONAR (paper) alive, build v2.340; open problems: poll, settle, "
                    "other, notify; channels: banner failing, ntfy ok")
    _, body, _ = alarm.render(alarm.Event("heartbeat"), BUILD, STATES)
    assert "open problems: none;" in body
    assert_allowlisted("SONAR (paper) alive", body)


def test_an_event_has_no_field_for_free_text():
    assert set(alarm.Event.__dataclass_fields__) == {"kind", "open_kinds", "urgent"}


# --------------------------------------------------------------------------- #
# The Keychain topic
# --------------------------------------------------------------------------- #
def test_the_topic_is_read_with_security_from_the_keychain():
    run = Run(stdout=TOPIC + "\n")
    assert alarm.read_topic(run=run) == (TOPIC, "ok")
    assert run.calls == [["/usr/bin/security", "find-generic-password", "-s",
                          "com.netrunner3000.sonar.ntfy", "-a", "topic", "-w"]]


@pytest.mark.parametrize("run,reason", [
    (Run(rc=44, stderr="The specified item could not be found in the keychain."), "absent"),
    (Run(rc=51, stderr=f"denied {TOPIC}"), "keychain error"),
    (Run(stdout="short\n"), "invalid"),
    (Run(stdout="a" * 65), "invalid"),
    (Run(stdout="has spaces in it but is long enough"), "invalid"),
    (Run(raises=subprocess.TimeoutExpired("security", 5)), "timeout"),
    (Run(raises=OSError("no such file /usr/bin/security")), "keychain error"),
])
def test_a_missing_or_bad_topic_means_not_configured(run, reason):
    assert alarm.read_topic(run=run) == (None, reason)


# --------------------------------------------------------------------------- #
# The ntfy channel
# --------------------------------------------------------------------------- #
def test_a_push_is_one_post_to_the_topic():
    opener = Opener(200)
    ch = alarm.NtfyChannel(TOPIC, opener)
    assert ch.send("SONAR (paper) alive", "body text", 2)
    (req,) = opener.requests
    assert req["url"] == "https://ntfy.sh/" + TOPIC and req["method"] == "POST"
    assert req["headers"]["x-title"] == "SONAR (paper) alive"
    assert req["headers"]["x-priority"] == "2"
    assert req["headers"]["content-type"] == "text/plain"
    assert req["body"] == "body text" and req["timeout"] == alarm.SEND_TIMEOUT_S


@pytest.mark.parametrize("answer,why", [
    (500, "HTTP 500"), (302, "HTTP 302"), (http_error(404), "HTTP 404"),
    (http_error(429), "HTTP 429"), (url_error(), "URLError"),
    (TimeoutError("timed out"), "timeout"), (ValueError(TOPIC), "ValueError"),
])
def test_a_failed_push_says_why_without_the_topic(answer, why):
    ch = alarm.NtfyChannel(TOPIC, Opener(answer))
    assert ch.send("t", "b", 4) is False
    assert ch.why == why and TOPIC not in ch.why and TOPIC not in repr(ch)


def test_any_2xx_is_delivered():
    assert alarm.NtfyChannel(TOPIC, Opener(204)).send("t", "b", 2)


def test_without_a_topic_nothing_is_sent():
    opener = Opener(200)
    ch = alarm.NtfyChannel(None, opener, "absent")
    assert not ch.configured and ch.send("t", "b", 2) is False
    assert opener.requests == [] and ch.why == "not configured (absent)"


def test_the_real_opener_ignores_proxies_and_redirects(monkeypatch):
    monkeypatch.setenv("https_proxy", "http://proxy.example:3128")
    handlers = alarm._ntfy_opener().handlers
    assert not [h for h in handlers if getattr(h, "proxies", None)]
    assert urllib.request.build_opener().handlers[0].proxies, "the default would use it"
    redirects = [h for h in handlers if isinstance(h, urllib.request.HTTPRedirectHandler)]
    assert redirects and all(isinstance(h, alarm._NoRedirect) for h in redirects)
    assert redirects[0].redirect_request(None, None, 302, "Found", {}, "https://x") is None


# --------------------------------------------------------------------------- #
# The banner channel (today's notify_macos, moved)
# --------------------------------------------------------------------------- #
def test_the_banner_is_unavailable_off_macos():
    run = Run()
    ch = alarm.BannerChannel(run=run, platform="linux")
    assert not ch.configured and ch.send("t", "b") is False and run.calls == []


def test_the_banner_passes_text_as_arguments_and_reports_failures():
    run = Run()
    ch = alarm.BannerChannel(run=run, platform="darwin")
    assert ch.send('SONAR "x"', 'a "quoted"\x01 body')
    args = run.calls[0]
    assert args[0] == "osascript" and args[args.index("--") + 1:] == [
        'a "quoted" body', 'SONAR "x"']
    ch = alarm.BannerChannel(run=timed_out, platform="darwin")
    assert ch.send("t", "b") is False and ch.why == "timed out after 10 s"
    ch = alarm.BannerChannel(run=Run(rc=1, stderr="execution error -2741"), platform="darwin")
    assert ch.send("t", "b") is False and ch.why == "refused (1): execution error -2741"


# --------------------------------------------------------------------------- #
# The notifier
# --------------------------------------------------------------------------- #
def test_a_failed_push_is_retried_once_then_counted(notifiers):
    """Owner decision 5. URLError, then 500: two attempts, one failure."""
    opener = Opener(url_error(), 500)
    n = notifiers(opener=opener)
    n.send(alarm.Event("poll", (("poll", 700.0),)))
    assert n.drain(5)
    assert len(opener.requests) == 2
    ntfy = n.states()["ntfy"]
    assert ntfy["state"] == "failing" and ntfy["failures"] == 1 and ntfy["consecutive"] == 1
    assert ntfy["last_fail_at"] and ntfy["last_ok_at"] is None
    opener.answers = [200]
    n.send(alarm.Event("recovery"))
    assert n.drain(5)
    ntfy = n.states()["ntfy"]
    assert ntfy["state"] == "ok" and ntfy["failures"] == 1 and ntfy["consecutive"] == 0


def test_a_retry_that_succeeds_is_not_a_failure(notifiers):
    opener = Opener(http_error(503), 200)
    n = notifiers(opener=opener)
    n.send(alarm.Event("poll"))
    assert n.drain(5) and len(opener.requests) == 2
    assert n.states()["ntfy"] | {"last_ok_at": None} == {
        "state": "ok", "reason": "ok", "attempts": 1, "failures": 0, "consecutive": 0,
        "last_ok_at": None, "last_fail_at": None, "in_flight_s": None, "dropped": 0}


def test_an_urgent_event_is_tried_once(notifiers):
    opener = Opener(500)
    n = notifiers(opener=opener, retry_after_s=60.0)
    n.send(alarm.Event("stopped", urgent=True))
    assert n.drain(5) and len(opener.requests) == 1
    assert n.states()["ntfy"]["failures"] == 1


def test_a_full_queue_drops_and_counts(notifiers):
    """Seventeen sends with the push hung: sixteen outstanding, one dropped."""
    release = threading.Event()
    opener = Opener(200, block=release)
    logs = []
    n = notifiers(opener=opener, log=logs.append)
    try:
        for _ in range(17):
            n.send(alarm.Event("recovery"))
        ntfy = n.states()["ntfy"]
        assert ntfy["dropped"] == 1 and ntfy["failures"] == 1
        assert any("ntfy alarm dropped" in line for line in logs)
    finally:
        release.set()
    assert n.drain(5)
    assert len(opener.requests) == 16


def test_a_send_hung_past_thirty_seconds_is_failing(notifiers):
    release = threading.Event()
    opener = Opener(200, block=release)
    now = [1000.0]
    n = notifiers(opener=opener)
    n.clock = lambda: now[0]
    try:
        n.send(alarm.Event("poll"))
        assert opener.called.wait(5)
        assert n.states()["ntfy"]["state"] == "ok"
        now[0] += alarm.IN_FLIGHT_FAILING_S + 1
        st = n.states()["ntfy"]
        assert st["state"] == "failing" and st["in_flight_s"] == alarm.IN_FLIGHT_FAILING_S + 1
    finally:
        release.set()
    assert n.drain(5)


def test_an_alarm_that_failed_on_ntfy_is_marked_until_something_is_delivered(notifiers):
    """Owner decision (a): only a failed push marks it, whatever the banner
    did, and the next delivered push clears it."""
    opener = Opener(500)
    n = notifiers(opener=opener)                  # the banner got it; the phone did not
    n.send(alarm.Event("poll"))
    assert n.drain(5) and n.undelivered
    n.send(alarm.Event("heartbeat"))              # not an alarm, and it failed too
    assert n.drain(5) and n.undelivered
    opener.answers = [200]
    n.send(alarm.Event("heartbeat"))
    assert n.drain(5) and not n.undelivered
    n.send(alarm.Event("poll"))
    assert n.drain(5) and not n.undelivered


def test_a_banner_only_install_never_marks_an_alarm_undelivered(notifiers):
    """Owner decision (a): with no topic, banner timeouts never turn health red."""
    banner = alarm.BannerChannel(run=timed_out, platform="darwin")
    n = alarm.Notifier([banner, alarm.NtfyChannel(None, Opener(200), "absent")],
                       log=lambda msg: None, retry_after_s=0.0)
    try:
        n.send(alarm.Event("loop"))
        assert n.drain(5) and not n.undelivered
        assert n.states()["banner"]["state"] == "failing"
    finally:
        n.close()


def test_with_no_channel_configured_a_send_is_a_no_op():
    n = alarm.Notifier([alarm.BannerChannel(run=Run(), platform="linux"),
                        alarm.NtfyChannel(None, Opener(200), "absent")], log=lambda m: None)
    n.send(alarm.Event("loop"))
    assert n.drain(1) and not n.undelivered
    assert {k: v["state"] for k, v in n.states().items()} == {
        "banner": "unavailable", "ntfy": "not configured"}
    n.close()


def test_failing_decays_after_an_hour_without_a_new_failure(notifiers):
    """Owner decision (b): ok again after FAILING_DECAY_S, with the failure
    time and count still shown."""
    now = [5000.0]
    n = notifiers(opener=Opener(500))
    n.clock = lambda: now[0]
    n.send(alarm.Event("poll"))
    assert n.drain(5)
    assert n.states()["ntfy"]["state"] == "failing"
    now[0] += alarm.FAILING_DECAY_S - 1
    assert n.states()["ntfy"]["state"] == "failing"
    now[0] += 1
    ntfy = n.states()["ntfy"]
    assert ntfy["state"] == "ok" and ntfy["failures"] == 1 and ntfy["last_fail_at"]


def test_the_stopped_notice_is_not_stuck_behind_a_retry(notifiers):
    """CR P2-1: an alarm waiting out its 60 s retry must not hold the notice
    the exit path is waiting for; the retry is abandoned."""
    opener = Opener(500, 200)
    n = notifiers(opener=opener, retry_after_s=60.0)
    n.send(alarm.Event("poll"))
    assert opener.called.wait(5)
    t0 = time.monotonic()
    n.send(alarm.Event("stopped", urgent=True))
    assert n.drain(5) and time.monotonic() - t0 < 5
    assert [r["headers"]["x-title"] for r in opener.requests] == [
        "SONAR (paper) needs attention", "SONAR (paper) stopped"]


class _HangFirst(Opener):
    """The first request hangs (a stuck connection); the rest answer 200.
    ``stopped`` is set when the "stopped" notice arrives."""

    def __init__(self, release):
        super().__init__(200)
        self.release, self.stopped = release, threading.Event()

    def open(self, req, timeout=None):
        first = not self.requests
        r = super().open(req, timeout)
        if dict(req.header_items()).get("X-title") == "SONAR (paper) stopped":
            self.stopped.set()
        if first:
            self.release.wait(30)
        return r


def test_the_stopped_notice_is_not_stuck_behind_a_hung_send(notifiers):
    """CR P2-1, QA N12: the notice goes past a hung send, and the urgent send
    neither hides the hung one's in-flight time nor leaves retries disabled."""
    release = threading.Event()
    opener = _HangFirst(release)
    n = notifiers(opener=opener)
    try:
        n.send(alarm.Event("poll"))
        assert opener.called.wait(10)
        delivery = n.send(alarm.Event("stopped", urgent=True))
        assert opener.stopped.wait(10), "the notice went out while the first send hung"
        with n._idle:
            assert n._idle.wait_for(lambda: n._urgent_live == 0, 10)
        assert delivery.delivered
        assert n.states()["ntfy"]["in_flight_s"] is not None, "the hung send is still shown"
        assert not n._hurry.is_set(), "later retries are not abandoned"
    finally:
        release.set()
    assert n.drain(5)
    assert n.states()["ntfy"]["failures"] == 0


def test_the_failing_decay_is_one_hour():
    """QA N8: owner decision (b) pins the value."""
    assert alarm.FAILING_DECAY_S == 3600


def test_a_delivery_counts_the_phone_when_there_is_one(notifiers):
    """Round 3, CR P3-1: with ntfy configured only the phone counts; with no
    topic the banner does."""
    n = notifiers(opener=Opener(500))             # the banner posted it, the phone did not
    d = n.send(alarm.Event("test"))
    assert n.drain(5) and not d.delivered and d.channels == {"banner"}
    n2 = notifiers(opener=Opener(200), banner_run=timed_out)
    d2 = n2.send(alarm.Event("test"))
    assert n2.drain(5) and d2.delivered
    n3 = alarm.Notifier([alarm.BannerChannel(run=Run(), platform="darwin"),
                         alarm.NtfyChannel(None, Opener(200), "absent")], log=lambda m: None)
    try:
        d3 = n3.send(alarm.Event("test"))
        assert n3.drain(5) and d3.delivered, "no topic: the banner is all there is"
    finally:
        n3.close()


def test_retries_stay_abandoned_until_every_urgent_lane_settles(notifiers):
    """QA M7: two urgent sends in flight (banner hung, ntfy answered). A retry
    that starts waiting after the first has settled is still abandoned."""
    release = threading.Event()
    banner = Run(block=release)
    opener = Opener(200, 500)                     # the urgent push is answered; later ones fail
    n = notifiers(opener=opener, banner_run=banner, retry_after_s=60.0)
    try:
        n.send(alarm.Event("stopped", urgent=True))
        assert banner.called.wait(10)
        lane = n._lanes["ntfy"]
        with n._idle:
            assert n._idle.wait_for(lambda: lane.outstanding == 0, 10), "the urgent push settled"
        assert n._urgent_live == 1 and n._hurry.is_set()
        n.send(alarm.Event("poll"))               # fails; its retry must not wait 60 s
        with n._idle:
            assert n._idle.wait_for(lambda: lane.outstanding == 0, 10)
        assert len(opener.requests) == 2, "urgent push, then one attempt and no retry"
    finally:
        release.set()
    assert n.drain(5) and not n._hurry.is_set()


def test_two_threads_share_no_failure_text():
    """CR P3-b: attempt() returns its own reason; nothing is shared."""
    ch = alarm.NtfyChannel(TOPIC, Opener(500, 200))
    assert ch.attempt("t", "b", 2) == (False, "HTTP 500")
    assert ch.attempt("t", "b", 2) == (True, "")
    assert ch.why == ""


def test_a_raising_log_does_not_kill_the_sender(notifiers):
    """Security P3-3: the lane outlives a log that raises."""
    def boom(msg):
        raise RuntimeError("disk full")
    opener = Opener(500, 500, 200)
    n = notifiers(opener=opener, log=boom)
    n.send(alarm.Event("poll"))                   # fails twice, logging raises each time
    assert n.drain(5)
    n.send(alarm.Event("recovery"))
    assert n.drain(5) and len(opener.requests) == 3
    assert n.states()["ntfy"]["state"] == "ok"


def test_the_push_gets_the_allowlist_and_the_banner_the_local_text(notifiers):
    opener, banner = Opener(200), Run()
    n = notifiers(opener=opener, banner_run=banner)
    n.send(alarm.Event("poll", (("poll", 660.0),)), ("SONAR needs attention", NASTY))
    assert n.drain(5)
    assert banner.calls[0][-2:] == [NASTY, "SONAR needs attention"]
    (req,) = opener.requests
    assert_allowlisted(req["headers"]["x-title"], req["body"])


# --------------------------------------------------------------------------- #
# Not configured (measure 3) and the startup line
# --------------------------------------------------------------------------- #
def test_with_no_topic_the_agent_says_so_once_and_sends_nothing(capsys):
    banner = Run()
    n = alarm.from_keychain(build=BUILD, read=lambda: alarm.read_topic(run=Run(rc=44)),
                            banner=alarm.BannerChannel(run=banner, platform="darwin"))
    try:
        n.send(alarm.Event("poll", (("poll", 700.0),)), ("SONAR needs attention", "x"))
        assert n.drain(5)
        assert banner.calls and banner.calls[0][-2:] == ["x", "SONAR needs attention"]
        ntfy = n.states()["ntfy"]
        assert ntfy["state"] == "not configured" and ntfy["reason"] == "absent"
        assert ntfy["failures"] == 0
    finally:
        n.close()
    lines = [ln for ln in capsys.readouterr().err.splitlines() if ln]
    assert lines == [lines[0]] and lines[0].endswith("push alarms: ntfy not configured (absent)")
    datetime.datetime.fromisoformat(TS_LINE.match(lines[0]).group(1))


def test_with_a_topic_the_agent_says_configured_without_the_topic(capsys):
    n = alarm.from_keychain(build=BUILD, read=lambda: (TOPIC, "ok"),
                            banner=alarm.BannerChannel(run=Run(), platform="darwin"),
                            opener=Opener(200))
    n.close()
    err = capsys.readouterr().err
    assert "push alarms: ntfy configured" in err and TOPIC not in err


def test_notifier_log_lines_are_timestamped_and_redacted(capsys, notifiers):
    n = notifiers(opener=Opener(url_error()), log=None)
    n._log = alarm._stderr
    n.send(alarm.Event("poll"))
    assert n.drain(5)
    n.say(f"a line that happens to hold {TOPIC}")
    lines = [ln for ln in capsys.readouterr().err.splitlines() if ln]
    assert len(lines) == 3
    for line in lines:
        datetime.datetime.fromisoformat(TS_LINE.match(line).group(1))
        assert TOPIC not in line
    assert "[topic]" in lines[-1]


# --------------------------------------------------------------------------- #
# The heartbeat schedule
# --------------------------------------------------------------------------- #
#: 2027-01-15 08:00:00 UTC; the tests read it with time.gmtime as "local".
NOW = 1_800_000_000.0
NINE = NOW + 3600


def _beat(path):
    return alarm.Heartbeat(path, localtime=time.gmtime)


def test_the_heartbeat_is_due_once_a_day_from_nine(tmp_path):
    path = tmp_path / "alarm.json"
    hb = _beat(path)
    assert not hb.due(NINE - 1)
    assert hb.due(NINE) and hb.due(NINE + 5 * 3600)
    hb.mark(NINE)
    assert not hb.due(NINE + 60)
    assert json.loads(path.read_text()) == {"heartbeat_day": "2027-01-15", "heartbeat_at": NINE}
    again = _beat(path)                       # a restart reads the day back
    assert not again.due(NINE + 3600)
    assert not again.due(NINE + 86400 - 1)
    assert again.due(NINE + 86400)


def test_a_corrupt_alarm_file_means_one_extra_heartbeat_never_a_crash(tmp_path):
    path = tmp_path / "alarm.json"
    path.write_text("[not an object")
    assert _beat(path).due(NINE)


def test_the_heartbeat_keeps_the_stopped_time_and_the_reverse(tmp_path):
    path = tmp_path / "alarm.json"
    alarm.merge_json(path, {"stopped_at": 5.0})
    _beat(path).mark(NINE)
    alarm.merge_json(path, {"stopped_at": 7.0})
    assert json.loads(path.read_text()) == {
        "stopped_at": 7.0, "heartbeat_day": "2027-01-15", "heartbeat_at": NINE}


# --------------------------------------------------------------------------- #
# --test-alarm (P3-3)
# --------------------------------------------------------------------------- #
def _test_alarm(opener, read=lambda: (TOPIC, "ok"), banner_run=None, out=None, **kw):
    out = out if out is not None else io.StringIO()
    rc = alarm.test_alarm(["--test-alarm"], read=read, opener=opener, out=out,
                          banner=alarm.BannerChannel(run=banner_run or Run(),
                                                     platform="darwin"),
                          retry_after_s=0.0, **kw)
    return rc, out.getvalue()


def test_the_test_alarm_pushes_and_says_so():
    opener = Opener(200)
    rc, out = _test_alarm(opener, build=BUILD)
    assert rc == 0 and out == "ntfy: ok\nbanner: ok\n"
    (req,) = opener.requests
    assert req["headers"]["x-title"] == "SONAR (paper) test alarm"
    assert req["headers"]["x-priority"] == "2"
    assert_allowlisted(req["headers"]["x-title"], req["body"])


def test_a_failing_test_alarm_is_retried_and_exits_non_zero():
    opener = Opener(http_error(404))
    rc, out = _test_alarm(opener, build=BUILD, banner_run=timed_out)
    assert rc == 1 and len(opener.requests) == 2
    assert out == "ntfy: failing (HTTP 404)\nbanner: failing (timed out after 10 s)\n"
    assert TOPIC not in out


def test_without_a_topic_the_test_alarm_says_not_configured():
    opener = Opener(200)
    rc, out = _test_alarm(opener, read=lambda: (None, "absent"), build=BUILD)
    assert rc == 1 and out.startswith("ntfy: not configured (absent)\n")
    assert opener.requests == []


def test_the_test_alarm_never_touches_the_data_directory(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setenv("SONAR_DATA", str(data))
    rc, _ = _test_alarm(Opener(200))              # build from version.info()
    assert rc == 0 and list(data.iterdir()) == []


def test_importing_the_alarm_module_cannot_reach_the_book(tmp_path):
    code = ("import sys, sonar.alarm; "
            "bad = [m for m in ('sonar.core', 'sonar.engine', 'sonar.portfolio') "
            "if m in sys.modules]; print(bad); sys.exit(1 if bad else 0)")
    env = {**os.environ, "SONAR_DATA": str(tmp_path)}
    r = _REAL_RUN([sys.executable, "-c", code], cwd=ROOT, env=env,
                  capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
    assert list(tmp_path.iterdir()) == []


def test_the_test_alarm_ignores_other_arguments():
    """main.py passes the whole argv; a stray flag must not abort the test."""
    rc, out = _test_alarm(Opener(200), build=BUILD)
    rc2 = alarm.test_alarm(["--test-alarm", "--port", "1"], read=lambda: (TOPIC, "ok"),
                           opener=Opener(200), out=io.StringIO(), build=BUILD,
                           banner=alarm.BannerChannel(run=Run(), platform="darwin"))
    assert rc == rc2 == 0


def test_main_dispatches_the_flag_before_headless():
    source = (ROOT / "main.py").read_text()
    assert source.index('"--test-alarm" in sys.argv') < source.index('"--headless" in sys.argv')
    assert "alarm.test_alarm(sys.argv[1:])" in source


@pytest.mark.parametrize("call", [
    lambda: subprocess.run("osascript -e 'beep'", shell=True),
    lambda: subprocess.run(["/usr/bin/security", "find-generic-password"]),
    lambda: subprocess.Popen(["osascript", "-e", "beep"]),
    lambda: subprocess.check_output("cd /tmp && /usr/bin/security dump-keychain", shell=True),
    lambda: subprocess.run(["sh", "-c", "echo hi; osascript -e beep"]),
    lambda: subprocess.run(["/bin/bash", "-c", "true && security find-generic-password"]),
    lambda: subprocess.run("echo x | osascript", shell=True),
    lambda: subprocess.run("echo $(security find-generic-password -w)", shell=True),
    lambda: subprocess.run("echo `osascript -e beep`", shell=True),
    lambda: subprocess.run("security>file", shell=True),
    lambda: subprocess.run("echo don't; security find-generic-password", shell=True),
    lambda: subprocess.run(["zsh", "-c", "(cd /; /usr/bin/osascript -e beep)"]),
], ids=["shell-str", "list", "popen", "and-chain", "sh-c-semicolon", "bash-c-and",
        "pipe", "dollar-paren", "backticks", "redirect", "unbalanced-quote", "subshell"])
def test_the_suite_guard_refuses_real_channels_in_any_form(call, monkeypatch):
    """Security P3-4: string commands and Popen are refused too."""
    import conftest
    monkeypatch.setattr(subprocess, "run", conftest._guarded_run)
    with pytest.raises(conftest.RealChannelInTest):
        call()


@pytest.mark.parametrize("args", [
    ["git", "log", "--grep", "security"],     # only a list's program is checked
    ["python", "-c", "print('osascript')"],   # not a shell: its -c is not scanned
    "echo don't panic",                        # an unbalanced quote does not raise
])
def test_the_suite_guard_lets_ordinary_commands_through(args):
    import conftest
    conftest._refuse_real_channel(args)


def test_a_raising_log_does_not_break_a_send_that_drops(notifiers):
    """CR P3-d: the "dropped" line goes through _safe_say, so a full queue and
    a broken log never raise into the watchdog."""
    def boom(msg):
        raise RuntimeError("log disk full")
    release = threading.Event()
    n = notifiers(opener=Opener(200, block=release), log=boom)
    try:
        for _ in range(alarm.QUEUE_MAX + 1):
            n.send(alarm.Event("recovery"))           # the last one drops; must not raise
        assert n.states()["ntfy"]["dropped"] == 1
    finally:
        release.set()
    assert n.drain(5)


# --------------------------------------------------------------------------- #
# SONAR_ALARM: the off-switch for diagnostic engines (starved-engine A2)
# --------------------------------------------------------------------------- #
class Read:
    """A Keychain read that records being called, or refuses to be."""

    def __init__(self, allowed=True):
        self.allowed, self.calls = allowed, 0

    def __call__(self):
        self.calls += 1
        if not self.allowed:
            raise AssertionError("the Keychain was read under SONAR_ALARM")
        return TOPIC, "ok"


@pytest.mark.parametrize("env,want", [
    ({}, "on"), ({"SONAR_ALARM": ""}, "on"), ({"SONAR_ALARM": "  "}, "on"),
    ({"SONAR_ALARM": "on"}, "on"), ({"SONAR_ALARM": "OFF "}, "off"),
    ({"SONAR_ALARM": " Banner-Only"}, "banner-only"), ({"SONAR_ALARM": "bogus"}, "bogus"),
])
def test_alarm_mode_is_stripped_and_lower_cased(env, want):
    assert alarm.alarm_mode(env) == want


@pytest.mark.parametrize("value", [None, "", "on", " ON "])
def test_the_default_modes_read_the_keychain_as_today(value):
    read = Read()
    env = {} if value is None else {"SONAR_ALARM": value}
    n = alarm.from_keychain(build=BUILD, read=read, log=lambda m: None,
                            mode=alarm.alarm_mode(env), opener=Opener(200),
                            banner=alarm.BannerChannel(run=Run(), platform="darwin"))
    try:
        assert read.calls == 1
        assert n.states()["ntfy"]["state"] == "ok"
    finally:
        n.close()


@pytest.mark.parametrize("value", ["banner-only", "off", "OFF ", "bogus"])
def test_any_other_mode_never_reads_the_keychain_or_pushes(value):
    opener = Opener(200)
    n = alarm.from_keychain(build=BUILD, read=Read(allowed=False), log=lambda m: None,
                            mode=alarm.alarm_mode({"SONAR_ALARM": value}), opener=opener,
                            banner=alarm.BannerChannel(run=Run(), platform="darwin"))
    try:
        n.send(alarm.Event("poll", (("poll", 700.0),)))
        assert n.drain(5)
        assert opener.requests == []
        ntfy = n.states()["ntfy"]
        assert ntfy["state"] == "not configured" and ntfy["reason"] == "off (SONAR_ALARM)"
        assert ntfy["failures"] == 0 and not n.undelivered
    finally:
        n.close()


def test_off_starts_no_osascript_and_reports_both_channels_off():
    banner = Run()
    lines = []
    n = alarm.from_keychain(build=BUILD, read=Read(allowed=False), log=lines.append,
                            mode="off", opener=Opener(200),
                            banner=alarm.BannerChannel(run=banner, platform="darwin"))
    try:
        d = n.send(alarm.Event("poll", (("poll", 700.0),)), ("SONAR needs attention", "x"))
        assert n.drain(5)
        assert banner.calls == [], "a banner was posted under SONAR_ALARM=off"
        assert d.required is None
        s = n.states()
        assert s["banner"]["state"] == "unavailable"
        assert s["banner"]["reason"] == "off (SONAR_ALARM)"
        assert s["ntfy"]["state"] == "not configured"
        assert s["ntfy"]["reason"] == "off (SONAR_ALARM)"
    finally:
        n.close()
    assert len(lines) == 1 and lines[0].endswith("push alarms: off (SONAR_ALARM=off)")


def test_banner_only_keeps_the_banner():
    banner = Run()
    lines = []
    n = alarm.from_keychain(build=BUILD, read=Read(allowed=False), log=lines.append,
                            mode="banner-only",
                            banner=alarm.BannerChannel(run=banner, platform="darwin"))
    try:
        n.send(alarm.Event("poll", (("poll", 700.0),)), ("SONAR needs attention", "x"))
        assert n.drain(5)
        assert banner.calls and banner.calls[0][-2:] == ["x", "SONAR needs attention"]
        assert "reason" not in n.states()["banner"]
    finally:
        n.close()
    assert len(lines) == 1 and lines[0].endswith("push alarms: off (SONAR_ALARM=banner-only)")


def test_an_unknown_mode_is_named_once_and_keeps_the_banner():
    banner = Run()
    lines = []
    n = alarm.from_keychain(build=BUILD, read=Read(allowed=False), log=lines.append,
                            mode=alarm.alarm_mode({"SONAR_ALARM": "Bogus"}),
                            banner=alarm.BannerChannel(run=banner, platform="darwin"))
    try:
        n.send(alarm.Event("poll", (("poll", 700.0),)), ("SONAR needs attention", "x"))
        assert n.drain(5)
        assert banner.calls, "an unknown value lost the banner"
        assert n.states()["ntfy"]["reason"] == "off (SONAR_ALARM)"
    finally:
        n.close()
    assert len(lines) == 1
    assert "'bogus'" in lines[0] and "treated as banner-only" in lines[0]


@pytest.mark.parametrize("value,want", [(None, "on"), ("off", "off"), ("x", "x")])
def test_server_main_passes_the_env_mode(monkeypatch, tmp_path, value, want):
    monkeypatch.setattr("sonar.paths.user_data_base", lambda: tmp_path)
    if value is None:
        monkeypatch.delenv("SONAR_ALARM", raising=False)
    else:
        monkeypatch.setenv("SONAR_ALARM", value)
    seen = []

    def fake_from_keychain(build=None, mode="on", **kw):
        seen.append(mode)
        return alarm.Notifier([], log=lambda m: None)

    class FakeServer:
        def __init__(self, *a):
            pass

        def serve_forever(self):
            pass

    class StubLive:
        def __init__(self, **kw):
            self.risk = type("R", (), {"name": "moderate"})()
            self.horizon = type("H", (), {"name": "week"})()
            self.read_only = False

        def run(self, role, url=None):
            pass

    monkeypatch.setattr(alarm, "from_keychain", fake_from_keychain)
    monkeypatch.setattr(server, "Live", StubLive)
    monkeypatch.setattr(server, "PaperServer", FakeServer)
    monkeypatch.setattr(server.time, "sleep", lambda s: None)
    monkeypatch.setattr(server.Handler, "live", None)
    monkeypatch.setattr(server.Handler, "notifier", None, raising=False)
    monkeypatch.setattr(server.Watchdog, "run", lambda self, stop=None: None)
    server.main(port=0)
    assert seen == [want]


def test_attempts_count_every_outcome_so_failures_per_attempt_can_be_read(notifiers):
    """starved-engine measure 4 reports banner failures per banner attempt."""
    banner = Run(rc=1)
    n = notifiers(opener=Opener(200, 200), banner_run=banner)
    n.send(alarm.Event("poll"))
    n.send(alarm.Event("recovery"))
    assert n.drain(5)
    b = n.states()["banner"]
    assert b["attempts"] == 2 and b["failures"] == 2
    assert n.states()["ntfy"]["attempts"] == 2 and n.states()["ntfy"]["failures"] == 0


def test_health_shows_the_alarm_is_off_under_sonar_alarm():
    """The harness's fail-closed check reads exactly this (QA test-quality gap)."""
    class Live:
        def health(self, now=None):
            return {"ok": True, "problems": [], "last_poll_age_s": 1.0}

    n = alarm.from_keychain(build=BUILD, read=Read(allowed=False), log=lambda m: None,
                            mode="off")
    try:
        h = server.agent_health(Live(), n)
    finally:
        n.close()
    assert h["notify"]["ntfy"]["reason"] == "off (SONAR_ALARM)"
    assert h["ok"] is True, "the switch alone must not turn health red"
