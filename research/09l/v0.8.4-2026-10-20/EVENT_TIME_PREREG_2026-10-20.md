# 09L v0.8.4B — event-time Bybit microstructure preregistration
Date: 2026-10-20. Registration BEFORE new event-time source replay; additive branch only. **SHADOW / NO TRADE AUTHORITY.**

## Fixed source and cases
Tardis first-of-month (2026-10-01 UTC) Bybit BTCUSDT, same four SHA-verifiable sources as v0.8.3; no replacement date.
Event minutes frozen from prior observed-liquidation output: 07:24 SELL, 08:32 SELL, 17:28 BUY, 18:38 BUY. Controls are 13:49, 14:19, 15:10, 15:49 UTC; no observed liquidation MESSAGE in selected minute, **not verified zero liquidations**. In liquidation minutes t0 = timestamp of FIRST observed BTCUSDT liquidation matching the minute and side; control t0 = 30th second of minute. All timestamp comparisons by local_timestamp (microseconds UTC). These event minutes selected retrospectively on realized volume and are NOT out-of-sample cases.

## Window, metrics and QA
- Historical `trades`, `liquidations`, `quotes`, and `book_snapshot_5` grouped per event in [-120,+300] seconds relative to t0; never assign quote/book from AFTER measurement time to past.
- Sample BBO spread, top-5 bid/ask depth and imbalance at t0-30s, t0-1s, t0, t0+5, t0+30, t0+60, t0+300 from most recent book entry timestamp **<= sampling time, age <= 2 seconds**; if missing => NULL.
- Compare support-side depth change t0-1 -> t0+30 (BUY liquidation: ask side, SELL: bid side) and t0-1 -> t0+60. This is a **snapshot depth proxy**, not proven maker replenishment, cancellation or executed amount.
- Count 30s prior/after and 300s after trades and observed liquidation rows and aggregate aggressive trade amount in source units by side. 5m price outcome is a quote mid difference t0 vs t0+300, only if both quote samples have age<=2sec. The +20bps extension same-direction threshold is descriptive from v0.8.3, not a trained classifier.
- Use CSV raw column order for within-timestamp tie-break, preserve `compressed_sha256`, byte count, row count, and QA per feed. No raw vendor files in GitHub. Quote and book feeds can disagree transiently due to source differences; flag >2bp discrepancy.
- Predeclare sensitivity (only descriptive): 1s stale cap (from 2s baseline), +15/+60 seconds, plus each side's depth change relative to -30s. Report missingness and no confirmed physical cluster touch/cascade.
- No PIT CoinGlass Model2, no signed dealer inventory, no causal attribution. No predictive lift/Brier/probabilities. No trade changes. Other prior 09L files immutable. Detailed incremental L2 add/remove or cancel-vs-fill deconvolution requires separate future verified reconstruction; top-5 is a snapshot, not raw L2.

**Success:** real synchronized short-window casebook. **Failure:** explicit data QA and inaccessible-source statuses, no invented measurements.
