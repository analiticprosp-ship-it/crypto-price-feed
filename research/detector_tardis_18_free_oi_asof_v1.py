#!/usr/bin/env python3
"""Research-only, byte-verified 18 Tardis OI 5m vendor-receipt ASOF audit.

All 18 free first-of-month derivative_ticker CSV.gz are pinned to the SHA256
reported by the independently completed PR #98. OI is a field-specific last
nonblank observation with vendor local_timestamp <= decision = 5m end +30s,
and source event timestamp <= decision. Never assume exchange release time,
historic continuous coverage, comparable native units, or tradable edge.
"""
import csv
import datetime as dt
import gzip
import hashlib
import io
import json
import math
import os
import statistics
from pathlib import Path

from research.detector_tardis_okx_free_archive_audit_v1 import load_bytes

ROOT="research/detector-tardis-18-free-oi-asof-5m/v1"
OUT=Path("detector_tardis_18_oi_asof")
PARENT_KEY="research/detector-free-tardis-okx-history-audit/v1/39289452550-1.json"
PARENT_SHA="fba968c37705b9b955f9b943a015d99e299a548eef30bbbf7a1a933365e14b33"
UTC=dt.timezone.utc
BUCKET_US=300_000_000
DECISION_DELAY_US=30_000_000
FRESH_US=120_000_000
COMPRESSED_CAP=10_000_000
PLAIN_CAP=130_000_000
MAX_ROWS=700_000

def parse_us(val):
    s=str(val).strip()
    if not (len(s)==16 and s.isdigit()):
        raise ValueError("VENDOR_TIMESTAMP_MUST_BE_UNIX_MICROSECONDS")
    n=int(s)
    if not (1_600_000_000_000_000 <= n <= 1_900_000_000_000_000):
        raise ValueError("RECEIPT_TIME_OUT_OF_RANGE")
    return n

