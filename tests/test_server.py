"""The headless HTTP daemon.

`sonar/server.py` was 0% — never executed by a test — and it has just become
more load-bearing than it was: closing the window now quits, so the daemon is
the documented answer for uptime. A route that 500s or hands back the wrong
shape would take the headless path down with nothing watching.

These run a real `server.PaperServer` on 127.0.0.1 with an ephemeral port and
query it over a real socket. The alternative — faking `rfile`/`wfile` and
driving the handler by hand — tests the fake at least as much as the server.
The `loopback` fixture is the narrow, by-name opt-out of the suite's ban on
sockets; see `conftest.py` for why that ban exists.

`Live` is stubbed. What is under test is the routing and the JSON, not the
engine, which has its own suite.
"""

import json
import threading
import urllib.error
import urllib.request

import pytest

from sonar import server


class FakeMacro:
    def __init__(self, payload):
        self._payload = payload

    def get(self):
        return self

    def as_dict(self):
        return self._payload


class FakeLive:
    """Only the surface `Handler` touches."""

    def __init__(self):
        self.lock = threading.Lock()
        self.snapshot = {"status": "live", "price": 42.0}
        self.assets = {"generated": 123, "rows": [{"symbol": "BTC"}]}
        self.macro = FakeMacro({"regime": "transitional"})
        self.configured = []
        self.reads = []

    def config(self):
        return {"risk": "moderate", "horizon": "week"}

    def configure(self, risk, hz, protocol=None):
        self.configured.append((risk, hz, protocol))
        return {"risk": risk or "moderate", "horizon": hz or "week",
                "protocol": {"on": bool(protocol)}}

    def read(self, kind, ident):
        self.reads.append((kind, ident))
        return {"kind": kind, "id": ident, "text": "a read"}


