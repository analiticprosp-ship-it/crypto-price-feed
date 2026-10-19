#!/usr/bin/env python3
"""Research-only historical boundary exploration of Binance USD-M 5m OI daily ZIPs.

Predeclared full 2019-01..2021-12 monthly 1st/15th HTTP HEAD probes for
BTC/ETH/SOL, then full two-month day probes around each earliest monthly HTTP200.
For each earliest HTTP200 day, SHA256 publisher + ZIP CRC + native CSV 5m quality.
HEAD 404 != historical nonexistence; original exchange publication remains unknown.
"""
import concurrent.futures
import datetime as dt
import hashlib
import json
import os
from pathlib import Path

from research.detector_source_depth_boundary_v1 import head_one
from research.detector_binance_early_oi_days_v1 import audit_one
from research.detector_earliest_archive_byte_audit_v1 import r2,verify_r2

FAMILY="binance_usdm_metrics_oi"
COINS=("BTCUSDT","ETHUSDT","SOLUSDT")
YEARS=(2019,2020,2021)
MONTH_GRID=(1,15)
MAX_HEAD=650
R2_ROOT="research/detector-binance-oi-earliest-month-day-boundary/v1"
OUT=Path("detector_binance_oi_earliest_boundary")

def exhaustive_month_grid():
    dates=[(FAMILY,s,f"{y:04d}-{m:02d}-{d:02d}")
      for s in COINS for y in YEARS for m in range(1,13) for d in MONTH_GRID]
    if len(dates)!=216 or len(set(dates))!=216:raise ValueError("BAD_PREREG_MONTH_GRID")
    return dates

def month_dates(year,month):
    begin=dt.date(year,month,1)
    end=dt.date(year+int(month==12),1 if month==12 else month+1,1)
    result=[]
    while begin<end:
        result.append(begin.isoformat())
        begin+=dt.timedelta(days=1)
    return result

def refine_requests(first_month):
    requested=[]
    for symbol,month in first_month.items():
        if month is None:continue
        begin=dt.date.fromisoformat(month+"-01")
        prior=begin-dt.timedelta(days=1)
        for year,mon in ((prior.year,prior.month),(begin.year,begin.month)):
            for day in month_dates(year,mon):
                requested.append((FAMILY,symbol,day))
    return sorted(set(requested))

def earliest_positive(observations):
    found={}
    for symbol in COINS:
        ds=sorted(q["date"] for q in observations if q["symbol"]==symbol
                  and q["http_status"]==200)
        found[symbol]=ds[0][:7] if ds else None
    return found

