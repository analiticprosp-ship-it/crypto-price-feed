# 09L v0.8.2 — BTC liquidation cluster research: options/hedging expiry audit

**20 October 2026** • **SHADOW / EXPLORATORY / NOT_TRADEABLE**

## Data provenance
- Source transfer: user's frozen 09L v0.8 ZIP, original 40/40 SHA-256 file integrity passed in v0.8.1. Prior protocols/results v0.1–v0.7 unchanged.
- New: 30 UTC-dated *third-party* Deribit options-chain snapshots, 2026-09-20–2026-10-19, 28,694 contract-row observations (not independent market episodes).
- Source: https://github.com/pitspa/btc-vol-surface . Public repo labels underlying raw archive proprietary: **do not redistribute raw data**. User-facing ZIP only contains derived aggregates, source git blob SHA1 per day and a standalone replay script.
- Embedded UTC timestamps and git blob SHA1 logged. The source is **NOT** independently verified against the Deribit trading feed. An additional source publication-time audit is required for all dates before predictive PIT use.
- All quoted BTC index prices are **historical** snapshot fields, not live quotes.

## v0.8.2 observations (not prediction)
1. 2026-09-24 to 25: total option OI dropped 501,759.5 -> 350,462.0 contracts. 171,242.9 contracts in the 24-Sep snapshot expired on 25 Sep. Remaining/new-expiry OI net difference = +19,945.4. This is a cross-sectional accounting identity, **not observed option rolls or trading flows**.
2. Strike 85,000 OI at **all expiries**: 19,042.3 on Sep20 -> 10,910.6 on Oct19 (-42.70%); 10,505.1 on Oct13 -> 10,910.6 on Oct19 (+3.86%). Different horizons give opposite apparent sign because expirations matter.
3. Strike 85,000 / **Oct30 expiry**: 2,375.9 on Sep20 -> 3,807.0 on Oct19 (+60.23%). Oct13 -> Oct19 = 2,952.5 -> 3,807.0 (+854.5); call OI +849.4, put OI +5.1. Dealer net inventory and direction of hedge flows **unknown**.
4. Seven daily near-25-delta risk reversals, expiries Oct23/Oct30/Dec25, 21 quotes: all negative (25-delta Put IV > Call IV). Oct30 25Δ RR ranged from -4.52 vol pp (Oct13) to -3.25 vol pp (Oct19), with intermediate fluctuations. **Nearest liquid strike approximations**, not interpolated benchmarks.
5. No historical CoinGlass PIT heatmaps, signed dealer gamma, synchronized L2 + forced-order cascade labels. **NO P(first-hit), P(cascade), directional signal, or proof of option-driven price motion.**

## Causal & measurement restrictions
- CoinGlass maps are estimated liquidation leverage levels, not resting order book liquidity; models 1/2/3 cannot be summed.
- Options OI is not dealer gamma sign; examine equal-status long/short signed scenarios only.
- Expiry adjustments mandatory for every OI comparison. A big options strike does not prove a liquidation cluster exists or attracts price.
- For actual cluster lifecycle require immutable provider heatmap timestamp at inception, repeated observations, and real first-hit/negative cases.
- OOS blocked chronology, distance/ATR/trend baseline, placebo strikes, L2/OFI/spot-perp flow controls. Don't infer late heatmap features at earlier timestamps.
- No edits to MASTER, SPOT, FUTURES, NAV, capital, P&L, reserve, trading limits, or any action strategy.

## Planned v0.8.3 — not yet run
- Capture immutable *future* CoinGlass snapshots Model2 (venue/pair/model/window/provider time, raw SHA, cluster bins); validate Model1/3 independently.
- Deribit and OKX option chain with Greeks/quote quality and instrument normalization; event clock UTC with expiry schedule.
- Validate 1-minute L2 replenishment and forced liquidations on Tardis sample dates, then classify real cascade vs absorption, and disappearing clusters.
- Estimate only after true PIT + labels; otherwise mark NOT_TESTED.

**Writeback status:** This is an isolated research-only GitHub branch. **Not merged into `main` and does not modify any canonical trading file.** Full quantitative dataset and replay utility are provided as separate v0.8.2 conversation ZIP, not published raw-source content.
