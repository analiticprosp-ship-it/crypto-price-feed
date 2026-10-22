# 09L v0.8.7 — retrospective baseline-vs-flow diagnostic, 2026-10-22
**STATUS: TEST COMPLETED; `NO_REPLICATED_INCREMENTAL_GAIN`; RESEARCH/SHADOW ONLY; no trading signal.**

## Summary and preregistration
Methods prelocked in `PREDICTIVE_COMPARISON_PREREG_LOCKED_2026-10-22.md` before fitting. The tested question is only whether prior 30s aggressive trade quantity imbalance improves BTC **forward price sign** predictions versus price momentum/volatility/trade count and venue flag; this is NOT a test of liquidation-cluster attraction, maker fills, or cascades.

Nine pre-existing source-date/venue derived JSONs, 72 clock-fixed cases, 5 distinct calendar dates. Primary +300 seconds: 62 eligible directional/complete-feature cases, **40 train** (June–August), **22 held-out retrospective** (September and October: 6 Bybit Sep, 8 Bybit Oct and 8 OKX Oct). Missing: 5 as-of price/clock failures, 4 prior-feature failures, 1 exactly flat return; no imputation. All nine inputs SHA256 catalogued and no raw Tardis data redistributed.

Constant-predictor baseline is training-set BTC-up prevalence with Laplace smoothing; baseline logistic uses strictly prior 30sec return/range/log trade count/venue; augmented logistic adds ONLY prior 30sec buy/sell volume imbalance. Same deterministic L2 regularization and training-only scaling. No post-event L2 updates used as predictive features. All models trained only on June/July/August. Both September and October outcomes were *already visible* during earlier 09L exploration, so this is **retrospective temporal holdout**, NOT sealed prospective OOS.

## Three frozen horizons (calendar-day-equal weighted Brier; lower is better)
| Horizon | Constant prevalence | Price + activity baseline | Price + activity + past trade-flow | Predeclared gate |
|---|---:|---:|---:|---|
| +30s (secondary) | 0.2613399 | 0.3294267 | 0.3342044 | FAILED |
| +60s (secondary) | 0.2475000 | 0.2984620 | 0.2934943 | FAILED |
| **+300s (primary)** | **0.2641723** | **0.2980572** | **0.2929874** | **`NO_REPLICATED_INCREMENTAL_GAIN`** |

**Primary 300s accuracy (22 venue/window predictions):** constant 11/22 = 50%, simple baseline 6/22 = 27.27%, augmented 6/22 = 27.27%. This is very weak directional performance on these dates and is NOT a statistically independent set of 22 outcomes (same BTC path shared across venues).

## Primary per-date and calibration details
| Calendar date | n venue/windows | Base Brier | Augmented Brier | Base logloss | Augmented logloss |
|---|---:|---:|---:|---:|---:|
| Sep 01, Bybit only | 6 | 0.2732981 | 0.2652393 | 0.7391912 | 0.7215846 |
| Oct 01, Bybit+OKX same market | 16 | 0.3228164 | 0.3207355 | 0.8419911 | 0.8374606 |

The augmented model **slightly improves both dates relative to the weak logistic baseline**, but **does not exceed even the constant-prevalence baseline**. The prelocked calibration non-deterioration test also failed on Bybit: absolute mean predicted probability minus actual UP frequency worsened from **0.0521761** to **0.0542797**, although OKX improved from 0.0099118 to 0.0066888. Therefore the frozen hypothesis gate **fails**. Avoid retroactively dropping calibration condition or changing scoring to claim success.

## Independent arithmetic verification
After GitHub's model run, independently recomputed day-equal Brier directly from the stored individual holdout probabilities and binary targets. All three model results match the stored output within **5e-8** due to reported rounding. No dependence on post-event data in the declared predictors and no futures/margin trading writes.

## Provenance, R2 and reproducibility
- Workflow executed successfully: https://github.com/analiticprosp-ship-it/crypto-price-feed/actions/runs/39850687833
- A previous first attempt failed only because an extreme-sigmoid **selftest** incorrectly forbade expected floating-point saturation at -900. Test corrected; no prereg parameters/thresholds/data partition changed before execution.
- Full derived machine-readable result: `research/09l/v0.8.7-2026-10-22/derived/09L_v087_retrospective_chronological_baseline_vs_flow.json`.
- Existing private Cloudflare R2 SHA256 readback successful: `research/09l/v087/validation/a9d48d9e75b9e7163df882895c6b9819dfd09fd7b8d8c6438364b34f16bdceab.json`; hash `a9d48d9e75b9e7163df882895c6b9819dfd09fd7b8d8c6438364b34f16bdceab`. Only derived JSON stored, no licensed source trade streams.
- Scientific status **`RETROSPECTIVE_BASELINE_DIAGNOSTIC_COMPLETE_NOT_PROSPECTIVE_OOS`**.

## Interpretation / next steps
On this sparse first-day-of-month sample, **adding 30-second flow imbalance failed to generate robust incremental predictive lift** by the predeclared standard; even the simple momentum/activity logistic underperformed the constant forecast. This does **not** disprove more sophisticated orderbook microstructure effects; this comparison is narrow, only two chronological holdout dates with substantial shared market events.

Next steps require (a) genuinely prospective future-day, timestamped and non-overlapping labels and (b) far broader independent periods, and (c) proper baseline + day-blocked calibration and, separately, true CoinGlass Model2 point-in-time cluster maps before testing cluster birth/death/first-touch. CoinGlass `CG_API_KEY` remains absent; no heatmap PIT or signed dealer gamma. Do not tune coefficients or switch target horizon retroactively to pursue a positive result. Keep 09L isolated from Spot/Futures/NAV/capital/P&L/reserve/trading limits/orders.