def run():
    OUT.mkdir(exist_ok=True)
    checked={}
    def query(items):
        tasks=[q for q in items if q not in checked]
        if len(checked)+len(tasks)>MAX_HEAD:raise ValueError("HEAD_REQUEST_BUDGET_EXCEEDED")
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            for row in pool.map(head_one,tasks):
                checked[(row["family"],row["symbol"],row["date"])]=row
    query(exhaustive_month_grid())
    first=earliest_positive(list(checked.values()))
    query(refine_requests(first))
    per_symbol=[];byte_samples=[]
    for symbol in COINS:
        rec=sorted([q for q in checked.values() if q["symbol"]==symbol],
                   key=lambda q:q["date"])
        positives=[q for q in rec if q["http_status"]==200]
        negative=sum(q["http_status"]==404 for q in rec)
        unknown=[q["date"] for q in rec if q["http_status"] not in (200,404)]
        early=positives[0]["date"] if positives else None
        # Earliest positive day is a probed URL, not guaranteed provider inception.
        grade="BOUNDED_EARLIEST_HTTP200_AT_CHECK" if early else "NO_HTTP200_IN_GRID"
        proof=None
        if early:
            proof=audit_one(symbol,early)
            byte_samples.append(proof)
            if proof["status"] not in ("FULL_288_SOURCE_LABEL_SAMPLE","SOURCE_SAMPLE_PARTIAL"):
                grade="EARLIEST_BYTES_UNVERIFIED"
            else:
                grade="EARLIEST_SHA_CRC_SOURCE_AUDITED"
        per_symbol.append({"symbol":symbol,
             "monthly_first_and_midpoint_probe_start":"2019-01-01",
             "monthly_first_and_midpoint_probe_end":"2021-12-15",
             "sampled_monthly_dates_count":72,
             "tested_urls":len(rec),"http_200_urls":len(positives),
             "http_404_urls":negative,"unverified_response_dates":unknown,
             "first_http_200_tested_date":early,
             "source_byte_audit_status":proof["status"] if proof else None,
             "first_positive_source_5m_quality":proof.get("quality") if proof else None,
             "observed_http_grade":grade,
             "absolute_start_of_all_history":"NOT_ESTABLISHED",
             "earliest_exchange_publication":"UNVERIFIED",
             "causal_PIT":"UNVERIFIED"})
        print("EARLIEST_OI_MONTH_DAY_SYMBOL",json.dumps({
            "symbol":symbol,"positive":early,"quality":grade,
            "http200":len(positives),"http404":negative,
            "unknown":len(unknown),"source_sha256":proof.get("source_sha256") if proof else None,
            "missing_5m":proof.get("quality",{}).get("missing_5m_labels") if proof else None},ensure_ascii=False),flush=True)
    rows=sorted(checked.values(),key=lambda q:(q["symbol"],q["date"]))
    report={"schema":"detector-binance-oi-2019-2021-bounded-month-day-source-depth-v1",
       "tested_years":list(YEARS),"month_grid_days":list(MONTH_GRID),
       "methodology":"2019-2021 first/midmonth day HEAD, refine full earliest HTTP200 month and its previous month",
       "fetched_first_positive_day_full_zip_csv_publisher_checksum":True,
       "http_observations":rows,"source_byte_samples":byte_samples,
       "series":per_symbol,"research_only":True,
       "edge_status":"EDGE_UNVALIDATED","spot_futures_nav_trading_changes":False,
       "caveats":["Earliest sampled HTTP200 may not be actual earliest archive",
          "HTTP404 proves only URL absent when tested; does not prove underlying dataset absence",
          "No continuous calendar between scattered positive observations is inferred",
          "Original exchange release and first trade-executable publication are NOT verified",
          "Naive create_time interpreted UTC for label grid only; no publish timestamp"] ,
       "run_id":os.environ["GITHUB_RUN_ID"]}
    encoded=json.dumps(report,ensure_ascii=False,sort_keys=True,indent=2).encode()
    sha=hashlib.sha256(encoded).hexdigest()
    key=R2_ROOT+"/"+str(os.environ["GITHUB_RUN_ID"])+"-"+str(os.environ.get("GITHUB_RUN_ATTEMPT","1"))+".json"
    s3=r2();bucket=os.environ["R2_BUCKET"]
    s3.put_object(Bucket=bucket,Key=key,Body=encoded,ContentType="application/json",Metadata={"sha256":sha})
    if verify_r2(s3,bucket,key,sha,len(encoded)+1)!=encoded:raise ValueError("R2_READBACK_BYTE_MISMATCH")
    (OUT/"report.json").write_bytes(encoded)
    print("EARLIEST_OI_BOUNDARY_SUMMARY",json.dumps({"head_requests":len(rows),
        "series":[{"symbol":q["symbol"],"first":q["first_http_200_tested_date"],
                   "grade":q["observed_http_grade"],
                   "unknown":len(q["unverified_response_dates"])}
            for q in per_symbol],
        "r2_key":key,"sha256":sha,"status":"BOUNDED_SOURCE_HISTORY_NOT_ABSOLUTE_INCEPTION",
        "edge":"EDGE_UNVALIDATED"},ensure_ascii=False),flush=True)
    if any(q["observed_http_grade"]=="EARLIEST_BYTES_UNVERIFIED" for q in per_symbol):
        raise SystemExit("EARLIEST_SOURCE_PROVENANCE_PARTIAL")
if __name__=="__main__":
    run()
