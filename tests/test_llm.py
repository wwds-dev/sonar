"""What a user sees when the model refuses, truncates, garbles or is unreachable.

``LLMReader.read`` turns every way a call can go wrong into an ``LLMRead`` with
``error`` set and nothing else filled in. The panel shows that error instead of a
read, so a half-answer from the model never reaches the screen looking like a
whole one. Before these tests only ``available()`` was ever patched; ``read()``
after the SDK import had never run in the suite (closing QA review, M3/M8).

The ``anthropic`` package is optional and not installed in CI, so a stand-in
module is put in ``sys.modules``. Its exception classes keep the SDK's shape:
``RateLimitError`` is an ``APIStatusError``, so the order of the ``except``
clauses in ``read()`` is what decides which message a 429 gets. No network.
"""

from __future__ import annotations

import json
import sys
import types
from types import SimpleNamespace

import pytest

from sonar import llm

GOOD = {"direction": "UP", "conviction": 72, "summary": "Momentum and odds agree.",
        "catalysts": ["ETF inflows"], "risks": ["Fed surprise"]}


class _APIError(Exception):
    def __init__(self, message: str = "") -> None:
        super().__init__(message)
        self.message = message


class _APIStatusError(_APIError):
    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


def _sdk_message(code: int, kind: str, text: str) -> str:
    """The SDK's own ``message``: status code plus the raw error body
    (anthropic 1.13 ``_base_client.py`` ``_make_status_error_from_response``)."""
    return f"Error code: {code} - " + str({"type": "error", "error": {"type": kind, "message": text}})


class _RateLimitError(_APIStatusError):
    def __init__(self, message: str = _sdk_message(429, "rate_limit_error", "slow down")) -> None:
        super().__init__(message, 429)


def _status(code: int, kind: str = "api_error", text: str = "boom") -> _APIStatusError:
    return _APIStatusError(_sdk_message(code, kind, text), code)


class _APIConnectionError(_APIError):
    pass


class _APITimeoutError(_APIConnectionError):
    """The SDK's timeout is a kind of connection error."""


class _Messages:
    def __init__(self, sdk) -> None:
        self._sdk = sdk

    def create(self, **kwargs):
        self._sdk.calls.append(kwargs)
        if isinstance(self._sdk.outcome, BaseException):
            raise self._sdk.outcome
        return self._sdk.outcome


def _fake_sdk() -> types.ModuleType:
    sdk = types.ModuleType("anthropic")
    sdk.APIError = _APIError
    sdk.APIStatusError = _APIStatusError
    sdk.RateLimitError = _RateLimitError
    sdk.APIConnectionError = _APIConnectionError
    sdk.APITimeoutError = _APITimeoutError
    sdk.calls = []
    sdk.clients = []
    sdk.outcome = None

    class Anthropic:
        def __init__(self, timeout=None) -> None:
            sdk.clients.append(timeout)
            self.messages = _Messages(sdk)

    sdk.Anthropic = Anthropic
    return sdk


def _response(stop_reason: str = "end_turn", text: str | None = None,
              blocks: list | None = None, category: str | None = None):
    if blocks is None:
        blocks = [SimpleNamespace(type="text", text=json.dumps(GOOD) if text is None else text)]
    details = SimpleNamespace(category=category) if category is not None else None
    return SimpleNamespace(stop_reason=stop_reason, content=blocks, stop_details=details)


@pytest.fixture
def sdk(monkeypatch):
    fake = _fake_sdk()
    monkeypatch.setitem(sys.modules, "anthropic", fake)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
    return fake


def _read(**kw):
    return llm.LLMReader().read(
        "BTC", "crypto", {"price": 64000.5, "name": "Bitcoin"},
        headlines=[{"title": "ETF flows rise", "source": "Wire", "age_h": 2}], **kw)


def _shows_nothing(read: llm.LLMRead) -> None:
    """An error read carries no direction, conviction or prose to display."""
    assert read.direction == "UNCLEAR"
    assert read.conviction == 0
    assert read.summary == "" and read.catalysts == [] and read.risks == []
    assert read.calibrated is False


# --- the read that works ------------------------------------------------------

def test_a_clean_response_becomes_the_read(sdk):
    sdk.outcome = _response()
    read = _read()
    assert read.error is None
    assert (read.direction, read.conviction) == ("UP", 72)
    assert read.summary == "Momentum and odds agree."
    assert read.catalysts == ["ETF inflows"] and read.risks == ["Fed surprise"]
    assert read.calibrated is False, "an LLM conviction is never presented as calibrated"


