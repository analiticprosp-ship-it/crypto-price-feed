# 09L v0.8.7 — R2 expansion pre-registration, 2026-10-22 UTC
**SHADOW / RESEARCH ONLY. Locked BEFORE executing any new source-day replay.**

## Existing, already verified infrastructure
Reuse Cloudflare R2 private bucket `crypto-detector-history` and existing GitHub Secrets names `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET`. Do NOT create a new bucket, account or rotate keys. Archive new 09L objects **under `research/09l/v087/` only**, leaving `research/detector/`, `research/btci/` and `shadow/` untouched. Verify SHA-256 readback of each uploaded JSON; avoid overwrite (content-addressed immutable keys).

## Frozen expansion
Add exactly six publicly available *first-of-month* Tardis trade datasets **before looking at outcomes**:
- Bybit BTCUSDT: 2026-06-01, 2026-07-01, 2026-08-01.
- OKX BTC-USDT-SWAP: 2026-06-01, 2026-07-01, 2026-08-01.
These come in addition to Bybit 2026-09-01, Bybit 2026-10-01, OKX 2026-10-01, already labelled in 09L-AUTO v1.1. Do not quietly substitute unavailable source dates/venues. Monthly samples restricted to first calendar day and dates before current UTC day.

### Features and outcomes
Use unchanged existing `no_lookahead_v087.py`: eight frozen wall-clock UTC anchors (07:24:30, 08:32:30, 13:49:30, 14:19:30, 15:10:30, 15:49:30, 17:28:30, 18:38:30), input trades [-30s,t0), t0 as-of last trade <=2 sec old; forward outcomes at +30,+60,+300sec as-of last observed trade <=2 sec old. Different venue native sizes NEVER combined. Null means missing, never forward fill past 2sec. No use of post-event quote decrements as predictor features. Do NOT use future outcome labels to choose event dates/thresholds.

### Cohort guard
The six additional days are historical *retrospective replication*, NOT genuine unseen future OOS; hypothesis and v087 method already exposed to September/October data. For predictive claims, require later-than-lock forward-saved independent holdout and formal baseline comparisons. Avoid p-values based on within-day dependent windows and never claim P(cascade) or first-touch. Label readiness remains distinct from forecast skill.
Store a manifest per source-day, hashes and completeness status (SOURCE_UNAVAILABLE not filled), archive compact derived labels and provenance in R2 with SHA256 readback. No raw Tardis redistributed in public GitHub/R2 by this job.

### Optional CoinGlass Model2
Official aggregated heatmap Model2 `GET /api/futures/liquidation/aggregated-heatmap/model2`, only Professional/Enterprise (confirmed 2026-10-22). This study must NOT contact API or infer paid access unless licensed key `CG_API_KEY` is explicitly configured; never guess credentials. Already-existing R2 storage may host new **raw licensed PIT snapshots privately** once permitted; no raw heatmaps on public GitHub. Until then `PIT_SNAPSHOT_MISSING`, not historical zero clusters.

No modification to `00`, `01`, `01A`, `02`, `03`, `04`, `05`, `06`, `06C`, Spot/Futures, balances, NAV, P&L, trading limits or approved signals. Changes remain on independent research branch + isolated workflow and R2 prefix only.
