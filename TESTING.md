# Testing roadmap

What is covered, what is not, and the order to fix it in. Every number here was
measured on 2026-09-16 with `coverage run --branch -m pytest tests/`, not
estimated.

---

## 0. Where we are

**838 tests. 64% of statements** (6,598 total, 2,191 unexecuted).

> **Progress.** Steps 1–4 are done. `model.py` 39% → **100%**, `engine.py`
> 38% → **100%**, `feeds.py` 30% → **82%**, `server.py` 0% → **92%**. The overall figure barely moves,
> which is the point: these are the modules that mattered, not the biggest ones.
> Writing them found a real bug (§1) and made a lookahead bug in the warm-up a
> one-character change that now fails a test (§2).
>
> **Two practices are worth keeping for the rest of the list.** Where two pieces
> of code compute the same quantity, compare them — that is what found the
> lattice bug, and neither implementation looked wrong alone. And *mutation-check*
> anything important: deliberately break the code and confirm a test notices.
> Coverage says a line ran, not that an assertion would have caught it being
> wrong. Twenty-eight mutations across these four modules: twenty-seven caught,
> and **the one that slipped is the argument for the practice**. A test asserted
> `b"SONAR" in body` to prove `/docs` served the manual — but the app page
> contains "SONAR" too, so wiring `/docs` to `index.html` passed happily.
> Coverage was green either way. Assert on something only the right answer has.

That number is respectable and it hides something worse than a low one would:
the coverage is almost exactly inverted against importance.

| | Coverage |
|---|---|
| Playmaker — the newest code | 86–100% |
| `execution.py`, `replay.py`, `calibration.py`, `costs.py`, `alerts.py` | 94–96% |
| ~~`sonar/engine.py` — the paper-trading engine~~ | ~~38%~~ → **100%** |
| ~~`sonar/model.py` — the probability model~~ | ~~39%~~ → **100%** |
| `sonar/core.py` — the engine driver | 34% |
| `sonar/feeds.py` — price and candle ingestion | 30% |
| `sonar/server.py`, `ui/tray.py` | **0%** |

Everything written while the discipline was fresh is well tested. The oldest
and most central code — the two modules that decide what the Terminal tab says
and what the Book records — is the least tested in the project.

---

## 1. Tier 1 — the heart of the app is 38% covered

These two modules produce every number a user acts on. Nothing else on this list
matters as much.

### `sonar/model.py` — **done, 100%**

Writing these found a ten-point bug on the main tab. `prob_up` is a closed form
and `lattice_distribution` is a binomial approximation of the same quantity;
`rows` is even, so the lattice always has an exact-middle bin, and when
price == open — where every hour starts — that bin sits on the barrier holding
21% of the distribution. `up: end_price >= open_` gave all of it to "up", so
the caption under the Terminal tab's lattice read **60.5%** while the signal
directly above it read **50.0%**.

Neither implementation looked wrong alone. Testing them against fixed values
would not have found it; testing them **against each other** did. That is the
lesson worth carrying to the rest of this list — wherever two pieces of code
compute the same thing, the cross-check is the test with the highest yield.

### ~~`sonar/model.py` (39%)~~ — the original plan

Untested: `prob_up`, `side`, `abs_edge`, `evaluate`, `lattice_distribution`,
`hourly_sigma`, `_phi`.

`prob_up` is the hourly up/down probability the Terminal tab is built around,
and `lattice_distribution` is the chart under it. Neither has a single test.
What to pin down:

- `_phi` against known normal-CDF values — it is hand-rolled, and a wrong
  constant would bias every probability in the app by a consistent amount that
  looks plausible.
- `prob_up` is 0.5 at zero drift, monotonic in drift, and symmetric:
  `prob_up(+x) == 1 - prob_up(-x)`.
- `hourly_sigma` on a known return series, and its behaviour on an empty one.
- `lattice_distribution` sums to 1, is centred on spot, and widens with sigma.
- `evaluate` and `abs_edge` agree with `prob_up` rather than drifting from it.

