#!/usr/bin/env python3
"""Independent simple forecast controls for pinned chronological Tardis Price-vs-OI study.

No new feature selection, retraining on holdout, threshold optimization,
historical publication claims, trading signals, or capital changes.
"""
import json
import math
import os
from pathlib import Path

import boto3

from research.detector_tardis_price_oi_chrono_ablation import (
    DAYS, SYMBOLS, HORIZONS, BASE_FIELDS, OI_FIELD, INPUT_KEY, INPUT_SHA,
    fit_logistic, walkforward, validate_and_build, evaluate, read, sha,
)

PRIOR_KEY="research/tardis-price-oi-chronological-ablation/v1/39152210127-1.json"
PRIOR_SHA="164cbaf3d5f1edf635cfee3945bba2fff6223f8943639a87c7067b569139f117"
REPORT_ROOT="research/tardis-price-oi-falsification-controls/v1"
OUT=Path("detector_price_oi_falsification_controls")
OUT.mkdir(exist_ok=True)
MODELS=("fixed_half","train_only_prior","price_only","price_plus_oi")


def train_only_prior(train):
    """Laplace-smoothed, predeclared P(up) from strictly earlier train days."""
    if not train:
        raise ValueError("EMPTY_TRAIN_SET")
    if any(r.get("y") not in (0,1) for r in train):
        raise ValueError("INVALID_TRAIN_BINARY_LABEL")
    return (sum(r["y"] for r in train)+1)/(len(train)+2)


def constant_metrics(test,p):
    """Brier and logloss; no market position or payoff interpretation."""
    if not test or not 0<p<1:
        raise ValueError("EMPTY_TEST_OR_INVALID_FORECAST")
    if any(r.get("y") not in (0,1) for r in test):
        raise ValueError("INVALID_TEST_BINARY_LABEL")
    n=len(test)
    brier=sum((p-r["y"])**2 for r in test)/n
    logloss=-sum(r["y"]*math.log(p)+(1-r["y"])*math.log1p(-p) for r in test)/n
    accuracy=sum(int((p>=.5)==bool(r["y"])) for r in test)/n
    return {"n":n,"brier":round(brier,8),"logloss":round(logloss,8),
            "direction_accuracy":round(accuracy,8),
            "up_fraction":round(sum(r["y"] for r in test)/n,8),
            "probability":round(p,10)}


def aggregate(blocks):
    result={}
    for horizon in HORIZONS:
        records=[x for x in blocks if x["horizon_min"]==horizon]
        counts={d:sum(x["n"] for x in records if x["test_day"]==d) for d in DAYS[1:]}
        if len(records)!=3*len(SYMBOLS) or any(n<=0 for n in counts.values()):
            raise ValueError("HOLDOUT_BLOCKS_MISSING")
        n=sum(x["n"] for x in records)
        item={"holdout_points":n,"holdout_days":3,"calendar_day_counts":counts,
              "independent_test_days_not_bars":3,"weighted_brier":{},
              "weighted_logloss":{},"day_brier":{}}
        for name in MODELS:
            item["weighted_brier"][name]=round(
                sum(x["models"][name]["brier"]*x["n"] for x in records)/n,8)
            item["weighted_logloss"][name]=round(
                sum(x["models"][name]["logloss"]*x["n"] for x in records)/n,8)
            item["day_brier"][name]={
                day:round(sum(x["models"][name]["brier"]*x["n"]
                              for x in records if x["test_day"]==day)/counts[day],8)
                for day in DAYS[1:]}
        item["brier_change_from_fixed_half"]={
            name:round(item["weighted_brier"]["fixed_half"]-item["weighted_brier"][name],8)
            for name in MODELS if name!="fixed_half"}
        result[f"{horizon}m"]=item
    return result


def reproduce_with_controls(samples,prior_blocks):
    """One fixed holdout sample for all models; test never feeds a training prior."""
    outputs=[]
    known={(x["horizon_min"],x["test_day"],x["symbol"]):x for x in prior_blocks}
    if len(known)!=3*len(SYMBOLS)*len(HORIZONS) or len(known)!=len(prior_blocks):
        raise ValueError("PINNED_MODEL_BLOCK_SET_INCOMPLETE")
    replay=walkforward(samples)
    for prior in replay:
        key=(prior["horizon_min"],prior["test_day"],prior["symbol"])
        old=known.get(key)
        if old is None or old["train_days"]!=prior["train_days"] or old["train_n"]!=prior["train_n"]:
            raise ValueError("PINNED_MODEL_SPLITS_CHANGED")
        for old_model,new_model in (("baseline","baseline"),("with_oi","with_oi")):
            for metric in ("n","brier","logloss","direction_accuracy","up_fraction"):
                if old[old_model][metric]!=prior[new_model][metric]:
                    raise ValueError("PREVIOUS_MODEL_METRIC_REPLAY_MISMATCH")
    for horizon in HORIZONS:
        data=samples[horizon]
        for index in range(1,len(DAYS)):
            train_days=DAYS[:index]
            day=DAYS[index]
            train=[x for x in data if x["day"] in train_days]
            test=[x for x in data if x["day"]==day]
            if not train or not test or any(r["day"]>=day for r in train):
                raise ValueError("TRAIN_DAY_LOOKAHEAD_OR_MISSING")
            p=train_only_prior(train)
            for symbol in SYMBOLS:
                hold=[r for r in test if r["symbol"]==symbol]
                key=(horizon,day,symbol)
                old=known[key]
                m1=constant_metrics(hold,.5)
                m2=constant_metrics(hold,p)
                if old["baseline"]["n"]!=m1["n"] or old["with_oi"]["n"]!=m1["n"]:
                    raise ValueError("MODEL_HOLDOUT_COUNTS_DIVERGE")
                outputs.append({"horizon_min":horizon,"test_day":day,
                    "symbol":symbol,"train_days":list(train_days),"train_n":len(train),
                    "train_up_count":sum(r["y"] for r in train),
                    "n":len(hold),
                    "models":{"fixed_half":m1,"train_only_prior":m2,
                        "price_only":old["baseline"],
                        "price_plus_oi":old["with_oi"]}})
    return outputs


