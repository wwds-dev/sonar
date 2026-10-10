# T0-7 review — security-engineer, 2026-10-10

Probed an own server on an ephemeral port (nothing sent to 8787). Playbook `status: baseline`.
9 of the new tests fail on HEAD's `server.py` (the 10th checks a legitimate write).

Host: only exact `127.0.0.1:P`, `localhost:P`, `[::1]:P` accepted; upper case, trailing dot, no
port, padding, missing Host refused. `Origin: null` refused. `text/plain; application/json` → 415.
No browser path sends a JSON content type without a preflight (forms, no-cors fetch, sendBeacon);
the preflight `OPTIONS` gets 501. HTTP/1.0 closes after one response (no smuggling). 403/415
bodies are fixed strings. No GET changes state. Legit clients unaffected (follower has sent JSON
since v2.128; TESTPLAN curls are GETs; nothing frames the pages).

**P0: none. P1: none. P2: none.**

| ID | Finding | Outcome |
|---|---|---|
| P3-1 | Chunked POST with no Content-Length read as `{}`, 200 — `/api/config` rescanned, payload lost | Fixed: 411; test |
| P3-2 | On port 80/443 clients omit the port from Host → everyone locked out | Fixed: bare names accepted on default ports; test |
| P3-3 | Slow-drip local client can hold threads (per-read timeout, no thread cap) | Deferred (spec residual risk) |

Unrelated: `--host ::1` passes `main()` but the IPv4-only server crashes at bind (pre-existing).
