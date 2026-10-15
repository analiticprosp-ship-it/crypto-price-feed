# Detector stage 2 — deployment and verification runbook

STATUS: deployment-ready package only, NOT an already running 24/7 service. Merging code does not deploy it.

## Security and scope
- Only public Bybit V5 spot and linear trade topics and linear allLiquidation; no keys, accounts, wallets, trading or order endpoints.
- Default SOLUSDT,SUIUSDT, at most four validated USDT instruments. No incoming ports exposed.
- Persists local SQLite (90m rolling) and local JSON snapshot in named Docker volume. Runs as non-root and read-only root FS.
- Does NOT modify prices.json, market-summary.json, Spot/Futures canonical holdings, NAV, permissions, risk, strategy or orders.

## Host needed
Choose an always-on Linux VM/VPS with Docker Engine and Docker Compose v2, durable disk, synchronized UTC clock and working outbound Bybit public WebSocket connectivity in that provider region. GitHub Actions cannot maintain continuous stream. Select and approve the host/provider and hosting cost before setup. No hosting service is provisioned by this pull request.

## Startup (on a designated host, once approved)
```bash
git clone https://github.com/analiticprosp-ship-it/crypto-price-feed.git
cd crypto-price-feed
docker compose -f compose.detector-stream.yml config -q
docker compose -f compose.detector-stream.yml up --build -d
docker compose -f compose.detector-stream.yml logs -f --tail=80 detector-stream
```

To change selected pairs, set DETECTOR_SYMBOLS=SOLUSDT,SUIUSDT consistently for the service and health checker.

## Distinguish liveness from readiness
```bash
docker compose -f compose.detector-stream.yml exec -T detector-stream python scripts/check_detector_microflow.py --mode liveness --file /data/detector-microflow.json --symbols SOLUSDT,SUIUSDT
docker compose -f compose.detector-stream.yml exec -T detector-stream python scripts/check_detector_microflow.py --mode readiness --window 15m --file /data/detector-microflow.json --symbols SOLUSDT,SUIUSDT
```

- Allow at least 15 complete minutes of observed flow before requiring the 15m readiness gate.
- Fresh JSON (liveness) DOES NOT prove working public subscriptions (readiness). Silent topics return NO_TRADE_EVENTS_UNVERIFIED, not a synthetic zero.
- Readiness is source/data quality only, NOT a price, trade signal or permission to trade.
- Compose marks an unhealthy container but restart:unless-stopped alone does not automatically restart an unhealthy running process. Production host needs separate alerting/monitoring.
- CI checks mock inputs and syntax, NOT real Bybit region access or runtime trade message rates.

## Acceptance: sustained 24-hour observation
Monitor snapshots and logs across a 24h pilot, including source timestamps, reconnect gaps, per-market/per-symbol trade counts, 1m/5m/15m quality, liquidations and deduplication collision risk. Verify broker-side liquidation side semantics and compare accessible exchange aggregates where truly comparable. Gaps remain null; no backfill or synthetic zeros.

## Publishing is a separate subsequent decision
NO remote publisher is configured; files stay on host. After sustained quality acceptance, agree on a secure destination, credentials/permissions and a new atomic read-only detector-microflow.json with hard TTL. Never overwrite prices.json. Only then may Detector consume public trade/liq signals as one evidence family, while Futures execution remains solely within Spекуляция and its authorization rules.
