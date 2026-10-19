#!/usr/bin/env python3
"""Bounded primary Binance historical OI daily sample audit 2020-2024.

Preserves duplicates, authentic SHA256, raw field parity and exact 5m gaps.
No claim that a sampled day proves all months or original publication time.
"""
import collections,csv,datetime as dt,hashlib,io,json,os,urllib.error
from decimal import Decimal,InvalidOperation
from pathlib import Path
from research.detector_earliest_archive_byte_audit_v1 import (
    get_limited,extract_zip,publisher_hash,r2,verify_r2)

ROOT="research/detector-binance-early-oi-selected-days/v1"
OUT=Path("detector_binance_early_oi_selected_days")
DATES={"BTCUSDT":("2020-09-01","2020-10-01","2021-01-01","2021-07-01",
                   "2021-12-01","2022-01-01","2022-07-01",
                   "2023-01-01","2023-07-01","2024-01-01"),
       "ETHUSDT":("2021-12-01","2022-01-01","2022-07-01","2023-01-01",
                  "2023-07-01","2024-01-01"),
       "SOLUSDT":("2021-12-01","2022-01-01","2022-07-01","2023-01-01",
                  "2023-07-01","2024-01-01")}
EXPECTED=22
UTC=dt.timezone.utc

def analyze_csv(blob,expected_day):
    reader=csv.DictReader(io.StringIO(blob.decode("utf-8-sig")))
    fields=reader.fieldnames or []
    if not {"create_time","sum_open_interest"}.issubset(fields):
        raise ValueError("METRICS_FIELDS_MISSING")
    groups=collections.defaultdict(list);bad=out_of_day=unaligned=0
    n=0; reversals=0;previous=None;timestamp_forms=collections.Counter()
    for row in reader:
        n+=1
        try:
            t=dt.datetime.fromisoformat(row["create_time"].replace("Z","+00:00"))
            if t.tzinfo is None:
                t=t.replace(tzinfo=UTC);timestamp_forms["naive_assumed_UTC_LABEL_ONLY"]+=1
            elif t.utcoffset()==dt.timedelta(0):
                timestamp_forms["aware_UTC"]+=1
            else:raise ValueError("NON_UTC_LABEL")
            if previous is not None and t<previous:reversals+=1
            previous=t
            if t.date().isoformat()!=expected_day:out_of_day+=1
            if t.second or t.microsecond or t.minute%5:unaligned+=1
            oi=Decimal(row["sum_open_interest"])
            if not oi.is_finite() or oi<=0:bad+=1
            groups[t.isoformat()].append((oi,row))
        except (ValueError,InvalidOperation,KeyError):
            bad+=1
    expected=[(dt.datetime.fromisoformat(expected_day).replace(tzinfo=UTC)+dt.timedelta(minutes=5*i)).isoformat() for i in range(288)]
    missing=[t for t in expected if t not in groups]
    duplicates={t:v for t,v in groups.items() if len(v)>1}
    conflict_pairs=sum(len({str(v[0]) for v in val})>1 for val in duplicates.values())
    conflict_rows=sum(len({json.dumps(v[1],sort_keys=True) for v in val})>1 for val in duplicates.values())
    extras=[t for t in groups if t not in expected]
    return {"raw_rows":n,"unique_source_5m_labels":len(groups),
       "expected_5m_labels":288,"missing_5m_labels":len(missing),
       "missing_labels_first_8":missing[:8],
       "duplicate_label_count":len(duplicates),
       "duplicate_extra_rows":sum(len(v)-1 for v in duplicates.values()),
       "duplicate_oi_value_conflicts":conflict_pairs,
       "duplicate_complete_row_conflicts":conflict_rows,
       "nonmonotonic_source_rows":reversals,
       "invalid_or_missing_values":bad,"out_of_day_rows":out_of_day,
       "unaligned_source_labels":unaligned,"extra_5m_labels":len(extras),
       "source_timestamp_formats":dict(timestamp_forms),
       "original_rows_mutated":False}

