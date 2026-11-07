# First successful Coinbase acquisition through GitHub Actions

Run: https://github.com/analiticprosp-ship-it/crypto-price-feed/actions/runs/42071818221

Source code commit: `ee25a99afd2d864b71c765852d586ca504f1d3e2`.
Run completed successfully. All 38 tests passed on the hosted runner.
The collection cutoff is **2026-11-05T17:09:38.456359Z** (18:09 Madrid).

Six successful original Coinbase HTTP responses, no failed pages, supply 793
closed 5m candles each for BTC-USD and ETH-USD. All 23 hashes in the collection
inventory were verified after downloading; the baseline-locked offline replay
also succeeded. Clocks, baselines, statuses and returns match exactly. Aggregate
volume/volatility agree within 1e-12 relative tolerance across runner/local Python
versions; floating-point summation is not claimed byte-identical across versions.
The downloaded artifact ZIP SHA-256 is
`772a457cfff94e805efb3bab646ad0f988763db54997aa3bf879d12e01b214c0`.

Permanent receipts and outputs: `market_runs/20261105T170938Z/`.
The GitHub artifact is `p1-midterms-market-42071818221-1`, ID 13436506837,
retained by Actions until 2027-02-03; repository copies retain the actual inputs.

## Calendar comparison results

The clock is the first scheduled IN/KY poll-close wave, 3 November 23:00 UTC.
Post-window start remains **3 November 23:05 UTC**, with opening prices
BTC 77721.01 USD and ETH 2287.11 USD. These are historical Coinbase prices,
not current quotes. Percent returns:

| Window | BTC-USD | ETH-USD |
|---|---:|---:|
| Previous 24h, ending 3 Nov 23:00 UTC | +1.29035% | +1.66090% |
| Post 15m | +0.05289% | +0.00131% |
| Post 1h | -0.46125% | -0.56097% |
| Post 4h | -2.30616% | -2.32827% |
| Post 1d | +3.56788% | +6.25374% |

The original 88 rows are now 10 OK, 6 WINDOW_NOT_MATURED, 72 PENDING_ANCHOR.
All 10 formerly pending market-data rows have actual results. The 6 remaining
calendar rows are the 7d/30d/90d horizons for both assets.

The separately recorded KY-06 observation starts at **5 November 16:55 UTC**.
Its first closed candles are now pinned: BTC 76454.06 USD; ETH 2265.66 USD.
Its 14 horizon rows are still WINDOW_NOT_MATURED at collection cutoff (the
first 15m window closes at 17:10 UTC). Together the v2 report has 102 rows:
10 OK, 20 WINDOW_NOT_MATURED, 72 PENDING_ANCHOR, no PENDING_MARKET_DATA.

These calendar returns do not measure reaction to an AP result declaration.
Seventy-two result rows still need first-publication receipts. Current historical
prices acquired now remain DESCRIPTIVE and do not alter the preserved old audit
cutoffs. Missing/unclosed results remain null, never zero.

## Replay

From this research directory:

```sh
python us_midterms_windows.py --ledger us_midterms_2026_11_05_v2.json --news-dir . --market-manifest market_runs/20261105T170938Z/market.json --as-of 2026-11-05T17:09:38.456359Z --baseline-lock market_runs/20261105T170938Z/baselines_001.json
```

Future collection/scoring must use this accepted baseline lock; do not silently
replace it with another run's first candle. This is a completed one-shot fetch,
not a recurring schedule. Production, trading, P1 gates and financial state are
outside this collection.
