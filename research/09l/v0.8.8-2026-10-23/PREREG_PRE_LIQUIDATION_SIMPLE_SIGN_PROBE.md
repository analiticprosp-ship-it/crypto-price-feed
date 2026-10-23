# 09L v0.8.8D — PRELOCKED simple pre-liquidation signs exploratory probe
2026-10-23 UTC; commit BEFORE computing results of this probe. The first-message event labels have already been produced and viewed; **not prospectively blind**.

## Question
Can two **past-only** signs measured at t0−30s differ between event price-behaviour proxies? This is a sensitivity/feasibility check and cannot validate predictive accuracy or true market-maker absorption.

- Retain only the 8 precommitted source-date/venue cohorts Feb-May 2026. Choose exactly the 3 first-message anchors after 06:00/12:00/18:00 UTC, no event selection after seeing outcomes; never pool venues as 24 independent experiments.
- Primary decisive outcome **only** `CONTINUATION_PROXY` vs `OPPOSITE_REVERSAL_PROXY` at +300s. Report total excluded `LIMITED_CONTINUATION_PROXY` and `MIXED_OR_UNCLASSIFIED`; record missing covariates.
- Two simple FIXED Boolean indicators using ONLY preevent values: 
  1. `SIGNED_PRE_MOMENTUM_POSITIVE`: `momentum_pre_30s_bps × (+1 for buy-liquidation, −1 for sell-liquidation) > 0`.
  2. `SIGNED_PRE_FLOW_POSITIVE`: `flow_imbalance_pre_30s × (+1 for buy-liquidation, −1 for sell-liquidation) > 0`.
  A positive sign predicts the continuation proxy, non-positive predicts reversal. Never optimize thresholds/horizons after seeing outcomes; if value missing, mark test ineligible.
- Constant reference: always predict continuation, not adapted based on sample proportions.
- Report confusion counts, fractions, **per-calendar-day** rates, by-venue and disagreements; no Fisher/p-value across non-independent venues, no holdout designation, no training, no model fit, no claim `P(cascade)`. Any difference only suggests a candidate for true prospective testing and is *not* a confirmed predictive advantage.
- Historical source and time gaps, source SHA256 and candidate keys retained. If any input missing/invalid, fail closed. Output `RETROSPECTIVE_EVENT_SIGN_PROBE_NONPREDICTIVE` whatever the result.

CoinGlass Model2 PIT absent; no first-hit result can be derived from liquidation print. No Spot/Futures/NAV/P&L/limits/strategy changes.
