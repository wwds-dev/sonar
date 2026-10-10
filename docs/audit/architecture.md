# SONAR architecture audit — 2026-10-10

Author: `architect` (read-only audit; no code changed). Scope: `sonar/`, `ui/`, `main.py`,
`scripts/`, `packaging/`, `build_app.sh`, `.github/workflows/tests.yml`. Evidence is file:line
from a read of the code; nothing was run. Findings marked *unverified* were reasoned from the
source and not reproduced.

## Shape of the system (one paragraph)
`sonar.core.Live` is the single stateful hub (925 lines). It owns an `Engine` (hourly BTC, `state.json`),
a `Portfolio` (general paper book, `portfolio.json`), five network caches and the poll loop.
`ui/app.py` (3698 lines, one `MainWindow`) and `sonar/server.py` (stdlib HTTP) both drive the same
`Live`. Exactly one process may "drive" (hold `engine.lock`); the other mirrors it over HTTP
("follow mode"). The modules under `sonar/` are mostly clean, leaf-like and well-commented;
the weaknesses are concentrated in the **hand-off between lock holders**, **unsynchronised
mutation of the books from several threads**, and **nested-repo / packaging seams**.

---

## P0 — fix before trusting the run

### P0-1 Lock takeover resumes on stale in-memory state and overwrites the other writer's record
- `sonar/core.py:101` (`Engine(...)` loads `state.json`) and `:121` (`Portfolio(...)` loads
  `portfolio.json`) happen in `Live.__init__`, **before** the lock is attempted at `:629`.
  `_wait_for_lock` (`:654-698`) returns True on acquiring the lock and `run()` proceeds to
  `warmup()`/`_poll()` (`:631-632`). Nothing re-reads either file: `grep` finds `_load()` only
  inside the two constructors (`engine.py:112`, `portfolio.py:186`).
- Scenario: the app is launched while the launchd agent drives (the normal case, `install_agent.sh`
  advertises "you can safely run both"). The window loads the book as of launch. The agent keeps
  settling hours, opening/closing protocol positions, appending to `scorelog`/`equity_log` for
  hours or days. The agent stops (reboot, `--uninstall`, crash, KeepAlive throttle) -> the window
  takes the lock and its first `Engine.save()` / `Portfolio.save()` (`engine.py:155`,
  `portfolio.py:200`) writes the launch-time copy over the agent's newer file. Settled trades,
  equity points and calibration samples vanish; positions the agent closed reappear open and are
  re-marked against barriers. The only recovery is the **daily** `.bak.<date>` (`paths.py:34`), which
  is taken once per day *before the first overwrite*, so it holds yesterday's state, not the
  agent's last good one. This is precisely the "double count / silent wrong numbers" the lock
  exists to prevent, reintroduced by the hand-off. Same for two windows.
- Fix: on a successful acquire in `_wait_for_lock` (and in `run()` after the first-try success,
  which is harmless there), rebuild `self.engine`, `self.book`, `self.positions`, `self.calibration`,
  `_protocol_*` from disk under `self.lock` before `warmup()`. Better: make `Live.__init__` not load
  until the lock is held (construct engines lazily in `run()`), and give followers a read-only
  view. Add a test in `tests/test_follow.py`/`test_two_processes.py`: A writes, B constructed
  earlier takes over, assert B's first save contains A's trades. No existing test I found covers
  state continuity across takeover (`grep takeover tests/` hits only a message string,
  `test_enginelock.py:112`).

---

## P1

### P1-1 A non-lock-holder with no URL can still write the book (`following` is the only guard)
- Every mutating entry point gates on `self.following` only: `core.py:251` (set_protocol), `:407`
  (trade), `:426` (close_position), `:446` (configure). In "read-only, holder has no URL"
  (second window, `core.py:690-695`) `following` is None, so `close_position` closes a position in
  the stale local book and `_mark_book` -> `Portfolio.save()` (`:421-439`, `portfolio.py:200`)
  while another process holds the lock. `configure()` (`:462-468`) calls `engine.set_risk()` ->
  `Engine.save()` (`engine.py:114-118`), and `_rescan()`, which marks and saves the book.
  The UI only disables the LLM button in this state (`ui/app.py:3239-3246`); buy/short/close/protocol
  stay live.
- Also at start-up: `Live.__init__` with `risk_name` calls `engine.set_risk()` (`core.py:105-106`)
  which saves `state.json` before any lock exists (`python main.py --headless --risk X` beside a
  running app).
