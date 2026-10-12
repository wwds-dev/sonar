# Security review: follow-url-localhost, 2026-10-12

Reviewer: security-engineer agent (read-only; saved by the orchestrator). Also the code review for
this small change. Playbook `status: baseline`: stale.

**Verdict: the check does its job; no P0/P1; one P2 (pre-existing) breaks the spec's promise.**
The lock URL is the only way a holder address enters `Live` (`EngineLock.holder()` is called only
from `_wait_for_lock`; `following` is assigned only in `_follow`; `describe_conflict` never reads
the URL; `ui/app.py` shows the local, admitted URL; `main.py`, `scripts/`, `packaging/` never read
it). `_loopback_url` matches exact host strings: `2130706433`, `0x7f.0.0.1`, `127.1`,
`127.0.0.1.`, `[::ffff:127.0.0.1]`, fullwidth `ｌocalhost`, bad ports, `127.0.0.1:1@evil.com`
all rejected (40 crafted URLs, Python 3.11.15). `http.client` sends `Host: [::1]:8787`, which
`_own_hosts` accepts: the bracket fix is right.

## Findings
| # | Pri | Where | Finding | Fix |
|---|---|---|---|---|
| F1 | P2 | `sonar/core.py` `_fetch`/`_post` (default `urlopen`) | With `http_proxy` set, or a macOS system proxy (default exceptions `*.local`, `169.254/16` do not cover 127.0.0.1; measured), every follow request, posts included, goes to the proxy, and its answers are shown as the holder's. | Own opener with `ProxyHandler({})`. |
| F2 | P3 | default `HTTPRedirectHandler` | A loopback answer `302 Location: http://redirect.example/x` made the GET connect off-machine (measured). | No-redirect handler in the same opener. |
| F3 | P3 | `_loopback_url` | Admits userinfo (`x@127.0.0.1`, `evil.com\@127.0.0.1`; resolver lookup of a chosen name), missing or zero port (another local service on :80/:0), `\t`/`\n` (stripped by urlsplit, rejected later by urllib with the wrong message). | Require no userinfo, port 1-65535, no surrounding whitespace or control characters; optionally empty path, no query/fragment. |
| F4 | P3 | `sonar/server.py` | `ThreadingHTTPServer` is AF_INET: `--host ::1` passes the loopback check, writes the lock, then fails to bind (`gaierror 8`, measured). | AF_INET6 subclass, or drop `::1`; a helper for the lock URL so a test can pin it. |
| F5 | P3 (pre-existing) | `sonar/enginelock.py:228` `describe_conflict` | `float("x")` on a hand-edited `since` raises inside `_wait_for_lock`, which has no try: the engine thread dies (code reading). | try/except, `?` minutes; test. |

Code quality: consistent style; `FOLLOW_HOSTS` duplication justified (circular import) and pinned
by a test; refused URL `_clean`ed into a plain-text label. Tests deterministic apart from the known
`_wait` pattern. ruff and pip-audit not available; native run and full suite not run.

## Dispositions (orchestrator)
- F1, F2: fixed. `_follow_opener()` builds `ProxyHandler({})` + `_NoRedirect`; `_fetch`/`_post`
  use it. Tests `test_following_uses_no_proxy` (opener built with `http_proxy` set),
  `test_a_redirect_is_not_followed_off_the_machine` (real loopback 302 -> HTTPError 302).
- F3: fixed as recommended, including empty path and no query/fragment; 11 cases added.
- F4: fixed: `PaperServer6` (AF_INET6) for a `:` host, `server.lock_url()`; tests pin both (the
  bind test skips only when the machine has no IPv6 loopback at all).
- F5: fixed, `test_a_lock_with_a_bad_start_time_still_reads_as_a_conflict`.
- Every fix's mutation dies (proxy default, redirects on, default urlopen in `_fetch`, userinfo,
  port range, path/query, whitespace, the `since` guard, AF_INET6, lock URL brackets).