def audit_5m(uncompressed,source_day,venue,symbol):
    """One-pass streaming ASOF audit; never forward-fill from another sample day."""
    day=dt.date.fromisoformat(source_day)
    start=int(dt.datetime(day.year,day.month,day.day,tzinfo=UTC).timestamp()*1_000_000)
    end=start+86_400_000_000
    decisions=[start+(i+1)*BUCKET_US+DECISION_DELAY_US for i in range(288)]
    reader=csv.DictReader(io.TextIOWrapper(io.BytesIO(uncompressed),encoding="utf-8-sig",newline=""))
    fields=set(reader.fieldnames or [])
    required={"exchange","symbol","timestamp","local_timestamp","open_interest"}
    if not required.issubset(fields):raise ValueError("VENDOR_SOURCE_COLUMNS_MISSING")
    i=0
    last=None
    prev=None
    rows=valid_oi=blank_oi=bad_oi=event_future=receipt_out_of_day=0
    usable=stale=missing=available=0
    ages=[]
    earliest_valid=None
    late_receipt_count=0
    def finalize(index,observation):
        if observation is None:return "missing",None
        local,event,oi=observation
        if local>decisions[index] or event>decisions[index]:
            raise ValueError("VENDOR_LOOKAHEAD_IN_DERIVED_FEATURE")
        age=decisions[index]-local
        if age<0:raise ValueError("NEGATIVE_VENDOR_AGE")
        return ("fresh" if age<=FRESH_US else "stale"),age
    for row in reader:
        rows+=1
        if rows>MAX_ROWS:raise ValueError("ARCHIVE_ROW_BUDGET_EXCEEDED")
        if row.get("exchange")!=venue or row.get("symbol")!=symbol:
            raise ValueError("VENDOR_VENUE_SYMBOL_MISMATCH")
        local=parse_us(row["local_timestamp"])
        event=parse_us(row["timestamp"])
        if local<start or local>=end:receipt_out_of_day+=1
        if prev is not None and local<prev:raise ValueError("VENDOR_RECEIPT_NONMONOTONIC")
        prev=local
        while i<288 and decisions[i]<local:
            quality,age=finalize(i,last)
            if quality=="missing":missing+=1
            elif quality=="fresh":usable+=1;available+=1;ages.append(age/1e6)
            else:stale+=1;available+=1;ages.append(age/1e6)
            i+=1
        raw=row.get("open_interest","")
        if raw is None or raw=="":
            blank_oi+=1
            continue
        try:
            value=float(raw)
            if not math.isfinite(value) or value<0:raise ValueError()
        except (ValueError,TypeError):
            bad_oi+=1
            continue
        valid_oi+=1
        if event>local:
            event_future+=1
            continue
        if not (start<=local<end):
            continue
        if local>decisions[-1]:
            late_receipt_count+=1
            continue
        last=(local,event,raw)
        if earliest_valid is None:earliest_valid=local
    while i<288:
        quality,age=finalize(i,last)
        if quality=="missing":missing+=1
        elif quality=="fresh":usable+=1;available+=1;ages.append(age/1e6)
        else:stale+=1;available+=1;ages.append(age/1e6)
        i+=1
    if rows==0 or usable+stale+missing!=288:
        raise ValueError("BUCKET_ACCOUNTING_OR_EMPTY_ARCHIVE")
    return {"source_rows":rows,"valid_numeric_oi_rows":valid_oi,
        "blank_oi_rows":blank_oi,"invalid_oi_rows":bad_oi,
        "event_timestamp_after_vendor_receipt_rows_excluded":event_future,
        "receipt_outside_day_rows":receipt_out_of_day,
        "late_receipts_after_final_decision":late_receipt_count,
        "asof_decision_delay_seconds":30,"oi_freshness_max_seconds":120,
        "total_5m_buckets":288,"fresh_oi_asof_buckets":usable,
        "stale_over_120s_buckets":stale,"missing_asof_buckets":missing,
        "available_asof_buckets":available,
        "median_asof_age_seconds":statistics.median(ages) if ages else None,
        "max_asof_age_seconds":max(ages) if ages else None,
        "first_usable_observation_receipt_utc":dt.datetime.fromtimestamp(earliest_valid/1e6,UTC).isoformat() if earliest_valid else None,
        "future_vendor_receipts_consumed":0,
        "source_exchange_first_release":"UNVERIFIED",
        "quality_status":"VENDOR_RECEIPT_ASOF_QUALITY_MEASURED_NOT_EXCHANGE_PIT"}

def checked_gzip(raw,expected_raw,expected_csv):
    if hashlib.sha256(raw).hexdigest()!=expected_raw:
        raise ValueError("SOURCE_COMPRESSED_SHA_MISMATCH")
    with gzip.GzipFile(fileobj=io.BytesIO(raw)) as z:
        plain=z.read(PLAIN_CAP+1)
        if len(plain)>PLAIN_CAP:raise ValueError("SOURCE_GZIP_EXPANSION_LIMIT")
    if hashlib.sha256(plain).hexdigest()!=expected_csv:
        raise ValueError("SOURCE_CSV_SHA_MISMATCH")
    return plain

