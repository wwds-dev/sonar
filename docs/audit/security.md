# SONAR security and privacy audit — 2026-10-10

Produced by the `security-engineer` role (read-only). Probes: source review, three harmless
`curl` requests to the running agent on 127.0.0.1:8787, an in-process NaN test of the order
guard against a temp audit file, `pip-audit` via `uvx`. No secret values were read or printed.
Findings come from that agent's report; the P1s below have not yet been independently
re-verified by a second reviewer.

## Threat model
**Assets:** the paper book and state files (`state.json`, `portfolio.json`, 7 daily `.bak`) —
integrity matters most, since they hold the calibration record; optional secrets
(`APCA_*` Alpaca paper keys via `<repo>/.env`/env, `ANTHROPIC_API_KEY`/`~/.config/anthropic`) —
none present today; Anthropic spend if a key is added; the "paper only" invariant; host
integrity (launchd agent runs the checkout's `.venv` python).

**Trust boundaries:** (1) web pages vs the unauthenticated loopback daemon `sonar/server.py`;
(2) follower app vs lock holder (`engine.lock` carries PID + URL); (3) ~25 RSS/JSON feeds and
pasted Playmaker text, all untrusted; (4) process → LLM → Qt rich text; (5) process → Alpaca
(not wired today: `portfolio.default_broker()` has no caller); (6) data dir files (0755/0644)
vs other same-user processes; (7) build/distribution (PyInstaller, ad-hoc signature).

**Entry points:** POST `/api/config|read|trade|close`; GET `/api/config|state|assets|macro|book|wire`;
static `/`, `/docs`, `/testplan`; `--host`/`--port` flags; on-disk state files and `.env`;
feeds; Playmaker text; launchd plist and `scripts/install_agent.sh`.

## Findings

### P1-1 Loopback API: no auth, Origin or Host check — CSRF and DNS rebinding
`sonar/server.py:45-50, 52-82, 123-137, 173`. Confirmed live: `Host: evil.example` gets a
200 from `/api/config`; body parsed regardless of `Content-Type`; no CORS headers (so
cross-origin reads blocked, cross-origin writes not).
Attack: any web page visited while the (always-on) agent runs does
`fetch("http://127.0.0.1:8787/api/trade", {method:"POST", mode:"no-cors", body:'{...}'})` — a
CORS simple request, no preflight. Works for `/api/trade`, `/api/close`, `/api/config` (flips
risk profile / calibration protocol), `/api/read`. DNS rebinding also allows reads.
Impact: corruption of the paper book and the experiment (the core asset); no financial loss
(Alpaca unwired); latent LLM cost if a key is ever present (`/api/read` unthrottled, Opus,
`MAX_TOKENS=16000`, `llm.py:51`).
Fix: reject `Host` not in `127.0.0.1:<port>`/`localhost:<port>`/`[::1]:<port>`; require
`Content-Type: application/json` on POST; check `Origin` if present; add a random per-install
token (`SONAR_DATA/api.token`, 0600, `X-SONAR-Token` on state-changing routes); refuse
non-loopback `--host` without a token; rate-limit `/api/read`.

### P1-2 Execution guard fails open on NaN quantity/price (verified in-process)
`sonar/execution.py:451, 456, 461` and the equity-percentage check. `OrderIntent(..., nan, 100.0,
confirmed=True).check() == []` and the same for NaN price; `inf` is rejected. All NaN comparisons
are False, so max-quantity, per-order notional and percent-of-equity checks pass together.
Latent today (only `SimBroker`), but it is the stated gate for any future venue.
Fix: reject non-finite `q`, `lp`, `reference_price`, equity; `Guard.equity()` returns `None` if
non-finite; add a `float('nan')` test.

### P2-1 Order caps and idempotency fail open if the audit log can't be written
`execution.py:223` (`except OSError: pass`), `:476, :484, :505`. Daily cap and idempotency read
the audit file; write errors are swallowed, so `today_count()` returns 0 (verified with an
unwritable audit path and `max_orders_per_day=1`). Log is 0644, same-user editable.
Fix: fail closed — raise before `broker.place` if the "submitted" write fails; keep an
in-memory counter; 0600 + `fsync`; optionally hash-chain.

### P2-2 Installed `/Applications/SONAR.app` has an invalid signature, no real identity
`build_app.sh:78-79`, `SONAR.spec` (`codesign_identity=None`). Ad-hoc; `plutil -replace` after
PyInstaller's signing breaks the seal (`spctl`: "invalid Info.plist"); no Developer ID, hardened
runtime or notarization; a quarantined copy will be blocked by Gatekeeper; tampering undetected.
Fix: re-sign after `plutil` (`codesign --force --deep --sign -` at minimum); better, Developer
ID + `--options runtime` + notarytool; or set versions via the spec's `info_plist`.

### P2-3 Prompt injection from news/market text only partly mitigated
`llm.py:152-163, 76-79`, `news.py:68, 221-248`. Good: titles only, 200-char cap, 8 headlines,
untrusted-data labelling, JSON-schema output, no tools, conviction clamped, LLM read never
averaged into `confidence`. Weak: spoofable delimiter (`</HEADLINES>`); `src`/age unescaped;
`subject`/`numbers` raw (Yahoo names, Polymarket titles); MarketWatch over plain http (MITM).
Impact: poisoned LLM read and `llm_calibration` record; cannot trade.
Fix: strip/escape angle brackets, random per-request delimiters, https for MarketWatch, an
injection test case.

### P2-4 LLM output rendered as Qt rich text unescaped
`ui/app.py:2995-3005` (`_playmaker_done`: `<b>{name}</b><br>{body}` → `setHtml`), input at
`:2937-2948`. Forged formatting/links can mimic the "commentary only" disclaimer; links are not
opened; `<img src="file://">` can render local images (cosmetic).
Fix: `html.escape(body)` or `setPlainText`/`setMarkdown`.

### P3 hardening
- **P3-1 Alpaca guard** (`alpaca.py:44-46, 89-103, 147-160, 162-171`): no host bypass found, but
  `assert_paper_only(PAPER_BASE, …)` compares a constant to itself; `looks_live` is a prefix
  heuristic; `urllib` honours proxy env vars and re-sends the secret header on redirects;
  `.env` mode not checked. `AlpacaPaperBroker.execute` is unguarded (no caps/confirm/audit) —
  route through `GuardedBroker` before wiring. Fix: `ProxyHandler({})`, refuse redirects, warn on
  group/world-readable `.env`, unit test `PAPER_BASE`.
- **P3-2 `engine.lock` trusted** (`enginelock.py:90,125`, `core.py:686-688,768-777`): lock URL goes
  to `urlopen` (any scheme); PID 1 reads as alive via `PermissionError` → read-only forever;
  0644. Fix: accept only `http://127.0.0.1|localhost:<port>`, validate schema, 0600.
- **P3-3 Server hardening** (`server.py:45-50, 123-137`): unbounded/negative `Content-Length`; no
  socket timeout (slowloris); no CSP/XFO/nosniff. `static/index.html` `innerHTML` writes
  (`:302,311,345,367,502`) are fed numeric daemon JSON — no current XSS. Fix: 64 KiB cap, timeout,
  CSP `default-src 'self'`.
- **P3-4 XML/plain HTTP** (`news.py:225`, `institutions.py:120`, `news.py:68`): `ElementTree` on
  untrusted feeds (expat mitigates entity bombs; low DoS risk); no SSRF (fixed URLs). Fix:
  `defusedxml` or cap response size.
- **P3-5 State files** (`paths.py:64-71, 90-128, 156-170`): no pickle/eval/shell; corrupt files
  quarantined with fallback to newest valid backup. But no integrity protection, 0644, predictable
  `.tmp`, unvalidated `SONAR_DATA`, and numeric fields not checked finite on load (same class as
  P1-2). Fix: umask 077 / chmod 0600; `math.isfinite` on load.
- **P3-6 launchd/install**: loopback, user agent, no secrets — good. Executes
  `<checkout>/.venv/bin/python main.py` from `~/Documents`, so any same-user writer gets
  persistence at login. Misplaced "Loopback only" comment. Agent does not inherit shell env
  (keys would need the plist or `.env`; plist is 0644).
- **P3-7 Dependencies**: `pip-audit` clean. `requirements.txt` is `PySide6>=6.6`, no pin/hashes;
  CI actions pinned by tag not SHA; unpinned installs; CI checks out `sonar_macro`/
  `sonar_playmaker` at default-branch HEAD and PyInstaller bundles whatever is in the gitignored
  nested dirs (supply-chain path). Fix: lockfile with hashes, pin Actions by SHA, pin sibling repos
  by commit.

## Checked and sound
No path traversal (fixed whitelist, `server.py:112-119`); no secrets in tree or history; Alpaca
host is a constant with no override; execution-guard design (confirmation, empty allowlist
permits nothing, unpriced order rejected, unknown outcome halts, `flatten`/`panic`) is sound
apart from NaN and audit-write cases; daemon binds loopback by default and `lsof` shows only
`127.0.0.1:8787`; `/api/trade` validates direction and symbol.

## Suggested fix order
1. P1-1 Host/Origin/content-type checks + token. 2. P1-2 finite checks + test. 3. P2-1 fail-closed
audit. 4. P2-2 re-sign after `plutil`. 5. P2-3/P2-4 escape headlines and LLM output, https
MarketWatch. 6. P3 hardening.
