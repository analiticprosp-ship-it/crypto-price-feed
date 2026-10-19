#!/usr/bin/env python3
"""Catch archive-history blind spots excluded by filename-based OI candidate filtering.

Inspect exactly the complementary 17 R2 ZIPs in the frozen 36-archive manifest.
SHA256+CRC verified, bounded downloads, original venue publication not assumed.
"""
import json,os
from pathlib import Path
import boto3
from research.detector_h1h10_archived_candidate_content_audit import (
 CENSUS_KEY,CENSUS_SHA,MAX_ZIP,MAX_ALL_COMPRESSED,
 ROOT as OLD_ROOT,get_verified,inspect_archive,summarize,digest
)

ROOT="research/detector-archive-nonkeyword-content-audit/v1"
OUT=Path("detector_archive_nonkeyword_audit")
OUT.mkdir(exist_ok=True)
EXPECTED_TOTAL=36
EXPECTED_OLD=19
EXPECTED_COMPLEMENT=17

def select_nonkeyword(census):
    all_rows=census.get("all_archives")
    selected=census.get("candidate_artifacts")
    if (not isinstance(all_rows,list) or not isinstance(selected,list)
        or len(all_rows)!=EXPECTED_TOTAL or len(selected)!=EXPECTED_OLD):
        raise ValueError("PINNED_ARCHIVE_CENSUS_CARDINALITY_CHANGED")
    keys={r["archive_object_key"] for r in selected}
    unique={r["archive_object_key"] for r in all_rows}
    if len(keys)!=EXPECTED_OLD or len(unique)!=EXPECTED_TOTAL or not keys.issubset(unique):
        raise ValueError("PINNED_ARCHIVE_SET_NOT_UNIQUE")
    remaining=[r for r in all_rows if r["archive_object_key"] not in keys]
    if len(remaining)!=EXPECTED_COMPLEMENT:
        raise ValueError("ARCHIVE_COMPLEMENT_CARDINALITY_CHANGED")
    return remaining

def audit_remaining(s3,bucket,metadata):
    records=[]
    for item in metadata:
        info={"run_id":item["run_id"],"archive_object_key":item["archive_object_key"],
              "workflow":item["workflow"],"artifact_name":item["artifact_name"]}
        size=item["archive_bytes"]
        if size>MAX_ZIP:
            info.update(archive_integrity="NOT_READ_OVER_SIZE_LIMIT",
                        error_type="BOUNDED_SIZE_EXCLUSION",
                        archive_bytes=size)
            records.append(info)
            continue
        try:
            payload=get_verified(s3,bucket,item["archive_object_key"],
                                item["archive_expected_sha256"],MAX_ZIP)
            result=inspect_archive(payload,item)
            records.append(result)
            print("NONKEYWORD_R2_CONTENT_ROW",json.dumps({
                "run":result["run_id"],"name":result["artifact_name"],
                "oi_csv":result["observed_oi_series"],
                "max_full_event_days":result["max_consecutive_288_event_label_days"],
                "files":[(f["name"],f["kind"]) for f in result["files"]][:15]},
                ensure_ascii=False),flush=True)
        except Exception as exc:
            info.update(archive_integrity="UNVERIFIED_ERROR",
                        error_type=type(exc).__name__,error=str(exc)[:160])
            records.append(info)
    return records

def main():
    s3=boto3.client("s3",
        endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
    bucket=os.environ["R2_BUCKET"]
    census=json.loads(get_verified(s3,bucket,CENSUS_KEY,CENSUS_SHA,1_000_000))
    if census.get("schema")!="detector-existing-research-r2-archive-census-v1":
        raise ValueError("CENSUS_SCHEMA_CHANGED")
    remaining=select_nonkeyword(census)
    total=sum(x["archive_bytes"] for x in remaining)
    if total>MAX_ALL_COMPRESSED:raise ValueError("NONKEYWORD_SCAN_EXCEEDS_BOUNDED_BUDGET")
    records=audit_remaining(s3,bucket,remaining)
    measures=summarize(records)
    status=("NONKEYWORD_ARCHIVE_CONTENT_PASS" if measures["archives_with_errors"]==0
            else "NONKEYWORD_ARCHIVE_CONTENT_PARTIAL")
    report={"schema":"detector-h1h10-nonkeyword-existing-archive-audit-v1",
       "status":status,"pinned_census":CENSUS_KEY,
       "pinned_census_sha256":CENSUS_SHA,
       "previous_audit":"research/detector-archive-candidate-content-audit/v1/39222450465-1.json",
       "scope":"Only the 17 complements of 19 previously examined R2 artifacts; now all 36 addressed",
       "archives":records,"summary":measures,
       "first_original_exchange_publication":"UNVERIFIED",
       "data_claim":"5m event labels alone NEVER prove initial availability or executable causal OI",
       "limits":["Historical source timestamps do not equal exchange publication",
                 "Some artifacts may be compact transformed features, not raw venue snapshots",
                 "No source re-download from venue, no price-trade profitability claim"],
       "research_only":True,"trade_actions":False,"edge_status":"EDGE_UNVALIDATED",
       "run_id":os.environ["GITHUB_RUN_ID"],"source_commit":os.environ.get("GITHUB_SHA")}
    body=json.dumps(report,ensure_ascii=False,sort_keys=True,indent=2).encode()
    key=ROOT+"/"+report["run_id"]+"-"+os.environ.get("GITHUB_RUN_ATTEMPT","1")+".json"
    expected=digest(body)
    s3.put_object(Bucket=bucket,Key=key,Body=body,ContentType="application/json",Metadata={"sha256":expected})
    if digest(s3.get_object(Bucket=bucket,Key=key)["Body"].read(len(body)+1))!=expected:
        raise ValueError("NONKEYWORD_REPORT_R2_READBACK_MISMATCH")
    (OUT/"report.json").write_text(json.dumps({**report,"r2_key":key,"r2_sha256":expected},ensure_ascii=False,indent=2))
    print("NONKEYWORD_R2_CONTENT_SUMMARY",json.dumps({
        "status":status,"summary":measures,
        "archive_names":[{"run":v["run_id"],"artifact":v["artifact_name"],
            "integrity":v["archive_integrity"],"oi_series":v.get("observed_oi_series",0),
            "max_days":v.get("max_consecutive_288_event_label_days",0)} for v in records],
        "r2_key":key,"sha256":expected,"edge_status":"EDGE_UNVALIDATED"},ensure_ascii=False),flush=True)
    if measures["archives_with_errors"]:raise SystemExit(2)

if __name__=="__main__":main()