@pytest.fixture
def daemon(loopback, monkeypatch):
    """A real server on an ephemeral port, torn down after the test."""
    live = FakeLive()
    monkeypatch.setattr(server.Handler, "live", live)
    # The production class, so its listen backlog is what is under test.
    srv = server.PaperServer(("127.0.0.1", 0), server.Handler)
    # serve_forever polls a shutdown flag every `poll_interval`, and the
    # default is half a second — paid once per teardown, which turned 21 tests
    # into eleven seconds of almost entirely waiting.
    thread = threading.Thread(target=srv.serve_forever,
                              kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    host, port = srv.server_address[:2]
    try:
        yield f"http://{host}:{port}", live
    finally:
        srv.shutdown()
        srv.server_close()
        thread.join(timeout=5)


def get(base, path):
    with urllib.request.urlopen(f"{base}{path}", timeout=5) as r:
        return r.status, r.headers, r.read()


def post(base, path, payload):
    body = json.dumps(payload).encode()
    req = urllib.request.Request(f"{base}{path}", data=body, method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as r:
        return r.status, json.loads(r.read())


# --------------------------------------------------------------------------- #
# The JSON API
# --------------------------------------------------------------------------- #
def test_state_serves_the_live_snapshot(daemon):
    base, live = daemon
    status, headers, body = get(base, "/api/state")
    assert status == 200
    assert headers["Content-Type"] == "application/json"
    assert json.loads(body) == live.snapshot


def test_assets_serves_the_screen(daemon):
    base, live = daemon
    assert json.loads(get(base, "/api/assets")[2]) == live.assets


def test_macro_serves_the_regime(daemon):
    base, _ = daemon
    assert json.loads(get(base, "/api/macro")[2])["regime"] == "transitional"


def test_config_round_trips(daemon):
    base, live = daemon
    assert json.loads(get(base, "/api/config")[2])["risk"] == "moderate"
    status, got = post(base, "/api/config",
                       {"risk": "aggressive", "horizon": "month"})
    assert status == 200 and got["risk"] == "aggressive"
    assert live.configured == [("aggressive", "month", None)]


def test_api_responses_are_never_cached(daemon):
    """A cached /api/state is a price that stops moving and says nothing."""
    base, _ = daemon
    assert get(base, "/api/state")[1]["Cache-Control"] == "no-store"


def test_the_content_length_matches_the_body(daemon):
    base, _ = daemon
    _, headers, body = get(base, "/api/state")
    assert int(headers["Content-Length"]) == len(body)


# --------------------------------------------------------------------------- #
# The LLM read, the one route that can cost money
# --------------------------------------------------------------------------- #
def test_a_read_is_forwarded_with_its_kind_and_id(daemon):
    base, live = daemon
    status, got = post(base, "/api/read", {"kind": "asset", "id": "BTC-USD"})
    assert status == 200 and got["kind"] == "asset"
    assert live.reads == [("asset", "BTC-USD")]


def test_an_unknown_read_kind_is_refused_before_it_reaches_the_model(daemon):
    """This is the route that spends money. An arbitrary `kind` from a request
    body must not get as far as the provider."""
    base, live = daemon
    with pytest.raises(urllib.error.HTTPError) as exc:
        post(base, "/api/read", {"kind": "../../etc/passwd", "id": "x"})
    assert exc.value.code == 400
    assert live.reads == [], "nothing should have reached Live.read"


def test_a_read_defaults_to_btc(daemon):
    base, live = daemon
    post(base, "/api/read", {})
    assert live.reads == [("btc", "")]


def _raw(base, path, data=b"", method="POST", headers=None):
    req = urllib.request.Request(f"{base}{path}", data=data, method=method,
                                 headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


JSON = {"Content-Type": "application/json"}


def test_a_malformed_body_is_refused_and_the_route_stays_up(daemon):
    base, live = daemon
    status, _ = _raw(base, "/api/config", b"{not json", headers=JSON)
    assert status == 400 and live.configured == []
    assert post(base, "/api/config", {})[0] == 200, "the route went down"


def test_a_body_with_no_content_length_is_treated_as_empty(daemon):
    base, live = daemon
    status, _ = _raw(base, "/api/config", b"", headers=JSON)
    assert status == 200 and live.configured == [(None, None, None)]


# --------------------------------------------------------------------------- #
# Only this machine's own requests (audit security P1-1)
# --------------------------------------------------------------------------- #
def test_a_cross_site_text_plain_write_is_refused(book_daemon):
    """What a web page can send without a preflight: no JSON content type."""
    base, live = book_daemon
    status, _ = _raw(base, "/api/trade", b'{"symbol":"AAA","direction":"LONG"}',
                     headers={"Content-Type": "text/plain"})
    assert status == 415 and live.trades == []


def test_a_write_from_a_foreign_origin_is_refused(book_daemon):
    base, live = book_daemon
    status, _ = _raw(base, "/api/close", b'{"id":"p1"}',
                     headers={**JSON, "Origin": "https://evil.example"})
    assert status == 403 and live.closes == []


def test_the_servers_own_origin_may_write(book_daemon):
    base, live = book_daemon
    status, _ = _raw(base, "/api/close", b'{"id":"p1"}', headers={**JSON, "Origin": base})
    assert status == 200 and live.closes == ["p1"]


@pytest.mark.parametrize("method,path", [("GET", "/api/state"), ("GET", "/"),
                                         ("POST", "/api/trade")])
def test_a_rebinding_host_is_refused_for_reads_and_writes(daemon, method, path):
    """A DNS-rebinding page reaches 127.0.0.1 under its own domain name."""
    base, live = daemon
    status, body = _raw(base, path, b"{}" if method == "POST" else None, method=method,
                        headers={**JSON, "Host": "evil.example:8787"})
    assert status == 403 and b"unknown host" in body


def test_an_oversized_or_non_object_body_is_refused(daemon):
    base, live = daemon
    assert _raw(base, "/api/config", b"[]", headers=JSON)[0] == 400
    big = b'{"x": "' + b"a" * (70 * 1024) + b'"}'
    assert _raw(base, "/api/config", big, headers=JSON)[0] == 413
    assert live.configured == []


def test_a_chunked_body_is_refused_rather_than_read_as_empty(daemon):
    base, live = daemon
    status, _ = _raw(base, "/api/config", None,
                     headers={**JSON, "Transfer-Encoding": "chunked"})
    assert status == 411 and live.configured == []


def test_responses_carry_the_hardening_headers(daemon):
    base, _ = daemon
    _status, headers, _ = get(base, "/")
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"


def test_the_daemon_refuses_to_listen_off_the_machine(monkeypatch):
    def started(*a, **k):
        raise AssertionError("started an engine for a non-loopback host")
    monkeypatch.setattr(server, "Live", started)     # fail fast, never serve
    with pytest.raises(SystemExit, match="loopback only"):
        server.main(host="0.0.0.0", port=0)


# --------------------------------------------------------------------------- #
# Pages
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("path", ["/", "/index.html"])
def test_the_app_page_is_served(daemon, path):
    base, _ = daemon
    status, headers, body = get(base, path)
    assert status == 200
    assert "text/html" in headers["Content-Type"]
    assert b"<" in body


@pytest.mark.parametrize("path", ["/docs", "/docs/", "/docs.html"])
def test_every_docs_url_reaches_the_manual(daemon, path):
    """Three spellings are wired on purpose; a reader typing /docs should not
    get a 404."""
    base, _ = daemon
    status, _, body = get(base, path)
    assert status == 200
    # Assert on something only the manual has. "SONAR" appears on both pages,
    # so checking for it passes happily when /docs is wired to index.html —
    # which a mutation check caught this test doing.
    assert b'id="learn"' in body, "this is the app page, not the manual"


def test_an_unknown_path_is_a_clean_404(daemon):
    base, _ = daemon
    for path in ("/nope", "/api/nope", "/static/../secret"):
        with pytest.raises(urllib.error.HTTPError) as exc:
            get(base, path)
        assert exc.value.code == 404


def test_an_unknown_post_is_a_clean_404(daemon):
    base, _ = daemon
    with pytest.raises(urllib.error.HTTPError) as exc:
        post(base, "/api/nope", {})
    assert exc.value.code == 404


def test_the_server_does_not_serve_arbitrary_files(daemon):
    """The page table is a fixed allowlist, not a path join — so a traversal
    has nothing to traverse."""
    base, _ = daemon
    for path in ("/../sonar/core.py", "/state.json", "/.env"):
        with pytest.raises(urllib.error.HTTPError) as exc:
            get(base, path)
        assert exc.value.code == 404


# --------------------------------------------------------------------------- #
# Concurrency — the daemon serves a browser and a poll thread at once
# --------------------------------------------------------------------------- #
def test_concurrent_requests_are_all_answered(daemon):
    base, _ = daemon
    results = []

    def hit():
        try:
            results.append(get(base, "/api/state")[0])
        except Exception as exc:                       # noqa: BLE001
            results.append(exc)

    threads = [threading.Thread(target=hit) for _ in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    assert results == [200] * 12


def test_the_app_page_is_not_the_manual(daemon):
    """The other half of the pair — so neither route can quietly become the
    other."""
    base, _ = daemon
    assert b'id="learn"' not in get(base, "/")[2]


# --------------------------------------------------------------------------- #
# main() — what the launchd agent actually runs
# --------------------------------------------------------------------------- #
def test_main_wires_the_engine_to_the_handler_and_serves(monkeypatch, tmp_path):
    """`main` is the entry point for `--headless` and the launchd agent, so a
    wiring mistake here is invisible until a machine is left running it."""
    monkeypatch.setattr("sonar.paths.user_data_base", lambda: tmp_path)
    started, served = [], []

    class FakeServer:
        def __init__(self, addr, handler):
            served.append(addr)
            self.handler = handler

        def serve_forever(self):
            served.append("serving")

    class StubLive:
        def __init__(self, **kw):
            self.risk = type("R", (), {"name": "moderate"})()
            self.horizon = type("H", (), {"name": "week"})()
            self.read_only = False

        def run(self, role, url=None):
            started.append(role)

    monkeypatch.setattr(server, "Live", StubLive)
    monkeypatch.setattr(server, "PaperServer", FakeServer)
    monkeypatch.setattr(server.time, "sleep", lambda s: None)
    monkeypatch.setattr(server.Handler, "live", None)

    server.main(host="127.0.0.1", port=0, role="test-role")

    assert isinstance(server.Handler.live, StubLive), "the handler has no engine"
    assert served[0] == ("127.0.0.1", 0)
    assert "serving" in served
    assert started == ["test-role"], "the engine loop never started"


def test_main_survives_a_keyboard_interrupt(monkeypatch, tmp_path):
    """Ctrl-C on a daemon should print and exit, not dump a traceback."""
    monkeypatch.setattr("sonar.paths.user_data_base", lambda: tmp_path)

    class FakeServer:
        def __init__(self, *a):
            pass

        def serve_forever(self):
            raise KeyboardInterrupt

    class StubLive:
        def __init__(self, **kw):
            self.risk = type("R", (), {"name": "moderate"})()
            self.horizon = type("H", (), {"name": "week"})()
            self.read_only = False

        def run(self, role, url=None):
            pass

    monkeypatch.setattr(server, "Live", StubLive)
    monkeypatch.setattr(server, "PaperServer", FakeServer)
    monkeypatch.setattr(server.time, "sleep", lambda s: None)
    server.main(port=0)          # must not raise


def test_a_second_daemon_reports_read_only_rather_than_double_counting(
        monkeypatch, tmp_path, capsys):
    """Two engines settling the same hour into one state file would double-count
    the portfolio silently. The lock makes the second one wait; this is the
    line that tells the operator."""
    monkeypatch.setattr("sonar.paths.user_data_base", lambda: tmp_path)

    class FakeServer:
        def __init__(self, *a):
            pass

        def serve_forever(self):
            pass

    class StubLive:
        def __init__(self, **kw):
            self.risk = type("R", (), {"name": "moderate"})()
            self.horizon = type("H", (), {"name": "week"})()
            self.read_only = True
            self.conflict = "another engine holds the lock"

        def run(self, role, url=None):
            pass

    monkeypatch.setattr(server, "Live", StubLive)
    monkeypatch.setattr(server, "PaperServer", FakeServer)
    monkeypatch.setattr(server.time, "sleep", lambda s: None)
    server.main(port=0)
    assert "WAITING" in capsys.readouterr().out


def test_the_static_dir_the_server_points_at_actually_exists():
    """A frozen bundle moves `static/`; this is the check that would catch it
    before every page 500s."""
    assert server.STATIC.is_dir()
    assert (server.STATIC / "index.html").exists()
    assert (server.STATIC / "docs.html").exists()


# --------------------------------------------------------------------------- #
# What a following window reads and writes (core.Live._wait_for_lock)
# --------------------------------------------------------------------------- #
class FakeBookLive(FakeLive):
    def __init__(self):
        super().__init__()
        self.positions = {"stats": {"n_open": 1}, "open": [{"id": "p1"}],
                          "closed": [], "equity": []}
        self.calibration = {"verdict": "unproven"}
        self.protocol_on = True
        self.alerts = [{"symbol": "AAA"}]
        self.inst = {"n": 0}
        self.trades, self.closes = [], []

    def trade(self, symbol, direction):
        self.trades.append((symbol, direction))
        return {"ok": True, "message": f"opened {direction} {symbol}", "position": {}}

    def close_position(self, pos_id):
        self.closes.append(pos_id)
        return {"ok": True, "message": "closed", "position": {}}


@pytest.fixture
def book_daemon(loopback, monkeypatch):
    live = FakeBookLive()
    monkeypatch.setattr(server.Handler, "live", live)
    srv = server.PaperServer(("127.0.0.1", 0), server.Handler)
    thread = threading.Thread(target=srv.serve_forever,
                              kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    host, port = srv.server_address[:2]
    try:
        yield f"http://{host}:{port}", live
    finally:
        srv.shutdown()
        srv.server_close()
        thread.join(timeout=5)


def test_the_book_is_served_with_its_grading_and_switch(book_daemon):
    base, live = book_daemon
    got = json.loads(get(base, "/api/book")[2])
    assert got == {"positions": live.positions, "calibration": live.calibration,
                   "protocol_on": True}


def test_the_wire_serves_alerts_and_institutions(book_daemon):
    base, live = book_daemon
    assert json.loads(get(base, "/api/wire")[2]) == {"alerts": live.alerts,
                                                     "inst": live.inst}


def test_a_trade_is_forwarded_to_the_book(book_daemon):
    base, live = book_daemon
    status, got = post(base, "/api/trade", {"symbol": "AAA", "direction": "long"})
    assert status == 200 and got["ok"]
    assert live.trades == [("AAA", "LONG")]


def test_a_trade_with_no_direction_never_reaches_the_book(book_daemon):
    base, live = book_daemon
    with pytest.raises(urllib.error.HTTPError) as exc:
        post(base, "/api/trade", {"symbol": "AAA", "direction": "sideways"})
    assert exc.value.code == 400
    assert live.trades == []


def test_a_close_is_forwarded_to_the_book(book_daemon):
    base, live = book_daemon
    status, got = post(base, "/api/close", {"id": "p1"})
    assert status == 200 and got["ok"]
    assert live.closes == ["p1"]


def test_on_a_default_port_the_bare_host_is_its_own():
    """Clients leave :80 out of the Host header; requiring it locked them out."""
    class Fake:
        server = type("S", (), {"server_address": ("127.0.0.1", 80)})()
    assert {"127.0.0.1", "localhost", "127.0.0.1:80"} <= server.Handler._own_hosts(Fake())

    class Other:
        server = type("S", (), {"server_address": ("127.0.0.1", 8787)})()
    assert "localhost" not in server.Handler._own_hosts(Other())
