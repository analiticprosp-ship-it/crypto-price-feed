#!/usr/bin/env python3
"""BTCI v8.18c4: frozen 2019 MVRV publication anchor vs Git archived values; RESEARCH_ONLY."""
import csv
import hashlib
import io
import json
import math
import os
import sys
import time
from datetime import date
from pathlib import Path
from urllib.request import Request, urlopen
import boto3

ROOT=Path(__file__).resolve().parents[1]
PREREG=ROOT/"research/btci_v818c4_contemporaneous_mvrv_anchor_prereg_2026-10-19.json"
FIELDS=("CapMVRVCur","CapRealUSD","CapMrktCurUSD","PriceUSD","SplyCur")

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def blob(raw):
    return hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()

def parse(raw):
    rd=csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    header=rd.fieldnames or []
    key="time" if "time" in header else "date" if "date" in header else None
    if not key:
        raise ValueError("NO_DATE_FIELD")
    seen=set()
    wanted={}
    n=0
    for record in rd:
        obs=(record[key] or "")[:10]
        date.fromisoformat(obs)
        if obs in seen:
            raise ValueError("DUPLICATE_DATE")
        seen.add(obs)
        n+=1
        if obs in ("2018-07-10","2018-10-01","2019-12-30","2020-01-30"):
            wanted[obs]={f:record.get(f) for f in FIELDS}
    return {"rows":n,"columns":{k:k in header for k in FIELDS},"anchorRows":wanted}

def fetch(repo,ref,expected,length):
    url=f"https://raw.githubusercontent.com/{repo}/{ref}/csv/btc.csv"
    last=None
    for attempt in range(3):
        try:
            with urlopen(Request(url,headers={"User-Agent":"BTCI-v818c4-Research/1.0"}),timeout=45) as r:
                raw=r.read(13_000_000)
            if len(raw)!=length:
                raise ValueError("ORIGINAL_BLOB_BYTE_LENGTH_MISMATCH")
            if blob(raw)!=expected:
                raise ValueError("ORIGINAL_GIT_BLOB_SHA1_MISMATCH")
            return url,raw
        except (OSError, TimeoutError) as exc:
            last=str(exc)
            if attempt<2:
                time.sleep(2*(attempt+1))
    raise RuntimeError("PINNED_SOURCE_UNAVAILABLE "+str(last))

def num(v):
    if v is None or str(v).lower() in ("","null","nan","none"):
        return None
    x=float(v)
    return x if math.isfinite(x) else None

def selftest():
    assert blob(b"hello\n")=="ce013625030ba8dba906f756967f9e9ca394464a"
    r=parse(b"date,CapMVRVCur,CapRealUSD,CapMrktCurUSD\n2019-12-30,1.33,100,133\n")
    assert r["rows"]==1 and r["anchorRows"]["2019-12-30"]["CapMVRVCur"]=="1.33"
    assert 1.325 <= 1.33 < 1.335
    assert not 1.325 <= 1.34 < 1.335
    print("V818C4_SELFTEST_PASS",flush=True)