def test_the_request_is_schema_bound_and_carries_the_headlines_as_data(sdk):
    sdk.outcome = _response()
    _read(horizon_label="1h")
    (call,) = sdk.calls
    assert call["system"] == llm.SYSTEM
    assert call["max_tokens"] == llm.MAX_TOKENS
    assert call["output_config"]["format"] == {"type": "json_schema", "schema": llm._SCHEMA}
    prompt = call["messages"][0]["content"]
    assert "<HEADLINES>" in prompt and "ETF flows rise" in prompt
    assert "Holding horizon: 1h" in prompt


def test_a_stated_conviction_is_clamped_and_lists_are_capped(sdk):
    over = dict(GOOD, conviction=180, catalysts=[f"c{i}" for i in range(10)])
    sdk.outcome = _response(text=json.dumps(over))
    read = _read()
    assert read.conviction == 100
    assert read.catalysts == [f"c{i}" for i in range(6)]
    sdk.outcome = _response(text=json.dumps(dict(GOOD, conviction=-20)))
    assert _read().conviction == 0


def test_a_thinking_block_before_the_text_is_skipped(sdk):
    sdk.outcome = _response(blocks=[SimpleNamespace(type="thinking", thinking="..."),
                                    SimpleNamespace(type="text", text=json.dumps(GOOD))])
    read = _read()
    assert read.error is None and read.conviction == 72


# --- the model declines or runs out of room (M8, M3) --------------------------

def test_a_refusal_is_shown_as_a_refusal_not_as_a_read(sdk):
    # The body is a well-formed read on purpose: if the refusal check went, this
    # would be drawn as the model's opinion.
    sdk.outcome = _response(stop_reason="refusal", category="cyber")
    read = _read()
    assert read.error == "model declined this request (cyber)"
    _shows_nothing(read)


def test_a_refusal_without_a_category_still_says_it_declined(sdk):
    sdk.outcome = _response(stop_reason="refusal")
    read = _read()
    assert read.error == "model declined this request (unspecified)"
    _shows_nothing(read)


@pytest.mark.parametrize("body", [
    json.dumps(GOOD),                       # parses, so only the stop reason can catch it
    json.dumps(GOOD)[:40],                  # cut off mid-object
], ids=["parses", "cut-mid-object"])
def test_a_truncated_response_is_reported_as_truncated(sdk, body):
    sdk.outcome = _response(stop_reason="max_tokens", text=body)
    read = _read()
    assert read.error == "response truncated — raise MAX_TOKENS"
    _shows_nothing(read)


def test_a_reply_cut_off_by_the_context_window_is_reported_as_cut_off(sdk):
    # Review R4: this stop reason used to fall through to parsing. With a body
    # that parses it was shown as a whole read.
    sdk.outcome = _response(stop_reason="model_context_window_exceeded")
    read = _read()
    assert read.error == "response cut off — the request filled the model's context window"
    _shows_nothing(read)


# --- the reply cannot be read -------------------------------------------------

@pytest.mark.parametrize("blocks", [
    [SimpleNamespace(type="text", text="Here is my read: UP, fairly sure.")],
    [SimpleNamespace(type="thinking", thinking="no text block at all")],
    [],
], ids=["prose-not-json", "no-text-block", "empty-content"])
def test_an_unparseable_reply_is_an_error_not_a_crash(sdk, blocks):
    sdk.outcome = _response(blocks=blocks)
    read = _read()
    assert read.error is not None and read.error.startswith("unparseable response")
    _shows_nothing(read)


@pytest.mark.parametrize("body", [
    "[]",                                               # JSON, but not an object
    json.dumps(dict(GOOD, conviction="high")),          # conviction is not a number
    json.dumps(dict(GOOD, conviction=None)),
    '{"direction": "UP", "conviction": Infinity, "summary": "", "catalysts": [], "risks": []}',
    json.dumps(dict(GOOD, catalysts=7)),                # not a list
    json.dumps(dict(GOOD, catalysts="abc")),            # a string would become bullets a, b, c
    json.dumps(dict(GOOD, risks={"k": "v"})),           # an object would become its keys
    "[" * 100_000 + "]" * 100_000,                      # nesting deep enough to recurse out
], ids=["array", "conviction-word", "conviction-null", "conviction-infinite", "catalysts-number",
        "catalysts-string", "risks-object", "deep-nesting"])
def test_json_of_the_wrong_shape_is_an_error_not_a_crash(sdk, body):
    # Review R1: these raised out of read(), and the caller (core.py) has no guard.
    sdk.outcome = _response(text=body)
    read = _read()
    assert read.error is not None and read.error.startswith("unparseable response")
    _shows_nothing(read)