- Fix: one guard method `_require_writer()` (returns a refusal dict when `read_only and not following`)
  used by `trade/close_position/configure/set_protocol`; defer `set_risk` persistence until the lock
  is held; disable the book buttons in `ui/app.py` when `snap["status"] == "read-only"`.

### P1-2 Books are mutated from several threads with no lock; two writers share one tmp name
- Threads: poll thread (`Live.run` -> `_poll`/`_rescan`/`_mark_book`), `ConfigThread` (`worker.py:78-91`
  -> `configure()` -> `_rescan()` runs a full scan on the config thread, `core.py:468-469`), and the
  **UI thread**, which calls `live.trade()` and `live.close_position()` synchronously
  (`ui/app.py:3183`, `:3191`) and `set_protocol` (`:1786`). `trade()` does `self.book.enter(...)` and
  `_mark_book` with **no** `self.lock` around `Portfolio` (the lock only covers the snapshot dicts).
  `Portfolio.open/closed/cash/equity_log` are plain lists/floats: a UI click during the poll thread's
  `book.mark()` can double-close, lose a `cash` update, or raise "list changed during iteration"
  (swallowed by the bare `except Exception: pass` at `core.py:224-225`, so the scan silently skips).
- Both `Engine.save` and `Portfolio.save` write to a fixed `*.tmp` (`engine.py:176`, `portfolio.py:209`);
  `paths.write_atomically` does likewise (`paths.py:69`). Two concurrent saves of the same file race on
  the tmp: one `replace()` raises `FileNotFoundError` (an `OSError`, mostly swallowed) or one writer's
  bytes interleave. `configure()` -> `Engine.save()` on the config thread runs concurrently with
  `engine.tick()` -> `save` on the poll thread (`core.py:463` vs `:848`).
- `AssetScanner.payload`/`_refresh` (`assets.py:329+`, `_bars` dict at `:334`, `:397`) has no lock, and
  can run on the poll thread and the config thread at once (double network burst + dict mutation).
- Fix: a `book_lock` (RLock) around every `Portfolio`/`Engine` mutation+save; route UI trade/close
  through the poll thread or a single-writer queue; unique tmp names (`tempfile.mkstemp` in the same
  dir) plus `os.fsync` before `replace`; serialise `_rescan` with a non-blocking guard.

### P1-3 Stale-lock reclaim is a check-then-act race; PID reuse defeats liveness
- `enginelock.py:85-102`: `holder()` reads the record, decides it is dead, then `unlink()`s **by path**.
  Two processes starting together can both judge the same stale file dead; A unlinks and creates a
  fresh lock with `O_EXCL` (`:117`), then B's late `unlink()` deletes A's *live* lock and B creates its
  own -> two drivers, silently. Fix: compare-and-delete (re-read and verify pid/`since` still match,
  or `flock`/`fcntl.lockf` on an open fd so the kernel releases it on death and PID files are
  advisory metadata only).
- `_alive` (`:66-82`) treats any live PID as the holder. After a crash and reboot, PID reuse by an
  unrelated process makes the lock look held indefinitely: every launch goes read-only and, because
  `url` may be absent, "waits" forever with only a message. Fix: record process start time (or
  `psutil`-style create time / `ps -o lstart`) in the record and require both to match, or use `flock`.
- `acquire()` degrades to **unlocked** on any `OSError` (`:132-138`), by design. Combined with an
  unwritable shared data dir this yields two un-fenced engines with no signal beyond `held=True`.
  Make the degradation visible (set `read_only`/log) or at least refuse when `SONAR_DATA` is set.

### P1-4 CI depends on two unpinned, differently-owned sibling repos
- `sonar/macro` and `sonar/playmaker` are separate git repos, gitignored (`.gitignore:29-30`), and
  **hard dependencies**: `core.py:24-25` (`macro`), `server.py:97`, `ui/app.py:44-46`, `main.py:26,
  117-122`. A fresh clone cannot import `sonar.core`.
- `.github/workflows/tests.yml:33,37` checks out `Netrunner3000/sonar_macro` and `.../sonar_playmaker`
  at their default-branch HEAD, but both nested repos' remotes are `wwds-dev/*`
  (`git -C sonar/macro remote -v`), as is the parent. Either the org was renamed (redirects work for
  public repos only) or CI is pulling a different/missing repo; *unverified* because I cannot reach
  GitHub. The checkout is also **unpinned**, so a push to either repo changes this repo's CI and a
  built `.app` without any commit here; the parent commit hash does not identify the build
  (`version.py` / `_build_info.json` stamps only the parent).
- The dependency is also **bidirectional**: `sonar/macro/__init__.py` does `from .. import paths`,
  `playmaker/ratings.py` and `scoring.py` import `sonar.research.features/stats` (grep). "Repo per
  module" modules that cannot build without the host are a submodule in all but name.
