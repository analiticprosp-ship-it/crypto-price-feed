#!/usr/bin/env python3
"""Detector exploratory 15m/60m magnitude: immutable zeros/train mean vs price vs price+OI.

Frozen broad H1-H10 prereg is distinct. Four previously viewed vendor-receipt
sample days are discovery, NOT untouched out-of-sample proof. No trades.
"""
import datetime as dt
import json
import math
import os
from pathlib import Path

import boto3

from research.detector_tardis_price_oi_chrono_ablation import (
    DAYS, SYMBOLS, HORIZONS, BASE_FIELDS, OI_FIELD, INPUT_KEY, INPUT_SHA,
    read, sha, validate_and_build,
)

OLD_CONTROL_KEY="research/tardis-price-oi-falsification-controls/v1/39170058191-1.json"
OLD_CONTROL_SHA="8fa495af13f3cca6cd99d1a6bfe7d081a9830b6398ceffc428e74085cd8ab8b7"
OUTPUT_ROOT="research/tardis-oi-abs-return-null-controls/v1"
OUT=Path("detector_tardis_oi_abs_return")
OUT.mkdir(exist_ok=True)
RIDGE_ALPHA=0.20
LR=0.10
STEPS=300
MAG_FEATURES=("past_abs_return_5m","past_abs_return_60m")
MAG_OI_FEATURE="past_abs_oi_delta_5m"
MODELS=("zero","train_mean","price_only","price_plus_oi")


def magnitude_rows(observations):
    """Only targets use FUTURE return, abs log1p; features are strictly previous."""
    output=[]
    for row in observations:
        f=float(row["forward_return"])
        if not math.isfinite(f) or f<=-1:raise ValueError("INVALID_FUTURE_RETURN")
        a=float(row[BASE_FIELDS[0]])
        b=float(row[BASE_FIELDS[1]])
        o=float(row[OI_FIELD])
        if not all(math.isfinite(x) for x in (a,b,o)):
            raise ValueError("NONFINITE_PAST_FEATURE")
        output.append({
            "day":row["day"],"symbol":row["symbol"],
            "minute_index":row["minute_index"],
            MAG_FEATURES[0]:abs(a),MAG_FEATURES[1]:abs(b),
            MAG_OI_FEATURE:abs(o),"target":abs(math.log1p(f))})
    return output


def fit_fixed_ridge(train,fields):
    """Only training data set normalization of x and y. No hyperparameter selection."""
    if not train:raise ValueError("EMPTY_TRAIN")
    xs=[[r[k] for k in fields] for r in train]
    ys=[r["target"] for r in train]
    n=len(train)
    x_mean=[sum(x[j] for x in xs)/n for j in range(len(fields))]
    x_scale=[]
    for j in range(len(fields)):
        sd=math.sqrt(sum((x[j]-x_mean[j])**2 for x in xs)/n)
        x_scale.append(max(sd,1e-12))
    y_mean=sum(ys)/n
    y_sd=math.sqrt(sum((y-y_mean)**2 for y in ys)/n)
    y_scale=max(y_sd,1e-12)
    xnorm=[[(x[j]-x_mean[j])/x_scale[j] for j in range(len(fields))] for x in xs]
    ynorm=[(v-y_mean)/y_scale for v in ys]
    weights=[0.0]*len(fields)
    bias=0.0
    for _ in range(STEPS):
        dbias=0.0
        grad=[0.0]*len(fields)
        for x,y in zip(xnorm,ynorm):
            delta=(bias+sum(w*v for w,v in zip(weights,x)))-y
            dbias+=delta
            for j,v in enumerate(x):grad[j]+=delta*v
        bias-=LR*dbias/n
        for j in range(len(fields)):
            weights[j]-=LR*(grad[j]/n+RIDGE_ALPHA*weights[j])
    return {"fields":tuple(fields),"x_mean":x_mean,"x_scale":x_scale,
            "y_mean":y_mean,"y_scale":y_scale,
            "weights":weights,"bias":bias}


def predict(model,row):
    out=model["bias"]+sum(model["weights"][i]*
       (row[field]-model["x_mean"][i])/model["x_scale"][i]
       for i,field in enumerate(model["fields"]))
    result=model["y_mean"]+model["y_scale"]*out
    if not math.isfinite(result):raise ValueError("INVALID_REGRESSION_PREDICTION")
    return max(0.0,result)


