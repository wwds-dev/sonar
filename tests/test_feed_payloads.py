"""The newswire and calendar parsers, fed recorded-shape payloads.

`news.py` and `events.py` read 24 RSS/Atom feeds and two Nasdaq JSON
endpoints that SONAR does not control. Until now only their pure helpers were
tested (38% and 47% covered); the code that turns a response into headlines
and calendar rows ran only against the live internet. These tests serve it
payloads of the shapes those hosts send — and of the shapes they send when
something is wrong: truncated, empty, a captive portal's HTML, a 200 with no
rows — by replacing `urlopen` where each module calls it. Nothing here
touches the network.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import io
import json
import time

import pytest

from sonar import events, news

RSS = b"""<?xml version="1.0"?>
<rss version="2.0"><channel><title>Wire</title>
<item><title>Central bank holds rates steady - Reuters</title>
  <link>https://example.org/a</link><pubDate>Fri, 09 Oct 2026 14:00:00 GMT</pubDate></item>
<item><title>Bitcoin miners expand capacity</title>
  <link>https://example.org/b</link><pubDate>not a date</pubDate></item>
<item><title></title><link>https://example.org/empty</link></item>
</channel></rss>"""

ATOM = b"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"><title>Atom wire</title>
<entry><title>Semiconductor exports fall sharply</title>
  <link href="https://example.org/c"/><published>2026-10-09T12:30:00Z</published></entry>
<entry><title>Central bank holds rates steady</title>
  <link href="https://example.org/d"/><updated>2026-10-09T13:00:00+02:00</updated></entry>
</feed>"""

