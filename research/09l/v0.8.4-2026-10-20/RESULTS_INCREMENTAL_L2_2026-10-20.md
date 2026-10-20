# 09L v0.8.4B–D — микроструктура BTC, 20 октября 2026 (RU)
**Статус:** SHADOW / exploratory historical mechanics / **NOT_TRADEABLE**, без изменений канона. Ничего не пересчитывалось задним числом в 09L v0.1–v0.8.3; новый event-time метод записан отдельно, не заменяет прежний minute-end метод.

## Что действительно исполнено
1. **v0.8.4B** — полный повторный разбор 4 Tardis исторических потоков Bybit BTCUSDT 2026-10-01: 526 BTCUSDT наблюдений ликвидаций, 1,475,829 сделок, 1,311,333 котировок и 1,562,205 снимков верхних пяти уровней. Все входные gzip SHA256 совпадают с архивами v0.8.3; 8 прежних, уже выбранных событий. При привязке к первой наблюдаемой ликвидации в минуте 07:24 SELL получено −28.7645 bp за 300 сек и ≥20 bp продолжение; при прошлой привязке к минутной цене было −3.9949 bp и такого продолжения не было. **Определение нулевого времени материально меняет вывод.** Другие три события не достигли 20bp в сторону ликвидации: 08:32 SELL +4.3371 bp, 17:28 BUY −1.3317 bp, 18:38 BUY −14.7619 bp. Разные anchor/price definitions нельзя складывать или усреднять как один тест.
2. **v0.8.4C** — источник incremental L2 доступен через GET 200, несмотря на HEAD 404; схема на восемь колонок подтверждена. Не называем HTTP HEAD 404 отсутствием данных.
3. **v0.8.4D** — полное реконструирование incremental L2 за тот же день: **26,324,148 строк**, исходный архив 139,683,883 compressed bytes (SHA256 \`f8f65353fa369d98e1a4ae990dc42eb21cea8dda16b9cb941c3e92d64daefa53\`), 0 невалидных строк, 0 нарушений монотонности local_timestamp, 2 снимка-сброса, 13 строк до первичного снимка отброшены. **96/96 совпадений объёмов** reconstructed vs supplied top5 — 48 точек * bid/ask; это проверка реализации на ДАННЫХ ТОГО ЖЕ ПРОВАЙДЕРА, не независимая биржевая аутентификация.

## Сопоставление top5 и фиксированного ±25bp price grid
At each case t0: first actual observed liquidation; support side = bid on long SELL, ask on short BUY; top5 depth baseline t0-1 sec, follow-up t0+30 sec. Gross increments/decrements are sums of positive/absolute negative changes in updated absolute L2 quantities (excluding snapshot resets), not identified new makers/cancels/fills.
| Event UTC | Side | top5 support Δ, % | Fixed-band gross increase | Fixed-band gross decrease | Net +/− |
|---|---|---:|---:|---:|---:|
| 07:24 | bid, SELL liquidation | −56.653 | +1481.772 | −1478.771 | **+3.001** |
| 08:32 | bid, SELL liquidation | +419.683 | +2709.378 | −2724.284 | **−14.906** |
| 17:28 | ask, BUY liquidation | −81.026 | +2740.823 | −2757.416 | **−16.593** |
| 18:38 | ask, BUY liquidation | −92.837 | +1794.966 | −1809.402 | **−14.436** |
The moving top5 and fixed-grid quote-size turnover answer different measurement questions; neither by itself proves absorption. In particular, large top5 growth at 08:32 coexists with a slightly negative fixed-grid net change. Even the net change can reflect price movement, full-book level updates, and fills. **No order-level maker identity or cancellation-vs-execution decomposition exists in these files.**

## Source QA / failure gates
- Tardis public first-of-month free samples, capture-time \`local_timestamp\` UTC µs, historical only. Full source URLs, compressed checksums/byte counts and row quality in \`derived/bybit_2026-10-01_event_time_casebook.json\` and \`derived/bybit_2026-10-01_full_l2_fixed_band.json\`. No raw vendor source redistributed.
- Valid top5/book + trades + liquidation source: **YES**. Independent observed real-liquidation-message windows: **YES**, four cases only. True controls: **NO**, four minutes without observed messages cannot prove absence of actual liquidation. Full historical PIT CoinGlass cluster: **NO**; verified cluster first touch/cascade: **NO**. Dealer signed inventory: **UNKNOWN**.
- **No inferential test**, no predictive calibrated probability, no lift score or causality. Single selected first-of-month day + event selection on realized liquidation size cannot generalize to other dates.
- Irregular quote sampling and 2s freshness applied, no future quotes/book assigned to past t. 1s sensitivity needs separate extra computation; not claimed run.
- Neither option contract OI nor sign-less gamma from prior study proves hedging at these intraday moments.

## Next 09L v0.8.5 — proposed, NOT RUN
Pre-register trade-by-trade L2 change matching at *same price* with multiple latency windows (0–50ms, 50–200ms, 200–1000ms); partition decreases into **potentially execution-related vs unassigned**, not unconditional cancels. Aggregate event times at 1/5/15/60/300s and quote replenishment hazard, uncertainty for identity matching; require samples across dates/venues and predeclared controls, then chronological independent test; bring options/expiry only if pre-event PIT available. Capture provider CoinGlass model2 **from now forward** for actual cluster lifecycle. No new trading rules without independent acceptance.

## Research-only verified writeback
Remote branch \`research/09l-v08-4-20261020\`. Exact study files:
- \`EVENT_TIME_PREREG_2026-10-20.md\`
- \`bybit_event_time_v084b.py\`
- \`derived/bybit_2026-10-01_event_time_casebook.json\`
- \`INCREMENTAL_L2_PREREG_2026-10-20.md\`
- \`bybit_full_l2_v084d.py\`
- \`derived/bybit_2026-10-01_full_l2_fixed_band.json\`
- this report.
No merge to \`main\`, no modifications of 00/01/01A/02/03/04/05/06/06C, NAV/P&L/Futures/trading limits.
