#!/usr/bin/env python3
"""Forensic exact timestamps of BTC USD-M OI on earliest observed 2020-09-01.

No sorting of raw record output, no imputation, no publication/PIT claims.
"""
import collections
import datetime as dt
import hashlib
import io
import json
import math
import os
from pathlib import Path
import csv
from research.detector_earliest_archive_byte_audit_v1 import (
    get_limited, extract_zip, publisher_hash, parse_time, r2, verify_r2)

URL="https://data.binance.vision/data/futures/um/daily/metrics/BTCUSDT/BTCUSDT-metrics-2020-09-01.zip"
OUT=Path("detector_btc_early_oi_forensic")
ROOT="research/detector-btc-early-oi-source-label-forensic/v1"
DAY=dt.date(2020,9,1)
UTC=dt.timezone.utc

def audit_records(data):
    records=csv.DictReader(io.StringIO(data.decode("utf-8-sig")))
    if not set(("create_time","sum_open_interest")).issubset(records.fieldnames or []):
        raise ValueError("OI_HEADER_NOT_COMPATIBLE")
    actual=[]; seen=collections.Counter();reversals=[];bad_values=0;not_in_day=0;misaligned=0;units=collections.Counter()
    previous=None;raw_count=0;bad_timestamp=0
    for row in records:
        raw_count+=1
        try:
            current, form=parse_time(row["create_time"])
            units[form]+=1
        except (ValueError,OverflowError,TypeError):
            bad_timestamp+=1;continue
        if previous is not None and current<previous and len(reversals)<15:
            reversals.append({"record_number":raw_count,
               "preceding_label":previous.isoformat(),"current_label":current.isoformat()})
        previous=current
        try:
            v=float(row["sum_open_interest"])
            if not math.isfinite(v) or v<=0:
                bad_values+=1
        except (ValueError,TypeError):
            bad_values+=1
        if current.date()!=DAY:
            not_in_day+=1
            continue
        if current.second or current.microsecond or current.minute%5:
            misaligned+=1
            continue
        seen[current.isoformat()]+=1
        actual.append(current)
    first=dt.datetime.combine(DAY,dt.time(0,0),UTC)
    ideal=[(first+dt.timedelta(minutes=5*i)).isoformat() for i in range(288)]
    missing=[stamp for stamp in ideal if seen[stamp]==0]
    duplicates=[{"label":k,"count":n} for k,n in seen.items() if n>1]
    return {
        "raw_rows":raw_count,"valid_aligned_in_day_rows":len(actual),
        "unique_valid_day_labels":len(seen),
        "duplicate_labels":duplicates[:25],"duplicate_label_count":len(duplicates),
        "duplicate_extra_rows":sum(n-1 for n in seen.values() if n>1),
        "reversal_examples":reversals,"out_of_order_first_15":len(reversals),
        "missing_labels_first_20":missing[:20],"missing_5m_label_count":len(missing),
        "first_raw_valid_label":actual[0].isoformat() if actual else None,
        "last_raw_valid_label":actual[-1].isoformat() if actual else None,
        "first_label_by_timestamp":min(actual).isoformat() if actual else None,
        "last_label_by_timestamp":max(actual).isoformat() if actual else None,
        "source_time_forms":dict(units),"invalid_oi_values":bad_values,
        "invalid_timestamps":bad_timestamp,"out_of_day_rows":not_in_day,
        "misaligned_rows":misaligned,
        "original_archive_reordered":False,"gap_imputation":False
    }

def main():
    OUT.mkdir(exist_ok=True)
    raw=get_limited(URL,4_000_000)
    csvdata,member=extract_zip(raw)
    sha=hashlib.sha256(raw).hexdigest()
    official=publisher_hash(URL,sha)
    if official["status"]!="PUBLISHER_SHA256_MATCH":
        raise ValueError("PUBLISHER_CHECKSUM_NOT_VERIFIED")
    result=audit_records(csvdata)
    if result["invalid_oi_values"] or result["invalid_timestamps"] or result["out_of_day_rows"]:
        quality="NUMERIC_OR_TIMELINE_PARTIAL"
    elif result["duplicate_label_count"] or result["out_of_order_first_15"] or result["missing_5m_label_count"]:
        quality="SOURCE_TIMESTAMP_QUALITY_PARTIAL"
    else:
        quality="FULL_288_SOURCE_LABEL_QUALITY_PASS"
    report={"schema":"detector-btc-earliest-oi-daily-forensic-v1",
        "source_url":URL,"source_date":DAY.isoformat(),"publisher_sha256":official,
        "archive_sha256":sha,"csv_sha256":hashlib.sha256(csvdata).hexdigest(),
        "zip_crc":"PASS","archive_member":member,"source_integrity":"PASS",
        "timestamp_quality":quality,"evidence":result,
        "scope":"exact earliest 2020-09-01 only; not a complete 2020-2026 series",
        "source_publication_time":"UNVERIFIED","causal_PIT":"UNVERIFIED",
        "units":"BINANCE_SOURCE_NATIVE_UNIT_NOT_EXTERNALLY_CONFIRMED",
        "research_only":True,"trading_actions":False,
        "run_id":os.environ.get("GITHUB_RUN_ID")}
    cli=r2();bucket=os.environ["R2_BUCKET"]
    body=json.dumps(report,sort_keys=True,ensure_ascii=False,indent=2).encode()
    digest=hashlib.sha256(body).hexdigest()
    key=ROOT+"/"+str(os.environ.get("GITHUB_RUN_ID"))+"-"+str(os.environ.get("GITHUB_RUN_ATTEMPT","1"))+".json"
    cli.put_object(Bucket=bucket,Key=key,Body=body,ContentType="application/json",Metadata={"sha256":digest})
    if verify_r2(cli,bucket,key,digest,len(body)+1)!=body:
        raise ValueError("R2_BYTE_MISMATCH")
    (OUT/"report.json").write_bytes(body)
    print("EARLY_BTC_OI_FORENSIC_SUMMARY",json.dumps({
      "source_integrity":"PASS","timestamp_quality":quality,
      "raw_rows":result["raw_rows"],"unique_labels":result["unique_valid_day_labels"],
      "duplicates":result["duplicate_label_count"],
      "out_of_order_examples":result["reversal_examples"],
      "missing_5m":result["missing_5m_label_count"],
      "time_forms":result["source_time_forms"],
      "first_by_time":result["first_label_by_timestamp"],
      "last_by_time":result["last_label_by_timestamp"],
      "r2_key":key,"sha256":digest},ensure_ascii=False))
if __name__=="__main__":
    main()
