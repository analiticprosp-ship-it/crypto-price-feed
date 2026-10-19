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


## 8. Дополнение: исходные квартальные OI-календари 2022Q1 и 2023Q1

- [PR #106](https://github.com/analiticprosp-ship-it/crypto-price-feed/pull/106) merged, [Actions #39308756529](https://github.com/analiticprosp-ship-it/crypto-price-feed/actions/runs/39308756529) **оба matrix jobs SUCCESS**; 11 offline regression tests PASS. Полный календарный аудит оригинальных Binance USD-M daily metrics, BTCUSDT/ETHUSDT/SOLUSDT × 90 дней за каждый квартал. **540/540 источниковых ZIP прошли publisher SHA256, ZIP CRC и проверку временных/числовых CSV-полей.**
- **2023Q1:** 270/270 FULL_SINGLE_VALID (90/90 каждый BTC/ETH/SOL), 0 missing 5m labels, 0 duplicate source labels, 0 invalid numeric OI; это качественная **источниковая** история за один весь квартал, но не доказательство первоначального времени публикации. Immutable R2: `research/detector-binance-oi-pre2024-quarter-calendars/v1/2023Q1/39308756529-1.json`, SHA256 `d89226756f5061dc8bcd8f84b8f59bb8733ed9c74af54bd48b5738dce308bbbc`.
- **2022Q1:** 263/270 FULL_SINGLE_VALID; 7 PARTIAL (ошибочные native numeric OI), 352 invalid values, 0 missing source 5m labels, 0 duplicate labels. Проблемные дни: BTC/ETH/SOL **2022-03-07** — по 102 ошибочных значения, **2022-03-08** — по 15; SOL **2022-03-15** — 1 значение. Immutable R2 `research/detector-binance-oi-pre2024-quarter-calendars/v1/2022Q1/39308756529-1.json`, SHA256 `c9ba36b579e2011a350ebaf5914e6204880be84ae7bb369aecc8659f79647a30`.
- Отсутствие пропущенных source timestamps не означает отсутствие некорректных OI **значений**. Исходные архивы не изменялись, импутации/дедупликации нет. Исследование остаётся `RESEARCH_ONLY / EDGE_UNVALIDATED / EXCHANGE_RELEASE_PIT_UNVERIFIED`.

## 9. Дополнение: самые ранние фактически проверенные Tardis free derivative_ticker OI

- [PR #107](https://github.com/analiticprosp-ship-it/crypto-price-feed/pull/107) merged, [Actions #39309240387](https://github.com/analiticprosp-ship-it/crypto-price-feed/actions/runs/39309240387) **SUCCESS**, 10 offline tests. Девять точных инструментов Binance Futures, Bybit, OKX Swap × BTC/ETH/SOL. Дата контрольного файла — первое число **следующего** месяца после instrument-specific `availableSince` из полного публичного Tardis catalog, не выдуманная дата начала OI и не доказательство непрерывной истории.
- **Binance Futures BTC/ETH 2019-12-01:** оба gzip-архива действительно существуют; BTC 45 493 / 45 493 исходных записей с **пустым** `open_interest`, ETH 32 636 / 32 636 с пустым `open_interest`. **0/288 свежих vendor-receipt as-of OI интервалов у каждой монеты**. Ни в коем случае не объявлять декабрь 2019 пригодным OI-набором Binance по этим Tardis архивам.
- **Binance Futures SOL 2020-10-01:** 94 101 numeric OI из 94 106 строк, **288/288** fresh 5m vendor receipt as-of.
- **Bybit:** BTC **2020-06-01**, ETH **2020-11-01**, SOL **2021-07-01** — каждая дата **288/288** fresh. Прямой Bybit REST ранее дал HTTP403, что не отрицает Tardis sample.
- **OKX Swap:** BTC и ETH **2020-01-01**, SOL **2021-02-01** — каждая дата **288/288** fresh.
- Бounded gzip CRC/sha256, поля OI и исходные microsecond timestamp проверены, отчёт SHA256 R2 write/readback PASS. R2: `research/detector-tardis-earliest-free-receipt/v1/39309240387-1.json`, SHA256 `12b936127078b4d0318a4f6c2b59c60ccfb28db562ccdef318b4e1fa1ed7bb95`.
- Точный rule: закрытый 5m бар +30s, Tardis vendor local receipt И событие источника не позднее cutoff, свежесть ≤120s. Это **VENDOR_RECEIPT_ASOF, а не оригинальный EXCHANGE_RELEASE_PIT**. Ни один из девяти дней не доказывает целую непрерывную 2019–2026 историю, нет сравнимости native OI units между площадками.

**Сводный актуальный gate:** `EARLIEST_TARDIS_FREE_SAMPLES_9_OF_9_AUDITED` / `2023Q1_BINANCE_OI_FULL_270` / `2022Q1_BINANCE_OI_263_FULL_7_INVALID` / `PRE2024_WHOLE_RANGE_UNCERTIFIED` / `EXCHANGE_RELEASE_PIT_UNVERIFIED` / `EDGE_UNVALIDATED`.

Следующий научный этап: оставшиеся кварталы 2020–2023 с дневным provenance и quality masks, классификация причин ошибочных OI 7–8 марта 2022, независимая публикационная семантика и затем frozen walk-forward H1–H10 без утечек. Все пользовательские Spot/Futures/NAV/P&L и лимиты неизменны.

## 10. Подтверждённый исходный календарь OI за 2022–2023 годы: ВСЕ даты

- [PR #109](https://github.com/analiticprosp-ship-it/crypto-price-feed/pull/109) объединён с main. [GitHub Actions #39311042453](https://github.com/analiticprosp-ship-it/crypto-price-feed/actions/runs/39311042453) **SUCCESS, 6/6 квартальных задач**, все 11 offline tests в каждой задаче PASS. Проверены 1 650 дополнительных ежедневных source ZIP для 2022Q2–Q4 и 2023Q2–Q4. Для каждого файла проверены издательский SHA256 из .CHECKSUM, ZIP CRC, исходные native OI значения, UTC-метки, дубли, пропуски. Неоднозначные записи не подменялись, все 6 отчётов записаны в R2 и прочитаны обратно по SHA256.
- С учётом уже независимо завершённых [PR #106](https://github.com/analiticprosp-ship-it/crypto-price-feed/pull/106) / [Actions #39308756529](https://github.com/analiticprosp-ship-it/crypto-price-feed/actions/runs/39308756529) аудирован **каждый из 2 190 дней-активов BTC/ETH/SOL с 2022-01-01 по 2023-12-31**. Полностью качественные **2 159 / 2 190**, частичные **31**, **401 исходное некорректное числовое OI** и **26 отсутствующих пятиминутных меток**. **Нулевые** publisher/source-fetch ошибки по всем кварталам. Это качество *исторических source labels*, НЕ изначальная доступность данных во время торгового решения.
- Кварталы (число дней-активов / полный источник / частичный):
  - 2022Q1 **270 / 263 / 7**, 352 invalid native OI, 0 gaps.
  - 2022Q2 **273 / 273 / 0**, 0 invalid, 0 gaps.
  - 2022Q3 **276 / 275 / 1**, SOLUSDT 2022-09-03: 1 invalid native OI, 0 gaps.
  - 2022Q4 **276 / 276 / 0**, 0 invalid, 0 gaps.
  - 2023Q1 **270 / 270 / 0**, 0 invalid, 0 gaps.
  - 2023Q2 **273 / 270 / 3**, 12 invalid, 0 gaps.
  - 2023Q3 **276 / 270 / 6**, 3 invalid, 9 missing 5m labels.
  - 2023Q4 **276 / 262 / 14**, 33 invalid, 17 missing 5m labels.
- **Итог:** статус `BINANCE_2022_2023_ALL_SOURCE_DAYS_AUDITED_WITH_QUALITY_MASKS`; не равно `ALL_PIT_CERTIFIED`. Сохранить defect masks в любой производной исследовательской панели. 2 159 полных дней-активов не равны 2 159 дням трехмонетного совместного календаря.

### Неизменяемые отчёты кварталов, проверенные R2 SHA256

| Квартал | Объект R2 относительно bucket | SHA256 |
|---|---|---|
| 2022Q2 | `research/detector-binance-oi-2022-2023-rest-quarters/v1/2022Q2/39311042453-1.json` | `7c129110b5ea0cc412956269e36616138185fc3562c8e6e7431809c075e9b812` |
| 2022Q3 | `research/detector-binance-oi-2022-2023-rest-quarters/v1/2022Q3/39311042453-1.json` | `e3e3f89227ee3eb8f4b80e5b4f6269320124e3dba457fe18de1d61694bd17c4b` |
| 2022Q4 | `research/detector-binance-oi-2022-2023-rest-quarters/v1/2022Q4/39311042453-1.json` | `dcd4065f15c333289cebbe1faefc75d337c965df20b3b588d920d2aec1ba54bf` |
| 2023Q2 | `research/detector-binance-oi-2022-2023-rest-quarters/v1/2023Q2/39311042453-1.json` | `b1668387ea4c10357dedd1cf38589531810eac117fc9f407bf8174c94f857741` |
| 2023Q3 | `research/detector-binance-oi-2022-2023-rest-quarters/v1/2023Q3/39311042453-1.json` | `b0c06c8dfaab2244954cd619bbaa73d7de54bd91ddab3c45748421dc1b6e955d` |
| 2023Q4 | `research/detector-binance-oi-2022-2023-rest-quarters/v1/2023Q4/39311042453-1.json` | `1afce2cd9b5855d84e19d6ad947620fb6e8b89872cf5383113d74420ab20c425` |

## 11. Перепроверка наиболее ранних известных Binance OI источников (2020–2021)

- [PR #111](https://github.com/analiticprosp-ship-it/crypto-price-feed/pull/111) объединён; [GitHub Actions #39311651357](https://github.com/analiticprosp-ship-it/crypto-price-feed/actions/runs/39311651357) **SUCCESS**, 10 offline tests PASS, **399 HEAD проверок** исходных ZIP по 3 монетам. Проверены 1-е, 15-е, последние дни каждого месяца 2020–2021 и ВСЕ даты непосредственно вокруг первого обнаруженного положительного месяца, затем источник каждого самого раннего выявленного дня перепроверен по publisher SHA256/ZIP CRC/CSV.
- **BTCUSDT: 2020-09-01; ETHUSDT: 2021-12-01; SOLUSDT: 2021-12-01** — первые **наблюдённые и побайтово проверенные** Binance USD-M daily metrics OI ZIP в этом ограниченном методе.
- Это `FIRST_OBSERVED_ARCHIVE_BYTES_VERIFIED`, а **не** доказательство абсолютного начала хранения/публикации: в более ранних месяцах проверены только три контрольных дня, любые остальные теоретически могут иметь архивы. До этого пункта нет `ABSOLUTE_EARLIEST_SOURCE`.
- R2 immutable: `research/detector-binance-oi-2020-2021-origin-recon/v1/39311651357-1.json`; SHA256 `7242d39d61634d137b3f11fff24729deb47411820b7794249b054ceeb5db683a`. Publisher SHA, ZIP CRC и R2 write/readback PASS. Нет правок исходных исторических данных.

**Новый суммарный gate:** `BINANCE_2022_2023_ALL_SOURCE_DAYS_AUDITED_WITH_QUALITY_MASKS`; `TARDIS_18_VENDOR_RECEIPT_ASOF_5184_5184_VERIFIED`; `BINANCE_ORIGIN_FIRST_OBSERVED_NOT_ABSOLUTE`; `EXCHANGE_RELEASE_PIT_UNVERIFIED`; `EDGE_UNVALIDATED`. Никаких изменений пользовательских Spot, Earn, Tangem, Futures, NAV, P&L, капитала, резерва и торговых лимитов.

## 12. Полный календарный SOURCE-аудит BTC OI 2020-09-01 — 2021-12-31

- [PR #113](https://github.com/analiticprosp-ship-it/crypto-price-feed/pull/113) merged. [Actions #39312585332](https://github.com/analiticprosp-ship-it/crypto-price-feed/actions/runs/39312585332) **SUCCESS, все пять matrix-jobs**, по 10 офлайн-регрессионных тестов в каждом. Буквально каждый из **426** дневных source ZIP BTCUSDT Binance USD-M OI за октябрь 2020 — ноябрь 2021 проверен издательским `.CHECKSUM` SHA256, ZIP CRC, исходными native значениями, 5m UTC календарём, полями, дублями и дефектами; оригиналы неизменны. Пять независимых R2 JSON с хешами / проверенным readback.
- Результат 426 дней: **364 FULL**, **62 PARTIAL**, **490 отсутствующих пятиминутных меток**, **10 некорректных числовых OI**, ноль publisher/source failures и ноль конфликтов значений в полных дублированных строках.
- Периоды (календарные дни / полные source-дни / частичные / пропуски 5m / invalid native OI):
  - 2020Q4: **92 / 89 / 3 / 29 / 0**. Все 89 полных дней с 288 парами полностью идентичных строк.
  - 2021Q1: **90 / 73 / 17 / 140 / 0**. Все 73 полных дня с 288 парами полностью идентичных строк.
  - 2021Q2: **91 / 80 / 11 / 229 / 10**. Среди 80 полных дней **46 full exact double** и **34 full single**; переход неоднороден и имеет дефекты.
  - 2021Q3: **92 / 80 / 12 / 32 / 0**. Все 80 полных дней одиночные.
  - 2021 Oct–Nov: **61 / 42 / 19 / 60 / 0**. Все 42 полных дня одиночные.
- Вместе с уже проверенными [PR #104](https://github.com/analiticprosp-ship-it/crypto-price-feed/pull/104) BTC сентябрём 2020 (30 дней, 29 FULL_DOUBLE, 1 PARTIAL, 4 missing source labels) и BTC декабрём 2021 (31 день, 26 FULL_SINGLE, 5 PARTIAL, 7 missing labels), **каждый день с 2020-09-01 по 2021-12-31 был исходно проверен: всего 487 дней, 419 полных (237 exact-double + 182 single), 68 частичных; 501 отсутствующая source 5m метка, 10 недопустимых числовых OI**.
- **ВНИМАНИЕ:** 419 полных дней включают 237 дней с удвоенными одинаковыми источниковыми записями. Нельзя использовать `raw_rows` как число независимых 5m-наблюдений, молча дедуплицировать или заполнять отсутствующие метки. `SOURCE_5M_CALENDAR_AUDITED` НЕ означает `VINTAGE_ASOF_EXCHANGE_RELEASE_PROVEN`. Original exchange publication и исторические revisions не доказаны, `EDGE_UNVALIDATED`.

| Интервал | Объект R2 | SHA256 |
|---|---|---|
| 2020Q4 | `research/detector-btc-usdm-oi-2020oct-2021nov/v1/2020Q4/39312585332-1.json` | `7206ede2c28c5cfd9bdc35efc788eecc619e85feddb31fca4c138291e68bd9d3` |
| 2021Q1 | `research/detector-btc-usdm-oi-2020oct-2021nov/v1/2021Q1/39312585332-1.json` | `322c18045c7cc4755b9c21f93d618fdaa84a4bffec437847f24a0e19f11fb599` |
| 2021Q2 | `research/detector-btc-usdm-oi-2020oct-2021nov/v1/2021Q2/39312585332-1.json` | `ea43561114bdb0611c2386e4b7869661cb5c9e7a3749fbbf823b2dd0117d9e67` |
| 2021Q3 | `research/detector-btc-usdm-oi-2020oct-2021nov/v1/2021Q3/39312585332-1.json` | `d640ebcabd95f7e8922383b7d00b0826bba0c48e01d872879035cb0757780f26` |
| 2021 Oct–Nov | `research/detector-btc-usdm-oi-2020oct-2021nov/v1/2021OCTNOV/39312585332-1.json` | `7fe4108e9fb734c887adfcaecbf37df0ea629993358caf5002fab845d94a72d0` |

**Актуальные ограничения:** `BINANCE_BTC_2020_09_2021_12_SOURCE_CALENDAR_ALL_DAYS_AUDITED`; `BINANCE_2022_2023_ALL_SOURCE_DAYS_AUDITED_WITH_QUALITY_MASKS`; `PRE2020_ORIGIN_ABSOLUTE_NOT_PROVEN`; `EXCHANGE_ORIGINAL_RELEASE_PIT_UNVERIFIED`; `EDGE_UNVALIDATED`. Для исходных ETH/SOL OI до декабря 2021 полный дневной непрерывный архив **не сертифицирован**. Никаких изменений Spot/Earn/Tangem/Futures/NAV/P&L/капитала/резерва/лимитов.

## 13. Новое свидетельство: поле OI в бесплатных Tardis Binance Futures BTC/ETH появляется в контрольных днях июня 2020

- [PR #110](https://github.com/analiticprosp-ship-it/crypto-price-feed/pull/110) отдельно объединён после проверки ранее открытого исследования; [Actions #39315241590](https://github.com/analiticprosp-ship-it/crypto-price-feed/actions/runs/39315241590) **SUCCESS**, 387 независимых HEAD-запросов (по 1/15 числам месяцев 2019–2021 + уточнение первых обнаруженных месяцев), 0 неизвестных HTTP ответов; самые ранние побайтово проверенные оригинальные Binance USD-M **daily/metrics 5m** архивы остались BTC **2020-09-01**, ETH/SOL **2021-12-01**. R2 `research/detector-binance-oi-earliest-month-day-boundary/v1/39315241590-1.json`, SHA256 `3c3a85c9f21bc9e336c28b5b18afeb4ff08291b2b60098982cbc8fd6100c33b3`. Это **ограниченное наблюдение**, не доказанное абсолютное происхождение набора.
- [PR #115](https://github.com/analiticprosp-ship-it/crypto-price-feed/pull/115) merged; [Actions #39315710848](https://github.com/analiticprosp-ship-it/crypto-price-feed/actions/runs/39315710848) **SUCCESS**, **11/11** offline tests. Ровно **28 из 28** бесплатных архивов Tardis Binance Futures `derivative_ticker` (BTCUSDT и ETHUSDT × каждый первый день месяца с **2019-12-01 по 2021-01-01**) успешно скачаны, полностью распакованы по gzip CRC, у каждого отдельно рассчитаны compressed SHA256 и CSV SHA256 и обработаны действительные Tardis `local_timestamp` в микросекундах. SHA256 источников за 2019-12-01 совпали с независимо закреплённым историческим отчётом PR #107 (source-revision guard).
- **2019-12-01, 2020-01-01, 2020-02-01, 2020-03-01, 2020-04-01, 2020-05-01:** все исходные события по обоим инструментам имеют **пустое `open_interest`**; поэтому каждый контрольный день содержит **0/288** доступных fresh OI 5m интервалов, а не 288 пригодных OI только по наличию тиков.
- **2020-06-01 — первая наблюдаемая пригодная бесплатная месячная выборка для обоих BTC/ETH:** BTC **184 437** исходных строк с числовым OI из **184 454** событий, ETH **160 625** из **160 635**; для обоих инструментов **288/288** пятиминутных интервалов содержат свежий OI с Tardis receipt и source event не позднее конца закрытого бара +30 секунд и возрастом receipt ≤120 секунд.
- **2020-07-01 ... 2021-01-01:** каждый из последующих **7** отдельных контрольных дней на BTC и ETH содержит **288/288** fresh vendor-receipt as-of OI слотов, **0 stale**, **0 missing**.
- **Интерпретация — строго:** Tardis event archive и Binance daily/metrics 5m ZIP — **разные источники/структуры**. Более раннее `VENDOR_RECEIPT_ASOF` OI подтверждено только на 8 бесплатных контрольных днях с июня 2020 по январь 2021 для каждой монеты. **НЕ** доказаны полный набор промежуточных дней, конкретный первый день между маем и июнем 2020, исходный биржевой publication time, PIT исполнимости пользователя или реальная доходность H1–H10. На остальных 6 контрольных днях данные событий есть, но поле OI пустое; не называть это «OI=0».
- Неизменяемый отчёт R2: `research/detector-tardis-binance-btc-eth-2020-free-monthly-oi/v1/39315710848-1.json`, SHA256 `b403139191a0ff8784adf0e2ff0ec2a215d700fada578143b92852d479892cf8` (write/readback PASS).

**Исследовательский статус:** `BINANCE_METRICS_SOURCE_BTC_2020_09/ETH_SOL_2021_12_FIRST_OBSERVED_NOT_ABSOLUTE`; `TARDIS_BTC_ETH_2020_06_FIRST_FRESH_FREE_MONTHLY_SAMPLE`; `VENDOR_RECEIPT_ONLY`; `EXCHANGE_RELEASE_PIT_UNVERIFIED`; `EDGE_UNVALIDATED`. Ни Spot/Earn/Tangem, ни Futures, ни NAV/P&L, ни лимиты, ни торговые операции не менялись.
