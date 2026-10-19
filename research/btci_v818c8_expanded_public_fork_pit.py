#!/usr/bin/env python3
"""BTCI v8.18c8 - pre-registered expansion of GitHub public witness MVRV ledger, RESEARCH_ONLY."""
import csv
import hashlib
import io
import json
import math
import os
import sys
import time
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import boto3

ROOT=Path(__file__).resolve().parents[1]
SPEC=ROOT/"research/btci_v818c8_expanded_public_fork_pit_prereg_2026-10-19.json"

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def gitblob(raw):
    return hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()

def dt(t):
    return datetime.fromisoformat(t.replace("Z","+00:00"))

def get(url,capacity=13_000_000):
    err=None
    for k in range(3):
        try:
            request=Request(url,headers={"User-Agent":"BTCI-v818c8-immutable-research-source/1.0"})
            with urlopen(request,timeout=65) as r:
                v=r.read(capacity+1)
            if len(v)>capacity: raise ValueError("SOURCE_TOO_LARGE")
            return v
        except (HTTPError,URLError,TimeoutError) as e:
            err=str(e)
            if k<2: time.sleep(k+2)
    raise RuntimeError("UNAVAILABLE_OR_RATE_LIMITED_SOURCE:"+url+":"+str(err))

def scalar(raw):
    if raw is None or str(raw).strip().lower() in ("","none","null","nan","na"): return None
    v=float(raw)
    return v if math.isfinite(v) else None

def parse_csv(raw):
    reader=csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    cols=reader.fieldnames or []
    datefield="time" if "time" in cols else "date" if "date" in cols else None
    required=("CapMVRVCur","CapRealUSD","CapMrktCurUSD")
    if not datefield: raise ValueError("DATE_COLUMN_MISSING")
    has={k:(k in cols) for k in required}
    values={}
    for row in reader:
        key=(row.get(datefield) or "")[:10]
        date.fromisoformat(key)
        if key in values: raise ValueError("DUPLICATE_DAILY_OBSERVATION")
        values[key]={name:scalar(row.get(name)) for name in required}
    if len(values)<1000: raise ValueError("TRUNCATED_ORIGINAL_ARCHIVE")
    return {"values":values,"columns":has,"rows":len(values),"last":max(values),"first":min(values)}

def witness(day,source):
    d=date.fromisoformat(day)
    if d.weekday()!=6: raise ValueError("SUNDAY_REQUIRED")
    deadline=datetime.combine(d,datetime.min.time(),timezone.utc)
    if source["witnessTime"]>=deadline:
        return None
    if not all(source["fields"].values()):
        return None
    for gap in range(2,8):
        obs=(d-timedelta(days=gap)).isoformat()
        v=source["values"].get(obs)
        if not v: continue
        a,b,c=v.get("CapMVRVCur"),v.get("CapRealUSD"),v.get("CapMrktCurUSD")
        if any(x is None or x<=0 for x in (a,b,c)): continue
        if not math.isclose(a,c/b,rel_tol=0.000005,abs_tol=0.000005): continue
        return {"source":source["name"],"observedDate":obs,"mvrv":a,
            "dailyObservationAgeDays":gap,
            "publicWitnessUTC":source["witnessTime"].isoformat(),
            "gitBTCBlob":source["gitBlob"],
            "classification":"INDEPENDENT_PUBLIC_GITHUB_FORK_NUMERIC_WITNESS_ONLY"}
    return None

def self_test():
    assert gitblob(b"hello\n")=="ce013625030ba8dba906f756967f9e9ca394464a"
    x=parse_csv(b"date,CapMVRVCur,CapRealUSD,CapMrktCurUSD\n2018-01-01,1.5,20,30\n"+b"".join(
        f"2018-01-{d:02d},1.5,20,30\n".encode() for d in range(2,32))
        +b"".join(f"2018-02-{d:02d},1.5,20,30\n".encode() for d in range(1,29))) if False else None
    src={"name":"test","witnessTime":dt("2021-04-17T03:23:32Z"),
        "fields":{"CapMVRVCur":True,"CapRealUSD":True,"CapMrktCurUSD":True},
        "gitBlob":"xx","values":{"2021-04-16":{"CapMVRVCur":1.5,"CapRealUSD":20,"CapMrktCurUSD":30}}}
    good=witness("2021-04-18",src)
    assert good and good["observedDate"]=="2021-04-16" and good["dailyObservationAgeDays"]==2
    assert witness("2021-04-11",src) is None
    assert witness("2021-04-25",src) is None
    src["fields"]["CapRealUSD"]=False
    assert witness("2021-04-18",src) is None
    print("V818C8_SELFTEST_PASS",flush=True)

