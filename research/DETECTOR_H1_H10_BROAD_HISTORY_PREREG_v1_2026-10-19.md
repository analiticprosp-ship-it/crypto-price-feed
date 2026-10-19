# ДЕТЕКТОР — H1–H10, расширенная историческая выборка: предварительный протокол v1.0
**Зафиксировано:** 19.10.2026 UTC, до какого-либо расширенного confirmatory H1–H10 backtest.
**Статус:** RESEARCH_ONLY / EDGE_UNVALIDATED. Это новый протокол будущей проверки, не ретроспективное утверждение, что H1–H10 уже проверены.

## 1. Неприкосновенные границы
- Независимое исследование. Никаких Futures-ордеров, изменений стратегий, торговых лимитов, NAV/капитала/P&L или прав на исполнение.
- Существующие тесты четырёх **бесплатных первых чисел месяца** уже просмотрены: 2024-01-01, 2025-01-01, 2026-09-01, 2026-10-01. **Они относятся к discovery и никогда не считаются новым независимым подтверждением.** Последний зафиксированный отрицательный baseline: fixed 50% Brier 0.25 превосходит Price и Price+OI на 15/60m. См. Issue #24, PR #71–75, успешный Actions #39170058191.
- Базовый universe: BTCUSDT, ETHUSDT, SOLUSDT; Binance/OKX/Bybit Spot и USDT perpetual, с точной записью venue, instrument, contract units, quote units, UTC. Межбиржевые OI не смешивать, OI contracts/tokens/USD не складывать без проверенного единичного пересчёта.
- Целевой период: **2024-01-01 — 2026-10-16 UTC**; данные до 2024 года — отдельная заранее документированная дополнительная выборка, если доступны. Отсутствующее = DATA_MISSING, без искусственных свечей/потоков/OI.
- Источники: из уже сохранённого приватного R2 и реально доступных архивов, с сохранением SHA256 и provenance. Покупка подписки/платного исторического пакета — только по отдельному явному согласию пользователя.

## 2. Изначальные направления H1–H10 (не подменять утверждённые названия)
| ID | Исследовательское направление | Основной сравнительный тест | Обязательная исходная информация |
|---|---|---|---|
| H1 | Направленный taker flow опережает Spot | Прирост OOS прогноза будущего Spot return против только-прошлая-цена | Spot aggTrades, подтверждённое время доступности |
| H2 | OI + активные покупки предшествуют цене | OOS абляция price+flow против price+flow+OI | Same-venue OI, taker buy/sell, price |
| H3 | Рост OI при почти неизменной цене = возможное поглощение | Сравнение будущей абсолютной доходности и продолжения/разворота с matched-control | OI, price, taker flow, заранее определённые пороги |
| H4 | Снижение плеча после ликвидаций → восстановление | Будущий recovery vs matched stress events | Ликвидации с временем публикации, OI, цена |
| H5 | Позиционные метрики могут дублировать друг друга | OOS ablation correlated leverage features vs reduced set | OI, funding, basis и единицы измерения |
| H6 | Futures flow опережает Spot | Проверка lead/lag c causal cutoffs и matched controls | Spot/Perp trades, сопоставимые часы/venue |
| H7 | Расхождение flow и price → истощение | OOS вероятность разворота против price-only | Flow, price, фиксированная причинная метка divergence |
| H8 | Малая глубина стакана усиливает market impact | Будущая абсолютная реакция цены на равный quote-flow vs high depth | PIT depth/order book, spread, flows |
| H9 | Эффект неодинаков для BTC, ETH, SOL | Заблаговременно заданные asset interactions, held-out days | Одни определения и покрытие трёх активов |
| H10 | Совместная модель превосходит действующий Детектор | A/B/C/D на тех же датах/эпизодах и с затратами | Оригинальный Detector as-of snapshot и весь joint data-set |

**Направления H1–H10 приведены как тематический план из предшествующего исследовательского обсуждения.** Точные рабочие пороги/алгоритмы, отсутствующие в исходных материалах, не изображаются «старой предрегистрацией»: эта версия задаёт новые условия будущей проверки. Подбор этих условий на исторических holdout после их просмотра запрещён.

## 3. A/B/C/D и неизменный контроль
- A = существующий Детектор как он был известен на соответствующий момент (при отсутствии PIT-снимка **A_MISSING**, не моделировать прошлые сигналы из современных правил).
- B = сокращённый набор проверенных функций без leverage/liquidity, поверх price/flow.
- C = совместная модель price + verified flow + same-venue OI + funding + liquidity с mask и provenance.
- D = адаптивная C, режим calm/stress определяется только прошлыми значениями, параметры режима обучаются **только на training**.
- Для самостоятельных OI и magnitude экспериментов: **null P(up)=0.5**, train-only Laplace positive frequency, price-only, price+OI; для абсолютного движения: **no-move=0**, train-only mean absolute return, past-volatility price-only, price+abs(OI change). Сравнение только по идентичным наблюдениям.
- Все ранее испытанные гипотезы H1–H10 и переборы индикаторов входят в журнал множественных проверок, включая отрицательные тесты.

