# Detector stage 2 — public microflow pilot (read-only)

**Status:** optional collector code, NOT a deployed 24/7 service. No changes to existing market-summary.json, prices.json or Spot/Futures trading rules. Stage 1 continues independently.

## Inputs and venues

- Bybit V5 public **linear** `wss://stream.bybit.com/v5/public/linear`: `publicTrade.SOLUSDT`, `allLiquidation.SOLUSDT` (and other selected symbols).
- Bybit V5 public **spot** `wss://stream.bybit.com/v5/public/spot`: `publicTrade.SOLUSDT`.
- Both channels are public: **no API keys or private/account/trade topics**. Request symbols are validated and the pilot is limited to four USDT pairs.

## Launch on a persistent host, NOT GitHub Actions

Use Python 3.11+, a host with durable disk and outgoing WebSocket connectivity, and:

```bash
python -m pip install -r requirements-detector-stream.txt
python scripts/detector_stream_pilot.py --symbols SOLUSDT,SUIUSDT --db /var/lib/detector/pilot.sqlite --out /var/lib/detector/detector-microflow.json
```

The output is **local**; publishing requires a separately authorized delivery step. Do not commit personal configuration, SQLite database, large raw-event logs or credentials. A disconnected collector may restart automatically; continuity gates invalidate partial windows. Run under systemd or comparable service supervisor, with durable mounted storage. Assess CPU/disk, Bybit region accessibility and websocket rate limits in a small pilot before extending to more instruments.

## Output interpretation

- `streams.spot.SOLUSDT.taker_trade.1m/5m/15m`: public Spot taker buy/sell quantity and estimated USD notional, window delta of **aggressive executed trades**.
- `streams.linear.SOLUSDT.taker_trade.*`: separately observed perpetual taker flow, never automatically combined with Spot.
- `streams.linear.SOLUSDT.liquidation.*`: observed venue liquidations. In Bybit V5 `allLiquidation`, `S=Buy` indicates a **liquidated long position** and `S=Sell` a **liquidated short position**. Price `p` is **bankruptcy price**, so volume×price is only a venue-specific notional estimate, not actual execution proceeds.
- Only **fully closed UTC minutes** are evaluated. A 1/5/15m window needs at least 99% recorded connection coverage; otherwise `data:null`, `NO_DATA_GAPPED_OR_WARMUP`. An authenticated subscription with no observed trade events does not prove zero market trades: `NO_TRADE_EVENTS_UNVERIFIED` and `data:null`. Connected liquidation topics with no events may report zero observed liquidations, strictly on that venue; whole windows are not retroactively restored after disconnections.
- Trade ids are deduplicated; liquidation streams lack stable event ids, so deduplication uses a composite fingerprint and may conflate genuinely identical events. Treat published liquidation totals as preliminary and document this limitation.
- `generatedAt` is **collector runtime**, not exchange source time or valid system price. `notSystemPrice=true`, `notTradeApproval=true`.
- The process keeps 90 minutes of observed events in SQLite and writes an atomic read-only JSON snapshot every 20 seconds; a host disconnect or restart can create explicit missing-data intervals.

## Acceptance gates before publishing to the Detector

1. Unit tests pass; no known parsing failures or double counts in replay data.
2. Collect for a sustained trial (suggested 24h), compare spot/perp channels to independent available venue aggregates where feasible.
3. Verify stream availability, connection-gap semantics, 5m and 15m rollups, timestamp delay, event ids and liquidation direction. Sampling rate and region-specific availability must be measured.
4. Define authenticated, least-privilege, atomic publication to a **new** data artifact `detector-microflow.json`, with hard TTL; no overwriting `prices.json` or market-structure/summary until integration is separately reviewed.
5. Detector uses feed as **one independent family** (not multiple votes for buy/sell/CVD from the same trades), and may show research confidence, never permission to place trades.

## Official data specifications

- https://bybit-exchange.github.io/docs/v5/ws/connect
- https://bybit-exchange.github.io/docs/v5/websocket/public/trade
- https://bybit-exchange.github.io/docs/v5/websocket/public/all-liquidation
