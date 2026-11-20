# Последнее обновление: 5 ноября 2026

Актуальный отчёт: `continuation_20261105/REPORT.md`; текущая исследовательская передача: `continuation_20261105/P3_P1_HANDOFF_V5.json`, статус `SHADOW_RESEARCH_CANDIDATE_NOT_ACCEPTED`. Входы FTX восстановлены из полного архива и сверены по хешам. Новый `reproduce_ftx.py` воспроизводит четыре исходных результата из компактных оригинальных USD-строк без полного архива; проверен также минимальный состав PR. H1–H3 остаются неподтверждёнными, revised history не превращена в PIT. Новых рыночных наблюдений нет.

Из каталога, содержащего P3, с новыми путями результатов:
```
python P3/continuation_20261105/reproduce_ftx.py --output-dir /tmp/p3-ftx-replay-1105
python P3/continuation_20261105/audit_readiness.py --output /tmp/p3-readiness-1105.json
```
В репозитории заменить `P3/` на `research/p3-infra-crises-20261101/`. Полный прежний скрипт `phase_uncertainty.py` сохранён без изменений. Предыдущие ограничения и результаты ниже остаются историей.

## Обновление от 2 ноября 2026

Актуальный отчёт: continuation_20261102/REPORT.md. Передача P1: continuation_20261102/P3_P1_HANDOFF_V4.json. Binance +72H закрыто; прежние PENDING-статусы сохранены как история. 80 raw SHA проверены, 1440 часовых свечей, 70 endpoints. Funding после31Oct неполно: November404/API451. H1-H3 не валидированы.

После распаковки из каталога, содержащего P3:
```
python P3/continuation_20261102/analyze_primary_spot.py
python P3/continuation_20261102/analyze_primary_funding.py
python P3/continuation_20261102/phase_uncertainty.py
```
Python3,pandas,numpy,matplotlib. Расчёты offline. Предыдущие исследования и входы сохранены. PR159 draft/unmerged; SHADOW / RESEARCH ONLY. Финансовые книги и торговые правила не менялись.