def test_model_text_quoted_in_a_parse_error_is_cleaned_and_capped(sdk):
    # int("<b>...") puts the model's own text into the exception message.
    sdk.outcome = _response(text=json.dumps(dict(GOOD, conviction="<b>buy</b>\n" * 100)))
    read = _read()
    assert read.error.startswith("unparseable response: ValueError")
    assert "<" not in read.error and "\n" not in read.error
    assert len(read.error) < 220


# --- the call itself fails ----------------------------------------------------

@pytest.mark.parametrize("raised, expected", [
    (_RateLimitError(), "rate limited — try again shortly"),
    (_status(529, "overloaded_error", "Overloaded"), "the API is overloaded — try again shortly (HTTP 529)"),
    (_status(401, "authentication_error", "invalid x-api-key"), "the API key was rejected (HTTP 401)"),
    (_status(403, "permission_error"), "this key is not allowed to make this request (HTTP 403)"),
    (_status(404, "not_found_error"), f"model {llm.MODEL} was not found (HTTP 404)"),
    (_status(400, "invalid_request_error", "bad param"), "the API rejected the request (HTTP 400)"),
    (_status(500), "the API had a server error (HTTP 500)"),
    (_status(503), "the API had a server error (HTTP 503)"),
    (_status(418), "the API returned an error (HTTP 418)"),
    (_APITimeoutError("Request timed out."), "the API did not answer within 120 s"),
    (_APIConnectionError("Connection error."), "could not reach the API (network)"),
    (RuntimeError("socket closed"), "RuntimeError: socket closed"),
], ids=["429", "529", "401", "403", "404", "400", "500", "503", "other-4xx",
        "timeout", "connection", "anything-else"])
def test_each_failure_gets_its_own_message(sdk, raised, expected):
    sdk.outcome = raised
    read = _read()
    assert read.error == expected
    _shows_nothing(read)


def test_a_programming_error_after_parsing_is_not_called_a_bad_reply(sdk, monkeypatch):
    # Only the reply's shape is caught. A bug in building the read must surface,
    # not be reported as the model's fault.
    real = llm.LLMRead

    def broken(**kw):
        if kw.get("error") is None:        # only the success path is broken; _err() still works
            raise TypeError("LLMRead() got an unexpected keyword argument 'conviction'")
        return real(**kw)
    sdk.outcome = _response()
    monkeypatch.setattr(llm, "LLMRead", broken)
    with pytest.raises(TypeError, match="unexpected keyword"):
        _read()


@pytest.mark.parametrize("raised, expected", [
    (_status(400, "invalid_request_error",
             "Your credit balance is too low to access the Anthropic API."),
     "the API account's credit balance is too low (HTTP 400)"),
    (_status(402, "billing_error", "payment required"),
     "the API account has a billing problem — check its credit balance (HTTP 402)"),
], ids=["400-credit", "402-billing"])
def test_running_out_of_credit_is_named(sdk, raised, expected):
    sdk.outcome = raised
    assert _read().error == expected


def test_an_unexpected_exception_is_shown_cleaned_and_capped(sdk):
    sdk.outcome = OSError("<a href='x'>profile</a>\n" + "y" * 400)
    read = _read()
    assert read.error.startswith("OSError: ")
    assert "<" not in read.error and "\n" not in read.error
    assert len(read.error) < 180


def test_a_plain_completion_shows_an_exception_cleaned_and_capped(sdk):
    """Review P3-5: Playmaker's completion path cleans its error as read() does."""
    sdk.outcome = OSError("<a href='x'>profile</a>\n" + "y" * 400)
    text, error = llm.complete("system", "prompt")
    assert text == ""
    assert error.startswith("OSError: ")
    assert "<" not in error and "\n" not in error
    assert len(error) <= 160


def test_a_status_error_never_shows_the_raw_error_body(sdk):
    # Review R2: the SDK's message is "Error code: 401 - {...raw dict...}".
    sdk.outcome = _status(401, "authentication_error", "invalid x-api-key")
    read = _read()
    assert "Error code" not in read.error and "{" not in read.error


def test_no_call_is_made_when_a_read_cannot_run(sdk, monkeypatch):
    monkeypatch.setattr(llm, "available", lambda: (False, "no ANTHROPIC_API_KEY"))
    read = _read()
    assert read.error == "no ANTHROPIC_API_KEY"
    assert sdk.clients == [] and sdk.calls == []
    _shows_nothing(read)
