# Detector SHADOW fusion — price / taker volume / OI

**Version:** detector-shadow-fusion-1.0. **Rights:** RESEARCH_ONLY. This file is not a trade signal, market price, NAV input, portfolio recommendation, Futures authority, strategy change, order request or validated forecasting model.

## Pipeline

- market-summary.json from OKX or verified fallback, with *fully closed* 15m candle lastClosedBar including t (open) and endMs (close), plus detectorFeatures and OKX observed OI/funding.
- detector-rest-flow.json from Binance or OKX fallback, with most recent **timestamped** closed 5m taker bars recentClosed5m. If provider is Binance but the price candle is OKX, **reject as a venue mismatch**. No automatic cross-venue fusion.
- scripts/detector_signal_engine.py fuses exactly **three consecutive 5m taker bars** for the SAME 15m candle, not the newest 15m volume irrespective of time. Previous three 5m bars provide a comparable baseline, not an extra independent evidence family.
- Output detector-candidates.json with source SHA256, event and publication times, gate reasons, missing values, LONG/SHORT qualitative hypotheses, per-family provenance, OI role, and no trading authorization.
- Optional Github Actions Build Detector SHADOW candidates scheduled at :12,:27,:42,:57 UTC, intended to follow the REST data schedule at :07,:22,:37,:52. Schedules may run late or skip; source-age and event-age gates are checked.

## Anti-leakage and freshness

1. Both source generatedAt timestamps must be timezone-aware UTC, no more than 45 minutes old. Current closed price bar must have true 15-minute-aligned t, endMs=t+15m, detectorFeatures.sourceBarClosedAt=endMs, and close no more than 35 minutes old.
2. Latest taker observation must have recent closed 5m timestamp and identity compatible with market-summary.json; never assume OKX and Binance flow are interchangeable.
3. Three 5-minute taker bars must cover precisely [price.openMs, price.closeMs). Duplicate, missing, invalid quantity, future or non-contiguous bars -> NO_DATA; no interpolation and no false zero.
4. Source publication must be no earlier than observed price bar end. Late OI observations must never be silently backdated.
5. At best OI with truly aligned 15m change can be a separate observation, not proof of the direction of new positions. 1H OI and funding are context.
6. Family grouping: price bars + RS + candles + sweeps => PRICE_STRUCTURE; taker buys/sells, imbalance, delta and shift => TAKER_VOLUME. OI is separate but correlated. **Not statistically independent evidence**; no score implying independent proof.
7. Experimental candidate heuristics: directional close or reclaim/reject on the closed bar together with a substantial taker-imbalance change, or opposing taker aggression combined with price resilience/weakness. Early candidates are labelled EARLY_CANDIDATE_SHADOW, never TRIGGER_CONDITIONAL. A missing bar or mismatch -> NO_DATA.
8. This engine **does not obtain or authorize system prices**, create entries/stops/targets, change ACTION_MAP, Spot/Futures canons, NAV, reserves, capital or leverage. Спекуляция remains the sole futures decision gate.

## Pilot and acceptance

- Run regression tests (anti-lookahead, exact alignment, duplicate/missing bars, venue identity, stale inputs, OI availability, LONG/SHORT symmetry, no trading permission).
- After first scheduled run check coverage.fullyAligned, coverage.unavailable, coverage.shadowCandidates and each reason. CI passing is **not** proof live candidate features are populated.
- Save input hashes/availability, compare forward return and adverse excursions vs Спекуляция baseline on identical periods, walk-forward out of sample including costs, fees, slippage, multiple testing and market regimes. Until then: EDGE_UNVALIDATED.
- Preserve current feeds and workflows; new engine creates only a separate read-only research artifact.
