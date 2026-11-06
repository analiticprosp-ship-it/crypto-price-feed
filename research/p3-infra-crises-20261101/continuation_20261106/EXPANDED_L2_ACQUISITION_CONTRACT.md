# P3 expanded cross-venue L2 acquisition contract — 2026-11-06

Status: RESEARCH_DESIGN_ONLY / SOURCE_DISCOVERY_NOT_DATA_VALIDATION. Owner P3; P1 recipient SHADOW_RESEARCH_CANDIDATE_NOT_ACCEPTED. No production changes.

## Scope
UTC 2026-10-26 00:00 through 2026-11-07 00:00 (end exclusive, future slots not mature). Preserve separate event clocks: Binance 2026-10-29; US election first scheduled poll closure 2026-11-03 23:00 UTC; each result anchor only upon first-publication proof. Controls: Binance (treated), OKX, Bybit, Bitget, Coinbase, Kraken; extended Gate, MEXC, Crypto.com where coverage passes. Hyperliquid isolated perpetual comparison. Spot and perpetual panels separate; BTC-USD vs BTC-USDT distinct quote panels.

## Source discovery (web catalog, not verified daily files)
- OKX official historical L2 since March 2023: https://www.okx.com/historical-data
- CryptoHFTData historical L2 since June 2025 (Bitget July 2025), Binance/OKX/Bybit/Bitget/Kraken spot and futures: https://www.cryptohftdata.com/datasets/crypto-orderbook-data
- Tardis tick L2 snapshots and deltas, first-day-of-month free samples: https://docs.tardis.dev/downloadable-csv-files
- CryptoStruct archive catalog currently advertises coverage only through Sep 2026: https://cryptostruct.com/historical-data/order-book
- ByKaranteli daily snapshots since Sep 2026, but varying REST depth reach; daily data insufficient for hourly normalization: https://bykaranteli.com/data
All require independent venue/symbol/day availability checks, access/licence review, raw-byte hashes and gap audits before acceptance.

## Non-negotiable acceptance
Build coverage matrix for venue x market x symbol x UTC hour x source, statuses VERIFIED / SOURCE_UNAVAILABLE / NOT_YET_MATURE / REPLAY_GAP / ACCESS_DENIED; never impute, zero-fill, forward-fill or interpolate. Target full coverage, not a claim of guaranteed full coverage. Reconstruct from initial snapshot + ordered deltas with sequence/checksum validation, venue and receive timestamps, resync markers, exact original bytes SHA256. Compute depth +/-0.1%, +/-1% (bid/ask separately), quoted spread bps, USD-equivalent notional only with observed timestamped FX conversion, slippage at fixed notional. Insufficient book reach => null not 0. Hourly sampling must have explicit observation timestamp and maximum staleness gate; missing hour remains missing and is escalated for alternative independent source. Cross-source overlap compare at matched times and market conventions; disagreements quarantine.

## Identification
Normalize each venue to its own pre-incident baseline. Report Binance minus contemporaneous median controls as descriptive difference; avoid causal attribution absent parallel trends and no-spillover checks. Evaluate Binance vs controls before breach, breach-to-election, post-election. Predefine normality: spread <=1.25 x pre24h median AND depth >=0.8 x pre24h median, six consecutive verified hourly observations, missing breaks streak. Compare with 7-closed-day price recovery only when mature. Explicit confounders: elections first-publication anchors, FOMC, ETF sessions/publication time, Nasdaq/risk, stablecoin flows, hacks/wallets. No H1/H2/H3 validation until synchronized complete panel and screened controls.

## Next execution gate
1. Probe exact dates/symbols/market data for five core sources, log HTTP/status/object checksum.
2. Acquire and replay one BTC and one ETH hour per venue from 2026-10-28, 2026-10-30 and 2026-11-04; validate reach, sequence, timestamps and cost.
3. If passed, backfill full range and audit every expected hour; use second vendor for missing slots.
4. Only then compute event panels and predeclared comparisons. No changes to main, trading, NAV/P&L, reserve, schedules or weekly runner.
