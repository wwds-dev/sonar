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

BANNED = ("skipped provider", "No code needed", "is the fix", "closes that gap",
          "highest-value", "survive Yahoo breaking", "still resolves",
          "provider layer")


@pytest.mark.parametrize("rel", CHECKED)
@pytest.mark.parametrize("phrase", BANNED)
def test_the_false_fallback_claims_stay_out(rel, phrase):
    assert phrase.lower() not in _flat(_read(rel)).lower(), (
        f"{rel} says {phrase!r} again")


@pytest.mark.parametrize("rel", CHECKED)
def test_coingecko_and_frankfurter_appear_only_as_not_used(rel):
    sentences = re.split(r"(?<=[.!?])\s+", _flat(_read(rel)))
    bad = [s for s in sentences
           if re.search(r"coingecko|frankfurter", s, re.I) and "not used" not in s]
    assert not bad, f"{rel}: {bad}"


def test_the_fallback_row_is_gone_from_the_data_table():
    assert "Crypto spot / FX fallback" not in DOCS_HTML


def test_the_module_map_does_not_list_the_deleted_module():
    assert "providers.py" not in README


# --------------------------------------------------------------------------- #
# What has to be said, in both places a user reads about the data

SOURCE = ("Yahoo is the only source for the Screener's equities, FX, commodities "
          "and crypto rows, with no fallback; the BTC hourly model uses Binance, "
          "with Coinbase if Binance is unreachable.")
DELAY = ("Quotes may be delayed by the exchange; Updated shows when SONAR fetched "
         "the price, not the exchange's time.")
SAID_IN_BOTH = (
    SOURCE,
    DELAY,
    "keeps scoring from cached prices",
    "also mean Yahoo is not answering",
    "A failed fetch keeps the closes already held.",
    "is not refetched until the next one",
    "only after 28 days and 3 failed fetch days",
    "an outage delays grading by at least a day, and only a long outage removes entries",
    "an empty answer uses none. So the equity curve waits.",
)


@pytest.mark.parametrize("doc", ["README.md", "static/docs.html"])
@pytest.mark.parametrize("text", SAID_IN_BOTH)
def test_the_data_section_says(doc, text):
    assert text in _flat(_read(doc)), f"{doc} no longer says {text!r}"


def test_the_outage_numbers_match_the_code():
    """The docs say "28 days and 3 failed fetch days"; the seed sentence names
    `SEED_RETRY_EVERY` and `SEED_MAX_TRIES`."""
    assert calibration.SHADOW_PRICE_GRACE_DAYS == 28
    assert calibration.SHADOW_PRICE_TRIES == 3
    assert "`SEED_RETRY_EVERY`" in README and "`SEED_MAX_TRIES`" in README
    assert core.SEED_RETRY_EVERY > 0 and core.SEED_MAX_TRIES > 0


def test_the_board_age_paragraph_names_a_yahoo_outage():
    assert "red can also mean Yahoo is not answering" in _flat(README)


# --------------------------------------------------------------------------- #
# Finnhub's status lives in one place

def test_finnhub_status_is_stated_only_in_the_readme():
    assert "Finnhub" in README.split("## Data providers", 1)[1].split("\n## ", 1)[0]
    for rel in ("static/docs.html", ".env.example", "SUGGESTIONS.md",
                "CONFIDENCE.md", "TESTPLAN.md"):
        assert "finnhub" not in _read(rel).lower(), rel
    rest = README.split("## Data providers", 1)
    outside = rest[0] + rest[1].split("\n## ", 1)[1]
    assert "finnhub" not in outside.lower(), "README states Finnhub outside its data section"


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
def test_each_result_record_names_its_price_source(rel):
    text = _flat(_read(rel))
    for result in ("v1.0 (30 days clean", "Shadow-ledger look 1"):
        at = text.find(result)
        assert at >= 0, f"{rel}: no record for {result!r}"
        line_end = text.find(" - ", at + 1)
        record = text[at:line_end if line_end > 0 else None]
        assert RECORD in record, f"{rel}: {result!r} does not name its price source"
