# 09L v0.8.7 — six-monthly-cohort expansion and existing R2 integration (2026-10-22)

**STATUS: REPRODUCIBLE HISTORICAL LABELS PREPARED; NOT A CONFIRMED PREDICTIVE STUDY.** SHADOW / RESEARCH ONLY.

## Verified existing Cloudflare R2
GitHub `main` already contains `research/DETECTOR_R2_SETUP.md`, `.github/workflows/archive-shadow-r2.yml` and corresponding SDK readback. Existing private R2 bucket: `crypto-detector-history`. No new bucket, account, keys or continuously running server. Existing repo secrets: `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET`. Prefix for isolated 09L: `research/09l/v087/`.

## Locked historical sample expansion
Prereg `research/09l/v0.8.7-2026-10-22/PREREG_6_EXTRA_MONTHS_R2_LOCKED.md` was committed before downloading new data. Predefined cases for June, July and August 2026 (1st day) on Bybit BTCUSDT and OKX BTC-USDT-SWAP, 8 UTC clock anchors per day. Source Tardis gzip downloaded and SHA256 recorded; only 30s pre-anchor features, t0 as-of price and forward +30s/+60s/+300s as-of labels with <=2s age. No adaptive selection or negative-case substitution.

| Month 2026 | Bybit BTCUSDT fully usable / 8 | OKX BTC-USDT-SWAP fully usable / 8 |
|---|---:|---:|
| June 1 | 8 | 8 |
| July 1 | 7 | 8 |
| August 1 | 3 | 6 |
| **Six new combinations** | **18 / 24** | **22 / 24** |

40 / 48 new complete all-horizon labels. With Bybit September 6/8 and October 8/8 and OKX October 8/8, total **62 / 72** fully ready observations in **nine** source-day/venue cohorts (Bybit June through October and OKX June, July, August and October). Ten records fail strict as-of capture freshness or horizon readiness. Missing never becomes a synthetic price or zero return.

## REAL existing R2 writeback, independently confirmed
GitHub first-run: https://github.com/analiticprosp-ship-it/crypto-price-feed/actions/runs/39771359020
Six historical source-day JSON compact derived objects archived with `R2_SHA256_READBACK_PASS` **6 / 6**. Content-addressed under `research/09l/v087/labels/{venue}/{YYYY-MM-DD}/{SHA256}.json`. Receipt in `research/09l/auto/v1/derived/r2_receipts/20261022T113418894480Z.json`, manifest SHA256 `edf1489b59b3282579528832cd6cacc4102b7faebbac46e365c6bae253200c9c`. No raw licensed vendor trade files copied into GitHub or R2.

Daily scheduled auto-archive main-branch workflow `.github/workflows/09l-auto-v1-daily.yml` now checks out `research/09l-v087-r2-expansion-20261022`, gathers monthly available archives/labels and calls `r2_archive_v087.py --all-available`. Verified run: https://github.com/analiticprosp-ship-it/crypto-price-feed/actions/runs/39771816250
**9 / 9** complete/partial label JSON objects verified by SHA-256 readback in existing R2 (includes prior cohorts; `ARCHIVE_COMPLETE` is *storage integrity*, not `LABEL_READY` or research conclusion). Total complete all-horizon labels: 62 / 72. Future first-of-month archives use append-only failures and are not substituted when unavailable; daily GitHub cron is best effort.

## CoinGlass access: separate decision
Official Model2 aggregated BTC heatmap endpoint: https://docs.coinglass.com/reference/liquidation-aggregate-heatmap-model2 . Access only **Professional / Enterprise** per official docs. Repo `CG_API_KEY` secret presence was checked **without API request** by https://github.com/analiticprosp-ship-it/crypto-price-feed/actions/runs/39772010306 : **NOT CONFIGURED**, so `PIT_SNAPSHOT_MISSING`. No subscription purchase and no CoinGlass API requests. Prepared `research/09l/auto/v1/coinglass_existing_r2_pit.py` uses existing R2 secrets and stores genuine licensed raw PIT privately only if future entitlement and secure key are configured; not activated or scheduled.

## Scientific limits and next stage
These are sparse, pre-chosen first-day samples. Bybit & OKX on same day face common price path, eight within-day times are correlated, and early-month backfills are retrospective relative to prereg; **no prospective chronological OOS forecast established**. No cluster birth/death/first touch or signed net dealer gamma identified, no proven cascade forecast / absorption mechanism / calibrated probability, no traded edge.
Next: add source-independent true PIT CoinGlass if licensed (not guessed), accrue genuinely prospective days and compare predeclared baseline vs incrementally augmented model at fixed horizons and whole-day/whole-month clustered uncertainty. Cloud R2 solves storage, not missing-source acquisition.

### Strict writeback
All derived source code and JSON live in 09L research branch; only scheduler workflow file was updated in `main`. Existing trading 00/01/01A/02/03/04/05/06/06C, Spot, Futures, NAV, P&L, reserves, capital, limits, orders untouched. No raw external source blobs made public.
