#!/usr/bin/env python3
"""Seven-day (nonconsecutive, selected) exploratory direction/magnitude fixed controls.

Replays EXACT frozen model parameters from prior H1-H10 studies. This is NOT a
confirmatory 60-day holdout; no tuning, inference of trading profits or signals.
"""
import json,math,os
from pathlib import Path
import boto3

from research.detector_tardis_price_oi_chrono_ablation import (
    BASE_FIELDS,OI_FIELD,HORIZONS,SYMBOLS,INPUT_KEY,INPUT_SHA,
    read,sha,validate_and_build,fit_logistic,evaluate
)
from research.detector_tardis_price_oi_null_controls import (
    train_only_prior,constant_metrics
)
from research.detector_tardis_oi_abs_return_magnitude import (
    MAG_FEATURES,MAG_OI_FEATURE,magnitude_rows,fit_fixed_ridge,predict,measures
)

ADDITIONAL_KEY="research/tardis-binance-expanded-price-5m-join/v1/manifest-39210755313.json"
ADDITIONAL_SHA="8a6403cedfd9cf4f31e8642b38668d6a6cc78e1f8646b7c0cd412d79a37a14bd"
DAYS=("2024-01-01","2024-04-01","2025-01-01","2025-07-01",
      "2026-02-01","2026-09-01","2026-10-01")
NEW_DAYS=("2024-04-01","2025-07-01","2026-02-01")
ROOT="research/detector-seven-day-fixed-control-pilot/v1"
OUT=Path("detector_seven_day_fixed_controls");OUT.mkdir(exist_ok=True)
NAMES=("zero","train_mean","price_only","price_plus_oi")
DIRECT=("fixed_half","train_only_prior","price_only","price_plus_oi")


def source_catalog(old,new):
    if (old.get("schema")!="detector-h1-h10-tardis-price-oi-forward-targets-v1"
     or new.get("schema")!="detector-tardis-expanded-three-day-price-oi-join-v1"):
        raise ValueError("SOURCE_SCHEMA_MISMATCH")
    if (tuple(old.get("days",()))!=("2024-01-01","2025-01-01","2026-09-01","2026-10-01")
       or tuple(new.get("days",()))!=NEW_DAYS):
        raise ValueError("SOURCE_DATE_SET_MISMATCH")
    out={}
    for report in (old,new):
        for row in report["outputs"]:
            key=(row["day"],row["symbol"])
            if key in out:raise ValueError("DUPLICATE_SOURCE_DAY_SYMBOL")
            out[key]=row
    if len(out)!=len(DAYS)*len(SYMBOLS):
        raise ValueError("SOURCE_COVERAGE_GAP")
    return out


def evaluate_seven_days(rows_by_horizon):
    """Expanding calendar-day splits; test-day outcomes never enter its train."""
    blocks=[]
    for horizon in HORIZONS:
        source=rows_by_horizon[horizon]
        actual_days={r["day"] for r in source}
        if actual_days!=set(DAYS):
            raise ValueError("TRAIN_TEST_SAMPLE_DAYS_MISSING")
        for k in range(1,len(DAYS)):
            day=DAYS[k];past=DAYS[:k]
            train=[x for x in source if x["day"] in past]
            held=[x for x in source if x["day"]==day]
            if not train or not held or any(x["day"]>=day for x in train):
                raise ValueError("CHRONO_TRAIN_MISMATCH")
            baseline=fit_logistic(train,BASE_FIELDS)
            with_oi=fit_logistic(train,BASE_FIELDS+(OI_FIELD,))
            prevalence=train_only_prior(train)
            mt=magnitude_rows(train)
            mh=magnitude_rows(held)
            mean_magnitude=sum(r["target"] for r in mt)/len(mt)
            mprice=fit_fixed_ridge(mt,MAG_FEATURES)
            moi=fit_fixed_ridge(mt,MAG_FEATURES+(MAG_OI_FEATURE,))
            for sym in SYMBOLS:
                d=[r for r in held if r["symbol"]==sym]
                m=[r for r in mh if r["symbol"]==sym]
                if not d or len(d)!=len(m):
                    raise ValueError("SYMBOL_HOLDOUT_COUNT_MISMATCH")
                directional={
                    "fixed_half":constant_metrics(d,0.5),
                    "train_only_prior":constant_metrics(d,prevalence),
                    "price_only":evaluate(baseline,d),
                    "price_plus_oi":evaluate(with_oi,d)}
                magnitude={
                    "zero":measures(m,[0.0]*len(m)),
                    "train_mean":measures(m,[mean_magnitude]*len(m)),
                    "price_only":measures(m,[predict(mprice,r) for r in m]),
                    "price_plus_oi":measures(m,[predict(moi,r) for r in m])}
                blocks.append({
                    "horizon_min":horizon,"held_day":day,"symbol":sym,
                    "new_predeclared_day":day in NEW_DAYS,
                    "train_days":list(past),"train_count":len(train),
                    "n":len(d),"direction":directional,"magnitude":magnitude})
    return blocks


