# SONAR code audit — 2026-10-10

Produced by the `code-reviewer` role, read-only. Read every module in `sonar/`,
`sonar/research/`, `sonar/playmaker/`, `sonar/macro/`, `main.py`, `ui/worker.py`, `ui/tray.py`,
`ui/appkit_guard.py`, `ui/tabs.py`, `ui/words.py`, charts; in `ui/app.py` the asset board,
Terminal, Book, Portfolio tabs, refresh/config/shutdown and thread wiring (rest grepped).
**[repro]** = reproduced by running the repo's code from scratch scripts (temp `SONAR_DATA`,
`python -B`, `git status` unchanged); **[code]** = proven by reading the call path. The test
suite was not run.

## P0 — loss of the record
**P0-1 Taking over the engine lock keeps a stale in-memory book and overwrites the holder's
`state.json`/`portfolio.json` [repro].** `core.py:101,121` load `Engine`/`Portfolio` once in
`Live.__init__`; `core.py:629-633, 654-683` (`run`, `_wait_for_lock`) return True on takeover
then `warmup()`/`_poll()` with no reload; `engine.py:155-178` and `portfolio.py:200-211` `save()`
write the whole object. Scenario: agent holds the lock and trades for hours → app launches as
follower with old state → agent stops → app takes the lock → first save (settle, scored hour,
`set_risk`, book mark) overwrites the file. Reproduced: holder wrote 1 trade; follower's `save()`
left 0 trades and a $10,000 bankroll. `daily_backup` doesn't help (holder already made today's).
Also: `engine.risk` stays at start-up value while `Live.risk` mirrors the holder
(`_mirror_config`, `:750-759`); positions opened via forwarded `/api/trade` vanish;
`Live.__init__:105-106` `engine.set_risk()` saves when `--risk` is passed, even without the lock.
Fix: reload engine+book right after a successful takeover, before `warmup`; no `save()` in
`__init__`/`configure` without the lock; test "holder writes, follower takes over, file keeps trades".

## P1 — wrong numbers / corruption in normal use
**P1-1 Fair-odds warm-up P&L is booked into the live bankroll, headline P&L and sizing [repro].**
`engine.py:406` (`seed_backtest`) adds synthetic trades to `self.bankroll`; `stats()` `:433-434`
derives `total_pnl`/`return_pct` from `bankroll - starting_bankroll` (only `n_trades`, `win_rate`,
`profit_factor` exclude seeds); shown at `ui/app.py:3278-3284`, `ui/tray.py:159`; Kelly sized from
`self.bankroll` (`:335`). Fresh install: `n_trades=0, n_seeded=36, total_pnl=-1327.45,
return_pct=-13.27`, bankroll 8672.55. Fix: keep live bankroll separate; compute from `kind=="live"`.

**P1-2 A stale/older candle voids a live position and drops the score snapshot [repro].**
`engine.py:193-195, 235-248` treat any `candle.open_time != current_hour` as rollover, including a
backward step; `feeds.py:137-147, 96-111` don't apply `is_stale` to the Coinbase fallback, and
`parse_coinbase_candles` falls back to `rows[0]`. Binance drops out, Coinbase still shows hour H-1
→ `close_lookup(H)` None → `open_position=None`, `n_voided += 1`; `_score_hour` clears
`pending_score`. Reproduced. Fix: ignore candles older than `current_hour`; `is_stale` on Coinbase;
require `row[0]==now_hr`.

**P1-3 Unlocked mutation of the book from three threads → double-credited cash, corrupt
`portfolio.json` [repro].** `core.py:405-438` (`trade`, `close_position`) run without `self.lock` on
UI thread (`ui/app.py:3183,3191`) and HTTP threads (`server.py:69-80`); `_rescan`→`_mark_book` on the
poll thread; `configure` calls `_rescan()` on `ConfigThread` (`ui/worker.py:78-91`, `core.py:471-472`);
`Portfolio.close` (`portfolio.py:272-291`) does find→credit→`list.remove` unlocked. Manual Close racing
a barrier hit: cash 7763.93 → 12536.07 (two credits of 2386), second thread `ValueError`. `save()`
shares a fixed `.tmp` name: two writers → 8,657 `FileNotFoundError`s in 2 s. Fix: `RLock` on
`Portfolio`/`Engine` mutators and `save`; `Live` methods take it; serialise `_rescan`.

**P1-4 Forced close/equity point on a symbol missing from the current board books it at entry price
[repro].** `core.py:429-435` `prices.get(pos.symbol, pos.entry)`; `assets.py:426-427` drops rows above
`max_daily_vol` (or on fetch failure); `portfolio.py:464-468` skips the held-position price guard when
`force=True`. Hold DOGE, DOGE −30%, switch to Conservative, Close → exit 1.0, pnl 0.0 vs true 0.70;
`mark()` stops watching its barriers. Fix: keep a last-known price per held symbol independent of the
display filter; refuse the close if none.

