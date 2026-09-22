# Versioning

SONAR versions look like **`v2.100`**. This is the lab-wide scheme, shared with
`imprint` and `sentinel_fork`; `sonar/version.py` implements it and
`tests/test_version.py` enforces it.

## The number

```
v<MAJOR>.<BUILD>
   │        └── git rev-list --count HEAD, zero-padded to three digits
   └─────────── the product arc, from the VERSION file
```

**MAJOR** is the only hand-edited part. It lives in the `VERSION` file at the
project root — one line, currently `2` — and changes only on a deliberate
milestone. Bumping it is a decision about scope, not a side effect of shipping;
v3 is defined in `TODO.md` and is not this.

**BUILD** is the repository's commit count. It is not a decision and **cannot be
forgotten**, which is the entire point. A hand-maintained build number is wrong
the first time someone ships without remembering to bump it, and silently wrong
from then on. Deriving it means the version *is* the development state.

It is monotonic on a linear history, which this repo has. A merge commit still
increments it, so the number never goes backwards. It is an ordering, not a
count of features — `v2.100` says a hundred commits precede it, nothing more.

There is no third component and no separate release step. Every commit is a
version; the ones that get installed are the ones anybody sees.

### Why not semver

Semver's minor/patch split encodes a promise about API compatibility to *other
software*. Nothing imports SONAR, so the promise has no audience — and inventing
one would mean guessing, every release, whether a change was "minor" or "patch":
a judgement with no consumer and therefore no right answer. An arc plus a
monotonic build says exactly what is true and nothing more.

### Why the dashboard cannot disagree

The Lab Project Monitor computes the version from the same two inputs — the
`VERSION` file and `git rev-list --count HEAD` — in `derive_version()`. There is
no second source to drift from. Do not add one here: a second scheme would be a
second answer to "which version is this", which is the question this exists to
settle.

## Writing a changelog entry

BUILD is the commit count, so the entry has to name a build that does not exist
yet — the one the commit you are about to make will produce. That number is
`git rev-list --count HEAD` **+ 1**, and the changelog edit goes in that same
commit. It is deterministic, not a guess.

Getting it wrong is caught: `tests/test_version.py` fails if the newest entry
names a build ahead of the repository, which is what a forgotten amend or an
invented number looks like.

The entry names the build that was **installed**, not every number in between.
Every commit is a version; only some become builds anyone runs.

## Bumping MAJOR

1. Edit `VERSION`.
2. Retitle the `## vN — current` section in `TODO.md`, and open the next one.
3. Note it at the top of `CHANGELOG.md`.

Nothing else. BUILD takes care of itself.

## The build stamp

A `.app` has no `.git`, so it cannot derive its own version at runtime.
`scripts/stamp_version.py` freezes the number into `_build_info.json` just
before PyInstaller runs, and the bundle carries it. The file is git-ignored: it
describes a build, not the source.

Running from a checkout, live git wins over the stamp — an edit shows up on the
next launch without re-stamping. Running frozen, the stamp wins: a bundle's own
build is what it is running, even with a checkout sitting beside it.

When neither is available the app shows `v2.???` and says "no version stamp".
That is a real state — a source copy with no `.git` — and showing it beats
inventing a number.

## "Is what I'm looking at current?"

`version.staleness()` answers it by comparing the running build against the
checkout:

| Situation | What it says |
|---|---|
| Checkout is at the same build or older | *Up to date with the checkout.* |
| Checkout has moved on | *7 commits behind the checkout (v2.107). Re-run ./build\_app.sh --install to catch up.* |
| No checkout reachable, or no git | *No checkout to compare against, so whether a newer build exists cannot be known from here.* |
| Build carries no stamp at all | *This build carries no version stamp.* |

The third and fourth rows matter as much as the first two. `known` is `False`
there, and the caller must say so rather than claim "up to date" — a version
display that guesses is worse than none, because it is believed.

## Where the version shows up

| Where | Form | Why there |
|---|---|---|
| Window title | `SONAR v2.100` | Bug reports arrive as screenshots, and the title is in every screenshot |
| Header, beside the name | `v2.100`, stamp + staleness on hover | The first thing you look at on opening the app |
| Menu-bar menu | `v2.100`, same tooltip | Reachable while the window is hidden, which is most of the time |
| `main.py --selftest` | Version, source, staleness | What a build reports about itself; **fails** if a frozen bundle has no stamp |
| `Info.plist` | `CFBundleShortVersionString` | So Finder's Get Info agrees with the window |
| `TODO.md` | `## v2 — current` | The arc; the Monitor derives the precise number itself |
| Lab Project Monitor | `v2.100 — current` | Derived, never hand-entered |

## Cost, and the rule it must not break

`sonar/version.py` shells out to git. **Nothing in this app may block the UI
thread** — that rule has been broken twice and both times shipped a window that
stopped repainting. So: `info()` is cached for the process, the badge text is
computed once at construction (~45ms, once), and the staleness check is paid
only on hover, where a 30ms pause is invisible. Nothing here is called from a
timer, a repaint, or the poll loop. `tests/test_version.py` holds that budget.

## Why this exists

SONAR had no version until 2026-09-22, and the cost was specific and repeated: a
rebuild would land, the app would be opened, and the new work was not there —
because the bundle in `/Applications` was older than the conversation about it.
Nothing on screen could distinguish a current build from a stale one. The window
now answers that by itself.