def measures(rows,probabilities):
    """MAE first, RMSE second. No overlapping-bar significance test."""
    if len(rows)!=len(probabilities) or not rows:raise ValueError("EVAL_EMPTY_OR_MISMATCH")
    errors=[]
    for r,p in zip(rows,probabilities):
        if not math.isfinite(p) or p<0:raise ValueError("INVALID_PREDICTED_MAGNITUDE")
        errors.append(p-r["target"])
    return {"n":len(rows),
        "mae":round(sum(abs(e) for e in errors)/len(errors),10),
        "rmse":round(math.sqrt(sum(e*e for e in errors)/len(errors)),10),
        "actual_mean_magnitude":round(sum(r["target"] for r in rows)/len(rows),10)}


def compare(rows_by_horizon,reference):
    """Three chronological day-level holdouts; the same fixed samples for all controls."""
    expected={(x["horizon_min"],x["test_day"],x["symbol"]):x
              for x in reference["holdout_blocks"]}
    if len(expected)!=18:raise ValueError("REFERENCE_HOLDOUT_INVALID")
    blocks=[]
    for horizon in HORIZONS:
        sample=magnitude_rows(rows_by_horizon[horizon])
        for fold in range(1,len(DAYS)):
            train_days=DAYS[:fold];held=DAYS[fold]
            train=[r for r in sample if r["day"] in train_days]
            if not train or any(r["day"]>=held for r in train):
                raise ValueError("CHRONO_LEAKAGE")
            train_mean=sum(r["target"] for r in train)/len(train)
            models={"price_only":fit_fixed_ridge(train,MAG_FEATURES),
                    "price_plus_oi":fit_fixed_ridge(train,MAG_FEATURES+(MAG_OI_FEATURE,))}
            for symbol in SYMBOLS:
                test=[r for r in sample if r["day"]==held and r["symbol"]==symbol]
                prior=expected.get((horizon,held,symbol))
                if not test or prior is None or len(test)!=prior["n"]:
                    raise ValueError("HOLDOUT_SET_CHANGED")
                predictions={
                    "zero":[0.0]*len(test),
                    "train_mean":[train_mean]*len(test),
                    "price_only":[predict(models["price_only"],r) for r in test],
                    "price_plus_oi":[predict(models["price_plus_oi"],r) for r in test]}
                blocks.append({"horizon_min":horizon,"test_day":held,
                    "symbol":symbol,"train_days":list(train_days),
                    "train_count":len(train),"n":len(test),
                    "metrics":{name:measures(test,predictions[name]) for name in MODELS}})
    return blocks


def summarize(blocks):
    result={}
    for horizon in HORIZONS:
        batch=[x for x in blocks if x["horizon_min"]==horizon]
        if len(batch)!=9:raise ValueError("HOLDOUT_BLOCKS_MISSING")
        n=sum(x["n"] for x in batch)
        item={"holdout_points":n,"holdout_calendar_days":3,"mae":{},"rmse":{},
              "per_day_mae":{}}
        for name in MODELS:
            item["mae"][name]=round(sum(x["metrics"][name]["mae"]*x["n"] for x in batch)/n,10)
            item["rmse"][name]=round(math.sqrt(sum(x["metrics"][name]["rmse"]**2*x["n"] for x in batch)/n),10)
            item["per_day_mae"][name]={}
            for day in DAYS[1:]:
                matches=[x for x in batch if x["test_day"]==day]
                m=sum(x["n"] for x in matches)
                item["per_day_mae"][name][day]=round(
                    sum(x["metrics"][name]["mae"]*x["n"] for x in matches)/m,10)
        item["oi_minus_price_mae"]=round(
            item["mae"]["price_plus_oi"]-item["mae"]["price_only"],10)
        item["oi_days_better_than_price"]=sum(
            item["per_day_mae"]["price_plus_oi"][day]
            <item["per_day_mae"]["price_only"][day] for day in DAYS[1:])
        result[f"{horizon}m"]=item
    return result