**P1-5 Calibration counts MANUAL closes as target hits [repro].** `calibration.py:103` `wins = pnl>0`,
`:116`, via `report()`→`implied_edge`→`core.py:308-309`→`AssetScanner.edge_sigma`/`calibrated`.
15 MANUAL +$1 closes + 5 STOPs → hit rate 0.75, `implied_edge_sigma` 0.6337, `calibrated=True`;
shifts every row's displayed P(profit). Fix: grade only `TARGET`/`STOP`; count MANUAL as censored.

## P2
- **P2-1** `hourlyvol.forecast()` (`research/hourlyvol.py:332-343`) multiplies a raw-return EWMA by the
  diurnal factor; the study's `ewma_diurnal` (`:247-261`) runs EWMA on `r²/fac` first. The "+7.51%,
  6/6 blocks" claim (`:289-310`) was measured on a different estimator. Synthetic diurnal series: QLIKE
  1.3812 (validated) vs 1.3941 (shipped) vs 1.4054 (plain EWMA) — gain ~0.9%, not 7.5%. No test ties
  them (`tests/test_hourlyvol.py`). (Independently confirmed on real data by the model-validation audit.)
- **P2-2** `fetch_hourly` (`hourlyvol.py:362-379`, `core.py:806-813`) accepts a partial history: if page
  2 raises it `break`s and returns page 1 ending ~20 days ago; also pops the last row blindly;
  `forecast()` has no recency check → σ=0.000605 "for the hour after 2026-09-19", used by `Live._sigma`
  for an hour (`VOL_EVERY`). Fix: require `times[-1] >= now-2h` and contiguity, else default σ.
- **P2-3** `_poll` (`core.py:815-856`) fetches the candle, then blocks in `_sigma()`/`_rescan()`
  (8–26 Yahoo fetches, 24 RSS, up to 10 Nasdaq calls at 12 s, 4 institution feeds), then fetches the
  market and ticks on a stale price (σ_h≈0.45%, τ≈0.3: 10 s stale ≈ ±4¢ model P(up) ≈ `edge_threshold`).
  Spurious edges after every rescan; `spark` stamped stale. Fix: move off the poll thread; fetch
  candle+market immediately before `tick`.
- **P2-4** `core.py:853-856` runs `_build` under `Live.lock`; at quarter/year horizons `_build`→
  `macro.get()` (`:918-919`; `macro/__init__.py:229-234`) fetches six FRED series at 25 s each → UI
  (takes `Live.lock` every second, `ui/app.py:3228`) blocks up to ~150 s every 6 h if FRED is down.
- **P2-5** `feeds.py:214-217` `strftime("%B"/"%p")` follow `LC_TIME`; Qt calls `setlocale(LC_ALL,"")`.
  `LANG=de_DE.UTF-8` → slug `bitcoin-up-or-down-oktober-10-2026-7-et`; primary lookup fails (launchd
  agent has no Qt, unaffected). Fix: English month table, `h%12 or 12`, `"am"/"pm"` explicitly.
- **P2-6** DST fall-back (`feeds.py:214-223`): 2026-11-01 two 01:30 ET instants give the same slug; second
  hour returns the ended market → `current_market` returns None (doesn't fall through to the series
  query since `ev` non-empty). **Lands before 2026-11-01.**
- **P2-7** `assets.py:426-427` drops rows above `max_daily_vol` before `_standardise_components`
  (`:492, 519-542`); class median/MAD computed on the filtered set → same asset scores differently by
  profile (24.3 vs 24.7; up to 1.3 pts), contradicting `risk.py`'s "never mutates a confidence number".
  Fix: standardise on the full set, then filter.
- **P2-8** `alerts.py:112-143` keys `_prev` by symbol only; vol model changes by horizon
  (`volatility.py:337-365`), confidence by profile → false "1.7× its own recent level" alerts after
  `configure()`. `data_age` taken from payload `generated`, not row `data_age_s` (`:121-122`), so `stale`
  almost never fires. Fix: key on `(horizon, risk)`; first scan after a change is baseline.
- **P2-9** LLM calibration scores UNCLEAR as a miss (`engine.py:697, 705`; schema `llm.py:86`) →
  zero-information LLM reads 0% at conviction 0-24 and ~49% above 50 — exactly the "conviction tracks
  reality" shape the table tests. `agreed_with_model_pct` same. Fix: exclude UNCLEAR, bucket separately.
