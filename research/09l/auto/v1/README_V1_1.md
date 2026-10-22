# 09L-AUTO v1.1 — deployed research-only collector and pre-event labels

**Activated and first tested 2026-10-22. SHADOW/NO TRADING.** State: `ACTIVE_BEST_EFFORT_HOURLY_PUBLIC_BOOK` and `ACTIVE_DAILY_RESEARCH_QA`. This is not a 24/7 WebSocket recorder.

## Deployment and verified runs
- Daily main-branch **scheduler only**: `.github/workflows/09l-auto-v1-daily.yml`, UTC `08:47`, checks out branch `research/09l-auto-v1-1-20261022`. Monthly Tardis first-day-of-month liquidation source audit, v0.8.7 as-of historical labels if not already registered, append-only source-quality/missingness health. No CoinGlass PRO key.
- Hourly main-branch **scheduler only**: `.github/workflows/09l-auto-v11-hourly-books.yml`, UTC minute `17` each hour, same research checkout. Does read-only public REST capture of Bybit BTCUSDT spot+linear and OKX BTC-USDT spot+swap. Each JSON has start/end/source timestamps, age QC, source SHA256 and derived bid/ask top5+25 native sizes. No API keys or orders.
- Research-only first-run pilot: `.github/workflows/09l-auto-v11-pilot.yml`. Every deployed action enforces staging only `research/09l/auto/v1/derived/` and pushes only to research branch. `main` has no new research calculations, only scheduled workflow definitions.
- Historical `09L v0.8.7` label readiness: eight predeclared wall-clock events per selected venue/date, features only from [-30,0) seconds, forward trade-price-as-of labels at +30,+60,+300 seconds. Strict 2s freshness cap with NULL not forward fabrication. In first archival pilot: Bybit Sep1 **6/8** all-horizon ready, 2 missing the +300s as-of price (15:49:30 and 17:28:30); OKX Oct1 **8/8**. L2 changes *after t0* from v086 are NOT future prediction features. No fitting, no cascade odds and no statistical claim.
- Live REST pilot: OKX spot and swap sourced; Bybit global endpoints were denied in GitHub US-hosted runner (HTTP access restrictions). Capture status explicitly records missing data; no attempt to evade provider controls. Bybit historical via Tardis remains available. Revisit data-collection region/authorization only with a compliant permitted environment.
- Health report: `health_report.py` daily health ledger includes captured hours **since activation**, per venue latest source status, v087 missing cases, true PIT missingness and `PREDICTIVE_LIFT_NOT_VALIDATED`.
- CoinGlass Model2: `PIT_SNAPSHOT_MISSING`, not available without approved Professional/Enterprise API access and separately provided **private** storage. Neither repository nor GitHub artifacts contain raw source heatmaps or secrets.
- Scheduled GitHub Actions can delay/skip runs; hourly snapshots are sparsely timed, no guaranteed every-hour uptime, **not continuous order-flow**, and cannot verify rapid 5-minute liquidation cascades between samples. Need compliant always-running VM/container with monitored WebSockets for true tick-level prospective capture. No speculative continuous capture statements.
- First-day Tardis sample is not a representative random set of market days; v087 14/16 ready labels from two original source days is **not** an independent chronological predictive validation. Future months locked by `PREREG_MONTHLY_HOLDOUT_EXTENSION.md`; absent samples are retried with append-only failure audits, never silently replaced.

## Hard write gates
Never write or merge into trading 00/01/01A/02/03/04/05/06/06C, futures positions, NAV, P&L, capital, reserves, Spot balances, trade orders, trade limits, approved signal engines. All 09L-AUTO derived artifacts clearly identify `SHADOW`. No user trading API keys.

## Useful files
- `collector.py` source availability, historic monthly liquidation messages, optional gated CoinGlass private PIT
- `live_book_sampler.py` as-collected hourly public top25 exchange snapshots
- `no_lookahead_v087.py` historical pre-anchor trades and labelled future price outcomes
- `health_report.py` independent reporting on source availability and sample sparsity
- `PREREG_V11_AND_087.md` / `PREREG_MONTHLY_HOLDOUT_EXTENSION.md` frozen methods
- `derived/live_snapshots/`, `derived/v087_labels/`, `derived/health/` append-only derived artefacts

**Research milestone:** v0.8.7 *label preparation* and AUTO v1.1 verified ingestion. **NOT:** proven predictive edge, proved liquidation-cluster attraction or authorised trading system.
