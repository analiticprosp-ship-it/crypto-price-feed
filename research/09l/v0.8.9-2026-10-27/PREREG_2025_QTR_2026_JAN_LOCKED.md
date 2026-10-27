# 09L v0.8.9 — locked earlier-regime robustness cohort design · 2026-10-27
**Research-only / shadow; frozen BEFORE fetching any of these new cohorts.**

## Why
v0.8.7+0.8.8 includes 9 distinct 2026 first-of-month calendar days Feb–Oct; 17 venue×day datasets (123/136 complete fixed clock labels); 30 selected observed liquidation events across Feb–May+Oct; no consistent predictive edge. Need additional **distinct dates across earlier regimes**, not pseudo-replication of the same UTC minute on two exchanges.

## Pre-declared 10 new venue×day sources / five unique dates
Only public free-first-calendar-day Tardis.dev BTC historical data. For Bybit BTCUSDT and OKX BTC-USDT-SWAP choose exactly **2025-01-01, 2025-04-01, 2025-07-01, 2025-10-01, 2026-01-01**, no after-the-fact substitutions. 5 distinct new market days, 10 new venue-day cohorts, 8 clock-fixed anchor comparisons per cohort and first three eligible observed liquidation print events per venue-day. Intended added **80 fixed-clock raw opportunities**, 30 first-message event opportunities. Empty/invalid/unavailable source -> missing; do not relax QC or backfill from another day.

### Frozen measurements
Run **unchanged scripts** derived from v0.8.7 and v0.8.8:
- 8 exact UTC clocks 07:24:30, 08:32:30, 13:49:30, 14:19:30, 15:10:30, 15:49:30, 17:28:30, 18:38:30.
- Trades features strictly `[t0-30 seconds,t0)`; as-of t0 reference trade must be captured at or before t0 and <=2s old; forward price labels +30/+60/+300s at most 2s old. Never replace missing with guessed price.
- Observed liquidation messages: first BTC liquidation after 06:00/12:00/18:00 UTC session boundaries. BUY-liq indicates bought-back short; SELL-liq indicates sold long, as recorded by source. Observe 5min signed continuation and maximum same-direction excursion. Frozen classes from v0.8.8: CONTINUATION_PROXY iff 300s >=15bp and peak >=20bp; OPPOSITE_REVERSAL_PROXY iff 300s <=-10bp; LIMITED_CONTINUATION_PROXY iff -10bp<300s<=5bp and peak<10bp, else mixed. No real maker absorption inference.
- Retain native vendor trade amount units; never pool raw volumes across two venues.
- Compare v0.8.8 unchanged **simple signed past-30s momentum** and **signed past-30s aggressor flow** Boolean indicators to the constant-continuation baseline on **only** continuation/reversal proxy cases. No fitting, optimized thresholds, tuning based on these new outcomes or binomial p-values. Summarize accuracy BY CALENDAR DAY and venue; count missing/excluded. If a strategy succeeds some days but fails others, report both without cherry picking.

### Temporal interpretation / stopping conditions
All new days are **EARLIER than the 2026 test**; this is backward historical stress/sensitivity, **NOT** sealed chronological forward out-of-sample (prospective OOS requires data after the 2026-10-27 design lock). First-of-month sampling is biased, 10 venue/day cohorts not 10 independent market days, same-price-path overlaps across Bybit/OKX. The first liquidation event each session may be unrepresentative. Even positive result cannot validate P(cascade), returns or trading authorization.

### Cluster-first-hit hypothesis remains separately blocked
No licensed as-of numerical CoinGlass Model2 snapshots available. Existing Cloudflare R2 stores data but does NOT create genuine past heatmaps. No cluster position, birth/lifecycle or first-hit probability may be estimated from observed liquidation prints. R2 private existing `crypto-detector-history`, prefix `research/09l/v089`. CoinGlass API Pro/Enterprise key remains absent until **verified otherwise**; never buy subscription, invent key or contact endpoint unauthenticated.

### Evidence and immutable archival
Verify gzip SHA256 and captured UTC timestamps, and trade gzip hash SAME on independent clock and liquidation pipelines; require source statuses OK. Store only compact derived JSON in existing Cloudflare R2 with SHA256 readback, branch `research/09l-v089-historical-robustness-20261027`, write R2 receipt per cohort and report success only after real readback. Preserve prior negative 09L v0.8.7 and v0.8.8 results unchanged, and do not merge into `main`. No modifications to Spot/Earn/Tangem, Futures, 00/01/01A/02/03/04/05/06/06C, NAV, P&L, capital, reserves, orders, approved signals or limits.
