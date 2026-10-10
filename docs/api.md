# Local HTTP API

Moved from `README.md` on 2026-10-10. Served by `sonar/server.py` (headless mode and the agent), loopback only.

| | |
|---|---|
| `GET /api/state` | live snapshot: candle, market, signal, portfolio, model-vs-market, run health, calibration |
| `GET /api/assets` | the real-asset screen |
| `GET /api/config` | current risk/horizon/protocol, available options, LLM availability |
| `POST /api/config` | `{"risk": "...", "horizon": "...", "protocol": true}` — switches and rescans |
| `POST /api/read` | `{"kind": "btc\|asset", "id": "..."}` — one LLM read |
| `GET /api/health` | is the engine doing its job — 200, or 503 with the problems listed |
| `GET /api/book`, `/api/wire`, `/api/macro` | the paper book, the alerts and central-bank calendar, the macro regime |
| `POST /api/undo` | `{"id": "...", "kind": "trade\|close"}` — take back a trade or a manual close made in the last 30 s (the window's Undo); it never reaches the graded record |
| `POST /api/trade`, `/api/close` | `{"symbol": "...", "direction": "LONG\|SHORT"}`, `{"id": "..."}` — paper trades; how a second window hands its actions to the engine that holds the book |
| `GET /`, `/docs`, `/testplan` | the BTC terminal page, the manual, the acceptance plan |

Every route answers only requests that name this machine in their `Host` header; writes must be JSON from no foreign `Origin` (see `docs/specs/t0-7-api-origin.md`).
