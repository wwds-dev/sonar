# alarm-delivery: domain-finance review

## Define pass (2026-10-14), spec docs/specs/alarm-delivery.md

The playbook `docs/playbooks/domain-finance.md` is `status: baseline` (last reviewed 2026-10-12), so treat it as stale.

**Verdict:** no P0, one P1.

**P1-1. Raw error text would leave the Mac.**
- Evidence: sonar/core.py:1548-1549 appends `(last error: {self.last_poll_error})` to the poll problem text. That value is `_exc_line(exc)` (core.py:79-82, 1513), which can quote a server body, a feed or a file path. Watchdog.step joins these texts into the alarm body, and the spec routes that body to ntfy (spec:55-56). This contradicts spec:59 (no symbols or prices) and radar-note:12.
- Fix: build the push body from a fixed allowlist of `kind` plus duration. Keep the full text in the local log only. Never push `problems[].text`, exception text or `run_health` fields beyond the allowlist.

**P2-1. Success measure 1 does not define "generic".**
- Fix: add a test that builds the push body for every health kind (loop, poll with an error carrying a symbol, URL and price, scan, settle, stopped, recovery). It asserts each body matches the allowlist, contains no digits other than durations, build or counts, and contains no `$`, ticker or path.

**P2-2. The heartbeat "coverage X%" could read as a performance claim.**
- It counts recorded hours (engine.py:809-834).
- Fix: label it as operational, e.g. "paper run: 312 of 318 hours recorded (98%) since 2026-10-10". Never include Brier, hit rate, P&L, balance, positions, open-trade count or "edge".

**P3-1.** Prefix push and heartbeat titles with "SONAR (paper)".

**P3-2.** Stale prices while positions are open are covered by the poll alarm (600 s, server.py:221). The execution guard's halt (execution.py:465-466, 551) is not wired into the live agent; core.py, engine.py and server.py do not import it. Add a non-goal: if a broker-paper executor is ever wired in, "guard halted" becomes a health kind that pushes.

**P3-3.** The test-alarm path must use no book, health or price data.

**Open question 2 (domain view): what text may leave the Mac.**
- Allowed: the problem kind, duration, build version, the state of each channel, and a paper label.
- Never: balances, cash, equity, P&L, positions or open-trade count, symbols, prices, model outputs or scores, exception or server text, file paths.

**Open question 3 (domain view): heartbeat content and timing.**
- Content: "SONAR (paper) alive, build vX", plus optionally the labelled recorded-hours count.
- Send it daily even when problems are open, with the problem kinds listed. Holding it back would turn a known problem into silence.
- The send time is an operations choice.

**Not verified:** the data-protection side of ntfy.sh (retention and terms). This needs a human check in the Secure phase. This review is not a legal or regulatory opinion.

## Architect pass (2026-10-14): spec `## Architecture`, ADR 0005

No P0 and no P1. The design addresses every Define finding: P1-1 at spec:160-179, P2-1 at spec:367 and :372, P2-2 deferred, P3-1 at spec:168, P3-3 at spec:158, :277 and :370. P3-2 is adopted at spec:121 but missing from Non-goals.

- **P3-A.** The allowlist test (spec:367) bans `:` except in "channels:", but the heartbeat contains "open problems:" (spec:173). Fix: put both fixed labels in the closed grammar and keep the bare-colon ban everywhere else.
- **P3-B.** An Event carries several kinds but only one `duration_s` (spec:163 and :198). The push could show the wrong duration next to a kind. Fix: store a duration per kind and test the case where two kinds are due at once.
- **P3-C.** If the deferred "recorded hours" line is added later, it must use exactly the operational wording, be a closed template inside the allowlist test, and get a domain re-review first.
- **P3-D.** The engine-mode word in the heartbeat raises no domain objection. If it is added, it must be a closed vocabulary covered by the allowlist test. Defaulting to "no" is fine.

**Not verified:** ntfy.sh's data-protection terms and retention, and that the topic is the only access control. This needs a human check in Secure (ADR 0005:59). Not a legal opinion.

## Review pass (2026-10-19): uncommitted diff

**Verdict:** no P0, P1 or P2. tests/test_alarm.py and tests/test_health.py: 96 passed.

All earlier findings are confirmed in the code:
- **P1-1 (allowlist push body):** alarm.py:112-175, :247-261, :412-434.
- **P2-1 (allowlist test over every health kind, hostile text):** `test_every_push_says_only_what_the_allowlist_allows` and alarm_fakes.py:24, :130-143.
- **P3-A (closed labels):** alarm_fakes.py:138.
- **P3-B (per-kind durations):** alarm.py:125, test_alarm.py:117.
- **P3-1 ("SONAR (paper)" title):** alarm.py:66.
- **P3-3 (test alarm loads no book data):** test_alarm.py:456-472.
- **P3-2 ("guard halted" non-goal):** spec:77-78.

New finding:
- **P3-E.** The local banner titles have no "(paper)": server.py:351, :372 and :377. Fix: prefix them with `alarm.TITLE`.

Other checks:
- **RUNBOOK §2:** no overclaims. The `scan` and `settle` worst-case cells are blank, which is a gap, not a claim.
- **Trading state:** untouched.

**Not verified:** ntfy.sh's data terms. This is not a legal opinion.
