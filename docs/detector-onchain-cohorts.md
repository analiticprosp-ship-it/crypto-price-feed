# Дополнение «Детектора»: BTC on-chain age cohorts / exchange flows — v1.0 SHADOW

**Статус:** `RESEARCH_ONLY`. Публичный скриншот не является проверенной числовой временной серией. Новых live-данных CryptoQuant к системе не подключено. Полномочия «Спекуляции», риск-лимиты и торгуемые цены НЕ меняются.

## Почему появилось дополнение

16.10.2026 пользователь предоставил график с заголовком **BTC Price vs. BTC Movement by Holding Age**, линиями **BTC Moved After 1–3 Years (7D Avg.)** и **BTC Moved After 3+ Years (7D Avg.)**. В конце видимого периода обе линии растут, особенно 1–3 года. График не подписан Exchange Inflow; из него нельзя заключить, что старые монеты отправлены на биржи или проданы. Он подтверждает направление изображения, но не удостоверяет экспорт из оригинального дата-сета, точную величину в единицах BTC/сутки, лаг или дату публикации.

### Строго разные источники

1. `BTC_SPENT_OUTPUT_AGE_1Y_3Y` / `BTC_SPENT_OUTPUT_AGE_3Y_PLUS`: старые UTXO пришли в движение по всей сети. НЕТ доказательства движения на биржи.
2. `BTC_EXCHANGE_INFLOW_AGE_1Y_3Y` / `BTC_EXCHANGE_INFLOW_AGE_3Y_PLUS`: только aged UTXO, поступившие на биржевые адреса по собственной методологии провайдера. Потенциальное предложение, НЕ исполненная продажа.
3. `BTC_EXCHANGE_INFLOW` / `OUTFLOW` / `NETFLOW`: биржевые потоки и баланс направления; Netflow = Inflow - Outflow и не считается отдельным независимым подтверждением.
4. Годовалый UTXO — это возраст выхода со времени последнего движения, не достоверная идентификация личности или стратегия конкретного инвестора. Старые монеты и StH/LTH по иным методикам не смешиваются.

**CryptoQuant документация:** [Spent Output Age Bands](https://userguide.cryptoquant.com/cryptoquant-metrics/utxo/utxo-bands-age), [Exchange Inflow – Spent Output Age Bands](https://userguide.cryptoquant.com/cryptoquant-metrics/exchange/exchange-inflow-spent-output-age-bands), [Data API terms](https://www.cryptoquant.com/apis).

Документация API CryptoQuant указывает, что бесплатный план даёт market data, но специализированный on-chain API начинается с Professional (и зависит от разрешения/плана). Поэтому у этого модуля **нет автоматической платной интеграции, ключей или подделанной бесплатной выгрузки**. Любое внешнее соединение и стоимость — только по отдельному решению.

## Источник данных и приёмка

- `research/detector-onchain-observations.json` — входной машинный контракт. Сейчас `observations: []`: отсутствие подтверждённых исходных данных, НЕ нулевой приток.
- Импортировать только документируемые provider export rows с названием метрики, точным объёмом BTC, scope, metric kind, ссылкой на оригинальную метрику, SHA256 выгрузки, UTC `windowStartUtc`/`windowEndUtc`, `availableAtUtc` (когда данные стали известны), `retrievedAtUtc`, rollingAverageDays и isExchangeTagged.
- Защита не утверждает криптографическую независимую проверку на основании введённого хеша: источник получает `PROVIDER_REPORTED_NOT_INDEPENDENTLY_REPRODUCED`. Исторически пересматриваемые метки биржевых адресов не допускают PIT-доказательства без сохранённых vintages.
- Не импортировать числа, считанные на глаз со скриншота. Скриншот может храниться отдельно как `QUALITATIVE_UNVERIFIED`, не проходя числовой gate.
- При несоответствии границ времени, отсутствии provenance, неверной биржевой области или TTL — `NO_VALID_OBSERVATIONS`/ `NO_DATA` и точная причина.
- Одним семейством остаётся `ONCHAIN_SUPPLY_MOVEMENT`. Отдельные Inflow, Outflow, Netflow и age-countries не дают несколько независимых голосов.
- Ончейн-данные пригодны для контекста BTC на горизонтах 1h/4h/1D (если выбранный провайдер/тариф реально их предоставляет); **не подтверждают закрытие конкретной свечи 15m**, если данные опубликованы позднее события.

## Реализация

- `scripts/detector_onchain_context.py` создаёт `detector-onchain-context.json` с исследовательскими метриками, раздельными областями данных и `sourceStatus`.
- `scripts/detector_signal_engine.py` добавляет в `detector-candidates.json` только компактное поле `onchainContext` со статусом, хешем источника, количеством проверенных записей и `noEffectOnCandidateRanking: true`.
- Workflow `Build Detector SHADOW candidates` при очередном запуске публикует оба файла; **не требует сервера, оплаченного API или кошелька**.
- LONG/SHORT семейства price/taker/OI, список кандидатов и их правила не изменяются. Схему текущих котировок `prices.json` и торговые ограничения не менять.

## Отдельный следующий шаг

Если появится правомерный машинный экспорт CryptoQuant/Glassnode, добавим 7-дневную историю с `available_at`, сохранением ревизий и проведём OOS/ablation. Только после этого можно проверять, улучшает ли BTC age-flow предупреждение об избытке предложения и не просто повторяет ценовые и taker показатели.
