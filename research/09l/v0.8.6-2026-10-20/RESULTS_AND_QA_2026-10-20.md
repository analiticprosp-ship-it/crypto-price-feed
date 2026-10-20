# 09L v0.8.6 — independent date, second exchange + strict L2 reset audit
2026-10-20 · **SHADOW / EXPLORATORY / NOT_TRADEABLE** · all earlier v0.1–v0.8.5 artifacts immutable.

## Frozen methodology
`PREREG_LOCKED_2026-10-20.md` committed before ingesting new source files; it specified Bybit BTCUSDT on 2026-09-01 UTC, OKX BTC-USDT-SWAP on 2026-10-01 UTC, eight clock-fixed case windows per venue, a fixed ±25bp event-price band, event as-of price from most recent trade ≤5s before anchor, L2 decrease-to-aggressor trade match **at exact price** and capture-clock absolute lags [0,50], (50,200], (200,1000] ms. Correct side: taker SELL↔bid decrease, BUY↔ask decrease; competing flipped-side and +5sec time-shift placebos independently reallocate trade budgets (no reuse per scenario). Windows selected by historical clock from v0.8.5 **before seeing outcomes for new date/venue**, but not independently random; studies are distinct source datasets yet not true future OOS forecasts. Chronologically first observed liquidation messages after UTC 06:00/12:00/18:00 are separate exploratory cases, never mixed into primary eight windows.

## Successfully ingested and source-hash verified
| Historical dataset | Trades | L2 updates | BTC liquidation messages | L2 snapshot resets | Fixed cases valid after reset exclusion |
|---|---:|---:|---:|---:|---:|
| Bybit BTCUSDT 2026-09-01 | 2,017,317 | 23,077,949 | 1,245 | 3 | 8/8 |
| OKX BTC-USDT-SWAP 2026-10-01 | 2,757,848 | 42,194,739 | 481 | 49 | 7/8 |

All six source gzip SHA256 hashes, compressed sizes, row counts, zero invalid rows and zero capture-time reversals are stored in `derived/09L_v086_bybit_sep_fixed_clock_robustness.json` and `derived/09L_v086_okx_oct_fixed_clock_robustness.json`. Raw Tardis files not redistributed. Same-day OKX and older Bybit Oct1 can share market-wide shocks; neither cross-venue liquidity nor contract raw units is interchangeable.

## Primary 8 pre-set wall clock minutes: full descriptive audit
| Venue/day | Correct matching | Flipped side | Trade time shifted +5s | Windows correct > both |
|---|---:|---:|---:|---:|
| Bybit Sep1 | 2.2400% | 0.9442% | 0.3047% | 8/8 |
| OKX Oct1 | 1.6902% | 0.5204% | 0.2236% | 8/8 (before reset exclusion) |

Fractions are **within-venue share of all L2 quote-size decreases** in the fixed band potentially associated with captured trades by nearest time and identical price. They are **not** actual uniquely identified fill rates, P(cascade), support/replenishment probability, nor p-values. The rate is small: unmatched quote-size reductions cannot be automatically classified as cancellations.

## Mandatory L2 restart sensitivity after publication of primary output
A separately logged full-file historical L2 audit `l2_reset_sensitivity_v086.py` independently downloaded and SHA-verified both feeds and recorded every `is_snapshot` false→true transition. Bybit 3 resets, **zero within any of eight windows**. OKX 49 resets, **one inside window 18:38:30**, at **2026-10-01 18:39:36.610213 UTC**. This window is excluded entirely from the strict sensitivity analysis (not silently altered in the original JSON).

| Strict only no-reset fixed windows | Correct | Flipped-side placebo | +5-second placebo | Correct > both |
|---|---:|---:|---:|---:|
| Bybit 8/8 | 2.2400% | 0.9442% | 0.3047% | 8/8 |
| OKX 7/8 | 1.6399% | 0.5181% | 0.2191% | 7/7 |

Full machine result: `derived/09L_v086_resets_summary.json` and individual `derived/09L_v086_*_l2_reset_window_audit.json`. **Combined 15/15 remaining windows** show a correct-side matching advantage over both placebos. Temporal correlations make treating 15/15 as a set of independent Bernoulli trials scientifically invalid.

## Additional chronologically selected liquidations
Observed first messages after each fixed session bucket: 3 Bybit and 3 OKX; correct-side match fraction also exceeds flipped-side in all six, but this is exploratory and not a chronological independent predictive validation. It neither identifies old Model2 liquidation clusters nor measures cascade outcomes.

## Interpretation and research hard limits
**Supported:** correct-side, same-price, near-capture-time association reliably outruns two falsification controls across one added date and a second futures venue, even after excluding an observed provider L2 restart case.

**NOT SUPPORTED:** proving a particular transaction caused a particular depth decrease; classifying unmatched changes as cancel vs fill; maker identity, absorption causality, hedging or signed dealer gamma; explaining direction of BTC prices, cluster formation/maturity, verifying PIT CoinGlass Model2 first-hit, or claiming a calibrated probability/forecast of cascades. Tardis source is captured WebSocket messages and `local_timestamp` is arrival time; instrument contract denominations remain venue-specific. Current source sample is first day of the month, which is not a representative randomly sampled trading day.

## Execution and verified writeback
Original two-job test run: https://github.com/analiticprosp-ship-it/crypto-price-feed/actions/runs/39421052781
Derived results imported into the **research branch** only: https://github.com/analiticprosp-ship-it/crypto-price-feed/actions/runs/39421573354
Reset full source QA: https://github.com/analiticprosp-ship-it/crypto-price-feed/actions/runs/39421989406
Research branch `research/09l-v08-6-20261020`. No merge to `main`, no modification to 00/01/01A/02/03/04/05/06/06C; NAV, capital, P&L, reserve, Spot, Futures, signals, position sizing, trading limits unchanged.

## Next stage v0.8.7, NOT RUN
Preregister new monthly historical dates with no lookahead, include actual signed forward mid-price +30s/+60s/+300s, realized volatility/volume/session/mid-depth controls; test whether an execution-related quote-change proxy adds incremental explanatory/predictive value for continuation versus a baseline over **genuinely independent chronological periods**; predeclare data-missingness, L2 restarts and status gates. Separately accumulate true **forward-saved CoinGlass Model2 PIT clusters** before testing cluster first-hit, and time-matched Deribit pre-event options only if exact historical snapshot exists. Keep gamma sign unknown absent inventory.
