#!/usr/bin/env python3
"""Private R2 connection smoke test. No trading or portfolio changes."""
import hashlib, os, sys
from datetime import datetime, timezone
import boto3
from botocore.config import Config

required = ["R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET"]
missing = [k for k in required if not os.getenv(k)]
if missing:
    sys.exit("Missing GitHub Actions secrets: " + ", ".join(missing))
account = os.environ["R2_ACCOUNT_ID"].strip()
bucket = os.environ["R2_BUCKET"].strip()
endpoint = f"https://{account}.r2.cloudflarestorage.com"
s3 = boto3.client("s3", endpoint_url=endpoint,
    aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
    aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
    region_name="auto", config=Config(signature_version="s3v4",
    retries={"max_attempts": 3, "mode": "standard"}))
payload = ("detector-r2-smoke-test\n" + datetime.now(timezone.utc).isoformat() + "\n").encode()
digest = hashlib.sha256(payload).hexdigest()
key = "system/smoke-test.txt"
s3.put_object(Bucket=bucket, Key=key, Body=payload, ContentType="text/plain",
    Metadata={"sha256": digest})
obj = s3.get_object(Bucket=bucket, Key=key)
readback = obj["Body"].read()
assert hashlib.sha256(readback).hexdigest() == digest, "SHA256 mismatch"
assert obj["Metadata"].get("sha256") == digest, "R2 metadata mismatch"
print("PASS: R2 upload, download, SHA256 and metadata verified")
print("Bucket:", bucket, "Object:", key, "SHA256:", digest)
