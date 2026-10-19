"""The docs have to describe the price path that actually runs.

They used to say that SONAR fell back to another vendor when Yahoo failed: that
"a vendor going down is a skipped provider rather than a broken app", that
crypto and FX "survive Yahoo breaking" through CoinGecko and Frankfurter, and
that a free Finnhub key was "the fix". The module behind those claims,
`sonar/providers.py`, was imported by nothing, so none of it ran. It was
deleted, and the docs now say that Yahoo is the only source for the Screener's
rows (`docs/specs/providers-wiring.md`).

So this file binds the docs to the code in two halves:

* a static scan of `sonar/`, `ui/`, `scripts/` and `main.py` for a `providers`
  module or an import of one. If one comes back, the data section of the docs
  has to be rewritten along with it;
* phrase checks on the documents that made the claim: the false claims stay
  out, the single-source sentence, the outage behaviour and the delay
  disclosure stay in, Finnhub's status lives in one place, and the result
  records name their price source.

The outage numbers are also tied to the constants they describe. Like the
broker test, the phrase checks only guard the known false claims, so a new
wording of the same claim can get past them; the reviewer still reads the data
section in full.
"""

import ast
import html
import re
from pathlib import Path

import pytest

from sonar import calibration, core

ROOT = Path(__file__).resolve().parents[1]


def _read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def _flat(text):
    """Tags stripped, entities decoded, whitespace collapsed: a sentence the
    page wraps across lines still reads as one."""
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", text)))


README = _read("README.md")
DOCS_HTML = _read("static/docs.html")


def _between(text, start, end, what):
    """The part of ``text`` from ``start`` up to ``end``, with a message that
    names the heading when the document has been restructured."""
    _, found, rest = text.partition(start)
    assert found, f"{what}: {start!r} not found; update this test with the docs"
    body, found, _ = rest.partition(end)
    assert found, f"{what}: {end!r} not found after {start!r}"
    return body


README_DATA = _between(README, "## Data providers\n", "\n## ", "README data section")
README_LAYOUT = _between(README, "## Layout\n", "\n## ", "README module map")
DOCS_DATA = _between(DOCS_HTML, 'id="data"', 'id="model"', "docs.html §3")

# The six documents Measure 1 of the spec greps.
CHECKED = ("README.md", "static/docs.html", ".env.example", "TODO.md",
           "SUGGESTIONS.md", "CONFIDENCE.md")

REWRITE = ("The docs say Yahoo is the only source for the Screener's rows, with "
           "no fallback; rewrite the data section (README, static/docs.html) "
           "along with this change.")


# --------------------------------------------------------------------------- #
# The code fact: there is no provider module, and nothing imports one

def _sources():
    files = []
    for d in ("sonar", "ui", "scripts"):
        files += sorted((ROOT / d).rglob("*.py"))
    files.append(ROOT / "main.py")
    return files


def test_there_is_no_provider_module():
    assert not (ROOT / "sonar" / "providers.py").exists(), REWRITE
    assert not (ROOT / "sonar" / "providers").is_dir(), REWRITE


def test_nothing_imports_a_provider_module():
    found = []
    for path in _sources():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                base = node.module or ""
                names = [base] + [f"{base}.{a.name}" for a in node.names]
            else:
                continue
            if any(n.split(".")[-1] == "providers" for n in names):
                found.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert not found, f"{found}: {REWRITE}"


# --------------------------------------------------------------------------- #
# The false claims stay out

# Phrases only the fallback claim used: banned everywhere in the six documents.
VENDOR_CLAIMS = ("skipped provider", "survive Yahoo breaking", "still resolves")
# Phrases that are ordinary English elsewhere ("this is the fix" for a UI bug, a
# research item ranked "highest-value"): banned in the data sections and the
# env example, and in any sentence that names a data source.
GENERIC_CLAIMS = ("No code needed", "is the fix", "closes that gap", "highest-value",
                  "provider layer")
SOURCE_NAME = re.compile(r"yahoo|finnhub|twelve ?data|alpha ?vantage|coingecko|"
                         r"frankfurter|stooq|provider|fallback|second source", re.I)


def _sentences(text):
    return re.split(r"(?<=[.!?])\s+", _flat(text))


@pytest.mark.parametrize("rel", CHECKED)
@pytest.mark.parametrize("phrase", VENDOR_CLAIMS)
def test_the_false_fallback_claims_stay_out(rel, phrase):
    assert phrase.lower() not in _flat(_read(rel)).lower(), (
        f"{rel} says {phrase!r} again")


@pytest.mark.parametrize("where,text", [
    ("README data section", README_DATA),
    ("docs.html §3", DOCS_DATA),
    (".env.example", _read(".env.example")),
], ids=["readme", "docs-html", "env-example"])
@pytest.mark.parametrize("phrase", GENERIC_CLAIMS)
def test_the_data_sections_carry_no_fix_claim(where, text, phrase):
    assert phrase.lower() not in _flat(text).lower(), f"{where} says {phrase!r}"


@pytest.mark.parametrize("rel", CHECKED)
@pytest.mark.parametrize("phrase", GENERIC_CLAIMS)
def test_no_sentence_naming_a_source_carries_a_fix_claim(rel, phrase):
    bad = [s for s in _sentences(_read(rel))
           if SOURCE_NAME.search(s) and phrase.lower() in s.lower()]
    assert not bad, f"{rel}: {bad}"