def summary(blocks):
    result={}
    for horizon in HORIZONS:
        xs=[r for r in blocks if r["horizon_min"]==horizon]
        if len(xs)!=6*len(SYMBOLS):raise ValueError("EXPECTED_SIX_HOLDOUT_DAYS")
        out={"heldout_calendar_days":6,"new_selected_days":len(NEW_DAYS),
             "observation_count":sum(r["n"] for r in xs),
             "direction_brier":{},"magnitude_mae":{},
             "per_held_day":{},"new_days_only":{}}
        for day in DAYS[1:]:
            ds=[r for r in xs if r["held_day"]==day]
            n=sum(r["n"] for r in ds)
            out["per_held_day"][day]={
                "n":n,"new_day":day in NEW_DAYS,
                "price_minus_oi_direction_brier":round(sum(
                    (r["direction"]["price_only"]["brier"]-
                     r["direction"]["price_plus_oi"]["brier"])*r["n"] for r in ds)/n,10),
                "price_minus_oi_magnitude_mae":round(sum(
                    (r["magnitude"]["price_only"]["mae"]-
                     r["magnitude"]["price_plus_oi"]["mae"])*r["n"] for r in ds)/n,10)}
        for names,metric,key,dst in (
            (DIRECT,"brier","direction","direction_brier"),
            (NAMES,"mae","magnitude","magnitude_mae")):
            n=out["observation_count"]
            out[dst]={name:round(sum(x[key][name][metric]*x["n"] for x in xs)/n,10)
                      for name in names}
            novel=[x for x in xs if x["held_day"] in NEW_DAYS]
            count=sum(x["n"] for x in novel)
            out["new_days_only"][dst]={
                name:round(sum(x[key][name][metric]*x["n"] for x in novel)/count,10)
                for name in names}
        result[f"{horizon}m"]=out
    return result


def main():
    bucket=os.environ["R2_BUCKET"]
    s3=boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
    old=json.loads(read(s3,bucket,INPUT_KEY,INPUT_SHA,250000))
    new=json.loads(read(s3,bucket,ADDITIONAL_KEY,ADDITIONAL_SHA,300000))
    catalog=source_catalog(old,new)
    samples={h:[] for h in HORIZONS}
    for day in DAYS:
        for symbol in SYMBOLS:
            row=catalog[(day,symbol)]
            feature=read(s3,bucket,row["features_key"],row["features_sha256"],250000)
            label=read(s3,bucket,row["labels_key"],row["labels_sha256"],250000)
            derived,_=validate_and_build(feature,label,day,symbol)
            for h in HORIZONS:samples[h].extend(derived[h])
    blocks=evaluate_seven_days(samples)
    aggregate=summary(blocks)
    report={
        "schema":"detector-h1h10-seven-free-day-exploratory-fixed-controls-v1",
        "status":"SEVEN_DAY_FIXED_CONTROL_REPLAY_COMPLETE",
        "old_manifest_key":INPUT_KEY,"old_manifest_sha256":INPUT_SHA,
        "new_manifest_key":ADDITIONAL_KEY,"new_manifest_sha256":ADDITIONAL_SHA,
        "calendar_days":list(DAYS),"new_frozen_days":list(NEW_DAYS),
        "symbols":list(SYMBOLS),"horizons_minutes":list(HORIZONS),
        "controls":{"direction":list(DIRECT),"absolute_magnitude":list(NAMES)},
        "algorithm_freeze":"Same fixed logistic and fixed magnitude ridge as #71/#78; no hyperparameter tuning",
        "folds":"Train on earlier whole UTC first-of-month sample days; test next first-of-month day",
        "training_only_scaling":True,"no_future_labels_as_features":True,
        "summary":aggregate,"blocks":blocks,
        "research_only":True,"no_trade_actions":True,"edge_status":"EDGE_UNVALIDATED",
        "limitations":[
           "All seven days are selected first-of-month free samples, not a representative time series",
           "Three previously unseen dates are additional discovery checks, not certified pristine 60-day holdout",
           "Time source Tardis vendor receipt is not original Binance publication",
           "5-minute rows and adjacent price targets are serially dependent",
           "No executable bid/ask, funding or real transaction cost proof",
           "Original flow availability time not established; therefore H1-H10 full joint tests blocked",
           "Cannot use this run to choose parameters and then claim its held days remained unseen"],
        "run_id":os.environ["GITHUB_RUN_ID"],
        "source_commit":os.environ.get("GITHUB_SHA")}
    data=json.dumps(report,ensure_ascii=False,indent=2,sort_keys=True).encode()
    digest=sha(data)
    key=ROOT+"/"+os.environ["GITHUB_RUN_ID"]+"-"+os.environ.get("GITHUB_RUN_ATTEMPT","1")+".json"
    s3.put_object(Bucket=bucket,Key=key,Body=data,ContentType="application/json",Metadata={"sha256":digest})
    if sha(s3.get_object(Bucket=bucket,Key=key)["Body"].read(len(data)+1))!=digest:
        raise ValueError("SEVEN_DAY_REPORT_READBACK_MISMATCH")
    (OUT/"report.json").write_text(json.dumps({**report,"r2_report_key":key,"r2_sha256":digest},
       ensure_ascii=False,indent=2),encoding="utf-8")
    print("DETECTOR_SEVEN_DAY_FIXED_SUMMARY",json.dumps({
        "status":report["status"],"results":aggregate,"r2_report_key":key,
        "sha256":digest,"edge_status":"EDGE_UNVALIDATED"},ensure_ascii=False),flush=True)

if __name__=="__main__":main()
