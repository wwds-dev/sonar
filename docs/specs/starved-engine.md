# Spec: Starved engine (agent CPU priority and follower timeout)

- Status: Define approved 2026-10-19 (with changes from `docs/audit/starved-engine-domain-finance.md`)
- Owner approval: Define gate approved 2026-10-19
- Priority: **P1** (operations audit wave 2, P1-2; tier-3 item 2)
- Radar note: reuses `docs/company/radar-notes/2026-10-14-feature-alarm-delivery.md` (launchd row, under 30 days old)
- Evidence: `docs/audit/alarm-delivery-osascript-diagnosis.md` (verdict: starvation, not TCC)

## Problem
The owner runs the paper agent on a shared dev Mac that is often heavily loaded. On that Mac, the agent gets too little CPU to keep its own schedule.
- **Priority.** The plist sets `ProcessType Background` and `Nice 5` (`packaging/com.netrunner3000.sonar.plist:65-70`).
  The live agent runs at `PRI 4`; a normal process runs at 20. `launchctl print` shows `spawn type = background (5)`.
- **Slow answers.** `/api/health` took 3.0-24.5 s and `/api/config` 3.5-20.7 s (audit table). `/api/config` is a dict
  build with no I/O. One health response was a 503. Load average was 97-182.
- **Late polls.** `PRICE_EVERY` is 4 s (`sonar/core.py:88`), but `last_poll_age_s` reached 22 s. Poll outages of
  12-24 min happened at least 7 times in three days. Whether starvation causes them is **not verified**.
- **Followers give up.** `FOLLOW_TIMEOUT` is 2.0 s (`core.py:111`), for both `_fetch` and `_post` (`core.py:1800-1811`).
  After 3 failed rounds in a row, a follower window shows "not answering" (`core.py:1731-1738`). With health at 3-24 s,
  a window opened now would show that. There are 913 client-disconnect tracebacks in `agent.err.log`, which fits
  clients timing out (which client is not identified).
- **Measured cause.** Two throwaway launchd jobs ran side by side. The `Background` + `Nice 5` job had 6 of 10 `osascript`
  runs over 10 s (max 19.5 s) and took about 47 s to spawn. The `Standard` job, with no `Nice`, had 0 of 10 over 10 s
  (max 4.9 s), at a *higher* load (111-118 against 77-109). Diagnosis §4.

The 30-day clean run (due 2026-11-09) depends on poll freshness and scored-hour coverage. Today both depend on what else the owner happens to run.

## User and goal
**User:** the owner. He runs the paper agent, opens follower windows on it, and uses the same Mac for other work.
**Goal:** the agent keeps its 4 s poll and answers `/api/health` in about a second at the load seen in the audit,
without making the owner's interactive work noticeably slower.

## Success measures (all must be shown)
1. **Test: plist guard.** A test reads `packaging/com.netrunner3000.sonar.plist` with `plistlib`. It asserts
   `ProcessType == "Standard"` and that there is no `Nice` key. A second test renders the plist through
   `install_agent.sh`'s plistlib step into a temporary file and asserts the same. This proves the setting reaches the
   installed plist.
