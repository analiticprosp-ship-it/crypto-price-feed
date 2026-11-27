# P3 L2 sample probe receipt audit — 2026-11-06

Source: user-provided GitHub Actions artifact `p3-l2-probe-receipts.zip`, containing only `probe_manifest.json`; generated_at_utc=2026-11-06T12:09:10.218365+00:00. Receipt audited without access to downloaded raw Parquet objects. The JSON contains 30 requested venue/date/symbol slots, hour=12 UTC, on 2026-10-28, 2026-10-30 and 2026-11-04.

| Venue | HTTP 200 / 6 | HTTP 404 / 6 | Manifest reported bytes | Status |
| --- | ---: | ---: | ---: | --- |
| binance_spot | 6 | 0 | 35407205 | DOWNLOADED_UNVALIDATED_L2 |
| okx_spot | 6 | 0 | 29027941 | DOWNLOADED_UNVALIDATED_L2 |
| bybit_spot | 6 | 0 | 41468481 | DOWNLOADED_UNVALIDATED_L2 |
| bitget_spot | 6 | 0 | 23024070 | DOWNLOADED_UNVALIDATED_L2 |
| kraken_spot | 0 | 6 | 0 | HTTP_404_PATH_OR_AVAILABILITY_UNRESOLVED |
| TOTAL | 24 | 6 | 128927697 | NO_L2_REPLAY_YET |

Each HTTP 200 receipt records a reported SHA256, response size and local temporary path. The artifact ZIP does not contain the corresponding binary files; hashes have NOT been independently recomputed, file signatures/Parquet schema have NOT been checked, and the data have NOT been reconstructed. A 404 is not evidence of no historical Kraken data: validate the vendor's Kraken symbol and venue naming through documented catalog before retrying. Never substitute zeros.

## Next actions
1. Correct probe workflow: keep raw sample Parquet objects as an artifact with sufficient quota/retention, or preserve deterministic content-addressed storage with download receipts. Ensure artifacts are scoped to read-only research, no secrets or signed URLs leaked. 24 sample files reported total ~129 MB compressed.
2. Verify actual downloaded bytes against manifest SHA256, inspect Parquet schema and event types, identify snapshot/update sequence IDs, timestamps and order book reach.
3. Reconstruct one hour per venue/symbol/date; verify sequence continuity and compute bid/ask depth +/-0.1% and +/-1% only if the book reaches those price levels. Quarantine failures.
4. Resolve Kraken symbol mapping, add independent Coinbase provider; then probe Gate/MEXC/Crypto.com and separate perpetual markets.
5. Backfill full hour-by-hour coverage matrix only after sample validation. All H1/H2/H3 remain NOT_TESTABLE_WITH_CURRENT_PANEL until a synchronized panel exists.

No changes to P1 acceptance, production, trading, NAV/P&L, reserve, limits or schedules.