def main():
    specbytes=SPEC.read_bytes()
    p=json.loads(specbytes)
    if p["version"]!="8.18c8" or not p["researchOnly"] or p["tradeAuthority"]:
        raise ValueError("PREREG_CHANGED")
    s3=boto3.client("s3",region_name="auto",
        endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"])
    bucket=os.environ["R2_BUCKET"]
    def pinned(entry,name):
        data=s3.get_object(Bucket=bucket,Key=entry["key"])["Body"].read()
        if sha(data)!=entry["sha256"]: raise ValueError("PARENT_SHA256_MISMATCH_"+name)
        return json.loads(data)
    base=pinned(p["parents"]["btcPanel"],"BTC684")
    old=pinned(p["parents"]["c7PublicWitnesses"],"C7_PUBLIC_FORKS")
    c6=pinned(p["parents"]["c6ZeroProviderClock"],"C6_PROVIDER_CLOCK")
    panel=base["weeklyPanel"]
    first=[r["date"] for r in panel]
    if len(first)!=684 or len(set(first))!=684 or first!=sorted(first):
        raise ValueError("PARENT_684_PANEL_CHANGED")
    oldrows=old["perSundayAsOfWitness"]
    if [r["date"] for r in oldrows]!=first or [r["date"] for r in c6["perSundayEligibility"]]!=first:
        raise ValueError("OLD_PARENT_WEEKS_NOT_MATCHED")
    if old["independentlyDatedPublicExactMVRVWitnessWeeks"]!=3 or old["originalProviderDailyPublicationTimeVerifiedWeeks"]!=0:
        raise ValueError("C7_PARENT_WITNESS_STATUS_CHANGED")
    if c6["strictOriginalPublicationVerifiedWeeks"]!=0: raise ValueError("C6_PIT_STATUS_CHANGED")
    histories=[]
    audits=[]
    for cfg in p["sources"]:
        name=cfg["repo"]
        rep=json.loads(get("https://api.github.com/repos/"+name,250_000))
        ref=json.loads(get("https://api.github.com/repos/"+name+"/git/ref/heads/master",120_000))
        if not rep.get("fork") or rep.get("source",{}).get("full_name")!="coinmetrics/data" or rep.get("private"):
            raise ValueError("NOT_PUBLIC_COINMETRICS_FORK_"+name)
        if rep["created_at"]!=cfg["createdUTC"] or rep["pushed_at"]!=cfg["pushedUTC"] or ref["object"]["sha"]!=cfg["headCommit"]:
            raise ValueError("FORK_METADATA_NO_LONGER_MATCHES_"+name)
        t=json.loads(get("https://api.github.com/repos/"+name+"/git/trees/"+cfg["headCommit"]+"?recursive=1",1_000_000))
        blob=next((v for v in t["tree"] if v["path"]=="csv/btc.csv"),None)
        if not blob or blob["sha"]!=cfg["btcBlobSha1"] or blob["size"]!=cfg["bytes"]:
            raise ValueError("FROZEN_BTC_TREE_BLOB_MISMATCH_"+name)
        raw=get("https://raw.githubusercontent.com/"+name+"/"+cfg["headCommit"]+"/csv/btc.csv",13_000_000)
        if len(raw)!=cfg["bytes"] or gitblob(raw)!=cfg["btcBlobSha1"]:
            raise ValueError("GIT_BLOB_INTEGRITY_FAILURE_"+name)
        parsed=parse_csv(raw)
        when=max(dt(cfg["createdUTC"]),dt(cfg["pushedUTC"]))
        histories.append({"name":name,"witnessTime":when,"fields":parsed["columns"],
            "values":parsed["values"],"gitBlob":cfg["btcBlobSha1"]})
        audits.append({"name":name,"publicForkCreatedUTC":cfg["createdUTC"],
            "latestPushUTC":cfg["pushedUTC"],"publicWitnessUTC":when.isoformat(),
            "masterCommit":cfg["headCommit"],"fileGitSha1":cfg["btcBlobSha1"],
            "sourceCsvSha256":sha(raw),"fileBytes":len(raw),"records":parsed["rows"],
            "first":parsed["first"],"last":parsed["last"],"columns":parsed["columns"],
            "firstOfficialPublisherDailyReleaseClockVerified":False})
        print("V818C8_SOURCE "+json.dumps({"repo":name,"rows":parsed["rows"],
            "hasMVRV":all(parsed["columns"].values()),"last":parsed["last"]}),flush=True)
    rows=[]
    era=defaultdict(lambda:{"weeks":0,"totalForkWitnessWeeks":0,"newForkAddedWeeks":0})
    newdays=[]
    for original,prior in zip(panel,oldrows):
        day=original["date"]
        initial=prior["evidence"]
        inherited=None
        if initial is not None:
            inherited={"source":initial["source"],"observedDate":initial["observationDate"],
                "mvrv":initial["mvrv"],"dailyObservationAgeDays":initial["ageDays"],
                "publicWitnessUTC":initial["firstIndependentPublicWitnessUTC"],
                "gitBTCBlob":initial["historicGitBlobSHA1"],
                "classification":"INHERITED_C7_PUBLIC_GITHUB_FORK_NUMERIC_WITNESS_ONLY"}
        potential=[v for source in histories if (v:=witness(day,source)) is not None]
        if inherited: potential.append(inherited)
        potential.sort(key=lambda x:x["publicWitnessUTC"],reverse=True)
        chosen=potential[0] if potential else None
        prior_yes=initial is not None
        new_yes=not prior_yes and chosen is not None
        if new_yes: newdays.append(day)
        e=original["era"]
        era[e]["weeks"]+=1
        era[e]["totalForkWitnessWeeks"]+=int(chosen is not None)
        era[e]["newForkAddedWeeks"]+=int(new_yes)
        rows.append({"date":day,"era":e,"publicGitHubForkMvrvEvidence":chosen is not None,
            "inheritedC7Witness":prior_yes,"newWitnessBeyondC7":new_yes,
            "numericEvidence":chosen,"originalProviderPublicationClockVerified":False,
            "status":"INDEPENDENT_GITHUB_SNAPSHOT_NUMERIC_ASOF_ONLY" if chosen else "UNKNOWN_OR_UNVERIFIED_ASOF"})
    total=sum(r["publicGitHubForkMvrvEvidence"] for r in rows)
    if total<3 or len(newdays)+3!=total:
        raise ValueError("INHERITED_C7_WITNESSES_LOST_OR_COUNT_MISMATCH")
    bysource=dict(sorted(Counter(r["numericEvidence"]["source"] for r in rows if r["numericEvidence"]).items()))
    report={"version":"8.18c8","researchOnly":True,"tradeAuthorized":False,
        "status":"PUBLIC_FORK_ASOF_EVIDENCE_EXPANDED_PROVIDER_RELEASE_CLOCK_UNVERIFIED",
        "prereg":{"path":str(SPEC.relative_to(ROOT)),"sha256":sha(specbytes)},
        "parents":p["parents"],"unchanged684SundayCohort":True,"weeks":684,
        "parentC7NumericWitnessWeeks":3,"newIndependentForkWitnessWeeks":len(newdays),
        "cumulativePublicForkWitnessWeeks":total,
        "originalProviderDailyPublicationClockVerifiedWeeks":0,
        "newWitnessDates":newdays,"allWitnessDates":[r["date"] for r in rows if r["publicGitHubForkMvrvEvidence"]],
        "bySource":bysource,"byEra":dict(sorted(era.items())),
        "sourceAudits":audits,"perSundayEvidence":rows,
        "limitations":[
            "Public GitHub archived fork creation/upload is strong independent numeric snapshot evidence, not proof of Coin Metrics original daily API first-seen publication clock.",
            "An archived file can have retrospective historical rows; only observations from at least two days prior and within seven days were considered, and snapshot must predate Sunday.",
            "The 684 future price labels were not examined; no forecasting performance, thresholds, optimization or trades.",
            "Old third-party fork data may be frozen at creation; do not forward fill beyond seven days.",
            "Traditional MVRV definition distinct from free-float; neither is claimed to improve BTC price prediction.",
            "No historic value prior to earliest available snapshot can be projected backwards, and missing source data were never imputed."
        ],"portfolioWriteback":{x:False for x in p["frozenRequirements"]["noTradeMutation"]}}
    folder=Path("btci_v818c8_reports");folder.mkdir(exist_ok=True)
    raw=(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+"\n").encode()
    (folder/"independent_fork_684_asof_expansion_FULL.json").write_bytes(raw)
    prefix="research/btci/v8.18c8/runs/{}-{}/".format(os.environ["GITHUB_RUN_ID"],os.getenv("GITHUB_RUN_ATTEMPT","1"))
    def store(name,data):
        key=prefix+name; digest=sha(data)
        s3.put_object(Bucket=bucket,Key=key,Body=data,ContentType="application/json",
            Metadata={"sha256":digest,"research-only":"true"})
        got=s3.get_object(Bucket=bucket,Key=key)["Body"].read()
        if sha(got)!=digest: raise ValueError("R2_REPORT_SHA_READBACK_FAILED")
        return {"key":key,"sha256":digest,"bytes":len(data)}
    rep=store("independent_fork_684_asof_expansion_FULL.json",raw)
    manifest=store("manifest.json",(json.dumps({"version":"8.18c8",
        "status":report["status"],"researchOnly":True,"report":rep,
        "preregSha256":sha(specbytes),"priorC7ReportSha256":p["parents"]["c7PublicWitnesses"]["sha256"],
        "noPortfolioMutation":True},ensure_ascii=False,indent=2)+"\n").encode())
    summary={"status":report["status"],"weeks":684,"prior":3,"new":len(newdays),
        "total":total,"newDates":newdays,"dates":report["allWitnessDates"],
        "bySource":bysource,"byEra":report["byEra"],"providerFirstSeenVerified":0,
        "reportSha256":rep["sha256"],"manifestSha256":manifest["sha256"],"prefix":prefix}
    (folder/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n")
    print("V818C8_RESULT "+json.dumps(summary,ensure_ascii=False),flush=True)

if __name__=="__main__":
    if "--self-test" in sys.argv: self_test()
    else: main()
