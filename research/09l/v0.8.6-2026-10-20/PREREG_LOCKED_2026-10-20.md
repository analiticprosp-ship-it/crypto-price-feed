# 09L v0.8.6 — Independent date/second venue robustness, PREREG LOCKED (2026-10-20)
Status **SHADOW_RESEARCH_ONLY**; no pricing/trading authority and no editing old results. Frozen BEFORE downloading new first-of-month historical data. New test explicitly **holdout-style exploratory** (different historical days and venues), NOT a formal predictive OOS confirmation.

## Pre-selected sources (do not substitute on results)
A. **Bybit** linear BTCUSDT, 2026-09-01 UTC, source Tardis `trades`, `incremental_book_L2`; `liquidations/PERPETUALS` separately for descriptive incident counts.
B. **OKX Swap** linear BTC-USDT-SWAP, 2026-10-01 UTC, Tardis `okex-swap` `trades`, `incremental_book_L2`, grouped `liquidations/PERPETUALS` separately. Different exchange and contract; raw size unit cross-venue conversion forbidden pending multiplier validation. No fallback to inverse BTC-USD-SWAP; source unavailable if not supported.
Both are public first-day-of-month **historical sample dates**, not contemporaneous Oct20 snapshots. All Tardis capture timestamps are `local_timestamp` microseconds UTC, not exchange execution ordering. Daily provider gzip SHA256 + row count must be recorded. No raw data committed/rehosted.

## Independent event selection
Primary, fixed UTC clock windows independent of NEW realized liq and price response: 07:24:30, 08:32:30, 13:49:30, 14:19:30, 15:10:30, 15:49:30, 17:28:30, 18:38:30. These times are transferred from earlier v0.8.5 *selection* and therefore NOT randomly selected; for new date and venue no response lookahead is used. Each window: quote-size decreases [-30,+300] seconds; trade messages [-31,+301] seconds. Event-mid proxy: most recent trade price at or BEFORE t0, at most 5s old. Band fixed t0 price ±25 bp for **both sides**, no moving band or post-event anchoring. If missing mid => EXCLUDED_MISSING_PIT_PRICE, no forward-fill beyond 5s.
Secondary liquidation-focused descriptive anchors: first BTC liquidation message at/after 06:00, 12:00, 18:00 UTC, if feed exists; one anchor per bucket and no selection based on size or future market outcomes. Keep this secondary subset explicitly separate from primary 8 windows. Missing liq feed does not undermine price-time fixed-window computation but blocks liquidation event analysis.

## Frozen matching
- Tardis incremental L2 amounts are *absolute size at level*, snapshot transition resets book; ignore pre-first-snapshot and snapshot changes, update in capture order. Each decrement >0 inside fixed band on bid is paired to aggressor SELL same exact price; on ask to aggressor BUY same price. Reverse mapping is primary placebo.
- One-to-one capacity-constrained greedy nearest temporal matching by *absolute timestamp lag*, no trade size reuse within each mapping; disjoint windows [0,50]ms, (50,200]ms, (200,1000]ms. Report each and combined, plus total changed quote-size denominator and unmatched (not asserted cancelled).
- Timestamp shift placebo +5000ms on correct-side trades (same prices) as falsification/sanity; recompute in independent capacity-constrained pass. Same price and distance matching with shifted timestamps. No posthoc tuning of windows.
- Compare **within-venue percentage** share correct versus flipped versus shifted. Do not compare absolute raw volume across exchanges.
- No merge of distinct instruments, no true zero-liquidation controls, no independent OOS forecast metrics. Sensitivity of pass criterion: primary *descriptive* directional positive correct vs flipped for fixed windows, and correct vs shifted. Assess number of windows passing; no p-value because temporal dependence and small n. Compare with old v0.8.5 only acknowledging anchor- and date-selection differences.

## Stop/QA
Reject any source with missing required fields, negative or non-finite quantities, invalid time ordering, compressed-file cap 450MB, missing valid initial L2 snapshot, conflicting symbol or date. `SOURCE_UNAVAILABLE`, `DATA_INCOMPLETE`, `QA_FAIL` honestly. Grouped liquidation source may be unavailable, but may not fabricate cases. No options dealer signed gamma/heatmap cluster first-touch without PIT provider.
Do not change 00/01/01A/02/03/04/05/06/06C, Spot, Futures, NAV, capital, P&L, reserve, trading limits, orders or accepted historical research. Only commit research files on branch `research/09l-v08-6-20261020`, no main merge.
