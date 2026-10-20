#!/usr/bin/env python3
"""Independent daily SHA-reverified audit of the time-bounded OKX 3-metric pilot.

Uses actual on-run response receipt timestamps, not GitHub cron promises.
Reopens pinned run reports and (for v1 manifests with a raw key) each source
poll under its exact SHA256. Missing evidence remains MISSING, never PIT.
"""
import datetime as dt
import hashlib
import json
import math
import os
import statistics
from pathlib import Path

from research.detector_okx_3metric_forward_48h import PREFIX,SCHEMA,SYMBOLS,METRICS
from research.detector_okx_oi_48h_pilot import store
from research.detector_h1h10_verified_source_inventory import bytes_from_r2

OUT=Path("detector_h1h10_fastlane")
AUDIT_PREFIX="research/detector-okx-3metric-forward-audit/v1"
MAX_RUN_REPORTS=240
RAW_SAMPLE_LAST_N_RUNS=20
MAX_REPORT_BYTES=200000

def verified_json(s3,bucket,key,expected=None,cap=MAX_REPORT_BYTES):
    data,meta=bytes_from_r2(s3,bucket,key,cap)
    digest=hashlib.sha256(data).hexdigest()
    recorded=meta.get("sha256")
    if not recorded or digest!=recorded.lower():
        raise ValueError("SHA256_R2_OBJECT_METADATA_INVALID")
    if expected is not None and digest!=expected:
        raise ValueError("PINNED_RAW_OBJECT_SHA256_MISMATCH")
    return json.loads(data)

def check_one(s3,bucket,document,verify_raw=True):
    if (document.get("schema")!=SCHEMA or
        document.get("scope")!="RESEARCH_ONLY" or
        document.get("trading_actions") is not False or
        document.get("original_exchange_first_publication")!="UNVERIFIED" or
        document.get("causal_join_training")!="BLOCKED" or
        document.get("edge_status")!="EDGE_UNVALIDATED"):
        raise ValueError("FORWARD_SOURCE_SCOPE_OR_PIT_PROMOTED")
    quality=document.get("status")
    if quality not in ("SOURCES_ALL_RECEIVED","PARTIAL_SOURCE_FAILURE"):
        raise ValueError("UNKNOWN_SOURCE_RESEARCH_STATUS")
    fields=document.get("source_reports")
    if not isinstance(fields,dict) or len(fields)>9:
        raise ValueError("WRONG_NUMBER_OF_SOURCE_REPORTS")
    manifest_proofs=0;unlinked_legacy=0
    for name,value in fields.items():
        p=name.split("|")
        if len(p)!=2 or p[0] not in SYMBOLS or p[1] not in METRICS:
            raise ValueError("FOREIGN_SYMBOL_OR_METRIC")
        if not isinstance(value.get("row_count"),int) or value["row_count"]<1 or value["row_count"]>100:
            raise ValueError("INVALID_OBSERVATION_COUNT")
        receipt=value.get("response_received_ms")
        if not isinstance(receipt,int) or receipt<1600000000000:
            raise ValueError("MISSING_OBSERVED_RESPONSE_CLOCK")
        if not value.get("raw_sha256") or not value.get("raw_r2_key"):
            unlinked_legacy+=1
            continue
        key=value["raw_r2_key"];expected=value["raw_sha256"]
        if (not isinstance(key,str)
            or not key.startswith(PREFIX+"/polls/")
            or not key.endswith("/"+document["run"]+"-"+document["attempt"]+"-"+p[0]+"-"+p[1]+".json")
            or not isinstance(expected,str) or len(expected)!=64):
            raise ValueError("RAW_SOURCE_PROVENANCE_KEY_INVALID")
        if not verify_raw:
            continue
        raw=verified_json(s3,bucket,key,expected)
        if (raw.get("schema")!=SCHEMA or raw.get("metric")!=p[1]
            or raw.get("symbol")!=p[0]
            or raw.get("response_received_ms")!=receipt
            or raw.get("receipt_semantics")!="LOCAL_HTTP_RESPONSE_OBSERVED_NOT_EXCHANGE_PUBLICATION"
            or len(raw.get("rows",[]))!=value["row_count"]
            or raw.get("research_only") is not True):
            raise ValueError("RAW_SOURCE_PROVENANCE_MISMATCH")
        manifest_proofs+=1
    if quality=="SOURCES_ALL_RECEIVED" and len(fields)!=9:
        raise ValueError("ALL_RECEIVED_WITH_FEWER_THAN_9_SOURCES")
    for instrument in SYMBOLS:
        mark=document.get("coverage_gate",{}).get(instrument)
        if (not isinstance(mark,dict)
            or mark.get("causal_5m_rows_authorized")!=0
            or mark.get("training_authorized") is not False
            or mark.get("join_grade")!="SOURCE_LABEL_OVERLAP_ONLY_NO_CAUSAL_PIT"):
            raise ValueError("COLLECTOR_JOINS_NOT_CAUSAL")
    return manifest_proofs,unlinked_legacy

def millis(when):
    moment=dt.datetime.fromisoformat(when.replace("Z","+00:00"))
    if moment.tzinfo is None or moment.utcoffset()!=dt.timedelta(0):
        raise ValueError("FORWARD_DATE_MUST_BE_UTC")
    return int(moment.timestamp()*1000)

