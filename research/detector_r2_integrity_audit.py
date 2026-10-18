#!/usr/bin/env python3
"""Independent read-only integrity audit of archived H1-H10 data in private R2.

Does not trust publishing run outcome or its stored SHA-256 metadata alone.
No trading data, credentials or raw research payloads in the public summary.
"""
import datetime as dt
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sys
import zipfile

import boto3
from botocore.exceptions import ClientError

SCHEMA = "detector-research-r2-v1"
MANIFEST = re.compile(r"^research/([0-9]+)/manifest\.json$")
OBJECT = re.compile(r"^research/([0-9]+)/([0-9]+)-[^/]+\.zip$")
MAX_ARCHIVE_BYTES = 80_000_000
MAX_TOTAL_BYTES = 2_000_000_000
MAX_MANIFEST_BYTES = 1_000_000
MIN_EXPECTED_MANIFESTS = 18
OUT = Path("detector_h1_h10_r2_integrity")
OUT.mkdir(parents=True, exist_ok=True)


def main():
    bucket = os.environ["R2_BUCKET"]
    s3 = boto3.client(
        "s3",
        endpoint_url="https://" + os.environ["R2_ACCOUNT_ID"] + ".r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )
    problems = []
    manifest_keys = []
    pages = 0
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix="research/"):
        pages += 1
        if pages > 100:
            problems.append("R2_LIST_PAGINATION_LIMIT")
            break
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if MANIFEST.fullmatch(key):
                manifest_keys.append(key)
    checked = 0
    objects = 0
    total_bytes = 0
    records = []
    manifests = {}
    for key in sorted(manifest_keys, key=lambda k: int(MANIFEST.fullmatch(k).group(1))):
        rid = int(MANIFEST.fullmatch(key).group(1))
        try:
            response = s3.get_object(Bucket=bucket, Key=key)
            size = int(response.get("ContentLength", -1))
            if size < 0 or size > MAX_MANIFEST_BYTES:
                raise ValueError("MANIFEST_SIZE_INVALID")
            manifest = json.loads(response["Body"].read(MAX_MANIFEST_BYTES + 1))
            if manifest.get("schema") != SCHEMA or manifest.get("run_id") != rid:
                raise ValueError("MANIFEST_SCHEMA_OR_ID_MISMATCH")
            artifacts = manifest.get("artifacts")
            if not isinstance(artifacts, list) or not artifacts:
                raise ValueError("MANIFEST_NO_ARTIFACTS")
            if key in manifests:
                raise ValueError("DUPLICATE_MANIFEST")
            names = set()
            for art in artifacts:
                object_key = art["key"]
                match = OBJECT.fullmatch(object_key)
                if not match or int(match.group(1)) != rid or int(match.group(2)) != int(art["artifact_id"]):
                    raise ValueError("ARTIFACT_PATH_OR_ID_MISMATCH")
                if object_key in names:
                    raise ValueError("DUPLICATE_ARTIFACT_KEY")
                names.add(object_key)
                expected_bytes = int(art["bytes"])
                expected_hash = str(art["sha256"]).lower()
                if expected_bytes <= 0 or expected_bytes > MAX_ARCHIVE_BYTES or not re.fullmatch(r"[a-f0-9]{64}", expected_hash):
                    raise ValueError("ARTIFACT_MANIFEST_METADATA_INVALID")
                if total_bytes + expected_bytes > MAX_TOTAL_BYTES:
                    raise ValueError("AUDIT_TOTAL_BYTES_LIMIT")
                r = s3.get_object(Bucket=bucket, Key=object_key)
                meta_hash = r.get("Metadata", {}).get("sha256", "").lower()
                if meta_hash and meta_hash != expected_hash:
                    raise ValueError("ARTIFACT_R2_METADATA_SHA256_MISMATCH")
                if int(r.get("ContentLength", -1)) != expected_bytes:
                    raise ValueError("ARTIFACT_LENGTH_MISMATCH")
                payload = r["Body"].read(MAX_ARCHIVE_BYTES + 1)
                if len(payload) != expected_bytes:
                    raise ValueError("ARTIFACT_READ_LENGTH_MISMATCH")
                actual_hash = hashlib.sha256(payload).hexdigest()
                if actual_hash != expected_hash:
                    raise ValueError("ARTIFACT_BODY_SHA256_MISMATCH")
                with zipfile.ZipFile(io.BytesIO(payload)) as z:
                    if z.testzip() is not None:
                        raise ValueError("ARTIFACT_ZIP_CRC_MISMATCH")
                total_bytes += len(payload)
                objects += 1
            manifests[rid] = manifest
            checked += 1
            records.append({"run_id": rid, "artifacts": len(artifacts), "sha256": "PASS"})
        except (ClientError, KeyError, TypeError, ValueError, zipfile.BadZipFile, OSError) as exc:
            problems.append({"run_id": rid, "error_type": type(exc).__name__, "check": str(exc)[:100]})
            print("INTEGRITY_FAILED", rid, type(exc).__name__, flush=True)

    latest_run_id = None
    try:
        response = s3.get_object(Bucket=bucket, Key="research/latest.json")
        if int(response.get("ContentLength", -1)) > MAX_MANIFEST_BYTES:
            raise ValueError("LATEST_TOO_LARGE")
        latest = json.loads(response["Body"].read(MAX_MANIFEST_BYTES + 1))
        latest_run_id = int(latest["run_id"])
        if latest_run_id not in manifests:
            raise ValueError("LATEST_MANIFEST_NOT_FOUND")
        if latest != manifests[latest_run_id]:
            raise ValueError("LATEST_MANIFEST_CONTENT_MISMATCH")
        if latest_run_id != max(manifests):
            raise ValueError("LATEST_POINTER_REGRESSED")
    except (ClientError, KeyError, TypeError, ValueError) as exc:
        problems.append({"check": "latest", "error_type": type(exc).__name__, "detail": str(exc)[:100]})
    if len(manifest_keys) < MIN_EXPECTED_MANIFESTS:
        problems.append({"check": "minimum_history", "found": len(manifest_keys), "expected_at_least": MIN_EXPECTED_MANIFESTS})
    status = "INTEGRITY_PASS" if not problems and checked == len(manifest_keys) else "INTEGRITY_FAIL"
    report = {
        "status": status, "scope": "R2 research/<run_id>/manifest.json + all listed ZIPs + latest.json",
        "audited_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "manifests_discovered": len(manifest_keys), "manifests_checked": checked,
        "artifacts_sha256_crc_verified": objects, "bytes_sha256_verified": total_bytes,
        "latest_run_id": latest_run_id, "errors": problems, "runs": records,
        "limitations": [
            "Independent R2 read and full SHA256/ZIP CRC verification, not proof of correctness of source or predictive edge",
            "No proof of original OI actual publication time",
            "Runs not archived and not listed by R2 are outside this audit; research history completeness audited separately",
        ],
    }
    (OUT / "audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("R2_INTEGRITY_AUDIT", json.dumps({k: v for k, v in report.items() if k not in ("runs", "limitations")}, ensure_ascii=False), flush=True)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write("## H1-H10 independent R2 integrity audit\n\n")
            f.write(f"- Status: {status}\n- Manifests: {checked}/{len(manifest_keys)}\n")
            f.write(f"- ZIPs verified by full SHA256 + CRC: {objects}\n- Verified bytes: {total_bytes}\n")
            f.write(f"- latest run_id: {latest_run_id}\n- Errors: {len(problems)}\n")
    if problems:
        sys.exit(2)


if __name__ == "__main__":
    main()
