# Detector H1–H10: existing Cloudflare R2 integration

**Do not create a second bucket or rotate existing credentials.** The existing private bucket is `crypto-detector-history`, configured through repository secrets `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET`.

The H1–H10 archive workflow `.github/workflows/detector-r2-archive.yml` reuses these exact secret names and runs daily at 05:17 UTC, or manually via workflow_dispatch. It publishes a separate research prefix `research/<run_id>/` and `research/latest.json`; this does not overwrite v6.8 `research/detector/v6.8/latest.json`.

**Verification required**: Check a successful run log and inspect R2 readback before claiming end-to-end archival. The current script only archives the latest allowlisted successful H1–H10 workflow run in the last 100 runs; this is a bootstrap, not complete historical retention. The workflow must be extended to queue or backfill all H1–H10 runs for durable full coverage. GitHub workflow success alone is not proof that ChatGPT can read private R2 objects. A scoped authenticated read gateway or connector is still needed. Never expose keys in chat or public source. No trading changes.
