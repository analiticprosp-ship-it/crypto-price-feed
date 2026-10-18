#!/usr/bin/env python3
"""H1-H10 research data preparation: vendor-asof OI + price, future targets isolated.

Four freely available first-of-month Tardis Binance Futures derivative_ticker
sample days. Not original exchange 5m metrics, not executable bids/asks, not
demonstration of profitable signals. NEVER feed future_labels into features.
"""
import csv
import datetime as dt
import gzip
import hashlib
import io
import json
import math
import os
from pathlib import Path
import boto3
from research.detector_tardis_fourday_independent_audit import (
    DAYS,SYMBOLS,MULTI,OCT,MAX_GZ,usec,get_bytes,assert_digest,
    read_manifest,raw_snapshots,verify_derived
)

ROOT="research/tardis-binance-oi-price-5m-join/v1"
FIVE_US=300_000_000
DELAY_US=30_000_000
AGE_LIMIT_S=120
HORIZONS=(1,3,12)  # 5m, 15m, 60m; NO cross-day labels
OUT=Path("detector_tardis_price_oi_join")
OUT.mkdir(exist_ok=True)

FEATURE_FIELDS=(
    "day","symbol","decision_time_utc","bucket_end_utc",
    "open_interest","oi_vendor_receipt_utc","oi_age_seconds",
    "oi_delta_5m","last_price","last_price_vendor_receipt_utc",
    "last_price_age_seconds","mark_price","mark_price_vendor_receipt_utc",
    "mark_price_age_seconds","past_last_price_return_5m","past_last_price_return_60m",
    "price_oi_feature_quality",
)
LABEL_FIELDS=(
    "day","symbol","decision_time_utc","label_5m_available_at_utc",
    "future_last_price_return_5m","label_15m_available_at_utc",
    "future_last_price_return_15m","label_60m_available_at_utc",
    "future_last_price_return_60m","label_quality",
)

def iso(us):
    return dt.datetime.fromtimestamp(us/1_000_000,dt.timezone.utc).isoformat()

def validated_number(raw,positive=False):
    try:
        n=float(raw)
        return raw if math.isfinite(n) and (n>0 if positive else n>=0) else None
    except (ValueError,TypeError):
        return None

def price_snapshots(blob,day,symbol):
    """Each price observation carries its OWN vendor receipt time."""
    start=usec(day+"T00:00:00+00:00")
    end=start+86_400_000_000
    records={"last_price":[],"mark_price":[]}
    stats={"source_rows":0,"last_price_valid":0,"mark_price_valid":0,
           "future_source_event_vs_receipt":0}
    with gzip.open(io.BytesIO(blob),"rt",encoding="utf-8-sig",newline="") as fp:
        rd=csv.DictReader(fp)
        required={"symbol","timestamp","local_timestamp","last_price","mark_price"}
        if not required.issubset(rd.fieldnames or []):raise ValueError("MISSING_PRICE_SOURCE_COLUMNS")
        for order,row in enumerate(rd):
            stats["source_rows"]+=1
            if order>=200000:raise ValueError("PRICE_SOURCE_ROWS_LIMIT")
            if row["symbol"]!=symbol:raise ValueError("PRICE_SOURCE_SYMBOL_MISMATCH")
            try:
                receipt=int(row["local_timestamp"]);event=int(row["timestamp"])
            except (ValueError,TypeError):continue
            if not start<=receipt<end:continue
            if event>receipt:
                stats["future_source_event_vs_receipt"]+=1
                # Vendor receipt proves observation, but anomalous event clock excluded.
                continue
            for field in records:
                raw=validated_number(row.get(field),positive=True)
                if raw is not None:
                    records[field].append((receipt,order,event,raw))
                    stats[field+"_valid"]+=1
    for v in records.values():v.sort(key=lambda r:(r[0],r[1]))
    return records,stats

def price_asof_by_bucket(records,day):
    """Two independent causal cursors for last_price and mark_price."""
    start=usec(day+"T00:00:00+00:00")
    cursors={k:0 for k in records};last={k:None for k in records}
    result=[]
    for i in range(288):
        decision=start+(i+1)*FIVE_US+DELAY_US
        snap={}
        for field,data in records.items():
            while cursors[field]<len(data) and data[cursors[field]][0]<=decision:
                last[field]=data[cursors[field]]
                cursors[field]+=1
            observed=last[field]
            if observed is None:
                snap[field]={"value":"","receipt":"","age":"","valid":False}
            else:
                receipt,_,_,raw=observed
                age=(decision-receipt)/1_000_000
                snap[field]={
                    "value":raw if age<=AGE_LIMIT_S else "",
                    "receipt":iso(receipt),"age":round(age,6),
                    "valid":age<=AGE_LIMIT_S,
                }
        result.append(snap)
    return result

def ratio_change(current,previous):
    if current in ("",None) or previous in ("",None):return ""
    base=float(previous)
    if base<=0:return ""
    return f"{float(current)/base-1:.12g}"

