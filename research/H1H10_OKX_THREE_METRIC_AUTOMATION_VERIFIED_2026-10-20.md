# H1–H10 — автоматический OKX OI + цена + поток: проверенное состояние 20.10.2026

**Статус:** `RESEARCH_ONLY / EDGE_UNVALIDATED / ORIGINAL_EXCHANGE_RELEASE_PIT_UNVERIFIED`. Настоящая автоматизация исследовательских источников, не торговый сигнал и не доказанный причинный бэктест.

## I. Что уже реализовано

1. [PR #131](https://github.com/analiticprosp-ship-it/crypto-price-feed/pull/131) (MERGED): отдельный пилот GitHub Actions `.github/workflows/detector-okx-3metric-forward-48h.yml`, в собственной исследовательской области R2 `research/detector-okx-3metric-forward/v1/`.
   - BTC-USDT-SWAP, ETH-USDT-SWAP, SOL-USDT-SWAP; по **три** открытых публичных OKX REST ответа на монету, девять независимых фактических `response_received_ms`: `/rubik/stat/contracts/open-interest-history` (native OI), `/market/candles` (5m price), `/rubik/stat/taker-volume-contract` (5m taker SELL затем BUY, unit=1).
   - Для каждого ответа записаны request start, actual receipt timestamp, source label, исходные строки/хеши, metadata, отсутствие подмены пробелов. Venue=OKX, perpetual только; цена не превращается в системную NAV-котировку.
   - Собирает first-observed upper bounds с предыдущими observed-absence границами, но **не** заявляет точную историческую публикацию биржей. Создаёт immutable per-run R2 report + SHA256 readback. Отдельные source receipts и новые записи сохраняются с SHA256.
   - Cron `*/15` UTC best-effort, `workflow_dispatch`, 48h capped pilot с попыткой self-disable через `actions:write` **только своего workflow**. Автоматическое self-disable будет считаться проверенным лишь после фактического результата. GitHub cron не гарантирует ни 15 минут, ни тем более непрерывную доступность 5m на границе bucket+30s.
2. [PR #132](https://github.com/analiticprosp-ship-it/crypto-price-feed/pull/132) (MERGED): добавляет к будущим run-report точные immutable raw-object keys и SHA256 для девяти потоков, bounded независимый аудит `research/detector_okx_3metric_receipt_audit.py` и интеграцию с ежедневным Fastlane. Аудит повторно читает все run-report bytes+metadata SHA256, а для последних двадцати запусков — raw файлы с точными SHA из run manifest; отдельно фиксирует исторические записи без raw-link и старые raw pins, которые не перечитывались в этом запуске.
3. [PR #133](https://github.com/analiticprosp-ship-it/crypto-price-feed/pull/133) (MERGED): точечное исправление одного отрицательного offline теста постороннего инструмента, без изменения промышленного кода.

## II. Реальные результаты, без смешения с будущими автоматическими запусками

- [GitHub Actions #39388020682](https://github.com/analiticprosp-ship-it/crypto-price-feed/actions/runs/39388020682): **SUCCESS**; **16 offline PASS**, **9/9** OKX source responses BTC/ETH/SOL, zero API error. Первый bootstrap означает **0 подтверждённых новых first-observed upper bounds относительно прошлых проверенных наблюдений** (исходные данные получены, но невозможно доказать предыдущую недоступность). Совпало по 19 source-label слотов каждого инструмента, исключительно `SOURCE_LABEL_OVERLAP_ONLY_NO_CAUSAL_PIT`. R2 `research/detector-okx-3metric-forward/v1/run-reports/39388020682-1.json`, SHA `52ac5a007b732f93b301eca2ef9576f2c464fa96b7328228abac0d11a6cb1c0b`.
- [GitHub Actions #39388707578](https://github.com/analiticprosp-ship-it/crypto-price-feed/actions/runs/39388707578): **SUCCESS**; **16 offline PASS**, 9/9 source responses, **12** новых first-observed записей после bootstrap, 19 пересекающихся source labels на coin; **0** causal training rows authorized. R2 `research/detector-okx-3metric-forward/v1/run-reports/39388707578-1.json`, SHA `74702e434dbfb203647db7456a2a370c0c68fdeddd643aa8a266e218aab4f5c1`. Следующие run manifests содержат raw-object SHA.
- [GitHub Actions #39388707579](https://github.com/analiticprosp-ship-it/crypto-price-feed/actions/runs/39388707579): **FAILED** из-за двух пересекавшихся условий в отрицательном test fixture; до аудита pipeline не дошёл. Результат не переписывать задним числом.
- [GitHub Actions #39388880757](https://github.com/analiticprosp-ship-it/crypto-price-feed/actions/runs/39388880757): **SUCCESS, 49 offline PASS** и actual-readback evidence:
  * 2 контрольных run-report;
  * 9 linked raw source streams SHA-verified по второму запуску;
  * 9 legacy source streams первого run без raw-key в родительском манифесте (отдельно обозначены, не утверждать их повторную SHA-проверку);
  * 0 **наблюдённых** межзапусковых gaps больше 20 минут в рамках этих всего двух запусков, `continuous_5m_pit_grade=UNVERIFIED`;
  * `causal_5m_rows_authorized=0` и `EDGE_UNVALIDATED`.
  * R2 audit `research/detector-okx-3metric-forward-audit/v1/39388880757-1.json`, SHA `84123232d17a66cc56ef996dea3153caf444612eaa9ca53e1b032de2f10073ba`.
  * R2 совместный source inventory `research/detector-h1h10-evidence-inventory/v1/39388880757-1.json`, SHA `93ff308d9accbc7227a812a69a28b7c9c041255516fb624e8ccc08c23d875535`.
  * R2 Fastlane gate state `research/detector-h1h10-fastlane/v1/evidence-7f4a5e3039788b8161b3782fd4e66de9afa68b596b1c61aa0d0fc535d87220e4.json`, SHA `7f4a5e3039788b8161b3782fd4e66de9afa68b596b1c61aa0d0fc535d87220e4`. Приращение относительно старой версии мониторинга не означает подтверждённую рыночную гипотезу.
  * Сохранён старый source-quality календарь 1 734/1 750 2022–2026 с 16 исключениями; historical first-publication release не подтверждён.

## III. Что специально НЕ заявляется

- 15-минутные best-effort GitHub job times **не обеспечивают** 5m SLA, исполнение ордера или непрерывный PIT. Даже с 0 наблюдённых gaps в двух контрольных runs нельзя расширять это на каждый исторический 5m bucket.
- Совпадение `ts` OI, свечи и taker данных может означать различную семантику начала/конца периода; источник публикационного времени неизвестен. Нельзя складывать native OI-contracts / base taker-volume / quote price как одноименовые единицы.
- Нельзя превращать экспортируемый исторический архив или `source timestamp` в независимую first-received прошлую историю. Исторический multi-asset holdout подтверждения H1–H10 по этой работе не запускался.
- Никакие расходы на 24/7 VPS/WebSocket/Cloudflare worker не одобрены; не создавались. Никаких Futures-ордеров, новых лимитов, изменений Spot/Earn/Tangem, NAV/капитала/P&L/резерва.

## IV. Очередность следующего этапа

1. После окончания ограниченного пилота проверить реальное self-disable, фактическую задержку и пропуски/количество записей за весь период; отдельно зафиксировать график состояния, не подменять из него venue publication PIT.
2. Доказать по официальным источникам, что timestamp OI, price и flow относится к одному и тому же закрытому 5m interval; подтвердить native contract units и historical contract metadata. Только после этого допустить join с проверенным `available_at<=decision_at`, без backfill availability догадками.
3. Для устойчивого real-time PIT потребуется явно согласованная инфраструктура постоянного процесса; GitHub 15-minute cron является исследовательским демо и не заменяет потоковый точный сбор.
4. H1–H10, locked holdout, сравнение A/B/C/D, costs, Holm/CI и единичная проверка trade economics остаются `BLOCKED/EDGE_UNVALIDATED` до качества источников и отдельного решения о production authority.

Журнал: [issue #24](https://github.com/analiticprosp-ship-it/crypto-price-feed/issues/24). Исходный архиватор и Fastlane: PR #123–130.
