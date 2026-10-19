# providers-wiring: domain-finance review, Define pass (2026-10-19)

Reviewer: `domain-finance` (read-only). Saved by the orchestrator. The playbook is stale (`status: baseline`).

**Verdict:** option B is right: there's no data-path change, so the 30-day run and look 1 stay comparable. But as
written, the success measures leave the false crypto/FX fallback claim visible and require a new false sentence.
Fix both before the gate.

The spec's evidence checks out. Nothing imports `sonar/providers.py`. README:177-179, 192 and 397-398,
`static/docs.html:409-417`, `.env.example:10-11`, `TODO.md:98` and `SUGGESTIONS.md:11` all say what the spec says they
do.

## P1
- **P1-1. The crypto/FX fallback claim survives option B.**
  - **Where:** `static/docs.html:398-399` ("Keyless second sources, so crypto and FX survive Yahoo breaking") and
    README:183-185 and 190-191 ("crypto still resolves via CoinGecko, FX via Frankfurter").
  - **Why it's false:** CoinGecko and Frankfurter appear only in `providers.py`.
  - **Fix:**
    - Add these lines to the Problem section and Measure 1.
    - Add "survive Yahoo breaking", "still resolves" and CoinGecko/Frankfurter (outside the BTC/feeds context) to
      the grep.
    - Remove the dangling "See the provider layer below" at docs.html:397.
- **P1-2. Measure 1's required sentence "Yahoo is the only price source for every class" is itself false.** The BTC
  hourly model uses Binance, with a wired fallback to Coinbase (`sonar/feeds.py:5-8, 148-153`, `core.py:1515`,
  README:66, docs.html:393).
  - **Fix:** "Yahoo is the only source for the Screener's equities, FX, commodities and crypto rows, with no
    fallback; the BTC hourly model uses Binance, with Coinbase if Binance is unreachable."

## P2
- **P2-1.** Spell out what the user sees during a Yahoo outage:
  - one source;
  - cached prices, with the Updated column ageing from gold to red;
  - shadow grading and the equity seed also depend on Yahoo (`core.py:619, 1065`), so an outage delays grading.

  README:200-202 currently reads red as "losing ground". The architect should confirm how grading behaves on a fetch
  failure before the copy says so.
- **P2-2.** Closing `TODO.md:98` deletes the only mention of the ~15-minute quote delay. Fix: add a disclosure (quotes
  may be delayed by exchange; Updated shows when SONAR fetched the price, not the exchange time), or keep it as an
  owner question. The delay itself is not verified.

## P3
- **P3-1.** Record "prices: Yahoo chart endpoint only, no fallback, run window X–Y" in the look-1 and v1 result
  records (`docs/specs/v1-product.md`, `CONFIDENCE.md`).
- **P3-2.** If `providers.py` is deleted, add README:370 (the module map) to Measure 4.

---

# Review pass on the diff (2026-10-19)

**Verdict:** the corrected copy holds up against the code, with no P0 or P1.
- The single source (`assets.py:395-401`), board staleness (`:400-409`, `ui/app.py:176-177`), shadow grading
  (`core.py:1047-1072`, `calibration.py:281-282`), seed (`core.py:98-99, 620-622`) and delay disclosure all match.
- `tests/test_providers_docs_truth.py`: 83 passed.

## P2
- **P2-1.** "The BTC hourly model uses Binance, with Coinbase if Binance is unreachable" overstates the fallback.
  - Coinbase only serves the live candle, and only for BTCUSDT (`feeds.py:151-153`).
  - Volatility (`research/hourlyvol.py:381-383`, `feeds.py:157-162`; it falls back to a default σ via
    `model.py:48-60`) and gap settlement (`feeds.py:165-183`) are Binance-only.
  - Fix README:173-174, `static/docs.html:408-409`, the CHANGELOG and the test's required sentence. Also fix README:66
    (an older line): ETH has no Coinbase fallback.

## P3
- **P3-1.** "Keeps scoring from cached prices" holds only while the app runs: the cache is in memory and keyed by range
  (`assets.py:334, 380`). After a relaunch or a horizon change during an outage, rows are missing.
- **P3-2.** After 6 partial answers, seeding stops until the next launch (`core.py:321, 612`). "The equity curve waits"
  implies it will eventually fill.
- **P3-3.** The Updated tooltip (`ui/app.py:165-166`) doesn't mention outages.
- **P3-4.** The shadow copy leaves out the 7-days-after-t_T condition (`calibration.py:283`). Optional.
