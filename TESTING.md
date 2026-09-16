# Testing roadmap

What is covered, what is not, and the order to fix it in. Every number here was
measured on 2026-09-16 with `coverage run --branch -m pytest tests/`, not
estimated.

---

## 0. Where we are

**666 tests. 61% of statements, 6,579 statements total, 2,373 unexecuted.**

That number is respectable and it hides something worse than a low one would:
the coverage is almost exactly inverted against importance.

| | Coverage |
|---|---|
| Playmaker — the newest code | 86–100% |
| `execution.py`, `replay.py`, `calibration.py`, `costs.py`, `alerts.py` | 94–96% |
| **`sonar/engine.py` — the paper-trading engine** | **38%** |
| **`sonar/model.py` — the probability model** | **39%** |
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

### `sonar/model.py` (39%)

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

### `sonar/engine.py` (38%)

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

### `sonar/feeds.py` (30%)

Untested: `_binance_hour`, `_coinbase_hour`, `current_market`, `_midpoint`,
`_fill_book`, `_iso_to_unix`, `historical_decision_points`.

These *look* like network code and mostly are not — they are parsers with a
fetch at the top. The pattern is already established in
`playmaker/results.py`: split the parse from the fetch, test the parse on a
saved payload, and never let the suite touch the network. Every one of these
should be a fixture test.

A payload-shape change is the realistic failure here, and it is the one that
would silently zero out a price rather than raise.

### `sonar/universe.py` (17%)

Untested: `canonical_title`, `wiki_article`, `article_map`, `_load_cache`,
`_save_cache`, `_throttle`.

Same split. The title-canonicalisation logic in particular is pure string
handling with no excuse for being untested.

### `sonar/server.py` (0%)

The headless HTTP daemon, and now the documented answer for uptime — so it is
about to matter more than it did. `http.server` is testable in-process against
a real socket on port 0. Worth: every route returns 200 with the shape the app
expects, an unknown route 404s, and it serves `docs.html`.

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

1. `model.py` — five tests, no fixtures needed, protects every number on screen.
2. `engine.py` — the tick/enter/settle path, on a synthetic book.
3. `feeds.py` — split parse from fetch, test the parsers on saved payloads.
4. `server.py` — it is the answer for uptime now, and has never been run by a test.
5. The Book tab's trade path end to end.
6. `universe.py`, `charts.py`, `tray.py` formatting.
7. `research/features.py` — before the next study leans on it.

Steps 1 and 2 are the ones worth doing this week. The rest can wait.
