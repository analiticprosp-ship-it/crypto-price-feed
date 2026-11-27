# Kraken L2 availability confirmed — 2026-11-08
Source: GitHub Actions run 42462128799, artifact 13609538364 (manifest), raw artifact 13609493423.
Observed 2026-10-30 12 UTC:
- kraken_spot BTC_USD: HTTP 200, 8,296,579 bytes, SHA256 46c8e5ecc570c85d006d8b5a4ff1995cbb4269e66881731c821d667c2e611e8d.
- kraken_spot ETH_USD: HTTP 200, 7,910,691 bytes, SHA256 18e0d6478eeb7b4cb97cdb08d4b5e1f91b71f35f2d65cf469d773a218fce98bc.
- kraken_spot XBTUSD and ETHUSD: HTTP 404.
- binance_spot BTCUSDT control: HTTP 200, 5,513,987 bytes, SHA256 62ff3cc619ef58500257ca9fc675ae0456dada332e6fcf41c4cbd2e9db9093a3.

Confirmed: documented Kraken symbol names resolve and historical binary downloads exist for the checked hour. NOT confirmed: Parquet schema integrity, full hourly book continuity, replay and ±1% depth, other days/hours.
Do not extrapolate one-hour availability to full panel. Original Kraken HTTP 404 was a path/symbol error, not evidence of market absence.
