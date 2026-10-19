#!/usr/bin/env python3
"""Evidence-based inventory of verified Detector H1-H10 R2 inputs.

Reads the PINNED seven Tardis vendor-asof source manifests, validates all
corresponding 5m feature/label CSV bytes and event-time-only 3-day Spot/Perp
aggTrades from a SHA/CRC verified archived run. Measures actual OKX prospective
poll spacing without inventing missing 5-minute observations.

No execution, no signals, no fee/profit claims, no paid data, no silent gaps.
"""
import csv,datetime as dt,hashlib,io,json,math,os
from pathlib import Path

import boto3
from research.detector_h1_h10_r2_source import download as fetch_archived_zip
from research.detector_tardis_flow_boundary_audit import validate_flow

SYMBOLS=("BTCUSDT","ETHUSDT","SOLUSDT")
DAYS=("2024-01-01","2024-04-01","2025-01-01","2025-07-01",
      "2026-02-01","2026-09-01","2026-10-01")
OLD_DAYS=("2024-01-01","2025-01-01","2026-09-01","2026-10-01")
NEW_DAYS=("2024-04-01","2025-07-01","2026-02-01")
PRICE_OLD="research/tardis-binance-oi-price-5m-join/v1/manifest-39136673601.json"
PRICE_OLD_SHA="d194fa14729614106e045735bdc05d1c1f51a2e0f24c1e834feb4dedfde7ce55"
PRICE_NEW="research/tardis-binance-expanded-price-5m-join/v1/manifest-39210755313.json"
PRICE_NEW_SHA="8a6403cedfd9cf4f31e8642b38668d6a6cc78e1f8646b7c0cd412d79a37a14bd"
OI_NEW="research/tardis-binance-oi-expansion/v1/manifest.json"
OI_NEW_SHA="75db27426a90d1e877a1475c3470bbcbd0b666d3762327c7294d2b5098a17370"
OKX_REPORTS="research/oi-availability-okx/v1/pilot/run-reports/"
OUTROOT="research/detector-h1h10-evidence-inventory/v1"
ARTIFACT=Path("detector_h1h10_evidence_inventory")
ARTIFACT.mkdir(exist_ok=True)
MAX_BYTES=400000
MAX_OKX_REPORTS=300
TARGET_START="2024-01-01"
TARGET_END="2026-10-16"


def bytes_from_r2(client,bucket,key,cap=MAX_BYTES):
    obj=client.get_object(Bucket=bucket,Key=key)
    n=int(obj.get("ContentLength",-1))
    if n<=0 or n>cap:raise ValueError("SOURCE_SIZE_OUT_OF_BOUNDS")
    data=obj["Body"].read(cap+1)
    if len(data)!=n:raise ValueError("SOURCE_LENGTH_MISMATCH")
    return data,obj.get("Metadata",{})

def sha(data):return hashlib.sha256(data).hexdigest()

def verified(client,bucket,key,expected,cap=MAX_BYTES):
    if len(expected)!=64:raise ValueError("MISSING_OR_INVALID_PINNED_SHA")
    data,metadata=bytes_from_r2(client,bucket,key,cap)
    if sha(data)!=expected:raise ValueError("SOURCE_SHA256_MISMATCH")
    if metadata.get("sha256","").lower() not in ("",expected.lower()):
        raise ValueError("R2_SOURCE_METADATA_SHA256_MISMATCH")
    return data

def utc(value):
    t=dt.datetime.fromisoformat(value.replace("Z","+00:00"))
    if t.tzinfo is None or t.utcoffset()!=dt.timedelta(0):
        raise ValueError("NON_UTC_SOURCE_TIMESTAMP")
    return t