def audit_one(symbol,day):
    url=f"https://data.binance.vision/data/futures/um/daily/metrics/{symbol}/{symbol}-metrics-{day}.zip"
    item={"symbol":symbol,"date_utc":day,"source_url":url,
      "status":"UNVERIFIED","source_exchange_publication":"UNVERIFIED"}
    try:
        raw=get_limited(url,2_000_000)
        data,name=extract_zip(raw)
        sha=hashlib.sha256(raw).hexdigest()
        ck=publisher_hash(url,sha)
        item.update(source_sha256=sha,content_sha256=hashlib.sha256(data).hexdigest(),
           source_member=name,publisher_checksum_status=ck["status"])
        if ck["status"]!="PUBLISHER_SHA256_MATCH":
            item["status"]="PUBLISHER_PROVENANCE_UNVERIFIED"
            return item
        detail=analyze_csv(data,day);item["quality"]=detail
        item["status"]=("FULL_288_SOURCE_LABEL_SAMPLE" if detail["unique_source_5m_labels"]==288
          and not detail["missing_5m_labels"] and not detail["extra_5m_labels"]
          and not detail["invalid_or_missing_values"]
          and not detail["duplicate_oi_value_conflicts"]
          and not detail["duplicate_complete_row_conflicts"]
          else "SOURCE_SAMPLE_PARTIAL")
    except urllib.error.HTTPError as e:
        item.update(status="HTTP_UNAVAILABLE_NOT_DATA_ABSENCE",http=e.code)
    except Exception as e:
        item.update(status="SAMPLE_ERROR",error_type=type(e).__name__,error=str(e)[:150])
    return item

def main():
    OUT.mkdir(exist_ok=True)
    rows=[]
    for sym,days in DATES.items():
        for day in days:
            r=audit_one(sym,day);rows.append(r)
            print("BINANCE_EARLY_OI_DAY",json.dumps({
             "sym":sym,"date":day,"status":r["status"],
             "unique":r.get("quality",{}).get("unique_source_5m_labels"),
             "dup":r.get("quality",{}).get("duplicate_label_count"),
             "missing":r.get("quality",{}).get("missing_5m_labels"),
             "value_conflicts":r.get("quality",{}).get("duplicate_oi_value_conflicts"),
             "error":r.get("error_type")},ensure_ascii=False),flush=True)
    if len(rows)!=EXPECTED:raise ValueError("SAMPLE_CASE_COUNT_MISMATCH")
    report={"schema":"detector-binance-early-oi-selected-day-forensic-v1",
       "research_only":True,"cases":rows,
       "original_exchange_publication_time":"UNVERIFIED","edge_status":"EDGE_UNVALIDATED",
       "limits":["22 predeclared individual sample days not complete pre-2024 source",
         "source create_time is event label only, no first-published date inferred",
         "duplicate labels never silently removed",
         "all numeric values in Binance native units, no cross-venue comparison",
         "no trading positions or strategies modified"],"run_id":os.environ.get("GITHUB_RUN_ID")}
    data=json.dumps(report,sort_keys=True,indent=2,ensure_ascii=False).encode()
    digest=hashlib.sha256(data).hexdigest()
    key=ROOT+"/"+str(os.environ["GITHUB_RUN_ID"])+"-"+str(os.environ.get("GITHUB_RUN_ATTEMPT","1"))+".json"
    client=r2();bucket=os.environ["R2_BUCKET"]
    client.put_object(Bucket=bucket,Key=key,Body=data,ContentType="application/json",Metadata={"sha256":digest})
    if verify_r2(client,bucket,key,digest,len(data)+1)!=data:raise ValueError("R2_BYTE_MISMATCH")
    (OUT/"report.json").write_bytes(data)
    print("BINANCE_EARLY_OI_SUMMARY",json.dumps({
       "full_288_sample_days":sum(x["status"]=="FULL_288_SOURCE_LABEL_SAMPLE" for x in rows),
       "partial":sum(x["status"]=="SOURCE_SAMPLE_PARTIAL" for x in rows),
       "other":sum(x["status"] not in ("FULL_288_SOURCE_LABEL_SAMPLE","SOURCE_SAMPLE_PARTIAL") for x in rows),
       "total":len(rows),"r2_key":key,"sha256":digest,"edge_status":"EDGE_UNVALIDATED"},ensure_ascii=False))
if __name__=="__main__":
    main()
