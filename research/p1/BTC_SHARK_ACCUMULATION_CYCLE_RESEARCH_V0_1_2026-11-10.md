# BTC shark accumulation × P1 CYCLE / ONCHAIN_DEMAND — research registration v0.1
Date: 2026-11-10. Status: SHADOW_RESEARCH_CANDIDATE_NOT_ACCEPTED. No production/trading/NAV changes.

## Rationale
Santiment screenshot reports last-two-week collective balances +10,076 BTC (+0.49%) for 1–10 BTC addresses and +4,131 BTC (+0.10%) for 10–100 BTC addresses. These are screenshot-reported, NOT independently verified provider API observations; screenshot date, exact as-of and historical revisions require verification. Changes in address cohorts do not equal net spot purchases or unique investor entities.

## Ownership and routing
Primary owner: P1 / ONCHAIN_DEMAND. Secondary consumer: P1 / CYCLE (command «Цикл»), linked to existing P1_WHALES_CORRECTION_DEMAND_V1, P1_RECOVERY_QUALITY_V1, P1_UTXO_AGE_REGIME_V1, P1_REALIZED_CAP_RECOVERY_V1. Display in «Индикаторы». P3 crisis-event descriptive tests; P2 LONG and BTC72H research-only, no execution authority. No modifications to «Чистые активы», «Структура портфеля», P&L, Futures, trading limits, reserves, BTC72H frozen rules.

## Data specification
Separate cohorts 1–10, 10–100, 100–1,000, 1,000–10,000 BTC; raw supply held (BTC), absolute delta, percent delta and acceleration; windows 7/14/30 days for demand, 30/90/180 days for CYCLE. Record metric name, provider, UTC observation date, first_available_at, fetched_at, source revision/version, unit, address/entity definition, exchange exclusion policy, API response hash, coverage, last-good and missingness. Separate screenshot-reported from API-confirmed. Do not infer exchange/entity adjustment where provider does not support it. Address threshold migration, custody changes and exchange labels are confounders.

## Prospective and historical testing
Compare against predeclared baselines: BTC-only trend, existing P1 without shark feature, and shuffled/lagged placebo. Stratify by bear/bull regimes, drawdown, realized-cap slope, UTXO age, 2Y Treasury and liquidity where point-in-time available. Evaluate future BTC returns 3/7/14/30/60d, max adverse excursion, precision, false-positive rates, calibration, independent crisis episodes and overlap-adjusted confidence intervals. For CYCLE, focus on 30/90/180d and 4/13/26-week outcomes; prohibit overlapping observations from being treated as independent. Distinguish early accumulation with continued drawdown from genuine recovery. No hindsight thresholds or retrospective first-availability leakage. Predefine thresholds only after exploratory phase and freeze before OOS.

## Acceptance gates
1. Provider API access and exact metric definitions confirmed.
2. Screenshot values verified against date-stamped provider data or explicitly unresolved.
3. Historical coverage, revision behavior and PIT availability audited.
4. Out-of-sample incremental value versus existing P1 baselines shown with uncertainty and negative cases.
5. Only then propose promotion; until then NOT_ACCEPTED / NO_TRADES.

## Execution status
Research specification only. No live API collection, no backtest, no validated predictive edge, no automated ingestion or production deployment claimed.
