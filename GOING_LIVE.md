# Going live — wiring SONAR to real money

This is the implementation guide for replacing the simulator with a real venue. It is
written against this codebase specifically: file names, function names, and the traps
that are in *these* files rather than generic advice.

Nothing in this document has been applied. `sonar/execution.py` still talks only to
`SimBroker`, and `sonar/alpaca.py` still refuses any host but the paper one.

---

## 0. The arithmetic, before any code

This shapes the design, so it comes first.

SONAR's own numbers say it has no edge. Five pre-registered studies across 116,563
asset-days found nothing that survived multiple-testing correction. The score is therefore
uncalibrated, and `scoring.py` prices every plan off a driftless random walk:

```
P(profit) = stop / (target + stop) = 1 / (1 + R:R)
```

With `K_TARGET = 1.5` and `K_STOP = 1.0`, that is `P = 0.40`, and the expected value is

```
EV = 0.40 × 1.5 − 0.60 × 1.0 = 0
```

Exactly zero, gross of costs. That is not pessimism, it is the definition of the model:
a driftless walk with a 1.5:1 target has no edge by construction, and the research
failed to find drift to add to it.

Now subtract costs. If a round trip costs `c` (spread + commission + slippage), expressed
as a fraction of the amount you risk per trade:

```
EV = −c   per trade, every trade
```

At crypto taker fees of 0.2% a side and 1% of a €2,000 account risked per trade, `c` is
roughly 4% of the risk unit — about €0.80 a trade. A hundred trades is about €80, and the
distribution around it is wide enough that a good month proves nothing.

**What this means for the code**, which is why it is here and not at the end:

- The caps in `DEFAULT_LIMITS` are the product, not a formality. Size them so that being
  wrong about all of the above costs you an amount you have already decided to spend.
- Do not auto-trade. `Guard.submit` refuses an unconfirmed intent — keep that.
  Zero edge plus automation means a bug is the only thing with a nonzero expectation.
- Track realized cost per round trip from day one (§5). It is the one number that is
  definitely real, and it is the number that decides whether to continue.

The purpose of the app is not void without this. It asked whether the edge existed and
answered honestly, which is more than the post that started it managed. But you want to be
able to act, so here is how to do it without the app lying to you on the way.

---

## 1. What already exists — and the one trap

`sonar/execution.py` is the whole safety layer and it is already written and tested:

| Rule | Where |
|---|---|
| Human confirmation required | `Guard.submit` refuses `confirmed=False` |
| Idempotency | `OrderIntent.client_order_id`, recorded *before* the send |
| Per-order notional cap | `Guard.check` |
| Orders/day, open positions, quantity caps | `Guard.check` |
| Instrument allowlist, fails closed when empty | `DEFAULT_ALLOWLIST = ()` |
| Unpriced orders rejected | `Guard.check` — no limit price means no notional to cap |
| Append-only audit log | `AuditLog`, JSONL under Application Support |
| Kill switch | `Guard.panic` |
| Never retry an unknown outcome | `Guard.submit` halts and tells you to reconcile |

A live venue implements `BrokerPort` and the guard is unchanged. That is the design.

### The trap: there are two broker seams, and only one is guarded

```
sonar/portfolio.py   Broker.execute(symbol, direction, units, price)
                     └─ PaperBroker, AlpacaPaperBroker
                     └─ NO guard. Market orders. No caps, no confirmation,
                        no idempotency, no audit, no kill switch.

sonar/execution.py   BrokerPort.place(coid, symbol, side, quantity, limit_price)
                     └─ SimBroker only
                     └─ Behind Guard. Every rule above applies.
```

`portfolio.Broker` is the obvious place to add a live broker — it is where Alpaca already
sits, it is what the Book tab calls, and `default_broker()` picks it up automatically.

**Do not put a live venue there.** `AlpacaPaperBroker.execute` sends
`{"type": "market"}` with no cap check of any kind. That is correct for paper and
catastrophic for live: a market order with a quantity bug has no upper bound on what it
costs you, and nothing in that path would stop it.

The live venue goes behind `BrokerPort`, and the portfolio seam gets an adapter that
routes *through* the guard (§4).

---

## 2. Choosing a venue

You are in Germany, which rules out most of the obvious answers.

