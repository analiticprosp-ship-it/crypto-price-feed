#!/usr/bin/env python3
"""Exploratory chronological PRICE vs PRICE+OI ablation, research only.

Fixed features/horizons, immutable verified R2 input, successive full-day
holdouts. Not H1-H10 strategy validation, trading signals, or P&L.
First-of-month days and overlapping targets make any statistical edge UNPROVEN.
"""
import csv, datetime as dt, hashlib, io, json, math, os
from pathlib import Path
import boto3

ROOT="research/tardis-binance-oi-price-5m-join/v1"
INPUT_KEY=ROOT+"/manifest-39136673601.json"
INPUT_SHA="d194fa14729614106e045735bdc05d1c1f51a2e0f24c1e834feb4dedfde7ce55"
OUTROOT="research/tardis-price-oi-chronological-ablation/v1"
DAYS=("2024-01-01","2025-01-01","2026-09-01","2026-10-01")
SYMBOLS=("BTCUSDT","ETHUSDT","SOLUSDT")
HORIZONS=(15,60)
BASE_FIELDS=("past_last_price_return_5m","past_last_price_return_60m")
OI_FIELD="oi_delta_5m"
REGULARIZATION=0.15
LEARNING_RATE=0.15
ITERATIONS=240
MAX_SOURCE_BYTES=450_000
OUT=Path("detector_price_oi_chrono_ablation");OUT.mkdir(exist_ok=True)


def sha(data):return hashlib.sha256(data).hexdigest()
def utc(string):
    d=dt.datetime.fromisoformat(string.replace("Z","+00:00"))
    if d.tzinfo is None or d.utcoffset()!=dt.timedelta(0):
        raise ValueError("NON_UTC_TIMESTAMP")
    return d
def read(s3,bucket,key,digest,max_bytes=MAX_SOURCE_BYTES):
    r=s3.get_object(Bucket=bucket,Key=key)
    if not 0<int(r["ContentLength"])<=max_bytes:
        raise ValueError("R2_SOURCE_SIZE_INVALID")
    data=r["Body"].read(max_bytes+1)
    if len(data)>max_bytes or sha(data)!=digest:raise ValueError("R2_SOURCE_HASH_INVALID")
    return data
def csv_rows(blob):
    return list(csv.DictReader(io.StringIO(blob.decode("utf-8-sig"))))
def finite_value(row,column):
    try:
        x=float(row[column])
        return x if math.isfinite(x) else None
    except (ValueError,KeyError,TypeError):return None

