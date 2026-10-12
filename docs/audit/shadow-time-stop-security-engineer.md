# Security review: time-stop shadow readout (ADR 0002)

- Role: security-engineer, read-only. Diff `cf84642..cca9428` on `claude/zealous-mclaren-8985d0`,
  2026-10-12. Saved by the orchestrator from the agent's report.
- **Playbook is stale:** `docs/playbooks/security-engineer.md` is `status: baseline`, last-reviewed
  2026-10-10, never radar-verified; it added nothing beyond AGENTS.md.
- **Evidence:** the diff, `docs/company/app-context.md`, prior audits (`security.md`, `t0-7-…`,
  `t1-8-…`), the radar note (`docs/company/radar-notes/2026-10-12-security-shadow-time-stop.md`) and
  the spec. Three scratch probes against the worktree code with the main `.venv`, `SONAR_DATA` at a
  scratch directory and `PYTHONDONTWRITEBYTECODE=1`: `shadow_texts` with crafted dicts; `ShadowGrade`
  offscreen; `shadow_time_stop` on a synthetic book with garbage bars.
- **Not touched:** the live data directory, the app, the launchd agent, the main checkout. No secrets read.

## Threat model
- **Assets:** integrity of the pre-registered gate (looks, z, "crossed", "test finished"); window
  availability; Yahoo's goodwill (rate limits); book data served on localhost.
- **Trust boundaries:** (a) holder vs Yahoo's unofficial chart endpoint (JSON untrusted); (b) follower
  vs whatever answers at the holder URL in `engine.lock` (`/api/book` untrusted; boundary (2) of
  `docs/audit/security.md`: any same-user process can already lie to a follower); (c) web pages vs the
  loopback daemon (T0-7 Host/Origin rules apply).
- **Entry points:** `assets.fetch_bars` → `Live._shadow_fetch` → `calibration.shadow_time_stop`
  (holder); `GET /api/book` (`sonar/server.py:178-182`); `Live._mirror_book` (`sonar/core.py:1224-1242`)
  → `ShadowGrade.render` (`ui/app.py:964`), every `REFRESH_MS` = 1000 ms on both pages.

## Findings

### P2-1: An `OSError` escapes `ShadowGrade.render` and stops the whole window from refreshing
- **Where:** `ui/app.py:696` (`_sh_date` → `time.localtime(t)`), `:811` (`computed_at` →
  `time.localtime(at)`), `:970-971` (except tuple lacks `OSError`), call sites `:2436`, `:4163`.
- **Evidence:** on macOS `time.localtime(1e17)` raises `OSError: [Errno 22]` (`1e16` works, `1e300`
  raises the caught `OverflowError`). `ShadowGrade.render({"n_entered":50,"n_reached":30,"looks":[],
  "computed_at":1e18}, 28.0)` raised `OSError`; likewise `next_t` = 1e18 and `looks[].due` = 1e18.
- **Scenario:** a finite timestamp ≥ ~1e17 from a hostile/buggy holder, schema skew, or a corrupt
  `opened_at` feeding `t_due`. `render` raises inside `_refresh_book()`, the first statement of
  `MainWindow.refresh()`, so every tick stops there: book, portfolio, wire, screener, macro and status
  line all freeze while the payload stays. Contradicts `ui/app.py:972-973` ("say so rather than show
  half of it").
- **Fix:** add `OSError` to the tuple; better, clamp timestamps outside `0 ≤ t ≤ 4e10` to `None`/"n/a"
  in `_sh_date` and the `computed_at` branch. Test with `computed_at=1e18`.

### P2-2: A wrong close, not a failed one, becomes a graded outcome and can rewrite a look after it is evaluated
- **Where:** `sonar/calibration.py:356-360` (gap check runs `p.hit()` on any finite close); `:477-480`
  (only non-finite filtered); `sonar/core.py:540-553` (bars refetched every UTC day);
  `sonar/assets.py:292` (`indicators.quote[0].close`).
- **Evidence (synthetic LONG at 100, stop 98, target 103):** one 0.0 close → `stop`, gap, R −1; one −5
  close → `stop`, gap, R −1; one 1e9 close → `target`, gap, R +1.5; one NaN close → dropped (correct).
- **Scenario:** bad ticks grade an entry. Yahoo's chart `close` is reported (third-party sources, not
  checked live) to be split-adjusted: a split after an entry rescales every earlier bar; with nothing
  persisted and a daily recompute, an entry graded `time` can flip to a gap STOP/TARGET and an
  evaluated look's z changes — weakening "evaluated once" beyond Build note 6's `n_no_price` case.
  Related: `t_cut` (`calibration.py:349`) is never compared with `now`; a bar stamped in the future
  makes the in-progress T bar count as final (verified: `no_price` → `time`, R = 1.25).
- **Fix:** do not grade from implausible bars — reject closes ≤ 0; reject a series whose close near
  `opened_at` is far from `p.entry` (e.g. ratio outside [0.5, 2]); reject bars stamped after `now`;
  request `events=split` and refuse to grade across a split. Each counts as `wait_price`/`no_price`,
  never a guess. Freezing evaluated looks in memory is an ADR §7 decision (model-validator, architect).

### P3-1: A follower takes `crossed` and `evaluated` on trust and can show contradictory verdicts
- `ui/app.py:820-830`. A look with `"crossed": "no"` (truthy) and `z: 0.30` rendered "crossed the line
  … z = +0.30 … The test ends here." A single look with `evaluated: true` renders "Three looks, no
  crossing … The test is finished."