| Venue | API | Reality for a German retail account |
|---|---|---|
| **Trade Republic** | none | No public API. Already investigated and closed — see README. |
| **Revolut** | none for investments | No public retail-investment API. Closed. |
| **Alpaca** | excellent REST | Onboarding for EU retail is limited and changes; verify before building. The paper adapter you already have is the same API shape. |
| **Interactive Brokers** | Client Portal Web API, TWS API | The realistic choice for EU equities/FX. Serves Germany, full API, and IBKR Ireland is the entity you would face. |
| **Kraken / Bitstamp / Coinbase Advanced** | REST + HMAC | Serve Germany, no MiFID onboarding friction, 24/7, fractional units, small minimums. |

### Two recommendations, for different goals

**If the goal is to exercise the machinery at the smallest possible stake:** a crypto
exchange. No market hours to model, fractional sizes so €20 positions are possible,
minimum order sizes in the single-euro range, and the assets are already in your universe.
Fees are the worst of any option (0.1–0.4% a side), which makes §0 bite hardest here — but
you will find every bug for €50 rather than €5,000.

**If the goal is equities with realistic costs:** Interactive Brokers.

A detail that matters for this codebase: **IBKR's Client Portal Gateway is a local process
exposing REST on `https://localhost:5000/v1/api/`.** You authenticate in a browser once,
then talk to it with `urllib`. That keeps SONAR's zero-dependency constraint intact — no
`ib_insync`, no socket protocol. Kraken's REST API is likewise reachable with stdlib
`urllib` + `hmac` + `hashlib` + `base64`.

Verify current onboarding, fees, and API terms yourself. Those change, and I would rather
you check than take a stale table on faith.

---

## 3. Writing the BrokerPort

Create `sonar/venues/<name>.py`. It implements five methods and knows nothing about SONAR.

```python
class LiveBroker:
    """A real venue. Every method here can move money."""

    live = True                      # never let this be inferred
    name = "kraken-live"

    def describe(self) -> dict:
        return {"venue": self.name, "kind": "LIVE",
                "detail": "REAL MONEY — orders here settle against your account"}

    def place(self, coid, symbol, side, quantity, limit_price) -> dict: ...
    def cancel(self, order_id) -> dict: ...
    def working_orders(self) -> list[dict]: ...
    def positions(self) -> list[dict]: ...
```

Requirements that are not optional:

**Pass `coid` to the venue as its client order id.** Every serious venue supports one
(`userref` on Kraken, `client_order_id` on Alpaca, `cOID` on IBKR). This is what makes the
idempotency in `Guard` real rather than decorative: if the connection drops after the
request leaves and you resend, the venue rejects the duplicate id instead of opening a
second position. Without it, `Guard`'s idempotency only protects against double-clicks
within one process.

**Limit orders only.** `Guard.check` already rejects unpriced intents. Do not add a market
path "for closing" — see §6 on flattening.

**Return the venue's own status, unmapped.** Do not normalise `accepted` into `Filled` to
match `SimBroker`. Callers must learn that a live order is asynchronous.

**Never swallow an exception.** `Guard.submit` treats a raised exception as *outcome
unknown* and halts, which is correct. A `try/except: return None` in the adapter converts
"I may have just opened a position" into "nothing happened", which is the single worst bug
available in this file.

### Distinguishing live from paper at the type level

`sonar/alpaca.py` makes the paper host a module constant so there is no argument to
override. Do the mirror image: make the live adapter announce itself loudly and require an
explicit opt-in that cannot be reached by accident.

```python
LIVE_ACK = "I ACCEPT REAL MONEY LOSSES"

def __init__(self, ..., acknowledgement: str = "") -> None:
    if acknowledgement != LIVE_ACK:
        raise LiveTradingRefused(
            "the live adapter requires an explicit acknowledgement argument")
```

A constant a caller must type in full is not security, but it does mean no import,
autocomplete, or config-file typo reaches a live order, and it makes the diff that enables
live trading impossible to miss in review.

---

## 4. Routing the app through the guard

The Book tab calls `portfolio.Broker.execute(...)`. To make that path safe, adapt rather
than replace:

```python
class GuardedBroker:
    """Presents the portfolio's Broker interface, enforces the execution Guard.

    The portfolio seam takes market orders and applies no limits. This wraps the
    guarded path in that shape so the existing UI keeps working without gaining
    an unguarded route to a live venue.
    """

    def __init__(self, guard: execution.Guard) -> None:
        self.guard = guard
        self.live = True
        self.name = guard.broker.describe()["venue"]

    def execute(self, symbol, direction, units, price) -> dict:
        side = "BUY" if direction.upper() in ("LONG", "BUY", "COVER") else "SELL"
        intent = execution.OrderIntent(
            symbol=symbol, side=side, quantity=units,
            limit_price=price,          # never None — the guard rejects unpriced
            source="book-tab", note=direction.upper())
        # confirmed stays False. The UI must set it from an explicit human action,
        # not from the fact that a button was wired up.
        return self.guard.submit(intent)
```