def validate_and_build(feature_blob,label_blob,day,symbol):
    features=csv_rows(feature_blob);labels=csv_rows(label_blob)
    if len(features)!=288 or len(labels)!=288:raise ValueError("EXPECTED_288_ROWS")
    fhead=set(features[0]);lhead=set(labels[0])
    required=set(BASE_FIELDS)|{OI_FIELD,"day","symbol","decision_time_utc",
      "open_interest","last_price","oi_vendor_receipt_utc",
      "last_price_vendor_receipt_utc","price_oi_feature_quality"}
    if not required.issubset(fhead):raise ValueError("MISSING_FEATURE_COLUMNS")
    if any(col.startswith("future_") or col.startswith("label_") for col in fhead):
        raise ValueError("FUTURE_TARGET_IN_FEATURE_FILE")
    if not {"future_last_price_return_15m","future_last_price_return_60m",
            "label_15m_available_at_utc","label_60m_available_at_utc"}.issubset(lhead):
        raise ValueError("MISSING_TARGET_COLUMNS")
    usable={15:[],60:[]};skips={15:0,60:0}
    for i,(f,l) in enumerate(zip(features,labels)):
        if f["day"]!=day or l["day"]!=day or f["symbol"]!=symbol or l["symbol"]!=symbol:
            raise ValueError("SOURCE_DAY_OR_SYMBOL_MISMATCH")
        t=utc(f["decision_time_utc"])
        if t!=utc(l["decision_time_utc"]):raise ValueError("LABEL_FEATURE_CLOCK_MISMATCH")
        if t.date()!=dt.date.fromisoformat(day) and not (i==287 and t.date()==dt.date.fromisoformat(day)+dt.timedelta(days=1)):
            raise ValueError("DECISION_NOT_IN_SOURCE_DAY")
        start=utc(day+"T00:00:00+00:00")
        expected=start+dt.timedelta(minutes=5*(i+1),seconds=30)
        if t!=expected:raise ValueError("WRONG_DECISION_TIME")
        for name in ("oi_vendor_receipt_utc","last_price_vendor_receipt_utc"):
            if f[name] and utc(f[name])>t:
                raise ValueError("FUTURE_VENDOR_RECEIPT_IN_FEATURES")
        values=[finite_value(f,x) for x in BASE_FIELDS+(OI_FIELD,)]
        features_valid=(f["price_oi_feature_quality"]=="OK_VENDOR_ASOF" and
                       all(x is not None for x in values) and
                       finite_value(f,"open_interest") is not None and
                       finite_value(f,"last_price") is not None)
        for h in HORIZONS:
            target=finite_value(l,f"future_last_price_return_{h}m")
            published=l[f"label_{h}m_available_at_utc"]
            if target is None or not published:
                if i+h//5<288:raise ValueError("MISSING_EARLY_FUTURE_LABEL")
                skips[h]+=1;continue
            published_t=utc(published)
            if published_t-t!=dt.timedelta(minutes=h):
                raise ValueError("WRONG_FORWARD_LABEL_HORIZON")
            if published_t.date()>dt.date.fromisoformat(day)+dt.timedelta(days=1):
                raise ValueError("CROSS_DAY_FORWARD_LABEL")
            if not features_valid:
                skips[h]+=1;continue
            usable[h].append({
                "day":day,"symbol":symbol,"minute_index":i,
                BASE_FIELDS[0]:values[0],BASE_FIELDS[1]:values[1],OI_FIELD:values[2],
                "y":int(target>0),"forward_return":target,
            })
    return usable,skips


def fit_logistic(rows,cols):
    """Plain fixed-parameter ridge logistic, training-only normalization."""
    if not rows:raise ValueError("NO_TRAIN_ROWS")
    means=[sum(r[c] for r in rows)/len(rows) for c in cols]
    stdev=[]
    for k,col in enumerate(cols):
        scale=math.sqrt(sum((r[col]-means[k])**2 for r in rows)/len(rows))
        stdev.append(scale if scale>1e-12 else 1.0)
    x=[[1.0]+[(r[c]-means[k])/stdev[k] for k,c in enumerate(cols)] for r in rows]
    weights=[0.0]*(len(cols)+1)
    for _ in range(ITERATIONS):
        grad=[0.0]*len(weights)
        for row,r in zip(x,rows):
            z=sum(v*w for v,w in zip(row,weights))
            z=max(-30.0,min(30.0,z))
            p=1.0/(1.0+math.exp(-z))
            residual=p-r["y"]
            for k,value in enumerate(row):grad[k]+=residual*value
        n=len(rows)
        weights[0]-=LEARNING_RATE*grad[0]/n
        for k in range(1,len(weights)):
            weights[k]-=LEARNING_RATE*(grad[k]/n+REGULARIZATION*weights[k])
    return {"columns":cols,"means":means,"scales":stdev,"weights":weights}

def probability(model,row):
    z=model["weights"][0]
    for k,name in enumerate(model["columns"]):
        z+=model["weights"][k+1]*(row[name]-model["means"][k])/model["scales"][k]
    z=max(-30.0,min(30.0,z))
    return min(1-1e-12,max(1e-12,1/(1+math.exp(-z))))

