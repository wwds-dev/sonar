# SONAR v2 — acceptance test plan

The plan for signing off v2. `TESTING.md` is the *automated* coverage roadmap;
this is everything a person has to check, because the suite structurally cannot.

**Run it against `/Applications/SONAR.app`, not the checkout.** Several of the
failures below only exist in a packaged build — a module PyInstaller could not
see, a resource path that moves when frozen, a Qt plugin inherited from a parent
process. A green suite says nothing about any of them.

| | |
|---|---|
| Build under test | `./build_app.sh --install`, then `/Applications/SONAR.app/Contents/MacOS/SONAR --selftest` |
| Automated suite | `./run-tests.sh tests/ -q` — expect **1,073 passed** |
| Time to run this plan | ~30 minutes |
| Prerequisite | A working internet connection. Two cases deliberately need it off. |

**⚠ marks a case that has caught a real regression.** Those are the ones worth
running even when short of time — the list doubles as this project's bug history.

---

## 0. Before starting

| # | Step | Expected |
|---|---|---|
| 0.1 | `./run-tests.sh tests/ -q` | 1,073 passed. A wedge on the Qt window tests is a known issue (§9) — re-run once. |
| 0.2 | `./build_app.sh --install` | Ends with `All checks passed.` then `Installed:` |
| 0.3 | `/Applications/SONAR.app/Contents/MacOS/SONAR --selftest` | `All checks passed.` Reports 7 sports, 5 rated, cycling with no feed. |
| 0.4 | Note the bankroll before you start | You will compare against it in 5.x |

---

## 1. Launch and window

| # | ⚠ | Steps | Expected |
|---|---|---|---|
| 1.1 | ⚠ | Launch from `/Applications`. Time it. | First paint in **under 3s**. *Once took 11s of sequential fetches.* |
| 1.2 | | Count the tabs | Seven: Terminal · Assets · Wire · Book · Macro · Lab · Playmaker |
| 1.3 | | Wait 30s, visit each tab | No tab shows "—" in every field |
| 1.4 | ⚠ | Resize the display to 1280×800 (or check on a laptop screen) | Nothing clipped, no horizontal scroll. *Once opened 4,540pt wide on a 1,280pt display.* |
| 1.5 | ⚠ | Click the **red close button** | Window disappears; menu-bar icon stays; app still running. *Broken twice, two different causes.* |
| 1.6 | | Click the menu-bar icon | Window returns |
| 1.7 | ⚠ | Enter full screen, leave full screen, then close | Window hides and **does not reopen itself** a second later |
| 1.8 | | ⌘H, then click the Dock icon | Window returns |
| 1.9 | | Menu bar → **Quit SONAR** | Process exits. No crash dialog, no "Python quit unexpectedly". |
| 1.10 | | Relaunch, then ⌘Q | Also quits cleanly |
| 1.11 | ⚠ | Relaunch. Leave it running **15 minutes**, clicking between tabs throughout | Stays responsive the whole time. *The Wire's news TTL is 8 minutes; a UI-thread fetch froze the window white and it ignored the close button.* |

---

## 2. Terminal

| # | ⚠ | Steps | Expected |
|---|---|---|---|
| 2.1 | | Read the price | Live BTC price, moves within ~5s |
| 2.2 | | Read the stat row | `price · hour · model · market · edge · tau · bankroll · pnl · trades · win rate · profile` all populated |
| 2.3 | ⚠ | Compare the lattice caption's **P(up)** with the **model** figure above it | They agree. *They disagreed by 10 points at the top of every hour — one counted a bin sitting exactly on the barrier as a win.* |
| 2.4 | | Watch the lattice for a minute | Redraws as price moves; bars at/above the open are coloured differently |
| 2.5 | | Read the equity curve | Renders; a gold **LIVE** marker separates the warm-up from real trades |
| 2.6 | | Press **LLM read on this hour** | Either a read appears, or it says why not. With no API key, "off — no key" is the correct answer, not an error. |
| 2.7 | | Hover every number in the stat row | Each has a tooltip explaining it in plain words |

---

## 3. Assets

