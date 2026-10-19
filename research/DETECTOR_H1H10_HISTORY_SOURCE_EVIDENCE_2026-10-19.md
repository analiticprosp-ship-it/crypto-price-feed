# Детектор H1–H10: проверенная глубина и качество исторических источников

**Заморозка состояния:** 19 октября 2026 года, после PR #101.  
**Статус:** `RESEARCH_ONLY / EDGE_UNVALIDATED / EXCHANGE_FIRST_PUBLICATION_UNVERIFIED`.  
**Запрет:** нельзя изменять Spot, Futures, NAV, P&L, лимиты и торговые решения на основании этого документа. Никаких новых подписок, платных источников или региональных обходов не было.

## 1. Уровни доказательств (НЕ смешивать)

1. **PROVIDER_CATALOG_METADATA:** поставщик заявляет даты и инструменты; это не фактические CSV и не гарантированная непрерывность.
2. **HTTP_ARCHIVE_EXISTENCE:** HTTP200 подтверждает URL лишь в момент проверки; HTTP404 не доказывает, что более ранних записей не существует.
3. **SOURCE_HASH_CRC_CSV:** фактические файлы, publisher SHA256 (если источник поддерживает), gzip/ZIP CRC, строки, числовые поля, UTC-метки и пропуски.
4. **VENDOR_RECEIPT_ASOF:** Tardis `local_timestamp` сообщает время получения сообщения поставщиком; не является точным временем публикации *биржей*.
5. **EXCHANGE_RELEASE_PIT / RETROSPECTIVE_REVISIONS:** не доказано в этих прогонах для исторического Binance `create_time` или OKX / Bybit.
6. **H1–H10_CONFIRMATORY_EDGE:** не установлен; до этого уровня необходимы frozen prereg, отсутствие lookahead, корректный holdout и исполнимость с реальными затратами.

## 2. Binance: глубина исторических источников

### Archive existence / sample proof

| Датасет | BTC | ETH | SOL | Proof |
|---|---|---|---|---|
| Spot hourly OHLCV | 2017-08-17 04:00 UTC | 2017-08-17 04:00 UTC | 2020-08-11 06:00 UTC | earliest sampled publisher SHA/ZIP CRC/CSV |
| USD-M hourly OHLCV | Jan 2020 | Jan 2020 | 2020-09-14 07:00 UTC | earliest sampled publisher SHA/ZIP CRC/CSV |
| Spot monthly aggTrades | Aug 2017 | Aug 2017 | Aug 2020 | HEAD-only, not byte-validated in this stage |
| USD-M monthly aggTrades | Jan 2020 | Jan 2020 | Sep 2020 | HEAD-only |
| USD-M monthly fundingRate | Jan 2020 | Jan 2020 | Sep 2020 | earliest sampled publisher SHA/ZIP CRC/CSV |
| USD-M 5m OI daily metrics | 2020-09-01 | 2021-12-01 | 2021-12-01 | selected original daily source archives, not full chronology |

