#!/usr/bin/env python3
"""Exhaustively probe one historical Binance USD-M OI ZIP URL per date before
each known earliest byte-verified daily metric archive, without inventing PIT.

2019-01-01 through BTC 2020-09-01 / ETH and SOL 2021-12-01 inclusive.
All HTTP responses, including transient and unknown, preserved. HTTPS HEAD
does not reveal original archive upload time. First observed positive ZIP is
read and publisher SHA256/ZIP CRC reverified without altering any source rows.
No trade, portfolio, NAV or paid services.
"""
import argparse,collections,concurrent.futures,datetime as dt,hashlib,json,os
from pathlib import Path
from research.detector_source_depth_boundary_v1 import head_one
from research.detector_binance_early_oi_days_v1 import audit_one
from research.detector_earliest_archive_byte_audit_v1 import r2,verify_r2

FAMILY="binance_usdm_metrics_oi"
SOURCES={"BTCUSDT":"2020-09-01","ETHUSDT":"2021-12-01","SOLUSDT":"2021-12-01"}
START="2019-01-01"
PARENT_KEY="research/detector-binance-oi-earliest-month-day-boundary/v1/39315241590-1.json"
PARENT_SHA="3c3a85c9f21bc9e336c28b5b18afeb4ff08291b2b60098982cbc8fd6100c33b3"
ROOT="research/detector-binance-oi-preorigin-all-daily-head/v1"
OUT=Path("detector_binance_oi_preorigin_exhaustive")
MAX_PER_SYMBOL=1100
WORKERS=4

def grid(symbol):
    if symbol not in SOURCES:raise ValueError("UNAPPROVED_SYMBOL")
    begin=dt.date.fromisoformat(START)
    end=dt.date.fromisoformat(SOURCES[symbol])
    result=[]
    while begin<=end:
        result.append((FAMILY,symbol,begin.isoformat()))
        begin+=dt.timedelta(days=1)
    if len(result)>MAX_PER_SYMBOL or len(set(result))!=len(result):
        raise ValueError("GRID_OR_REQUEST_BUDGET_INVALID")
    return result

def pinned_baseline(report,symbol):
    if report.get("schema")!="detector-binance-oi-2019-2021-bounded-month-day-source-depth-v1":
        raise ValueError("PINNED_SOURCE_REPORT_SCHEMA_CHANGED")
    rows=[x for x in report.get("series",[]) if x.get("symbol")==symbol]
    if len(rows)!=1:
        raise ValueError("PINNED_SYMBOL_MISSING")
    row=rows[0]
    if (row.get("first_http_200_tested_date")!=SOURCES[symbol] or
        row.get("observed_http_grade")!="EARLIEST_SHA_CRC_SOURCE_AUDITED"):
        raise ValueError("PINNED_EARLIEST_SOURCE_NOT_VERIFIED")
    return {"key":PARENT_KEY,"sha256":PARENT_SHA,
        "first_verified_positive":row["first_http_200_tested_date"],
        "proof_grade":row["observed_http_grade"]}

def judge(rows,symbol,source_proof):
    expected=[x[2] for x in grid(symbol)]
    observed=[r["date"] for r in rows]
    if observed!=expected or len(rows)!=len(expected):
        raise ValueError("DAILY_GRID_INCOMPLETE_OR_WRONG_ORDER")
    counter=collections.Counter(str(x.get("http_status")) for x in rows)
    first=next((r for r in rows if r["http_status"]==200),None)
    earlier=[r["date"] for r in rows[:-1] if r["http_status"]==200]
    unknown=[{"day":r["date"],"http":r["http_status"],
              "error":r.get("error_type")}
             for r in rows if r["http_status"] not in (200,404)]
    baseline_ok=rows[-1]["http_status"]==200
    proof_ok=bool(source_proof and
      source_proof.get("status") in ("FULL_288_SOURCE_LABEL_SAMPLE","SOURCE_SAMPLE_PARTIAL")
      and source_proof.get("publisher_checksum_status")=="PUBLISHER_SHA256_MATCH")
    if unknown or not baseline_ok or not proof_ok:
        grade="INCOMPLETE_OR_SOURCE_REVISED_NO_EARLIEST_CLAIM"
    elif earlier:
        grade="EARLIER_HTTP200_ARCHIVE_BYTE_VALIDATED_NOT_GENESIS"
    else:
        grade="COMPLETE_PREORIGIN_DAILY_ENDPOINT_404_AT_CHECK"
    return {"status":grade,"symbol":symbol,
      "period_start":START,"period_end_inclusive":SOURCES[symbol],
      "total_dates":len(rows),"http_200":counter["200"],"http_404":counter["404"],
      "http_unknown":len(unknown),"unknown_details":unknown,
      "prior_http_200_dates":earlier,
      "first_positive_http_day":first["date"] if first else None,
      "baseline_head_ok":baseline_ok,"first_positive_publisher_sha_crc_ok":proof_ok,
      "dataset_absolute_origin":"NOT_PROVEN",
      "original_exchange_upload_and_publication":"UNVERIFIED",
      "historical_snapshot_tradable_PIT":"UNVERIFIED"}

