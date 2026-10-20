# 09L v0.8.5 — real Bybit BTCUSDT trade–L2 pairing result (2026-10-20)
**STATUS: MATCHING_EXPLORATORY_COMPLETE; SHADOW ONLY, NOT_TRADEABLE.**
Replayed historical Bybit 2026-10-01 Tardis public free sample: 1,475,829 trade rows + 26,324,148 incremental L2 rows, same source compressed SHA256 as v0.8.4. No invalid source rows, two snapshot resets, 13 pre-snapshot rows skipped, zero local-time reversals; recomputed 30-sec fixed-band quote change totals match frozen v0.8.4 exactly.
This is a **quote-size reduction ↔ aggressor trade temporal association proxy**, not uniquely identified executions, order cancellations or maker hedges. Frozen v0.8.4 event anchors (4 observed liquidation events + 4 high-trade minutes without recorded liquidation message). Same exact price, bid decrease ↔ taker SELL, ask decrease ↔ taker BUY. Greedy non-reusable amounts, disjoint absolute capture-time buckets 0–50, 50–200, 200–1000ms. Independent side-flipped placebo. Same historical UTC day, no OOS.

## Aggregates, raw source quantity (do not call USD)
| Group | Decreases in fixed ±25bp band | Correct matching ≤1000ms | Flipped-side placebo | Shares correct/placebo |
| --- | ---: | ---: | ---: | --- |
| Four observed liq windows | 150,152.929 | 4,043.790 | 1,681.347 | 2.6931% / 1.1198% |
| Four no-message control windows | 133,717.134 | 1,906.440 | 999.041 | 1.4257% / 0.7471% |
| All eight windows | 283,870.063 | 5,950.230 | 2,680.388 | 2.0961% / 0.9442% |

In liquidation windows **only**, correct match volume by disjoint latency: <=50ms 2,349.950; additional 50–200ms 431.186; additional 200–1000ms 1,262.654. Large unpaired volume is **NOT proved cancellations**, and side-correct advantage also appears in the control windows: association is generic microstructure and does NOT show incremental ability to predict a liquidation cascade.
Support-side comparison in 4 liquidations: 07:24 SELL/bid correct 4.7993% vs placebo 1.8919%; 08:32 SELL/bid 3.6264% vs 0.7906%; 17:28 BUY/ask 1.7794% vs 0.9478%; 18:38 BUY/ask 2.0852% vs 0.7568%. Event-time forward returns inherited from v0.8.4; not recalculated or reclassified.

## Source files & clock gates
- Script `bybit_trade_l2_match_v085.py`, pre-run frozen `PREREG_LOCKED.md`.
- Complete numeric audit incl both sides, all 8 events and provenance hashes: `derived/bybit_2026-10-01_price_time_trade_l2_matching.json`.
- Source schema https://docs.tardis.dev/downloadable-csv-files/data-types.md and Bybit feed caveats https://docs.tardis.dev/historical-data-details/bybit.md ; data clock `local_timestamp` (message arrival), no order-level identifiers. Different WebSocket feeds can have variable capture latency. Book can omit RPI quotes. Quantity shared-unit multiplier has not been independently verified.
- A same-price 0–1000ms association **does not prove actual trade↔book linkage**; parsing full venue depth may nevertheless miss kinds of liquidity and updates. No independent chronological holdout or uncertainty estimates.
- No historical as-of CoinGlass heatmaps, no verified cluster first hit, no signed net dealer gamma, no market maker identities, no causal claims and no `P(cascade)` or `P(first-hit)` estimates.

## Proposed v0.8.6 — not run
Pre-register independent monthly-free dates / another venue (without picking events by realized response), align trades with L2 and liquidation reports, test latency sign and +5s/+10s clock-shift placebos, narrower fixed ±5/±10bp bands and equal session/volatility controls. Only then consider true PIT heatmap cluster lifecycle, signed gamma scenario gating, later held-out OOS.
**WRITEBACK:** isolated branch `research/09l-v08-5-20261020` only; no merge or 00/01/01A/02/03/04/05/06/06C, Spot, Futures, NAV, P&L, capital, reserve, trading limits or orders changed.