- **P2-10** `server.py:45-82` no Origin/Host/content-type check; non-dict JSON body (`[]`) crashes
  the handler (`body.get`). (See `security.md` P1-1.)
- **P2-11** `version.info()` omits `dirty` for the "unknown" build (`version.py:193-194`);
  `version.py:279` and `main.py:33` read it → `KeyError('dirty')` in `tooltip()` (`ui/tray.py:89`,
  `ui/app.py:371`) and `--selftest`. Unstamped bundle can fail to start. Fix: `"dirty": False`.
- **P2-12** Book tab grades "won"/"lost" on P&L sign (`ui/app.py:2050-2054, 1858`;
  `portfolio.py:393-397`) → MANUAL closes shown as "N won" vs "plan promised 40%".

## P3
- P3-1 `feeds.historical_decision_points` (`feeds.py:333-388`) off by one minute (price at :41, τ for :40).
- P3-2 `_get` (`feeds.py:46`) misses `http.client.HTTPException`; `IncompleteRead` replaces the whole
  snapshot with `{"status":"error"}` for a cycle (`core.py:637-639`).
- P3-3 `_midpoint` returns 0.0 on an unparsable value (`feeds.py:264-272`); `buyability` excludes
  0.02–0.98 (`engine.py:509`) but `_maybe_enter` doesn't, so the verdict doesn't measure what is traded.
- P3-4 `_iso_to_unix` (`feeds.py:308-315`) discards explicit offsets; missing `endDate` → "next top of
  hour", satisfying alignment for the wrong market.
- P3-5 Settlement mixes sources (`engine.py:236-241`); source not stored on `Trade`/scorelog.
- P3-6 Earnings calendar uses local date for a US calendar (`events.py:107-125`; `research/
  earnings.py:196-205`); from 00:00-06:00 German time "today" is the next US day; same-day pre-market
  print scored as upcoming catalyst.
- P3-7 News keyword false positives [repro] (`assets.py:309-326`): "US intel officials" → Intel, "Visa
  rules for H-1B" → Visa, "Shell companies" → Shell, "Turkey prices…" → USD/TRY, "Apple harvest" → Apple,
  "Meta analysis" → Meta. News carries 0.35 weight in confidence.
- P3-8 `enginelock.py`: stale-lock path lets two processes both unlink and create; PID reuse; `holder()`
  raises on malformed lock (`int(d.get("pid"))` with None / non-dict).
- P3-9 Dormant code: `GuardedBroker` routes SELL/COVER through `Guard.check` so max-open-positions
  (`execution.py:480-481`) and daily-cap (`:476-478`) reject closes (flatten exempt, `Portfolio.close`
  not); `AlpacaPaperBroker` (`alpaca.py:125-190`) declares `synchronous=False`, has no `settlements()`,
  returns no `client_order_id` → positions PENDING forever; `portfolio.default_broker()` unused.
- P3-10 Research validity: salted `hash()` in `random_control` (`features.py:287-289`); survivorship in
  `fetch_universe` (`universe.py:97-132`); weekday study uses UTC weekday (`backtest.py:651`);
  `run_symbol` drops TIMEOUT (`:267`); HAC over concatenated symbols ignores cross-symbol correlation.
- P3-11 Dixon-Coles home advantage applied to every fixture incl. neutral-site (`playmaker/poisson.py:192`).
- P3-12 Macro `stale` only true when every series empty (`macro/__init__.py:163`).
- P3-13 `llm.available()` ready if `~/.config/anthropic` exists even empty (`llm.py:144-148`).
- P3-14 Wording: Terminal stat labelled "edge" and coloured by side (`ui/app.py:1472, 3278`), tray
  "edge +x¢" (`ui/tray.py:170`); it is midpoint disagreement. Per AGENTS.md ("copy that implies edge is
  a bug"), consider "disagreement" in expert mode too.
- P3-15 UI-thread blocking network: `Live.trade`/`close_position`/`set_protocol` → `_forward` (2 s
  POST + 2 s mirror fetch) while following an unresponsive holder (`ui/app.py:1786, 3183, 3191`).

## Checked and dismissed
`model.prob_up`, `lattice_distribution`, Kelly/risk maths, `scoring.barrier_probability`, devig methods
(multiplicative, power, Shin), Elo, Dixon-Coles fitting; hourly-vol study loop, `backtest.run_symbol`,
`research/panel.build`, regime labelling free of look-ahead; `buyability()`/`model_vs_market()` cost
~6 ms / 2 ms at 3000 rows. Gamma `bestBid/bestAsk` staleness vs CLOB not verifiable without live data.

**Suggested order:** P0-1; P1-1…P1-5; P2-1/2/3; P2-5/P2-6 (DST fix before 2026-11-01).
