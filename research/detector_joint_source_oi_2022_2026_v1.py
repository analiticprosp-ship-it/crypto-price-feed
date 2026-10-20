#!/usr/bin/env python3
"""Research only: joint 3-coin source OI calendar 2022-01-01..2026-10-16.

Append-only cross-period merge from TWO frozen SHA256 R2 reports:
* 2022-2023: eight original Binance publisher-checksummed daily source audit
  reports, previously joined with strict all-three quality masks.
* 2024-2026: sorted 3060-source long-series ZIP SHA+CRC lineage/gap ledger.
The source provenance levels differ and are explicitly preserved.
Source event-time availability is NOT publication time or execution-system PIT.
"""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
from research.detector_earliest_archive_byte_audit_v1 import r2,verify_r2

SOURCES={
    "2022_2023":{
      "key":"research/detector-2022-2023-joint-3coin-oi-daily-mask/v1/39319707132-1.json",
      "sha256":"d8a139875ef3e87976e980dfc9996a8976e108f3ed12acc3152fd63c1c202f28",
      "schema":"detector-h1h10-2022-2023-three-coin-joint-source-day-mask-v1"},
    "2024_2026":{
      "key":"research/detector-oi-long-metrics-exact-gap-ledger/v1/39224876509-1.json",
      "sha256":"bddb9d07d9ec22392cc631fbe3e16ec19530eac291587cf1725d49fbbe29e180",
      "schema":"detector-h1h10-2024-2026-metrics-exact-5m-gap-ledger-v1"}}
SYMBOLS=("BTCUSDT","ETHUSDT","SOLUSDT")
START=dt.date(2022,1,1)
BRIDGE=dt.date(2024,1,1)
END=dt.date(2026,10,16)
ROOT="research/detector-h1h10-joint-oi-source-mask-2022-2026/v1"
OUT=Path("detector_joint_source_oi_2022_2026")

def dates(first,last):
    if first>last:raise ValueError("INVERTED_SOURCE_DATE_GRID")
    out=[]
    while first<=last:
        out.append(first.isoformat())
        first+=dt.timedelta(days=1)
    return out

def check_parent(doc,name):
    if name not in SOURCES or doc.get("schema")!=SOURCES[name]["schema"]:
        raise ValueError("PINNED_REPORT_SCHEMA_MISMATCH")
    if doc.get("edge_status")!="EDGE_UNVALIDATED" or not doc.get("research_only"):
        raise ValueError("PINNED_REPORT_RESEARCH_SCOPE_CHANGED")

def early_2022_2023(doc):
    check_parent(doc,"2022_2023")
    if (doc.get("calendar_days")!=730 or doc.get("three_coin_joint_full_days")!=717
        or doc.get("source_complete_asset_days")!=2159
        or doc.get("partial_asset_days")!=31):
        raise ValueError("EARLY_SOURCE_COUNTS_MISMATCH")
    rows=doc.get("daily_source_quality_mask")
    if not isinstance(rows,list) or len(rows)!=730:raise ValueError("EARLY_DAILY_ROWS_MISSING")
    expected=dates(START,BRIDGE-dt.timedelta(days=1))
    observed=[r.get("day") for r in rows]
    if observed!=expected:raise ValueError("EARLY_DATE_GRID_NOT_EXACT")
    merged={}
    for row in rows:
        per=row.get("per_symbol")
        if not isinstance(per,dict) or set(per)!=set(SYMBOLS):
            raise ValueError("EARLY_THREE_COIN_PROVENANCE_INVALID")
        rejects=sorted(sym for sym in SYMBOLS if not per[sym].get("full_288_labels_and_numeric"))
        if rejects!=sorted(row.get("excluded_symbols",[])):
            raise ValueError("EARLY_ASSET_REJECTION_NOT_EXACT")
        clean=not rejects
        if clean!=row.get("three_coin_full_source_day"):
            raise ValueError("EARLY_DATE_CLEAN_CONTRADICTION")
        merged[row["day"]]={"date_utc":row["day"],"all_three_5m_source_clean":clean,
            "rejected_assets":rejects,"native_quality_by_asset":per,
            "provenance_level":"ORIGINAL_BINANCE_DAILY_ZIP_PUBLISHER_SHA_CRC",
            "exchange_first_publication":"UNVERIFIED"}
    if sum(x["all_three_5m_source_clean"] for x in merged.values())!=717:
        raise ValueError("EARLY_JOINT_CLEAN_TOTAL_MISMATCH")
    return merged

