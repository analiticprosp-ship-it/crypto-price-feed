#!/usr/bin/env python3
"""Fetch pinned, SHA256-verified H1-H10 input from private R2, not expiring Actions ZIPs.

Source selection is latest *archived* run for an exact workflow + artifact pair.
Provenance is persisted to make every downstream research result reproducible.
This is not a claim of source-event publication time.
"""
import argparse
import datetime as dt
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import zipfile

import boto3

MANIFEST_RE = re.compile(r"^research/([0-9]+)/manifest\.json$")
OBJECT_RE = re.compile(r"^research/([0-9]+)/([0-9]+)-[^/]+\.zip$")
MAX_MANIFEST = 1_000_000
MAX_ZIP = 80_000_000
MAX_UNPACKED = 450_000_000


def choose(manifests, workflow, artifact):
    """Select by immutable R2 run id, never by wall-clock download time."""
    matches = []
    for m in manifests:
        if m.get("schema") != "detector-research-r2-v1" or m.get("workflow") != workflow:
            continue
        rid = m.get("run_id")
        if type(rid) is not int or rid <= 0:
            continue
        for a in m.get("artifacts", []):
            if a.get("name") == artifact:
                matches.append((rid, m, a))
    if not matches:
        raise ValueError("ARCHIVED_SOURCE_MISSING")
    matches.sort(key=lambda t: t[0])
    if len(matches) >= 2 and matches[-1][0] == matches[-2][0]:
        raise ValueError("AMBIGUOUS_ARCHIVED_SOURCE")
    return matches[-1]


def safe_members(z):
    total = 0
    members = z.infolist()
    if not members:
        raise ValueError("EMPTY_ARCHIVE")
    for member in members:
        p = PurePosixPath(member.filename)
        mode = (member.external_attr >> 16)
        if (not member.filename or p.is_absolute() or ".." in p.parts
                or "\\" in member.filename or re.match(r"^[A-Za-z]:", member.filename)
                or stat.S_ISLNK(mode)):
            raise ValueError("UNSAFE_ZIP_MEMBER")
        total += member.file_size
        if total > MAX_UNPACKED:
            raise ValueError("UNPACKED_SIZE_LIMIT")
    return members


def download(s3, bucket, workflow, artifact, dest):
    candidates = []
    pages = 0
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix="research/"):
        pages += 1
        if pages > 100:
            raise ValueError("MANIFEST_LIST_PAGINATION_LIMIT")
        for obj in page.get("Contents", []):
            match = MANIFEST_RE.fullmatch(obj["Key"])
            if match:
                response = s3.get_object(Bucket=bucket, Key=obj["Key"])
                if int(response.get("ContentLength", -1)) > MAX_MANIFEST:
                    raise ValueError("MANIFEST_SIZE_LIMIT")
                raw = response["Body"].read(MAX_MANIFEST + 1)
                m = json.loads(raw)
                if m.get("run_id") != int(match.group(1)):
                    raise ValueError("MANIFEST_ID_MISMATCH")
                candidates.append(m)
    rid, m, art = choose(candidates, workflow, artifact)
    key = art["key"]
    match = OBJECT_RE.fullmatch(key)
    if (match is None or int(match.group(1)) != rid
            or int(match.group(2)) != int(art["artifact_id"])):
        raise ValueError("ARTIFACT_PATH_MISMATCH")
    expected_len = int(art["bytes"])
    expected_sha = str(art["sha256"]).lower()
    if not 0 < expected_len <= MAX_ZIP or not re.fullmatch("[a-f0-9]{64}", expected_sha):
        raise ValueError("INVALID_SOURCE_METADATA")
    response = s3.get_object(Bucket=bucket, Key=key)
    if int(response.get("ContentLength", -1)) != expected_len:
        raise ValueError("R2_CONTENT_LENGTH_MISMATCH")
    data = response["Body"].read(MAX_ZIP + 1)
    if len(data) != expected_len or hashlib.sha256(data).hexdigest() != expected_sha:
        raise ValueError("R2_SOURCE_SHA256_MISMATCH")
    root = Path(dest)
    if root.exists() and any(root.iterdir()):
        raise ValueError("DESTINATION_NOT_EMPTY")
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        members = safe_members(z)
        if z.testzip() is not None:
            raise ValueError("R2_SOURCE_CRC_FAILURE")
        root.mkdir(parents=True, exist_ok=True)
        z.extractall(root, members=members)
    proof = {
        "source": "private-R2-verified",
        "run_id": rid, "workflow": workflow, "artifact_name": artifact,
        "source_head_sha": m.get("head_sha"),
        "source_completed_at": m.get("completed_at"),
        "source_published_at": m.get("published_at"),
        "fetched_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "r2_object_key": key, "archive_sha256": expected_sha,
        "artifact_bytes": expected_len,
        "status": "HASH_VERIFIED_NOT_PUBLICATION_TIME_VALIDATED",
    }
    (root / "_r2_provenance.json").write_text(json.dumps(proof, ensure_ascii=False, indent=2), encoding="utf-8")
    print("ARCHIVED_INPUT_VERIFIED", json.dumps(proof, ensure_ascii=False), flush=True)
    return proof


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workflow", required=True)
    parser.add_argument("--artifact", required=True)
    parser.add_argument("--dest", required=True)
    args = parser.parse_args()
    client = boto3.client(
        "s3",
        endpoint_url="https://" + os.environ["R2_ACCOUNT_ID"] + ".r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )
    download(client, os.environ["R2_BUCKET"], args.workflow, args.artifact, args.dest)


if __name__ == "__main__":
    main()
