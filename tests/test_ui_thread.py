"""Nothing the UI thread touches may go to the network.

The bug: `_refresh_wire()` read `news.headlines()` and `events.payload()`, both
of which fetch when their cache ages out. News ages out every eight minutes and
a refresh is twenty-four HTTP GETs at a ten-second timeout, eight at a time — up
to half a minute. Whichever thread reached the expired cache first did that
work, so roughly every eight minutes the *UI* thread might. When it did, the
event loop stopped: the window went blank white and ignored the close button,
while the process sat at 0.4% CPU looking alive.

Sampling a frozen SONAR showed exactly that — the main thread a hundred frames
deep inside a Qt slot with OpenSSL on the stack, which is a socket, on the
thread that is supposed to be painting.

So the cache-only accessors exist, and these tests hold the line: they must
never fetch, however stale they are.
"""

import time

import pytest

from sonar.events import EventsCache
from sonar.news import NewsCache


@pytest.fixture
def never_fetches(monkeypatch):
    """Record any attempt to go out to the network, rather than blocking on it."""
    attempts = []
    monkeypatch.setattr(NewsCache, "_refresh",
                        lambda self: attempts.append("news"))
    monkeypatch.setattr(EventsCache, "refresh",
                        lambda self, *a, **k: attempts.append("events"))
    return attempts


def _stale(cache):
    """Age the cache out so the fetching accessors definitely would fetch."""
    cache._at = 0.0
    return cache


# --------------------------------------------------------------------------- #
# The cache-only reads
# --------------------------------------------------------------------------- #
def test_cached_headlines_do_not_fetch_however_stale(never_fetches):
    assert _stale(NewsCache()).cached() == []
    assert never_fetches == []


def test_cached_payload_does_not_fetch_however_stale(never_fetches):
    payload = _stale(EventsCache()).cached_payload()
    assert payload["n_earnings"] == 0
    assert never_fetches == []


def test_the_cached_payload_is_shaped_like_the_fetching_one(never_fetches):
    cache = EventsCache()
    cache._at = time.time()          # fresh, so payload() will not fetch either
    assert cache.payload().keys() == cache.cached_payload().keys()
    assert never_fetches == []


def test_cached_headlines_are_a_copy_not_the_live_list():
    """A caller mutating what it got back must not corrupt the cache."""
    cache = NewsCache()
    got = cache.cached()
    got.append("not a headline")
    assert cache.cached() == []


# --------------------------------------------------------------------------- #
# The fetching reads still fetch — this is a split, not a removal
# --------------------------------------------------------------------------- #
def test_headlines_still_refreshes_when_it_is_stale(never_fetches):
    _stale(NewsCache()).headlines()
    assert never_fetches == ["news"]


def test_payload_still_refreshes_when_it_is_stale(never_fetches):
    _stale(EventsCache()).payload()
    assert never_fetches == ["events"]


def test_a_fresh_cache_is_left_alone(never_fetches):
    cache = NewsCache()
    cache._at = time.time()
    cache._headlines = ["something"]
    cache.headlines()
    assert never_fetches == []


# --------------------------------------------------------------------------- #
# The poll thread is the one that does the work
# --------------------------------------------------------------------------- #
def test_the_background_scan_warms_both_caches(monkeypatch, tmp_path):
    """`_rescan` runs on the poll thread and is what keeps the UI's caches
    full. It used to warm news and not the calendar, which left the first Wire
    render after six hours doing the calendar fetch on the UI thread."""
    monkeypatch.setattr("sonar.paths.user_data_base", lambda: tmp_path)
    warmed = []
    monkeypatch.setattr(NewsCache, "headlines",
                        lambda self: warmed.append("news") or [])
    monkeypatch.setattr(EventsCache, "payload",
                        lambda self: warmed.append("events") or {})

    from sonar.core import Live
    live = Live()
    try:
        live._rescan()
    except Exception:
        pass                 # the screen itself needs data we have not stubbed
    assert "news" in warmed
    assert "events" in warmed, "the calendar is still not warmed in the background"


def test_the_network_ban_still_holds_for_tests_that_did_not_ask(monkeypatch):
    """`tests/test_server.py` opts back into sockets with the `loopback`
    fixture, so this checks the ban is still the default for everyone else."""
    import urllib.request
    with pytest.raises(OSError):
        urllib.request.urlopen("http://example.invalid/", timeout=1)


# --------------------------------------------------------------------------- #
# The same freeze, reached through a lock instead of a socket
# --------------------------------------------------------------------------- #
def test_the_institutions_refresh_does_not_hold_the_ui_lock(monkeypatch):
    """Reported 2026-09-22 as a close button that stopped reacting.

    `MainWindow.refresh()` takes `live.lock` every second, and `_rescan()` held
    that same lock across `institutions.payload()` — which goes to the network
    for four RSS feeds at a 12s timeout each whenever its fifteen-minute cache
    expires. Nothing on the UI thread fetched, exactly as the rule says; the UI
    thread blocked on a mutex held by a thread that was fetching, which is the
    same dead event loop. It showed up as a window that went blank, ignored the
    close button, and came back a few seconds later.
    """
    from types import SimpleNamespace

    from sonar.core import Live

    live = Live()
    held = []

    def payload():
        held.append(live.lock.locked())
        return {"pressure": None}

    monkeypatch.setattr(live, "institutions", SimpleNamespace(payload=payload))
    monkeypatch.setattr(live, "news", SimpleNamespace(headlines=lambda: []))
    monkeypatch.setattr(live, "events", SimpleNamespace(payload=lambda: {}))
    monkeypatch.setattr(live, "asset_scanner",
                        SimpleNamespace(payload=lambda *a, **k: {"assets": []}))

    live._rescan()

    assert held == [False], "the UI's lock was held across the institutions fetch"
    assert live.inst == {"pressure": None}, "the payload still has to land"


def test_nothing_that_fetches_is_called_inside_a_lock():
    """By AST, because the next one will look as innocent as this one did.

    A fetch inside a lock the UI thread waits on is indistinguishable, from the
    user's side, from a fetch on the UI thread. Compute first, then take the
    lock for the assignment.
    """
    import ast
    import pathlib

    fetchers = {
        "institutions": {"payload"},
        "events": {"payload", "refresh"},
        "news": {"headlines", "refresh"},
        "asset_scanner": {"payload"},
        "reader": {"read"},
    }
    root = pathlib.Path(__file__).resolve().parents[1]
    offenders = []
    for path in (root / "sonar" / "core.py", root / "ui" / "app.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.With):
                continue
            if not any(isinstance(item.context_expr, ast.Attribute)
                       and item.context_expr.attr == "lock"
                       for item in node.items):
                continue
            for inner in ast.walk(node):
                if not (isinstance(inner, ast.Call)
                        and isinstance(inner.func, ast.Attribute)
                        and isinstance(inner.func.value, ast.Attribute)):
                    continue
                owner = inner.func.value.attr
                if inner.func.attr in fetchers.get(owner, ()):
                    offenders.append(
                        f"{path.name}:{inner.lineno} .{owner}.{inner.func.attr}()")
    assert not offenders, "a fetch is held inside a lock: " + ", ".join(offenders)
