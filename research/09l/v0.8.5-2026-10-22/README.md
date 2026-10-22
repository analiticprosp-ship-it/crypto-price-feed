# 09L v0.8.5 — historical Bybit event-clock, completed 22 Oct 2026

**Status:** EVENTCLOCK_EXPLORATORY_COMPLETE / SHADOW ONLY. Existing v0.8.3 and v0.8.4 results remain unchanged; no main or trade-canon writeback by this study.

## Frozen source audit
Tardis Bybit 2026-10-01: liquidations (526 BTC rows), trades (1,475,829), quotes (1,311,333), top-5 order-book snapshots (1,562,205). All **four compressed SHA256 hashes are identical** to v0.8.3. Full provenance and per-event seconds, market orders, quote, top5 values, and missingness in [derived/eventclock_2026-10-01.json](derived/eventclock_2026-10-01.json). Reproduce with [remote_v085_eventclock.py](remote_v085_eventclock.py). [Successful GitHub Actions run](https://github.com/analiticprosp-ship-it/crypto-price-feed/actions/runs/39750073177).

## Prespecified historical windows (all returns in basis points)
| 2026-10-01 UTC | message side | previously v083 +5m from minute-close | v085 +60s from first message | v085 +300s from first message | observed messages +300s |
|---|---|---:|---:|---:|---:|
| 07:24 | sell | -3.9949 | -21.9056 | -28.7646 | 34 |
| 08:32 | sell | +23.5641 | -11.1621 | +5.2266 | 30 |
| 17:28 | buy | -6.1382 | +0.5775 | -1.3435 | 44 |
| 18:38 | buy | -38.6436 | +13.8804 | -14.7619 | 50 |

The 07:24 selected event moves from *not* showing 20bp directional extension by the old close-minute clock to **showing 28.7646bps sell-direction extension** by the prespecified event clock. This is an **anchor sensitivity result**, not evidence of a confirmed cluster cascade.

Four fixed high-activity controls yielded +5m returns +5.1663, +3.8019, +27.1337 and -14.9152 bps with zero **observed** Bybit liquidation messages in corresponding 5m windows. These controls do not prove actual liquidation absence and are not matched for volatility or session.

## Scope of interpretation
- t0 is local_timestamp of first **observed** liquidation message of the chosen side *within previously selected minute*. Not the earliest real liquidation or the first touch of a liquidity heatmap.
- Top-five order-book snapshots and one-tick BBO spreads cannot identify adds vs cancellations vs executed market impact; full incremental L2 is needed for OFI.
- No CoinGlass Model2 point-in-time cluster timeline; no option dealer signed inventory; no verified P(cascade | touch).
- Four realized-event minutes were selected retrospectively; this cannot calibrate prospective success rates.
- No futures orders, NAV, Spot, portfolio capital, reserves, canonical files or live trading authority modified.

## Next frozen research question
Expand to predeclared first-of-month Aug/Sept 2026, select liquidation events independently of future price returns; compare to prespecified activity-aware controls, using strictly as-of clocks and complete missingness. Dealer gamma only signed scenario stress bands until actual participant positioning data available. No retroactive modifications of this result.
