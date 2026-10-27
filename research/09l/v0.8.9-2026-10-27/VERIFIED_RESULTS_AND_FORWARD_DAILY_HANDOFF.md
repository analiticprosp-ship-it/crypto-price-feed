# 09L v0.8.9 / forward daily v0.9.0 — verified evidence and automation
**Recorded:** 2026-10-27 UTC. **STATUS: SHADOW / RESEARCH ONLY / NO PROVEN CASCADE PREDICTION.**

## 1. Expanded actual BTC trade/liquidation evidence, NO curve-fitting
2025 Jan 1, Apr 1, Jul 1, Oct 1 and 2026 Jan 1 were committed **before** source processing in `PREREG_2025_QTR_2026_JAN_LOCKED.md`; two venues Bybit BTCUSDT and OKX BTC-USDT-SWAP. Fixed 8 UTC clocks/day, pre-30-second trade features, as-of max2s, +30/+60/+300s. Fixed first observed liq after 06/12/18 UTC; no outcome/event sorting. All 10 paired SHA256 trade-source cross-checks PASS:
- New fixed-clock price samples **70 / 80** ready, 10 correctly missing.
- New observed liquidation events **30 / 30**, but strict proxy outcome counts: `CONTINUATION_PROXY=0`; `OPPOSITE_REVERSAL_PROXY=2`; `LIMITED_CONTINUATION_PROXY=19`; `MIXED_OR_UNCLASSIFIED=9`. No real cascade/absorption mechanism proved.
- Fixed first-liq signed past 30s momentum and aggressor flow simple sign tests were applicable to **only 2 decisive observed outcomes**, and all three prior frozen rules (always-continuation, momentum, flow) were **0 / 2**. Too small and one-sided for any predictive inference.
- New 10 cohort-derived price and liquidation behavior JSON each archived into existing Cloudflare R2, `research/09l/v089/`; **20 / 20** private readback SHA256 PASS. Pilot: https://github.com/analiticprosp-ship-it/crypto-price-feed/actions/runs/40492765405 .

## 2. Aggregate ORIGINAL Tardis research status (do not pool dependent observations)
Across existing and new vintages 2025 Jan/Apr/Jul/Oct and 2026 Jan–Oct except OKX Sep:
- **14 unique market calendar dates**, **27 venue×date price cohorts**, **193 / 216** complete price as-of horizons from fixed clocks (23 missing). Stored daily evidence with **27/27 SHA readback** in existing private R2; main-branch daily GitHub workflow first revalidated new branch https://github.com/analiticprosp-ship-it/crypto-price-feed/actions/runs/40494635438 .
- Observed-liq fixed clock/session study across **10 distinct dates**, **20 venue×date event cohorts**, **60 / 60 selected event price-behavior proxies**: strict continuation **8**, opposite reversal **9**, limited continuation **30**, mixed/other **13**.
- The R2 archive for this event cohort source study in `research/09l/v088/` (content-addressed by date and hash) now returned **40 / 40** object checks with readback integrity on daily run. No downstream trade entry approval.
- The original v0.8.7 regression `NO_REPLICATED_INCREMENTAL_GAIN` was **not** re-trained or retroactively rewritten. Five earlier dates are historical backward sensitivity and do not form unseen later prospective OOS.

## 3. Truly distinct non-first-of-month price-data diagnostic
Official Binance data.binance.vision **USD-M BTCUSDT DAILY aggTrades** for **2026-10-19 through 2026-10-26**, 8 full daily archive ZIPs with publisher .CHECKSUM SHA256 and ZIP CRC, strict millisecond timestamp/order/native size QA, 8 fixed clocks/day: **63 / 64** eligible five-minute **price-only** observations. This is a *different data type* from Tardis individual trade capture: aggTrades grouped, original live receipt not measured.
Pre-frozen model-free direction-sign methods (no fit or tuning):
- Always up: **31/63**; always down **32/63**.
- Prior 30s BTC price direction: **36/63 = 57.14%**.
- Prior 30s BUY-minus-SELL aggregated quantity: **37/63 = 58.73%**.
Day-level reports retained; 8 adjacent UTC days are correlated. No price predictor validated out of sample, no liquidation prints/cascade nor CoinGlass heatmap first-hit inferred.
- Source pilot / R2 8/8 readback PASS: https://github.com/analiticprosp-ship-it/crypto-price-feed/actions/runs/40493770155 .
- Official source explanation: https://github.com/binance/binance-public-data .

## 4. NEW truly forward-calendar source collection WITHOUT a running server
`PREREG_FORWARD_DAILY_FROM_OCT27_LOCKED.md` committed **before the UTC 2026-10-27 market day finished**, locking date start **2026-10-27 UTC**, same 8 clocks, same <=2s as-of rule, same no-fit signs and +300s price-direction target. `main` scheduled workflow `.github/workflows/09l-v090-forward-binance-daily-shadow.yml` runs daily 11:11 UTC (best effort), using only public publisher ZIP + SHA and existing Cloudflare R2. It retries the last 7 completed dates (up to but never including current UTC date), saves missing as missing, and checks readback. Actual analysis & writeback only in isolated research branch `research/09l-v089-historical-robustness-20261027`, no trade keys or live orders.
- First scheduled-workflow push test SUCCESS: https://github.com/analiticprosp-ship-it/crypto-price-feed/actions/runs/40494496826 .
- That run was on 2026-10-27 **before its UTC market-day close**, so correctly emitted `NO_CLOSED_FORWARD_DAILY_DATES_YET` / `NO_FORWARD_SOURCE_YET`, no invented outcome. It reverified the prior 8/8 derived daily objects, status `ARCHIVE_COMPLETE_FOR_PRESENT_SOURCES`.
- Future daily provider data will be archived *after* trade completion, so the methodology is precommitted by date but receipt-time executable trading timeliness is NOT established. Consecutive days dependent; no liquidation observations in source. No implied 24/7 own-server process.

## 5. CoinGlass genuine cluster first-hit remains blocked
Separate read-only Secret-presence preflight (no API requests or payments), https://github.com/analiticprosp-ship-it/crypto-price-feed/actions/runs/40494759162 , confirmed `COINGLASS_MODEL2_KEY_NOT_CONFIGURED` as of 2026-10-27. Official Model2 requires Pro/Enterprise entitlement: https://docs.coinglass.com/reference/liquidation-aggregate-heatmap-model2 . Existing R2 is ready to store valid licensed *future* PIT heatmaps, but it does NOT reconstruct nonexistent historical clusters. Thus:
- `CLUSTER_FIRST_HIT_NOT_RUN`
- `PIT_SNAPSHOT_MISSING`
- `ACTUAL_CASCADE_VS_MAKER_ABSORPTION_UNIDENTIFIED`
No exact `P(first-touch)`, `P(cascade | touch)` or trade signal can be reported. The separate prereg `CLUSTER_MODEL2_PROSPECTIVE_FIRST_HIT_PREREG.md` remains unexecuted.

## 6. Writeback/isolation proof
New research branch has **ONLY** `research/09l/` and `.github/workflows/09l-*` path changes compared with v088 (GitHub compare). In `main`, changes related to this phase strictly scheduled workflows `.github/workflows/09l-auto-v1-daily.yml`, `.github/workflows/09l-auto-v11-hourly-books.yml`, and new `.github/workflows/09l-v090-forward-binance-daily-shadow.yml`. Main schedules research ref only, never writes production assets. `Spot/Earn/Tangem, 00/01/01A/02/03/04/05/06/06C, Futures, NAV, P&L, reserves/capital, limits and orders` untouched. Android PASS not claimed and is irrelevant to 09L.