### `sonar/engine.py` — **done, 100%**

39 tests against a real engine and a real state file. Verified they *bite*
rather than merely execute, with five deliberate mutations — wrong barrier
side, two positions in one hour, entries priced at the midpoint, uncapped
stake, skipped entry window — all five caught.

**Mutation-checking is worth repeating for the rest of this list.** Coverage
says a line ran; it does not say an assertion would have noticed if the line
were wrong.

### ~~`sonar/engine.py` (38%)~~ — the original plan

Untested: `tick`, `_maybe_enter`, `finalize`, `stats`, `save`, `_load`, `_tau`,
`seed_backtest`, `llm_calibration`.

`tick` is the hourly heartbeat and `finalize` is what settles a position — the
two places a bug silently corrupts the equity curve the app exists to produce.
What to pin down:

- `tick` advances exactly one hour and is idempotent if called twice in the
  same hour.
- `_maybe_enter` respects the risk profile's cap and refuses when flat-ish.
- `finalize` settles at the right price, and a position opened and settled in
  the same hour cannot double-count.
- `save`/`_load` round-trip a book with open and closed positions — including
  the migration path from a state file written by an older version.
- `stats` on an empty book returns zeros rather than dividing by zero.

---

## 2. Tier 2 — untestable-looking things that are actually testable

### `sonar/feeds.py` — **done, 82%**

Parsers split from fetches; 69 tests, none touching the network. What remains
uncovered is `_get` itself, the paging half of the historical fetch, and the
`__main__` smoke block — pure I/O, and not worth mocking a socket for.

The find here was **causality**. `historical_decision_points` computes each
hour's volatility from `closes[i - vol_window : i]`, strictly earlier hours.
Changing `:i` to `:i + 1` tells the backtest the volatility of the hour it is
predicting, which inflates every result in a way that looks entirely plausible
and raises nothing. One character. There is now a test that fails on it —
feed a flat series with one violent hour at the end and assert that hour's own
sigma is still the calm one.

The other half of the pair matters too, and has its own test: causal must not
mean blind, so the *following* hour's sigma does pick the move up.

### `sonar/universe.py` (17%)

Untested: `canonical_title`, `wiki_article`, `article_map`, `_load_cache`,
`_save_cache`, `_throttle`.

Same split. The title-canonicalisation logic in particular is pure string
handling with no excuse for being untested.

### `sonar/server.py` — **done, 92%**

25 tests against a real server on an ephemeral port. What is left is the
`__main__` argparse block, which only runs when the module is invoked directly.

This needed a socket, which the suite bans, so `conftest.py` grew a `loopback`
fixture: it captures the real `connect`/`urlopen` before anything patches them
and hands them back **by name**. The ban is about reaching the *internet* —
someone else's uptime, someone else's rate limit, a hang with no timeout — and a
server the test started on 127.0.0.1 is none of those. A test asserts the ban
still holds for everyone who does not ask.

`main()` is covered too, since that is what the launchd agent runs: the engine
reaches the handler, the loop starts, Ctrl-C prints rather than dumping a
traceback, and a second daemon reports READ-ONLY instead of silently
double-counting the same hour into one state file.

### `ui/tray.py` (0%)

The menu bar item. `QSystemTrayIcon` needs a display, but `update_state` is
pure formatting over a snapshot dict and can be tested directly — it is also
the thing that shows a wrong bankroll if the snapshot shape drifts.

---

## 3. Tier 3 — the research apparatus

`research/study.py` 0%, `research/panel.py` 27%, `research/features.py` 31%,
`research/regimes.py` 49%.

Lower priority *only* because these produce findings a human reads and argues
with, rather than numbers the app acts on automatically. But `features.py` is
what every study's conclusion rests on, and a wrong feature would invalidate
findings rather than crash — the worst kind of bug to leave untested.

---

## 4. What the UI needs

