# starved-engine: domain-finance review, Define pass (2026-10-19)

Reviewer: `domain-finance` (read-only). Saved by the orchestrator. Spec: `docs/specs/starved-engine.md`.

**Verdict:** the spec carries no real-money or order-forwarding risk to a venue. But measures 2 and 5 as written
could disturb the live 30-day paper run, and three P1 gaps should be closed before the Define gate.

**Basis:** `docs/company/app-context.md` (`## Domain specialist`, Invariants), `docs/playbooks/domain-finance.md`
(stale: `status: baseline`, `last-reviewed: 2026-10-12`). No external regulator text was checked.

**Real money: nothing found.** `portfolio.default_broker()` is the only route to `AlpacaPaperBroker`. Its docstring
says "Nothing calls this yet" (`sonar/portfolio.py:137-153`), and no call site was found in `sonar/`, `ui/` or
`main.py`. `alpaca.available()` refuses non-PK keys (`sonar/alpaca.py:216-226`). There is no `.env`. The diag
engines trade only their own scratch internal book. The plist change does not touch trading, scoring or the book.

## P1

**P1-1. The throwaway engines will push alarms to the owner's phone that look the same as the live agent's.**
- **Evidence:**
  - `sonar/server.py:431` always calls `alarm.from_keychain(...)` for `--headless`, with no off switch.
  - `server.py:437-438` starts the Watchdog and Heartbeat, with `alarm.json` in the scratch `SONAR_DATA`
    (`server.py:250-251`), so a fresh dir has no "already sent today" record.
  - The push carries only the build version (`alarm.py:138`), which is the same for all engines.
- **Scenario:**
  - The `bg` job starves and pushes "poll stalled". The owner can't tell which engine sent it and may restart the
    live agent, which breaks the 30-day run.
  - A diag heartbeat or recovery push can mask a real live outage.
- **Fix:** do one of these before measure 2 runs:
  - an env switch (e.g. `SONAR_ALARM=banner-only`) set in the diag plists;
  - a push prefix that carries the port or data dir;
  - the owner accepts real pushes in writing.

**P1-2. Measure 2 can throttle the live agent's data sources, silently degrading the live paper record.**
- **Evidence:**
  - A cold cache fetches all 129 instruments in one pass (`sonar/assets.py:380-382`), and two cold scratch dirs
    start at once.
  - README:198-199: a throttled scan "returns fewer rows rather than an error".
  - The keyed free tiers share the env and IP: Alpha Vantage allows about 25 requests a day (README:187), and Twelve
    Data has a tight limit (`providers.py:231`).
- **Scenario:** an unflagged coverage dip or an exhausted daily quota during the 30-day run (due 2026-11-09).
- **Fix:**
  - stagger the diag starts;
  - give the diag plists keyless providers only (no keyed env);
  - prefer a window outside US market hours;
  - log the window's start and end in the 30-day run record.

  Acceptability stays with the owner.

**P1-3. Measure 5 doesn't say how the follower is pointed at port 8789; by default it follows the live agent with
write access to the live book.**
- **Evidence:**
  - The follower finds its holder via `engine.lock` under `paths.user_data_base()` (`sonar/enginelock.py:71`).
  - The frozen app defaults to `~/Library/Application Support/SONAR` (`sonar/paths.py:259-270`).
  - The GUI has no URL or port flag (`main.py:171+`).
  - Trade, Close, Undo and the knobs forward via `_forward` (`sonar/core.py:1127, 1151, 1183, 478`).
- **Fix:**
  - launch the follower from the checkout with `SONAR_DATA` set to the `std` scratch dir;
  - confirm in the window that it follows `127.0.0.1:8789`;
  - take no trade, close, undo or config action during the hour.

## P2

**P2-1. A timed-out forwarded trade is reported "not taken" but may have been booked.**
- **Evidence:** `core.py:1827-1830` says "did not take it" on any exception. `/api/trade` has no idempotency key
  (`server.py:137-143`).
- **Scenario:** a slow holder books the trade after the 2 s timeout, and the user clicks again, which opens a
  duplicate paper position.
- **Fix:** do one of these:
  - copy: "no answer in time; it may have gone through, check the book";
  - a client id that `/api/trade` deduplicates;
  - a backlog item.

