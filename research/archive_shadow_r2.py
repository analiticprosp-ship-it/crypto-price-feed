#!/usr/bin/env python3
"""Append-only SHADOW event archive in existing Cloudflare R2 bucket."""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import boto3

ROOT = Path(__file__).resolve().parents[1]
PREFIX = "shadow/v1"
REQUIRED = ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET")

def main():
    missing = [k for k in REQUIRED if not os.getenv(k)]
    if missing:
        raise RuntimeError("Missing R2 secrets: " + ", ".join(missing))
    client = boto3.client(
        "s3",
        endpoint_url=f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )
    bucket = os.environ["R2_BUCKET"]
    raw = (ROOT / "detector-signal-events.json").read_bytes()
    data = json.loads(raw)
    if not isinstance(data, (dict, list)):
        raise ValueError("Unexpected events JSON structure")
    candidates_raw = (ROOT / "detector-candidates.json").read_bytes()
    json.loads(candidates_raw)
    digest = hashlib.sha256(raw).hexdigest()
    now = dt.datetime.now(dt.timezone.utc)
    day = now.strftime("%Y-%m-%d")
    event_key = f"{PREFIX}/events/{day}/{digest}.json"
    candidate_digest = hashlib.sha256(candidates_raw).hexdigest()
    candidate_key = f"{PREFIX}/candidates/{day}/{candidate_digest}.json"

    # Immutable content-addressed snapshots. Repeated runs cannot create duplicate objects.
    for key, body in ((event_key, raw), (candidate_key, candidates_raw)):
        try:
            client.head_object(Bucket=bucket, Key=key)
            print("EXISTS", key)
        except client.exceptions.ClientError as exc:
            if exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode") != 404:
                raise
            client.put_object(Bucket=bucket, Key=key, Body=body, ContentType="application/json",
                              Metadata={"sha256": hashlib.sha256(body).hexdigest()})
            print("WRITTEN", key)
        result = client.get_object(Bucket=bucket, Key=key)["Body"].read()
        if hashlib.sha256(result).hexdigest() != hashlib.sha256(body).hexdigest():
            raise RuntimeError("R2 readback SHA-256 mismatch: " + key)
    print("R2_SHADOW_ARCHIVE_READBACK_OK", event_key, candidate_key)

if __name__ == "__main__":
    main()
