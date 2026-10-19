"""Alarms that reach the owner away from this Mac.

The agent's only alarm was a macOS banner through ``osascript``, and from
2026-10-12 45 of its 47 attempts timed out: the text existed and never left the
machine. This adds an ntfy.sh push beside the banner, a daily heartbeat whose
absence is itself the alarm, and per-channel counts for ``/api/health``, so a
broken channel no longer looks healthy (``docs/specs/alarm-delivery.md``,
``docs/adr/0005-ntfy-push-alarm-keychain-topic.md``).

What may leave the Mac is closed by construction. An :class:`Event` has no
free-text field, and :func:`render` builds every push from fixed phrases, whole
durations, a version that matches a pattern and each channel's state word.
Problem text, exception text and server text stay in the local log.

Stdlib only, and it never imports ``core``, ``engine`` or ``portfolio``:
``--test-alarm`` runs through here and must not be able to reach the book.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import queue
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from . import paths

#: The push host is a constant, not a setting: a setting is a way to send the
#: alarm text somewhere else.
NTFY_URL = "https://ntfy.sh/"

#: The topic is a generic password in the login Keychain. ``security`` reads
#: it, not SONAR: an ad hoc signed build has a new identity every time, so a
#: Keychain ACL naming SONAR would prompt after every build with nobody there
#: to answer, while ``/usr/bin/security`` is Apple-signed and stays trusted.
KEYCHAIN_SERVICE = "com.netrunner3000.sonar.ntfy"
KEYCHAIN_ACCOUNT = "topic"
KEYCHAIN_TIMEOUT_S = 5

#: Anyone who knows the topic can read the pushes, so it must be long and random.
TOPIC_RE = re.compile(r"[A-Za-z0-9_-]{24,64}")
VERSION_RE = re.compile(r"v?[0-9][0-9A-Za-z.+-]{0,31}")

SEND_TIMEOUT_S = 10
#: One retry per ntfy event (owner decision 5). 10 + 20 + 10 s is inside the
#: spec's 60 s delivery budget.
NTFY_RETRY_AFTER_S = 20.0
#: DNS resolution is not covered by urllib's timeout, so a send this old is
#: reported as failing rather than trusted to finish.
IN_FLIGHT_FAILING_S = 30.0
#: A channel whose last send failed shows "failing" for this long without a new
#: failure, then "ok" again with ``last_fail_at`` and ``failures`` still shown
#: (owner decision (b), Review): one lost push must not keep health red until
#: the next event, which can be a day away.
FAILING_DECAY_S = 3600.0
#: Events queued or in flight per channel; past this they are dropped and counted.
QUEUE_MAX = 16

#: Local time of the daily heartbeat: waking hours, when a missing push is noticed.
HEARTBEAT_AT = (9, 0)

TITLE = "SONAR (paper)"
PRIORITY_ALARM, PRIORITY_INFO = 4, 2

#: The only words a problem kind can become on the phone: (phrase, unit of its
#: duration or None). A kind missing here is pushed as "other problem", and
#: tests/test_alarm.py fails until it has a phrase.
PHRASES = {
    "loop": ("the engine loop stopped", None),
    "poll": ("no successful price poll", "min"),
    "scan": ("the board scan stalled", "min"),
    "settle": ("no hour settled", "h"),
    "notify": ("an alarm channel is failing", None),
    "other": ("other problem", None),
}

#: Events that are not a problem: (title suffix, body phrase, priority).
NOTICES = {
    "stopped": ("stopped", "the engine loop ended and the agent is restarting",
                PRIORITY_ALARM),
    "recovery": ("working again", "no open problems", PRIORITY_INFO),
    "heartbeat": ("alive", None, PRIORITY_INFO),
    "test": ("test alarm", "test alarm, no action needed", PRIORITY_INFO),
}

STATE_WORDS = ("ok", "failing", "unavailable", "not configured")


def ts() -> str:
    """Now as a local ISO timestamp, the prefix of every alarm and watchdog
    log line, so the log shows when an alarm fired."""
    return _dt.datetime.now().astimezone().isoformat(timespec="seconds")


def _iso(t: float | None) -> str | None:
    if t is None:
        return None
    return _dt.datetime.fromtimestamp(t).astimezone().isoformat(timespec="seconds")


def _stderr(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


# --------------------------------------------------------------------------- #
# What a push may say
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Event:
    """Something to tell the owner. There is no text field on purpose.

    ``kind`` is a problem kind (``loop``, ``poll``, ...) for an alarm, or one
    of :data:`NOTICES`. ``open_kinds`` pairs each kind with how long it has
    lasted in seconds (None when unknown): the kinds due in an alarm, or the
    kinds open at a heartbeat. Each kind carries its own duration, so one push
    naming two problems cannot put one's duration beside the other (domain
    P3-B). ``urgent`` is the "stopped" notice: one attempt, no retry, because
    the process is about to exit."""

    kind: str
    open_kinds: tuple[tuple[str, float | None], ...] = ()
    urgent: bool = False

    @property
    def is_alarm(self) -> bool:
        return self.kind not in NOTICES


def _version(build) -> str:
    return build if isinstance(build, str) and VERSION_RE.fullmatch(build) else "unknown"


def _kind_word(kind: str) -> str:
    return kind if kind in PHRASES else "other"


def _phrase(kind: str, duration_s) -> str:
    text, unit = PHRASES[_kind_word(kind)]
    if unit is None or isinstance(duration_s, bool) \
            or not isinstance(duration_s, (int, float)) or not duration_s >= 0:
        return text
    n = int(duration_s // (60 if unit == "min" else 3600))
    return f"{text} for at least {n} {unit}"


def _channels(states) -> str:
    def word(name: str) -> str:
        s = ((states or {}).get(name) or {}).get("state")
        return s if s in STATE_WORDS else "unknown"
    return f"channels: banner {word('banner')}, ntfy {word('ntfy')}"


def render(event: Event, build, channel_states) -> tuple[str, str, int]:
    """``(title, body, priority)`` for a push: the only place push text is made.

    Every part comes from a closed vocabulary: the phrases above, whole
    minutes or hours, a version matching :data:`VERSION_RE` (else "unknown")
    and each channel's state word. Nothing a caller passes is copied in."""
    v = _version(build)
    channels = _channels(channel_states)
    if event.kind == "heartbeat":
        kinds = list(dict.fromkeys(_kind_word(k) for k, _ in event.open_kinds))
        body = (f"{TITLE} alive, build {v}; open problems: "
                f"{', '.join(kinds) or 'none'}; {channels}")
        return f"{TITLE} alive", body, PRIORITY_INFO
    if event.kind in NOTICES:
        suffix, text, priority = NOTICES[event.kind]
        return f"{TITLE} {suffix}", f"{text}; build {v}; {channels}", priority
    pairs = event.open_kinds or ((event.kind, None),)
    said = "; ".join(dict.fromkeys(_phrase(k, d) for k, d in pairs))
    return f"{TITLE} needs attention", f"{said}; build {v}; {channels}", PRIORITY_ALARM