- **Fix:** require `is True`; re-derive crossed from `abs(z) >= calibration.SHADOW_BOUNDARY` and
  `evaluated`; require `k ∈ {1,2,3}` and `n == SHADOW_LOOKS[k-1]`; otherwise "unreadable".

### P3-2: Lists from the holder have no size bound; a large payload can freeze the UI
- `ui/app.py:889`, `:895`, `:915` loop over `looks`/`bands` unbounded; `sonar/core.py:1239` accepts any
  dict; `sonar/core.py:1269` `r.read()` unbounded (pre-existing). 20,000 bands: 9.2 s to render offscreen;
  200,000 looks: 28 MB of label text in 1.5 s of formatting; repeated every 1 s.
- **Fix:** slice `looks[:len(SHADOW_LOOKS)]` and `bands[:len(calibration.BUCKETS)]`; cap the response
  size in `Live._fetch`.

### P3-3: One malformed bar fails the whole readout for the rest of the UTC day
- `sonar/calibration.py:478`, `sonar/core.py:553`. A timestamp of `10**400` raised `OverflowError` in
  `float(t)`, aborting `shadow_time_stop` for every symbol. Fails closed (last good readout + `error`)
  but the bad series is cached until the next UTC day.
- **Fix:** per-row `try` in the cleaning loop, or validate in `_shadow_fetch` and treat the symbol as
  having no bars.

### P3-4: The daily fetch runs on the scan thread, and its request count only grows
- `sonar/core.py:302` (before `_protocol_scan`), `:550` (8 workers, no `_stop` check),
  `sonar/assets.py:255` (8 s per socket operation). `shadow_needs_bars` stays true for every entry past T
  that the book did not settle before T; nothing persisted, so graded entries are refetched daily; the
  count tends to the number of distinct protocol symbols (≤ ~129). Worst case with timeouts:
  ceil(129/8) × 8 s ≈ 2 min once per UTC day, delaying marking, the protocol scan and shutdown. Not
  measured.
- **Fix:** cap the due list per pass (e.g. `ROLL_BATCH`) and carry the rest; or check `_stop` and a time
  budget; optionally cache graded `time` outcomes in memory for the process lifetime.

## Checked, no finding
- **Markup injection:** all five `ShadowGrade` labels are `Qt.PlainText` (confirmed at runtime); the
  heading is a static `SHADOW_WORDS` entry.
- **Holder text / format strings:** `error` cut to 80 characters, plain text; templates are constants.
- **Payload numbers:** `_sh_num` rejects bool, NaN, inf; huge ints raise a caught `OverflowError`.
- **Mirroring:** a follower keeps only `None` or a dict (`core.py:1239`); missing key → "unavailable";
  a follower never fetches or computes (`core.py:510`), asserted by a test.
- **Requests to Yahoo:** symbols URL-quoted (`assets.py:288`; `safe='/'` leaves `/`, but the host is
  fixed and protocol symbols come from scan rows, `core.py:620-624`); range from a fixed table; 8 s
  timeout; one request per symbol per UTC day, failures included (`core.py:540`, `:553`).
- **A failed fetch never becomes a number:** `get()` → `None`; `b or None`; falsy filtered; the entry
  ends `wait_price` then `no_price`. NaN/inf dropped; unsorted timestamps sorted.
- **Locks:** copied under `book.lock`; fetch and compute outside both locks; only the assignment under
  `self.lock` (`core.py:512-526`); `_shadow_bars` used only by the poll thread.
- **Data exposure:** `shadow.entries` derivable from the already-served `positions`; the Host check
  (`server.py:69-72`) still applies; no CORS headers; no secrets; the static web UI does not read
  `/api/book`.
- **No file writes, secrets or new dependencies:** grep of added lines; `pyproject.toml` change is pytest
  markers only; no requirements, spec, build script or plist changed.
- **Test isolation:** conftest guards point `user_data_base` at a temp directory and block `urlopen` and
  `connect`; new tests stub `fetch_bars` and `_fetch`; `test_follow` uses a loopback FakeAgent with its
  lock file in the temp directory; no test references the real data directory. Minor, pre-existing:
  `NetworkUsedInTest` subclasses `OSError`, so `_get`/`get()` would turn an accidental network call into
  "no bars" rather than failing.
- **Pre-registration:** the only path that computes outcomes for the real book is the holder engine
  itself, if this branch's app/server became the holder on the default data directory (e.g. while the
  agent is stopped). Run worktree builds with `SONAR_DATA` set. TESTPLAN 11.16 runs after release by
  design. Nothing was computed for the real book in this review.

## Not verified
Live Yahoo responses (incl. whether `close` is split-adjusted); PySide6's handling of an exception
escaping a `QTimer` slot (only that `render` raises); the scan-thread stall in an outage; a dependency
audit (`pip-audit` not installed; no dependency changed); the full suite.

**Verdict:** no P0 or P1. Fix P2-1 before release (one line plus a test). P2-2 needs an ADR §7 decision
(model-validator, architect). P3s to the backlog.

Sources: [AmiBroker forum: adjusted data via Yahoo Finance](https://forum.amibroker.com/t/adjusted-data-via-yahoo-finance/39718),
[clj-yfinance docs](https://cljdoc.org/d/com.github.clojure-finance/clj-yfinance/0.1.8/api/clj-yfinance.core),
[yahoo-finance2 chart module](https://jsr.io/@gadicc/yahoo-finance2/doc/modules/chart).
