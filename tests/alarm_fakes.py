"""Fakes and the allowlist check shared by tests/test_alarm.py and tests/test_health.py.

Nothing here touches a real Keychain, the network or ``osascript``: every
channel gets an injected ``run`` or ``opener``. Not a test module, so pytest
does not collect it.
"""

from __future__ import annotations

import re
import secrets
import subprocess
import threading
import urllib.error

from sonar import alarm

#: A fresh random topic per run, so a leak cannot match by accident.
TOPIC = secrets.token_hex(20)            # 40 characters
BUILD = "v2.340"

#: Everything a problem text or an exception could carry that must never leave
#: the Mac: a symbol, a price, a path, a URL, exception text.
NASTY = "AAPL $187.42 at /Users/as/x https://evil.example/?q=1 ValueError: secret"


class Resp:
    def __init__(self, status):
        self.status = status

    def getcode(self):
        return self.status

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class Opener:
    """A fake ntfy opener. Records every request and answers from a script:
    an int is a status, an exception is raised. The last answer repeats.
    ``block`` makes every call wait on that Event first (a hung connection)."""

    def __init__(self, *answers, block: threading.Event | None = None):
        self.answers = list(answers) or [200]
        self.requests: list[dict] = []
        self.block = block
        self.called = threading.Event()
        self._lock = threading.Lock()

    def open(self, req, timeout=None):
        with self._lock:
            self.requests.append({
                "url": req.full_url, "method": req.get_method(), "timeout": timeout,
                "headers": {k.lower(): v for k, v in req.header_items()},
                "body": req.data.decode("ascii")})
            answer = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        self.called.set()
        if self.block is not None:
            self.block.wait(30)
        if isinstance(answer, BaseException):
            raise answer
        return Resp(answer)


class Run:
    """A fake ``subprocess.run`` for ``osascript`` or ``security``: records the
    args; returns ``rc``/``stdout``/``stderr``, or raises ``raises``, or waits
    on ``block``."""

    def __init__(self, rc=0, stdout="", stderr="", raises=None,
                 block: threading.Event | None = None):
        self.rc, self.stdout, self.stderr = rc, stdout, stderr
        self.raises, self.block = raises, block
        self.calls: list[list[str]] = []
        self.called = threading.Event()
        self.returned = threading.Event()

    def __call__(self, args, **kw):
        self.calls.append(list(args))
        self.called.set()
        if self.block is not None:
            self.block.wait(30)
        self.returned.set()
        if self.raises is not None:
            raise self.raises
        return type("R", (), {"returncode": self.rc, "stdout": self.stdout,
                              "stderr": self.stderr})()


def timed_out(args, **kw):
    raise subprocess.TimeoutExpired(args, 10)


def http_error(code: int) -> urllib.error.HTTPError:
    """An HTTPError whose ``url`` and text carry the topic, as a real one would."""
    return urllib.error.HTTPError(alarm.NTFY_URL + TOPIC, code,
                                  f"failed {alarm.NTFY_URL + TOPIC}", {}, None)


def url_error() -> urllib.error.URLError:
    return urllib.error.URLError(f"cannot reach {alarm.NTFY_URL + TOPIC}")


def notifier(opener=None, banner_run=None, log=None, retry_after_s=0.0,
             topic=TOPIC, build=BUILD) -> alarm.Notifier:
    banner = alarm.BannerChannel(run=banner_run or Run(), platform="darwin")
    return alarm.Notifier([banner, alarm.NtfyChannel(topic, opener or Opener())],
                          log=log if log is not None else (lambda msg: None),
                          build=build, retry_after_s=retry_after_s)


# --------------------------------------------------------------------------- #
# The closed grammar a push must match (domain P1-1, P2-1, P3-A)
# --------------------------------------------------------------------------- #
_PHRASE = "|".join(re.escape(text) + (rf"(?: for at least \d+ {unit})?" if unit else "")
                   for text, unit in alarm.PHRASES.values())
_NOTICE = "|".join(re.escape(text) for _, text, _ in alarm.NOTICES.values() if text)
_KIND = "|".join(alarm.PHRASES)
_BUILD = r"build (?:v?[0-9][0-9A-Za-z.+-]{0,31}|unknown)"
_CHANNELS = (r"channels: banner (?:ok|failing|unavailable|unknown), "
             r"ntfy (?:ok|failing|not configured|unknown)")
GRAMMAR = re.compile(
    rf"(?:(?:{_PHRASE})(?:; (?:{_PHRASE}))*; {_BUILD}; {_CHANNELS}"
    rf"|(?:{_NOTICE}); {_BUILD}; {_CHANNELS}"
    rf"|SONAR \(paper\) alive, {_BUILD}; open problems: "
    rf"(?:none|(?:{_KIND})(?:, (?:{_KIND}))*); {_CHANNELS})")


def assert_allowlisted(title: str, body: str) -> None:
    """A push says only what the allowlist lets leave the Mac."""
    assert title.startswith("SONAR (paper) "), title
    assert body.isascii() and title.isascii()
    assert GRAMMAR.fullmatch(body), body
    for bad in ("$", "/", "http", "AAPL", "Error", "secret", "187", "evil", TOPIC):
        assert bad not in body and bad not in title, (bad, body)
    # The only colons are the two fixed labels (domain P3-A).
    assert ":" not in body.replace("channels:", "").replace("open problems:", ""), body
    assert set(re.findall(r"[A-Z]+", body)) <= {"SONAR"}, body
    # Every digit run is a duration or the build.
    rest = re.sub(r"for at least \d+ (?:min|h)", "", body)
    rest = re.sub(_BUILD, "", rest)
    assert not re.search(r"\d", rest), body