def late_2024_2026(doc):
    check_parent(doc,"2024_2026")
    if doc.get("status")!="OI_SOURCE_LABEL_GAP_LEDGER_COMPLETE":
        raise ValueError("LATE_GAP_AUDIT_NOT_COMPLETE")
    if doc.get("window_start")!="2024-01-01" or doc.get("window_end")!="2026-10-16":
        raise ValueError("LATE_PERIOD_MISMATCH")
    src=doc.get("symbols")
    if not isinstance(src,dict) or set(src)!=set(SYMBOLS) or not doc.get("all_symbols_same_gap_ledger"):
        raise ValueError("LATE_THREE_COIN_GAP_LEDGER_NOT_AGREED")
    bad={}
    for sym in SYMBOLS:
        q=src[sym]
        if (q.get("calendar_days")!=1020 or q.get("complete_5m_days")!=1017
            or q.get("missing_5m_slots")!=130 or q.get("duplicate_label_rows")!=0):
            raise ValueError("LATE_SOURCE_COUNTS_CHANGED")
        items=q.get("anomalous_days")
        if not isinstance(items,list) or len(items)!=3:
            raise ValueError("LATE_EXPECTED_THREE_ANOMALIES_MISSING")
        bad[sym]={}
        for r in items:
            date=r.get("date_utc")
            amount=r.get("missing")
            if date in bad[sym] or date not in dates(BRIDGE,END) or not isinstance(amount,int) or amount<=0:
                raise ValueError("LATE_BAD_GAP_RECORD")
            bad[sym][date]=amount
    if any(bad[s]!=bad[SYMBOLS[0]] for s in SYMBOLS[1:]):
        raise ValueError("LATE_COIN_GAP_SETS_DIVERGE")
    merged={}
    for day in dates(BRIDGE,END):
        rejected=[s for s in SYMBOLS if day in bad[s]]
        by_asset={s:{"full_288_numeric_source_labels":s not in rejected,
            "missing_5m_source_labels":bad[s].get(day,0)} for s in SYMBOLS}
        merged[day]={"date_utc":day,"all_three_5m_source_clean":not rejected,
            "rejected_assets":rejected,"native_quality_by_asset":by_asset,
            "provenance_level":"SHA_CRC_SORTED_SOURCE_CENSUS_GAP_LEDGER",
            "exchange_first_publication":"UNVERIFIED"}
    if (len(merged)!=1020 or
        sum(x["all_three_5m_source_clean"] for x in merged.values())!=1017):
        raise ValueError("LATE_JOINT_CLEAN_TOTAL_MISMATCH")
    return merged

def contiguous_ranges(merged):
    expected=dates(START,END)
    if list(merged)!=expected:raise ValueError("UNSORTED_OR_MISSING_SOURCE_DATES")
    streaks=[];first=None;previous=None;span=0
    for day in expected:
        good=merged[day]["all_three_5m_source_clean"]
        if good:
            if first is None:first=day;span=0
            previous=day;span+=1
        elif first is not None:
            streaks.append({"start":first,"end":previous,"calendar_days":span})
            first=None;previous=None;span=0
    if first is not None:streaks.append({"start":first,"end":previous,"calendar_days":span})
    return sorted(streaks,key=lambda a:(-a["calendar_days"],a["start"]))