`ui/app.py` is 61%, which is high for a 1,879-line window, and the three tests
that build a real `MainWindow` are how it got there. The gap is the interactive
half — the handlers nothing clicks in a test.

The pattern that works is already in `test_lab_tab.py` and the Playmaker check:
build the window, drive the handler directly, assert on what it rendered. No
clicking required. Worth extending to:

- the Book tab's buy/short/close path end to end against the paper engine
- the Terminal tab's render across every engine status
- the Assets table's sort and filter
- `ui/charts.py` (22%) — the painters take a data series and produce geometry,
  which is checkable without a screen

---

## 5. What tests structurally cannot catch

Some of the worst bugs in this project's history were invisible to any unit
test, and they each need a different net.

| Failure | Only caught by |
|---|---|
| A QThread missing from `shutdown()` → SIGABRT on quit | `tests/test_shutdown.py` plus actually quitting a built app |
| A module PyInstaller cannot see → missing in the bundle only | `main.py --selftest` against the **built binary** |
| Qt plugin inheritance crash when one frozen app launches another | a packaged run; invisible from source |
| A `QLabel` that will not wrap setting the window's minimum width | `tests/test_layout.py` |
| The UI thread blocking on a fetch → blank window | `tests/test_ui_thread.py` |
| An ESPN/Yahoo payload changing shape | `-m network` tests, run deliberately |

**The rule that falls out: after any packaging or threading change, run
`./build_app.sh --install` and then the installed binary's `--selftest`.** The
suite cannot tell you the bundle is correct.

---

## 6. Manual checklist

Things a human has to look at, once per release. Each one is on this list
because it has actually broken.

- [ ] Launch from `/Applications`, not the checkout. Time it — under three
      seconds to first paint.
- [ ] Every tab renders with content, not "—" everywhere.
- [ ] **Close the window: it disappears, the menu-bar icon stays, the app is
      still running.** Broken twice, for two different reasons.
- [ ] Quit from the menu bar: the process actually exits, no SIGABRT, no
      "Python quit unexpectedly".
- [ ] Leave full screen, then close. The window must not reopen itself.
- [ ] Leave it running for fifteen minutes and click around. The Wire's news
      TTL is eight minutes, and a UI-thread fetch would freeze it there.
- [ ] Resize to 1280×800. Nothing clipped, no horizontal scroll.
- [ ] Hover a number in each tab — a tooltip that explains it, in plain words.
- [ ] Open the Docs button. §1 loads, every link resolves.

---

## 7. Known infrastructure problems

- **The Qt window tests wedge about one run in three.** A PySide6 teardown race
  leaves a pthread mutex orphaned; the main thread then blocks below Python, so
  no in-process timeout can fire. `./run-tests.sh` bounds it from outside and
  samples the stack before killing. Ruled out already: the network, shared
  state, the poll thread, undrained `deleteLater`, and cross-file window
  accumulation. See `TODO.md`.
- **`coverage` is a dev dependency**, installed with
  `uv pip install --python .venv/bin/python coverage`. It is deliberately not in
  `pyproject.toml`'s runtime dependencies, which stay empty.

Re-measure with:

```bash
.venv/bin/python -m coverage run --source=sonar,ui --branch -m pytest tests/ -q
.venv/bin/python -m coverage report --skip-empty --sort=cover
```

---

## 8. Order to do it in

1. ~~`model.py`~~ — **done**, 100%, and it found the lattice bug.
2. ~~`engine.py`~~ — **done**, 100%, mutation-checked.
3. ~~`feeds.py`~~ — **done**, 82%, and it made the lookahead bug testable.
4. ~~`server.py`~~ — **done**, 92%.
5. The Book tab's trade path end to end.
6. `universe.py`, `charts.py`, `tray.py` formatting.
7. `research/features.py` — before the next study leans on it.

Steps 1–4 are done, and they were the ones that mattered. **Step 5 is next** —
the Book tab's trade path end to end, which is the last place a user action
reaches the engine without a test between them.