- Nested repo hygiene: `playmaker`'s last commits are `autosync:` snapshots (`git log`), i.e. work is
  committed by a timer, not by a person; `sonar/macro/.DS_Store` is present; both have pending
  `TODO.md` of their own that the parent's `TODO.md` does not index.
- Fix: make them real submodules (or vendor them into the tree and drop the pretence) with the
  commit pinned in the parent; CI checks out the pinned SHA with the right owner; `version.py` records
  the nested SHAs in `_build_info.json`; remove `autosync` commits from these repos.

---

## P2

### P2-1 The provider layer is documented as a feature but is dead code; there is no data fallback where it matters
- `sonar/providers.py` (294 lines) is imported by nothing (`grep` over `sonar ui main.py scripts`; only
  `tests/test_providers.py` and `tests/test_state_recovery.py:125`). README §Data providers
  (`README.md:425`, `:601-603`, `:990`) presents the switch + fallback chain as live. The module's own
  docstring says Yahoo "already" broke once (quoteSummary -> 401).
- Reality: three independent Yahoo chart clients with no fallback: `assets.py:42,255-300` (`_get`
  returns None for *every* exception, so throttling, bad JSON and a 401 are indistinguishable),
  `backtest.py:56,106-125` (duplicate `_CHART` and a second `fetch_bars` with the same name and a
  different return type), plus `universe.py:111,154`. A Yahoo outage turns the asset board and the
  paper book's marks to nothing; `_mark_book` returns early on empty prices (`core.py:293-295`) so
  open positions silently stop being marked/stopped while the UI shows "live".
  The only real fallback chain is BTC candle Binance -> Coinbase (`feeds.py:114-150`).
- Fix (pick one, then align README): either wire `providers.resolve` into `assets.fetch_bars/_fetch`
  and `backtest.fetch_bars` and delete the two copies, or delete `providers.py` and the README
  claims. Surface "prices stale since T" in the snapshot when marks stop (the book needs an
  explicit staleness state, not an early `return`).

### P2-2 HTTP daemon: no auth, CSRF-able, binds wherever told, hands out a book-writing API
- `server.py:45-50` parses the body as JSON regardless of `Content-Type`, so a web page can issue a
  "simple" cross-origin `text/plain` POST to `http://127.0.0.1:8787/api/trade|close|config|read`
  with no preflight. Any site the user visits can open/close paper positions, flip the protocol
  switch (`/api/config`) or burn LLM budget (`/api/read`); DNS-rebinding likewise (no `Host` check).
  `--host 0.0.0.0` is accepted (`server.py:178`) with the same endpoints. Paper money limits the blast
  radius, but the **calibration record is the product** and this lets a stranger write to it.
  The agent always runs it (plist), so it is always listening. Needs `security-engineer` per AGENTS.md
  step 8 (network + local server).
- Fix: require `Content-Type: application/json` (forces a preflight), check `Host`/`Origin` against
  loopback, add a per-install bearer token written beside the lock (the follower reads it from there),
  refuse non-loopback `--host` without an explicit flag.
- `GET /api/macro` calls `live.macro.get()` on the handler thread (`server.py:97`), i.e. a FRED fetch
  on request threads (6 series x timeout) with no lock around the cache -> thundering herd. Serve the
  cached value only.

### P2-3 Follower forwards writes synchronously on the UI thread; failure modes are text-only
- `ui/app.py:3183,3191` call `live.trade/close_position` on the UI thread. While following, that is a
  blocking `urllib` POST (`core.py:773-780`, 2s timeout) plus a `_mirror_book` GET (`:797`): a stuck
  agent freezes the window for up to ~4s per click, and the comment "nothing to wait on" (`:3178`) is
  false in follow mode. Also `_forward` swallows `Exception` into a message, so a half-applied POST
  (server wrote, response lost) is reported as failure and a retry double-opens. Make the forward
  idempotent (client-generated id) and run it off the UI thread via the existing Thread pattern.
- `_mirror` (`core.py:700-736`) trusts the holder's `/api/state` JSON blindly into `self.snapshot`;
  a holder on a different build (app vs checkout agent, a documented scenario in `portfolio.py:559`)
  can send a different shape. No protocol version in `/api/state` or in the lock record.