@pytest.mark.parametrize("rel", CHECKED)
def test_coingecko_and_frankfurter_appear_only_as_not_used(rel):
    """A sentence may name them only to say they are not used, with nothing
    else in it: "CoinGecko and Frankfurter (crypto and FX) are not used." """
    allowed = re.compile(r"^(CoinGecko|Frankfurter)( and (CoinGecko|Frankfurter))?"
                         r"( \([^)]*\))? (is|are) not used\.$")
    bad = [s for s in _sentences(_read(rel))
           if re.search(r"coingecko|frankfurter", s, re.I) and not allowed.match(s.strip())]
    assert not bad, f"{rel}: {bad}"


def test_the_fallback_row_is_gone_from_the_data_table():
    assert "Crypto spot / FX fallback" not in DOCS_HTML


def test_the_module_map_does_not_list_the_deleted_module():
    assert "providers.py" not in README_LAYOUT


# --------------------------------------------------------------------------- #
# What has to be said, in both places a user reads about the data

SOURCE = ("Yahoo is the only source for the Screener's equities, FX, commodities "
          "and crypto rows, with no fallback; the BTC hourly model uses Binance; if "
          "Binance is unreachable, Coinbase supplies the live candle, but volatility "
          "and gap settlement still need Binance (the model then falls back to a "
          "default volatility).")
DELAY = ("Quotes may be delayed by the exchange; Updated shows when SONAR fetched "
         "the price, not the exchange's time.")


@pytest.mark.parametrize("doc", ["README.md", "static/docs.html"])
@pytest.mark.parametrize("text", [SOURCE, DELAY], ids=["source", "delay"])
def test_the_data_section_says_verbatim(doc, text):
    assert text in _flat(_read(doc)), f"{doc} no longer says {text!r}"


# The outage behaviour, by its key facts rather than its exact prose. The
# numbers are tied to the constants below.
OUTAGE_TOKENS = (
    "cached prices", "in memory", "relaunch", "horizon change",
    "not answering",
    "closes already held", "UTC day", "28 days", "3 failed fetch days",
    "empty answer uses none", "six partial answers", "next launch",
)


@pytest.mark.parametrize("where,text", [
    ("README data section", README_DATA), ("docs.html §3", DOCS_DATA)],
    ids=["readme", "docs-html"])
@pytest.mark.parametrize("token", OUTAGE_TOKENS)
def test_the_data_section_says_what_an_outage_does(where, text, token):
    assert token in _flat(text), f"{where} no longer says {token!r}"


def test_the_outage_numbers_match_the_code():
    """The docs say "28 days and 3 failed fetch days" and "six partial
    answers"; the README names `SEED_RETRY_EVERY` and `SEED_MAX_TRIES`."""
    assert calibration.SHADOW_PRICE_GRACE_DAYS == 28
    assert calibration.SHADOW_PRICE_TRIES == 3
    assert core.SEED_MAX_TRIES == 6
    assert "`SEED_RETRY_EVERY`" in README_DATA and "`SEED_MAX_TRIES`" in README_DATA


def test_the_board_age_paragraph_names_a_yahoo_outage():
    assert "red can also mean Yahoo is not answering" in _flat(README)


# --------------------------------------------------------------------------- #
# Finnhub's status lives in one place

def test_finnhub_status_is_stated_only_in_the_readme():
    assert "Finnhub" in README_DATA
    for rel in ("static/docs.html", ".env.example", "SUGGESTIONS.md",
                "CONFIDENCE.md", "TESTPLAN.md"):
        assert "finnhub" not in _read(rel).lower(), rel
    assert "finnhub" not in README.replace(README_DATA, "").lower(), "README states Finnhub outside its data section"


def test_the_backlog_only_points_at_the_readme_for_finnhub():
    lines = [ln for ln in _read("TODO.md").splitlines() if "finnhub" in ln.lower()]
    assert all('README "Data providers"' in ln for ln in lines), lines


def test_no_market_data_key_is_offered_in_the_env_example():
    env = _read(".env.example")
    for key in ("FINNHUB_API_KEY", "TWELVEDATA_API_KEY", "ALPHAVANTAGE_API_KEY"):
        assert key not in env, key


# --------------------------------------------------------------------------- #
# The result records name their price source

RECORD = "prices: Yahoo chart endpoint only, no fallback, run window"


@pytest.mark.parametrize("rel", ["docs/specs/v1-product.md", "CONFIDENCE.md"])
@pytest.mark.parametrize("result", [r"v1\.0 \(30 days clean", r"Shadow-ledger look 1"])
def test_each_result_record_names_its_price_source(rel, result):
    """Each result is a bullet; its wrapped lines are indented. The bullet,
    not the rest of the file, has to carry the source line."""
    bullet = re.search(rf"^- \*\*{result}.*?(?=^\S|^- |\Z)", _read(rel), re.M | re.S)
    assert bullet, f"{rel}: no result bullet for {result!r}"
    assert RECORD in _flat(bullet.group(0)), f"{rel}: {result!r} does not name its price source"
