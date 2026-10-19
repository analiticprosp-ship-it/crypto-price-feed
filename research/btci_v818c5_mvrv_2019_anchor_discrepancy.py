#!/usr/bin/env python3
"""BTCI v8.18c5: non-confirmatory, post-mismatch MVRV diagnosis; research only."""
import csv
import hashlib
import io
import json
import math
import os
import sys
from pathlib import Path
import boto3
sys.path.insert(0,str(Path(__file__).resolve().parent))
from btci_v818c4_contemporaneous_mvrv_anchor import fetch,digest,num

ROOT=Path(__file__).resolve().parents[1]
SPEC=ROOT/"research/btci_v818c5_mvrv_2019_anchor_discrepancy_prereg_2026-10-19.json"
CAP=("CapMVRVCur","CapRealUSD","CapMrktCurUSD","PriceUSD","SplyCur")

def slice_days(raw,dates):
    reader=csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    fields=reader.fieldnames or []
    datecol="time" if "time" in fields else "date" if "date" in fields else None
    if datecol is None:
        raise ValueError("MISSING_DATE_FIELD")
    result={}
    for row in reader:
        d=(row.get(datecol) or "")[:10]
        if d in dates:
            if d in result:
                raise ValueError("DUPLICATE_DATE")
            result[d]={k:num(row[k]) if k in fields else None for k in CAP}
    return result

def asof_rows(src,dates):
    rows=slice_days(src,dates)
    return {date:rows.get(date) for date in dates}

def selftest():
    sample=b"time,CapMVRVCur,CapRealUSD,CapMrktCurUSD\n2019-12-30T00:00:00Z,1.25,2,2.5\n"
    assert slice_days(sample,["2019-12-30"])["2019-12-30"]["CapMVRVCur"]==1.25
    assert slice_days(sample,["2019-12-29"])=={}
    assert num("1.0")==1.0
    print("V818C5_SELFTEST_PASS",flush=True)

