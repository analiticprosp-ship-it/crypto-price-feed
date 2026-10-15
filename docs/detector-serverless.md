# Independent Detector serverless REST feed (NO VPS)

## Decision

Use **GitHub Actions only** for current Detector research. The continuously running WebSocket collector, Dockerfile and external host setup are **deferred**. Keep the existing code for later; do not provision a server or publish a fake live CVD. No API keys are required.

## New published artifact

\`detector-rest-flow.json\` — independently published by \`.github/workflows/update-detector-rest-flow.yml\` every 15 minutes on a best-effort GitHub scheduler, plus manual \`workflow_dispatch\`. **GitHub schedules can lag or skip runs**: consumer must check timestamps and never treat a successful historical run as live.

The system price contract \`prices.json\` is unchanged; this file is strictly **research**, never suitable for NAV, fill prices, actual trade execution or margin/account conclusions.

### Data

- \`instruments.<symbol>.taker\`: Binance USD-M *historical completed* 5-minute public REST taker-buy and taker-sell **base-asset volume** (source: \`/futures/data/takerlongshortRatio\`). Compute latest 5m, trailing contiguous 15m and previous contiguous 15m, delta and normalized imbalance. This is a completed-bar **venue aggregate**, not tick-by-tick CVD and **not Spot demand**.
- \`instruments.<symbol>.openInterest\`: Bybit V5 **linear** public REST \`/v5/market/open-interest\` at 5min interval, current observed source timestamp and conditional 15m change in **same contract/source** (base unit per USDT linear contracts). Not merged with Binance OI or used as directional positions.
- Universe derived from \`universe.json\` perpetual_core + first futures_extended, capped at **15 assets per run**, no portfolio holdings/equity/lot/valuation loaded.
- \`NO_DATA\`, error category, and missing window \`null\` are intentional. An entirely failed run cannot overwrite the previous successful snapshot.
- \`generatedAt\` is a research-generation timestamp, not evidence of current exchange trades or system price. Signals must check the source observation timestamps and their own maximum age; source data can become stale even when the file is new.
- Taker data 5m and 15m are the **same evidence family**. Do not double count. It must not be interpreted as verified absorption or as a profitable independent forecast.
- WebSocket-only liquidation feeds, continuous order book, streaming trade execution, true tick-level CVD and spot aggressive trade flow remain unavailable until a host or equivalent external service exists.

## Data consumer preflight

1. Confirm successful action and published JSON schema \`detector-rest-flow-1.0\`, symbol identity, market type, \`researchOnly=true\`, \`notTradeApproval=true\`, \`notSystemPrice=true\`.
2. Check freshness independently for \`generatedAt\`, \`lastClosed5mEndMs\`, Bybit OI \`asOfMs\`; use most recent completed bar, never an unfinished bar.
3. Confirm \`window15m != null\` only if exactly 3 consecutive completed 5m taker volume periods; no gap filling by interpolation.
4. Keep Binance taker base-volume separate from Bybit OI base-unit reports; no cross-venue sums or fabricated liquidation series.
5. Do not treat 15m REST observations as a trade authorization. Stage1 \`market-summary.json\` still provides historical 15m/1H/4H price structure, and \`Спекуляция\` alone controls futures trading.

## Endpoints

- https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Taker-BuySell-Volume
- https://bybit-exchange.github.io/docs/v5/market/open-interest

## Further improvements possible without a server

Test Bybit/OKX public historical Spot OHLCV liquidity metrics with separate venue/definition. Consider direct Spot taker aggregate only when exchange provides a trustworthy **historical** side-separated series. Future continuous streams require explicit infrastructure and cost approval, postponed.
