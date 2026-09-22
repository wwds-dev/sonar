# Changelog

Versions follow `VERSIONING.md`: `v<MAJOR>.<BUILD>`, where BUILD is the commit
count. Every commit is therefore a version, so this file records the **builds
that were installed** and what changed in them — not every number that existed.
Newest first.

Builds before v2.103 predate the version number. Nothing has been
back-numbered: assigning versions to releases that never had them would make
this a worse record than the git log it was written from. `TODO.md`'s `## v2`
section lists what the v2 arc shipped.

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