def evaluate(model,rows):
    values=[(probability(model,r),r["y"]) for r in rows]
    if not values:raise ValueError("EMPTY_HOLDOUT")
    brier=sum((p-y)**2 for p,y in values)/len(values)
    logloss=-sum(y*math.log(p)+(1-y)*math.log1p(-p) for p,y in values)/len(values)
    accuracy=sum(int((p>=0.5)==bool(y)) for p,y in values)/len(values)
    return {"n":len(rows),"brier":round(brier,8),"logloss":round(logloss,8),
            "direction_accuracy":round(accuracy,8),
            "up_fraction":round(sum(y for _,y in values)/len(values),8)}

def walkforward(rows_by_horizon):
    results=[]
    for h in HORIZONS:
        all_rows=rows_by_horizon[h]
        for index in range(1,len(DAYS)):
            train_days=DAYS[:index];test_day=DAYS[index]
            train=[r for r in all_rows if r["day"] in train_days]
            test=[r for r in all_rows if r["day"]==test_day]
            if not train or not test:raise ValueError("MISSING_TRAIN_OR_TEST")
            baseline=fit_logistic(train,BASE_FIELDS)
            expanded=fit_logistic(train,BASE_FIELDS+(OI_FIELD,))
            for symbol in SYMBOLS:
                hold=[r for r in test if r["symbol"]==symbol]
                if not hold:raise ValueError("MISSING_HOLDOUT_SYMBOL")
                p=evaluate(baseline,hold)
                q=evaluate(expanded,hold)
                results.append({"horizon_min":h,"train_days":train_days,
                    "test_day":test_day,"symbol":symbol,"train_n":len(train),
                    "baseline":p,"with_oi":q,
                    "delta_brier_baseline_minus_oi":round(p["brier"]-q["brier"],8),
                    "delta_logloss_baseline_minus_oi":round(p["logloss"]-q["logloss"],8)})
    return results

def summarize(results):
    totals={}
    for h in HORIZONS:
        selected=[r for r in results if r["horizon_min"]==h]
        # Weight test blocks by size; disclose only three held-out calendar days.
        n=sum(r["baseline"]["n"] for r in selected)
        def avg(metric,model):
            return sum(r[model][metric]*r[model]["n"] for r in selected)/n
        a=avg("brier","baseline");b=avg("brier","with_oi")
        daily=[]
        for day in DAYS[1:]:
            blocks=[r for r in selected if r["test_day"]==day]
            denom=sum(r["baseline"]["n"] for r in blocks)
            improvement=sum(r["delta_brier_baseline_minus_oi"]*r["baseline"]["n"] for r in blocks)/denom
            daily.append({"holdout_day":day,"delta_brier_price_minus_price_oi":round(improvement,8)})
        totals[str(h)+"m"]={
            "holdout_points":n,"holdout_days":len(DAYS)-1,
            "price_brier":round(a,8),"price_plus_oi_brier":round(b,8),
            "delta_brier_price_minus_price_plus_oi":round(a-b,8),
            "day_deltas":daily,
            "number_of_positive_days":sum(r["delta_brier_price_minus_price_oi"]>0 for r in daily),
        }
    return totals