Source boundary [PR #92](https://github.com/analiticprosp-ship-it/crypto-price-feed/pull/92), [Actions #39272568024](https://github.com/analiticprosp-ship-it/crypto-price-feed/actions/runs/39272568024) SUCCESS, 573 bounded HEAD probes/279 HTTP200/294 HTTP404, 0 unknown. R2 `research/detector-source-depth-boundary/v1/39272568024-1.json`, SHA256 `4938b03031812f2f40bd3f1b24f03d97470c84ba09554ef5d842e926d08cd0fd`.

First archival data [PR #93](https://github.com/analiticprosp-ship-it/crypto-price-feed/pull/93) [Actions #39273270916](https://github.com/analiticprosp-ship-it/crypto-price-feed/actions/runs/39273270916) **FAIL/PARTIAL**: 11/12 publisher CRC/CSV samples PASS; initial BTC 2020-09-01 OI had duplicates (correctly flagged). Follow-up [PR #95](https://github.com/analiticprosp-ship-it/crypto-price-feed/pull/95), [Actions #39274327303](https://github.com/analiticprosp-ship-it/crypto-price-feed/actions/runs/39274327303) SUCCESS: 576 raw rows, 288 labels, exactly two identical complete rows per 5m label, no conflicts.

**2024-01-01..2026-10-16:** already verified 1,017 completely filled 5m-calendar days out of 1,020 per BTC, ETH, SOL; 130 missing 5m labels per asset across three partially filled days; 413 longest full consecutive days. Source event labels are **NOT venue publication proof**. [PR #90](https://github.com/analiticprosp-ship-it/crypto-price-feed/pull/90), [Actions #39224876509](https://github.com/analiticprosp-ship-it/crypto-price-feed/actions/runs/39224876509) PASS.

**Selected pre-2024 5m OI days:** [PR #99](https://github.com/analiticprosp-ship-it/crypto-price-feed/pull/99), [Actions #39289782545](https://github.com/analiticprosp-ship-it/crypto-price-feed/actions/runs/39289782545) SUCCESS: 22/22 chosen days passed original publisher SHA256/ZIP CRC, 288 unique 5m labels, no numeric/CSV duplicate conflicts. This does **NOT** establish every intervening day. BTC Sep/Oct 2020 and Jan 2021 each have 288 duplicate pairs; BTC July 2021 has singles. Immutable R2 `research/detector-binance-early-oi-selected-days/v1/39289782545-1.json`, SHA256 `2cd89888036c66f2321119913268923e8ca5d60fbaaa0d238d9c1a6ed218a8d8`.

**2021 OI duplicate transition:** [PR #100](https://github.com/analiticprosp-ship-it/crypto-price-feed/pull/100) initial [Actions #39290188396](https://github.com/analiticprosp-ship-it/crypto-price-feed/actions/runs/39290188396) **FAIL (regression test caught fail-open)**; fixed [PR #101](https://github.com/analiticprosp-ship-it/crypto-price-feed/pull/101), [Actions #39290424525](https://github.com/analiticprosp-ship-it/crypto-price-feed/actions/runs/39290424525) SUCCESS, 61 daily archives audited May–June 2021. **TRANSITION_PARTIAL_UNCERTIFIED**:
- 2021-05-20: all 288 5m labels doubled, native numeric values/complete rows match.
- 2021-05-21: 284 unique labels / eight duplicates / four missing.
- 2021-05-22: 288 single labels but ten invalid OI numeric values.
- 2021-05-23: 284 single labels, four missing.
- 2021-05-24: 288 complete single labels, zero detected defects.
- Additional partial days May 19, May 28, June 22–24; do not interpolate.

R2 `research/detector-btc-oi-2021-duplicate-transition/v1/39290424525-1.json`, SHA256 `c623f1bb3dd76f97e4a7eca65f6f185d57eca15cc882c30b1c109a108ce301a2`. Exact single instant of semantic regime change **not proven**; source transitions around 21–22 May only. Preserve original source rows. Any eventual derived deduplication must carry explicit provenance/masks.

## 3. Tardis: true free first-of-month receipt archives

Provider catalog [PR #96](https://github.com/analiticprosp-ship-it/crypto-price-feed/pull/96), [Actions #39283941176](https://github.com/analiticprosp-ship-it/crypto-price-feed/actions/runs/39283941176) SUCCESS, R2 `research/detector-multivenue-depth/v1/39283941176-1.json`, SHA256 `c0bc98d6d146d08cb98bdcea96365b5cad810f222bc6b73b8c6af7ffba30b80d`.

Catalog `availableSince` for *instrument*, not independent proof of continuous usable dataset:
- Binance Futures BTCUSDT 2019-11-17, ETHUSDT 2019-11-27, SOLUSDT 2020-09-14;
- OKX Swap BTC-USDT-SWAP and ETH-USDT-SWAP 2019-12-04, SOL-USDT-SWAP 2021-01-22;
- Bybit BTCUSDT catalog 2020-05-28. Other Bybit symbols require full catalog, not truncated preview.

[PR #97](https://github.com/analiticprosp-ship-it/crypto-price-feed/pull/97), first [Actions #39289030348](https://github.com/analiticprosp-ship-it/crypto-price-feed/actions/runs/39289030348) collection SUCCESS but **0/18 dataset parser PASS** (mistook 16-digit microsecond receipts for ISO); corrected by [PR #98](https://github.com/analiticprosp-ship-it/crypto-price-feed/pull/98), [Actions #39289452550](https://github.com/analiticprosp-ship-it/crypto-price-feed/actions/runs/39289452550) **SUCCESS, 18/18 actual free gzip derivative_ticker CSV** for BTC/ETH/SOL × Binance Futures/Bybit/OKX Swap × 2024-01-01 and 2026-09-01. All have validated gzip CRC, two SHA256 fields (raw compressed/decoded), strictly monotonic vendor receipt timestamps, zero out-of-day rows or invalid OI values, and event receipts in 288/288 5m time buckets. **Some isolated tick rows have blank `open_interest`; event coverage is not proof every bucket has valid PIT OI feature.**

R2 `research/detector-free-tardis-okx-history-audit/v1/39289452550-1.json`, SHA256 `fba968c37705b9b955f9b943a015d99e299a548eef30bbbf7a1a933365e14b33`; full Bybit catalog additionally freshly SHA-checked, separate from pinned truncated report. Tardis free access to first-of-month sample dates only; no paid continuous dataset requested.

## 4. OKX / Bybit direct APIs

- OKX latest 5m and 1D OI works (6/6 sample queries, three symbols). Historical **18 explicitly dated 5m January windows from 2021 through 2026 returned HTTP200/code=0 but zero rows**. This means **no historical-depth proof** via this endpoint; it does NOT establish historic nonexistence.
- Bybit 21 historical OI REST requests failed HTTP403 in GitHub runner. That is a region/access constraint, **NOT** evidence historical records do not exist. Vendor Tardis confirms certain instrument-specific archived days through independent receipt evidence. No credential/region bypass.

## 5. Research gating for the next stage

1. Build full actual **daily 5m source calendar for pre-2024 Binance** using bounded requests, publisher hash, month/source transition masks, and append-only reports. A handful of first-of-month samples must never stand for continuous years.
2. Build *separate* Tardis 5m **valid OI feature/as-of** coverage from vendor `local_timestamp`, not from mere receipt event coverage. Preserve provider-specific unit/instrument specifications.
3. Keep source inventory per `venue × market × symbol × dataset × date`: raw hash, bytes, UTC event and receipt time, label gaps, duplicates, validity masks, real first seen/revisions; `NOT_PROVEN` where missing.
4. Maintain frozen prereg H1–H10, chronological expanding walk-forward; no confirmatory holdout tests or trading advantage claims until causality, publication semantics, price/flow labels and economic fees/slippage gates are satisfied.

**Immutable evidence is in GitHub Actions and project R2 keys above. Project Spot/Futures/NAV/capital/reserve are unchanged.**


## 6. Дополнение: верифицированный 5m vendor-receipt as-of по 18 архивам Tardis

- [PR #103](https://github.com/analiticprosp-ship-it/crypto-price-feed/pull/103) merged; [Actions #39298935123](https://github.com/analiticprosp-ship-it/crypto-price-feed/actions/runs/39298935123) **SUCCESS**, все 11 offline regression tests PASS. Входной immutable SHA256 из PR #98 был проверен перед скачиванием.
- Ровно 18 источниковых файлов: Binance Futures/Bybit/OKX Swap × BTC/ETH/SOL × 2024-01-01 и 2026-09-01. Для каждого подтверждены compressed gzip SHA256, decompressed CSV SHA256, gzip CRC и точное число строк относительно PR #98.
- **5 184 из 5 184** пятиминутных интервалов: получено ненулевое/непустое, числово валидное native OI с `local_timestamp <= конец закрытого 5m бара + 30s` И `source_event_timestamp <= момент решения`, возраст от receipt **<=120s**. **0 stale, 0 missing, 0 использованных future vendor receipts**. Для каждой из 18 выборок — строго 288/288 свежих интервалов.
- Это «достаточно свежо по времени получения **Tardis**», **НЕ** «доказано изначально опубликовано биржей», не «наш исполнимый 5m snapshot», не сплошная доступная платная история между двумя контрольными датами. Не нормализовать единицы OI между venues.
- R2: `research/detector-tardis-18-free-oi-asof-5m/v1/39298935123-1.json`, SHA256 `677a0ac996fbb42c02d20dae79e68696cbe01bcc8578001177abfe97233c2827` (write/readback PASS).

## 7. Дополнение: полный исходный календарь двух ранних месяцев Binance OI

- [PR #104](https://github.com/analiticprosp-ship-it/crypto-price-feed/pull/104) merged; [Actions #39299592505](https://github.com/analiticprosp-ship-it/crypto-price-feed/actions/runs/39299592505) **SUCCESS**, 9 offline tests PASS.
- Источники **все 123 asset×day**: каждый из 30 дней 2020-09 для BTCUSDT плюс каждый из 31 дней 2021-12 отдельно для BTCUSDT, ETHUSDT, SOLUSDT. Для каждого издательский SHA256, ZIP CRC, native CSV, 288 ожидаемых 5m UTC меток.
- **78 FULL_SINGLE**, **29 FULL_DOUBLE** (по две полностью идентичные source строки в каждой из 288 уникальных меток), **16 PARTIAL**, **25 пропущенных source 5m меток**, **0 ошибок скачивания/publisher SHA256**, **0 конфликтующих native OI в дублях**.
- BTC 2020-09: 29 двойных полных дней; 2020-09-27 — 284 уникальные метки, **4 пропуска**, все 284 метки дублированы без расхождения native значений.
- Каждый BTC/ETH/SOL 2021-12: 26 single полных дней, 5 частичных дат, синхронных по календарю: 2021-12-04 (**3** отсутствующие метки), 2021-12-15 (**1**), 2021-12-24 (**1**), 2021-12-29 (**1**), 2021-12-31 (**1**). **7 пропусков на актив**, **21 суммарно**. Совпадение дат не доказывает первопричину дефекта; отсутствующие строки не восполнялись.
- R2: `research/detector-binance-early-oi-month-calendars/v1/39299592505-1.json`, SHA256 `13b5382f7e60dadc3c3de29913a828d4e1cf8aa89785c6d73f6de2f8d3c1b561` (write/readback PASS).
- 123 подтверждённых исходных дня **не доказывают полную доступную глубину** для остальных дней 2020–2023; исходный `create_time` — метка данных, не доказательство original publication/causal PIT.

**Текущий gate:** `BINANCE_EARLY_TWO_MONTHS_CALENDAR_VALIDATED_WITH_GAPS`; `TARDIS_18_VENDOR_RECEIPT_ASOF_5184_5184_VERIFIED`; `PRE2024_WHOLE_RANGE_UNCERTIFIED`; `EXCHANGE_FIRST_PUBLICATION_UNVERIFIED`; `EDGE_UNVALIDATED`. Данные research-only; ни одна торговая позиция, Spot/Futures/NAV/P&L или лимит не изменены.