### P2-4 State files: no schema version; unknown fields are dropped on rewrite
- `Engine._load` (`engine.py:134-152`) and `Portfolio._load` (`portfolio.py:189-198`) use `.get()` with
  defaults and `_trade_from`/`_position_from` **discard unknown keys** (`engine.py:717-727`,
  `portfolio.py:559-570`). That makes old->new and new->old load safe (good, and well tested) but the
  next save by the older build **strips the newer build's fields permanently**. App-vs-agent skew
  (frozen bundle vs `.venv` checkout, same `SONAR_DATA`) makes this a live scenario, and rollbacks too.
  There is no `"schema": N` key, so a migration cannot know what it is migrating, and "n_scored_total
  = d.get(...) or len(scorelog)" (`engine.py:146`) is an implicit migration with a lossy fallback
  (a legitimate 0 becomes `len(scorelog)`).
- Writes lack `fsync` before `replace` (`engine.py:176-178`, `portfolio.py:209-211`,
  `paths.py:64-71`): atomic against a crash of the process, not against power loss.
- `paths.read_state` (`:90-135`) is good (moves aside, falls back to newest parseable backup) but a
  parse-valid, semantically-truncated file (e.g. `{}` or missing `trades`) is accepted and then
  overwritten by the next save, and the backup is daily only. Add a minimal shape check (required keys)
  and an `unreadable` path for it; keep N rolling backups per day or on every settle.
- Fix: add `"schema": 1` + preserve-unknown-keys round trip (`extra: dict` on Trade/Position), refuse
  to write a file whose schema is newer than this build understands.

### P2-5 `core.Live` is a god object and `ui/app.py` is a god module
- `Live` (925 lines, `core.py:76`) mixes: poll loop, lock/follow protocol, HTTP client (`_fetch/_post/
  _forward`), protocol scheduler, book marking, LLM read orchestration, snapshot rendering
  (`_build`, 318 lines, `core.py:859`). Follow mode is ~150 lines of client logic with no seam, which
  is why every public method begins with `if self.following:` (six occurrences).
- `ui/app.py` is 3698 lines, 103 methods in `MainWindow`, tab builders of 150-210 lines
  (`_lab_tab` 211, `_portfolio_tab` 157, `_playmaker_tab` 148). Business logic leaks in:
  `ui/app.py:44-46` imports `playmaker.devig/staking`, `risk`, and `:2399` calls `backtest/replay`
  directly; `ui/app.py:513` calls `venues`. The UI also reads `live.horizon`, `live.risk` directly
  (`:3257`, `:3273`) without the lock.
- Fix (incremental, no behaviour change): extract `Follower` (mirror/forward/_fetch/_post) and
  `ProtocolScheduler` from `Live`; give `Live` a `Writer` strategy (`LocalWriter` / `RemoteWriter`) so
  the six `if self.following` branches become polymorphism; split `ui/app.py` per tab into `ui/tabs/*.py`
  (a `ui/tabs.py` already exists at 415 lines, which is only the tab bar). Gate: the spec says module
  boundaries need owner approval (AGENTS.md step 3).

### P2-6 Swallowed exceptions hide real failures in the engine loop
- 49 `except Exception` sites in `sonar/ui/main` (excluding nested repos); in `core.py` the scan body
  is `try: ... except Exception: pass` (`:222-226`): a bug in `_mark_book`, `calibration.report`,
  `alerts` or `_protocol_scan` makes the whole rescan a no-op with no log, no counter and no
  snapshot field, while `_scan_at` is still advanced (`:226`). Same in `warmup` (`:154-165`), `_sigma`
  (`:807-812`), `_seed_account_history` (`:358-359`). The run-health block (`engine.run_health`) cannot
  see any of it. There is no logging module in use at all.
- Fix: a tiny `log = logging.getLogger("sonar")` writing to `data/logs/`, a `last_error`/`error_count`
  in the snapshot and run-health, and narrow the `except` to the network/parse errors that are
  expected.

---

## P3

- **P3-1 Dead / near-dead code.** `providers.py` (see P2-1), `universe.py` (292 lines, no importer
  outside tests), `alpaca.py` + `portfolio.default_broker` (`portfolio.py:135-155`; nothing calls it,
  `Portfolio(...)` is built with the default `PaperBroker` at `core.py:121`, so `poll_fills()` /
  `settle_fills()` / async-fill paths are exercised only by tests), `execution.py` (732) + `costs.py`
  (127) which `main.py` force-imports solely for the self-test and `build_app.sh` force-bundles
  ("nothing imports them at all yet"). ~1,500 lines carried, bundled and tested for features that are
  not reachable. Either wire them or move to `experiments/` and drop the `--hidden-import`s.
