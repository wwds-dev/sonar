"""The documentation, rendered inside the app.

SONAR already had a good 60KB manual — a plain-English primer, a glossary, and
a section on how to tell whether a result means anything. It opened in a web
browser. That is the wrong place for it: the reader is looking at a number they
do not understand *right now*, in a window that is already open, and asking them
to leave the app to find out what it means is asking them to give up.

So the same file is rendered here. `static/docs.html` stays the single source —
it is what the tests in `tests/test_docs.py` check, and a second copy of the
prose would be a second thing to keep true. What this module does is translate
it into what Qt's rich text engine actually supports.

That translation is the whole job, and it is small on purpose:

* **The page's own ``<style>`` goes.** It is built on CSS custom properties,
  flexbox and gradients, none of which Qt renders — and a stylesheet Qt half
  understands is worse than none, because it silently drops the rules it cannot
  parse and keeps the ones it can. :data:`STYLESHEET` below is the replacement,
  written against the subset Qt documents.
* **The chrome goes.** The page header and its "back to the app" link make no
  sense in a tab that *is* the app, and the table of contents is a widget here
  rather than a block of links, so it is removed and rebuilt.

Nothing else is touched. If a paragraph reads oddly here, it reads oddly in the
browser too, and the fix belongs in the HTML.
"""

from __future__ import annotations

import html as html_mod
import re

from sonar import paths

#: The Qt rich-text stylesheet. Colours are the app's own (see `ui.theme`), but
#: written out rather than pulled from it: this is a stylesheet string handed to
#: a QTextDocument, not a Qt widget stylesheet, and it only supports a subset of
#: CSS 2.1 — no variables, no flexbox, no border-radius.
STYLESHEET = """
body { color: #e6edf3; background: #080b11; }
h1 { font-size: 21px; color: #e6edf3; }
h2 { font-size: 16px; color: #e6edf3; }
h3 { font-size: 13px; color: #3ea6ff; }
p, li, td, th { font-size: 13px; color: #e6edf3; }
.sub, .muted { color: #8b98a5; }
.faint { color: #4a5867; }
.n { color: #e8b84b; }
.up { color: #3ea6ff; }
.down { color: #ff6a54; }
.gold { color: #e8b84b; }
a { color: #3ea6ff; }
code, pre { color: #cfe3ff; background: #0a0f17; }
th { color: #8b98a5; }
table { border-color: #1a2431; }
.callout { background: #0d131d; color: #e6edf3; }
"""

#: Blocks that exist only because the page is a web page.
_DROP = (
    re.compile(r"<style\b.*?</style>", re.S),
    re.compile(r"<header\b.*?</header>", re.S),
    re.compile(r'<div class="toc">.*?</div>', re.S),
    re.compile(r"<script\b.*?</script>", re.S),
)

_SECTION = re.compile(r'<h2 id="([a-z-]+)"><span class="n">(\d+)</span>([^<]*)')


def _source(name: str = "docs.html") -> str:
    return (paths.resource_base() / "static" / name).read_text()


def sections(html: str) -> list[tuple[str, str, str]]:
    """``(anchor, number, title)`` for every section, in page order.

    Read from the document rather than kept in a list here, so a section added
    to the HTML appears in the app's contents without anyone remembering to.
    """
    # Unescaped: the titles come out of HTML source but go into a list widget,
    # where "Alerts &amp; where you could trade" is simply wrong.
    return [(a, n, html_mod.unescape(t).strip())
            for a, n, t in _SECTION.findall(html)]


def document(name: str = "docs.html") -> tuple[str, list[tuple[str, str, str]]]:
    """The page as Qt rich text, plus its contents."""
    html = _source(name)
    found = sections(html)
    for pattern in _DROP:
        html = pattern.sub("", html)
    # Qt's rich text follows `<a name="x">`, and does not reliably follow an
    # `id` on a heading — which is what the page uses, because a browser does.
    # Both are left in place: the browser keeps working from the same file.
    html = _SECTION.sub(lambda m: f'<a name="{m.group(1)}"></a>' + m.group(0), html)
    # Qt does not honour a margin on an inline span, so the section number ran
    # straight into its title: "1Start here". The separator is added here
    # rather than in the page, where the CSS already handles it.
    html = re.sub(r'(<span class="n">\d+)(</span>)', r"\1 · \2", html)
    body = re.search(r"<body\b[^>]*>(.*)</body>", html, re.S)
    return (body.group(1) if body else html), found