2. **Side-by-side measurement, done in Build without touching the live agent.**
   - **Setup.** Two throwaway launchd jobs run at the same time: `com.netrunner3000.sonar-diag.bg` (today's
     settings) and `com.netrunner3000.sonar-diag.std` (the new settings).
   - Each job runs the built app (or the checkout) with `--headless`, on its own port (8788 and 8789), with its own
     scratch `SONAR_DATA=$(mktemp -d)/data`.
   - The jobs are loaded with `launchctl bootstrap gui/$(id -u) $D/<v>.plist`, never from `~/Library/LaunchAgents`,
     and removed with `bootout` afterwards.
   - **No phone pushes (domain P1-1).** A diag engine must not send ntfy pushes: they would look the same as the live
     agent's. The diag plists set an env switch (for example `SONAR_ALARM=banner-only` or `off`); the Architect
     decides the mechanism. Today `--headless` always reads the Keychain topic (`server.py:431`), so this switch is a
     prerequisite for measure 2.
   - **Protect the live agent's data sources (domain P1-2).** The diag plists carry keyless providers only (no keyed
     env such as Alpha Vantage, Twelve Data or Finnhub). Starts are staggered, so the two cold 129-instrument scans
     do not run at once. The run is outside US market hours. The window's start and end are logged in the 30-day run
     record.
   - **Backups stay in scratch (domain P3-2).** The diag plists set `SONAR_BACKUP_DIR` to a directory inside the
     scratch dir (`paths.py:45`), so pruning never touches the live book's off-disk copies.
   - **Sampling.** Every 30 s for 60 min, sample both ports with `curl -m 60 -w '%{time_total}'` on `/api/health`
     and `/api/config`. Record `last_poll_age_s` and the 1-min load average with each sample.
   - **Bar for `std`:**
     - health p50 ≤ 1 s, p95 ≤ 3 s, max < 10 s;
     - `last_poll_age_s` p95 ≤ 12 s (3 × `PRICE_EVERY`), and never over `HEALTH_MAX_POLL_AGE` (120 s) unless a
       provider failure is logged at that time;
     - 0 of 10 `osascript` banners over 10 s, using the diagnosis probe in the same job class;
     - `std`'s health p95 is at most half of `bg`'s.
   - **Valid only under load.** The run counts only if the 1-min load is ≥ 50 for most of the hour. Otherwise the
     result is "not determined" and the run is repeated.
   - **Output.** Raw numbers go to `docs/audit/starved-engine-measurement.md`. It holds only latency, poll age, load
     and CPU, with no book, P&L or score figures (domain P2-2). The scratch dirs are deleted afterwards, and nothing
     else is copied out of them.
3. **Interactive cost.** During the same run, record each job's CPU time (`ps -o cputime` at the start and at the end).
   Bar: `std` averages ≤ 5% of one core. The live agent showed 0.0% CPU in the diagnosis, so the change is expected to
   alter *when* the agent runs, not *how much*.
4. **Installed agent, after the single restart.** Run the same sampler against port 8787 every 5 min for 7 days,
   read-only. Bar:
   - health p95 ≤ 3 s, and no 503 from `poll` age that is not explained by a logged provider failure;
   - the count of poll/scan alarms is compared with the 7 outages in 3 days before the change, and reported with N;
   - `notify.banner.failures` per banner attempt, reported with N.
5. **Follower.** Point a follower window at the `std` job (port 8789) for the 60 min of measure 2. Bar: it never shows
   "not answering". By default a follower follows the live agent, with write access to the live book (domain P1-3).
   So:
   - launch it from the checkout with `SONAR_DATA` set to the `std` job's scratch dir;
   - confirm in the window that it follows `127.0.0.1:8789` before the hour starts;
   - take no trade, close, undo or config action during the hour. The `FOLLOW_TIMEOUT` decision is recorded in the spec (see Scope (b)).
6. **RUNBOOK.** The RUNBOOK states the agent's priority and the measured numbers. Each number carries its date
   range, N, load range and job class. The comparison with earlier outages is labelled indicative, not causal
   (domain P3-1). It also says that heavy local load
   still degrades the paper run, and that monitors need a timeout of 30 s or more.

## Scope
- **(a) Plist priority.** Set `ProcessType` to `Standard` and remove `Nice`. Update the plist comment so it gives the
  reason. The new setting reaches the agent **only** through `scripts/install_agent.sh`:
  - it re-renders `~/Library/LaunchAgents/com.netrunner3000.sonar.plist` from `packaging/` with plistlib, which
    copies every template key (`install_agent.sh:204-232`);
  - it then runs `bootout` and `bootstrap` (`:238-249`);
  - `scripts/install_app.sh` step 5 calls it (`install_app.sh:110`), and `./build_app.sh --install` calls that.

  No manual edit of the live plist is needed or allowed.
- **(b) Follower timeout.** Measure first, then decide; do not change by default. If the `std` health p95 is ≤ 1 s, keep
  `FOLLOW_TIMEOUT = 2.0` and the 3-failure rule. If it is not, the Architect proposes a change, for example a longer
  timeout for the read-only `_fetch` only. `_post` (`core.py:1806-1811`), called from `_forward` (`core.py:1813-1830`), forwards trades, knob changes and
  the LLM read (`core.py:1310`; a retry could bill twice), and a
  longer wait there changes what a timeout means for an action that may already have happened.
- **(c)** The measurements, the evidence file and the RUNBOOK lines described above.
- **One restart.** Item 1 (`alarm-delivery`, d548361, v2.362) and this item ship in one build and one
  `./build_app.sh --install`. The live agent restarts **once**, and only with the owner's yes (alarm-delivery Owner
  decision 6).

