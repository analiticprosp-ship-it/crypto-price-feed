#!/usr/bin/env python3
"""Exact calendar gap ledger for previously SHA/CRC verified long OI label history.

An available five-minute event label is NOT the source's original publication
timestamp. Long coverage is exploratory metadata, never executable PIT proof.
"""
import collections,csv,datetime as dt,io,json,os
from pathlib import Path
import boto3

from research.detector_metrics_413day_source_lineage import (
    SORTED_RUN,index_archive,open_zip,label,numeric,
)
from research.detector_h1h10_archived_candidate_content_audit import (
    CENSUS_KEY,CENSUS_SHA,get_verified,digest
)

START=dt.date(2024,1,1)
END=dt.date(2026,10,16)
SYMBOLS=("BTCUSDT","ETHUSDT","SOLUSDT")
ROOT="research/detector-oi-long-metrics-exact-gap-ledger/v1"
OUT=Path("detector_oi_long_metrics_gap_ledger")
OUT.mkdir(exist_ok=True)


def calendar(start=START,end=END):
    days=[]
    d=start
    while d<=end:
        days.append(d)
        d+=dt.timedelta(days=1)
    return days


def analyze_one_csv(archive,member,start=START,end=END):
    slots=collections.defaultdict(set)
    n=invalid=duplicate=non_utc=out_of_scope=misaligned=0
    with archive.open(member) as f:
        rows=csv.DictReader(io.TextIOWrapper(f,encoding="utf-8-sig",newline=""))
        for row in rows:
            n+=1
            stamp,naive=label(row.get("timestamp_utc"))
            if stamp is None or naive:non_utc+=1;continue
            timestamp=dt.datetime.fromisoformat(stamp)
            value=numeric(row.get("sum_open_interest"))
            if value is None or row.get("sum_open_interest_valid")!="1":
                invalid+=1;continue
            date=timestamp.date()
            if not start<=date<=end:
                out_of_scope+=1;continue
            if timestamp.microsecond or timestamp.second or timestamp.minute%5:
                misaligned+=1;continue
            slot=(timestamp.hour*60+timestamp.minute)//5
            if slot in slots[date]:duplicate+=1
            slots[date].add(slot)
    series=calendar(start,end)
    issues=[];complete=[]
    all_observed=0;total_missing=0
    for d in series:
        seen=slots.get(d,set())
        all_observed+=len(seen)
        missing=288-len(seen)
        if missing<0:raise ValueError("MORE_THAN_288_UNIQUE_BUCKETS_PER_DAY")
        if missing:
            total_missing+=missing
            issues.append({"date_utc":d.isoformat(),"present":len(seen),"missing":missing,
              "first_missing_slots":["%02d:%02d"%(i//12,(i%12)*5)
                  for i in range(288) if i not in seen][:16]})
        else:
            complete.append(d)
    longest=0;current=0;best_start=best_end=None;run_start=None;prev=None
    for day in complete:
        if prev and day-prev==dt.timedelta(days=1):
            current+=1
        else:
            current=1;run_start=day
        if current>longest:longest=current;best_start=run_start;best_end=day
        prev=day
    return {
        "rows_seen":n,"unique_valid_observed_5m":all_observed,
        "expected_5m":len(series)*288,
        "calendar_days":len(series),"complete_5m_days":len(complete),
        "incomplete_or_missing_days":len(issues),
        "missing_5m_slots":total_missing,
        "misaligned_5m_labels":misaligned,
        "out_of_scope_numeric_rows":out_of_scope,
        "duplicate_label_rows":duplicate,
        "invalid_or_masked_numeric_rows":invalid,
        "invalid_or_naive_sorted_timestamp_rows":non_utc,
        "longest_consecutive_full_days":longest,
        "longest_streak_first_day":best_start.isoformat() if best_start else None,
        "longest_streak_last_day":best_end.isoformat() if best_end else None,
        "anomalous_days":issues,
        "publication_time":"ORIGINAL_EXCHANGE_PUBLICATION_UNVERIFIED"}


def main():
    bucket=os.environ["R2_BUCKET"]
    s3=boto3.client("s3",
       endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
       aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
       aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
    census=json.loads(get_verified(s3,bucket,CENSUS_KEY,CENSUS_SHA,1_000_000))
    meta=index_archive(census,SORTED_RUN)
    evidence={}
    with open_zip(s3,bucket,meta) as archive:
        for symbol in SYMBOLS:
            entry=symbol+"_research_5m.csv"
            if entry not in archive.namelist():raise ValueError("SOURCE_CSV_NOT_FOUND")
            value=analyze_one_csv(archive,entry)
            evidence[symbol]=value
            print("METRICS_GAP_SYMBOL",json.dumps({
                "symbol":symbol,
                "full_days":value["complete_5m_days"],
                "missing_5m":value["missing_5m_slots"],
                "incomplete_dates":value["anomalous_days"],
                "longest_days":value["longest_consecutive_full_days"],
                "longest_start":value["longest_streak_first_day"],
                "longest_end":value["longest_streak_last_day"],
                "duplicate_labels":value["duplicate_label_rows"]},ensure_ascii=False),flush=True)
    same_missing=all(
       [(v["anomalous_days"],v["longest_streak_first_day"],v["longest_streak_last_day"])
        for v in evidence.values()][0] ==
       (v["anomalous_days"],v["longest_streak_first_day"],v["longest_streak_last_day"])
        for v in evidence.values()
    )
    report={
        "schema":"detector-h1h10-2024-2026-metrics-exact-5m-gap-ledger-v1",
        "status":"OI_SOURCE_LABEL_GAP_LEDGER_COMPLETE",
        "source_archive_run":SORTED_RUN,
        "source_archive_sha256":meta["archive_expected_sha256"],
        "source_verified_lineage":"research/detector-metrics-413day-source-lineage/v1/39224085034-1.json",
        "window_start":START.isoformat(),"window_end":END.isoformat(),
        "symbols":evidence,"all_symbols_same_gap_ledger":same_missing,
        "research_only":True,"trading_actions":False,"edge_status":"EDGE_UNVALIDATED",
        "limitations":[
            "Source Binance futures/um/daily/metrics create_time is event/source label only",
            "This report does NOT prove first publication of any historical 5m OI measurement",
            "Do not use this history for causally executable H1–H10 strategy or P&L",
            "Missing 5m slots were neither imputed nor backfilled"],
        "run_id":os.environ["GITHUB_RUN_ID"],"source_commit":os.environ.get("GITHUB_SHA")}
    blob=json.dumps(report,ensure_ascii=False,sort_keys=True,indent=2).encode()
    key=ROOT+"/"+report["run_id"]+"-"+os.environ.get("GITHUB_RUN_ATTEMPT","1")+".json"
    check=digest(blob)
    s3.put_object(Bucket=bucket,Key=key,Body=blob,ContentType="application/json",
        Metadata={"sha256":check})
    if digest(s3.get_object(Bucket=bucket,Key=key)["Body"].read(len(blob)+1))!=check:
        raise ValueError("GAP_LEDGER_R2_SHA_READBACK_FAIL")
    (OUT/"report.json").write_text(json.dumps({**report,"r2_key":key,
        "r2_sha256":check},ensure_ascii=False,indent=2))
    print("METRICS_EXACT_GAP_SUMMARY",json.dumps({
        "status":report["status"],
        "across_assets_identical_gaps":same_missing,
        "by_asset":[{"symbol":k,"complete_days":v["complete_5m_days"],
            "missing":v["missing_5m_slots"],
            "max_streak_days":v["longest_consecutive_full_days"],
            "start":v["longest_streak_first_day"],
            "end":v["longest_streak_last_day"]} for k,v in evidence.items()],
        "r2_key":key,"sha256":check,"edge_status":"EDGE_UNVALIDATED"},ensure_ascii=False),flush=True)

if __name__=="__main__":
    main()
