# HYPE derivatives shadow — validation log

Authority: SHADOW_RESEARCH_ONLY_NO_TRADES. This is a separate experimental PR; no NAV/P&L, orders, signals, or trading limits.

## First two independent GitHub Actions observations

- Run 40881590609: 2026-10-29T13:24:17Z. Hyperliquid OI 23250456.50 HYPE; OKX OI 1456298.3 HYPE.
- Run 40882017211: 2026-10-29T13:27:03Z. Hyperliquid OI 23265504.22 HYPE; OKX OI 1467909.2 HYPE.
- Both runs: Hyperliquid and OKX returned OK, with separate funding and 24h volume values.
- OI deltas over ~166s: Hyperliquid +15047.72 HYPE (+0.06472%); OKX +11610.9 HYPE (+0.79729%).
- This is a short observation interval; no conclusion about sustained trends, long/short direction, or price causality.
- Liquidations remain UNAVAILABLE. Venue funding periods are not yet normalized; 24h volumes use different units.
- Source timestamp/freshness enforcement and historical collection are still pending.

## Quality gates before scheduling

1. Three independent observations with both venues valid and source timestamps verified.
2. Validate exact instrument and contract units for every venue; reject stale data.
3. Normalize funding by its actual period and keep spot vs perpetual volumes separate.
4. Treat unavailable liquidations as missing, never zero.
5. Do not merge or activate scheduled workflow without review.

Artifacts:
- https://github.com/analiticprosp-ship-it/crypto-price-feed/actions/runs/40881590609
- https://github.com/analiticprosp-ship-it/crypto-price-feed/actions/runs/40882017211