**P2-2. Keep measurement evidence free of money figures.**
- The evidence file should hold only latency, poll age, load and CPU.
- Delete the scratch dirs afterwards, with no book or score numbers copied out.

## P3

- **P3-1.** Each RUNBOOK number should carry its date range, N, load range and job class. The comparison with
  earlier outages is indicative, not causal.
- **P3-2.** Set `SONAR_BACKUP_DIR` explicitly to the scratch dir in the diag plists. `paths.py:45` honours the env,
  and the stem pruning in `paths.py:55-62` could drop the live book's off-disk copies.
- **P3-3.** The spec cites `core.py:1813-1823` for `_post`, but `_post` is at 1806-1811 and `_forward` at
  1813-1830. The LLM read is also forwarded (`core.py:1310`), so a retry could double-bill.

## Needs the owner
- Whether a third and fourth engine stay within the Yahoo, CoinGecko and keyed-tier terms and rate limits is not
  verified. No provider ToS was checked.

---

# Architect pass (2026-10-19)

**Verdict:** the architecture carries all five Define fixes (P1-1, P1-2, P1-3, P2-2, P3-2). It adds no real-money,
order-forwarding or live-book risk, and there is no new P0 or P1. P2-1 is deferred to the backlog (`TODO.md:61-64`).

- **P1-1:** `SONAR_ALARM=off` in the diag plists, so no Keychain read and no push; an unknown value never pushes; the
  harness aborts unless both report `off (SONAR_ALARM)`.
- **P1-2:** the provider keys and `ANTHROPIC_API_KEY` are set to `""`; key reads are env-only; the cold scans run
  one after the other; the harness refuses US market hours and prints the UTC window.
- **P1-3:** the follower runs with `SONAR_DATA=$D/std/data`, which takes precedence (`sonar/paths.py:265-267`).
- **P2-2:** the health body is whitelisted, the output is numbers only, and the scratch dir is deleted.
- **P3-2:** `SONAR_BACKUP_DIR` is set under the scratch dir and wins (`paths.py:45-51`).

## P3
- **P3-a.** A global `SONAR_ALARM` would silence the live agent's phone alarm. Fix: the release smoke test checks
  that the live `/api/health` `notify.ntfy` has no "off (SONAR_ALARM)" reason, and the A3 env check includes
  `launchctl getenv SONAR_ALARM`.
- **P3-b.** Also blank `ANTHROPIC_AUTH_TOKEN` in the diag plists (`sonar/llm.py:170-171`), and test it.
- **P3-c.** Discard the `/api/state` and `/api/config` bodies (`-o /dev/null`); apply the whitelist in `watch` on
  port 8787 too.
- **P3-d.** "Outside US hours" doesn't protect crypto feeds. The logged window is the mitigation. Accepting this is
  the owner's call, and provider ToS is not verified.

---

# Review pass on the diff (2026-10-19)

**Verdict:** no P0, P1 or P2. The diff carries Define P1-1, P1-2, P1-3, P2-2 and P3-2, and Architect P3-a to P3-d.
Ran `.venv/bin/python -m pytest -q tests/test_diag_priority.py tests/test_alarm.py tests/test_agent_from_bundle.py`,
result: 226 passed.

## P3
- **P3-R1.** The market-hours check (`scripts/diag_priority.py:660`) runs before the follower `input()` prompt
  (`:696`), which can wait without limit, so the hour could slide into the US open. Fix: run
  `check_market_hours` again just before `window_start` (`:700`).
- **P3-R2.** If the first cold scan misses its cap, the second engine starts anyway (`:686-687`), so the two cold
  scans overlap. Fix: abort, or wait further. At minimum, record the overlap in the evidence meta.
- **P3-R3.** An `ant auth login` profile (`~/.config/anthropic`, accepted at `sonar/llm.py:170-173`) would let a
  follower LLM read bill even with the keys blanked. Not reachable today: the directory doesn't exist. Fix: a
  RUNBOOK §7 note, or the harness refuses to start when the directory exists.

## Needs the owner
Provider ToS for about 80 min of extra keyless polling is not verified; the owner accepted the provider load at
the Architect gate.
