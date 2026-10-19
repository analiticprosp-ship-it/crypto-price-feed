#!/usr/bin/env python3
"""Bounded Binance 5m OI raw archive first-observed-month reconnaissance.

Probe 1st, 15th and last of each month 2020-01..2021-12, for BTC/ETH/SOL;
then scan EVERY day in first observed positive month and previous month.
Byte+publisher SHA+ZIP CRC audit the earliest observed archive per coin.
HTTP 404 cannot prove universal data nonexistence or release-time semantics.
No trading, imputation, or original source modifications.
"""
import calendar,datetime as dt,hashlib,json,os,urllib.error,urllib.request
from pathlib import Path
from research.detector_binance_early_oi_days_v1 import audit_one
from research.detector_earliest_archive_byte_audit_v1 import r2,verify_r2

SYMBOLS=("BTCUSDT","ETHUSDT","SOLUSDT")
YEAR_MONTHS=tuple((y,m) for y in (2020,2021) for m in range(1,13))
OUT=Path("detector_binance_oi_early_origin")
R2_ROOT="research/detector-binance-oi-2020-2021-origin-recon/v1"
BASE="https://data.binance.vision/data/futures/um/daily/metrics"

def month_dates(year,month):
    return [f"{year:04d}-{month:02d}-{d:02d}"
      for d in range(1,calendar.monthrange(year,month)[1]+1)]
def calendar_probes(year,month):
    ds=month_dates(year,month)
    return (ds[0],ds[14],ds[-1])
def previous_month(year,month):
    return (year-1,12) if month==1 else (year,month-1)
def url_for(symbol,day):
    if symbol not in SYMBOLS or len(day)!=10:raise ValueError("INVALID_SOURCE_SELECTOR")
    return f"{BASE}/{symbol}/{symbol}-metrics-{day}.zip"
def head_status(symbol,day):
    url=url_for(symbol,day)
    req=urllib.request.Request(url,method="HEAD",
       headers={"User-Agent":"Detector-H1H10-Source-Origin-Forensics/1.0"})
    try:
        with urllib.request.urlopen(req,timeout=14) as r:
            return {"http":r.status,"state":"SOURCE_ARCHIVE_EXISTS" if r.status==200 else "HEAD_NON200_UNVERIFIED"}
    except urllib.error.HTTPError as e:
        return {"http":e.code,"state":"404_AT_CHECK_TIME" if e.code==404 else "HTTP_ACCESS_OR_SOURCE_UNVERIFIED"}
    except Exception as e:
        return {"http":None,"state":"NETWORK_UNVERIFIED","error_type":type(e).__name__}
def run_symbol(symbol,head=head_status,byte_audit=audit_one):
    # 72 date markers per symbol in 2020-2021, no claim they certify intervening days.
    probes=[]
    for year,month in YEAR_MONTHS:
      for date in calendar_probes(year,month):
        r=head(symbol,date)
        probes.append({"day":date,**r})
    positives=[x["day"] for x in probes if x["state"]=="SOURCE_ARCHIVE_EXISTS"]
    if not positives:
        return {"symbol":symbol,"status":"NO_POSITIVE_MONTH_IN_BOUNDED_SAMPLES",
          "month_sample_probes":probes,"day_boundary_probes":[],
          "original_exchange_publication":"UNVERIFIED"}
    first=min(positives)
    year=int(first[:4]);month=int(first[5:7])
    py,pm=previous_month(year,month)
    window=month_dates(py,pm)+month_dates(year,month)
    boundary=[]
    for date in window:
        r=head(symbol,date)
        boundary.append({"day":date,**r})
    positives_window=[x["day"] for x in boundary if x["state"]=="SOURCE_ARCHIVE_EXISTS"]
    first_confirmed=min(positives_window) if positives_window else None
    proof=byte_audit(symbol,first_confirmed) if first_confirmed else None
    expected="FULL_288_SOURCE_LABEL_SAMPLE"
    # Partial but source-authentic day may also verify first recorded archive
    verified=bool(proof and proof.get("status") in (expected,"SOURCE_SAMPLE_PARTIAL")
       and proof.get("publisher_checksum_status")=="PUBLISHER_SHA256_MATCH")
    return {"symbol":symbol,
      "status":"FIRST_OBSERVED_ARCHIVE_BYTES_VERIFIED" if verified else "FIRST_ARCHIVE_SOURCE_NOT_FULLY_VERIFIED",
      "earliest_month_sample_positive":first,
      "earliest_full_two_month_scan_positive":first_confirmed,
      "month_sample_probes":probes,"day_boundary_probes":boundary,
      "first_positive_archive_source_evidence":proof,
      "intermediate_months_not_scanned_every_day":True,
      "historical_absolute_start":"NOT_PROVEN",
      "original_exchange_publication":"UNVERIFIED"}
def main():
    OUT.mkdir(exist_ok=True)
    all_result=[run_symbol(s) for s in SYMBOLS]
    report={"schema":"detector-binance-oi-first-month-bounded-origin-recon-v1",
      "source":"Binance USD-M daily/metrics source archives",
      "sampled_range":"2020-01-01..2021-12-31",
      "calendar_sampling":"1st, 15th, final day of each month, all days of first detected month+preceding month",
      "symbols":all_result,"research_only":True,
      "edge_status":"EDGE_UNVALIDATED","portfolio_or_trading_modifications":False,
      "source_origin_proof":"SAMPLED_BOUNDARY_ONLY_NOT_ABSOLUTE",
      "original_exchange_publication":"UNVERIFIED",
      "limitations":["Unprobed intervening days in earlier months prevent absolute inception claim",
        "Source creation timestamps are not first exchange publication/availability",
        "HTTP HEAD existence and first positive source ZIP are separate evidence",
        "No silent deduplication or interpolation of historic source rows",
        "Producer's .CHECKSUM must match source ZIP to mark a sample verified"],
      "run_id":os.environ.get("GITHUB_RUN_ID")}
    payload=json.dumps(report,sort_keys=True,indent=2,ensure_ascii=False).encode()
    digest=hashlib.sha256(payload).hexdigest()
    key=R2_ROOT+"/"+str(os.environ["GITHUB_RUN_ID"])+"-"+str(os.environ.get("GITHUB_RUN_ATTEMPT","1"))+".json"
    client=r2();bucket=os.environ["R2_BUCKET"]
    client.put_object(Bucket=bucket,Key=key,Body=payload,ContentType="application/json",Metadata={"sha256":digest})
    if verify_r2(client,bucket,key,digest,len(payload)+1)!=payload:
        raise ValueError("R2_REPORT_READBACK_FAILED")
    (OUT/"report.json").write_bytes(payload)
    print("OI_FIRST_MONTH_SOURCE_SUMMARY",json.dumps({
      "probes":sum(len(x["month_sample_probes"])+len(x["day_boundary_probes"]) for x in all_result),
      "per_symbol":[{"symbol":x["symbol"],"status":x["status"],
        "first_month_sample":x.get("earliest_month_sample_positive"),
        "first_day_byte_checked":x.get("earliest_full_two_month_scan_positive"),
        "earlier_month_absolute_start":"NOT_PROVEN"} for x in all_result],
      "r2_key":key,"sha256":digest,"edge":"EDGE_UNVALIDATED"},ensure_ascii=False),flush=True)

if __name__=="__main__":
    main()
