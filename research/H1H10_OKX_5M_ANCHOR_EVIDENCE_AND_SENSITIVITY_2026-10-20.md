# H1–H10 — OKX 5m timestamp semantics и альтернативные якоря, 20.10.2026

**Scope:** `RESEARCH_ONLY / EDGE_UNVALIDATED / NO_TRADE_AUTHORITY / HISTORICAL_CAUSAL_PIT_BLOCKED`.
**Frozen prereg:** `research/DETECTOR_H1_H10_BROAD_HISTORY_PREREG_v1_2026-10-19.md`. Не менять первичные R2, P&L/Futures/NAV/сигналы, пороги и подтверждающие holdout.

## 1. Семантика, отделённая по степени доказанности

| Источник | Что подтверждает источник | Что НЕ подтверждается |
|---|---|---|
| OKX `/api/v5/market/candles` / `bar=5m` | Официальная документация OKX: `ts` — **время начала** свечи (millisecond UNIX), `confirm=1` — закрытая свеча | Реальный точный первый момент HTTP-доступности исторической записи |
| OKX `/api/v5/rubik/stat/contracts/open-interest-history` / `period=5m` | Реальный HTTP receipt с исходной 5m меткой и значением OI, SHA-pinned 9-stream observer | Что `ts` — начало точно той же 5m свечи, когда данные впервые опубликованы, или исторически действовавшие `ctVal`/`ctMult` |
| OKX `/api/v5/rubik/stat/taker-volume-contract` / `period=5m,unit=1` | Реальный HTTP receipt, исходные sell/buy поля и их порядок, SHA-pinned poll | Что `ts` — начало/конец именно свечи price; единая универсальная unit-conversion; original-first-release |
| OKX `/api/v5/public/instruments` | Проверенные 20.10.2026 текущие `ctVal`, `ctMult`, `ctValCcy`, `ctType`, `settleCcy`; raw SHA/R2 | Непрерывная историческая таблица effective-from/effective-to с 2022 года |

**Официальные первоисточники:**
- OKX API v5 candlesticks: https://www.okx.com/docs-v5/en/ и публичная копия региональной документации https://app.okx.com/docs-v5/en/ .
- OKX API changelog: https://www.okx.com/docs-v5/log_en/ , запись **2024-06-13** о добавлении двух исследуемых trading-data endpoints. Дата добавления API НЕ равна дате первой публикации любой исторической 5m строки.
- OKX справка о contract face value и multiplier: https://www.okx.com/en-gb/help/how-can-i-do-derivatives-trading-with-the-jupyter-notebook . Текущая формула не подтверждает исторический version ledger.

**Область неопределённости:** соотношение трех 5m timestamp якорей НЕ доказано первоисточником. Историческая запись по `ts` != знание записи на прошлый `decision_at`. Даже одинаковые `ts` на всех трёх REST endpoints не доказывают original exchange first release.

## 2. Forward-only диагностика чувствительности без PIT-утверждения

Дополнение к `research/detector_h1h10_okx_receipt_join_guard.py`:

1. Верифицирует последний immutable per-run R2-манифест OKX и девять raw objects по точным SHA256. Источники и алгоритм `JOIN_CANDIDATE_ONLY` PR #135 не переписываются.
2. Берёт только confirmed (`confirm=1`) ценовые свечи с `price_open + 5m <= actual audit cutoff`, плюс реальное `response_received_ms` каждого из 9 REST-ответов.
3. Для каждого BTC/ETH/SOL строит **девять** отдельных гипотетических вариантов: `oi_source_label = price_open + {-5m,0,+5m}`; `flow_source_label = price_open + {-5m,0,+5m}`. Эти сдвиги НЕ означают установленные semantics и НЕ изменяют исходные строки.
4. Считает только количество raw-source-label совпадений при каждой альтернативе. Без пересчёта USD/контрактов, признаков, торгового edge, интерполяции, ожидания закрытия неизвестных интервалов или walk-forward.
5. В каждом варианте `causal_authorized=0`, `historical_pit_qualified=false`; весь исходный candidate-only архив остается отдельным immutable run report. Не допускает смену status из `EDGE_UNVALIDATED`.

**Результаты и хэши появляются только после настоящего GitHub Actions/R2 readback.** Наличие алгоритма/PR не эквивалентно успешному выполнению.

## 3. Блокирующие условия для будущего теста

Для H1–H10 OOS/locked holdout по-прежнему нужны оригинальная биржевая семантика OI/flow интервалов, `first_available_at` или реально измеренный и достаточный forward receipt для каждого признака, историческая цепочка изменений единиц контракта, same-venue matching, frozen train/validation/holdout и PIT-снимок действовавшего Detector A (`A_MISSING`, если его нет). После этого всё равно обязательны costs, walk-forward, multiple-testing correction, без изменения торговой authority.

**Нельзя выводить причинное преимущество из числа matched labels, нескольких successful Actions или актуальных таблиц контрактов.**
