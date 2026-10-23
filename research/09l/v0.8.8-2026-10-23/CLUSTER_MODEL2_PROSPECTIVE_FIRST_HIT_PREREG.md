# 09L v0.8.8C — prospective first-hit of CoinGlass Model2 clusters, PRE-DATA protocol
2026-10-23 UTC — **FROZEN DESIGN ONLY / PIT NOT AVAILABLE**. No inference from retrospective exchange prints.

## Objective
At a given UTC capture instant `t0`, does a genuinely *previously saved* Model2 BTC liquidation heatmap provide incremental information about (i) the **first** reached price zone above/below spot within an independently specified horizon, and (ii) after touch, continuation vs opposite reversal, over equidistant price-band controls? This is distinct from the v0.8.8 observed-liq print event study.

## Required PIT input gates
1. Raw Model2 response `data.y_axis, data.liquidation_leverage_data, data.price_candlesticks` from **licensed Professional/Enterprise** API stored privately in existing R2 `research/09l/pit/`, with request start UTC, end UTC, SHA-256, private readback success, vendor product/range and UTC capture. License must permit storage; no API key in public GitHub.
2. Each sample must have nonempty sorted positive y-axis, valid integer x/y indices and nonnegative finite modeled values; latest observed BTC price from live venue quote captured independently within **120 seconds of t0**; no same-source candle beyond t0. Avoid historical backfills presented as contemporary PIT.
3. For a heatmap consisting of x-axis bins, use **only data cells with the greatest valid x-axis index not exceeding the final candle index** as the frozen current modeled level field. Empty/mismatched grids => `PIT_FORMAT_UNDETERMINED` until provider schema verified on real licensed response. Never repurpose past/future heatmap colors as actual liquidations.
4. No first-hit outcome from ongoing unverified hourly REST snapshots. Future path requires continuous trade prices or independently retrieved minute OHLC with source capture and ordering provenance, from t0 forward. For within-one-minute ambiguity (both sides touched), label `AMBIGUOUS_ORDER`, exclude; never award a winner.

## Candidate selection frozen *before any live eligible model2 sample*
- Origin `P0`: independent last bid/ask midpoint from an exchange with source age <=120s, not source's modeled candle close. Use one stable venue definition per study; an OKX reference where available.
- Target candidate price band on each side within **0.50%–5.0%** of P0; fixed half-width **0.10% of P0** around y_axis level, non-overlapping with opposite side band. Candidate rank: **largest modeled liquidation value in last valid X column** on each side, tie-breaker closest to P0 then smaller absolute price. If no level on a side, `NO_BOTH_SIDE_CANDIDATES`.
- Frozen lookahead horizons **24h, 7d, 30d**; first-entry into either band is the outcome (upper-first, lower-first, both-in-same-resolution-interval ambiguous, neither censored). If initial price already in a band, ineligible. Strongest-value candidates are modeled and may not represent any true liquidation volume.
- Controls must be fixed at t0: an *equal-distance random-sign* placebo and *nearer of two levels* benchmark, and no comparison is made if price-series availability differs. Do not optimize thresholds on observed outcomes.

## After touch — NOT proof of maker absorption
Freeze signed continuation +300s from actual first band entry: `>=15bp` with max excursion `>=20bp` = `CONTINUATION_PROXY`; opposite signed five-minute `<=-10bp` = `OPPOSITE_REVERSAL_PROXY`; signed <=5 and > -10bp with no +10bp excursion = `LIMITED_CONTINUATION_PROXY`; otherwise mixed/unknown. Need timestamped price path, known book freshness and observed **actual** liquidation prints for mechanistic testing. A cluster disappears from subsequent estimated heatmaps is **not** proof that it was liquidated; model can regenerate.

## Validation
- Freeze full set of eligible t0 observations before reading future path. Group overlapping snapshots into temporal episodes; never treat adjacent 1h captures as independent Bernoulli samples. Strict future chronological holdout not seen during model tuning. Report missingness/censored outcomes, first-hit hit rate vs matched distance baselines, Brier/logloss only if a calibrated model is actually trained. Use days/weeks as unit for confidence intervals, avoid tiny window p-values.
- `PIT_SNAPSHOT_MISSING` and `CLUSTER_FIRST_HIT_NOT_RUN` are the only honest current statuses. The existing CoinGlass `CG_API_KEY` was NOT configured in verified prior preflight. Do not substitute public observed liquidation or inferred L2 depth for missing Model2 heatmap.

No trading permissions, no updates to 00/01/01A/02/03/04/05/06/06C NAV/P&L/reserve, Spot/Futures/limits/orders.
