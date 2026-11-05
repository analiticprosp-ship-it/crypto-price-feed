# Coinbase acquisition through GitHub Actions

This adds a one-shot branch-push collection to draft PR #157. It is not a scheduled
collector. The GitHub-hosted runner accesses Coinbase directly and needs no API key.
Only public BTC-USD / ETH-USD native 5m data enter the frozen calculator.

The workflow `us-midterms-market.yml` runs tests, collects the closed range needed
by the existing calendar and observation clocks, and uploads the entire research
directory as the immutable per-run artifact `p1-midterms-market-RUN_ID-ATTEMPT`.
It has read-only repository permissions, no secrets and no repository writeback.
The artifact retention is 90 days; download or archive the artifact before expiry.

`market_run/` contains original response bytes, HTTP headers and failure receipts,
aligned requests of at most 299 buckets, SHA-256 inventory, `market.json`,
`results.json`, `summary.json`, and a baseline lock if an eligible first candle
was obtained. The runner log also prints the compact summary. Failed pages or
incomplete mature windows fail collection acceptance while keeping the artifact.

The calculation cutoff is actual collection completion. Prices acquired now
describe current historical data; they do not become receipts available at the
old 3 November or 5 November 16:52:10 audit cutoffs. Old audits stay unchanged.
Result clocks still awaiting first-publication evidence remain PENDING_ANCHOR.
Unclosed windows remain null; missing data are never replaced by zero.

After downloading the artifact, from the research directory replay with:

```sh
python us_midterms_windows.py --ledger us_midterms_2026_11_05_v2.json --news-dir . --market-manifest market_run/market.json --as-of ACTUAL_AS_OF_FROM_RESULTS --baseline-lock market_run/baselines_001.json
```

Replace the as-of placeholder with the actual `as_of_utc` in `results.json`.
For later collection use a new output directory and pass the accepted prior lock
via `collect_us_midterms_market.py --output NEW_RUN --baseline-lock PRIOR_LOCK`.
The push workflow is the first collection only; it does not automatically restore
previous artifacts or claim cross-run baseline continuity. Later scoring must
carry the accepted first lock forward and reject revised/missing initial candles.

No success or actual return is claimed merely because this workflow exists.
Confirm the Actions run, HTTP receipts, coverage, baseline lock and output before
reporting acquisition as complete.