def parse_feature_pair(day,symbol,feature_csv,label_csv):
    features=list(csv.DictReader(io.StringIO(feature_csv.decode("utf-8-sig"))))
    labels=list(csv.DictReader(io.StringIO(label_csv.decode("utf-8-sig"))))
    if len(features)!=288 or len(labels)!=288:raise ValueError("NOT_288_ASOF_ROWS")
    start=utc(day+"T00:00:00+00:00")
    missing=stale=lastprice_missing=zero_future=0
    min_receipt=None;max_receipt=None
    for i,(f,l) in enumerate(zip(features,labels)):
        end=start+dt.timedelta(minutes=5*(i+1))
        decision=end+dt.timedelta(seconds=30)
        if (f["day"]!=day or l["day"]!=day
            or f["symbol"]!=symbol or l["symbol"]!=symbol
            or utc(f["decision_time_utc"])!=decision
            or utc(l["decision_time_utc"])!=decision
            or utc(f["bucket_end_utc"])!=end):
            raise ValueError("FEATURE_LABEL_ALIGNMENT_INVALID")
        oi=f.get("open_interest","")
        if not oi or f.get("price_oi_feature_quality")!="OK_VENDOR_ASOF":
            missing+=1
        price=f.get("last_price","")
        if not price:lastprice_missing+=1
        for col in ("oi_vendor_receipt_utc","last_price_vendor_receipt_utc"):
            raw=f.get(col,"")
            if raw:
                received=utc(raw)
                if received>decision:raise ValueError("FUTURE_VENDOR_RECEIPT")
                min_receipt=min(received,min_receipt) if min_receipt else received
                max_receipt=max(received,max_receipt) if max_receipt else received
        if oi and f.get("oi_age_seconds",""):
            age=float(f["oi_age_seconds"])
            if not math.isfinite(age) or age<0:raise ValueError("INVALID_RECEIPT_AGE")
            if age>120:stale+=1
        for h in (15,60):
            target=i+h//5
            label=f"future_last_price_return_{h}m"
            raw=l.get(label,"")
            available=l.get(f"label_{h}m_available_at_utc","")
            if target>=288:
                if raw or available:raise ValueError("CROSS_DAY_FUTURE_LABEL")
            elif raw and utc(available)-decision!=dt.timedelta(minutes=h):
                raise ValueError("FORWARD_LABEL_CLOCK_INVALID")
        if f.get("price_oi_feature_quality")!="OK_VENDOR_ASOF":
            zero_future+=1
    return {"feature_rows":288,"expected_buckets":288,"missing_vendor_asof":missing,
            "stale_vendor_oi_over_120_seconds":stale,"missing_last_price":lastprice_missing,
            "missing_joint_features":zero_future,
            "first_vendor_receipt_utc":min_receipt.isoformat() if min_receipt else None,
            "last_vendor_receipt_utc":max_receipt.isoformat() if max_receipt else None,
            "usable_feature_slots":288-missing}

def make_price_oi_records(client,bucket):
    old=json.loads(verified(client,bucket,PRICE_OLD,PRICE_OLD_SHA))
    new=json.loads(verified(client,bucket,PRICE_NEW,PRICE_NEW_SHA))
    if (old.get("schema")!="detector-h1-h10-tardis-price-oi-forward-targets-v1"
        or new.get("schema")!="detector-tardis-expanded-three-day-price-oi-join-v1"
        or tuple(old["days"])!=OLD_DAYS or tuple(new["days"])!=NEW_DAYS):
        raise ValueError("SOURCE_MANIFEST_DATES_INVALID")
    raw_new=json.loads(verified(client,bucket,OI_NEW,OI_NEW_SHA))
    if tuple(raw_new.get("dates",()))!=NEW_DAYS or len(raw_new.get("records",[]))!=9:
        raise ValueError("EXPANSION_RAW_MANIFEST_INVALID")
    index={}
    for doc in (old,new):
        for record in doc["outputs"]:
            key=(record["day"],record["symbol"])
            if key in index:raise ValueError("DUPLICATE_INVENTORY_ASSET_DAY")
            index[key]=record
    if set(index)!={(day,sym) for day in DAYS for sym in SYMBOLS}:
        raise ValueError("SOURCE_INVENTORY_COVERAGE_MISMATCH")
    expansion={(r["day"],r["symbol"]):r for r in raw_new["records"]}
    rows=[]
    for day in DAYS:
        for sym in SYMBOLS:
            info=index[(day,sym)]
            f=verified(client,bucket,info["features_key"],info["features_sha256"])
            l=verified(client,bucket,info["labels_key"],info["labels_sha256"])
            evidence=parse_feature_pair(day,sym,f,l)
            if day in NEW_DAYS:
                src=expansion[(day,sym)]
                raw_key=src["original_key"];raw_sha=src["source_sha256"]
                raw_record_count=src["source_quality"]["rows"]
            else:
                raw_key=info.get("source_key")
                raw_sha=info.get("source_sha256")
                raw_record_count=info.get("source_stats",{}).get("source_rows")
            if not raw_key or len(raw_sha or "")!=64:
                raise ValueError("SOURCE_ARCHIVE_PROVENANCE_MISSING")
            if raw_record_count is None or raw_record_count<=0:
                raise ValueError("SOURCE_ARCHIVE_COUNT_UNVERIFIED")
            status=("VERIFIED_VENDOR_RECEIPT_ONLY" if
                    evidence["missing_joint_features"]==0 and
                    evidence["stale_vendor_oi_over_120_seconds"]==0
                    else "PARTIAL_VENDOR_RECEIPT_ONLY")
            rows.append({
                "venue":"Binance USD-M via Tardis","market_type":"perpetual",
                "symbol":sym,"dataset":"open_interest_plus_last_price",
                "interval":"5m","date_start_utc":day,
                "date_end_utc":day,"rows":evidence["feature_rows"],
                "expected_rows":288,"missing_intervals":evidence["missing_joint_features"],
                "source_records":raw_record_count,"time_basis":"vendor_receipt_asof_not_exchange_publication",
                "availability_status":"VENDOR_RECEIPT_VERIFIED_EXCHANGE_PUBLICATION_UNVERIFIED",
                "source_object_key":raw_key,"source_sha256":raw_sha,
                "derived_object_key":info["features_key"],
                "derived_sha256":info["features_sha256"],
                "label_object_key":info["labels_key"],
                "label_sha256":info["labels_sha256"],
                "source_event_first":None,"source_event_last":None,
                "verified_first_receipt_utc":evidence["first_vendor_receipt_utc"],
                "verified_last_receipt_utc":evidence["last_vendor_receipt_utc"],
                "units":"source OI amount native; price USDT per coin",
                "status":status})
    return rows