## Non-goals
- Any change to trading, scoring, the book or alarm thresholds. Real money stays out of scope.
- Touching live state: no read or write of `~/Library/Application Support/SONAR*`, and no `kickstart`, `bootout` or
  signal to `com.netrunner3000.sonar` during Build or Verify.
- Restarting the live agent without the owner's explicit yes.
- **`ProcessType Adaptive`.** Per `launchd.plist(5)`, Adaptive moves a job between Background and Interactive based on
  XPC activity. SONAR uses no XPC, so it would stay Background. `Interactive` is meant for apps, not agents.
- A precomputed or cached `/api/health` answer (audit fix item). Deferred: build it only if measure 2 fails under `Standard`.
- Client-disconnect traceback noise and log rotation (audit P2-2), the external probe (its own P1), and moving the
  agent to an always-on host (owner decision, see question 3).

## Challenge to the request
The plist change is small, and it is backed by a controlled measurement. That makes it the right first step. The
`FOLLOW_TIMEOUT` change is not: raising the timeout would hide slowness rather than remove it. It also touches the
`_post` path that forwards actions. So (b) is a measured decision, not a default edit. Starvation only shrinks under
`Standard`: at load 182 everything is slow, and this spec does not promise otherwise.

## Risks
- **Interactive cost.** Under `Standard`, the agent competes equally with the owner's apps and builds. Measure 3 bounds
  the cost, but the owner's own sense of lag is not measured.
- **Two extra engines during measure 2.** Two more headless engines poll market APIs for an hour, so the machine's
  request rate to the data sources is about triple. That is a risk of being rate-limited (README: "got this machine throttled"). Mitigation: 60 min only, keyless
  providers only, staggered starts, and a window outside US market hours (measure 2). Whether this stays within the
  provider terms is not verified.
  The poll interval is not lengthened to compensate, because that would change what is being measured.
- **Engine lock.** Each throwaway job needs its own `SONAR_DATA`. One agent per data directory is an invariant
  (RUNBOOK §3).
- **Not the whole cause.** If measure 4 shows that the poll outages persist under `Standard`, they come from providers, not
  starvation. That outcome gets reported, not hidden.
- **The 30-day run.** The restart happens before 2026-11-09. It is shared with item 1, so there is only one.

## Open questions for the owner
1. **Decided 2026-10-19: Standard is approved.** Rationale as recorded at Define: the only recorded reason for Background is the plist comment "Low priority: this is
   a background poller, not interactive work" (`plist:68`). The CHANGELOG has no earlier rationale (`CHANGELOG.md:39`
   only cites the diagnosis). `git log -S ProcessType` was **not run** in this session (no shell); the Architect
   should run it. Recommended: Standard. The agent's CPU use is near zero, so it gains on-time scheduling and costs
   little.
2. **Answered 2026-10-19.** The rate-limit question for measure 2's two extra engines is answered by the domain P1-2
   fix: keyless providers only, staggered starts, outside US market hours, and the window logged.
3. Long term: keep the agent on this shared dev Mac (and accept that load degrades the paper run), or plan an
   always-on host as a separate item?
4. Is a 7-day window for measure 4 enough, given that it overlaps the 30-day run?

## Architecture

Architect pass 2026-10-19. Playbook `docs/playbooks/architect.md` is `status: baseline`, so this pass follows
`AGENTS.md` and the role prompt only. Radar: the stack pass in `docs/company/radar-notes/2026-10-14-feature-alarm-delivery.md`
is reused. Apple recommends `ProcessType` over `Nice`, and there are no new dependencies (stdlib only). ADR:
`docs/adr/0006-agent-processtype-standard.md`.

**History check.** `git log -S ProcessType -- packaging/ scripts/` finds one commit, `75956b6` ("autosync", 2026-08-05).
That commit created the plist with `Background` + `Nice 5` and the comment at `plist:68`. No other rationale exists. This
answers open question 1's "not run".

### A1. Plist priority (Scope a)
- **Change.** In `packaging/com.netrunner3000.sonar.plist:65-70`:
  - set `ProcessType` to `Standard`;
  - delete the `Nice` key and its comment;
  - replace the comment with the reason: "Standard: under Background + Nice 5 the agent missed its 4 s poll and took
    3-24 s to answer on a loaded Mac (docs/audit/alarm-delivery-osascript-diagnosis.md §4); it uses near-zero CPU".
