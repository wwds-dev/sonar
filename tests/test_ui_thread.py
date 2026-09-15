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