def combine(early,late):
    if set(early)&set(late):raise ValueError("OVERLAPPING_SOURCE_PERIODS")
    merged={k:v for k,v in sorted({**early,**late}.items())}
    full_dates=dates(START,END)
    if list(merged)!=full_dates or len(merged)!=1750:
        raise ValueError("EXACT_1750_DATES_SOURCE_GRID_MISSING")
    count=sum(v["all_three_5m_source_clean"] for v in merged.values())
    if count!=1734:raise ValueError("EXPECTED_JOINT_COVERAGE_DRIFT")
    failures=[v for v in merged.values() if not v["all_three_5m_source_clean"]]
    if len(failures)!=16:raise ValueError("EXCLUDED_SOURCE_DAY_COUNT_DRIFT")
    runs=contiguous_ranges(merged)
    if sum(r["calendar_days"] for r in runs)!=count:
        raise ValueError("JOINT_RUN_ACCOUNTING_FAILED")
    years={}
    for day,record in merged.items():
        y=day[:4]
        if y not in years:years[y]={"calendar_days":0,"joint_full_days":0,"excluded_days":0}
        years[y]["calendar_days"]+=1
        years[y]["joint_full_days"]+=int(record["all_three_5m_source_clean"])
        years[y]["excluded_days"]+=int(not record["all_three_5m_source_clean"])
    return {"total_calendar_days":len(merged),"joint_full_days":count,
        "joint_excluded_days":len(failures),"by_year":years,
        "rejected_day_details":failures,
        "clean_streaks_longest_first":runs,
        "source_daily_mask":[merged[d] for d in full_dates],
        "data_cutoff_last_day":END.isoformat()}

def main():
    OUT.mkdir(exist_ok=True)
    s3=r2();bucket=os.environ["R2_BUCKET"]
    parents={}
    for name,ref in SOURCES.items():
        body=verify_r2(s3,bucket,ref["key"],ref["sha256"],2_000_000)
        parents[name]=json.loads(body)
        check_parent(parents[name],name)
        print("PINNED_JOINT_SOURCE_VERIFIED",json.dumps({
          "source_period":name,"key":ref["key"],"sha256":ref["sha256"]},ensure_ascii=False),flush=True)
    result=combine(early_2022_2023(parents["2022_2023"]),
                   late_2024_2026(parents["2024_2026"]))
    report={"schema":"detector-h1h10-2022-2026-joint-3coin-source-quality-register-v1",
       "inputs":SOURCES,"source_quality_levels_not_equivalent":True,
       "research_only":True,"edge_status":"EDGE_UNVALIDATED",
       "pit_release_timestamp":"UNVERIFIED",
       "tradable_5m_asof":"NOT_ESTABLISHED",
       "trading_nav_spot_futures_changes":False,
       "future_market_data_usage_for_h1h10":"PROHIBITED_WITHOUT_SEPARATE_PIT_PROOF",
       "limitations":["2022-23 verified exact native Binance daily metrics publisher SHA+CRC",
           "2024-26 verified SHA+CRC sorted derived source ZIP and original source lineage",
           "No claim that full event/source labels were known to trader at that decision moment",
           "All 16 excluded calendar days are preserved, no imputation of OI, no silent dedup",
           "No original exchange first publication, full price/flow asof or cost model"],
       **result,"run_id":os.environ["GITHUB_RUN_ID"]}
    body=json.dumps(report,sort_keys=True,ensure_ascii=False,indent=2).encode()
    digest=hashlib.sha256(body).hexdigest()
    key=ROOT+"/"+str(os.environ["GITHUB_RUN_ID"])+"-"+str(os.environ.get("GITHUB_RUN_ATTEMPT","1"))+".json"
    s3.put_object(Bucket=bucket,Key=key,Body=body,ContentType="application/json",Metadata={"sha256":digest})
    if verify_r2(s3,bucket,key,digest,len(body)+1)!=body:
        raise ValueError("R2_JOINT_SOURCE_WRITE_READBACK_MISMATCH")
    (OUT/"report.json").write_bytes(body)
    print("H1H10_JOINT_SOURCE_2022_2026_SUMMARY",json.dumps({
      "calendar_days":result["total_calendar_days"],"joint_full":result["joint_full_days"],
      "excluded":result["joint_excluded_days"],"by_year":result["by_year"],
      "top_three_streaks":result["clean_streaks_longest_first"][:3],
      "rejected_days":[x["date_utc"] for x in result["rejected_day_details"]],
      "r2_key":key,"sha256":digest,"causal_PIT":"UNVERIFIED",
      "edge":"EDGE_UNVALIDATED"},ensure_ascii=False),flush=True)
if __name__=="__main__":
    main()