| # | ⚠ | Steps | Expected |
|---|---|---|---|
| 3.1 | | Count the rows | **26** instruments (7 Equity · 3 Index · 3 Forex · 11 Crypto · 2 Commodity) |
| 3.2 | | Read the columns | `TREND · PRICE · 1D · MOM · VOL · NEWS · R:R · P(PROF) · SCORE MIX · CONF` |
| 3.3 | | Read **P(PROF)** down the column | A flat **40%**, drawn grey. Anything else means calibration has moved it — check §5.5 agrees. |
| 3.4 | | Check the NEWS column | Quiet / Normal / Elevated / Spike. **No bullish/bearish lean anywhere.** |
| 3.5 | | Click each column header | Sorts, both directions |
| 3.6 | | Change **horizon** (5 options) | Numbers change; board redraws immediately, not on the next tick |
| 3.7 | | Change **risk profile** (3 options) | Same |
| 3.8 | ⚠ | Press **Buy** on a row | Status shows ✓ and "paper money only"; position appears in **Book at once**. *A cached board signature once made this look like a dead button.* |
| 3.9 | | Press **Short** on a different row | Same, direction SHORT |
| 3.10 | | Press **Buy** on the same row again | Refused: "already holding" |
| 3.11 | | Hover each column header | Tooltip explains the number, and CONF's says it is **not** the odds of profit |
| 3.12 | | Hover a row's name | Names where it could actually be traded. 8 of 26 are proxied and 1 is not tradeable — it must say so rather than implying you can buy it. |

---

## 4. Wire

| # | ⚠ | Steps | Expected |
|---|---|---|---|
| 4.1 | | Read the newswire | Headlines with source and age, from more than one press bloc |
| 4.2 | | Find the bloc spread | Renders |
| 4.3 | | Find the earnings / IPO calendar | Populated with dates |
| 4.4 | | Read the alerts panel | Lists alerts, or says nothing is firing |
| 4.5 | ⚠ | Read every alert carefully | **None contains "buy", "sell", "short" or "immediately".** An alert is a notability flag, never an instruction. |

---

## 5. Book

| # | ⚠ | Steps | Expected |
|---|---|---|---|
| 5.1 | | Find the positions opened in 3.8 / 3.9 | Both listed with entry, target, stop, unrealised P&L, progress bar |
| 5.2 | | Check a LONG's barriers | stop < entry < target |
| 5.3 | | Check the SHORT's | target < entry < stop |
| 5.4 | | Press **close** on one | Settles at the current price, moves to closed, bankroll changes by that P&L |
| 5.5 | | Read the calibration table | Either reports, **or says how many more closed positions it needs**. It must not claim an edge below the threshold. |
| 5.6 | | Read the stats | bankroll · total P&L · win rate · profit factor. Profit factor is blank with no losses — not zero, not a crash. |
| 5.7 | | Press **run backtest** | Completes and reports; says it is price-only and excludes costs |
| 5.8 | | Quit and relaunch; return to Book | Open position and bankroll **survive the restart** |

---

## 6. Macro

| # | ⚠ | Steps | Expected |
|---|---|---|---|
| 6.1 | | Read all seven | `10y · curve · fed funds · VIX · real 10y · CPI y/y · unemployment` populated |
| 6.2 | | Read the regime label | Named, with a rationale sentence |
| 6.3 | | Read central-bank communication | Lists releases/speeches. **No direction claimed anywhere.** |
| 6.4 | | Hover each of the seven | The tooltip says what it is *and how to read it* — not a restatement of the label. "Effective policy rate" would be a fail. |

---

## 7. Lab

| # | ⚠ | Steps | Expected |
|---|---|---|---|
| 7.1 | | **Run simulation**, whole watchlist, 2y | Completes; reports trials, hit rate, and an error bar |
| 7.2 | | Narrow the universe to one class, re-run | Fewer trials, still completes |
| 7.3 | | Read component attribution | Each component gets **KEEP / WEAK / DROP / INVERTED** |
| 7.4 | | Find the catalyst component | Says it is **not measured** — the replay has no historical earnings calendar — rather than implying it passed |
| 7.5 | | Change R:R and re-run | Realised hit rate moves toward `1/(1+R:R)`. *This identity is the claim the whole app rests on.* |
| 7.6 | | Press **Start replay** | A setup appears |
| 7.7 | ⚠ | Read the setup line | It does **not** reveal the model's call before you commit |
| 7.8 | | Press Buy, then Short, then **Skip** on successive setups | All three advance |
| 7.9 | | Read the scorecard | Shows **your P&L against the model's**, including on setups you skipped |