def build_join(day,symbol,derived_oi_csv,prices):
    """Feature and LABEL rows are kept in separate files by design."""
    oi=list(csv.DictReader(io.StringIO(derived_oi_csv.decode("utf-8-sig"))))
    if len(oi)!=288 or len(prices)!=288:raise ValueError("ROW_COUNT_NOT_288")
    features=[];labels=[]
    start=usec(day+"T00:00:00+00:00")
    for i in range(288):
        src=oi[i];price=prices[i]
        decision=start+(i+1)*FIVE_US+DELAY_US
        if src["symbol"]!=symbol or usec(src["decision_time_utc"])!=decision:
            raise ValueError("OI_SOURCE_ALIGNMENT_MISMATCH")
        oi_good=(src["open_interest"]!="" and
            src["asof_quality"] in ("OK_VENDOR_RECEIPT","OK_VENDOR_RECEIPT_PROVISIONAL"))
        if src["open_interest"] and usec(src["vendor_receipt_utc"])>decision:
            raise ValueError("LOOKAHEAD_OI_RECEIPT")
        latest=price["last_price"];mark=price["mark_price"]
        prev=features[-1] if i>=1 else None
        past60=features[i-12] if i>=12 else None
        row={
            "day":day,"symbol":symbol,"decision_time_utc":iso(decision),
            "bucket_end_utc":src["bucket_end_utc"],
            "open_interest":src["open_interest"] if oi_good else "",
            "oi_vendor_receipt_utc":src["vendor_receipt_utc"] if oi_good else "",
            "oi_age_seconds":src["observation_age_seconds"] if oi_good else "",
            "oi_delta_5m":ratio_change(src["open_interest"],prev["open_interest"]) if oi_good and prev else "",
            "last_price":latest["value"],
            "last_price_vendor_receipt_utc":latest["receipt"] if latest["valid"] else "",
            "last_price_age_seconds":latest["age"] if latest["valid"] else "",
            "mark_price":mark["value"],
            "mark_price_vendor_receipt_utc":mark["receipt"] if mark["valid"] else "",
            "mark_price_age_seconds":mark["age"] if mark["valid"] else "",
            "past_last_price_return_5m":ratio_change(latest["value"],prev["last_price"]) if prev else "",
            "past_last_price_return_60m":ratio_change(latest["value"],past60["last_price"]) if past60 else "",
            "price_oi_feature_quality":"OK_VENDOR_ASOF" if oi_good and latest["valid"] else "INCOMPLETE_OR_STALE",
        }
        for field in ("last_price","mark_price"):
            snap=price[field]
            if snap["valid"] and usec(snap["receipt"])>decision:
                raise ValueError("LOOKAHEAD_PRICE_RECEIPT")
        features.append(row)
    for i,row in enumerate(features):
        label={"day":day,"symbol":symbol,"decision_time_utc":row["decision_time_utc"],
               "label_quality":"LABELS_ARE_FUTURE_ONLY_NOT_INPUT_FEATURES"}
        for count in HORIZONS:
            suffix=f"{count*5}m"
            target=features[i+count] if i+count<288 else None
            label[f"label_{suffix}_available_at_utc"]=target["decision_time_utc"] if target else ""
            label[f"future_last_price_return_{suffix}"]=(
                ratio_change(target["last_price"],row["last_price"]) if target else "")
            if target and usec(target["decision_time_utc"])<=usec(row["decision_time_utc"]):
                raise ValueError("NON_FORWARD_LABEL")
        labels.append(label)
    return features,labels

def to_csv(rows,fields):
    out=io.StringIO(newline="")
    wr=csv.DictWriter(out,fieldnames=fields)
    wr.writeheader();wr.writerows(rows)
    return out.getvalue().encode()

def sha(obj):
    return hashlib.sha256(obj).hexdigest()

def store(s3,bucket,key,blob,content_type):
    digest=sha(blob)
    s3.put_object(Bucket=bucket,Key=key,Body=blob,ContentType=content_type,
                  Metadata={"sha256":digest})
    assert_digest(get_bytes(s3,bucket,key,len(blob)+1),digest)
    return digest