- **The installed plist cannot keep a stale `Nice`.** `install_agent.sh` loads the **template** (`PLIST_SRC`,
  `install_agent.sh:38`, read at `:213`), not the installed file. It overwrites five keys (`:217-221`), dumps a fresh
  dict to a temp file (`:223`) and `mv`s it over `PLIST_DST` (`:232`). The installed plist is replaced whole, so a key
  that was removed from the template disappears. No code change is needed in `install_agent.sh`.
- **Tests** (measure 1), in `tests/test_agent_from_bundle.py`, using the existing `env` fixture (`:63-88`):
  1. `plistlib.load` of the template: `ProcessType == "Standard"`, `"Nice" not in p`, and
     `p["EnvironmentVariables"]["SONAR_ALARM"] == "on"` (this guards A2's default; amended at the fix round,
     security P2-1).
  2. Run `install_agent.sh` in bundle mode and in `--checkout` mode, then read `_plist(env)`: the same three asserts.
  3. **Stale key.** Pre-seed `$HOME/Library/LaunchAgents/com.netrunner3000.sonar.plist` (fake HOME) with
     `ProcessType Background` + `Nice 5`. Run the install, then assert that `Nice` is gone and the type is `Standard`.
- **Mutation-check.** Put `Nice` back in the template: tests 1-3 must fail. Change `load(src)` to load `dst`: test 3
  must fail.

### A2. Alarm off-switch for diag engines (domain P1-1)
- **Mechanism: env var `SONAR_ALARM`.** Parsed in one place, `sonar/alarm.py`, by a new `alarm_mode(environ) -> str`.
  The value is stripped and lower-cased.

  | Value | Keychain read | ntfy | Banner |
  |---|---|---|---|
  | unset or `""` or `on` (default, the live agent) | yes, as today (`alarm.py:629-641`) | as today | as today |
  | `banner-only` | **no** | not configured, `reason` "off (SONAR_ALARM)" | as today |
  | `off` | **no** | not configured, `reason` "off (SONAR_ALARM)" | not configured, `reason` "off (SONAR_ALARM)" |
  | anything else | **no** | as `banner-only` | as `banner-only`, plus one `say()` line naming the bad value |

  - An unknown value fails closed for the **phone**. A typo in a diag plist must never push. The live agent is not
    affected: its plist **pins `SONAR_ALARM=on`** (amended at the fix round, security P2-1). A per-job value beats a
    global `launchctl setenv`, so a stray `launchctl setenv SONAR_ALARM off` cannot silence the live phone alarm. The
    template carries it, and `install_agent.sh` also sets it when it renders the plist (test A1.1 on the template, the
    rendered plist, and a template that lost the key).
  - Under `banner-only`, `off` and an unknown value, the Keychain is **not read at all**. A diag engine never holds
    the topic.
- **Where it is read.**
  - `from_keychain` (`alarm.py:629`) gains `mode: str = "on"`. Default `"on"` keeps every existing caller and test
    unchanged.
  - `BannerChannel.__init__` (`alarm.py:209-212`) gains `off_reason: str | None = None`. When set, the channel has
    `configured = False` and exposes `reason`, which `_state` already reports when present (`alarm.py:620-621`).
  - `server.main` (`server.py:431`) passes `mode=alarm.alarm_mode(os.environ)`. The say-line at `alarm.py:636-637`
    reads "push alarms: off (SONAR_ALARM=off)".
- **Watchdog and Heartbeat (`server.py:437-438`) stay unchanged.** With no configured lane, `Notifier.send`
  (`alarm.py:461-497`) queues nothing and returns `Delivery(required=None)`.
  - `undelivered` stays false: only a configured ntfy lane sets it (`alarm.py:427-432`). So `/api/health` does not go
    red from the switch.
  - The heartbeat marks `alarm.json` in the scratch dir and sends nothing.
  - The "stopped" notice is never marked delivered (`server.py:362-363`), so it is re-attempted hourly to nowhere.
    That is harmless.
