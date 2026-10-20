# H1–H10 — автономный исследовательский контур: проверенная настройка 20.10.2026

Статус: **RESEARCH_ONLY · EDGE_UNVALIDATED · NO_TRADE_AUTHORITY**.
Этот документ описывает только реально объединённые изменения и результаты Actions, а не обещанный фоновой работой будущий результат.

## 1. Что включено

1. **Новый архиватор исследовательских артефактов GitHub → приватный R2**: PR #123, PR #124. Установлен существующий ежедневный cron GitHub Actions в `.github/workflows/detector-r2-archive.yml` (05:17 UTC; расписание GitHub best-effort). Артефакты проверяются ZIP CRC, SHA256, фактическим обратным чтением из R2. Отсутствовавшие/истёкшие старые артефакты записываются в отдельный `research/archive-skipped-v2/<run_id>.json`, **не** классифицируются как ошибки R2; реальные исключения API, доступа, ZIP, хеша остаются FAIL.
2. **Высоководный курсор вместо полного исторического обхода**: после успешной проверки запоминается последний полностью обработанный GitHub run ID в `research/detector-h1h10-archive-cursor/v3/latest.json` с R2 SHA256. Следующее ежедневное выполнение просматривает только новые run IDs; на случай задержки ограничение восемь страниц GitHub API, при усечении всё ещё FAIL/нельзя двигать курсор. Bootstrap-примечание: v2 Actions #39382155529 достоверно обработал страницы 1–6 вплоть до #39205092827, но не всю давнюю историю; сохраняется отдельный доступ к прежним исходным R2. Старые архивы не «восстанавливаются» из истёкших GitHub артефактов.
3. **Ежедневный Fastlane Gatekeeper**: PR #123, `.github/workflows/detector-h1h10-fastlane.yml`, cron 06:45 UTC, `workflow_dispatch` и проверка при изменении кода. Сверяет immutable исходный отчёт качества 1750 дней (R2 SHA256), вычисляет статусы стадий, пишет idempotent fingerprint в R2 и короткий GitHub Actions summary. Имеет только `contents:read`, не получает торговых прав и не отправляет торговые команды.

## 2. Реально подтверждённые контрольные запуски

- Архиватор v2 PR #123: [Actions #39382155529](https://github.com/analiticprosp-ship-it/crypto-price-feed/actions/runs/39382155529) — **SYNC_PARTIAL**. 18/18 offline тестов PASS; 44 benign skips и ноль настоящих ошибок передачи. Причина PARTIAL: 6 страниц недостаточно для 7-дневного lookback. Это исторически неудавшийся запуск, его нельзя задним числом переименовывать в SUCCESS.
- Архиватор v3 PR #124: [Actions #39382711258](https://github.com/analiticprosp-ship-it/crypto-price-feed/actions/runs/39382711258) — **SUCCESS / SYNC_COMPLETE**: 22 offline теста PASS, 31 ранее архивированный run, 43 benign skips, 0 actual transfer failure, 7 страниц сканирования. Сохранены SHA/byte readback, курсор. R2 отчет `research/detector-h1h10-archive-sync-status/v3/39382711258-1.json`, SHA256 `2a572be71fb807794aca9db1678f91993f072ac25648abaaa085849d248e077a`.
- Gatekeeper PR #123: [Actions #39382155527](https://github.com/analiticprosp-ship-it/crypto-price-feed/actions/runs/39382155527) **SUCCESS**, 12/12 offline тестов, исходный pinned report SHA256 PASS. R2 idempotent состояние `research/detector-h1h10-fastlane/v1/evidence-a3bfb248ff1d270b8c836fb74d87cf5620a5627ab4c6776528172b2be7e1f955.json`, SHA256 `a3bfb248ff1d270b8c836fb74d87cf5620a5627ab4c6776528172b2be7e1f955`.

## 3. Gatekeeper readiness, что он РЕАЛЬНО разрешает

| Направление | Статус | Основание |
|---|---|---|
| Source-label/native numeric 5m OI BTC/ETH/SOL | PASS с 16 исключёнными датами | immutable отчёт 1 734/1 750 дат, SHA256 |
| Exchange original first-release / point-in-time | UNVERIFIED | Source create_time ≠ first publication |
| Полный historical joint price + flow + OI causal as-of | BLOCKED | Время доступности всех нужных показателей не доказано |
| PIT источник H1–H10 в locked holdout | BLOCKED | Известны discovery/holdout exclusions; невозможно заменить их чистым source-label OI |
| Автоматическое подтверждение прибыльной стратегии | FORBIDDEN | Нет достаточных PIT, costs, Detector A и независимых OOS доказательств |
| Реальные Spot/Futures/NAV/P&L/торговые лимиты | NO CHANGE | Нет полномочий writeback |

**Важно:** автоматическое продвижение по стадии допускается только после дополнительного доказательства и отдельного ревью контракта. В текущей версии Gatekeeper не покупает данные и **не** активирует pipeline training/holdout при недостатке PIT. Нельзя представить ежедневную сводку как уже реализованный непрерывный collector с точными first-seen временами.

## 4. Как продолжать ускорение без риска и лишних циклов

Приоритет 1: независимый 24/7 сборщик actual first-received timestamps и venue/source identifiers (при необходимости отдельное согласование инфраструктуры); GitHub cron со случайной задержкой **не годится** как точный 5m collector.

Приоритет 2: единый точный исторический реестр `price + taker flow + OI` для BTC/ETH/SOL с `source_event_at`, `vendor_receipt_at`, `collector_received_at`, `decision_at`, единицами/ценами/масками пропусков, NO FUTURE JOIN, без новых платных API или обходов ограничений.

Приоритет 3: после доказанной достаточности данных — уже зафиксированный строгий протокол H1–H10, walk-forward, frozen holdout, family-wise Holm, минимум 60 полных независимых holdout дней, корректировка комиссии/спреда/проскальзывания/funding и сравнение с реальным историческим Детектором A либо `A_MISSING`. До этого результаты только exploratory и `EDGE_UNVALIDATED`.

## 5. Автономность и контроль

- GitHub Actions cron и R2 автоматизируют выполняемые серверные шаги без необходимости вручную продолжать чат. Но запуск cron может запаздывать; это НЕ доказательство market-time latency.
- Переход `SYNC_COMPLETE` не означает, что все старые GitHub артефакты существовали/архивированы. В рамках проверенного постоянного курсора доказана только непрерывная обработка новых run IDs.
- Каждая реальная ошибка GitHub/R2/API/ZIP/SHA или переполнение pagination остаётся явной ошибкой.
- Никаких новых подписок/оплат, ордеров, сигналов Детектора, изменений торговых лимитов, NAV, капитала, резервов и P&L. Android PASS к этим исследованиям не относится.

Ссылки: [PR #123](https://github.com/analiticprosp-ship-it/crypto-price-feed/pull/123), [PR #124](https://github.com/analiticprosp-ship-it/crypto-price-feed/pull/124), [исследовательский журнал #24](https://github.com/analiticprosp-ship-it/crypto-price-feed/issues/24).
