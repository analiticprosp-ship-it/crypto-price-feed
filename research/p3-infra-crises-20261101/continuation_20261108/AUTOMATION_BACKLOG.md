# P3 cross-venue L2: accelerated execution backlog (2026-11-08)

Owner P3. Existing PR #159; no main, NAV, trading or P1 acceptance changes. Read-only research.

## Confirmed receipts
- Sample probe run 42455425848: successful; original raw artifact 13606999593 (~129 MB, expiry 2026-11-22), receipt artifact 13606954961 (expiry 2026-12-08).
- Schema audit run 42460193205: successful, artifact 13609790007 (expiry 2027-01-07). This validates hash+Parquet metadata for downloaded files, not L2 sequence or book reach. Do not claim 24 complete hourly order books.
- Original probe: 24 HTTP 200 from Binance/OKX/Bybit/Bitget and 6 Kraken 404. Kraken symbol mapping unresolved.

## Prioritized task board
P0 (immediate, parallel):
1. Preserve raw artifact beyond Nov 22 in durable immutable SHA256-addressed storage or reproducible vendor download manifest; no secrets, access URLs or tokens committed.
2. Inspect actual schema receipt and raw Parquet event columns; implement venue-specific event decoding; reject unknown schema. Verify UTC event/receive times, snapshot start, ordered updates, resync, duplicate and gap policy. Calculate best bid/ask and reach ±0.1/±1% only after deterministic replay.
3. Resolve Kraken using vendor's documented symbol/market catalog and one-day availability query; never assume HTTP 404 means absence.
4. Identify vendor-supported Gate/MEXC/Crypto.com pairs; obtain exact file listings before adding requests. Coinbase use a separate source and isolate USD vs USDT quotes.
5. Record source coverage: venue × market × pair × UTC hour × source, statuses VERIFIED, NOT_YET_MATURE, AUTH_REQUIRED, HTTP_404, SOURCE_GAP, SEQUENCE_GAP, SCHEMA_MISMATCH, NOT_DEEP_ENOUGH; no zero-fill/interpolation.
P1 (after schema/event replay pass):
6. Expand from three sample hours to every hour 2026-10-26 through 2026-11-07 UTC (future endpoints only when mature). First batch one day per venue; then controlled parallel backfill, rate-limit and cost-aware.
7. Search alternative primary archives for gaps: official OKX historical-data, Tardis downloadable L2, other archival providers with historical provenance. Validate identical venue/symbol/time and independent source timestamps; never substitute spot for futures or another venue as the same observation.
8. Independent cross-source consistency, signed/hashed provenance, sequence and checksum checks, quote FX timestamp, depth bid/ask separately, spread, fixed-notional slippage.
P2 (only after complete panel):
9. Lock pre-incident baselines, compare Binance with contemporaneous controls by venue-relative change. Stratify pre-hack, hack-to-election, election onward, with official first-publication event anchors.
10. H1/H2/H3 assessment, six consecutive verified hourly normality samples, seven closed-day price recovery, risk controls and sensitivity; publish read-only P1 shadow handoff, no production promotion.

## Automation rules
- Dedicated workflow_dispatch/push research workflows; no cron by default, avoid duplicating existing independent P1 weekly runner.
- Fail-closed integrity and replay gates; artifacts for receipts, coverage matrix, error diagnostics and raw archives with explicit retention.
- Retries only for transient HTTP/network errors with bounded backoff; never retry invalid credentials blindly.
- A missing hour queues an alternative source discovery task, not an imputed price or depth.
- Never claim complete panel until each required slot is verified. Preserve immutable as-of provenance; no PIT rewriting.