def main():
    bucket=os.environ["R2_BUCKET"]
    client=boto3.client("s3",
        endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
    old=json.loads(read(client,bucket,PRIOR_KEY,PRIOR_SHA,500000))
    if (old.get("schema")!="detector-tardis-chrono-price-oi-ablation-v1"
        or old.get("status")!="EXPLORATORY_ABLATION_COMPUTED"
        or old.get("data_manifest_key")!=INPUT_KEY
        or old.get("data_manifest_sha256")!=INPUT_SHA
        or tuple(old.get("sample_days",()))!=DAYS
        or tuple(old.get("symbols",()))!=SYMBOLS):
        raise ValueError("PINNED_REPORT_SOURCE_INVALID")
    manifest=json.loads(read(client,bucket,INPUT_KEY,INPUT_SHA,200000))
    if (manifest.get("schema")!="detector-h1-h10-tardis-price-oi-forward-targets-v1"
        or len(manifest.get("outputs",()))!=12):
        raise ValueError("PINNED_FEATURE_SOURCE_INVALID")
    samples={h:[] for h in HORIZONS}
    for day in DAYS:
        for symbol in SYMBOLS:
            matches=[x for x in manifest["outputs"] if x["day"]==day and x["symbol"]==symbol]
            if len(matches)!=1:raise ValueError("FEATURE_MANIFEST_MATCH_INVALID")
            meta=matches[0]
            features=read(client,bucket,meta["features_key"],meta["features_sha256"])
            labels=read(client,bucket,meta["labels_key"],meta["labels_sha256"])
            data,_=validate_and_build(features,labels,day,symbol)
            for h in HORIZONS:samples[h].extend(data[h])
    blocks=reproduce_with_controls(samples,old["holdout_blocks"])
    summary=aggregate(blocks)
    report={
        "schema":"detector-h1h10-price-oi-falsification-controls-v1",
        "status":"NULL_CONTROLS_REPLAY_PASS","pinned_prior_report_key":PRIOR_KEY,
        "pinned_prior_report_sha256":PRIOR_SHA,
        "pinned_features_manifest_key":INPUT_KEY,
        "pinned_features_manifest_sha256":INPUT_SHA,
        "days":list(DAYS),"symbols":list(SYMBOLS),"horizons_min":list(HORIZONS),
        "models":{
            "fixed_half":"Always P(up)=0.5",
            "train_only_prior":"(training positive target count +1)/(training row count+2), pooled BTC/ETH/SOL, no test labels",
            "price_only":"Prior verified fixed ridge logistic past 5m/60m last-price changes",
            "price_plus_oi":"Same logistic + 5m open-interest change"},
        "walkforward":"expanding train on strictly earlier calendar days",
        "labels_are_not_features":True,
        "holdout_blocks":blocks,"summary":summary,
        "important_limits":[
            "Just three independent nonconsecutive holdout calendar days; 5m rows are serially dependent",
            "All days are free first-of-month samples; not representative of realistic market regimes",
            "Last traded vendor price is not executable bid/ask and not net strategy P&L",
            "Spot/futures flow excluded because aggTrade publication availability is not established",
            "No naive significance claims or H1-H10 trading signals",
            "Original Binance OI exchange publication time remains unverified"],
        "research_only":True,"trading_or_portfolio_changes":False,
        "edge_status":"EDGE_UNVALIDATED",
        "run_id":os.environ["GITHUB_RUN_ID"],
        "source_commit":os.environ.get("GITHUB_SHA"),
    }
    blob=json.dumps(report,ensure_ascii=False,indent=2,sort_keys=True).encode()
    digest=sha(blob)
    key=REPORT_ROOT+"/"+report["run_id"]+"-"+os.environ.get("GITHUB_RUN_ATTEMPT","1")+".json"
    client.put_object(Bucket=bucket,Key=key,Body=blob,ContentType="application/json",
                      Metadata={"sha256":digest})
    received=client.get_object(Bucket=bucket,Key=key)["Body"].read(len(blob)+1)
    if sha(received)!=digest:raise ValueError("R2_READBACK_SHA256_FAIL")
    (OUT/"report.json").write_text(json.dumps({**report,"r2_key":key,
        "r2_sha256":digest},ensure_ascii=False,indent=2),encoding="utf-8")
    print("DETECTOR_H1H10_NULL_CONTROL_SUMMARY",json.dumps({
        "status":report["status"],"summary":summary,"r2_key":key,
        "r2_sha256":digest,"edge_status":"EDGE_UNVALIDATED"
    },ensure_ascii=False),flush=True)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"],"a",encoding="utf-8") as stream:
            stream.write("## Detector H1-H10: fixed 50% and train-only base-rate controls\n\n")
            for horizon in HORIZONS:
                record=summary[f"{horizon}m"]
                stream.write(f"- {horizon}m: Brier "+", ".join(
                    f"{k}={v}" for k,v in record["weighted_brier"].items())+"\n")
            stream.write("- Three holdout dates only. This does not validate trading edge.\n")

if __name__=="__main__":
    main()