## 4. Часы и запрещённые подмены
Каждая величина должна иметь отдельно `source_event_at`, `source_first_available_at` / `vendor_receipt_at`, `collector_received_at`, `decision_at`, `venue`, `symbol`, `unit`, `source_sha256`, `quality_status`. Событие в истории != его публикация. Правило as-of: feature_available_at <= decision_at. Для подтверждённой historical OI Tardis допускается только **VENDOR_ASOF_RESEARCH**, не Binance exchange-publication-PASS. Неизвестное время публикации aggTrades допускает EVENT_BOUNDARY_PASS, но запрещает назвать full-flow model executable-confirmed.
- Закрытый 5m bucket — не ранее конца bucket +30 секунд для vendor-receipt OI/price; для другого источника — собственный измеренный release SLA + safety lag, никогда не подменять timestamp label временем доступности.
- Future price labels строятся отдельно от признаков; горизонты направления **15m (primary), 60m (secondary)**; magnitude **absolute |future log return| на 15m (primary) и 60m (secondary)**, если цена >0. Исходная earlier ablation использовала simple returns; новый magnitude pilot маркировать exploratory, не менять исходный retrospective label.
- No train/validation/test row crossing observed source day boundary; no future event records in features; no forward-fill across missing publication/collector outages; censor unresolved outcomes.

## 5. Расширение данных — обязательный порядок
1. Машиночитаемый inventory: venue, market, symbol, dataset, interval, window, rows, missing intervals, first-available evidence, units, license/cost, R2 object SHA256, status VERIFIED/PARTIAL/MISSING.
2. Отдельные small bounded pilots 7–14 календарных дней на реально доступных без оплаты источниках; валидировать формат и вычитку, не запускать бесконтрольный full-history replay.
3. Backfill по календарным месяцам с checkpoints, разрешёнными ограничениями GitHub Actions и идемпотентными ключами R2. Vendor/venue/metric provenance в каждом месяце.
4. До сравнения price+OI+flow подтвердить publication as-of, иначе masked/PARTIAL, без выдуманного full joint coverage.

## 6. Freeze/splits/статистика
- **Discovery:** прежние четыре sample days и любые просмотренные до freeze дни (исключить из untouched holdout).
- **Train/validation:** prior UTC dates до 2026-06-30. Expanding walk-forward: начальная train-history >=180 календарных дней; test windows = последовательные неперекрывающиеся 30-дневные блоки; purge/embargo **24 часа** между train и последующим test и между границами label windows.
- **Окончательный locked holdout:** 2026-07-01 00:00 UTC — 2026-10-16 23:59 UTC с явными исключениями *любых уже просмотренных дат/эпизодов* (как минимум 2026-09-01 и 2026-10-01). Эти исключения означают, что holdout может стать неполным. До проверки покрытия не объявлять pristine.
- Normalization, regime thresholds, class weights, calibration и любые признаки обучать исключительно на earlier train; заранее зафиксированные параметры не оптимизировать по holdout.
- Единица независимости: календарный UTC-день и не перекрывающиеся рыночные эпизоды, **не 5m строки**; блоковые bootstrap доверительные интервалы с блоком >=1 UTC дня; overlapping 15/60m метки внутри дня коррелируют.
- Минимальный claim gate: >=60 полных независимых holdout дней, >=100 независимых эпизодов для event hypotheses, >=3 режима и все три основных актива с достаточным качеством; иначе **INSUFFICIENT_COVERAGE**. Эти критерии — консервативный research gate, не обещание наличия данных.
- Метрики direction: Brier (primary), logloss, calibration, accuracy (secondary). Magnitude: MAE по absolute log-return (primary), RMSE, отдельно recall/precision tail event на фиксированном **train-only** p90 threshold. H10: incremental out-of-sample net performance после комиссии, slippage, spread, funding и capacity, против A на **тех же** событиях (A_MISSING => H10 not testable).
- Family-wise correction: Holm step-down alpha=0.05 на **10 основных H1–H10 comparisons**, отрицательные outcomes сохраняются. Все вторичные горизонты, активные режимы и asset cuts описательные, без притворных независимых p-values; для post-hoc идей — новый discovery-only пакет/будущий locked holdout.
- Cost stress: fees / spread / slippage / funding и биржевые ограничения задаются только из проверенных источников на дату теста; при отсутствии fee tier и исполнения **COST_UNVERIFIED**, не объявлять прибыль.
- На одном из доступных публичных наборов возможен только **exploratory research** до выполнения evidence gates. Negative result не удалять и не превращать в PASS.

## 7. Приёмка и authority
Артефакты: immutable prereg JSON+SHA256, git commit, run-id, source inventory с gaps, timestamp proof, training code and hashes, holdout exclusion ledger, A/B/C/D одинаковые folds, независимая audit replay, per-day/per-asset metrics, corrected testing ledger, затратные сценарии. Статусы: `DATA_MISSING`, `ASOF_PUBLICATION_UNVERIFIED`, `INSUFFICIENT_COVERAGE`, `EDGE_UNVALIDATED`. Любое production authority требует отдельного решения по действующему MASTER. Этот документ ничего не активирует в реальной торговле.
