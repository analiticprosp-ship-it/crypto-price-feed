#!/usr/bin/env python3
"""Bounded primary Binance BTCUSDT 2021 OI duplicate-transition search.

Uses publisher SHA/CRC verified source files; no inferred continuous history outside
the exact inspected months, no source file rewrites or publication/PIT claims.
"""
import calendar,datetime as dt,hashlib,json,os
from pathlib import Path
from research.detector_binance_early_oi_days_v1 import audit_one
from research.detector_earliest_archive_byte_audit_v1 import r2,verify_r2
ROOT="research/detector-btc-oi-2021-duplicate-transition/v1"
OUT=Path("detector_btc_oi_2021_transition")
FIRST_DAYS=tuple(f"2021-{month:02d}-01" for month in range(1,8))
LIMIT=90

def quality_key(row):
    q=row.get("quality")
    if row.get("status")!="FULL_288_SOURCE_LABEL_SAMPLE" or not q:
        return "UNVERIFIED"
    if q["duplicate_label_count"]==288 and q["duplicate_extra_rows"]==288:
        return "ALL_LABELS_DOUBLE"
    if q["duplicate_label_count"]==0:
        return "ALL_LABELS_SINGLE"
    return "MIXED_DUPLICATION"

def bracket(first_rows):
    states=[quality_key(x) for x in first_rows]
    if "UNVERIFIED" in states or "MIXED_DUPLICATION" in states:
        raise ValueError("ANCHOR_SOURCE_QUALITY_NOT_CONSISTENT")
    positions=[i for i,v in enumerate(states) if v=="ALL_LABELS_DOUBLE"]
    single=[i for i,v in enumerate(states) if v=="ALL_LABELS_SINGLE"]
    if not positions or not single:raise ValueError("TRANSITION_NOT_BRACKETED")
    left=max(positions)
    # A single-label month before the last double-label month is a reversal,
    # not a monotonic transition. Earlier code failed to reject this.
    if any(i<left for i in single):
        raise ValueError("DUPLICATION_REAPPEARS_AFTER_SINGLE_LABEL_MONTH")
    right=min(i for i in single if i>left)
    if right-left!=1:raise ValueError("TRANSITION_HAS_UNKNOWN_INTERVAL")
    if any(v=="ALL_LABELS_DOUBLE" for v in states[right+1:]):
        raise ValueError("DUPLICATION_REAPPEARS_IN_ANCHORS")
    return first_rows[left]["date_utc"],first_rows[right]["date_utc"]

def month_days(anchor):
    date=dt.date.fromisoformat(anchor)
    count=calendar.monthrange(date.year,date.month)[1]
    return [f"{date.year:04d}-{date.month:02d}-{d:02d}" for d in range(1,count+1)]

def main():
    OUT.mkdir(exist_ok=True)
    anchors=[audit_one("BTCUSDT",day) for day in FIRST_DAYS]
    result={"schema":"detector-btc-2021-oi-duplicate-transition-v1",
      "anchor_days":anchors,"anchor_quality":[quality_key(x) for x in anchors],
      "source_publication_time":"UNVERIFIED","research_only":True,
      "edge_status":"EDGE_UNVALIDATED","source_original_mutations":False,
      "trade_actions":False,"run_id":os.environ.get("GITHUB_RUN_ID")}
    try:
        left,right=bracket(anchors)
        requested=sorted(set(month_days(left)+month_days(right)))
        if len(requested)>LIMIT:raise ValueError("EXCEEDS_MONTH_BRACKET_LIMIT")
        days=[audit_one("BTCUSDT",day) for day in requested]
        result["days"]=days
        result["bracket_months"]=[left[:7],right[:7]]
        classified=[{"date_utc":x["date_utc"],"status":quality_key(x),
                     "publisher_sha":x.get("publisher_checksum_status")} for x in days]
        result["daily_states"]=classified
        first_single=next((x["date_utc"] for x in classified if x["status"]=="ALL_LABELS_SINGLE"),None)
        last_double=next((x["date_utc"] for x in reversed(classified) if x["status"]=="ALL_LABELS_DOUBLE"),None)
        result["candidate_first_single_day"]=first_single
        result["candidate_last_double_day"]=last_double
        if any(x["status"] not in ("ALL_LABELS_DOUBLE","ALL_LABELS_SINGLE") for x in classified):
            result["status"]="TRANSITION_PARTIAL_UNCERTIFIED"
        elif (last_double and first_single and
              dt.date.fromisoformat(first_single)-dt.date.fromisoformat(last_double)==dt.timedelta(days=1) and
              all(x["status"]=="ALL_LABELS_DOUBLE" for x in classified if x["date_utc"]<=last_double) and
              all(x["status"]=="ALL_LABELS_SINGLE" for x in classified if x["date_utc"]>=first_single)):
            result["status"]="EXACT_DAILY_LABEL_DUPLICATION_TRANSITION_OBSERVED"
        else:
            result["status"]="NONMONOTONIC_OR_UNBRACKETED_TRANSITION"
    except Exception as e:
        result.update(status="TRANSITION_GATE_UNVERIFIED",error_type=type(e).__name__,error=str(e)[:120])
    result["limits"]=[
      "If exact day is found, transition means only verified raw CSV label duplication semantics",
      "Does not prove vendor publication time nor OI value causal correctness",
      "Earlier history outside Jan-Jul 2021 not reverified by this script",
      "No source deduplication, no imputation and no trade signal calculation"]
    body=json.dumps(result,sort_keys=True,ensure_ascii=False,indent=2).encode()
    digest=hashlib.sha256(body).hexdigest()
    key=ROOT+"/"+str(os.environ["GITHUB_RUN_ID"])+"-"+str(os.environ.get("GITHUB_RUN_ATTEMPT","1"))+".json"
    client=r2();bucket=os.environ["R2_BUCKET"]
    client.put_object(Bucket=bucket,Key=key,Body=body,ContentType="application/json",Metadata={"sha256":digest})
    if verify_r2(client,bucket,key,digest,len(body)+1)!=body:raise ValueError("R2_READBACK_MISMATCH")
    (OUT/"report.json").write_bytes(body)
    print("BTC_OI_2021_DUPLICATE_TRANSITION_SUMMARY",json.dumps({
      "status":result["status"],
      "anchor_states":result["anchor_quality"],"bracket":result.get("bracket_months"),
      "first_single":result.get("candidate_first_single_day"),
      "last_double":result.get("candidate_last_double_day"),
      "dates_audited":len(result.get("days",[])),
      "partial_days":sum(x["status"]!="FULL_288_SOURCE_LABEL_SAMPLE" for x in result.get("days",[])),
      "r2_key":key,"sha256":digest,"error":result.get("error")},ensure_ascii=False))
if __name__=="__main__":
    main()
