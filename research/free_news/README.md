# Free news SHADOW ingestion v1

Research-only manual pilot for issue #160. No paid CryptoPanic token, production trading, NAV, P&L or detector scoring changes.

Initial candidates: SEC press-release RSS and Federal Reserve press RSS. **Candidate endpoints are not yet verified by a GitHub Actions run.** Sources may reject automated clients, change URLs, or include unrelated news. They are not substitutes for broad crypto news coverage.

Run: `python scripts/collect_free_news.py --output /tmp/free-news-receipts`.
Tests: `python -m unittest discover -s tests -p test_free_news.py`.
Workflow: `free-news-shadow-manual.yml` (manual only). Download run artifact for run.json and items.jsonl; no automatic persistence or schedule.

`published_raw` is a source-claimed string and is **not** normalized or verified; `first_seen_at_utc` is observed collection time and **not** the true earliest public availability. Repeated runs do not yet have durable cross-run deduplication. Treat as pilot only; do not backfill event timing from publication date.

Next: verify two real workflow receipts; validate feed terms/coverage, UTC parsing, persisted immutable receipts, source expansion, cross-run dedup, retry/backoff, and market-outcome join before proposing scheduling. Missing sources and fields remain explicit.
