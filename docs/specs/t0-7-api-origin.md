# Spec: T0-7 — the local API answers only this machine's own requests

- Status: built (branch `fix/t0-7-api-origin`)
- Owner approval: delegated in chat 2026-10-10 (work through Tier 0, pause for decisions).
- Source: `docs/audit/security.md` P1-1 (confirmed live), P3-3; architecture P2, code P2-10.
- Review: `docs/audit/t0-7-api-origin-security-engineer.md` — no P0–P2; P3-1, P3-2 fixed.

## Problem
`sonar/server.py` had no auth and no Origin/Host checks. Any web page the owner visited could POST
`/api/trade|close|config|read` (a text/plain CORS simple request, no preflight) to the always-on
agent, and a DNS-rebinding page could read every route. Bodies were unbounded and parsed whatever
their type; a non-object body crashed the handler; sockets had no timeout.

## Success measure
- A request whose Host is not this server (rebinding) → 403, reads and writes.
- A write that is not `application/json` → 415; from a foreign or `null` Origin → 403; the
  server's own Origin may write.
- Bodies: oversized → 413, negative/non-numeric length or non-object → 400, chunked → 411.
- Hardening headers on every response; `main()` refuses a non-loopback `--host`.
- The follower (including an older installed build: `Live._post` has sent JSON since v2.128) and
  `static/index.html` (GET only) keep working; `test_follow`/`test_two_processes` pass.
- 6 planted mutations, 6 caught; the reviewer saw 9 new tests fail on HEAD's `server.py`.

## Architecture
`Handler._refused(write)` runs first in `do_GET`/`do_POST`: Host must be one of the loopback names
or the bound host with the port (bare names too on 80/443); writes also need a JSON content type
and no foreign Origin. `_read_json_body` reads once per POST and answers 400/411/413 itself.
`timeout = 10`; `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`.

## Decided without asking
No per-install token: same-user processes can read the state files directly, and the checks above
close the browser paths (no browser can send a JSON content type cross-site without a preflight,
which this server never grants).

## Residual risk
- A slow-drip local client can hold handler threads (10 s timeout is per read; no thread cap).
- A page can still detect that something listens on 8787 (browser local-network permissions).
- `--host ::1` passes the loopback check but the server listens IPv4 only (pre-existing crash).

## Verification
Full suite 1,644 passed natively and under `QT_QPA_PLATFORM=offscreen`.

## CHANGELOG draft
**Web pages can no longer reach the agent.** Any site you visited could open or close paper
positions or change settings through the agent's local port. The agent now answers only requests
that name this machine, takes writes only as JSON from no foreign site, and caps what it reads.
