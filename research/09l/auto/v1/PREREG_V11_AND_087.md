# 09L-AUTO v1.1 + v0.8.7 — locked design (2026-10-22, prior to fresh processing)
**Research/shadow only. No trading, no NAV/Futures/limits, no automatic strategy approval.**

## A. New automated, as-collected sparse venue snapshots
- Run hourly UTC (best effort; GitHub Actions cron delays possible) using only **public, unauthenticated GET**: Bybit V5 BTCUSDT spot and linear `/v5/market/orderbook` with top 25 per side; OKX BTC-USDT spot and BTC-USDT-SWAP `/api/v5/market/books` with 25 levels.
- Store only derived top-5+top-25 summaries, source timestamp, capture begin/end UTC milliseconds, instrument and venue, spread, visible quantities and checksum hash of raw HTTP JSON bytes (do not put raw response or any key into public GitHub).
- Read-only remote API GET; no account access, no order endpoints, no exchange private credentials. No cross-venue raw quantity aggregation (contract multiplier differences); top5 in book native units.
- Source age gate <=120 seconds and valid crossed-market/positive-quantity checks; failures reported as `SOURCE_UNAVAILABLE`, `STALE`, `INVALID` per venue. Each run's JSON append-only in `research/09l/auto/v1/derived/live_snapshots/YYYY/MM/DD/`, never replace data or backdate capture. Separate run manifests and source provenance. No claim this is continuous Level 2, 24/7 WS, historical PIT of CoinGlass, or liquidation clusters. Hourly snapshots cannot identify messages between snapshots.
- Exclude future snapshots as backfill: first record time is actual fetch time; gaps explicitly counted later.

## B. 09L v0.8.7 *label readiness*, before model-fitting
- Use predeclared historical first-day samples: Bybit BTCUSDT 2026-09-01 UTC and OKX BTC-USDT-SWAP 2026-10-01 UTC (no changes to v0.8.6). Same eight clock-fixed anchors 07:24:30, 08:32:30, 13:49:30, 14:19:30, 15:10:30, 15:49:30, 17:28:30, 18:38:30 UTC, stored on earlier frozen design.
- Read `trades` only for this **label-registration stage**: at time t0 use last observed trade with local_timestamp <=t0, <=2 sec old. Forward outcomes use last observed price captured <=t0+30s, +60s, +300s, <=2 sec old. No future price is permitted in features. Directional return in bps `10000*(P_h/P0-1)` and absolute-return threshold 20bp are *descriptions, not verified cascade labels*.
- As-of features solely the window [t0-30s,t0): trades count, aggressor buy/sell amount, count-imbalance, raw quantity imbalance, prior 30-second last-price return and raw volatility proxy. Zero denominator => null; never zero-fill. No future-window L2 deltas from v0.8.6 in pre-event model features — **material leakage blocker**.
- Eligibility: capture-time monotonic, source hash checked against immutable v0.8.6, time staleness max2s, return horizon valid, QA each point. Exclude window with L2 reset in t0-30 to t0+300 if L2 features are ever used; labels based on trades alone remain descriptive, but flag known OKX 18:38:30 reset in notes.
- No regression, cross-validation, Brier score or forecast claim at 16 anchors (two dates, two venues), do **not** call 16 independent trials. Later true OOS requires future timestamps, more dates, source continuity and predeclared model/controls.

## Gate and writeback
Data integrity status separate from scientific validity. `LABELS_REGISTERED_EXPLORATORY` never equals a trade signal or verified `P(cascade)`. 00/01/01A/02/03/04/05/06/06C Spot/Futures/NAV/P&L/reserve untouched. Safe GitHub scheduling code in main is only minimal workflow; all research source/outputs stored on isolated branch. No CoinGlass model2 PIT absent paid API and **private encrypted storage**. No trading runtime dependencies or secrets.
