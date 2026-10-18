#!/usr/bin/env python3
"""Independent replay of four Tardis Binance OI free sample days stored in R2.

Checks each derived 5m value against the latest vendor-received raw snapshot,
not merely whether its displayed vendor timestamp precedes decision time.
Audits vendor-time causality only, NEVER assumes official Binance publication.
"""
import csv
import datetime as dt
import gzip
import hashlib
import io
import json
import math
import os
from pathlib import Path
import boto3

DAYS=("2024-01-01","2025-01-01","2026-09-01","2026-10-01")
SYMBOLS=("BTCUSDT","ETHUSDT","SOLUSDT")
MULTI="research/tardis-binance-oi-multiday/v1"
OCT="research/tardis-binance-oi-sample/v1/2026-10-01"
MAX_GZ=10_000_000
MAX_MANIFEST=2_000_000
MAX_ROWS=200_000
OUT=Path("detector_tardis_fourday_verify")
OUT.mkdir(exist_ok=True)


def usec(iso):
    t=dt.datetime.fromisoformat(iso.replace("Z","+00:00"))
    if t.tzinfo is None:raise ValueError("TIMEZONE_REQUIRED")
    return int(t.timestamp()*1_000_000)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def get_bytes(s3,bucket,key,limit):
    obj=s3.get_object(Bucket=bucket,Key=key)
    if int(obj.get("ContentLength",-1))>limit:raise ValueError("OBJECT_SIZE_LIMIT")
    result=obj["Body"].read(limit+1)
    if len(result)>limit:raise ValueError("OBJECT_READ_LIMIT")
    return result


def assert_digest(data,expected):
    if digest(data)!=expected:raise ValueError("SOURCE_OR_DERIVED_SHA_MISMATCH")


def raw_snapshots(blob,day,symbol):
    """Different replay implementation from production: filter and sort all OI."""
    start=usec(day+"T00:00:00+00:00")
    end=start+86_400_000_000
    result=[]
    with gzip.open(io.BytesIO(blob),"rt",encoding="utf-8-sig",newline="") as f:
        rd=csv.DictReader(f)
        if not {"symbol","timestamp","local_timestamp","open_interest"}.issubset(rd.fieldnames or []):
            raise ValueError("RAW_COLUMNS_MISSING")
        for pos,row in enumerate(rd):
            if pos>=MAX_ROWS:raise ValueError("RAW_ROWS_LIMIT")
            if row["symbol"]!=symbol:raise ValueError("RAW_SYMBOL_MISMATCH")
            try:
                receipt=int(row["local_timestamp"])
                event=int(row["timestamp"])
            except (ValueError,TypeError):
                continue
            if not start<=receipt<end:continue
            raw=row.get("open_interest")
            try:
                value=float(raw)
            except (ValueError,TypeError):
                continue
            if not math.isfinite(value) or value<0:continue
            result.append((receipt,pos,event,raw))
    if not result:raise ValueError("RAW_VALID_OI_EMPTY")
    result.sort(key=lambda x:(x[0],x[1]))
    return result


def verify_derived(raw,derived,day,symbol):
    """Verify exact source record selection and every time boundary independently."""
    start=usec(day+"T00:00:00+00:00")
    cutoff_delay=30_000_000
    cursor=0;last=None
    missing=stale=0
    max_age=0
    lines=list(csv.DictReader(io.StringIO(derived.decode("utf-8-sig"))))
    if len(lines)!=288:raise ValueError("DERIVED_BUCKET_COUNT")
    for idx,row in enumerate(lines):
        if row["symbol"]!=symbol:raise ValueError("DERIVED_SYMBOL_MISMATCH")
        boundary=start+(idx+1)*300_000_000
        decision=boundary+cutoff_delay
        if (usec(row["bucket_start_utc"])!=boundary-300_000_000
                or usec(row["bucket_end_utc"])!=boundary
                or usec(row["decision_time_utc"])!=decision):
            raise ValueError("DERIVED_TIME_BOUNDARY_MISMATCH")
        while cursor<len(raw) and raw[cursor][0]<=decision:
            last=raw[cursor]
            cursor+=1
        if last is None:
            if row["open_interest"] or row["vendor_receipt_utc"] or row["asof_quality"] not in (
                "MISSING_ASOF_OI","MISSING_VENDOR_ASOF"):
                raise ValueError("FUTURE_OR_SYNTHETIC_OI")
            missing+=1
            continue
        receipt,_,event,oi=last
        if receipt>decision:raise ValueError("FUTURE_SNAPSHOT_USED")
        if row["open_interest"]!=oi or usec(row["vendor_receipt_utc"])!=receipt:
            raise ValueError("DERIVED_NOT_LATEST_ELIGIBLE_RAW_OI")
        if usec(row["source_event_utc"])!=event:
            raise ValueError("DERIVED_SOURCE_EVENT_MISMATCH")
        age=(decision-receipt)/1_000_000
        max_age=max(max_age,age)
        if abs(float(row["observation_age_seconds"])-age)>0.00001:
            raise ValueError("DERIVED_AGE_INCORRECT")
        if age>120:
            stale+=1
            if row["asof_quality"] not in ("STALE_VENDOR_OI_OVER_120S","STALE_VENDOR_OVER_120S"):
                raise ValueError("STALE_FLAG_MISSING")
        elif row["asof_quality"] not in ("OK_VENDOR_RECEIPT_PROVISIONAL","OK_VENDOR_RECEIPT"):
            raise ValueError("OK_QUALITY_MISMATCH")
    return {"verified_5m_buckets":288,"missing":missing,"stale_gt120s":stale,
            "max_age_s":round(max_age,6),"verified_vendor_future_receipts":0,
            "raw_valid_snapshots":len(raw)}


