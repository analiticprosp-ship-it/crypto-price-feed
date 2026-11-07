# Election study continuation — 6 November 2026

Scope: PR #157, descriptive research, frozen v2 ledger and Coinbase USD series.
Successful Actions run: https://github.com/analiticprosp-ship-it/crypto-price-feed/actions/runs/42214266193
Collector commit: `8d47ba1a43e88077228b189791efc31bde8e4798`.

## Market acquisition and baseline continuity

Actual cutoff: **2026-11-06T11:59:43.562247Z** (12:59 Madrid).
Eight validated original HTTP pages provide **1,019 closed native 5m candles per
asset**, 2,038 total; no failed pages. The complete immutable run is in
`market_runs/20261106T115943Z/`. All 39 runner tests passed, including rejection
of a changed candle under a prior baseline lock.

The acquisition explicitly loaded the accepted first lock from
`market_runs/20261105T170938Z/baselines_001.json`; the four entries are unchanged.
The new lock's parent SHA-256 is
`88794766bb93c2bfec08be612acc357a73bceb6d5b0355f0e50764384d56c89c`.
All ten previous complete windows retain exactly the same opening price, final
close, return and MAE/MFE. New data have not moved either series' start.

The artifact ZIP SHA-256 is
`d2494bd88a256b4b5ac97358218a328b127f0bbea53a4dd362c5e4905b41fb9e`.
Its market inventory and all compressed/uncompressed source hashes were verified
after download. Baseline-locked local replay matched clocks/statuses/baselines
exactly and numeric metrics within 1e-12 relative tolerance across Python versions.

## Newly closed observation windows

This series starts **5 November 16:55 UTC** after our saved KY-06 observation.
Opening prices remain BTC **76454.06 USD**, ETH **2265.66 USD**. These are fixed
historical candle opens, not current prices or assumed trade fills.

| Horizon | End UTC, 5 November | BTC return | ETH return | BTC MAE | ETH MAE |
|---|---|---:|---:|---:|---:|
| 15m | 17:10 | -0.54943% | -0.59938% | -0.62660% | -0.66912% |
| 1h | 17:55 | -0.85353% | -0.62984% | -1.01237% | -0.91761% |
| 4h | 20:55 | -0.34343% | -0.71855% | -1.17771% | -1.17008% |

MAE is the lowest intrawindow low relative to the starting open, not a
peak-to-trough drawdown. MFE remains available in `results.json`.

Both assets were below the fixed baseline at all three completed horizons. BTC
was less negative at 4h than at 1h, while ETH was more negative. This is a path
description after our late observation, not a causal estimate of the election
outcome or evidence against a multi-day recovery. It must not be combined with
the earlier calendar series as though their baselines were identical.

Current v2 status inventory (102 rows):

| Series | OK | WINDOW_NOT_MATURED | PENDING_ANCHOR |
|---|---:|---:|---:|
| Calendar comparison | 10 | 6 | 0 |
| Post-observation monitoring | 6 | 8 | 0 |
| Original result events | 0 | 0 | 72 |
| Total | 16 | 14 | 72 |

No PENDING_MARKET_DATA or DATA_GAP remains in this run. The observation 1d window
ends **6 November 16:55 UTC / 17:55 Madrid**, later than this cutoff, so its
metrics remain null. Calendar 7d ends 10 November 23:05 UTC. Longer horizons
remain as frozen in the ledger. No interim result or zero-fill is supplied.

## Publication-clock work

`source_runs/20261106T115946Z/` retains original current response bytes compressed
with deterministic gzip, their SHA-256 hashes, HTTP status, request/receipt clocks
and a manifest. Capture ended 11:59:46 UTC. This is a source-access inventory,
not a record of the original election-night releases.

| Source | Direct runner response | Timing assessment |
|---|---|---|
| KY official results | HTTP 200, current positive KY-06 tally | Dembo 138777; Alvarado 114030, unofficial. Displayed update 6 Nov 6:58:04 AM has no offset and does not date the first positive release. |
| Indiana official shell | HTTP 200, JavaScript template | Shell Last-Modified is 21 Oct; it is not the IN-05 result-feed time. No qualifying tally payload captured. |
| Three AP pages | HTTP 403, failure bodies preserved | No original article or call response captured from the runner. An HTTP failure is not evidence that AP made no call. |

The web retriever did expose AP control coverage and a Spanish updates page,
but not a qualifying versioned first-call receipt. A retrieved AP explainer now
discusses results while its indexed article date remains 3 Nov 05:24:28 UTC,
before the first close. That date cannot be assigned to the later result text.
This is a document-version/availability ambiguity, not an accepted result anchor.

The six original result events remain pending. A future attempt needs the
publisher's original timed item/version or a matching last-absent/first-present
feed bracket under the frozen rules. AP call occurrence time alone, translated
coverage, an article creation/update time, or a current positive tally is
insufficient. The KY observation clock is not reset to today's fetch time.

## Replay and next gate

From this research directory:

```sh
python -m unittest -v test_us_midterms_windows.py test_collect_us_midterms_market.py
python us_midterms_windows.py --ledger us_midterms_2026_11_05_v2.json --news-dir . --market-manifest market_runs/20261106T115943Z/market.json --as-of 2026-11-06T11:59:43.562247Z --baseline-lock market_runs/20261105T170938Z/baselines_001.json
```

Next collection should carry the existing accepted lock and wait until the 1d
observation window has actually ended before scoring it. No recurring schedule
has been installed. Original ledgers and prior run outputs remain unchanged;
no production, P1 rules, trading, NAV/P&L or financial permissions are altered.
