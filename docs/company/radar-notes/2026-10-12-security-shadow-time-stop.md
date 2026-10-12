# Radar note: security, shadow-time-stop (2026-10-12)

Scope: the time-stop shadow readout adds holder-side Yahoo daily-bar requests (`assets.fetch_bars`,
symbols taken from the paper book), a `shadow` key in the localhost `/api/book` payload that follower
windows mirror, and Qt labels that render it. No new dependency, no secrets, no file writes.
Installed: PySide6 / Qt 6.11.2, Python 3.11.15 (the main `.venv`). Three searches; web content
treated as data.

| Finding | Source | Impact | Recommendation | Approval needed |
|---|---|---|---|---|
| Qt advisory CVE-2026-15037: XML injection in QDom serialization (Jul 2026); a separate Qt advisory: out-of-bounds read in `QTextCodec::codecForName()` (Jul 2026). SONAR uses neither QDom/QtXml nor QTextCodec (`grep` on `sonar/`, `ui/`: no hits). Fixed versions not confirmed (advisory pages not opened). | [qt.io news](https://qt.io/news/), [cve-dev.imfht.com Qt](https://cve-dev.imfht.com/vendor/Qt?lang=en) | P3 | **Watch.** Confirm on the next dependency upgrade that the pinned PySide6 is at or past the fixed Qt patch release. | None now; any upgrade goes through `/radar-check upgrade` |
| CPython 2026 advisories (CVE-2026-1502 `http.client` CR/LF in proxy tunnel headers; `wsgiref`, `http.cookies`, `webbrowser` fixes). None names `http.server`, which SONAR's localhost server uses; the docs still say `http.server` is not for untrusted networks. `fetch_bars` uses `urllib`, no proxy tunnel. | [CVE-2026-1502](https://cve.circl.lu/vuln/CVE-2026-1502), [RHSA-2026:19019](https://access.redhat.com/errata/RHSA-2026:19019), [USN-8509-1](https://ubuntu.com/security/notices/USN-8509-1) | P3 | **Watch.** Keep the server bound to 127.0.0.1 (unchanged by this change). Pick up the next 3.11.x patch with the venv. | Owner, for a Python upgrade |
| Yahoo's chart endpoint is unofficial and throttles bursts (429 / empty answers reported since 2025). No 2026 policy change found. The shadow adds at most one request per symbol per UTC day, behind the scan's existing requests. | [Portfolio Performance forum](https://forum.portfolio-performance.info/t/yahoo-finance-too-many-requests-getting-errors-on-updates-desktop-only/32780), [yfinance #2297](https://github.com/ranaroussi/yfinance/issues/2297) | P3 | **Skip** a new tool. The once-a-day cache and "no price → waiting, then counted" handling already fit; the security review should confirm a failed fetch is never turned into a number. | None |

## Checked, nothing new
- No better-fitting library or connector for daily closes is worth adding for one request per
  symbol per day; `assets.fetch_bars` is already the book's price source (ADR 0002 §5).
- Nothing in the scan changes the security-engineer playbook (`status: baseline`, 2026-10-10).