def make_flow_records(client,bucket):
    """Use existing archived verified 3-day ZIP. Original trade publication unknown."""
    from research.detector_h1_h10_r2_source import download
    folder=ARTIFACT/"flow_verified"
    proof=download(client,bucket,
        "Detector H1-H10 Three-Day Real AggTrades Expansion",
        "detector-h1-h10-aggtrades-3day",str(folder))
    manifest=json.loads((folder/"manifest.json").read_text())
    if tuple(manifest.get("dates",()))!=("2026-09-01","2026-09-02","2026-09-03"):
        raise ValueError("FLOW_DATES_INVALID")
    all_items={(x["market"],x["symbol"]):x for x in manifest["datasets"]}
    if len(all_items)!=6:raise ValueError("FLOW_SOURCE_SERIES_MISSING")
    rows=[]
    for market in ("spot","perp"):
        for sym in SYMBOLS:
            meta=all_items[(market,sym)]
            file=folder/meta["output"]
            file_rows=list(csv.DictReader(file.open(encoding="utf-8-sig",newline="")))
            for day in ("2026-09-01","2026-09-02","2026-09-03"):
                originals=[a for a in meta["days"] if a["date"]==day]
                if len(originals)!=1:raise ValueError("FLOW_DAY_AMBIGUOUS")
                orig=originals[0]
                slots,q=validate_flow(file_rows,day,market,sym)
                count=len(slots)
                raw_ok=orig.get("status")=="VERIFIED" and len(orig.get("archive_sha256",""))==64
                status=("VERIFIED_EVENT_TIME_ONLY" if raw_ok and count==288
                        else "PARTIAL_EVENT_TIME_ONLY")
                rows.append({"venue":"Binance","market_type":market,
                    "symbol":sym,"dataset":"taker_aggtrades_5m","interval":"5m",
                    "date_start_utc":day,"date_end_utc":day,
                    "rows":count,"expected_rows":288,"missing_intervals":288-count,
                    "source_records":orig.get("aggtrades"),
                    "time_basis":"trade_event_time_only_not_first_publication",
                    "availability_status":"AGGTRADES_PUBLICATION_UNVERIFIED",
                    "source_object_key":proof["r2_object_key"],
                    "source_sha256":proof["archive_sha256"],
                    "derived_object_key":meta["output"],"derived_sha256":None,
                    "label_object_key":None,"label_sha256":None,
                    "source_event_first":day+"T00:00:00+00:00",
                    "source_event_last":day+"T23:55:00+00:00",
                    "verified_first_receipt_utc":None,"verified_last_receipt_utc":None,
                    "units":"quote flow USDT; count native aggTrades",
                    "status":status})
    return rows

