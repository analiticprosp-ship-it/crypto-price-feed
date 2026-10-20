# BTCI Research Engine v0.1 — независимый научный контур

**Дата:** 2026-10-20. **Режим:** RESEARCH_ONLY, никакой торговой власти.

## Ключевой статус

Система содержит четыре исследовательских конвейера: audit, h41, treasury, mvrv. Запускается параллельно, сохраняет отчёты и исходные HTML/CSV-кандидаты (если их удалось получить); агрегатор показывает WARN и пропуски. Предварительная история BTCI v8.18d7 **не меняется**: исходные 684 даты и 31 MVRV-свидетельство, прежние отрицательные эксперименты, даты 13/26/52 недель.

**Важно:** текущий staging-branch в репозитории crypto-price-feed не содержит долгоживущих двух исторических fixtures; временно читает родительский GitHub Actions artifact (который истекает). До развёртывания в самостоятельном исследовательском репозитории расписание GitHub Actions НЕ действует: schedule запускает workflows только с ветки по умолчанию. Новые результаты не пишутся в main, R2, Spot, Earn, Futures, NAV, MASTER, Detector.

## Развёртывание в новом, отдельно изолированном GitHub-репозитории

1. Создать **отдельный** репозиторий `btci-research-engine` (желательно private). Не импортировать торговую main.
2. Скопировать содержимое каталога `STANDALONE_REPOSITORY/` из переносимого ZIP в корень нового репозитория: `.github/workflows/btci_research_engine.yml`, `research_engine/*.py`, `fixtures/*.zip` / `fixtures/*.json`.
3. В репозитории по умолчанию должна быть ветка `main`. Сверить SHA `fixtures/BTCI_v8171_684_MACRO_ORIGINAL.zip` и `fixtures/BTCI_684_UST_H41_MVRV_SOURCE_ONLY_JOIN.json` с файлами `SHA256_MANIFEST.json`.
4. В Actions открыть «BTCI RESEARCH ENGINE v0.1 — isolated RESEARCH ONLY», выполнить вручную с `mode=offline`; потом `mode=smoke`. Обязательно сверить артефакт `btci-engine-summary-...`.
5. После этого GitHub cron дважды в неделю: понедельник и четверг, 07:23 UTC; возможны задержки GitHub schedule. `workflow_dispatch` предусмотрен для запуска вручную.
6. **Ограничение хранения**: GitHub Actions artifacts сохраняются 45 дней; для многолетнего исследовательского архива потребуется отдельное долговременное хранилище исключительно под research, с отдельными credentials и подтверждённой записью. Не заявлять долговременную сохранность без него.

## Инварианты

- SHA исходного отчёта BTCI v8.17.1: `539bcc1817a2120287497c2814d0344aae5d62714b4f35a36f30c2425e5d3091`.
- SHA неизменного ZIP оригинала: `9cf12204ec0820de4f9303e17a47f9ea3318c089a1e19a1b9892c595e43fb726`.
- SHA `fixtures/BTCI_684_UST_H41_MVRV_SOURCE_ONLY_JOIN.json`: `82a66ae9a7f2ca3c5d21df10c178edde48567387b3f04e12f8b74566b3b65d92`.
- 684 исходные даты, MVRV=31 witness, H4.1=680/684, UST=684/684, 14 изначально исключённых календарных воскресений не добавляются.
- Вся исходная база UST-PIT-07 — `SOURCE_ONLY_CANDIDATE`: 0 строгих PIT-допусков, пока не доказана первая дата публикации/историческая версия.
- GitHub Actions «SUCCESS» означает успех выполнения кода, **не** пользу прогноза.
- Нельзя переписывать отрицательные результаты, предрегистрации, P&L, NAV, торговые сигналы и капитал.
- Архивные значения, выгруженные в 2026 году, никогда не повышаются до строго PIT-аттестованных автоматически.

## Что пока не реализовано

Это проверяемый MVP, а не завершённый автономный научный цикл: H.4.1 ищет первичные страницы для четырёх пропусков, Treasury перепроверяет два архивных месяца, MVRV смотрит источник-кандидат, а полный исторический архив остаётся неизменным seed. Проверка первых версий публикаций, автономное пополнение долговременного research-хранилища, детальный поиск GHArchive/Wayback, автоматическое ретестирование 13/26/52-недельных моделей требуют отдельной научной предрегистрации/адаптера. Пока ни одна новая модель не обучается.

## Проверка локально

```bash
python -m pip install "requests>=2.31,<3" "beautifulsoup4>=4.12,<5"
python research_engine/btci_engine.py --track audit --mode offline --out smoke
python research_engine/btci_engine.py --track h41 --mode offline --out smoke
python research_engine/btci_engine.py --track treasury --mode offline --out smoke
python research_engine/btci_engine.py --track mvrv --mode offline --out smoke
python research_engine/aggregate.py smoke combined
```

Финальный README и переносимый пакет полностью воспроизводят файлы скрипта, workflow и эталонной базы; собирать модуль из прежних объяснений вручную не требуется.
