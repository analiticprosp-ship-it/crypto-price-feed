#!/usr/bin/env python3
"""Research-only exhaustive six remaining 2022/2023 Binance USDM OI quarters.

PR #106 already froze 2022Q1 and 2023Q1. This independently audits
2022Q2/Q3/Q4 and 2023Q2/Q3/Q4, with exactly one original daily Binance
metrics ZIP per symbol×calendar day and mandatory publisher SHA256+ZIP CRC.
No source deduplication, no filling absent labels, no release-time inference.
"""
import argparse
import collections
import datetime as dt
import hashlib
import json
import os
from pathlib import Path

from research.detector_binance_early_oi_days_v1 import audit_one
from research.detector_binance_oi_early_month_calendars_v1 import classify
from research.detector_binance_oi_pre2024_quarter_calendars_v1 import sample_quality, report_counts
from research.detector_earliest_archive_byte_audit_v1 import r2, verify_r2

SYMBOLS=("BTCUSDT","ETHUSDT","SOLUSDT")
QUARTERS=("2022Q2","2022Q3","2022Q4","2023Q2","2023Q3","2023Q4")
R2_ROOT="research/detector-binance-oi-2022-2023-rest-quarters/v1"
OUT=Path("detector_binance_oi_2022_2023_remaining")

def days_and_cases(quarter):
    if quarter not in QUARTERS:
        raise ValueError("NOT_AN_ALLOWED_QUARTER")
    year=int(quarter[:4])
    q=int(quarter[-1])
    first=3*(q-1)+1
    begin=dt.date(year,first,1)
    finish=dt.date(year+int(first+3>12),first+3 if first+3<=12 else first-9,1)
    ds=[];now=begin
    while now<finish:
        ds.append(now.isoformat())
        now+=dt.timedelta(days=1)
    if len(ds) not in (91,92) or not ds or len(set(ds))!=len(ds):
        raise ValueError("DAY_GRID_FAILURE")
    cases=[(symbol,day) for symbol in SYMBOLS for day in ds]
    if len(cases)!=3*len(ds) or len(set(cases))!=len(cases):
        raise ValueError("SOURCE_CASE_GRID_FAILURE")
    return ds,cases

def derive_missing_dates(rows,month):
    return [dict(symbol=x["symbol"],day=x["date_utc"],
                 quality=x["calendar_quality"],
                 missing_5m_labels=x.get("quality",{}).get("missing_5m_labels"),
                 invalid_oi_values=x.get("quality",{}).get("invalid_or_missing_values"),
                 duplicate_label_count=x.get("quality",{}).get("duplicate_label_count"),
                 status=x["status"]) for x in rows if x["calendar_quality"] not in
                 ("FULL_SINGLE_VALID","FULL_EXACT_DOUBLE_VALID")]

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--quarter",choices=QUARTERS,required=True)
    q=p.parse_args().quarter
    OUT.mkdir(exist_ok=True)
    days,cases=days_and_cases(q)
    results=[]
    for idx,(symbol,date) in enumerate(cases,1):
        info=audit_one(symbol,date)
        info["source_quality_class"]=classify(info)
        info["calendar_quality"]=sample_quality(info)
        results.append(info)
        src=info.get("quality",{})
        print("SOURCE_DAY_QUARTER",json.dumps({
           "quarter":q,"index":idx,"symbol":symbol,"day":date,
           "grade":info["calendar_quality"],"publisher_status":info.get("publisher_checksum_status"),
           "missing":src.get("missing_5m_labels"),"invalid":src.get("invalid_or_missing_values"),
           "duplicates":src.get("duplicate_label_count"),
           "error":info.get("error_type")},ensure_ascii=False),flush=True)
    summary=report_counts(results)
    per_symbol={s:report_counts([x for x in results if x["symbol"]==s]) for s in SYMBOLS}
    if summary["source_day_count"]!=len(cases):raise ValueError("SOURCE_DAY_ACCOUNTING_MISMATCH")
    if any(per_symbol[s]["source_day_count"]!=len(days) for s in SYMBOLS):
        raise ValueError("PER_SYMBOL_SOURCE_DAY_ACCOUNTING_FAILURE")
    if (summary["days_full_single_strict"]+summary["days_full_exact_double_strict"]+
        summary["days_partial_or_semantic"]+summary["days_source_unverified"]!=len(cases)):
        raise ValueError("SOURCE_QUALITY_ACCOUNTING_FAILURE")
    anomalies=derive_missing_dates(results,q)
    report={"schema":"detector-binance-oi-2022-2023-rest-quarter-daily-sources-v1",
        "preregistered_quarters":list(QUARTERS),"quarter":q,"symbols":list(SYMBOLS),
        "start_date":days[0],"end_date":days[-1],
        "expected_days_per_symbol":len(days),"raw_source_day_count":len(cases),
        "summary":summary,"per_symbol":per_symbol,
        "source_anomaly_calendar":anomalies,"original_source_provenance":results,
        "source_validation":"Publisher SHA256 .CHECKSUM and ZIP CRC; native CSV OI Decimal and precise 5m UTC source labels",
        "duplicates_preserved_in_source":True,"source_missing_5m_labels_not_imputed":True,
        "research_only":True,"edge_status":"EDGE_UNVALIDATED",
        "original_exchange_publication":"UNVERIFIED",
        "PIT_tradable_data_claim":"NOT_PROVEN",
        "trading_portfolio_changes":False,
        "limits":["Source event labels are NOT original publication timestamps",
                  "No claim of continuous valid pre-2024 source outside audited dates",
                  "Native OI units are venue and contract specific",
                  "Missing, duplicated and invalid original measurements remain visible",
                  "Not permission for H1-H10 confirmatory holdout or trading"],
        "run_id":os.environ["GITHUB_RUN_ID"],
        "source_script_sha_provenance":"GitHub immutable workflow commit"}
    blob=json.dumps(report,sort_keys=True,ensure_ascii=False,indent=2).encode()
    digest=hashlib.sha256(blob).hexdigest()
    key=R2_ROOT+"/"+q+"/"+str(os.environ["GITHUB_RUN_ID"])+"-"+str(os.environ.get("GITHUB_RUN_ATTEMPT","1"))+".json"
    s3=r2();bucket=os.environ["R2_BUCKET"]
    s3.put_object(Bucket=bucket,Key=key,Body=blob,ContentType="application/json",
                  Metadata={"sha256":digest})
    if verify_r2(s3,bucket,key,digest,len(blob)+1)!=blob:
        raise ValueError("R2_READBACK_CONTENT_FAILURE")
    (OUT/(q+".json")).write_bytes(blob)
    print("BINANCE_REMAINING_QUARTER_SUMMARY",json.dumps({
        "quarter":q,"status":"SOURCE_AUDITED_WITH_MASKS",
        "summary":summary,"per_symbol":per_symbol,"r2_key":key,
        "sha256":digest,"edge_status":"EDGE_UNVALIDATED",
        "original_publication":"UNVERIFIED"},ensure_ascii=False),flush=True)
    if summary["days_source_unverified"]:
        raise SystemExit("SOURCE_PROVENANCE_INCOMPLETE_CHECK_REPORT")
if __name__=="__main__":
    main()