def summarize(docs):
    ids=set();receipts=[];success=0;partial=0;total_streams=0
    for d in docs:
        rid=d.get("run");att=d.get("attempt")
        if not isinstance(rid,str) or not rid.isdigit() or not isinstance(att,str) or not att.isdigit():
            raise ValueError("RUN_ID_OR_ATTEMPT_INVALID")
        if (rid,att) in ids:raise ValueError("DUPLICATE_RUN_ATTEMPT")
        ids.add((rid,att))
        timestamp=millis(d["observed_at_utc"])
        receipts.append(timestamp)
        if d["status"]=="SOURCES_ALL_RECEIVED":success+=1
        else:partial+=1
        total_streams+=len(d["source_reports"])
    ordered=sorted(receipts)
    spacing=[(b-a)/1000 for a,b in zip(ordered,ordered[1:])]
    if any(g<0 for g in spacing):raise ValueError("OBSERVATION_CLOCK_REGRESSED")
    gaps=[x for x in spacing if x>1200]
    return {"schema":"detector-h1h10-okx-3metric-real-receipt-audit-v1",
      "reports":len(docs),"all_sources_runs":success,
      "partial_runs":partial,"verified_source_streams":total_streams,
      "observed_start_utc":utc(ordered[0]) if ordered else None,
      "observed_last_utc":utc(ordered[-1]) if ordered else None,
      "median_actual_run_spacing_seconds":statistics.median(spacing) if spacing else None,
      "max_actual_run_spacing_seconds":max(spacing) if spacing else None,
      "gaps_over_20_minutes":len(gaps),
      "configured_15min_cron_is_not_a_5min_data_guarantee":True,
      "collector_first_receipt_is_not_exchange_first_release":True,
      "continuous_5m_pit_grade":"UNVERIFIED",
      "historical_h1h10_confirmation":"BLOCKED",
      "edge_status":"EDGE_UNVALIDATED","trading_actions":False}

def utc(ms):
    return dt.datetime.fromtimestamp(ms/1000,dt.timezone.utc).isoformat()

def main():
    import boto3
    bucket=os.environ["R2_BUCKET"]
    s3=boto3.client("s3",
         endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
         aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
         aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
    prefix=PREFIX+"/run-reports/"
    keys=[]
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket,Prefix=prefix):
        keys.extend(x["Key"] for x in page.get("Contents",[]) if x["Key"].endswith(".json"))
        if len(keys)>MAX_RUN_REPORTS:raise ValueError("PILOT_REPORT_SAFETY_CAP_EXCEEDED")
    documents=[];raw_verified=0;legacy=0;unsampled_raw=0
    sorted_keys=sorted(keys)
    for i,key in enumerate(sorted_keys):
        doc=verified_json(s3,bucket,key)
        sample=i>=len(sorted_keys)-RAW_SAMPLE_LAST_N_RUNS
        proven,old=check_one(s3,bucket,doc,verify_raw=sample)
        raw_verified+=proven;legacy+=old
        if not sample:
            unsampled_raw+=sum(
               1 for value in doc["source_reports"].values()
               if value.get("raw_r2_key") and value.get("raw_sha256"))
        documents.append(doc)
    report={**summarize(documents),"raw_sha_verified":raw_verified,
      "legacy_streams_missing_raw_pin":legacy,
      "older_stream_raw_pins_not_reread":unsampled_raw,
      "latest_runs_raw_sha_sample_cap":RAW_SAMPLE_LAST_N_RUNS,
      "readback_report_count":len(keys),
      "scope":"RESEARCH_ONLY",
      "replay_first_publication_pit":"UNVERIFIED",
      "source_prefix":prefix}
    if documents and raw_verified==0:
        report["raw_evidence_grade"]="RUN_REPORT_SHA_ONLY_RAW_PIN_PENDING"
    else:
        report["raw_evidence_grade"]="RAW_SHA_VERIFIED_WHERE_PRESENT"
    OUT.mkdir(exist_ok=True)
    ident=os.environ["GITHUB_RUN_ID"]+"-"+os.environ.get("GITHUB_RUN_ATTEMPT","1")
    key=AUDIT_PREFIX+"/"+ident+".json"
    stamp=store(s3,bucket,key,report)
    (OUT/"okx_three_metric_receipt_audit.json").write_text(
         json.dumps({**report,"r2_key":key,"sha256":stamp},indent=2,ensure_ascii=False),
         encoding="utf-8")
    print("OKX_THREE_METRIC_RECEIPT_AUDIT",json.dumps({
        "reports":len(documents),"source_streams":raw_verified,
        "legacy_raw_pins_missing":legacy,"observed_gaps_gt20min":report["gaps_over_20_minutes"],
        "causal_pit":"UNVERIFIED","r2_key":key,"sha256":stamp}),flush=True)
    summary=os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary,"a",encoding="utf-8") as fp:
            fp.write("## OKX three metric real receipt audit\n\n")
            fp.write(f"- Reports: {len(documents)}; SHA-verified raw streams: {raw_verified}\n")
            fp.write(f"- Historical raw pin missing: {legacy}; observed >20min gaps: {report['gaps_over_20_minutes']}\n")
            fp.write("- 5m PIT grade: UNVERIFIED; live trading: PROHIBITED\n")
if __name__=="__main__":main()
