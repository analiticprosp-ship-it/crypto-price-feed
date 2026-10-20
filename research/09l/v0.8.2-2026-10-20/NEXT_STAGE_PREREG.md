# 09L v0.8.3 — proposed stage, NOT RUN (2026-10-20)
## Eligibility gates
- Heatmap attraction study: STOP if no true prior CoinGlass Model2 provider snapshot + future tracked cluster_id.
- Cascade study: STOP if no synchronized 1m/5m L2 and actual forced-liquidation executions (coverage must be documented).
- Dealer gamma: report BOTH conditional signs; if participant net dealer inventory missing, DO NOT label observed positive or negative net gamma.
- Deadline/expiry: use exact UTC exchange settlement time; distinguish expired contracts, added/removed listings, and continuing option instrument (expiry, strike, C/P).
## Predictions, when eligible
- First-hit upper/lower/no-hit/death at 7,14,21,30,60,90 days.
- Conditional cascade/absorption/reversal 5m,15m,1h,4h post-first-hit with pre-registered realized-liquidations and price-impact thresholds.
- Compare baseline distance/ATR/trend against incremental options OI/IV/skew and L2/order flow; matched negative cases and fake strikes.
- Chronological blocked OOS, no future leakage, report Brier/log-loss/calibration and clustered uncertainty.
## Stop policy
No numerical trading probability and no changes to Spot/Futures/NAV/P&L/reserve/trading canon until independently accepted evidence and separate user approval.