---

## 8. Playmaker

| # | ⚠ | Steps | Expected |
|---|---|---|---|
| 8.1 | | Open the sport picker | Seven: NFL · College Football · NBA · MMA (UFC) · International Football · Golf · Cycling |
| 8.2 | | Switch between them | Prop list, context hint and price example all change |
| 8.3 | | Select International Football | Price example shows **three** prices per book |
| 8.4 | | Paste 4 books, 2-way, one clearly generous. Press **Price it** | `books · margin · fair · book spread · best edge · EV / unit · stake` populate |
| 8.5 | | Read the fair-price panel | All three devig methods shown, with the default (shin) marked |
| 8.6 | | Read the screen | The generous book flagged as an outlier with a z-score |
| 8.7 | | Delete two books, re-price | Explains there is no consensus below three books, rather than showing an empty table |
| 8.8 | | Enter a line with only one price | Names the line that failed and why both sides are needed |
| 8.9 | | Select **Golf** | Says plainly that no head-to-head model rates a field event |
| 8.10 | | Select **Cycling** | Says it has **no results feed at all** |
| 8.11 | ⚠ | Read the model's narrative section | Labelled commentary, and states the stake is **not** derived from it |

---

## 9. Docs

| # | Steps | Expected |
|---|---|---|
| 9.1 | Press **Docs** | Opens; §1 is "Start here — plain English" |
| 9.2 | Click every entry in the table of contents | All 13 resolve |
| 9.3 | Read the glossary | 24 terms across markets, probability, betting, macro |
| 9.4 | Check §13 | Documents Playmaker, including Kaunitz's account-limiting caveat next to the profit figure |

---

## 10. Degraded conditions

The cases most likely to be skipped, and the ones that produced the worst bugs.

| # | ⚠ | Steps | Expected |
|---|---|---|---|
| 10.1 | | Turn Wi-Fi **off**. Relaunch. | Starts. Shows stale/empty values with a visible reason. **Does not hang, does not crash.** |
| 10.2 | ⚠ | With Wi-Fi off, click every tab | All render. *A stale feed must read as missing, never as a price — Binance served a delisted pair's last candle for years without erroring.* |
| 10.3 | | Turn Wi-Fi back on | Recovers within one poll cycle without a restart |
| 10.4 | | Launch a **second** SONAR while the first runs | Second says **READ-ONLY** and names the conflict. Two engines settling the same hour would double-count the book. |
| 10.5 | | Quit both. Relaunch. | Starts normally — the stale lock is reclaimed |

---

## 11. Exit criteria

v2 signs off when:

- [ ] Every ⚠ case passes. These are regressions; a failure is a re-opened bug.
- [ ] §0 passes — build, self-test, and 1,073 automated tests.
- [ ] No case in §1 (launch, window, quit) fails. The app being hard to close or
      quit has been reported twice and is the most visible class of defect here.
- [ ] §10 passes. An app that misbehaves offline is worse than one that says it
      is offline.
- [ ] Any failure is either fixed, or written into `TODO.md` with its evidence.

## 12. Known, and not blocking

- **The Qt window tests wedge about one run in three.** A PySide6 teardown race
  leaves a pthread mutex orphaned below Python, so no in-process timeout can
  fire. `./run-tests.sh` bounds it externally. The app is unaffected.
- **The calibration table will be empty** until ~20 paper positions have closed.
  That is the honest state, not a defect.
- **No Finnhub key** means equities ride on one undocumented Yahoo endpoint, with
  a ~15-minute delay during market hours.
- **Golf and cycling have no rating model**, and cycling has no results feed.
  Both are stated in the UI.
