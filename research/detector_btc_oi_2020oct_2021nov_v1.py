#!/usr/bin/env python3
"""Research-only original BTC Binance USDM 5m OI daily calendar, 2020Oct-2021Nov.

These five disjoint source periods fill the previous full-calendar gap between
already-verified 2020-09 BTC and 2021-12 BTC. Source ZIP originals unmodified.
Every day publisher .CHECKSUM SHA256, ZIP CRC, original CSV native values and
288 5m UTC labels checked via pinned existing validated audit_one.
"""
import argparse,datetime as dt,hashlib,json,os
from pathlib import Path
from research.detector_binance_early_oi_days_v1 import audit_one
from research.detector_binance_oi_early_month_calendars_v1 import classify
from research.detector_binance_oi_pre2024_quarter_calendars_v1 import sample_quality,report_counts
from research.detector_earliest_archive_byte_audit_v1 import r2,verify_r2

SYMBOL="BTCUSDT"
SOURCE_WINDOWS={
  "2020Q4":("2020-10-01","2021-01-01"),
  "2021Q1":("2021-01-01","2021-04-01"),
  "2021Q2":("2021-04-01","2021-07-01"),
  "2021Q3":("2021-07-01","2021-10-01"),
  "2021OCTNOV":("2021-10-01","2021-12-01")}
COUNTS={"2020Q4":92,"2021Q1":90,"2021Q2":91,"2021Q3":92,"2021OCTNOV":61}
ROOT="research/detector-btc-usdm-oi-2020oct-2021nov/v1"
OUT=Path("detector_btc_2020oct_2021nov")

def source_dates(window):
    if window not in SOURCE_WINDOWS:raise ValueError("SOURCE_WINDOW_NOT_PREAPPROVED")
    lo,hi=SOURCE_WINDOWS[window]
    now=dt.date.fromisoformat(lo)
    last=dt.date.fromisoformat(hi)
    dates=[]
    while now<last:
        dates.append(now.isoformat())
        now+=dt.timedelta(days=1)
    if len(dates)!=COUNTS[window] or not dates or len(set(dates))!=len(dates):
        raise ValueError("CALENDAR_LENGTH_MISMATCH")
    return dates

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--window",choices=list(SOURCE_WINDOWS),required=True)
    window=p.parse_args().window
    OUT.mkdir(exist_ok=True)
    cases=[]
    for date in source_dates(window):
        item=audit_one(SYMBOL,date)
        item["source_quality_class"]=classify(item)
        item["calendar_quality"]=sample_quality(item)
        cases.append(item)
        qual=item.get("quality",{})
        print("BTC_2020_2021_SOURCE_DAY",json.dumps({
            "window":window,"date":date,"status":item["status"],
            "quality":item["calendar_quality"],
            "unique":qual.get("unique_source_5m_labels"),
            "duplicates":qual.get("duplicate_label_count"),
            "missing":qual.get("missing_5m_labels"),
            "invalid":qual.get("invalid_or_missing_values"),
            "row_conflicts":qual.get("duplicate_complete_row_conflicts"),
            "error_type":item.get("error_type")},ensure_ascii=False),flush=True)
    summary=report_counts(cases)
    if summary["source_day_count"]!=COUNTS[window]:raise ValueError("SOURCE_CASES_ACCOUNTING_FAILURE")
    if (summary["days_full_single_strict"]+summary["days_full_exact_double_strict"]+
        summary["days_partial_or_semantic"]+summary["days_source_unverified"]!=COUNTS[window]):
        raise ValueError("SOURCE_QUALITY_ACCOUNTING_FAILURE")
    anomalies=[{"date":row["date_utc"],"source_quality":row["calendar_quality"],
         "missing_labels":row.get("quality",{}).get("missing_5m_labels"),
         "invalid_native_values":row.get("quality",{}).get("invalid_or_missing_values"),
         "exact_duplicate_labels":row.get("quality",{}).get("duplicate_label_count"),
         "source_status":row["status"]} for row in cases if row["calendar_quality"] not in
         ("FULL_SINGLE_VALID","FULL_EXACT_DOUBLE_VALID")]
    report={"schema":"detector-btc-oi-2020oct-2021nov-daily-originals-v1",
       "window":window,"inclusive_first_date":source_dates(window)[0],
       "inclusive_last_date":source_dates(window)[-1],
       "source":"Binance USD-M BTCUSDT daily/metrics 5m historical source archives",
       "tested_day_count":COUNTS[window],"summary":summary,
       "defect_calendar":anomalies,"original_source_evidence":cases,
       "source_integrity_requirements":"publisher CHECKSUM SHA256; ZIP CRC; source CSV Decimal OI; exact 5m calendar",
       "mutated_source_rows":False,"interpolated_or_imputed_rows":0,
       "original_exchange_release":"UNVERIFIED",
       "causal_PIT":"UNVERIFIED","trading_permission":False,
       "edge_status":"EDGE_UNVALIDATED","research_only":True,
       "scope_warning":"Single BTC source-only calendar; not ETH/SOL, not original venue first publication, not trading eligibility",
       "run_id":os.environ.get("GITHUB_RUN_ID")}
    body=json.dumps(report,sort_keys=True,indent=2,ensure_ascii=False).encode()
    digest=hashlib.sha256(body).hexdigest()
    key=ROOT+"/"+window+"/"+str(os.environ["GITHUB_RUN_ID"])+"-"+str(os.environ.get("GITHUB_RUN_ATTEMPT","1"))+".json"
    s3=r2();bucket=os.environ["R2_BUCKET"]
    s3.put_object(Bucket=bucket,Key=key,Body=body,ContentType="application/json",Metadata={"sha256":digest})
    if verify_r2(s3,bucket,key,digest,len(body)+1)!=body:
        raise ValueError("R2_REPORT_HASH_READBACK_FAILED")
    (OUT/(window+".json")).write_bytes(body)
    print("BTC_2020_2021_GAP_WINDOW_SUMMARY",json.dumps({"window":window,
        "summary":summary,"r2_key":key,"sha256":digest,
        "publication":"UNVERIFIED","edge":"EDGE_UNVALIDATED"},ensure_ascii=False),flush=True)
    if summary["days_source_unverified"]:
        raise SystemExit("SOURCE_FETCH_OR_CHECKSUM_FAILURE_SEE_REPORT")

if __name__=="__main__":
    main()