def main():
    specbytes=SPEC.read_bytes()
    spec=json.loads(specbytes)
    assert spec["version"]=="8.18c5" and spec["researchOnly"] and spec["exploratoryPostMismatch"]
    s3=boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
                    aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
    bucket=os.environ["R2_BUCKET"]
    parentkey="research/btci/v8.18c4/runs/39298506014-1/contemporaneous_2019_mvrv_anchor_FULL.json"
    parentraw=s3.get_object(Bucket=bucket,Key=parentkey)["Body"].read()
    if digest(parentraw)!=spec["parent"]["reportSHA256"]:
        raise ValueError("PINNED_PARENT_SHA_MISMATCH")
    parent=json.loads(parentraw)
    if parent["status"]!="HISTORICAL_MVRV_ANCHOR_MISMATCH":
        raise ValueError("PARENT_RESULT_CHANGED")
    info=spec["src"]
    url1,raw1=fetch(info["repo"],info["one"]["sha"],info["one"]["blob"],info["one"]["bytes"])
    url2,raw2=fetch(info["repo"],info["two"]["sha"],info["two"]["blob"],info["two"]["bytes"])
    dates=spec["frozenDates"]
    prior=asof_rows(raw1,dates)
    later=asof_rows(raw2,dates)
    if any(prior[d] is None or later[d] is None for d in dates):
        raise ValueError("FROZEN_FIVE_DATES_NOT_FULLY_AVAILABLE")
    extracted=[]
    for d in dates:
        a=prior[d]
        b=later[d]
        m=a["CapMVRVCur"]
        cap=a["CapMrktCurUSD"]/a["CapRealUSD"] if a["CapRealUSD"] else None
        matches= m is not None and 1.325<=m<1.335
        change={k:(a[k]!=b[k]) for k in CAP}
        extracted.append({"date":d,"mvrvJan2020":m,"mvrvDec2020":b["CapMVRVCur"],
            "marketCap":a["CapMrktCurUSD"],"realizedCap":a["CapRealUSD"],
            "recomputedRatio":cap,"arithmeticMatches":math.isclose(m,cap,rel_tol=0.000005) if cap else False,
            "roundsToPublicValue":matches,"changedAcrossVintages":change})
    hits=[x["date"] for x in extracted if x["roundsToPublicValue"]]
    original=next(x for x in extracted if x["date"]=="2019-12-30")
    if original["mvrvJan2020"]!=parent["historical2020CSV"]["mvrv"]:
        raise ValueError("PARENT_DATE_REPLAY_CHANGED")
    revised=[{"date":x["date"],"column":c} for x in extracted for c,changed in x["changedAcrossVintages"].items() if changed]
    status="DATE_WINDOW_CONTAINS_ROUNDING_MATCH_NONCONFIRMATORY" if hits else "SOURCE_METHOD_DIFFERENCE_UNRESOLVED_FIVE_DAYS"
    report={"version":"8.18c5","status":status,"researchOnly":True,"noTradingAuthority":True,
       "diagnosticOnlyAfterObservedMismatch":True,
       "prereg":{"sha256":digest(specbytes),"path":str(SPEC.relative_to(ROOT))},
       "pinnedParent":{"key":parentkey,"sha256":digest(parentraw)},
       "sourceVintages":[{"url":url1,"sha256":digest(raw1),"gitSHA":info["one"]["sha"]},
                         {"url":url2,"sha256":digest(raw2),"gitSHA":info["two"]["sha"]}],
       "publicRoundedAnchor":spec["article"],
       "fixedFiveDays":extracted,"nearDateRoundingMatches":hits,"changedHistoricalCells":revised,
       "interpretation":"Date-neighbor or vintage agreement is descriptive only; no proof of published-data methodology, first-seen availability or trading performance.",
       "limitations":["Five dates selected post hoc after observing v8.18c4 mismatch, not independent test",
                      "Coin Metrics public article may use a different market valuation method or chart reference; not established",
                      "Git archive history is not exact public first-available proof for Jan 2020",
                      "2018 conceptual availability does not make reconstructed 2012-2017 backtest valid",
                      "No MVRV live trading signal, no retroactive retuning"],
       "portfolioWriteback":{x:False for x in ("Spot","Futures","NAV","PnL","capital","reserve","MASTER","Detector","tradingLimits","orders")}}
    out=Path("btci_v818c5_reports");out.mkdir(exist_ok=True)
    raw=(json.dumps(report,indent=2,ensure_ascii=False)+"\n").encode()
    (out/"five_day_discrepancy_FULL.json").write_bytes(raw)
    prefix="research/btci/v8.18c5/runs/{}-{}/".format(os.environ["GITHUB_RUN_ID"],os.getenv("GITHUB_RUN_ATTEMPT","1"))
    def put(name,data):
        key=prefix+name
        s3.put_object(Bucket=bucket,Key=key,Body=data,ContentType="application/json",Metadata={"sha256":digest(data),"research-only":"true"})
        if digest(s3.get_object(Bucket=bucket,Key=key)["Body"].read())!=digest(data):
            raise ValueError("R2_READBACK_SHA_MISMATCH")
        return {"key":key,"sha256":digest(data),"bytes":len(data)}
    saved=put("five_day_discrepancy_FULL.json",raw)
    manifest=put("manifest.json",(json.dumps({"version":"8.18c5","status":status,"researchOnly":True,"report":saved,
                                            "preregSha256":digest(specbytes),"parentSha256":digest(parentraw)},
                                         indent=2,ensure_ascii=False)+"\n").encode())
    result={"status":status,"matchedDates":hits,"fiveDatesChecked":len(dates),"changedCells":len(revised),
           "reportSha256":saved["sha256"],"manifestSha256":manifest["sha256"],"prefix":prefix}
    (out/"summary.json").write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n")
    print("V818C5_RESULT "+json.dumps(result,ensure_ascii=False),flush=True)
    for row in extracted:
        print("V818C5_DAY "+json.dumps({"date":row["date"],"mvrv":row["mvrvJan2020"],"other":row["mvrvDec2020"],
            "roundsTo1_33":row["roundsToPublicValue"]},ensure_ascii=False),flush=True)
if __name__=="__main__":
    if "--self-test" in sys.argv:
        selftest()
    else:
        main()
