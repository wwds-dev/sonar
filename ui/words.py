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


# --- AI-generated output and betting notices (legal audit 2026-11-10, #3 #5) ---
# One home for wording that must stay identical wherever it is shown, with a
# (plain, expert) pair where the two vocabularies differ. Expert keeps the
# familiar name but never drops the AI-generated label.
AI_TAG = "AI-generated (Anthropic Claude) · commentary, not advice"
LLM_READ_TITLE = ("AI-GENERATED COMMENTARY", "LLM READ · AI-GENERATED")
MODEL_READ_TITLE = ("AI-GENERATED COMMENTARY", "MODEL READ — AI-GENERATED")
DIRECTION_NOTE = ("This direction is a model's output, shown so it can be "
                  "scored against what happens. It is not a recommendation "
                  "and has not been shown to be right more often than chance.")
# The hourly model is the one place SONAR states a direction of its own (not an
# AI's), so it carries its own line; the claim about the edge is the manual's
# (Learn §4) and a test keeps the two in step.
HOURLY_MODEL_NOTE = ("P(up) is a model's output, shown so it can be graded "
                     "against the market and against what happens. It is not a "
                     "recommendation to buy, sell or bet, and its disagreement "
                     "with the market has not been shown to be an edge.")
PLAYMAKER_NOTICE = (
    "Playmaker does arithmetic on bookmakers' published prices: their margin, "
    "where they disagree, and what a formula would stake if a gap were real. "
    "It is not betting advice, takes no bets and links to no bookmaker. "
    "Betting can lose money and can be addictive; if it stops being fun, "
    "stop. Gambling is for adults only, and the law where you live applies.")
STAKE_TIP = ("What fraction of a bankroll the Kelly formula suggests — the size "
             "that grows a bankroll fastest over many bets if the probability "
             "is right. If it is wrong, Kelly over-bets and can lose most of "
             "the bankroll.\n"
             "Sized at the pessimistic end of the estimate and capped, so it "
             "reads 0 whenever the edge might not be real. 0 is the normal "
             "answer.")
