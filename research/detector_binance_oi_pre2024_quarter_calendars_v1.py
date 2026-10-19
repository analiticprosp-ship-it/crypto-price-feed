#!/usr/bin/env python3
"""Bounded full daily-source Binance USD-M historical OI quarter audits.

Two independent quarterly jobs: 2022Q1 and 2023Q1, 3 symbols each.
Publisher SHA256, ZIP CRC, 5m calendar, duplicate and numerical field masks
are all checked by existing vetted audit_one. No source edits or imputation.
The original historical exchange publication time is NEVER inferred.
"""
import argparse,collections,datetime as dt,hashlib,json,os
from pathlib import Path
from research.detector_binance_early_oi_days_v1 import audit_one
from research.detector_binance_oi_early_month_calendars_v1 import classify,totals
from research.detector_earliest_archive_byte_audit_v1 import r2,verify_r2

QUARTERS=("2022Q1","2023Q1")
SYMBOLS=("BTCUSDT","ETHUSDT","SOLUSDT")
ROOT="research/detector-binance-oi-pre2024-quarter-calendars/v1"
OUT=Path("detector_binance_oi_pre2024_quarter")
UTC=dt.timezone.utc

def quarter_cases(quarter):
    if quarter not in QUARTERS:raise ValueError("QUARTER_NOT_PREREGISTERED")
    year=int(quarter[:4])
    day=dt.date(year,1,1);end=dt.date(year,4,1)
    days=[]
    while day<end:
        days.append(day.isoformat())
        day+=dt.timedelta(days=1)
    if len(days)!=90 or days[-1]!=f"{year}-03-31":
        raise ValueError("QUARTER_DAY_GRID_INVALID")
    cases=[(sym,day) for sym in SYMBOLS for day in days]
    if len(cases)!=270 or len(set(cases))!=270:
        raise ValueError("UNEXPECTED_SOURCE_COUNT")
    return cases

def sample_quality(rec):
    name=classify(rec)
    q=rec.get("quality",{})
    if (rec["status"]=="FULL_288_SOURCE_LABEL_SAMPLE" and
        q.get("invalid_or_missing_values",0)==0 and
        q.get("out_of_day_rows",0)==0 and
        q.get("unaligned_source_labels",0)==0 and
        q.get("nonmonotonic_source_rows",0)==0 and
        name=="288_UNIQUE_SINGLE_ROWS_FULL_DAY"):
        return "FULL_SINGLE_VALID"
    if (rec["status"]=="FULL_288_SOURCE_LABEL_SAMPLE" and
        q.get("invalid_or_missing_values",0)==0 and
        q.get("out_of_day_rows",0)==0 and
        q.get("unaligned_source_labels",0)==0 and
        q.get("nonmonotonic_source_rows",0)==0 and
        name=="288_UNIQUE_IDENTICAL_DOUBLES_FULL_DAY"):
        return "FULL_EXACT_DOUBLE_VALID"
    if rec["status"] not in ("FULL_288_SOURCE_LABEL_SAMPLE","SOURCE_SAMPLE_PARTIAL"):
        return "SOURCE_UNVERIFIED"
    return "PARTIAL_OR_SEMANTIC_ANOMALY"

def report_counts(rows):
    kinds=collections.Counter(r["calendar_quality"] for r in rows)
    base=totals(rows)
    return {**base,"source_day_count":len(rows),
        "days_full_single_strict":kinds["FULL_SINGLE_VALID"],
        "days_full_exact_double_strict":kinds["FULL_EXACT_DOUBLE_VALID"],
        "days_partial_or_semantic":kinds["PARTIAL_OR_SEMANTIC_ANOMALY"],
        "days_source_unverified":kinds["SOURCE_UNVERIFIED"],
        "days_invalid_oi_numeric":sum(bool(r.get("quality",{}).get("invalid_or_missing_values",0)) for r in rows),
        "days_missing_labels":sum(bool(r.get("quality",{}).get("missing_5m_labels",0)) for r in rows),
        "days_duplicate_content_conflicts":sum(bool(r.get("quality",{}).get("duplicate_complete_row_conflicts",0)) for r in rows),
        "invalid_oi_values":sum(r.get("quality",{}).get("invalid_or_missing_values",0) for r in rows),
        "sum_missing_5m_labels":sum(r.get("quality",{}).get("missing_5m_labels",0) for r in rows)}

