# Changelog

Versions follow `VERSIONING.md`: `v<MAJOR>.<BUILD>`, where BUILD is the commit
count. Every commit is therefore a version, so this file records the **builds
that were installed** and what changed in them — not every number that existed.
Newest first.

Builds before v2.103 predate the version number. Nothing has been
back-numbered: assigning versions to releases that never had them would make
this a worse record than the git log it was written from. `TODO.md`'s `## v2`
section lists what the v2 arc shipped.

## v2.116 — 2026-09-29

**The Cockpit shell.** The second design round, from a mockup approved before
any code moved (the first round, v2.108, fixed vocabulary and contrast; this
one fixes structure). The eight top tabs became a **left rail** — both names
per destination, exactly as before, folding to icons below 1420pt of window
width and unfolding above it; the toolbar's wordmark, version badge and
practice-money line moved to the rail's head, the Wording and Test plan
buttons and the status line to its foot. A **page header** names every screen
in one sentence and keeps the risk and horizon knobs visible everywhere. The
Terminal's six equal stat cells became a hierarchy: the edge — the only
number in the app that is a disagreement with a market — is the largest
figure on screen in the one highlighted cell, tau is drawn as a filling
hour-bar as well as printed, and the bankroll strip and the model-vs-market
Brier line share one ledger panel under the equity curve. Same readouts, same
tooltips, same wording rules; `tests/test_layout.py` gained the two shell
invariants (folded fits 1280×775; expanded minimum stays below the fold
threshold, or the fold could never be reached by dragging). For the record:
two sessions shared this checkout on the day, so the shell's code landed
split across the v2.115 and v2.116 commits rather than under its own message.

## v2.115 — 2026-09-29

**The engine can no longer trade an hour that has already settled.** `tick()`
never checked that the market belongs to the candle, so around wakes and feed
hiccups a stale candle could meet a fresh market and buy the known outcome —
five live fills entered 22–51 minutes after their own hour closed were 71% of
the first week's paper P&L. One invariant now guards signal, scoring and entry
alike: an hourly market ends exactly one hour after its candle opens, or the
tick is refused. The phantom fills were scrubbed and the equity curve rebuilt.
`Engine.buyability()` also lands in this build, rebuilt after adversarial
review to price the strategy the engine actually trades — entry-window hours
only, side chosen as the entry path chooses it, settlement-state books
excluded and counted, Newey-West-widened errors, and a positive verdict that
must survive leave-one-out of its best hour.

## v2.114 — 2026-09-28

**CI survives a machine that is not this one.** The dashboard-consistency
test skips on an `exists()` check instead of trusting a spec for a missing
file, the AGE column widened 66→72 so DejaVu's metrics fit as well as SF's,
and the checkout fetches full history because the version *is* the commit
count. A four-lens adversarial audit found nothing further real.

## v2.113 — 2026-09-23

**The catalyst weight faced attribution — the first component ever to come
back KEEP** (IC +0.040 surviving FDR, +5.0-point quintile spread, 6/6 time
blocks, and the phase-shift control inverts rather than shrugs), measured
against a historical earnings calendar built from EDGAR Item-2.02 8-K
filings; a volatility effect, not a direction, and P(profit) stays pinned.
The Lab gained the earnings-history checkbox and the SPORTS MODELS panel, so
both studies re-run from inside the app; the Playmaker KEEP bar became a
measured bootstrap interval; `universe.py`, `charts.py` and `tray.py` got
their tests; and the score log stopped booking snapshots against
already-ended markets.

## v2.112 — 2026-09-22

**SONAR no longer aborts when its menu bar menu opens.** macOS 27 made
`-[NSEvent clickCount]` raise for an event that has no click count, and Qt's
cocoa plugin asks for it whenever a menu begins tracking — the Objective-C
exception unwinds through C++ frames that catch nothing, into `terminate()`.
PySide6 6.11.2 is the newest release, so there was nothing to upgrade to.
`ui/appkit_guard.py` is Lab Hub's guard, ported: it replaces that one selector
with an implementation answering 0 for the event types that have no click count
and calling through for the ten that do, installed before `QApplication` is
built. `--selftest` fails without it. This matters more here than in most apps —
the close button hides to the menu bar, so that menu is the way back in. Both
copies of the guard should be deleted once Qt ships a fixed cocoa plugin.

## v2.108 — 2026-09-22

The build a person without a finance background can read.

**The Plain Language direction.** Picked from three mockups. The complaint was
specific — the font, the contrast, the dropdowns — and the diagnosis underneath
it was that the board was five abbreviations in a row with no way in. `MOM` is
now "Recent move" over *over 5 days*; `VOL` is "Swing size" over *big swings*;
`R:R` and `P(PROF)` are one column reading "win 1.5× the risk / 40% of the
time"; `CONF` is "Worth a look", with the score drawn as a meter whose segments
are still the component breakdown. Every row carries one plain sentence built
from numbers already on it, and a test asserts that sentence can never acquire a
direction — it is the easiest place in the app to break the rule the project
rests on, and it would do it in a friendly voice.