- **P3-2 Stale build artifacts.** `SONAR.spec` (untracked and matched by `.gitignore` `*.spec`) lists
  hidden imports that differ from `build_app.sh` (`SONAR.spec:9` vs `build_app.sh` flags; it also has no
  `--exclude-module` list). `build_app.sh` does not use it. Delete it, or make it the single source.
- **P3-3 Duplicated plumbing.** Three copies of "fetch Yahoo chart" (`assets.py:42`, `backtest.py:56`,
  `universe.py`), five copies of a User-Agent/urlopen helper (`feeds.py:40`, `providers.py:49`,
  `assets.py:253`, `events.py:55`, `news.py:224`, `institutions.py:118`, `macro`). One `http.py`
  with timeout, retry/backoff, status classification, optional cache would also give P2-6 a place to log.
- **P3-4 Two functions named `fetch_bars` with incompatible return types** (`assets.py:282` returns
  `[(ts, close)]`, `backtest.py:106` returns `Bars`). Rename one.
- **P3-5 Threading style.** Qt threads are `QThread` subclasses overriding `run()` (`ui/worker.py`), so
  `thread.quit()` is a no-op (stated in `app.py` `shutdown`) and shutdown relies on `os._exit`
  (`ui/app.py:3485-3507`) with the lock released manually. The `os._exit(0)` path skips `Engine.save`
  (fine today because save-on-change) but also skips any future flush. `PollThread.run()` ignores the
  `role`/`url` args of `Live.run`, so the app registers with default `role="app"`, which is intended.
  Nested `ThreadPoolExecutor`s: `_seed_account_history` (`core.py:349`) inside `_rescan` inside
  scanner pool (`assets.py:393`) - OK, but each opens its own pool per call.
- **P3-6 Time and calendar.** `_protocol_scan` uses local `time.strftime("%Y-%m-%d")` (`core.py:263`)
  for "once per day"; a DST/timezone change or a laptop travelling re-opens or skips a day. Use UTC.
  `_protocol_last_day` is saved only after the entries loop, so a crash mid-loop re-enters positions
  next scan (guarded only by `position_for`/`n_open`).
- **P3-7 Config & paths.** The checkout default (`data/`) and the frozen default (Application Support)
  differ (`paths.py:150-157`), so a source run silently starts a second book unless `SONAR_DATA` is
  set; the agent plist sets it but a developer's `python main.py` does not (documented in README, but
  a single-line stderr warning at start-up when `state.json` exists in the *other* location would
  prevent a repeat of the "weeks of a second run" incident).
- **P3-8 Size/complexity outliers** beyond P2-5: `assets.AssetScanner._refresh` 135 lines,
  `engine.buyability` 129, `execution._trade_from` 114 (a third `_trade_from`, besides `engine` and
  `portfolio`'s `_position_from`; unify the "tolerant dataclass loader" in `paths.py`).
- **P3-9 Repo hygiene.** `data/` holds live state in the working tree (gitignored, fine) including
  `engine.lock`; the local copy of `data/engine.lock` is a PID file that a checkout on another machine
  must not inherit (already ignored, `.gitignore`); `.DS_Store` files committed inside the nested
  repos; `AGENTS.md`, `CLAUDE.md`, `docs/`, `.claude/*` are untracked at HEAD (git status) so the
  process documents are not under version control yet.

---

## What is good (keep)
- Single-writer lock design, with zombie handling and re-entrancy (`enginelock.py`), and follow mode
  (read-only mirror + action forwarding) is a sound idea; P0-1/P1-1 are gaps in the hand-off, not in
  the concept.
- `paths.read_state` recovery order (move aside -> newest parseable backup -> clean start, original
  kept) and `daily_backup` with pruning; `read_preferences` for human-edited files.
- Fetch-then-lock discipline in `_rescan` and `_poll` (network never under `self.lock`), and the
  documented history behind it.
- `Live` is Qt-unaware; `server.py` and the GUI share it. The module graph under `sonar/` is acyclic
  and shallow (scoring/model/risk/horizon are pure; feeds/assets/news/events are I/O edges).
- Self-test (`main.py --selftest`) guarding the frozen-bundle failure modes; broad test suite (66 files).

## Suggested order
1. P0-1 (reload on takeover) + test. 2. P1-1 guard on writes while not the writer. 3. P1-2 book lock +
unique tmp files. 4. P1-3 lock hardening (`flock`). 5. P1-4 pin/own the nested repos and fix CI owner.
6. P2-2 with `security-engineer`. 7. Decide P2-1 / P3-1 (wire or delete). 8. P2-4 schema key before the
next state-shape change. Items touching state files, threads, the lock or module boundaries are
**owner-gated** per AGENTS.md step 3.