def audit(quarter):
    OUT.mkdir(exist_ok=True)
    cases=quarter_cases(quarter)
    records=[]
    for index,(sym,day) in enumerate(cases):
        rec=audit_one(sym,day)
        rec["source_quality_class"]=classify(rec)
        rec["calendar_quality"]=sample_quality(rec)
        records.append(rec)
        q=rec.get("quality",{})
        print("OI_QUARTER_DAY",json.dumps({"quarter":quarter,"index":index+1,
          "symbol":sym,"day":day,"status":rec["status"],"quality":rec["calendar_quality"],
          "unique5m":q.get("unique_source_5m_labels"),
          "duplicates":q.get("duplicate_label_count"),
          "missing":q.get("missing_5m_labels"),
          "invalid":q.get("invalid_or_missing_values"),
          "error_type":rec.get("error_type")},ensure_ascii=False),flush=True)
    counts=report_counts(records)
    per_symbol={}
    for sym in SYMBOLS:
        group=[r for r in records if r["symbol"]==sym]
        per_symbol[sym]=report_counts(group)
        if len(group)!=90:raise ValueError("SYMBOL_CALENDAR_INCOMPLETE")
    report={"schema":"detector-binance-usdm-pre2024-oi-quarter-calendar-v1",
        "quarter":quarter,"venue":"Binance","market":"USD-M Futures",
        "dataset":"daily/metrics 5m historical open interest source labels",
        "scope":"90 consecutive calendar days for BTC/ETH/SOL; exactly 270 asset-days",
        "records":records,"summary":counts,"per_symbol":per_symbol,
        "provenance":"publisher .zip.CHECKSUM SHA256 + ZIP CRC + native numeric CSV + 288 expected 5m UTC labels",
        "original_source_rows_modified":False,"imputed_or_interpolated_values":0,
        "source_publication_time":"UNVERIFIED",
        "causal_PIT":"UNVERIFIED","research_only":True,
        "edge_status":"EDGE_UNVALIDATED","portfolio_trading_changes":False,
        "strict_gates":["An HTTP200 response alone never counts as a usable 5m day",
          "Incomplete days remain incomplete; exact duplicate source rows are never silently changed",
          "Source event timestamps are NOT original exchange publication timestamps",
          "Provider-historical source integrity is NOT a license for causal H1-H10 model validation",
          "This quarter does not certify all dates before 2024"],
        "run_id":os.environ.get("GITHUB_RUN_ID")}
    content=json.dumps(report,sort_keys=True,ensure_ascii=False,indent=2).encode()
    digest=hashlib.sha256(content).hexdigest()
    key=ROOT+"/"+quarter+"/"+str(os.environ["GITHUB_RUN_ID"])+"-"+str(os.environ.get("GITHUB_RUN_ATTEMPT","1"))+".json"
    client=r2()
    bucket=os.environ["R2_BUCKET"]
    client.put_object(Bucket=bucket,Key=key,Body=content,ContentType="application/json",
                      Metadata={"sha256":digest})
    if verify_r2(client,bucket,key,digest,len(content)+1)!=content:
        raise ValueError("R2_READBACK_MISMATCH")
    (OUT/(quarter+".json")).write_bytes(content)
    print("BINANCE_OI_PRE2024_QUARTER_SUMMARY",json.dumps({
      "quarter":quarter,"status":"QUARTER_SOURCE_CALENDAR_VALIDATED_WITH_QUALITY_MASKS",
      "summary":counts,"per_symbol":per_symbol,"r2_key":key,"sha256":digest,
      "causal_PIT":"UNVERIFIED","edge":"EDGE_UNVALIDATED"},ensure_ascii=False),flush=True)
    if counts["days_source_unverified"]:
        raise SystemExit("QUARTER_SOURCE_VERIFICATION_PARTIAL")

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--quarter",choices=QUARTERS,required=True)
    a=parser.parse_args()
    audit(a.quarter)
if __name__=="__main__":
    main()
