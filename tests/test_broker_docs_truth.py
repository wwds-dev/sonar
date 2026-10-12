"""The docs have to say which broker the book actually uses.

They used to say that adding Alpaca paper keys made the book use Alpaca, and
that Alpaca was the more honest mode. No code path did that: the book was, and
is, always the built-in `PaperBroker`. A user who added keys would then read the
book as the realistic version while it still filled instantly, exactly at target
or stop, with no spread, slippage or fees (`docs/specs/book-broker-truth.md`).

So this file binds the docs to the code in two halves:

* a static scan of `sonar/`, `ui/` and `main.py` for the ways Alpaca could be
  wired into the book: a `Portfolio(` call given a broker, any reference to
  `default_broker` outside its own definition, an `AlpacaPaperBroker(` built
  outside `default_broker`, and a `broker` attribute assigned anywhere but the
  two constructors that own one. Imports under another name are resolved. If
  one of these fails, the docs below have to be rewritten along with the code;
* phrase checks on the four documents that made the claim — the false claims
  stay out, and the Alpaca section keeps its cost disclosure.

The static half carries the weight. It reads source, so a deliberate evasion
(`getattr(portfolio, "default_broker")`) gets past it; it is a guard against
wiring the book up without noticing the docs, not against hiding it. The phrase
checks only guard the known false claims and the disclosure, so they are
deliberately narrow.
"""

import ast
import html
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

README = (ROOT / "README.md").read_text(encoding="utf-8")
DOCS_HTML = (ROOT / "static" / "docs.html").read_text(encoding="utf-8")
GOING_LIVE = (ROOT / "GOING_LIVE.md").read_text(encoding="utf-8")
ENV_EXAMPLE = (ROOT / ".env.example").read_text(encoding="utf-8")

REWRITE = ("The docs (README, static/docs.html, GOING_LIVE.md, .env.example) say "
           "the book always uses the built-in simulator; rewrite them along with "
           "this change.")


# --------------------------------------------------------------------------- #
# The code fact: the book is always built without a broker

def _sources():
    files = sorted((ROOT / "sonar").rglob("*.py")) + sorted((ROOT / "ui").rglob("*.py"))
    files.append(ROOT / "main.py")
    return files


# Where a `broker` attribute may be assigned: the book's own constructor, and
# the execution guard's, whose `broker` is its BrokerPort and not the book's.
BROKER_OWNERS = {
    ("sonar/portfolio.py", "Portfolio.__init__"),
    ("sonar/execution.py", "Guard.__init__"),
}


class _Scan(ast.NodeVisitor):
    """One file: the calls and references this test cares about, with the
    qualified name of the function or class each one sits in."""

    WATCHED = ("Portfolio", "default_broker", "AlpacaPaperBroker")

    def __init__(self, rel):
        self.rel = rel
        self.scope = []
        self.scopes_seen = set()
        # local name -> the watched name it stands for, `import ... as` resolved
        self.names = {name: name for name in self.WATCHED}
        self.portfolio_calls = []
        self.default_broker_refs = []
        self.adapter_calls = []
        self.broker_assignments = []

    def where(self, node):
        return f"{self.rel}:{node.lineno}"

    def _scoped(self, node):
        self.scope.append(node.name)
        self.scopes_seen.add(".".join(self.scope))
        self.generic_visit(node)
        self.scope.pop()

    visit_FunctionDef = visit_AsyncFunctionDef = visit_ClassDef = _scoped

    def visit_ImportFrom(self, node):
        for alias in node.names:
            if alias.name in self.WATCHED:
                self.names[alias.asname or alias.name] = alias.name
                if alias.name == "default_broker":
                    self.default_broker_refs.append(self.where(node))
        self.generic_visit(node)

    def _watched(self, node):
        if isinstance(node, ast.Name):
            return self.names.get(node.id)
        if isinstance(node, ast.Attribute) and node.attr in self.WATCHED:
            return node.attr
        return None

    def visit_Name(self, node):
        if self._watched(node) == "default_broker":
            self.default_broker_refs.append(self.where(node))

    def visit_Attribute(self, node):
        if self._watched(node) == "default_broker":
            self.default_broker_refs.append(self.where(node))
        self.generic_visit(node)

    def visit_Call(self, node):
        watched = self._watched(node.func)
        if watched == "Portfolio":
            self.portfolio_calls.append((self.where(node), node))
        elif watched == "AlpacaPaperBroker":
            in_alpaca = self.rel == "sonar/alpaca.py"
            in_default = (self.rel, ".".join(self.scope)) == ("sonar/portfolio.py",
                                                              "default_broker")
            if not (in_alpaca or in_default):
                self.adapter_calls.append(self.where(node))
        elif (isinstance(node.func, ast.Name) and node.func.id == "setattr"
              and len(node.args) > 1 and isinstance(node.args[1], ast.Constant)
              and node.args[1].value == "broker"):
            self._broker_assigned(node)
        self.generic_visit(node)

    def _broker_assigned(self, node):
        if (self.rel, ".".join(self.scope)) not in BROKER_OWNERS:
            self.broker_assignments.append(self.where(node))

    def _targets(self, targets, node):
        for target in targets:
            for sub in ast.walk(target):
                if isinstance(sub, ast.Attribute) and sub.attr == "broker":
                    self._broker_assigned(node)

    def visit_Assign(self, node):
        self._targets(node.targets, node)
        self.generic_visit(node)

    def visit_AnnAssign(self, node):
        self._targets([node.target], node)
        self.generic_visit(node)

    def visit_AugAssign(self, node):
        self._targets([node.target], node)
        self.generic_visit(node)