def quantify_okx_runs(client,bucket):
    keys=[]
    for page in client.get_paginator("list_objects_v2").paginate(Bucket=bucket,Prefix=OKX_REPORTS):
        keys.extend(x["Key"] for x in page.get("Contents",[]) if x["Key"].endswith(".json"))
        if len(keys)>MAX_OKX_REPORTS:
            raise ValueError("OKX_RUN_REPORT_LIMIT")
    docs=[]
    for key in sorted(keys):
        raw,metadata=bytes_from_r2(client,bucket,key,140000)
        content_sha=sha(raw)
        if metadata.get("sha256") and metadata["sha256"].lower()!=content_sha:
            raise ValueError("OKX_REPORT_METADATA_SHA_MISMATCH")
        v=json.loads(raw)
        if v.get("schema")!="detector-okx-oi-5m-forward-48h-v1":
            raise ValueError("OKX_REPORT_SCHEMA_INVALID")
        docs.append(v)
    docs.sort(key=lambda x:utc(x["observed_at_utc"]))
    intervals=[]
    for previous,current in zip(docs,docs[1:]):
        gap=(utc(current["observed_at_utc"])-utc(previous["observed_at_utc"])).total_seconds()
        if gap<0:raise ValueError("RUN_CLOCK_REGRESSED")
        intervals.append(gap)
    counts={k:0 for k in ("POLL_PASS","POLL_PARTIAL")}
    for item in docs:counts[item["status"]]=counts.get(item["status"],0)+1
    report={"report_objects_read":len(docs),
        "observed_first_utc":docs[0]["observed_at_utc"] if docs else None,
        "observed_last_utc":docs[-1]["observed_at_utc"] if docs else None,
        "successful_runs":counts["POLL_PASS"],"partial_runs":counts["POLL_PARTIAL"],
        "other_runs":len(docs)-counts["POLL_PASS"]-counts["POLL_PARTIAL"],
        "gaps_observed_gt_10_minutes":sum(x>600 for x in intervals),
        "median_actual_gap_seconds":sorted(intervals)[len(intervals)//2] if intervals else None,
        "max_actual_gap_seconds":max(intervals) if intervals else None,
        "success_attempts_using_retry":sum(
            any(len(s.get("attempts",[]))>1 for s in item.get("symbols",[]))
            for item in docs),
        "pilot_end_utc":docs[0].get("pilot_end_utc") if docs else None,
        "venue_publication_verified":False,
        "limits":"R2 run-report observations only; missing cron runs cannot be synthesized"}
    return report

def summary_metrics(rows,okx):
    oi=[x for x in rows if x["dataset"]=="open_interest_plus_last_price"]
    flows=[x for x in rows if x["dataset"]=="taker_aggtrades_5m"]
    if len(oi)!=21 or len(flows)!=18:raise ValueError("INVENTORY_EXPECTED_SOURCE_ROWS_MISSING")
    calendar_span=(dt.date.fromisoformat(TARGET_END)-dt.date.fromisoformat(TARGET_START)).days+1
    known_oi_days={x["date_start_utc"] for x in oi if x["status"]=="VERIFIED_VENDOR_RECEIPT_ONLY"}
    known_flow_days={x["date_start_utc"] for x in flows if x["status"]=="VERIFIED_EVENT_TIME_ONLY"}
    return {
        "oi_source_asset_days":len(oi),
        "oi_verified_vendor_asof_days":len(known_oi_days),
        "oi_verified_5m_slots":sum(x["rows"]-x["missing_intervals"] for x in oi),
        "taker_event_asset_market_days":len(flows),
        "flow_verified_event_boundary_days":len(known_flow_days),
        "flow_event_time_5m_slots":sum(x["rows"] for x in flows),
        "target_calendar_days":calendar_span,
        "target_calendar_days_without_pinned_vendor_oi_evidence":calendar_span-len(known_oi_days),
        "oi_consecutive_day_streak_max":max_streak(known_oi_days),
        "flow_consecutive_day_streak_max":max_streak(known_flow_days),
        "okx":okx,
    }

def max_streak(days):
    values=sorted(dt.date.fromisoformat(x) for x in days)
    previous=None;current=0;best=0
    for day in values:
        current=current+1 if previous and day-previous==dt.timedelta(days=1) else 1
        best=max(best,current);previous=day
    return best

def main():
    bucket=os.environ["R2_BUCKET"]
    client=boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
    records=make_price_oi_records(client,bucket)
    records.extend(make_flow_records(client,bucket))
    okx=quantify_okx_runs(client,bucket)
    metrics=summary_metrics(records,okx)
    status="INVENTORY_PROVENANCE_VERIFIED_PARTIAL_HISTORY"
    doc={
        "schema":"detector-h1h10-real-evidence-inventory-v1","status":status,
        "scope":"ONLY pinned Tardis 7d price/OI, independently archived 3d Binance spot/perp aggTrades, measured OKX pilot run-reports",
        "scope_not_claimed":"Not an exhaustive listing of all GitHub artifacts or all R2 objects; other history may exist but is not attested here",
        "target_start_utc":TARGET_START,"target_end_utc":TARGET_END,
        "rows":records,"summary":metrics,
        "missing_or_unverified":{
            "continuous_same_venue_oi_7_to_14_days":"DATA_MISSING_IN_PINNED_SOURCE_SET",
            "original_tardis_binance_exchange_publication":"UNVERIFIED",
            "original_aggtrade_publication_and_first_available":"UNVERIFIED",
            "OKX_full_48_hour_pilot_completion":"PENDING_UNTIL_2026-10-20_13:34:59_UTC",
            "original_detector_A_point_in_time_history":"NOT_ASSESSED",
            "funding_liquidations_orderbook_full_PIT":"NOT_ASSESSED",
        },
        "scientific_conclusion":"NO_7_DAY_CONTINUOUS_OI_OR_EXECUTION_READY_FULL_FLOW_EVIDENCE_IN_THIS_PINNED_SCOPE",
        "edge_status":"EDGE_UNVALIDATED","research_only":True,
        "trading_actions":False,"source_commit":os.environ.get("GITHUB_SHA"),
        "run_id":os.environ["GITHUB_RUN_ID"],
    }
    contents=json.dumps(doc,sort_keys=True,ensure_ascii=False,indent=2).encode()
    key=OUTROOT+"/"+os.environ["GITHUB_RUN_ID"]+"-"+os.environ.get("GITHUB_RUN_ATTEMPT","1")+".json"
    digest=sha(contents)
    client.put_object(Bucket=bucket,Key=key,Body=contents,ContentType="application/json",Metadata={"sha256":digest})
    check=client.get_object(Bucket=bucket,Key=key)["Body"].read(len(contents)+1)
    if sha(check)!=digest:raise ValueError("INVENTORY_REPORT_READBACK_SHA_MISMATCH")
    (ARTIFACT/"inventory.json").write_text(json.dumps({
        **doc,"r2_key":key,"r2_sha256":digest},ensure_ascii=False,indent=2),encoding="utf-8")
    cols=list(records[0])
    with (ARTIFACT/"inventory.csv").open("w",newline="",encoding="utf-8") as fp:
        writer=csv.DictWriter(fp,fieldnames=cols)
        writer.writeheader();writer.writerows(records)
    print("H1H10_EVIDENCE_INVENTORY_SUMMARY",json.dumps({
        "status":status,"summary":metrics,"r2_key":key,"sha256":digest,
        "edge_status":"EDGE_UNVALIDATED"},ensure_ascii=False),flush=True)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"],"a",encoding="utf-8") as f:
            f.write("## Detector evidence inventory — verified pinned scope only\n\n")
            f.write(f"- Tardis asof OI: {metrics['oi_verified_vendor_asof_days']} nonconsecutive days, {metrics['oi_verified_5m_slots']} asset-slots\n")
            f.write(f"- Binance aggTrades: {metrics['flow_verified_event_boundary_days']} consecutive event-time days\n")
            f.write(f"- Max OI consecutive-day streak: {metrics['oi_consecutive_day_streak_max']} day(s)\n")
            f.write(f"- OKX pilot run-report objects read: {okx['report_objects_read']}\n")
            f.write("- Original venue publication and trade execution: UNVERIFIED. Edge: UNVALIDATED.\n")

if __name__=="__main__":main()