- **Visible in health.** `/api/health` `notify.ntfy.reason == "off (SONAR_ALARM)"`. The harness (A4) refuses to
  continue unless both diag engines report this within 120 s of start (each request capped at 30 s; amended at the
  fix round, review P2-1: the Background engine took 3-24 s to answer and about 47 s to spawn). It still fails
  closed.
- **Tests** in `tests/test_alarm.py`, using the fakes in `tests/alarm_fakes.py`:
  - unset, `""` and `on` call `read`. This uses a fake that records the call.
  - `banner-only`, `off`, `OFF ` and `bogus` never call `read`. The fake raises if called.
  - `off`: `send()` starts no `osascript` (the fake `run` is never called), and `states()` shows both channels "not
    configured"/"unavailable" with the reason.
  - `bogus` logs one line naming the value and keeps the banner.
  - In `server`, `main`'s wiring passes the env mode (a monkeypatched `from_keychain` captures `mode`).
- **Mutation-check.** Flip the `mode == "on"` guard, and drop the `.lower()`.

### A3. Keyless providers for diag plists (domain P1-2): no code change
- **Where keys come from.** Keyed providers read only the process environment: `FINNHUB_API_KEY`,
  `TWELVEDATA_API_KEY` and `ALPHAVANTAGE_API_KEY` (`sonar/providers.py:200,218,235`). They are `configured` only
  when that var is non-empty (`providers.py:71`).
- **Nothing else injects keys.**
  - The only `.env` loader is `alpaca.load_env()`, which reads `<checkout>/.env` (`sonar/alpaca.py:62-77`). It is
    called only from `AlpacaPaperBroker.__init__` and `alpaca.available()` (`:130`, `:217`). Their only caller is
    `portfolio.default_broker()` (`portfolio.py:137-153`), which nothing calls.
  - Nothing reads a `.env` under `SONAR_DATA`.
  - The Keychain holds only the ntfy topic (A2).
  - There is no `.env` in this worktree.
  - `launchctl getenv` is empty for all three keys (checked 2026-10-19). A launchd job does not inherit the shell's
    env.
- **Belt and braces.** The diag plists set all three keys and `ANTHROPIC_API_KEY` to `""` in `EnvironmentVariables`.
  Per-job values override any `launchctl setenv` global, and an empty string makes `configured` false.
- **The LLM.** The LLM read runs only on a user action, and the follower takes none (measure 5). `llm.available()`
  may still find an `ant auth login` profile (`llm.py:170-173`), but it only reports this; it bills nothing.

### A4. Measurement harness `scripts/diag_priority.py` (measures 2, 3, 5)
Stdlib Python 3, run with `python3 -I`. The engines run from **this checkout** (`.venv/bin/python main.py --headless`),
not from `/Applications/SONAR.app`: the installed build lacks `SONAR_ALARM`.

**Subcommands:**
- **`run`** (the hour): the steps below.
- **`probe <tag> <n>`**: the diagnosis probe (§4). It posts `SONAR diag <n>` banners, 2 s apart, each with a 15 s
  cap, and writes JSON lines to the scratch dir.
- **`watch --port 8787 --every 300 --days 7`**: measure 4, read-only, health only. It writes to a path outside
  Application Support.
- **`cleanup`**: boots out any loaded `com.netrunner3000.sonar-diag.*` label.

**Hard guards.** Each is a refusal with a non-zero exit, and each is unit-tested:
- Every label the script builds matches `^com\.netrunner3000\.sonar-diag\.[a-z-]+$`. It asserts `!=
  com.netrunner3000.sonar`, and `bootout`/`bootstrap` are only ever called with such labels.
- Plists are written only under `D = mkdtemp(prefix="sonar-diag-")`. If the resolved path is under
  `~/Library/LaunchAgents` or `~/Library/Application Support`, the script refuses.
- `SONAR_DATA=$D/<v>/data` and `SONAR_BACKUP_DIR=$D/<v>/backup` (domain P3-2; this wins over `backup-to`,
  `paths.py:45-51`). Both must resolve under `D`.
- Ports 8788 and 8789 must be free before the start.
- It refuses during US market hours (Mon-Fri 09:30-16:00 `America/New_York`, `zoneinfo`) unless `--force`. It prints
  the UTC start and end of the window for the 30-day run record.
- **The live agent is read, never touched.** At the start and at the end, the script runs `launchctl print
  gui/$UID/com.netrunner3000.sonar` and reads `pid` and `spawn type`. It reports both and fails the run if the pid
  changed. It sends no request to 8787 during `run`.
