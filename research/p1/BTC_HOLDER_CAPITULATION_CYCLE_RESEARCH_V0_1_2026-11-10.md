# BTC holder-count contraction / retail capitulation hypothesis — v0.1
Date: 2026-11-10
Status: SHADOW_RESEARCH_CANDIDATE_NOT_ACCEPTED / NO_TRADES

## Screenshot evidence (not API verified)
Santiment graphic dated Nov 9: Oct 16 peak ~59.99M total holders, decline 108.7K (~0.181%), ~59.88M total holders, exchange supply ~1.28M BTC, price ~$74,761. These are screenshot readings, not verified Sanbase API data. Total holders count means nonempty addresses, not unique people or retail capitulation. "First since August" unverified.

## Routing
Primary P1 ONCHAIN_DEMAND; secondary P1 CYCLE («Цикл»); consumers P1 RECOVERY_QUALITY, P1_WHALES_CORRECTION_DEMAND, P1_UTXO_AGE_REGIME, P1_REALIZED_CAP_RECOVERY; «Индикаторы» diagnostic; P3 crises research. Cross-reference draft PR #162 shark accumulation. No NAV/P&L/Futures/trading/BTC72H changes.

## Required data
Santiment holders_distribution_total and address counts per 0-0.001, 0.001-0.01, 0.01-0.1, 0.1-1, 1-10, 10-100, 100-1k BTC. Corresponding combined balances (BTC) and active counts where available. Supply on exchanges, exchange flows, labeling revisions, BTC price, realized cap, UTXO age and STH/LTH metrics. Record UTC observed_at, first_available_at, fetched_at, provider, metric version, source SHA, unit, coverage and missingness. Do not fill missing data with zeros.

## Hypotheses and test
H0: no incremental prediction after BTC trend and existing P1.
H1: shrinking small-address cohorts plus price stabilization and shark accumulation predicts better 7/14/30/60d recovery outcomes than baseline.
H2: shrinking address counts during ongoing price falls alone is insufficient. Negative cases essential.
CYCLE: 30/90/180d features, 4/13/26-week outcomes. ONCHAIN_DEMAND: 7/14/30d features. Pre-register price stabilization definition before OOS; report returns, max adverse excursion, false positives, time to recovery, overlapping-window-aware intervals, crisis strata and placebo tests. Confounders: address consolidation/splitting, bucket migration, custody and ETF changes, CEX labeling, historical revisions. No causal or retail identity claim.

## Gates
1. Verify screenshot date and values against timestamped API or mark unresolved.
2. Attribute 108.7K count reduction by balance cohort; verify "first since August" claim.
3. Check provider revisions and cross-provider exchange balance consistency.
4. Historical PIT and frozen prospective OOS tests.
5. Promote only after incremental validated evidence. Until then research-only NOT_ACCEPTED / NO_TRADES.

## Execution status
This is a research registration only. No automated ingestion, API history, backtest, deployment, or trade authorized.