def main():
    import boto3
    OUT.mkdir(exist_ok=True)
    s3=boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
      aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
      aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
    bucket=os.environ["R2_BUCKET"]
    parent_raw=s3.get_object(Bucket=bucket,Key=PARENT_KEY)["Body"].read(250_000)
    if hashlib.sha256(parent_raw).hexdigest()!=PARENT_SHA:raise ValueError("PARENT_SHA256_MISMATCH")
    parent=json.loads(parent_raw)
    if parent.get("schema")!="detector-h1h10-tardis-free-csv-okx-vintage-audit-v1":
        raise ValueError("PARENT_MANIFEST_SCHEMA_MISMATCH")
    samples=parent.get("Tardis_free_samples",[])
    if len(samples)!=18 or any(q.get("status")!="VENDOR_GZIP_RECEIPT_PASS" for q in samples):
        raise ValueError("PINNED_18_SAMPLES_NOT_ALL_SOURCE_VERIFIED")
    results=[]
    for src in samples:
        proof=src["quality"]
        blob,http=load_bytes(src["source_url"],COMPRESSED_CAP,30)
        if http!=200:raise ValueError("TARDIS_SAMPLE_HTTP_NOT_200")
        plain=checked_gzip(blob,proof["compressed_sha256"],proof["csv_sha256"])
        stats=audit_5m(plain,src["sample_day_utc"],src["exchange"],src["symbol"])
        if stats["source_rows"]!=proof["rows"] or stats["blank_oi_rows"]!=proof["missing_open_interest_rows"]:
            raise ValueError("ARCHIVE_ROW_COUNT_DRIFT_FROM_PINNED_SOURCE")
        row={"venue":src["exchange"],"symbol":src["symbol"],"date":src["sample_day_utc"],
           "compressed_sha256":proof["compressed_sha256"],"csv_sha256":proof["csv_sha256"],
           "source_archive_verified_against_previous_run":True,**stats}
        results.append(row)
        print("TARDIS_18_ASOF_CASE",json.dumps({
          "venue":row["venue"],"symbol":row["symbol"],"day":row["date"],
          "fresh":row["fresh_oi_asof_buckets"],"stale":row["stale_over_120s_buckets"],
          "missing":row["missing_asof_buckets"],"future_excluded":row["event_timestamp_after_vendor_receipt_rows_excluded"]},
          ensure_ascii=False),flush=True)
    status="VENDOR_ASOF_MEASURED_NOT_PIT"
    report={"schema":"detector-h1h10-tardis-18-free-oi-asof-5m-v1",
       "parent_key":PARENT_KEY,"parent_sha256":PARENT_SHA,
       "status":status,"samples":results,"case_count":len(results),
       "total_buckets":288*len(results),
       "fresh_buckets":sum(q["fresh_oi_asof_buckets"] for q in results),
       "stale_buckets":sum(q["stale_over_120s_buckets"] for q in results),
       "missing_buckets":sum(q["missing_asof_buckets"] for q in results),
       "vendor_asof_rule":"5m closed bucket end + 30s; nonblank OI receipt <= decision AND source event <= decision",
       "stale_policy":"age_since_vendor_receipt > 120s NOT a fresh H1-H10 feature",
       "causal_gate":"VENDOR_RECEIPT_ONLY_NO_EXCHANGE_ORIGINAL_PUBLICATION_PROOF",
       "research_only":True,"edge_status":"EDGE_UNVALIDATED","trading_changes":False,
       "limitations":["18 nonconsecutive free days, NOT a continuous multiyear historical database",
       "No previous-day warmup: conservative early missing slots",
       "Native OI units are NOT assumed comparable across exchange contracts",
       "Vendor timestamp indicates Tardis receipt, not execution-system receipt or exchange original publication",
       "No transaction or trading signal from these metrics"],
       "run_id":os.environ.get("GITHUB_RUN_ID")}
    content=json.dumps(report,ensure_ascii=False,sort_keys=True,indent=2).encode()
    digest=hashlib.sha256(content).hexdigest()
    key=ROOT+"/"+str(os.environ["GITHUB_RUN_ID"])+"-"+str(os.environ.get("GITHUB_RUN_ATTEMPT","1"))+".json"
    s3.put_object(Bucket=bucket,Key=key,Body=content,ContentType="application/json",Metadata={"sha256":digest})
    back=s3.get_object(Bucket=bucket,Key=key)["Body"].read(len(content)+1)
    if back!=content or hashlib.sha256(back).hexdigest()!=digest:
        raise ValueError("R2_WRITE_READBACK_SHA_MISMATCH")
    (OUT/"report.json").write_bytes(content)
    print("TARDIS_18_ASOF_SUMMARY",json.dumps({"case_count":len(results),
       "total_buckets":report["total_buckets"],"fresh":report["fresh_buckets"],
       "stale":report["stale_buckets"],"missing":report["missing_buckets"],
       "status":status,"r2_key":key,"sha256":digest,"edge":"EDGE_UNVALIDATED"},ensure_ascii=False))
if __name__=="__main__":
    main()