CAPTIVE_PORTAL = b"<html><head><title>Sign in to Wi-Fi</title></head><body>...</body></html>"
TRUNCATED = RSS[: len(RSS) // 2]


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _serve(monkeypatch, module, table: dict[str, object]):
    """Answer each URL containing a key with that key's body; raise for the rest.

    A body that is an exception instance is raised instead, the way a refused
    connection or a timeout arrives."""
    calls: list[str] = []

    def urlopen(req, timeout=None):
        url = getattr(req, "full_url", req)
        calls.append(url)
        for key, body in table.items():
            if key in url:
                if isinstance(body, BaseException):
                    raise body
                return _Resp(body if isinstance(body, bytes) else json.dumps(body).encode())
        raise OSError(f"no recorded payload for {url}")

    monkeypatch.setattr(module.urllib.request, "urlopen", urlopen)
    return calls


# --------------------------------------------------------------------------- #
# news — one feed
# --------------------------------------------------------------------------- #
def _feed(url: str = "https://feed.test/rss") -> news.Feed:
    """A real registry entry pointed somewhere recorded."""
    return dataclasses.replace(next(iter(news.FEEDS.values())), url=url)


def test_an_rss_feed_becomes_headlines(monkeypatch):
    _serve(monkeypatch, news, {"feed.test": RSS})
    heads = news.NewsCache()._one("Wire", _feed())
    titles = [h.title for h in heads]
    assert titles == ["Central bank holds rates steady", "Bitcoin miners expand capacity"], \
        "the ' - Publisher' suffix is stripped and an empty title is skipped"
    first, second = heads
    assert first.link == "https://example.org/a"
    assert first.ts == int(dt.datetime(2026, 10, 9, 14, tzinfo=dt.timezone.utc).timestamp())
    assert second.ts == 0 and second.dated is False, "an unparseable date is undated, not now"
    assert "bitcoin" in second._tokens


def test_an_atom_feed_becomes_headlines(monkeypatch):
    _serve(monkeypatch, news, {"feed.test": ATOM})
    heads = news.NewsCache()._one("Atom wire", _feed())
    assert [h.link for h in heads] == ["https://example.org/c", "https://example.org/d"]
    assert heads[0].ts == int(dt.datetime(2026, 10, 9, 12, 30, tzinfo=dt.timezone.utc).timestamp())
    # <updated> stands in when there is no <published>, offset honoured.
    assert heads[1].ts == int(dt.datetime(2026, 10, 9, 11, tzinfo=dt.timezone.utc).timestamp())


@pytest.mark.parametrize("body", [TRUNCATED, CAPTIVE_PORTAL, b"", OSError("refused"),
                                  TimeoutError("timed out")],
                         ids=["truncated", "captive portal", "empty", "refused", "timeout"])
def test_a_broken_feed_yields_nothing_rather_than_raising(monkeypatch, body):
    _serve(monkeypatch, news, {"feed.test": body})
    assert news.NewsCache()._one("Wire", _feed()) == []


def test_a_feed_is_read_to_forty_items_at_most(monkeypatch):
    items = b"".join(b"<item><title>Story %d about refinery output</title></item>" % i
                     for i in range(60))
    _serve(monkeypatch, news, {"feed.test": b"<rss><channel>" + items + b"</channel></rss>"})
    assert len(news.NewsCache()._one("Wire", _feed())) == 40


# --------------------------------------------------------------------------- #
# news — the whole refresh
# --------------------------------------------------------------------------- #
def test_a_refresh_keeps_the_first_feed_to_carry_a_story(monkeypatch):
    """Feeds are fetched concurrently but deduplicated in FEEDS order, so the
    source a story is credited to does not depend on which host was fastest."""
    names = list(news.FEEDS)
    monkeypatch.setattr(news, "FEEDS", {names[0]: _feed("https://one.test/"),
                                        names[1]: _feed("https://two.test/")})
    _serve(monkeypatch, news, {"one.test": RSS, "two.test": ATOM})
    cache = news.NewsCache()
    heads = cache.headlines()
    by_title = {h.title: h.source for h in heads}
    assert by_title["Central bank holds rates steady"] == names[0]
    assert sum(1 for h in heads if h.title == "Central bank holds rates steady") == 1
    assert len(heads) == 3


def test_a_refresh_that_gets_nothing_keeps_the_last_good_set(monkeypatch):
    names = list(news.FEEDS)
    monkeypatch.setattr(news, "FEEDS", {names[0]: _feed("https://one.test/")})
    _serve(monkeypatch, news, {"one.test": RSS})
    cache = news.NewsCache()
    good = cache.headlines()
    assert good
    _serve(monkeypatch, news, {"one.test": OSError("offline")})
    cache._at = 0.0
    assert cache.headlines() == good, "going offline must not blank the Wire"


def test_an_empty_cache_retries_on_the_next_call_whatever_the_ttl(monkeypatch):
    names = list(news.FEEDS)
    monkeypatch.setattr(news, "FEEDS", {names[0]: _feed("https://one.test/")})
    calls = _serve(monkeypatch, news, {"one.test": OSError("offline")})
    cache = news.NewsCache(ttl=3600)
    assert cache.headlines() == []
    _serve(monkeypatch, news, {"one.test": RSS})
    assert cache.headlines(), "back online, the next call fetches again"
    assert calls


# --------------------------------------------------------------------------- #
# news — matching a story to an instrument
# --------------------------------------------------------------------------- #
def _heads(*titles, age_h=1.0):
    now = time.time()
    return [news.Headline(title=t, link="", source="Wire", category="markets",
                          ts=int(now - age_h * 3600),
                          _tokens={w.lower() for w in news._WORD.findall(t)},
                          origin="US", state=False) for t in titles]


def test_a_shared_month_or_weekday_is_not_a_match():
    kw = news.keywords("Will Nvidia close above $150 on Friday in October?")
    assert "friday" not in kw and "october" not in kw and "150" not in kw
    assert news.match(_heads("Friday trading in October was quiet"), kw) == []


def test_a_distinctive_pair_matches_and_a_lone_common_word_does_not():
    kw = news.keywords("Nvidia semiconductor exports")
    hits = news.match(_heads("Nvidia semiconductor sales jump",
                             "Exports rise"), kw)
    assert [h.title for h in hits] == ["Nvidia semiconductor sales jump"]


def test_bitcoin_matches_on_the_alias_alone():
    kw = news.keywords("Bitcoin above 90k?")
    assert {"bitcoin", "btc", "crypto"} <= kw
    assert len(news.match(_heads("Crypto funds see inflows"), kw)) == 1


def test_coverage_weights_fresh_news_over_old_and_undated():
    fresh = news.news_signal(_heads("a", "b", age_h=1))[0]
    old = news.news_signal(_heads("a", "b", age_h=48))[0]
    undated = news.news_signal([news.Headline(**{**vars(h), "ts": 0})
                                for h in _heads("a", "b")])[0]
    assert fresh == 1.0 and old == pytest.approx(0.2) and undated == pytest.approx(0.3)


# --------------------------------------------------------------------------- #
# events — the earnings and IPO calendars
# --------------------------------------------------------------------------- #
def _earnings_day(*rows):
    return {"data": {"rows": [dict(r) for r in rows]}}


def test_the_calendar_keeps_each_symbols_soonest_report(monkeypatch):
    today = dt.date.today()
    workdays = [today + dt.timedelta(days=i) for i in range(14)
                if (today + dt.timedelta(days=i)).weekday() < 5]
    first, later = workdays[0], workdays[1]
    table = {f"date={first.isoformat()}": _earnings_day(
                 {"symbol": "aapl ", "time": "time-pre-market"},
                 {"symbol": "", "time": "x"}),
             f"date={later.isoformat()}": _earnings_day(
                 {"symbol": "AAPL", "time": "time-after-hours"},
                 {"symbol": "MSFT", "time": "time-after-hours"}),
             "ipo/calendar": {"data": {
                 "upcoming": {"rows": [{"proposedTickerSymbol": "NEWC ",
                                        "companyName": "New Co", "expectedPriceDate": "10/20/2026",
                                        "proposedSharePrice": "14.00-16.00",
                                        "proposedExchange": "NASDAQ"}]},
                 "priced": {"rows": []}, "filed": None}}}
    calls = _serve(monkeypatch, events, table)
    cache = events.EventsCache()
    cache.refresh()
    aapl = cache.earnings_for("aapl")
    assert aapl.date == first.isoformat() and aapl.when == "pre-market"
    assert cache.earnings_for("MSFT").when == "after-hours"
    assert cache.earnings_for("MSFT").days_away == (later - today).days
    assert [x.symbol for x in cache.listings()] == ["NEWC"]
    assert all(dt.date.fromisoformat(u.split("date=")[1]).weekday() < 5
               for u in calls if "earnings" in u), "no request for a weekend day"


def test_an_offline_calendar_is_retried_soon_not_a_ttl_later(monkeypatch):
    """It used to stamp a refresh that got nothing as fresh: started offline,
    the Wire showed no calendar for six hours after the network came back."""
    _serve(monkeypatch, events, {})                     # every request refused
    cache = events.EventsCache()
    cache.refresh()
    assert cache.cached_payload()["n_earnings"] == 0
    assert cache.cached_payload()["generated"] == 0, "nothing was fetched, so nothing is dated"
    later = time.time() + events.RETRY_AFTER_FAILURE_S + 1
    monkeypatch.setattr(events.time, "time", lambda: later)
    asked = []
    monkeypatch.setattr(events.EventsCache, "refresh", lambda self, *a, **k: asked.append(1))
    cache.payload()
    assert asked, "still offline-stale ten minutes on: it must try again"


def test_a_good_calendar_is_not_refetched_inside_its_ttl(monkeypatch):
    today = dt.date.today()
    day = next(today + dt.timedelta(days=i) for i in range(7)
               if (today + dt.timedelta(days=i)).weekday() < 5)
    _serve(monkeypatch, events, {f"date={day.isoformat()}": _earnings_day(
        {"symbol": "AAPL", "time": "time-pre-market"})})
    cache = events.EventsCache()
    cache.refresh()
    assert cache.cached_payload()["generated"] > 0
    asked = []
    monkeypatch.setattr(events.EventsCache, "refresh", lambda self, *a, **k: asked.append(1))
    cache.payload()
    assert asked == []


@pytest.mark.parametrize("body", [{"data": None}, {"data": {"rows": None}}, {},
                                  b"<html>captive</html>", b""],
                         ids=["no data", "no rows", "empty object", "html", "empty"])
def test_a_malformed_calendar_day_is_skipped_not_raised(monkeypatch, body):
    _serve(monkeypatch, events, {"earnings": body, "ipo/calendar": body})
    cache = events.EventsCache()
    cache.refresh()
    assert cache.cached_payload()["n_earnings"] == 0
    assert cache.cached_payload()["listings"] == []


@pytest.mark.parametrize("days,label", [(0, "earnings today (pre-market)"),
                                        (1, "earnings tomorrow (pre-market)"),
                                        (5, "earnings in 5d")])
def test_an_earnings_label_reads_as_a_date_never_a_view(days, label):
    e = events.Earnings("AAPL", "2026-10-10", "pre-market", days)
    assert e.label == label