**Type and contrast.** `ui/theme.py` splits one font helper into three: `text`
for words, `figure` for numbers (same face, tabular digits), `code` for actual
monospace, which survives in the two places that take a pasted table. `MUTED`
and `FAINT` both clear 4.5:1 against the panel they sit on; `FAINT` measured
1.9:1. Raising it exposed a latent bug: every `QLabel` inherited the blanket
`QWidget { background }` rule and painted the window colour over whatever panel
it sat on — invisible while the two colours were three points apart on the same
near-black, a dark box behind every cell once they were not.

**Plain or expert.** A `Wording` button switches the whole app between the two
vocabularies, and `ui/words.py` remembers the choice. Expert restores MOM, VOL,
`R:R · P(PROF)` and CONF, puts the ticker back, drops the second lines and the
banner, and shows one line per tab — about a third less row height. It changes
the vocabulary and the density, **never the layout**: `ASSET_COLS` carries both
headings and one width, so the header re-captions in place and there is only
ever one board to keep correct.

**The manual is a tab.** `static/docs.html` — the primer, the 24-term glossary
and §8 on judging a result — now renders inside the window, with contents on the
left and a search box that takes one unfamiliar word. It was a button that opened
a web browser, which is the wrong place for it: someone looking at a number they
do not understand is exactly the person who will not go and find a second
window. The HTML stays the single source; `ui/learn.py` strips the CSS Qt cannot
parse and injects the anchors Qt needs. Headings that name something non-obvious
link into it, and a test checks every anchor resolves.

**How old is this price?** An `Updated` column on every Screener row. The board
refetches only the 26 stalest of 129 markets per scan, so a row is routinely
minutes old by design — defensible until the screen shows the age as nothing at
all, at which point a fifteen-minute-old number reads exactly like a live one.
It is anchored to the scan's own timestamp so it keeps counting between scans.

**Both names on every tab**, painted by the new `ui/tabs.py`: the plain one over
the one the manual uses. Qt draws a `\n` in a tab label on one line and clips it.
The Practice and Sports tabs moved into scroll areas — a `QTabWidget`'s minimum
height is its tallest page's, so those two decided how short the window could be,
which was survivable in 9pt monospace and is not in the interface font.

1,339 tests. `TESTPLAN.md` is 117 manual cases.

## v2.103 — 2026-09-22

The first build that can say what it is, and whether it is current.

**Versioning.** `VERSION` holds the arc (`2`); the build number is
`git rev-list --count HEAD`. The window title, the header badge beside the name,
the menu-bar menu, `--selftest` and the bundle's `Info.plist` all read it from
`sonar/version.py`. Frozen builds carry `_build_info.json`, stamped by
`scripts/stamp_version.py` before packaging; `--selftest` now fails for a frozen
bundle without one. Hovering the badge reports the commit, the date, whether
this is a checkout or a package, and — by comparing against the checkout —
whether a newer build exists. When that cannot be known it says so instead of
claiming "up to date". A packaged bundle has no `.git` inside it, so the stamp
also records where the checkout was and the staleness check looks there — a
bundle copied to another machine finds nothing and goes back to saying it cannot
know. Same scheme and same two inputs as the Lab Project Monitor, so the
dashboard and the app cannot disagree. See `VERSIONING.md`.

**Quitting no longer freezes the app.** `shutdown()`'s last resort for a thread
that would not stop was `QThread.terminate()`, which kills a thread wherever it
stands; one running Python holds the GIL and never returns it, so every thread
blocked forever — the event loop included. The window stopped repainting and
macOS showed its empty backing store: the blank white window reported four
times, in an app themed `#080b11`. It fired routinely, because `live.stop()`
only lands between fetches, so any quit during a request had to outlast an 8–30s
socket timeout. The process now ends with `os._exit` instead, which skips the
QThread destructors whose `qFatal()` was the only reason terminate was wanted.
Nothing is lost: the engine writes through on every change, and the engine lock
is a PID file the next launch reclaims. The per-thread 4s wait became a 1.5s
budget shared across all six threads — six waits on the UI thread was up to 24s
of the same unpainted window.

**The local server answers bursts.** `PaperServer` sets a listen backlog of 64.
`socketserver`'s default of 5 is how many connections the kernel holds before
`accept()` reaches them, so past it a connection is refused with an RST before
any application code runs. Measured at twelve simultaneous requests, one was
reset every run.

**Build order fixed.** `build_app.sh` regenerated `static/testplan.html` *after*
packaging and installing, so an edited `TESTPLAN.md` shipped as the previous
build's page and was only corrected in time for the next one. It now runs before
PyInstaller, as its comment always claimed.

**Tests.** The suite's teardown had the same `terminate()` deadlock, which is
why it wedged about one run in three: the conftest guards were `autouse` at
*function* scope, and pytest builds fixtures highest-scope-first, so none of
them was in force when the module-scoped window fixtures built a window — those
tests were running the real engine against the real application directory and
the real network. Guards are session-scoped now. Deterministic, 9.3s.
