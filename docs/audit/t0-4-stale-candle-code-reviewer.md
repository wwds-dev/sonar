# T0-4 review — code-reviewer, 2026-10-10

Read-only. Playbook still `status: baseline`. 168 engine/feed tests and the full offscreen suite
pass; all 3 new tests fail against the old `engine.py`/`feeds.py`.

**P0: none. P1: none. P2: none.**

| ID | Finding | Outcome |
|---|---|---|
| P3-1 | `_poll` still put an ignored earlier-hour candle on the spark line and in the snapshot (clock a few seconds behind the exchange): last hour's price beside this hour's signal | Fixed: `_poll` drops it; `tests/test_poll.py` via a new `real_poll` fixture |
| P3-2 | The new `is_stale` check on the Coinbase result is unreachable with real data (strict parser) | Kept as a backstop; noted in the spec |

Checked fine: clock skew both ways at the top of the hour, DST (unix time), no permanent freeze
(`current_hour` only comes from a feed-checked candle), restart/long sleep, scoring, warm-up path.
