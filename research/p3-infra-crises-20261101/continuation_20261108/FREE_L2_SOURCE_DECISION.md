# P3 free historical L2 replacement — operational decision (2026-11-08)
Scope: research-only PR #159; no production, P1 acceptance, trading, NAV, P&L or reserve modifications.

1. CryptoHFTData is the primary already-working source for Kraken, Binance, OKX, Bybit and Bitget. Check four missing venues on 2026-10-29T12:00Z via workflow p3-free-venues-20261108.yml, run 42465641273. Only SHA-receipted actual files count as historical L2 availability.
2. If a candidate returns HTTP 404, classify PATH_OR_COVERAGE_UNRESOLVED rather than ABSENT: exchange ID/symbol variants may be incorrect.
3. Official public archives are secondary candidates. An OHLCV/trade/ticker archive or current REST/WebSocket book does NOT substitute for historical L2 snapshot + delta. Validate license, historical date, snapshot, delta sequence and checksum before acceptance.
4. Existing Kraken 2026-10-28 through 2026-10-30 hourly downloads are raw, not replay-validated. Historical L2 reconstruction requires provider-specific event_type/sequence semantics, initial snapshot, gap handling, best bid/ask cross checks and ±1% depth.
5. Forward collection via exchange WebSocket is useful but cannot recover missing historical events. Never label future capture as 2026-10-29 historical.
6. No Tardis paid key is assumed. Historical gaps must remain explicit.
