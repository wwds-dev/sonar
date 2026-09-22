"""Two vocabularies for one app.

The Plain Language direction fixed a real problem and created a smaller one.
"Worth a look" is what `CONF` means and is the right heading for someone who has
never traded; it is also three words where one would do, and it does not match
the term the manual, the research notes and every other market tool use. A
reader who has learnt what P(profit) is should not have to translate back.

So the wording is a setting rather than a decision. **Plain** is the default and
the one the app is designed around: words instead of abbreviations, a second
line under each figure saying what it means, one plain sentence per row.
**Expert** is the same board in the standard terms and without the second lines,
which also makes it about a third shorter per row.

What it deliberately does *not* change is the layout: same columns, same widths,
same order. A mode that rearranged the board would be a second interface to
build and to keep true, and the point of the switch is the vocabulary.

The choice is remembered, because nobody wants to re-pick it every launch, and
it is the only thing in this module that touches disk.
"""

from __future__ import annotations

import json

from sonar import paths

PLAIN = "plain"
EXPERT = "expert"

_mode = PLAIN


def _file():
    return paths.user_data_base() / "wording.json"


def mode() -> str:
    return _mode


def plain() -> bool:
    return _mode == PLAIN


def set_mode(new: str) -> str:
    """Switch, and remember. A bad value falls back to plain rather than
    raising: this is a preference file that a human may well have edited."""
    global _mode
    _mode = EXPERT if new == EXPERT else PLAIN
    try:
        _file().write_text(json.dumps({"wording": _mode}))
    except OSError:
        pass            # a preference that cannot be saved is still a preference
    return _mode


def toggle() -> str:
    return set_mode(EXPERT if plain() else PLAIN)


def load() -> str:
    """Read the remembered choice. Called once, when the window is built."""
    global _mode
    try:
        stored = json.loads(_file().read_text()).get("wording")
    except (OSError, ValueError, AttributeError):
        stored = None
    _mode = EXPERT if stored == EXPERT else PLAIN
    return _mode


def pick(pair: tuple[str, str]) -> str:
    """``(plain, expert)`` → whichever is in force."""
    return pair[0] if plain() else pair[1]