Then in `portfolio.default_broker()`, leave the default alone. Live must never be the
fallback:

```python
def default_broker():
    # unchanged: Alpaca paper if configured, else the internal book.
    # A live broker is constructed explicitly by the caller, never selected here.
```

The confirmation must happen in the UI, and the dialog should render
`intent.describe()` — it exists to be the exact line a human approves — plus
`guard.broker.describe()["kind"]`. A paper habit of clicking through must not
survive contact with a live venue, so the live dialog should look different enough
to interrupt muscle memory.

---

## 5. What paper trading hides

Every item here is something `PaperBroker` and `SimBroker` get wrong in your favour.

**Fills are asynchronous.** `SimBroker.place` returns `status: "Filled"`. A real venue
returns `accepted` or `new`, and the fill arrives later or never. You need an order-state
poller and a concept of a working order that the current code does not have.

**Partial fills exist.** You ask for 40 and get 12, then 9, then the rest — or the rest
never comes. Position quantity must come from `broker.positions()`, never from the intent
you sent.

**The price you see is not the price you get.** `PaperBroker` fills at the quoted price.
Your quotes are delayed (Yahoo is 15 minutes for many symbols), so a limit at the "current"
price may be far from the book. Derive limit prices from the venue's own top-of-book, not
from `assets.py`.

**Precision rules reject orders.** Tick size, lot size, minimum notional, and quantity
decimals differ per instrument. This is the most common first live error. Fetch the
venue's instrument metadata and round to it before sending.

**Costs are per-instrument and must be measured.** Log for every round trip: intended
price, fill price, commission, and the difference. After 20 closed trades you will have an
empirical `c` for §0. If it exceeds what you assumed, the answer is fewer, larger trades —
or none.

**Short selling is a different animal.** `portfolio.py` treats SHORT as a sign flip. Live
it needs a margin account, borrow availability, and carries borrow fees and buy-in risk.
Go long-only for v1. `K_STOP` losses on a short are not symmetric with a long.

**Your account may change without you.** You might trade manually in the broker's own app.
Local state and venue state will diverge. See §6.

**Rate limits are real.** `Guard.check` calls `self.broker.positions()` on every single
check, and `AuditLog.seen_client_id` re-reads the entire log file. At 10 orders a day
neither matters. If you ever raise `max_orders_per_day`, cache the positions call with a
short TTL before you get throttled mid-submit.

---

## 6. Changes the guard itself needed before live — **done**

These three gaps were closed in `sonar/execution.py`, with 28 new tests. They are worth
having whether or not you ever go live: a kill switch that leaves you holding a position is
a bug in the simulator too.

**`Guard.flatten(prices=None, slippage=0.01)`** — closes every open position, and is the
half of the kill switch that was missing. `panic()` now cancels working orders, flattens,
*then* latches, in that order.

Its exemptions look like holes in the limits and are the opposite. Flatten ignores the halt
latch, the daily order cap, the notional cap, and the allowlist, because every one of those
exists to stop you *taking on* exposure and none should be able to stop you shedding it. A
daily cap you have hit would otherwise leave you holding a position with no way to close it.

Idempotency is the one rule that still applies, and it matters more here than anywhere: a
duplicate closing order does not flatten you twice, it opens the opposite position. The
nonce is derived from the position itself (`flat-{symbol}-{qty}`) rather than random, so a
repeat is refused while a genuinely changed holding — a partial fill landed — passes.

Closing orders are priced *through* the mark: below it to sell, above it to buy. A limit at
the mark may never fill, which leaves exposure open during the one operation meant to
remove it; a market order has no worst case at all. A marketable limit crosses the spread
and still caps the fill. A position with no usable price is **reported, not guessed at**.

**`Guard.reconcile(expected=None)`** — unchanged when called bare. Hand it
`{symbol: signed quantity}` as local state believes it stands, and any disagreement halts
the guard. Call it at startup: a position opened by hand in the broker's own app is
invisible to local state, and both directions are caught (venue-only and local-only).
Comparison uses an epsilon, since crypto quantities are fractional.

**Equity now comes from the venue.** `BrokerPort.equity()` is required rather than
optional, and `max_notional_pct_equity` (default 10%) is checked against it on every order.
Putting the check in the guard rather than in `scoring.position_size` means it holds even
if the sizing code is wrong — which is the point of a backstop. A port that cannot report
equity is refused, the same way an empty allowlist permits nothing.

