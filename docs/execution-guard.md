# Execution guard (simulator only)

What `sonar/execution.py` enforces. It contains no broker integration; real money is out of scope until the owner says otherwise in writing.

Moved verbatim from `README.md` on 2026-10-10 when the README was cut to what / how / where. Statements here are as of the commit they were written in; the README no longer repeats them.

`sonar/execution.py` is the safety layer that would sit between a signal and a real order. It
contains **no broker integration** — it talks to an abstract port whose only implementation is
an in-process simulator, so every rule in it is testable:

- an order is never sent without explicit human confirmation
- idempotent client order ids, recorded *before* the send, so a double-click cannot double-fill
- hard caps on notional, quantity, orders per day, and open positions, checked locally
- an instrument allowlist that **fails closed** — empty permits nothing
- unpriced orders rejected: no limit price means no notional to cap
- an unknown outcome halts the guard rather than retrying, because a retry is how one order
  becomes two
- notional also capped as a share of equity **read from the venue**, so a stale local bankroll
  cannot size the next position; a port that cannot report equity is refused
- append-only audit log
- a kill switch that cancels, **flattens**, then latches — `flatten()` is exempt from the halt
  latch and every cap, because a limit that can stop you closing a position is one that traps
  you in it, and it stays idempotent because a duplicate closing order opens the opposite
  position rather than closing twice
- `reconcile(expected=...)` halts on any disagreement between local state and the venue —
  a position opened by hand in the broker's own app is otherwise invisible
- `GuardedBroker` fills the portfolio's broker seam through the guard, so the Book tab
  cannot become a second unguarded route to a venue. Confirmation defaults to *refuse*, and
  a refusal **raises** rather than returning an error dict — `Portfolio.enter` ignores that
  return value, so a dict would leave the book holding a position that was never sent
- the book distinguishes **accepted** from **filled**. A broker declares `synchronous`; when it
  is false a position is recorded `PENDING`, carries no unrealised P&L, and is never closed on a
  barrier — `poll_fills()` then rewrites it from the venue's real quantity and price, or refunds
  the reserved cash if the order died. The target and stop are deliberately *not* re-derived
  from a worse fill: slippage should eat the reward, not move the goalposts
- `settle()` polls orders to a terminal state and records what each one actually cost;
  `sonar/costs.py` turns that into cost per round trip. Slippage is measured against the
  decision mark rather than the limit, so deliberately crossing the spread is not scored as
  a cost, and the summary refuses to name a figure below 20 completed round trips

There is deliberately **no live venue wired up**. SONAR's only calibrated model prices the
Polymarket hourly BTC market, which conventional brokers cannot trade; the assets board, which
they can trade, explicitly asserts nothing. Connecting execution to the board SONAR does not
model would be pointing a careful safety layer at the wrong signal.

If you intend to connect one anyway, [GOING_LIVE.md](GOING_LIVE.md) is the implementation
guide: venue choice, the `BrokerPort` contract, what paper trading hides, and the trap that
there are **two** broker seams here and only one of them is guarded.
