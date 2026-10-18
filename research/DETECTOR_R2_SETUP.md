# Detector research: private R2 archival

Research-only; no production trading changes.

## Cloudflare setup
1. Create private R2 bucket `detector-research` (or choose another name).
2. Create a bucket-scoped R2 API token with object read/write, not account-wide permissions.
3. Configure repository **Secrets**: `DETECTOR_R2_ACCOUNT_ID`, `DETECTOR_R2_ACCESS_KEY_ID`, `DETECTOR_R2_SECRET_ACCESS_KEY`.
4. Configure repository **Variables**: `DETECTOR_R2_BUCKET` (bucket name), `DETECTOR_R2_ENABLED` = `true` only after the secrets and bucket exist.
5. Manually dispatch workflow **Detector Research R2 Archive** for the first test; daily runs follow automatically.

The publisher scans the latest 100 successful workflow runs, selects the newest **allowlisted** research workflow on main, downloads its unexpired artifacts (max 80 MB per artifact), validates ZIP integrity, publishes immutable run-id keys and SHA-256 metadata, then updates `research/latest.json` only after successful uploads.

**Limitations**: this is an initial bootstrap, not a complete historical migration; it archives only the newest matching run per invocation. GitHub Actions artifacts expire; for durable full coverage a future workflow_run-based event queue or run-index sync is needed. R2 is private; ChatGPT cannot read it until a separate authenticated read gateway or suitable connector is configured. Never paste credentials in chat or commit them to source control. Do not expose raw research data publicly.