- `cleanup` runs from a `finally` and from a SIGINT/SIGTERM handler. It boots out the diag labels, then deletes `D`
  with `shutil.rmtree`, only if `D` still has the `sonar-diag-` prefix and sits under the temp dir. Nothing is copied
  out first.

**Plists.** Each is built with `plistlib`:
- `bg`: `ProcessType Background`, `Nice 5`. `std`: `Standard`, no `Nice`.
- Arguments: `--headless --host 127.0.0.1 --port 8788|8789`.
- `EnvironmentVariables`: `SONAR_DATA`, `SONAR_BACKUP_DIR`, `SONAR_ALARM=off`, and the keys set to `""` (A3; seven
  after the fix round: the three providers, `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, `APCA_API_KEY_ID`,
  `APCA_API_SECRET_KEY`).
- `RunAtLoad true`, no `KeepAlive`.
- Logs go to `$D/<v>/logs`.

**Sequence:**
1. Bootstrap `bg`. Wait until its first scan has completed, by polling `/api/health` until `last_poll_age_s` is
   not null and no `scan` problem is listed, capped at `--stagger` (default 600 s).
2. Then bootstrap `std`, the same way. The cold scans therefore never overlap. If `bg`'s first scan misses the cap,
   the run stops rather than start `std` (fix round, QA P2-3 / domain P3-R2).
3. Check A2's `notify.ntfy.reason` on both. Read each engine's pid from `launchctl print` and record `ps -o cputime=`.
4. Every 30 s for 60 min, for each port:
   - `curl -s -m 60 -w '\n%{http_code} %{time_total}'` on `/api/health`, `/api/config` and `/api/state` (the
     follower's every-round call, `core.py:1707`);
   - from the health body, keep **only** `ok`, `last_poll_age_s` and the problem `kind`s (a whitelist; the body is
     never stored);
   - `os.getloadavg()[0]`.
5. At minute 30, bootstrap `com.netrunner3000.sonar-diag.probe-bg` and `.probe-std`, with the same
   `ProcessType`/`Nice` as their engine, each running `probe <tag> 10`. They run at the same time.
6. At the end, record `cputime` again. CPU % = Δcputime / wall time.

**Output.** One numbers-only file, `--out`, default `docs/audit/starved-engine-measurement.md`. It holds the per-sample
table (t, port, endpoint, ms, code, poll age, load) and a summary:
- p50, p95 and max per port and endpoint;
- probe count over 10 s;
- CPU %;
- the share of samples at load ≥ 50, labelled "valid" if ≥ 60 %, otherwise "not determined";
- each bar from measure 2 marked pass or fail;
- the window, the live agent's pid and spawn type before and after.

No book, P&L or score field is ever parsed (domain P2-2).

**Follower (measure 5, domain P1-3).** `run --follower` starts `.venv/bin/python main.py` with
`SONAR_DATA=$D/std/data` and `SONAR_BACKUP_DIR=$D/std/backup`. A window finds its holder through `engine.lock`
under `user_data_base()` (`enginelock.py:71`, `paths.py:265-267`). The `std` engine holds that lock with
`lock_url("127.0.0.1", 8789)` (`server.py:416-419`, `:434-435`), so the window can only follow 8789.
- The harness waits for the owner to type `y` after confirming that the window shows `127.0.0.1:8789`. Only then does
  the hour start.
- The window is closed in `cleanup`.
- The window has no external "not answering" signal. The evidence is therefore:
  - the owner's look at minutes 0, 15, 30, 45 and 60, recorded as "not continuously observed";
  - the harness's proxy: the count of `/api/state` samples over 2.0 s, and the longest run of consecutive ones.
- **Known bias.** Only `std` carries a follower, which slightly penalises `std`, the conservative direction.

**Tests** (`tests/test_diag_priority.py`, no real launchd; a fake `launchctl`/`curl` on PATH as in
`test_agent_from_bundle.py:63-88`):
- label and path guards refuse the live label, `~/Library/LaunchAgents` and Application Support;
- generated plists: type, `Nice`, env (`SONAR_ALARM=off`, four empty keys, both paths under `D`);
- cleanup boots out only `sonar-diag.*` labels and removes only `D`;
- market-hours guard (clock injected);
- percentile and pass/fail logic, including "not determined";
- the health whitelist drops every other key.

### A5. `FOLLOW_TIMEOUT` and the 3-failure rule (Scope b): no change by default
The follower's real cost is `/api/state` every `FOLLOW_EVERY` = 2 s (`core.py:103`, `:1707`), with each request capped
at `FOLLOW_TIMEOUT` = 2.0 s (`:111`, `:1801-1811`). It shows "not answering" after 3 failed rounds in a row
(`:1731-1738`). The decision rule uses `std`'s `/api/state` numbers from A4. `/api/health` is only the spec's proxy.
- **Keep both** (default): the window never showed "not answering" when checked, `/api/state` p95 ≤ 1 s, and no 3
  consecutive samples were over 2 s. Record the numbers here at Verify.
- **Keep, flag:** p95 ≤ 1 s, but there are isolated samples over 2 s. Record them, and change nothing. The 3-in-a-row
  rule is what absorbs these.
- **Propose a change** (back through Architect, owner gate): p95 > 1 s, or the window showed "not answering".
  - The only candidate is a separate `FOLLOW_READ_TIMEOUT` for `_fetch` alone, set to the measured `/api/state`
    p99 × 1.5 and at most 10 s.
  - Cost: a slow round then stalls the follow loop by up to 5 × that timeout (state, assets, wire, book, config).
  - `_post` stays at 2.0 s. A longer wait on a forwarded trade or LLM read changes what a timeout means (`core.py:1813-1830`,
    `:1310`). The "may have gone through" wording (domain P2-1) is its own backlog item either way.

### Failure modes
| Failure | Effect | Handling |
|---|---|---|
| `Standard` makes the owner's interactive work slower | the owner feels lag | measure 3 bounds CPU (≤ 5 % of a core); revert is a template edit plus the one install |
| Poll outages persist under `Standard` | the cause is providers, not starvation | measure 4 reports it with N; not hidden |
| Harness killed mid-hour (`kill -9`) | diag jobs are left loaded | they have no `KeepAlive`; `diag_priority.py cleanup` boots them out; the scratch dir sits in `$TMPDIR` |
| A diag engine pushes to the phone | the owner confuses it with the live agent | Keychain never read under A2; the harness aborts if `ntfy.reason` is not "off (SONAR_ALARM)" |
| Diag engines throttle shared providers | live coverage dips | keyless only, staggered, outside market hours, 60 min, window logged |
| `SONAR_ALARM` off reaches the live agent (plist or global `setenv`) | the live agent loses its phone alarm | the live plist pins `SONAR_ALARM=on`, which beats a global value; test A1.1 on the template, the rendered plist and a template without the key |

### Migration of existing state
None. No state file, schema or `SONAR_DATA` content changes. The new priority reaches the live agent only through
the single shared restart with item 1 (`./build_app.sh --install` → `install_app.sh:110` → `install_agent.sh`), and only
with the owner's yes. Afterwards, `launchctl print` must show `spawn type = daemon (3)` and no `nice`. Add this to the
release smoke test.

### Release smoke test additions (domain P3-a)
After the single `./build_app.sh --install`, on top of the app-context smoke test:
1. `launchctl print gui/$(id -u)/com.netrunner3000.sonar | grep -Ei 'spawn type|nice'` shows `spawn type = daemon (3)`
   and no `nice` line.
2. `launchctl getenv SONAR_ALARM` prints nothing. The live plist pins `SONAR_ALARM=on`, which beats a global value,
   but a global value is still a fault to remove. The A3 env check is the same command for `SONAR_ALARM`, `FINNHUB_API_KEY`, `TWELVEDATA_API_KEY`,
   `ALPHAVANTAGE_API_KEY`, `ANTHROPIC_API_KEY` and `ANTHROPIC_AUTH_TOKEN`; `diag_priority.py run` and `watch` print it.
3. `curl -s 127.0.0.1:8787/api/health` has a `notify.ntfy` block whose `reason` is **not** `off (SONAR_ALARM)`.
   `diag_priority.py watch` prints a WARNING if it ever sees that reason on the port it watches.

### Build notes (2026-10-19)
Folded in from the Architect-pass domain review, and the small choices made in Build:
- **P3-b.** The diag plists also set `ANTHROPIC_AUTH_TOKEN` to `""` (five blank keys, not four). Tested.
- **P3-c.** `/api/state` and `/api/config` are fetched with `-o /dev/null`, so their bodies are never read. The
  health whitelist is applied in `watch` on 8787 too. Both tested.
- **P3-d.** "Outside US market hours" does not protect the crypto feeds, which trade around the clock. The mitigation
  is the logged window: the harness prints the UTC start and end for the 30-day run record. Provider ToS is not
  verified; the owner accepted the load at the Architect gate.
- **Whitelist.** Besides `ok`, `last_poll_age_s` and the problem kinds, it keeps two fixed-vocabulary fields that
  measure 2 step 3 and measure 4 need: whether `notify.ntfy.reason` equals `off (SONAR_ALARM)` (a boolean) and
  `notify.banner.failures` and `notify.banner.attempts` (integers). No other field is kept. `attempts` is a new
  per-channel count in `/api/health`'s `notify` block (every counted outcome), so measure 4 can report failures per
  attempt (QA P3-5).
- **Unknown `SONAR_ALARM`.** One log line names the value and says it is treated as banner-only.
- **Market hours.** The guard checks the whole projected window (the hour plus both stagger caps), not only its
  start.
- **`watch` output.** Defaults to `~/Library/Logs/SONAR/diag-watch.jsonl` (beside the agent's logs, outside
  Application Support); `--out` changes it.
- **Not run in Build:** `run`, `probe` and `watch` were not executed and no launchd job was loaded. Unit tests only,
  with `launchctl`, `curl` and `osascript` faked.

**Fix round (2026-10-19)**, from `docs/audit/starved-engine-{code-reviewer,qa,security,domain-finance}.md`:
- Security P2-1: the live plist pins `SONAR_ALARM=on` (A2 above).
- Review P2-1 / QA P2-1: the alarm-off check waits up to 120 s, with 30 s per request, and still fails closed.
- Review P2-2: a non-answer counts as infinitely slow in p50/p95/max, so timeouts push p95 up.
- Review P2-3, security P3-1, QA P3-3: during cleanup INT, TERM and HUP are ignored, then the previous handlers come
  back. HUP is handled like TERM. Each `bootout` has a 90 s timeout and its own error handling, and its real return
  code is reported. `cleanup` without `--dir` removes every `$TMPDIR/sonar-diag-*` dir that passes `check_scratch`.
- Review P2-4: the path guard ignores letter case.
- QA P2-2, P2-3, P3-1, P3-2: the tests now cover a changed live pid (exit 1), a first scan that misses its cap (the
  run stops before `std`), a failed bootstrap, and a market open inside the window. Mutants D15, D22, D23 and D24 are
  killed.
- Domain P3-R1 / review P3-1: market hours are checked again just before the hour starts.
- Domain P3-R3: the harness refuses to run while `~/.config/anthropic` exists.
- Review P3-2: rows are appended to `<out>.partial` as they arrive, and the file is removed after a good run. Review
  P3-3: the tests fake the venv python. Review P3-5: `.venv` is in `.gitignore`.
- Security P3-2: `/bin/launchctl`, `/bin/ps` and `/usr/bin/curl` are called by absolute path. Security P3-4: the Alpaca
  keys are blanked. Security P3-5: the output is written to the resolved path with `O_NOFOLLOW`.
- QA P3-4: `make_scratch` removes its dir when the guard refuses it. QA P3-5: `watch` keeps the banner attempt count
  and labels its problem count as samples, not alarms.
- **Deferred** (owner's call at the fix round):
  - Security P3-3: a per-run label suffix, so `cleanup` cannot boot out another session's run.
  - QA P3-6: coverage of the CLI dispatch for `probe`, `watch` and `cleanup`, and of exit 130 from the CLI.
  - QA P3-7: noise from leftover watchdog threads in the older `tests/test_server.py` `server.main` tests. It existed
    before this change.

### Test strategy
- Unit tests: A1, A2 and A4 as listed above.
- Full suite native and offscreen (app-context).
- Mutation checks: as listed in A1 and A2, plus A4's guard regexes.
- Measures 2, 3 and 5 run once at Build, from the harness.
- Measure 4 runs for 7 days after the restart.

### Gate
**Applies.** The change sets the scheduling class of the single-writer engine (concurrency), and it adds an
alarm-silencing input to `sonar/alarm.py`'s module boundary. No persisted state changes.