def main():
    bucket=os.environ["R2_BUCKET"]
    s3=boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
    multi=read_manifest(s3,bucket,MULTI+"/manifest.json","detector-tardis-multiday-vendor-asof-v1")
    oct_raw=read_manifest(s3,bucket,OCT+"/manifest.json","detector-tardis-binance-oi-receipt-asof-sample-v1")
    oct_derived=read_manifest(s3,bucket,OCT+"/derived/manifest.json","detector-tardis-oi-vendor-receipt-5m-asof-v1")
    outputs=[]
    for day in DAYS:
        for symbol in SYMBOLS:
            if day=="2026-10-01":
                x=next(x for x in oct_raw["records"] if x["symbol"]==symbol)
                y=next(y for y in oct_derived["outputs"] if y["symbol"]==symbol)
                source_key=x["r2_key"];source_hash=x["compressed_sha256"]
                oi_key=y["object_key"];oi_hash=y["sha256"]
            else:
                x=next(x for x in multi["records"] if x["day"]==day and x["symbol"]==symbol)
                source_key=x["original_key"];source_hash=x["source_sha256"]
                oi_key=x["derived_key"];oi_hash=x["derived_sha256"]
            raw=get_bytes(s3,bucket,source_key,MAX_GZ)
            oicsv=get_bytes(s3,bucket,oi_key,150000)
            assert_digest(raw,source_hash)
            assert_digest(oicsv,oi_hash)
            # Recheck the entire original OI join, not only stored CSV timestamps.
            verify_derived(raw_snapshots(raw,day,symbol),oicsv,day,symbol)
            obs,source_stats=price_snapshots(raw,day,symbol)
            prices=price_asof_by_bucket(obs,day)
            features,labels=build_join(day,symbol,oicsv,prices)
            root=f"{ROOT}/{day}"
            feature_key=f"{root}/{symbol}_vendor_asof_features.csv"
            label_key=f"{root}/{symbol}_future_price_labels.csv"
            feature_hash=store(s3,bucket,feature_key,to_csv(features,FEATURE_FIELDS),"text/csv")
            label_hash=store(s3,bucket,label_key,to_csv(labels,LABEL_FIELDS),"text/csv")
            stats={"day":day,"symbol":symbol,"source_key":source_key,"source_sha256":source_hash,
                 "oi_source_sha256":oi_hash,"features_key":feature_key,"features_sha256":feature_hash,
                 "labels_key":label_key,"labels_sha256":label_hash,
                 "rows":len(features),"features_oi_and_last_price_ready":sum(x["price_oi_feature_quality"]=="OK_VENDOR_ASOF" for x in features),
                 "last_price_ready":sum(bool(x["last_price"]) for x in features),
                 "mark_price_ready":sum(bool(x["mark_price"]) for x in features),
                 "future_5m_label_ready":sum(bool(x["future_last_price_return_5m"]) for x in labels),
                 "future_15m_label_ready":sum(bool(x["future_last_price_return_15m"]) for x in labels),
                 "future_60m_label_ready":sum(bool(x["future_last_price_return_60m"]) for x in labels),
                 "source_stats":source_stats}
            outputs.append(stats)
            print("TARDIS_PRICE_OI_JOIN_ROW",json.dumps({k:v for k,v in stats.items() if k not in ("source_stats",)},ensure_ascii=False),flush=True)
    report={"schema":"detector-h1-h10-tardis-price-oi-forward-targets-v1",
        "status":"FOUR_DAY_PRICE_OI_TARGET_DATASET_BUILT",
        "days":list(DAYS),"symbols":list(SYMBOLS),
        "future_price_label_horizons_minutes":[5,15,60],
        "features_publication_rule":"Tardis local_timestamp <= 5m bucket end +30s",
        "labels_rule":"Future LAST PRICE as observed at later decision time; never feature, no crossing sample-day boundary",
        "trading_price_warning":"Tardis last_price is vendor-received exchange derivative ticker, not executable bid/ask",
        "sample_selection_warning":"Four FREE FIRST-OF-MONTH days only; not representative OOS periods",
        "research_only":True,"no_trades_or_signals":True,
        "edge_status":"NOT_TESTED","source_publication_status":"EXCHANGE_PUBLICATION_UNVERIFIED",
        "run_id":os.environ["GITHUB_RUN_ID"],"outputs":outputs,
        "totals":{"feature_rows":sum(x["rows"] for x in outputs),
                  "ready_oi_and_price":sum(x["features_oi_and_last_price_ready"] for x in outputs),
                  "future_5m_labels":sum(x["future_5m_label_ready"] for x in outputs),
                  "future_15m_labels":sum(x["future_15m_label_ready"] for x in outputs),
                  "future_60m_labels":sum(x["future_60m_label_ready"] for x in outputs)},
        "limits":["5m-to-1h price targets are structural research labels, not trade returns net of fees or slippage",
                  "No full flow as-of joined, no H1-H10 strategy selection or statistical significance",
                  "Not the original Binance 5m OI summary metrics"]}
    blob=json.dumps(report,ensure_ascii=False,indent=2,sort_keys=True).encode()
    key=ROOT+"/manifest-"+os.environ["GITHUB_RUN_ID"]+".json"
    digest=store(s3,bucket,key,blob,"application/json")
    (OUT/"report.json").write_text(json.dumps({"r2_manifest_key":key,"sha256":digest,**report},ensure_ascii=False,indent=2))
    print("TARDIS_PRICE_OI_JOIN_SUMMARY",json.dumps({
        "status":report["status"],"r2_manifest_key":key,
        "sha256":digest,"totals":report["totals"],"edge_status":report["edge_status"]},ensure_ascii=False),flush=True)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"],"a",encoding="utf-8") as f:
            f.write("## H1-H10 research: source OI + as-of prices and SEPARATE future labels\n\n")
            f.write(f"- Feature rows: {report['totals']['feature_rows']}\n")
            f.write(f"- Valid OI + last price at decision: {report['totals']['ready_oi_and_price']}\n")
            for horizon in (5,15,60):f.write(f"- Future {horizon}m labels: {report['totals'][f'future_{horizon}m_labels']}\n")
            f.write("- No H1-H10 edge proven, no trades, no exchange publication-time guarantee.\n")

if __name__=="__main__":
    main()