def main():
    bucket=os.environ["R2_BUCKET"]
    s3=boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
    raw=read(s3,bucket,INPUT_KEY,INPUT_SHA,200000)
    manifest=json.loads(raw)
    if (manifest.get("schema")!="detector-h1-h10-tardis-price-oi-forward-targets-v1" or
        tuple(manifest.get("days",[]))!=DAYS or tuple(manifest.get("symbols",[]))!=SYMBOLS or
        len(manifest.get("outputs",[]))!=12):
        raise ValueError("PINNED_SOURCE_MANIFEST_MISMATCH")
    by_horizon={h:[] for h in HORIZONS};quality=[]
    for day in DAYS:
        for sym in SYMBOLS:
            matches=[x for x in manifest["outputs"] if x["day"]==day and x["symbol"]==sym]
            if len(matches)!=1:raise ValueError("AMBIGUOUS_SOURCE_OUTPUT")
            meta=matches[0]
            f=read(s3,bucket,meta["features_key"],meta["features_sha256"])
            l=read(s3,bucket,meta["labels_key"],meta["labels_sha256"])
            usable,skips=validate_and_build(f,l,day,sym)
            quality.append({"day":day,"symbol":sym,"usable_by_horizon":{str(k):len(v) for k,v in usable.items()},
                "excluded_by_horizon":skips})
            for h in HORIZONS:by_horizon[h].extend(usable[h])
    blocks=walkforward(by_horizon)
    totals=summarize(blocks)
    report={
        "schema":"detector-tardis-chrono-price-oi-ablation-v1",
        "status":"EXPLORATORY_ABLATION_COMPUTED",
        "data_manifest_key":INPUT_KEY,"data_manifest_sha256":INPUT_SHA,
        "sample_days":list(DAYS),"holdout_days":list(DAYS[1:]),"symbols":list(SYMBOLS),
        "primary_horizon_min":15,"secondary_horizon_min":60,
        "model":"fixed L2-regularized logistic regression (pure Python)",
        "baseline_features":list(BASE_FIELDS),
        "oi_model_features":list(BASE_FIELDS+(OI_FIELD,)),
        "training_rule":"strict chronological days, no training on target or later days",
        "feature_time_rule":"OI and price Tardis local_timestamp<=5m end+30 seconds, from verified upstream",
        "target_rule":"direction of FUTURE Tardis last price; target rows isolated, no next-day extrapolation",
        "normalization":"fit only on earlier training days",
        "ridge":REGULARIZATION,"learning_rate":LEARNING_RATE,"iterations":ITERATIONS,
        "metrics":"lower Brier/logloss is better; positive delta means OI improved fit",
        "quality":quality,"holdout_blocks":blocks,"summary":totals,
        "research_only":True,"trading_actions":False,
        "edge_status":"EDGE_UNVALIDATED",
        "non_claims":["3 full independent test dates are not statistically sufficient",
          "5m overlapping labels are not independent trials; no naive p-values or significance",
          "Dataset first-of-month days only, highly selected nonrepresentative samples",
          "OI is vendor received Tardis snapshots, not official 5m Binance aggregate",
          "No transaction prices, spreads, commissions, slippage, or H1-H10 execution",
          "Flows excluded: original aggTrade publication timing unverified",
          "Do not trade on exploratory Brier differences"],
        "run_id":os.environ.get("GITHUB_RUN_ID"),
        "source_commit":os.environ.get("GITHUB_SHA")}
    blob=json.dumps(report,ensure_ascii=False,sort_keys=True,indent=2).encode()
    key=OUTROOT+"/"+os.environ["GITHUB_RUN_ID"]+"-"+os.environ.get("GITHUB_RUN_ATTEMPT","1")+".json"
    digest=sha(blob)
    s3.put_object(Bucket=bucket,Key=key,Body=blob,ContentType="application/json",
                  Metadata={"sha256":digest})
    if sha(s3.get_object(Bucket=bucket,Key=key)["Body"].read(len(blob)+1))!=digest:
        raise ValueError("REPORT_R2_SHA256_READBACK_FAILED")
    (OUT/"report.json").write_text(json.dumps({**report,"r2_report_key":key,
        "r2_report_sha256":digest},ensure_ascii=False,indent=2))
    print("H1H10_PRICE_OI_CHRONO_ABLATION",json.dumps({
        "status":report["status"],"primary":totals["15m"],"secondary":totals["60m"],
        "r2_report_key":key,"sha256":digest,"edge_status":"EDGE_UNVALIDATED"},ensure_ascii=False),flush=True)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"],"a",encoding="utf-8") as f:
            f.write("## Detector: chronological exploratory Price-only vs Price+OI\n\n")
            for h in HORIZONS:
                x=totals[str(h)+"m"]
                f.write(f"- {h}m: price Brier {x['price_brier']}, price+OI Brier {x['price_plus_oi_brier']}, delta {x['delta_brier_price_minus_price_plus_oi']}\n")
            f.write("- ONLY THREE HOLDOUT DAYS, edge UNVALIDATED, no trading action.\n")

if __name__=="__main__":main()
