# H1–H10: Nine-stream OKX actual receipt gaps — методика v1, 20.10.2026

**Режим:** `RESEARCH_ONLY / EDGE_UNVALIDATED / NO_TRADE_AUTHORITY`.

## Исходная проблема
GitHub Actions `cron: */15` запускается best-effort, а девять REST запросов одного прохода выполняются последовательно (BTC/ETH/SOL × OI/candle/taker flow). Поэтому разница между `observed_at_utc` двух готовых run manifests, даже при корректном SHA256, **не** равна интервалу получения отдельно взятой метрики. Продолжительность одного 9-source run тоже не доказывает биржевое время публикации данных.

Исходные manifest+raw hashes берутся только из приватного R2:
- `research/detector-okx-3metric-forward/v1/run-reports/<run>-<attempt>.json`
- `research/detector-okx-3metric-forward/v1/polls/<UTCday>/<run>-<attempt>-<symbol>-<metric>.json`

Граница доказательства: каждый run report проверяется по SHA256 R2 object metadata; raw streams последних 20 run reports перечитываются независимо по точным SHA. Старые отсутствующие raw-key маркируются отдельно; не заявлять для них raw SHA readback. Ни исходные ключи, ни данные не перезаписываются.

## Новый дополнительный аудит
`research/detector_okx_3metric_receipt_audit.py`: `summarize_stream_receipts(docs)` считает независимые фактические HTTP-receipt интервалы **для всех 9 однозначных имен `symbol|metric`**. Поля:
- число фактически полученных ответов каждого потока; сколько run manifests не содержит этот поток;
- первый и последний реально наблюдавшийся `response_received_ms`;
- число наблюдённых пар соседних ответов одного потока, медиана/максимум расстояния и число интервалов строго **больше 5, 10 и 20 минут**;
- максимум расстояния среди всех девяти потоков, отсутствие 5m first-receipt continuity, отсутствие original exchange first publication, `causal_rows_authorized=0`.

Fail-closed при неизвестных символах/метриках, response receipt после `observed_at_utc` run-манифеста, дублированной или невалидной receipt метке. Отсутствие poll записывается как **missing**, не интерполируется. Пустой или редкий массив не выдаётся за непрерывный сбор. Результат включается в новый неизменяемый `research/detector-okx-3metric-forward-audit/v1/<run>-<attempt>.json`, с реальным R2 readback SHA256, затем в ежедневный Fastlane.

## Семантика источника
- Официальный [OKX API v5](https://app.okx.com/docs-v5/en/): `/api/v5/market/candles` `ts` — **opening time of candlestick**, `confirm=1` — completed. Эта семантика относится только к price candles.
- Официальный `/api/v5/public/open-interest`: `oi` в контрактах, `oiCcy` в монетах, `oiUsd` в USD; `ts` определён как **Data return time** для этого **другого, snapshot** endpoint. Нельзя приписывать это описание `/api/v5/rubik/stat/contracts/open-interest-history` и тем более использовать как historical first release.
- Документация `/api/v5/public/instruments` подтверждает значения `ctVal`, `ctMult`, `ctValCcy` **в момент запроса**, но сама по себе не содержит историю effective-at версий. Отдельный raw+receipt R2 pilot PR #136 сохраняет только текущие версии.
- Семантики `ts` именно архивного rubik OI и contract taker flow, исходное время release, as-of исторический unit ledger — **BLOCKED**. Сверять их 5m source labels разрешается только как diagnostic candidate-only; 9 альтернативных якорей PR #137 **не** доказывают истинного интервала.

**Здесь нет нового подтверждения H1–H10, сравнения A/B/C/D или права торговли.** Ни Spot/Earn/Tangem/Futures, ни NAV/капитал/P&L/резерв, сигналы и лимиты не изменяются.

Новые численные итоги и SHA появятся только после фактического Actions-run, его логов и R2 readback. Старые R2 ключи и отрицательные наблюдения сохраняются.