def main():
    bucket=os.environ["R2_BUCKET"]
    client=boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
    previous=json.loads(read(client,bucket,OLD_CONTROL_KEY,OLD_CONTROL_SHA,550000))
    if previous.get("schema")!="detector-h1h10-price-oi-falsification-controls-v1":
        raise ValueError("REFERENCE_SCHEMA_INVALID")
    manifest=json.loads(read(client,bucket,INPUT_KEY,INPUT_SHA,250000))
    if manifest.get("schema")!="detector-h1-h10-tardis-price-oi-forward-targets-v1":
        raise ValueError("INPUT_SCHEMA_INVALID")
    if tuple(manifest["days"])!=DAYS or tuple(manifest["symbols"])!=SYMBOLS:
        raise ValueError("INPUT_DATES_CHANGED")
    samples={h:[] for h in HORIZONS}
    for day in DAYS:
        for symbol in SYMBOLS:
            matches=[x for x in manifest["outputs"] if x["day"]==day and x["symbol"]==symbol]
            if len(matches)!=1:raise ValueError("SOURCE_AMBIGUOUS")
            entry=matches[0]
            source=read(client,bucket,entry["features_key"],entry["features_sha256"])
            labels=read(client,bucket,entry["labels_key"],entry["labels_sha256"])
            joined,_=validate_and_build(source,labels,day,symbol)
            for h in HORIZONS:samples[h].extend(joined[h])
    blocks=compare(samples,previous)
    statistics=summarize(blocks)
    report={
        "schema":"detector-h1h10-oi-abs-future-logreturn-exploratory-v1",
        "status":"MAGNITUDE_NULL_CONTROL_COMPARISON_COMPLETE",
        "prereg_document":"research/DETECTOR_H1_H10_BROAD_HISTORY_PREREG_v1_2026-10-19.md",
        "prior_null_control_key":OLD_CONTROL_KEY,"prior_null_control_sha256":OLD_CONTROL_SHA,
        "source_manifest":INPUT_KEY,"source_manifest_sha256":INPUT_SHA,
        "sample_days":list(DAYS),"held_out_days":list(DAYS[1:]),"symbols":list(SYMBOLS),
        "target":"abs(log1p(forward Tardis LAST price simple return))",
        "target_type":"absolute magnitude (not prediction of direction)",
        "falsification":["zero","train_mean","price_only","price_plus_oi"],
        "past_features_price":list(MAG_FEATURES),
        "additional_oi_feature":MAG_OI_FEATURE,
        "frozen_model":{"type":"train standardized L2-ridge pure Python","alpha":RIDGE_ALPHA,
                        "learning_rate":LR,"iterations":STEPS,
                        "negative_magnitude_predictions":"clip at 0"},
        "training":"expanding strictly prior days, means/scales fit ONLY on training",
        "metrics":"MAE primary (lower better), RMSE secondary, day-level reporting",
        "results":statistics,"blocks":blocks,"edge_status":"EDGE_UNVALIDATED",
        "warnings":["All four days previously inspected: exploratory only, NOT independent confirmatory holdout",
            "Only 3 non-consecutive calendar test dates, 5m outcomes overlap",
            "No actual bid/ask or execution transaction costs, zero profits claimed",
            "Tardis local_timestamp is vendor receipt, not native exchange publication",
            "No flow predictors due to unverified historical release times",
            "Never infer H1-H10 significance or changes to production Detector"],
        "research_only":True,"trading_actions":False,
        "github_run_id":os.environ["GITHUB_RUN_ID"],"source_commit_sha":os.environ.get("GITHUB_SHA")}
    blob=json.dumps(report,ensure_ascii=False,sort_keys=True,indent=2).encode()
    digest=sha(blob)
    key=OUTPUT_ROOT+"/"+os.environ["GITHUB_RUN_ID"]+"-"+os.environ.get("GITHUB_RUN_ATTEMPT","1")+".json"
    client.put_object(Bucket=bucket,Key=key,Body=blob,ContentType="application/json",Metadata={"sha256":digest})
    if sha(client.get_object(Bucket=bucket,Key=key)["Body"].read(len(blob)+1))!=digest:
        raise ValueError("REPORT_READBACK_SHA_FAIL")
    (OUT/"report.json").write_text(json.dumps({**report,"r2_key":key,"r2_sha256":digest},ensure_ascii=False,indent=2))
    print("DETECTOR_H1H10_ABS_RETURN_MAGNITUDE",json.dumps({
        "status":report["status"],"results":statistics,
        "r2_key":key,"sha256":digest,"edge_status":"EDGE_UNVALIDATED"},ensure_ascii=False),flush=True)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"],"a",encoding="utf-8") as f:
            f.write("## Detector magnitude of returns: discovery-only ablation\n\n")
            for h in HORIZONS:
                f.write(f"- {h}m MAE: {statistics[f'{h}m']['mae']}\n")
            f.write("- Only 3 tested days; no trading action, EDGE_UNVALIDATED.\n")

if __name__=="__main__":
    main()
