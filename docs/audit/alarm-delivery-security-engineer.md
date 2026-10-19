# alarm-delivery: security-engineer review (Secure phase, 2026-10-19)

The playbook is stale (`baseline`, last reviewed 2026-10-10). The change adds no new dependencies; it uses the standard library only. `sonar/alarm.py` changed on disk during the review, probably from QA's mutation runs. `read_topic` and the opener were re-read after the change.

**Verdict:** no P0 and no P1.

**P2-1: the test suite reads the real Keychain and could send a real "alive" push.**
- In tests/test_two_processes.py:37-59, the CHILD runs `server.main`, which calls `alarm.from_keychain()` (server.py:415). The conftest guard (conftest.py:426-441) covers only the test's own process.
- The child blocks `urllib.request.urlopen`, but NtfyChannel sends through `build_opener().open` (alarm.py:244, 297).
- With a fresh tmp SONAR_DATA after 09:00, the first watchdog tick (15 s) queues a real heartbeat, which can happen if the child lives 15 s or more.
- Impact: this breaks the "tests never read the Keychain" rule, and a heartbeat sent by a test could hide a dead agent.
- Fix: stub `read_topic` and turn the banner off in CHILD, or inject a notifier or an env switch. Add a test that the child never runs `security`.

**P3-1: ADR 0005 overstates what the Keychain protects.**
- The item's ACL trusts `/usr/bin/security`, so any process running as the user can read the topic without a prompt.
- Fix: correct the wording in the ADR and RUNBOOK (around lines 67-79) and record the remaining risk.

**P3-2: the topic is unauthenticated.**
- Anyone who knows the topic can post a fake "alive" push.
- ntfy.sh caches messages for 12 h, may log IPs and topics, and delivers to phones through Firebase (https://docs.ntfy.sh/privacy/, docs.ntfy.sh/faq; read from search snippets on 2026-10-19, not fetched).
- Fix: the owner acknowledges this in ADR 0005, and the reserved topic plus token goes on the backlog.

**P3-3: a sender thread can die while its channel still shows "ok".**
- An exception in `say` or `log` (alarm.py:474, 486) kills the thread.
- Afterwards `outstanding` is never decremented, health still reads "ok", and the drain waits the full 12 s.
- Fix: wrap the `_serve` loop in try/except and count the failure.

**P3-4: the conftest guard covers only list-form `subprocess.run`.**
- `Popen`, `os.system` and shell-string calls are not caught.

**Checked and sound:**
- The topic is never in argv or `ps`, in logs (redacted, and `_why` never uses `str(exc)`), in /api/health, or in the repr.
- The test topic is random.
- No proxy is used, a redirect makes the send fail, and TLS verification is on (fails closed).
- The watchdog is never blocked: sends have a 10 s timeout (DNS lookups are not covered), each channel has its own thread, a send counts as stuck after 30 s, and the queue is bounded at 16.
- osascript gets its arguments after `--`, cleaned by `plain()`.
- The push body comes only from ASCII fixed phrases.
- /api/health checks the Host header.
- The RUNBOOK's `-w` comes last, so `security` prompts for the topic and it stays out of argv and history.
- Minor: the RUNBOOK's generator prints the topic to the terminal scrollback.
