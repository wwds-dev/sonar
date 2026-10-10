# T1-2 review — model-validator, 2026-10-10

Read-only; cached 730-day Binance pull. **Approve.** 599/599 forecasts bit-identical to the study's
on a real 2,040-hour slice; not-full fallback bit-equal to plain EWMA. Study replication: ewma_diurnal
+7.57% 6/6, garch +6.08% 6/6, ewma +3.71% 5/6, trailing72_diurnal +3.73% 5/6 (matches the updated
note). Live-shaped 62-day window, n=16,031: new 1.82682 (+7.50%, 6/6), old 1.88352 (+4.63%);
new better by 0.0567 [0.041, 0.073]. `_sigma` is the only caller.

**P0: none. P1: none.**

| ID | Finding | Outcome |
|---|---|---|
| P2 | (pre-existing) `fetch_hourly` stops on a failed page and returns partial history; last bar always dropped; no freshness check — a 20-day-old EWMA could price the hour; "gappy" comment untrue | Fixed in this branch (= audit T1-6): failed page raises, only the in-progress hour dropped, gaps and >3 h age refuse; 4 tests |
| P3 | "1.830 vs 1.787" was a one-in-three-hours sample, unlabelled | Corrected to every hour: 1.884 vs 1.827 |
| P3 | "equals the study" holds on the same data only | Caveat added |
| P3 | Test covers only full-profile origins | Not-full path verified by hand; existing plain-EWMA test covers it |