# --------------------------------------------------------------------------- #
# Channels
# --------------------------------------------------------------------------- #
NOTIFY_SCRIPT = ("on run argv", "display notification (item 1 of argv) "
                 "with title (item 2 of argv)", "end run")


def plain(text: str, limit: int = 200) -> str:
    """One line of printable text: the body can carry exception text from the
    network, and a control character made AppleScript reject the whole call."""
    flat = "".join(c if c.isprintable() else " " for c in text)
    return " ".join(flat.split())[:limit]


class BannerChannel:
    """The macOS banner, the local channel. The text goes in as arguments,
    never into the script's source. It gets the full local text, not the push
    body: on this Mac nothing changes. ``send`` never raises; ``why`` says
    what went wrong last time."""

    name = "banner"
    idle_state = "unavailable"
    retries = False
    tracks_delivery = False
    wants_local_text = True

    def __init__(self, run=None, platform: str | None = None,
                 off_reason: str | None = None):
        self._run = run
        self.configured = (platform or sys.platform) == "darwin" and not off_reason
        if off_reason:                    # _state reports a reason only when there is one
            self.reason = off_reason
        self.why = ""

    def send(self, title: str, body: str, priority: int = PRIORITY_INFO,
             timeout: float = SEND_TIMEOUT_S) -> bool:
        """Post once; True if posted. ``why`` says what went wrong."""
        ok, self.why = self.attempt(title, body, priority, timeout)
        return ok

    def attempt(self, title: str, body: str, priority: int = PRIORITY_INFO,
                timeout: float = SEND_TIMEOUT_S) -> tuple[bool, str]:
        """Post once: ``(ok, why)``. Shares no state, so two threads may call it."""
        if not self.configured:
            return False, "not on macOS"
        args = ["osascript"]
        for line in NOTIFY_SCRIPT:
            args += ["-e", line]
        args += ["--", plain(body), plain(title, 60)]
        run = self._run or subprocess.run
        try:
            r = run(args, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return False, f"timed out after {timeout:g} s"
        except Exception as exc:          # a channel reports, it never raises
            return False, plain(f"{type(exc).__name__}: {exc}", 160)
        rc = getattr(r, "returncode", 0)
        if rc:
            return False, f"refused ({rc}): {plain(getattr(r, 'stderr', '') or '', 160)}"
        return True, ""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect is not followed off to another host; it fails the send."""

    def redirect_request(self, *args, **kwargs):
        return None


def _ntfy_opener() -> urllib.request.OpenerDirector:
    """No proxy from the environment or system settings and no redirects, as
    ``core._follow_opener``: the request goes to ntfy.sh or nowhere."""
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect)


def _why(exc: BaseException) -> str:
    """A failed send as a few safe words. Never ``str(exc)``: a URLError's text
    can carry the URL, and the URL carries the topic."""
    if isinstance(exc, TimeoutError):
        return "timeout"
    if isinstance(exc, urllib.error.URLError):
        reason = exc.reason
        if isinstance(reason, TimeoutError):
            return "timeout"
        if isinstance(reason, BaseException):
            return f"URLError ({type(reason).__name__})"
        return "URLError"
    return type(exc).__name__


class NtfyChannel:
    """An HTTPS POST to ntfy.sh, the channel that reaches the phone. Any 2xx is
    delivered. The response body is never read or logged, and the topic
    never appears in ``why`` or ``repr``."""

    name = "ntfy"
    idle_state = "not configured"
    retries = True
    #: Only a failed push can make "an alarm did not reach the phone" (owner decision (a)).
    tracks_delivery = True
    wants_local_text = False

    def __init__(self, topic: str | None, opener=None, reason: str | None = None):
        self._topic = topic or None
        self.configured = self._topic is not None
        self.reason = reason or ("ok" if self.configured else "absent")
        self._opener = opener
        self.why = ""

    def __repr__(self) -> str:
        return f"NtfyChannel(configured={self.configured}, reason={self.reason!r})"

    @property
    def topic(self) -> str | None:
        return self._topic

    def send(self, title: str, body: str, priority: int = PRIORITY_INFO,
             timeout: float = SEND_TIMEOUT_S) -> bool:
        """Post once; True if delivered. ``why`` says what went wrong."""
        ok, self.why = self.attempt(title, body, priority, timeout)
        return ok

    def attempt(self, title: str, body: str, priority: int = PRIORITY_INFO,
                timeout: float = SEND_TIMEOUT_S) -> tuple[bool, str]:
        """Post once: ``(ok, why)``. Shares no state, so two threads may call it."""
        if not self.configured:
            return False, f"not configured ({self.reason})"
        req = urllib.request.Request(
            NTFY_URL + self._topic, data=body.encode("ascii", "replace"), method="POST",
            headers={"X-Title": title, "X-Priority": str(priority),
                     "Content-Type": "text/plain"})
        opener = self._opener or _ntfy_opener()
        try:
            with opener.open(req, timeout=timeout) as r:
                code = getattr(r, "status", None) or r.getcode()
        except urllib.error.HTTPError as exc:
            code = exc.code
            try:
                exc.close()
            except Exception:
                pass
        except Exception as exc:          # a channel reports, it never raises
            return False, _why(exc)
        try:
            ok = 200 <= int(code) < 300
        except (TypeError, ValueError):
            ok = False
        return ok, "" if ok else f"HTTP {code}"


def read_topic(run=None) -> tuple[str | None, str]:
    """The ntfy topic from the login Keychain, as ``(topic, reason)``.

    ``reason`` is one of ok, absent, invalid, keychain error, timeout. It is
    never the value and never ``security``'s stderr. Read once, at start: a
    changed topic needs a restart."""
    run = run or subprocess.run
    try:
        r = run(["/usr/bin/security", "find-generic-password", "-s", KEYCHAIN_SERVICE,
                 "-a", KEYCHAIN_ACCOUNT, "-w"],
                capture_output=True, text=True, timeout=KEYCHAIN_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return None, "timeout"
    except Exception:
        return None, "keychain error"
    rc = getattr(r, "returncode", 1)
    if rc == 44:                          # errSecItemNotFound
        return None, "absent"
    if rc:
        return None, "keychain error"
    value = (getattr(r, "stdout", "") or "").strip()
    if not TOPIC_RE.fullmatch(value):
        return None, "invalid"
    return value, "ok"


# --------------------------------------------------------------------------- #
# The notifier: one sender thread per channel
# --------------------------------------------------------------------------- #
class _Lane:
    """One channel's queue, sender thread and counts."""

    def __init__(self, channel, retry_after_s: float | None):
        self.channel = channel
        self.retry_after_s = retry_after_s
        self.q: queue.Queue = queue.Queue()
        self.outstanding = 0              # queued or in flight
        self.failures = self.consecutive = self.dropped = 0
        #: Every counted outcome, delivered, failed or dropped: the denominator
        #: of "failures per attempt" (starved-engine measure 4).
        self.attempts = 0
        self.last_ok_at: float | None = None
        self.last_fail_at: float | None = None
        self.last_failed = False
        self.started_at: float | None = None
        self.thread: threading.Thread | None = None


class Delivery:
    """Whether one sent event got where it counts. Read after ``drain``.

    With ntfy configured, only the phone counts: a banner on an empty desk
    is not the owner told. With no topic, the banner is all there is, so it
    counts (owner decision, round 3)."""

    def __init__(self, delivered: bool = False, required: str | None = None):
        self.channels: set[str] = set()       # the channels that delivered it
        self.required = required              # the channel that must, if any
        self._forced = delivered              # the old notify= hook: always delivered

    @property
    def delivered(self) -> bool:
        if self._forced:
            return True
        if self.required is not None:
            return self.required in self.channels
        return bool(self.channels)


class Notifier:
    """Sends events on every configured channel without blocking the caller.

    Each channel has its own daemon thread, so a hung ``osascript`` never
    delays the push and a hung DNS lookup never delays the banner, and the
    watchdog's 15 s tick stays a 15 s tick. ``send`` never blocks: a channel
    with :data:`QUEUE_MAX` events outstanding drops the event and counts it.
    A failed ntfy send is retried once after ``retry_after_s``; then it is
    counted. Counts live in memory: a restart resets them, the log keeps the
    history.

    An urgent event (the "stopped" notice before exit 3) does not queue: it
    goes out at once on its own thread per channel, past a retry wait or a
    hung send, and any retry still waiting is abandoned, because the process
    is about to end and the notice is what matters."""

    def __init__(self, channels, log=None, clock=time.time, build=None,
                 retry_after_s: float = NTFY_RETRY_AFTER_S):
        self._log = log or _stderr
        self.clock = clock
        self.build = build
        self._lock = threading.Lock()
        self._idle = threading.Condition(self._lock)
        #: Set while an urgent event is being sent, or after close(): a retry
        #: still waiting is abandoned. Cleared when the last urgent send settles.
        self._hurry = threading.Event()
        self._urgent_live = 0
        self._closed = False
        self._lanes = {ch.name: _Lane(ch, retry_after_s if ch.retries else None)
                       for ch in channels}
        self._secrets = [s for s in (getattr(ch, "topic", None) for ch in channels) if s]
        #: The kinds of alarms that failed on the configured ntfy channel, with
        #: nothing delivered there since and the kinds still open: while any
        #: remain, "an alarm did not reach the phone" is a health problem. Never set
        #: by the banner, so a banner-only install never goes red from its
        #: timeouts (owner decision (a)).
        self._undelivered: set[str] = set()
        #: The problem kinds open now, from the watchdog; None until it says.
        self._open: set[str] | None = None
        for lane in self._lanes.values():
            if lane.channel.configured:
                lane.thread = threading.Thread(target=self._serve, args=(lane,),
                                               name=f"sonar-alarm-{lane.channel.name}",
                                               daemon=True)
                lane.thread.start()

    # -- text ------------------------------------------------------------- #
    def redact(self, s: str) -> str:
        """``s`` with the topic replaced. Defence in depth: no path is meant
        to put the topic in text, and every log line goes through here."""
        for secret in self._secrets:
            s = s.replace(secret, "[topic]")
        return s

    def say(self, msg: str) -> None:
        """One timestamped, redacted log line."""
        self._log(self.redact(f"SONAR {ts()}: {plain(msg, 2000)}"))

    # -- sending ---------------------------------------------------------- #
    @property
    def undelivered(self) -> bool:
        """An alarm failed on ntfy, and its kinds are still open."""
        with self._lock:
            return bool(self._undelivered)

    def send(self, event: Event, local_text: tuple[str, str] | None = None) -> Delivery:
        """Queue ``event`` on every configured channel. ``local_text`` is the
        banner's (title, body); the push always gets :func:`render`'s text.
        The returned :class:`Delivery` says, once the event has settled,
        whether any channel delivered it."""
        title, body, priority = render(event, self.build, self.states())
        local = local_text or (title, body)
        kinds = (frozenset(k for k, _ in event.open_kinds) or frozenset({event.kind})) \
            if event.is_alarm else frozenset()
        dropped = []
        with self._lock:
            lanes = [ln for ln in self._lanes.values() if ln.channel.configured]
            phone = next((ln.channel.name for ln in lanes if ln.channel.tracks_delivery), None)
            delivery = Delivery(required=phone)
            if event.urgent and lanes:
                self._urgent_live += len(lanes)
                self._hurry.set()             # abandon any retry still waiting
            now = self.clock()
            for lane in lanes:
                text = local if lane.channel.wants_local_text else (title, body)
                item = (kinds, event.urgent, text, priority, delivery)
                if event.urgent:
                    lane.outstanding += 1
                    threading.Thread(target=self._deliver, args=(lane, item),
                                     name=f"sonar-alarm-{lane.channel.name}-urgent",
                                     daemon=True).start()
                    continue
                if lane.outstanding >= QUEUE_MAX:
                    lane.dropped += 1
                    self._count(lane, False, now, kinds)
                    dropped.append(lane.channel.name)
                    continue
                lane.outstanding += 1
                lane.q.put(item)
        for name in dropped:
            self._safe_say(f"{name} alarm dropped: {QUEUE_MAX} already waiting")
        return delivery

    def set_open_kinds(self, kinds) -> None:
        """The watchdog's open problem kinds, each tick. An undelivered alarm
        stops being a problem once its own kinds have cleared (owner decision
        (a)), and a retry that fails after that cannot bring it back."""
        with self._lock:
            self._open = set(kinds)
            self._undelivered &= self._open

    def _count(self, lane: _Lane, ok: bool, now: float,
               kinds: frozenset = frozenset()) -> None:
        """Count one event's outcome on ``lane``. Under the lock."""
        lane.attempts += 1
        if ok:
            lane.consecutive, lane.last_ok_at, lane.last_failed = 0, now, False
        else:
            lane.failures += 1
            lane.consecutive += 1
            lane.last_fail_at, lane.last_failed = now, True
        if lane.channel.tracks_delivery:
            if ok:
                self._undelivered.clear()     # something reached the phone since
            elif kinds:
                self._undelivered |= kinds if self._open is None else kinds & self._open

    def _attempt(self, lane: _Lane, title: str, body: str, priority: int,
                 track: bool = True) -> tuple[bool, str]:
        """One send. Only the lane's own sends (``track``) set ``started_at``:
        an urgent send beside a hung one must not hide that it hangs."""
        if track:
            with self._lock:
                lane.started_at = self.clock()
        try:
            ok, why = lane.channel.attempt(title, body, priority, SEND_TIMEOUT_S)
            return bool(ok), why
        except Exception as exc:          # a channel is not meant to raise
            return False, type(exc).__name__

    def _safe_say(self, msg: str) -> None:
        """A log line from a sender thread: a raising log must not end the thread."""
        try:
            self.say(msg)
        except Exception:
            pass

    def _deliver(self, lane: _Lane, item) -> None:
        """Send one event on ``lane``, with the retry, then count it. Always
        settles the event, whatever raises, so ``drain`` and the counts hold."""
        kinds, urgent, (title, body), priority, delivery = item
        name, ok, why = lane.channel.name, False, "error"
        track = not urgent                    # an urgent send runs beside the lane's own
        try:
            ok, why = self._attempt(lane, title, body, priority, track)
            if not ok and lane.retry_after_s is not None and not urgent:
                self._safe_say(f"{name} alarm failed ({why}); "
                               f"retrying in {lane.retry_after_s:g} s")
                if not self._hurry.wait(lane.retry_after_s):
                    ok, why = self._attempt(lane, title, body, priority)
        finally:
            with self._lock:
                if track:
                    lane.started_at = None
                self._count(lane, ok, self.clock(), kinds)
                if ok:
                    delivery.channels.add(name)
                if urgent:
                    self._urgent_live -= 1
                    if self._urgent_live <= 0 and not self._closed:
                        self._hurry.clear()
                lane.outstanding -= 1
                self._idle.notify_all()
        if not ok:
            self._safe_say(f"{name} alarm not delivered ({why})")

    def _serve(self, lane: _Lane) -> None:
        while True:
            item = lane.q.get()
            if item is None:
                return
            try:
                self._deliver(lane, item)
            except Exception:                 # the lane outlives any one event
                pass

    def drain(self, deadline_s: float) -> bool:
        """Wait up to ``deadline_s`` for every queue to empty. True if it did."""
        end = time.monotonic() + deadline_s
        with self._idle:
            while any(ln.outstanding for ln in self._lanes.values()):
                left = end - time.monotonic()
                if left <= 0:
                    return False
                self._idle.wait(left)
        return True

    def close(self) -> None:
        """Stop the sender threads (after the event each is sending)."""
        with self._lock:
            self._closed = True
        self._hurry.set()
        for lane in self._lanes.values():
            if lane.thread is not None:
                lane.q.put(None)

    # -- health ----------------------------------------------------------- #
    def states(self) -> dict:
        """The ``notify`` block of ``/api/health``. Never holds the topic."""
        now = self.clock()
        with self._lock:
            return {name: self._state(lane, now) for name, lane in self._lanes.items()}

    def _state(self, lane: _Lane, now: float) -> dict:
        ch = lane.channel
        in_flight = None if lane.started_at is None else round(now - lane.started_at, 1)
        if not ch.configured:
            state = ch.idle_state
        elif (lane.last_failed and lane.last_fail_at is not None
              and now - lane.last_fail_at < FAILING_DECAY_S) \
                or (in_flight is not None and in_flight > IN_FLIGHT_FAILING_S):
            state = "failing"
        else:
            state = "ok"
        out = {"state": state}
        if hasattr(ch, "reason"):
            out["reason"] = ch.reason
        out.update({"attempts": lane.attempts, "failures": lane.failures,
                    "consecutive": lane.consecutive,
                    "last_ok_at": _iso(lane.last_ok_at),
                    "last_fail_at": _iso(lane.last_fail_at),
                    "in_flight_s": in_flight, "dropped": lane.dropped})
        return out


#: ``SONAR_ALARM``: the off-switch for throwaway diagnostic engines, which
#: must never push an alarm that looks like the live agent's
#: (``docs/specs/starved-engine.md`` A2). The live agent's plist pins it to ``on``.
ALARM_ENV = "SONAR_ALARM"
ALARM_MODES = ("on", "banner-only", "off")
OFF_REASON = "off (SONAR_ALARM)"


def alarm_mode(environ) -> str:
    """``SONAR_ALARM`` stripped and lower-cased: unset or empty is ``"on"``.
    Any other value is returned as it is, and :func:`from_keychain` treats a
    value it does not know as ``banner-only``: a typo must never push."""
    return (environ.get(ALARM_ENV) or "").strip().lower() or "on"


def from_keychain(build=None, log=None, read=None, banner=None, opener=None,
                  mode: str = "on") -> Notifier:
    """The agent's notifier: the banner plus ntfy with the Keychain topic.
    Blocks for at most :data:`KEYCHAIN_TIMEOUT_S`, once, at start, and logs
    one line saying whether pushes are on.

    ``mode`` is :func:`alarm_mode`'s value. Anything but ``"on"`` never reads
    the Keychain, so the engine never holds the topic; ``"off"`` also drops
    the banner."""
    if mode == "on":
        topic, why = (read or read_topic)()
        notifier = Notifier([banner or BannerChannel(), NtfyChannel(topic, opener, why)],
                            log=log, build=build)
        notifier.say("push alarms: ntfy configured" if topic
                     else f"push alarms: ntfy not configured ({why})")
        return notifier
    known = mode in ALARM_MODES
    if mode == "off":
        banner = BannerChannel(off_reason=OFF_REASON)
    notifier = Notifier([banner or BannerChannel(), NtfyChannel(None, opener, OFF_REASON)],
                        log=log, build=build)
    notifier.say(f"push alarms: off ({ALARM_ENV}={mode})" if known else
                 f"push alarms: off ({ALARM_ENV}={plain(mode, 40)!r} is not one of "
                 f"{', '.join(ALARM_MODES)}; treated as banner-only)")
    return notifier


# --------------------------------------------------------------------------- #
# The heartbeat
# --------------------------------------------------------------------------- #
def merge_json(path: Path, updates: dict) -> None:
    """Read, merge and write back a small JSON object. ``alarm.json`` holds
    keys for two writers' purposes, and an overwrite by one erased the other's.
    An unwritable file is skipped: the worst result is a duplicate notice."""
    data = paths.read_preferences(path)
    data.update(updates)
    try:
        paths.write_atomically(path, json.dumps(data))
    except OSError:
        pass


class Heartbeat:
    """Once a day at :data:`HEARTBEAT_AT` local time, "alive". If it does not
    arrive, that is the alarm: it is the only signal when the sender itself is
    dead, hung, asleep or logged out.

    The day is kept in ``alarm.json`` and written when the heartbeat is
    *queued*, not when it is delivered: a crash loop after 09:00 sends one,
    not one per restart, and a heartbeat lost to a failed push is not re-sent
    that day. The file is read once, here; after that only a send touches it.
    The day is a local date string, so a DST change or a clock set back cannot
    send twice on one date."""

    def __init__(self, path: Path, localtime=time.localtime, at=HEARTBEAT_AT):
        self.path, self.localtime, self.at = Path(path), localtime, tuple(at)
        self.day = paths.read_preferences(self.path).get("heartbeat_day")

    def _today(self, now: float) -> tuple[str, tuple[int, int]]:
        t = self.localtime(now)
        return f"{t.tm_year:04d}-{t.tm_mon:02d}-{t.tm_mday:02d}", (t.tm_hour, t.tm_min)

    def due(self, now: float) -> bool:
        day, hm = self._today(now)
        return hm >= self.at and self.day != day

    def mark(self, now: float) -> None:
        self.day = self._today(now)[0]
        merge_json(self.path, {"heartbeat_day": self.day, "heartbeat_at": now})


# --------------------------------------------------------------------------- #
# --test-alarm
# --------------------------------------------------------------------------- #
def test_alarm(argv=None, *, read=None, banner=None, opener=None, build=None,
               out=None, retry_after_s: float = NTFY_RETRY_AFTER_S) -> int:
    """``SONAR --test-alarm``: send one test alarm on each channel, now.

    Reads the Keychain topic and nothing else: no book, no health, no prices,
    and never ``SONAR_DATA`` (domain P3-3). Prints one line per channel and
    exits 0 only if the push was delivered. It runs in the caller's session,
    so it proves the topic and the phone, not the agent's Keychain access:
    the agent's startup line and its heartbeat prove that."""
    ap = argparse.ArgumentParser(prog="SONAR --test-alarm",
                                 description="Send one test alarm on each channel.")
    ap.add_argument("--test-alarm", action="store_true", help=argparse.SUPPRESS)
    ap.parse_known_args(argv or [])        # main.py passes the whole argv
    out = out or sys.stdout
    if build is None:
        from . import version
        build = version.info().get("version")
    topic, why = (read or read_topic)()
    ntfy = NtfyChannel(topic, opener, why)
    banner = banner or BannerChannel()
    states = {"banner": {"state": "ok" if banner.configured else banner.idle_state},
              "ntfy": {"state": "ok" if ntfy.configured else ntfy.idle_state}}
    title, body, priority = render(Event("test"), build, states)

    delivered = False
    if ntfy.configured:
        delivered = ntfy.send(title, body, priority)
        if not delivered:
            time.sleep(retry_after_s)
            delivered = ntfy.send(title, body, priority)
        line = "ok" if delivered else f"failing ({ntfy.why})"
    else:
        line = f"not configured ({ntfy.reason})"
    print(f"ntfy: {line}", file=out, flush=True)

    if banner.configured:
        line = "ok" if banner.send(title, body, priority) else f"failing ({banner.why})"
    else:
        line = banner.idle_state
    print(f"banner: {line}", file=out, flush=True)
    return 0 if delivered else 1


# Not a test: keep pytest from collecting it if it is ever imported into one.
test_alarm.__test__ = False
