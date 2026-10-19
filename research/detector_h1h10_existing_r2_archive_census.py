#!/usr/bin/env python3
"""Bounded census of existing H1-H10 research R2 archive manifests.

A metadata census, NOT as-of publication proof, continuous-coverage proof, or
another download of source archives. Avoid 2024–26 mass-download/cost.
"""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re

import boto3

MANIFEST=re.compile(r"^research/(\d+)/manifest\.json$")
OBJECT=re.compile(r"^research/(\d+)/(\d+)-[^/]+\.zip$")
ROOT="research/detector-archive-candidate-census/v1"
OUT=Path("detector_archive_candidate_census")
OUT.mkdir(exist_ok=True)
MAX_MANIFESTS=160
MAX_MANIFEST_SIZE=1_000_000
MAX_TOTAL_KEYS=3500

def classify(workflow,artifact):
    """Only a file-name candidate; NEVER classify actual field semantics."""
    name=(str(workflow)+" "+str(artifact)).lower()
    flags=[]
    for category,terms in (
        ("open_interest",("open interest","open-interest","oi availability","oi history","historical oi")),
        ("taker_flow",("aggtrades","agg-trades","taker flow","flow")),
        ("price_klines",("klines","candle","ohlcv")),
        ("perpetual",("perp","futures")),
        ("depth",("depth","orderbook","order book")),
        ("liquidations",("liquidat",)),
    ):
        if any(w in name for w in terms):
            flags.append(category)
    if re.search(r"(?<![a-z0-9])oi(?![a-z0-9])",name) and "open_interest" not in flags:\n        flags.append("open_interest")\n    return flags if flags else ["unclassified"]

def parse_manifest(key,blob):
    match=MANIFEST.fullmatch(key)
    if not match:raise ValueError("MANIFEST_KEY_INVALID")
    doc=json.loads(blob)
    if doc.get("schema")!="detector-research-r2-v1" or doc.get("run_id")!=int(match.group(1)):
        raise ValueError("MANIFEST_SCHEMA_OR_ID_MISMATCH")
    entries=doc.get("artifacts",[])
    if not isinstance(entries,list) or not entries:raise ValueError("ARCHIVE_NO_ARTIFACTS")
    records=[]
    for item in entries:
        path=item["key"]
        obj=OBJECT.fullmatch(path)
        if not obj or obj.group(1)!=match.group(1) or int(obj.group(2))!=int(item["artifact_id"]):
            raise ValueError("ARCHIVE_OBJECT_PATH_INVALID")
        checksum=item.get("sha256","")
        size=item.get("bytes")
        if not re.fullmatch("[0-9a-f]{64}",checksum) or not isinstance(size,int) or size<=0:
            raise ValueError("ARCHIVE_SHA_OR_SIZE_INVALID")
        tags=classify(doc.get("workflow"),item.get("name"))
        records.append({
            "run_id":doc["run_id"],"workflow":doc.get("workflow"),
            "source_commit":doc.get("head_sha"),
            "archive_object_key":path,"archive_expected_sha256":checksum,
            "artifact_name":item.get("name"),"archive_bytes":size,
            "metadata_candidate_categories":tags,
            "candidate_5m_continuous_oi":"NOT_PROVEN",
            "candidate_true_first_publication":"NOT_PROVEN",
            "content_evidence":"ARCHIVED_MANIFEST_METADATA_ONLY",
        })
    return records

