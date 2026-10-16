# BTC: пробная бесплатная выгрузка ончейн-активности — Coin Metrics Community

**Эксперимент без сервера и платного API.** Данные лицензированы Coin Metrics как **CC BY-NC 4.0**, с указанием источника и без коммерческого использования/перепродажи без разрешения.

По точному графику CryptoQuant BTC Moved After 1–3 Years (7D Avg.) и BTC Moved After 3+ Years (7D Avg.) бесплатной подтверждённой выгрузки нет. CryptoQuant API on-chain начинается с Professional. Не пытаться выдавать Coin Metrics за точную копию CryptoQuant.

Пробуем Community API с публичным ключ-независимым endpoint:
`https://community-api.coinmetrics.io/v4/timeseries/asset-metrics`.

Запрашиваем **каждый ряд независимо**, за последние 80 дней:
- `CDD` (Coin Days Destroyed): возрастно-взвешенная величина потраченных UTXO, **BTC-дни**, а не BTC 1–3 лет.
- `SplyAct1Yr`: запас BTC, активных в скользящем годовом окне, не суточный поток и не количество 1–3-летних монет.
- `SplyAct3Yr`: аналогично за 3 года, также не биржевой приток.

Если метрика не входит в бесплатный доступ — явный `NO_DATA`, причина ошибки отдельно. Нельзя автоматически считать неподдерживаемое поле нулём. Ни один из этих рядов не является Exchange Inflow/Outflow и не доказывает продажи или факт перевода на биржи. При частичном успехе сохранять только реально полученные и прошедшие проверки серии.

**Результаты после запуска**
- `research/btc-coinmetrics-community-proxy.json` только при наличии хотя бы одной реально наблюдаемой серии;
- `research/btc-coinmetrics-community-diagnostics.json` с отдельным статусом каждого запроса независимо от результата.

Это исследовательская проба: результаты **не импортируются** в `detector-onchain-context.json` (там строгий контракт CryptoQuant/Glassnode для других семейств метрик), `detector-candidates.json`, `market-summary.json`, `prices.json` или торговые правила. Не устанавливаются текущие LONG/SHORT, score, NAV, reserve, trading levels.

Исторические точки Community API не имеют сохранённых оригинальных времён их первой публикации. Поэтому загруженные старые значения **не считаются point-in-time достаточными для честного backtest** без истории vintage, задержки и возможных ревизий.

Источники:
- https://github.com/coinmetrics/data
- https://docs.coinmetrics.io/api/v4/
- https://gitbook-docs.coinmetrics.io/network-data/network-data-overview/supply/active-supply
- https://www.cryptoquant.com/apis

Запуск: **только ручной или одноразовый при включении кода в main**, без планового опроса и без API-ключей. Систематический сбор можно обсуждать после доказанного успешного доступа и оценки допустимости лицензии.