def read_manifest(s3,bucket,key,expected_schema):
    doc=json.loads(get_bytes(s3,bucket,key,MAX_MANIFEST))
    if doc.get("schema")!=expected_schema:raise ValueError("MANIFEST_SCHEMA_MISMATCH")
    return doc


def main():
    bucket=os.environ["R2_BUCKET"]
    s3=boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
                    aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
                    aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
    multi=read_manifest(s3,bucket,MULTI+"/manifest.json","detector-tardis-multiday-vendor-asof-v1")
    oct_source=read_manifest(s3,bucket,OCT+"/manifest.json",
                             "detector-tardis-binance-oi-receipt-asof-sample-v1")
    oct_derived=read_manifest(s3,bucket,OCT+"/derived/manifest.json",
                              "detector-tardis-oi-vendor-receipt-5m-asof-v1")
    results=[]
    for day in DAYS:
        for symbol in SYMBOLS:
            if day=="2026-10-01":
                origins=[r for r in oct_source["records"] if r["symbol"]==symbol]
                outputs=[r for r in oct_derived["outputs"] if r["symbol"]==symbol]
                if len(origins)!=1 or len(outputs)!=1:raise ValueError("OCT_MANIFEST_AMBIGUOUS")
                source_key=origins[0]["r2_key"]
                source_sha=origins[0]["compressed_sha256"]
                derived_key=outputs[0]["object_key"]
                derived_sha=outputs[0]["sha256"]
                root=OCT
            else:
                origins=[r for r in multi["records"] if r["day"]==day and r["symbol"]==symbol]
                if len(origins)!=1:raise ValueError("MULTI_MANIFEST_AMBIGUOUS")
                source_key=origins[0]["original_key"]
                source_sha=origins[0]["source_sha256"]
                derived_key=origins[0]["derived_key"]
                derived_sha=origins[0]["derived_sha256"]
                root=MULTI+"/"+day
            if not (source_key==root+"/"+symbol+".csv.gz" and
                    derived_key==root+"/derived/"+symbol+"_vendor_asof_5m.csv" if day!="2026-10-01"
                    else source_key==root+"/"+symbol+".csv.gz" and derived_key==root+"/derived/"+symbol+"_tardis_vendor_asof_5m.csv"):
                raise ValueError("MANIFEST_R2_PATH_MISMATCH")
            src=get_bytes(s3,bucket,source_key,MAX_GZ)
            bars=get_bytes(s3,bucket,derived_key,150_000)
            assert_digest(src,source_sha)
            assert_digest(bars,derived_sha)
            records=raw_snapshots(src,day,symbol)
            evidence=verify_derived(records,bars,day,symbol)
            item={"day":day,"symbol":symbol,"source_sha256":source_sha,
                  "derived_sha256":derived_sha,"quality":evidence,
                  "status":"INDEPENDENT_CAUSAL_REPLAY_PASS"}
            results.append(item)
            print("TARDIS_FOURDAY_REPLAY",json.dumps(item,ensure_ascii=False),flush=True)
    summary={"status":"INDEPENDENT_FOURDAY_REPLAY_PASS",
             "days":list(DAYS),"symbols":list(SYMBOLS),
             "source_days":len(results),"total_5m_verified":sum(r["quality"]["verified_5m_buckets"] for r in results),
             "source_snapshots_eligible":sum(r["quality"]["raw_valid_snapshots"] for r in results),
             "missing":sum(r["quality"]["missing"] for r in results),
             "stale_gt120s":sum(r["quality"]["stale_gt120s"] for r in results),
             "future_vendor_receipts":0,"venue":"Binance USDM observed by Tardis",
             "publication_time":"ORIGINAL_BINANCE_PUBLICATION_UNVERIFIED",
             "warning":"Vendor receipt time, not a historically proven time of API availability to trading bot"}
    report={"schema":"detector-tardis-4day-independent-vendor-replay-v1",
            "summary":summary,"evidence":results,"github_run_id":os.environ["GITHUB_RUN_ID"],
            "source_immutable_sha256_verified":True,"research_only":True}
    payload=json.dumps(report,ensure_ascii=False,sort_keys=True,indent=2).encode()
    key="research/tardis-binance-oi-independent-audit/v1/"+os.environ["GITHUB_RUN_ID"]+"-"+os.environ.get("GITHUB_RUN_ATTEMPT","1")+".json"
    checksum=digest(payload)
    s3.put_object(Bucket=bucket,Key=key,Body=payload,ContentType="application/json",
                  Metadata={"sha256":checksum})
    assert_digest(get_bytes(s3,bucket,key,len(payload)+1),checksum)
    (OUT/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2))
    summary["r2_audit_key"]=key
    summary["r2_audit_sha256"]=checksum
    print("TARDIS_FOURDAY_AUDIT_SUMMARY",json.dumps(summary,ensure_ascii=False),flush=True)
    summary_path=os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path,"a",encoding="utf-8") as f:
            f.write("## Independent causal replay of vendor-received Binance OI\n\n")
            f.write(f"- Status: {summary['status']}\n- 5m rows verified: {summary['total_5m_verified']}\n")
            f.write(f"- Missing: {summary['missing']}\n- Stale >120s: {summary['stale_gt120s']}\n")
            f.write("- Trading edge and original venue publication time: NOT VERIFIED\n")

if __name__=="__main__":
    main()
