#!/usr/bin/env python3
"""Full daily-source quality calendar for first BTC 2020 month and shared 2021 Dec.

Binds to independently vetted Binance original ZIP publisher SHA+CRC reader.
No deduplication or interpolation; event labels != historical first publication.
"""
import collections, datetime as dt, hashlib, json, os
from pathlib import Path
from research.detector_binance_early_oi_days_v1 import audit_one
from research.detector_earliest_archive_byte_audit_v1 import r2,verify_r2

ROOT="research/detector-binance-early-oi-month-calendars/v1"
OUT=Path("detector_binance_early_oi_month_calendars")
UTC=dt.timezone.utc

def month_days(year,month):
    start=dt.date(year,month,1)
    end=dt.date(year+(month==12),1 if month==12 else month+1,1)
    days=[];d=start
    while d<end:
        days.append(d.isoformat());d+=dt.timedelta(days=1)
    return days

def cases():
    result=[("BTCUSDT",day) for day in month_days(2020,9)]
    for symbol in ("BTCUSDT","ETHUSDT","SOLUSDT"):
        result.extend((symbol,day) for day in month_days(2021,12))
    if len(result)!=123 or len(set(result))!=123:raise ValueError("SOURCE_CASES_NOT_123_UNIQUE")
    return result

def classify(row):
    if row["status"]!="FULL_288_SOURCE_LABEL_SAMPLE":
        return "SOURCE_UNVERIFIED_OR_PARTIAL"
    quality=row["quality"]
    if quality["duplicate_label_count"]==0:return "288_UNIQUE_SINGLE_ROWS_FULL_DAY"
    if (quality["duplicate_label_count"]==288 and
        quality["duplicate_extra_rows"]==288 and
        quality["duplicate_oi_value_conflicts"]==0 and
        quality["duplicate_complete_row_conflicts"]==0):
        return "288_UNIQUE_IDENTICAL_DOUBLES_FULL_DAY"
    return "SOURCE_DUPLICATE_REGIME_PARTIAL"

def totals(rows):
    counters=collections.Counter(q["source_quality_class"] for q in rows)
    return {"selected_source_days":len(rows),
      "full_single_label_days":counters["288_UNIQUE_SINGLE_ROWS_FULL_DAY"],
      "full_exact_double_label_days":counters["288_UNIQUE_IDENTICAL_DOUBLES_FULL_DAY"],
      "partially_duplicated_or_quality_partial_days":counters["SOURCE_DUPLICATE_REGIME_PARTIAL"]+counters["SOURCE_UNVERIFIED_OR_PARTIAL"],
      "missing_5m_labels":sum(x.get("quality",{}).get("missing_5m_labels",0) for x in rows),
      "source_failures":sum(x["status"] not in ("FULL_288_SOURCE_LABEL_SAMPLE","SOURCE_SAMPLE_PARTIAL") for x in rows),
      "native_oi_duplicate_conflict_days":sum(bool(x.get("quality",{}).get("duplicate_oi_value_conflicts",0)) for x in rows)}

def main():
    OUT.mkdir(exist_ok=True)
    rows=[]
    for symbol,day in cases():
        rec=audit_one(symbol,day)
        rec["source_quality_class"]=classify(rec)
        rows.append(rec)
        q=rec.get("quality",{})
        print("EARLY_MONTH_SOURCE_DAY",json.dumps({
          "symbol":symbol,"date":day,"status":rec["status"],
          "quality_class":rec["source_quality_class"],
          "unique5m":q.get("unique_source_5m_labels"),
          "duplicates":q.get("duplicate_label_count"),
          "missing":q.get("missing_5m_labels"),"error":rec.get("error_type")},ensure_ascii=False),flush=True)
    summary=totals(rows)
    report={"schema":"detector-binance-early-oi-two-entire-month-calendar-v1",
      "scope":"2020-09 BTCUSDT all 30 calendar days; 2021-12 BTCUSDT ETHUSDT SOLUSDT all 31 calendar days each",
      "records":rows,"summary":summary,"data_type":"Binance USD-M daily/metrics 5m OI",
      "source_checks":"Publisher .zip.CHECKSUM SHA256; ZIP CRC; native CSV field and numeric validity; original 5m UTC event-time labels",
      "duplicate_handling":"Preserved and explicitly counted; never automatically removed",
      "no_imputation":True,"research_only":True,"edge_status":"EDGE_UNVALIDATED",
      "exchange_original_publication":"UNVERIFIED",
      "limits":["Two calendar months only, not full 2020-2023 continuity",
       "Original source event labels are not first available times",
       "Exact duplicate pairs remain in original archives; derived use requires explicit de-dup provenance and approval",
       "Native OI units not cross-venue comparable",
       "No live trading, P&L, NAV or limit changes"],
      "run_id":os.environ.get("GITHUB_RUN_ID")}
    body=json.dumps(report,sort_keys=True,ensure_ascii=False,indent=2).encode()
    sha=hashlib.sha256(body).hexdigest()
    key=ROOT+"/"+str(os.environ["GITHUB_RUN_ID"])+"-"+str(os.environ.get("GITHUB_RUN_ATTEMPT","1"))+".json"
    s3=r2();bucket=os.environ["R2_BUCKET"]
    s3.put_object(Bucket=bucket,Key=key,Body=body,ContentType="application/json",Metadata={"sha256":sha})
    if verify_r2(s3,bucket,key,sha,len(body)+1)!=body:raise ValueError("R2_WRITE_READBACK_BYTE_MISMATCH")
    (OUT/"report.json").write_bytes(body)
    print("BINANCE_TWO_MONTH_CALENDAR_SUMMARY",json.dumps({**summary,
      "r2_key":key,"sha256":sha,"status":"SOURCE_CALENDAR_RECORDED_WITH_QUALITY_MASKS",
      "publication":"UNVERIFIED","edge":"EDGE_UNVALIDATED"},ensure_ascii=False),flush=True)
    if summary["source_failures"]:raise SystemExit("SOURCE_FETCH_OR_PUBLISHER_VERIFICATION_PARTIAL")

if __name__=="__main__":
    main()
