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


def test_a_malformed_body_does_not_take_the_route_down(daemon):
    base, live = daemon
    req = urllib.request.Request(f"{base}/api/config", data=b"{not json",
                                 method="POST")
    with urllib.request.urlopen(req, timeout=5) as r:
        assert r.status == 200
    assert live.configured == [(None, None, None)], "an unreadable body reads as empty"


def test_a_body_with_no_content_length_is_treated_as_empty(daemon):
    base, live = daemon
    req = urllib.request.Request(f"{base}/api/config", data=b"", method="POST")
    with urllib.request.urlopen(req, timeout=5) as r:
        assert r.status == 200
    assert live.configured == [(None, None, None)]


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

        def run(self, role):
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

        def run(self, role):
            pass

    monkeypatch.setattr(server, "Live", StubLive)
    monkeypatch.setattr(server, "PaperServer", FakeServer)
    monkeypatch.setattr(server.time, "sleep", lambda s: None)
    server.main(port=0)          # must not raise


def test_a_second_daemon_reports_read_only_rather_than_double_counting(
        monkeypatch, tmp_path, capsys):
    """Two engines settling the same hour into one state file would double-count
    the portfolio silently. The lock makes the second one read-only; this is the
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

        def run(self, role):
            pass

    monkeypatch.setattr(server, "Live", StubLive)
    monkeypatch.setattr(server, "PaperServer", FakeServer)
    monkeypatch.setattr(server.time, "sleep", lambda s: None)
    server.main(port=0)
    assert "READ-ONLY" in capsys.readouterr().out


def test_the_static_dir_the_server_points_at_actually_exists():
    """A frozen bundle moves `static/`; this is the check that would catch it
    before every page 500s."""
    assert server.STATIC.is_dir()
    assert (server.STATIC / "index.html").exists()
    assert (server.STATIC / "docs.html").exists()