def run_symbol(symbol):
    OUT.mkdir(exist_ok=True)
    s3=r2()
    bucket=os.environ["R2_BUCKET"]
    parent=json.loads(verify_r2(s3,bucket,PARENT_KEY,PARENT_SHA,1_000_000))
    baseline=pinned_baseline(parent,symbol)
    items=grid(symbol)
    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as pool:
        rows=list(pool.map(head_one,items))
    if len(rows)!=len(items):raise ValueError("EXHAUSTIVE_DAILY_RESPONSES_MISSING")
    positive=next((r for r in rows if r.get("http_status")==200),None)
    checked_day=positive["date"] if positive else SOURCES[symbol]
    sample=audit_one(symbol,checked_day)
    result=judge(rows,symbol,sample)
    record={"schema":"detector-binance-oi-preorigin-exhaustive-head-source-v1",
        "research_only":True,"source_family":FAMILY,
        "pinned_prior_evidence":baseline,"result":result,
        "all_exact_original_daily_head_observations":rows,
        "first_positive_zip_byte_audit":sample,
        "interpretation":"Exhaustive publicly-addressable daily archive URL checks only at collection time, NOT original exchange upload time or absolute source inception",
        "missing_observations_imputed":False,
        "futures_spot_nav_portfolio_changes":False,"edge_status":"EDGE_UNVALIDATED",
        "original_exchange_publication":"UNVERIFIED",
        "h1h10_confirmatory_test_allowed":False,
        "run_id":os.environ["GITHUB_RUN_ID"]}
    blob=json.dumps(record,ensure_ascii=False,sort_keys=True,indent=2).encode()
    sha=hashlib.sha256(blob).hexdigest()
    key=ROOT+"/"+symbol+"/"+str(os.environ["GITHUB_RUN_ID"])+"-"+str(os.environ.get("GITHUB_RUN_ATTEMPT","1"))+".json"
    s3.put_object(Bucket=bucket,Key=key,Body=blob,ContentType="application/json",Metadata={"sha256":sha})
    if verify_r2(s3,bucket,key,sha,len(blob)+1)!=blob:
        raise ValueError("R2_ORIGINAL_REPORT_READBACK_MISMATCH")
    (OUT/(symbol+".json")).write_bytes(blob)
    print("PREORIGIN_FULL_DAILY_OI_SUMMARY",json.dumps({"symbol":symbol,
       "status":result["status"],"total_urls":result["total_dates"],
       "http200":result["http_200"],"http404":result["http_404"],
       "unknown":result["http_unknown"],"earliest_positive":result["first_positive_http_day"],
       "prior_positive_dates":len(result["prior_http_200_dates"]),
       "source_sha_verified":result["first_positive_publisher_sha_crc_ok"],
       "r2_key":key,"sha256":sha,"edge":"EDGE_UNVALIDATED"},ensure_ascii=False),flush=True)
    if result["status"]=="INCOMPLETE_OR_SOURCE_REVISED_NO_EARLIEST_CLAIM":
        raise SystemExit("DAILY_SOURCE_404_CLAIM_NOT_SAFE_SEE_SAVED_REPORT")

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--symbol",choices=tuple(SOURCES),required=True)
    run_symbol(parser.parse_args().symbol)
