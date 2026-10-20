# 09L v0.8.4 — PIT publication audit + options-strike placebo (2026-10-20)
**SHADOW / EXPLORATORY / NO TRADING / append-only**, continuation of v0.8.3.

## Newly executed
- Audited public GitHub commit timestamps for **all 30 daily third-party Deribit option-chain files** dated Sep20–Oct19; each commit postdates the embedded snapshot by 41–58 seconds and predates the next day's snapshot. A five-date subsample showed one file-history commit per day. Git publication timing does not independently authenticate the underlying derivatives feed.
- Fixed candidate options OI strikes $80K/$85K/$87K/$90K/$95K, pre-declared eligibility within 7.5% of the prior snapshot BTC index price. Compare (1) biggest OI strike's direction vs (2) nearest strike's direction over next daily (irregular clock) snapshot. **29 valid date pairs:** biggest OI correct **12**, nearest correct **14**; 4 exclusive wins vs 6 exclusive losses; 19 days both algorithms predict the same direction. When Sep24/25 expiry-boundary transitions are excluded: **11/27 vs 13/27**. These are retrospective descriptive checks; no OOS, and statistical dependence makes naive p-values non-decisive.
- Result: **NO EVIDENCE OF INCREMENTAL ATTRACTIVENESS** in this narrow proxy test. Options strikes are NOT historical liquidation clusters; signed dealer gamma and historical CoinGlass Model2 PIT are missing. Do not extrapolate to price-cascade probabilities.
- Frozen next mechanics test: **v0.8.4 event-time 30s pre / 30s, 60s, 300s post** using the SAME eight bybit BTCUSDT 2026-10-01 v0.8.3 case windows, Tardis source compressed hashes and local_timestamp alignment. Four true observed liq-message windows plus four controls with no message in the selected minute (not genuine 'no-liquidation' labels). Must not infer cancellations, absorption, or signed dealer inventory from top5 snapshots.
- New event-time tick-data replay is **NOT_RUN / NETWORK_BLOCKED** in this local runtime. The reproducible Python runner and full derived CSV/JSON are bundled locally for the user, not committed in this short remote summary; no claim of remote execution.

## Immutable gate
No edits to 00/01/01A/02/03/04/05/06/06C, Futures, Spot, NAV, P&L, capital, reserves, position limits, or trade signal permissions. Research v0.1–v0.8.3 remain unchanged. No merge to main. Do not call an observed liquidation event a verified cluster first-touch.

## Sources and conditions
- Public source repo: https://github.com/pitspa/btc-vol-surface (README states proprietary license; raw chains NOT redistributed)
- Event-time Tardis schema and free first-day sample: https://docs.tardis.dev/downloadable-csv-files
- CoinGlass Model2 API docs: https://docs.coinglass.com/reference/liquidation-heatmap-model2 (range param does not establish arbitrary old snapshot PIT)
- Full reproducible 09L v0.8.4 code, PIT publication audit JSON, sample event ledger and limitations are in the locally exported `09L_RESEARCH_STAGE_v0_8_4_2026-10-20.zip`.

**Remote writeback claim is limited to this summary and derived summary below; stage replay not executed remotely.**
