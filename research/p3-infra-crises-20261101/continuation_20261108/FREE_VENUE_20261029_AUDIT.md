# Free historical L2 coverage audit — 2026-11-08

## Executed evidence
GitHub Actions run: https://github.com/analiticprosp-ship-it/crypto-price-feed/actions/runs/42465641273
Artifact: p3-free-venue-manifest (ID 13611805528), no raw artifact.
Date/hour checked: 2026-10-29 12:00 UTC.
18 attempted CryptoHFTData file paths:
- Coinbase: 4 path/symbol variants, all HTTP 404.
- Gate.io: 6 variants, all HTTP 404.
- MEXC: 4 variants, all HTTP 404.
- Crypto.com: 4 variants, all HTTP 404.

Interpretation: NO files downloaded; 404 proves only that the exact guessed paths are unavailable, not that venue history is absent from the provider. Provider venue catalog and authoritative symbol IDs have NOT been verified.

## Free archive acceptance criteria
A source is acceptable only if it provides **2026-10-29 historical order book snapshots and ordered depth deltas** for spot BTC and ETH with timestamps, sufficient to replay both sides and detect gaps. OHLCV, trade, liquidation, funding and current REST/WebSocket book snapshots do NOT qualify. A WebSocket collector started now cannot retroactively reconstruct October.

## Remaining work
1. Query authoritative provider catalog/documentation for venue identifiers and symbol path conventions; do not blindly multiply guessed URLs.
2. Check each venue's official published historical bulk data and licenses, recording exact source URL and 2026-10-29 coverage.
3. For any verified available archive: download raw, hash, verify schema and snapshot/delta semantics; replay with native sequence/gap checks and compute spreads/depth.
4. Keep missing venues explicitly marked HISTORICAL_L2_NOT_VERIFIED. Existing Kraken/Binance/OKX/Bybit/Bitget raw downloads remain REPLAY_NOT_VALIDATED until order-book reconstruction is independently checked.
5. Never modify production or trading controls.

Status: FOUR_VENUES_UNRESOLVED; no fabricated L2 or accepted replay.