def main():
    prereg_raw=PREREG.read_bytes()
    spec=json.loads(prereg_raw)
    if spec["version"]!="8.18c4" or not spec["researchOnly"]:
        raise ValueError("INVALID_PREREG")
    original=spec["upstream"]["earlyGitBlob"]
    newer=spec["upstream"]["historicalGitBlob"]
    rootrepo="croque-m/coinmetrics-data"
    oldurl,oldraw=fetch(rootrepo,original["commit"],original["blob"],original["bytes"])
    newurl,newraw=fetch(rootrepo,newer["commit"],newer["blob"],newer["bytes"])
    old=parse(oldraw)
    new=parse(newraw)
    if old["columns"]["CapMVRVCur"] or old["columns"]["CapRealUSD"]:
        raise ValueError("FROZEN_2018_COLUMN_ASSUMPTION_CHANGED")
    if not new["columns"]["CapMVRVCur"] or not new["columns"]["CapRealUSD"]:
        raise ValueError("FROZEN_2020_COLUMN_ASSUMPTION_CHANGED")
    anchor=new["anchorRows"].get(spec["frozenAnchor"]["observationDate"])
    if anchor is None:
        raise ValueError("NO_2019_12_30_ANCHOR")
    mvrv=num(anchor["CapMVRVCur"])
    capreal=num(anchor["CapRealUSD"])
    capmrkt=num(anchor["CapMrktCurUSD"])
    if mvrv is None or capreal is None or capmrkt is None or capreal<=0:
        raise ValueError("MVRV_ANCHOR_MISSING_NUMBERS")
    ratio=capmrkt/capreal
    tol=spec["frozenAnchor"]["relativeArithmeticRatioTolerance"]
    exact=math.isclose(mvrv,ratio,rel_tol=tol,abs_tol=tol)
    match=1.325<=mvrv<1.335
    status=("HISTORIC_MVRV_MATCHES_PUBLIC_2019_ANCHOR_WITH_PROVENANCE_LIMITS"
            if match and exact else "HISTORICAL_MVRV_ANCHOR_MISMATCH")
    report={
        "version":"8.18c4","status":status,"researchOnly":True,"tradeAuthorized":False,
        "prereg":{"path":str(PREREG.relative_to(ROOT)),"sha256":digest(prereg_raw)},
        "historicSources":[
            {"label":"2018-07-11","url":oldurl,"blob":blob(oldraw),"sha256":digest(oldraw),
             "bytes":len(oldraw),"rows":old["rows"],"columns":old["columns"]},
            {"label":"2020-01-31","url":newurl,"blob":blob(newraw),"sha256":digest(newraw),
             "bytes":len(newraw),"rows":new["rows"],"columns":new["columns"]}
        ],
        "original2018Publication":{"date":"2018-10-01","source":spec["upstream"]["firstMvrvPublication"],
                                   "proof":"MVRV concept was already openly described; not original CSV daily availability"},
        "contemporaneous2020Publication":{"date":"2020-01-01","reportedMVRV":1.33,
                                         "observationDate":"2019-12-30","source":spec["upstream"]["contemporaneousArticle"]},
        "historical2020CSV":{"observationDate":"2019-12-30","mvrv":mvrv,"capRealUSD":capreal,
                              "capMrktUSD":capmrkt,"recomputedRatio":ratio,
                              "roundedValueEqualsPublication":match,
                              "ratioInternalConsistency":exact},
        "limits":[
            "Jan 2020 public article anchors the rounded 2019-12-30 MVRV; later Jan 2020 CSV does not independently prove this CSV was accessible Jan 1.",
            "2018 Oct paper proves concept, not contemporaneous availability of 2012-2018 daily MVRV vintages.",
            "2024 fork preserves old Git objects but their old timestamps are not standalone independent publication-date proof.",
            "MVRV price-derived: consistency with public article does not establish predictive power.",
            "No BTC outcomes, model threshold selection, OOS claim, or validated trade signal."
        ],
        "portfolioWriteback":{x:False for x in ("Spot","Futures","NAV","PnL","capital","reserve","MASTER","Detector","tradingLimits","orders")}
    }
    out=Path("btci_v818c4_reports")
    out.mkdir(exist_ok=True)
    payload=(json.dumps(report,ensure_ascii=False,indent=2)+"\n").encode()
    (out/"contemporaneous_2019_mvrv_anchor_FULL.json").write_bytes(payload)
    s3=boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
                     aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
    bucket=os.environ["R2_BUCKET"]
    prefix="research/btci/v8.18c4/runs/{}-{}/".format(os.environ["GITHUB_RUN_ID"],os.environ.get("GITHUB_RUN_ATTEMPT","1"))
    def put(name,raw):
        key=prefix+name
        checksum=digest(raw)
        s3.put_object(Bucket=bucket,Key=key,Body=raw,ContentType="application/json",Metadata={"sha256":checksum,"research-only":"true"})
        got=s3.get_object(Bucket=bucket,Key=key)["Body"].read()
        if digest(got)!=checksum:
            raise ValueError("R2_SHA_READBACK_MISMATCH")
        return {"key":key,"sha256":checksum,"bytes":len(raw)}
    r=put("contemporaneous_2019_mvrv_anchor_FULL.json",payload)
    manifest=(json.dumps({"version":"8.18c4","status":status,"researchOnly":True,
                          "report":r,"preregSha256":digest(prereg_raw),
                          "noPortfolioWriteback":True},ensure_ascii=False,indent=2)+"\n").encode()
    mm=put("manifest.json",manifest)
    result={"status":status,"mvrvArchived":mvrv,"mvrvPublicRounded":1.33,
            "roundedMatch":match,"arithmeticConsistency":exact,
            "reportSha256":r["sha256"],"manifestSha256":mm["sha256"],"prefix":prefix}
    (out/"summary.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print("V818C4_RESULT "+json.dumps(result,ensure_ascii=False),flush=True)

if __name__=="__main__":
    if "--self-test" in sys.argv:
        selftest()
    else:
        main()