Still worth doing before you go live: revisit `DEFAULT_LIMITS`. `max_order_notional: 500.0`
is a sane simulator default and probably 20× what you want on day one.

---

## 7. Secrets

Live API keys do not go in `.env`. That file is git-ignored, but it is plaintext, it gets
copied when you duplicate a project folder, and it is readable by everything you run.

Use the macOS Keychain via `keyring`, the pattern already established in `unblock_tracker`.
`CLAUDE.md` documents the packaging trap that comes with it: `keyring` resolves backends
through entry points, so a PyInstaller build needs explicit `--hidden-import` or it
silently no-ops once frozen — and a credential store that silently returns nothing is
exactly the failure you do not want here.

Additionally, at the venue:

- Create an API key with **trading enabled and withdrawal disabled**. Every exchange
  supports this separation. Then a total compromise of the key cannot move coins off the
  account.
- Bind the key to an IP if the venue allows it.
- Keep a separate read-only key for anything that only needs positions and equity.

---

## 8. Staged rollout

Do not skip stages. Each one is designed to fail cheaply.

1. **Adapter against the venue's own paper/sandbox endpoint.** Same code, same auth
   shape, no money. Run it four weeks. This is where precision rules, async fills and
   partial fills surface.
2. **Reconciliation drill.** Trade manually in the broker's app, restart SONAR, confirm it
   detects the divergence and halts. If it does not, §6 is not finished.
3. **Kill-switch drill.** Open a position, hit `flatten()`, confirm you are flat at the
   venue — not just that the log says so.
4. **Live, minimum stake.** One instrument, long only, `max_order_notional` at €25,
   `max_orders_per_day` at 2. The goal is not profit; it is discovering what a real fill
   costs you.
5. **Twenty closed round trips.** Compare realized cost per trade against §0. Compare
   realized win rate against the model's 40%.
6. **Decide with data.** If realized cost per trade exceeds the edge — and on current
   evidence the edge is zero — then the honest read is that this is a well-built machine
   for a market that does not pay, and the right move is to stop at stage 5. Deciding that
   deliberately, with your own numbers, is a real outcome and worth the €50 it cost.

---

## 9. Tax and regulatory reality (Germany)

Flagging, not advising — get a *Steuerberater* before the first live order, not after.

- **Kapitalerträge** are subject to *Abgeltungsteuer* (25%) plus *Solidaritätszuschlag*
  and church tax where applicable.
- **A German broker withholds automatically. A foreign one does not.** IBKR Ireland and
  any US or offshore venue leave you to self-declare in *Anlage KAP*. This surprises people.
- **Crypto is different.** Held privately, disposals fall under §23 EStG as *private
  Veräußerungsgeschäfte* — with a one-year holding period that a trading app will never
  reach. Every single disposal needs a record.
- **Frequent algorithmic trading can raise the question of *gewerblicher Wertpapierhandel*** —
  being treated as a commercial trader rather than a private investor, which changes the tax
  treatment entirely. Ask specifically about this, because "I wrote a program to do it" is
  exactly the fact pattern that prompts the question.
- **Your audit log is an asset here.** `execution_audit.jsonl` is append-only and records
  every intent, decision and venue reply with timestamps. Keep it, back it up, and do not
  rotate it. Add realized fill price and commission to it (§5) and it becomes most of what
  a tax preparer needs.

---

## 10. What stays off regardless

- **No auto-trading.** `Guard.submit` requires human confirmation. With a measured edge of
  zero, automation converts every bug directly into loss and adds nothing on the other side.
- **No live default.** `default_broker()` must never return a live venue. Live is
  constructed explicitly, with the acknowledgement constant, by a caller that means it.
- **No retry on unknown outcome.** Already correct in `Guard.submit`. Do not soften it —
  reconcile against the venue instead.
- **Withdrawal permissions off** on every API key, forever.

---

## Where I stand

I will not write the live adapter or flip the switch — connecting funded accounts is a
decision that should require your hands. Everything up to that line I am glad to build:
the `flatten()` and startup reconciliation in §6, the cost-measurement logging in §5, a
`GuardedBroker` adapter, or the whole venue adapter written and tested against a
sandbox endpoint with the live host unreachable, so that going live is a one-constant
change you make yourself and can see clearly in a diff.

Ask, and I will start with §6 — those three gaps are worth fixing whether or not you ever
go live, because a kill switch that leaves you holding a position is a bug in the
simulator too.
