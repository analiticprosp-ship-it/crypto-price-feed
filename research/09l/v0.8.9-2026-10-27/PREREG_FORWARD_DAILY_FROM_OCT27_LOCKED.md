# 09L forward daily price/flow audit v0.9.0 — FROZEN before future 2026-10-27 market day closes
Date authored 2026-10-27. SHADOW / RESEARCH ONLY. Starting prospective **calendar date** `2026-10-27` (UTC), with exactly 8 fixed UTC clock anchors inherited from 09L v087 for all future dates; use source publication next day.

## Daily scope
Official `data.binance.vision/data/futures/um/daily/aggTrades/BTCUSDT` ZIP + publisher SHA256 .CHECKSUM. Starting UTC trade date 2026-10-27 inclusive, all subsequent dates only **after completed UTC close**, no outcome selected days / regimes. Scheduled GitHub Actions best-effort at 11:11 UTC next day, retries last seven calendar days to handle delayed publisher exports; if absent, attempt ledger includes unavailable status. No paid subscription, private server, trade credentials or new storage.

## Frozen features and evaluation
`binance_daily_aggtrade_price_probe.py` unchanged:
- Only pre-event `[t0-30s,t0)` momentum and agg buy-minus-sell native-quantity imbalance. Exact fixed clocks 07:24:30,08:32:30,13:49:30,14:19:30,15:10:30,15:49:30,17:28:30,18:38:30 UTC.
- As-of source trade <=t0 and <=2s old; close forward target signed returns at +30, +60 and primary +300 seconds, <=2s old, no stale fill. Do not use future return in features. Need original publisher SHA256, ZIP CRC, mono trade timestamps/IDs, fixed schema 7 columns, data day; invalid=missing.
- Locked no-fit sign models: `always_up`, `always_down`, `past_30s_momentum_sign`, `past_30s_aggflow_sign`. All signs using past-only quantities, zero-return and missing excluded. Report each UTC calendar date separately and aggregate descriptively with explicit count of dates. Source `aggTrades` counts NOT comparable to Tardis raw individual trades; BTCUSDT Binance USD-M not interchangeable with Bybit/OKX native book.
- Each new day is *ex-ante date/predictor selection*, but daily Binance ZIP is an archival reconstruction made **after** the event. Historic backfilled data does not prove real-time first reception/publication latency or executable signal. No claim prospective live trading or actionable timing.

## Science gate
This is **PRICE_ONLY** and can at most contribute to an independent-date BTC direction feature diagnostic. No observed liquidation prints in Binance daily aggTrades, no Model2 heatmaps, no true cluster positions/first hits, no forced-exit cascade nor maker absorption labels. Never derive `P(cascade)` or `P(first cluster hit)` from this source. Those remain blocked `PIT_SNAPSHOT_MISSING` until licensed as-collected CoinGlass numerical source is stored privately and validated. No training/hyperparameter adjustments to earlier negative v087 results based on rolling days.

## Archival
Reuse existing Cloudflare R2 private bucket `crypto-detector-history`, existing GitHub R2 secret names; prefix `research/09l/v089/daily-binance`. Per immutable source-day digest: only compact derived row JSON and source SHA, never original Binance ZIP publicly or in R2. SHA256 readback required; report missing source separately (not assumed zero), repeat latest 7 days idempotently. Separate GitHub workflow file allowed in main ONLY as scheduler; analysis code and writeback confined to `research/09l-v089-historical-robustness-20261027`. No trades, Spot/Earn/Tangem, Futures, NAV, reserve/capital/P&L, permissions, trading limits or canonical changes.