def _scan():
    scans = []
    for path in _sources():
        rel = path.relative_to(ROOT).as_posix()
        scan = _Scan(rel)
        scan.visit(ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
        scans.append(scan)
    return scans


SCANS = _scan()


def test_the_scan_finds_the_book_being_built():
    """Without this the next test could pass by finding nothing to check."""
    assert any(s.portfolio_calls for s in SCANS), (
        "no Portfolio( call found in sonar/, ui/ or main.py")


def test_the_scan_finds_the_owners_it_allows():
    """The allowances below are only worth something if they still point at
    real code: `default_broker` building the adapter, and the two constructors
    assigning `broker`."""
    seen = {(s.rel, scope) for s in SCANS for scope in s.scopes_seen}
    for owner in BROKER_OWNERS | {("sonar/portfolio.py", "default_broker")}:
        assert owner in seen, f"{owner} no longer exists; update this test"


def test_every_book_is_built_without_a_broker():
    offenders = [where for s in SCANS for where, node in s.portfolio_calls
                 if len(node.args) > 1
                 or any(isinstance(a, ast.Starred) for a in node.args)
                 or any(k.arg in ("broker", None) for k in node.keywords)]
    assert not offenders, f"Portfolio( is given a broker at {offenders}. {REWRITE}"


def test_nothing_refers_to_default_broker():
    """Covers a call, an import under another name, and passing the function
    around (`functools.partial`, a default argument) without calling it here."""
    refs = [where for s in SCANS for where in s.default_broker_refs]
    assert not refs, f"default_broker is referenced at {refs}. {REWRITE}"


def test_the_alpaca_adapter_is_built_only_by_default_broker():
    calls = [where for s in SCANS for where in s.adapter_calls]
    assert not calls, (
        f"AlpacaPaperBroker( is built outside portfolio.default_broker at {calls}. "
        f"{REWRITE}")


def test_no_broker_is_swapped_in_after_construction():
    assigned = [where for s in SCANS for where in s.broker_assignments]
    assert not assigned, (
        f"a `broker` attribute is assigned at {assigned}, outside the "
        f"constructors that own one. {REWRITE}")


# --------------------------------------------------------------------------- #
# The documents: no false claim, and the disclosure stays

def _plain(text):
    """Tags out, entities decoded, whitespace collapsed, lower-cased — so
    `SONAR <b>uses</b> it`, `more&nbsp;honest` or a claim wrapped across two
    lines is still found."""
    return " ".join(html.unescape(re.sub(r"<[^>]+>", "", text)).replace("*", "")
                    .lower().split())


def _readme_alpaca_section():
    match = re.search(r"^## [^\n]*Alpaca[^\n]*\n(.*?)(?=^## )", README, re.M | re.S)
    assert match, "README.md has no ## section about Alpaca"
    return match.group(0)


def _docs_alpaca_section():
    match = re.search(r"<h3>[^<]*Alpaca[^<]*</h3>(.*?)(?=<h[23][ >])", DOCS_HTML, re.S)
    assert match, "static/docs.html has no <h3> section about Alpaca"
    return match.group(0)


DOCUMENTS = {
    "README.md": lambda: README,
    "static/docs.html": lambda: DOCS_HTML,
    "GOING_LIVE.md": lambda: GOING_LIVE,
    ".env.example": lambda: ENV_EXAMPLE,
}

# Where Alpaca is described: the comparative claims are checked only here, so
# "does better" elsewhere in a long README is not a false alarm.
ALPACA_TEXT = {
    "README.md (Alpaca section)": _readme_alpaca_section,
    "static/docs.html (Alpaca section)": _docs_alpaca_section,
    ".env.example": lambda: ENV_EXAMPLE,
}

AUTOMATIC_USE = [
    "picks them up automatically",
    "and SONAR uses it",
    "picks it up automatically",
    "where Alpaca already sits",
]

COMPARATIVE = [
    "does better",
    "more honest",
]


@pytest.mark.parametrize("doc", DOCUMENTS)
@pytest.mark.parametrize("claim", AUTOMATIC_USE)
def test_the_documents_do_not_say_the_book_uses_alpaca(doc, claim):
    assert claim.lower() not in _plain(DOCUMENTS[doc]()), (
        f"{doc} says {claim!r}, but the book never uses Alpaca")


@pytest.mark.parametrize("doc", ALPACA_TEXT)
@pytest.mark.parametrize("claim", COMPARATIVE)
def test_alpaca_is_not_compared_with_the_book(doc, claim):
    assert claim.lower() not in _plain(ALPACA_TEXT[doc]()), (
        f"{doc} says {claim!r}: Alpaca is not connected, so nothing may compare "
        "it with the book")


SECTIONS = {
    "README.md": _readme_alpaca_section,
    "static/docs.html": _docs_alpaca_section,
}


@pytest.mark.parametrize("doc", SECTIONS)
@pytest.mark.parametrize("phrase", [
    "always uses the built-in simulator",
    "optimistic bound",
    "slippage or fees",
    "does not use it yet",
])
def test_the_alpaca_section_keeps_the_disclosure(doc, phrase):
    assert phrase in _plain(SECTIONS[doc]()), (
        f"the Alpaca section of {doc} no longer says {phrase!r}")


def test_the_env_example_says_the_keys_are_not_used_by_the_book():
    assert "not used by the book" in ENV_EXAMPLE