def collect(s3,bucket):
    keys=[]
    pages=0;seen=0
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket,Prefix="research/"):
        pages+=1
        if pages>100:raise ValueError("ARCHIVE_PAGINATION_LIMIT")
        for obj in page.get("Contents",[]):
            seen+=1
            if seen>MAX_TOTAL_KEYS:raise ValueError("R2_KEY_SCAN_LIMIT")
            if MANIFEST.fullmatch(obj["Key"]):
                keys.append(obj["Key"])
                if len(keys)>MAX_MANIFESTS:
                    raise ValueError("TOO_MANY_R2_ARCHIVE_MANIFESTS")
    if not keys:raise ValueError("NO_ARCHIVED_MANIFESTS")
    inventory=[]
    for key in sorted(keys):
        resp=s3.get_object(Bucket=bucket,Key=key)
        length=int(resp.get("ContentLength",-1))
        if not 0<length<=MAX_MANIFEST_SIZE:raise ValueError("ARCHIVE_MANIFEST_SIZE_INVALID")
        content=resp["Body"].read(MAX_MANIFEST_SIZE+1)
        if len(content)!=length:raise ValueError("ARCHIVE_MANIFEST_READ_LENGTH_INVALID")
        inventory.extend(parse_manifest(key,content))
    unique={(r["run_id"],r["archive_object_key"]) for r in inventory}
    if len(unique)!=len(inventory):raise ValueError("ARCHIVE_ID_COLLISION")
    return len(keys),inventory

def main():
    bucket=os.environ["R2_BUCKET"]
    s3=boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
         aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
    count,rows=collect(s3,bucket)
    interesting=[v for v in rows if any(k in v["metadata_candidate_categories"] for k in ("open_interest","taker_flow","depth","price_klines","liquidations"))]
    report={
      "schema":"detector-existing-research-r2-archive-census-v1",
      "status":"ARCHIVE_METADATA_CENSUS_COMPLETE_NOT_DATA_VERIFICATION",
      "generated_utc":dt.datetime.now(dt.timezone.utc).isoformat(),
      "r2_manifests_examined":count,"archive_artifacts_catalogued":len(rows),
      "candidate_artifacts_from_names":len(interesting),
      "candidate_artifacts":interesting,"all_archives":rows,
      "source_provenance":"R2 archived manifest metadata only; original byte checks occur in independent integrity audits",
      "limits":["No huge archived ZIP downloaded in this census",
                "Archive filename does not establish data content, time coverage, completeness, OI units, 5m cadence, or publication timestamp",
                "Cannot infer continuous 7-day first-available OI from artifact names",
                "Use separate SHA256+CRC body verification and dataset-level as-of audit before any model",
                "This inventory complements but does not override pinned evidence inventory #82"],
      "next_action":"For only promising metadata candidates, inspect already archived source ZIP with R2 GET SHA256/CRC and measure dataset periods without expensive mass downloads",
      "research_only":True,"trade_actions":False,"edge_status":"EDGE_UNVALIDATED",
      "run_id":os.environ["GITHUB_RUN_ID"]}
    blob=json.dumps(report,ensure_ascii=False,indent=2,sort_keys=True).encode()
    key=ROOT+"/"+report["run_id"]+"-"+os.environ.get("GITHUB_RUN_ATTEMPT","1")+".json"
    checksum=hashlib.sha256(blob).hexdigest()
    s3.put_object(Bucket=bucket,Key=key,Body=blob,ContentType="application/json",Metadata={"sha256":checksum})
    if hashlib.sha256(s3.get_object(Bucket=bucket,Key=key)["Body"].read(len(blob)+1)).hexdigest()!=checksum:
        raise ValueError("CENSUS_R2_READBACK_SHA_MISMATCH")
    (OUT/"report.json").write_text(json.dumps({**report,"r2_key":key,"sha256":checksum},ensure_ascii=False,indent=2),encoding="utf-8")
    print("DETECTOR_ARCHIVE_CENSUS",json.dumps({
       "status":report["status"],"manifest_count":count,"archive_artifacts":len(rows),
       "candidate_artifacts":len(interesting),
       "candidates":[{"run":v["run_id"],"workflow":v["workflow"],"artifact":v["artifact_name"],"categories":v["metadata_candidate_categories"]}
          for v in interesting][:35],
       "r2_key":key,"sha256":checksum,"edge_status":"EDGE_UNVALIDATED"},ensure_ascii=False),flush=True)

if __name__=="__main__":main()
