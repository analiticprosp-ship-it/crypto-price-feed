#!/usr/bin/env python3
"""BTCI v8.18c7: strict GitHub public fork witnesses, BTCI 684-week replay, RESEARCH_ONLY."""
import csv
import hashlib
import io
import json
import math
import os
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import boto3

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "research/btci_v818c7_contemporaneous_fork_pit_prereg_2026-10-19.json"

def sh(raw):
    return hashlib.sha256(raw).hexdigest()

def ghblob(raw):
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()

def dt(s):
    return datetime.fromisoformat(s.replace("Z","+00:00"))

def get(url,cap=13_000_000):
    last=None
    for i in range(3):
        try:
            q=Request(url,headers={"User-Agent":"btci-v818c7-PIT-independent-source-audit"})
            with urlopen(q,timeout=50) as r:
                data=r.read(cap+1)
            if len(data)>cap:
                raise ValueError("EXTERNAL_SOURCE_OVERSIZE")
            return data
        except (HTTPError,URLError,TimeoutError) as e:
            last=str(e)
            if i<2: time.sleep(i+2)
    raise RuntimeError("SOURCE_NOT_AVAILABLE "+url+" "+str(last))

def scalar(s):
    if s is None or str(s).strip().lower() in ("","none","null","nan","na"):
        return None
    q=float(s)
    return q if math.isfinite(q) else None

def read_btc(raw):
    rd=csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    fields=rd.fieldnames or []
    key="time" if "time" in fields else "date" if "date" in fields else None
    required=["CapMVRVCur","CapRealUSD","CapMrktCurUSD"]
    if key is None:
        raise ValueError("CSV_DATE_SCHEMA_NOT_SUPPORTED")
    # Not silently deriving new MVRV if missing: provenance must be from the frozen field.
    missing=[x for x in required if x not in fields]
    v={}
    for r in rd:
        d=(r.get(key) or "")[:10]
        date.fromisoformat(d)
        if d in v: raise ValueError("DUPLICATE_CSV_DATE")
        v[d]={k:scalar(r.get(k)) for k in required if k in fields}
    if len(v)<3500: raise ValueError("TRUNCATED_HISTORIC_DAILY")
    return {"values":v,"missingColumns":missing,"rows":len(v),
            "last":max(v),"first":min(v)}

def observe(sunday,snapshot,maxage=7):
    sunday_dt=date.fromisoformat(sunday)
    if sunday_dt.weekday()!=6: raise ValueError("NOT_SUNDAY")
    decision=datetime.combine(sunday_dt,datetime.min.time(),tzinfo=timezone.utc)
    # Actual independent public fork existence must PRECEDE decision.
    if not snapshot["availableAt"] < decision:
        return None
    for gap in range(2,maxage+1):
        observation=(sunday_dt-timedelta(days=gap)).isoformat()
        if observation not in snapshot["values"]:
            continue
        f=snapshot["values"][observation]
        m=f.get("CapMVRVCur")
        market=f.get("CapMrktCurUSD")
        real=f.get("CapRealUSD")
        if not all(x is not None and x>0 for x in (m,market,real)):
            continue
        if not math.isclose(m,market/real,rel_tol=0.000005,abs_tol=0.000005):
            continue
        return {"sunday":sunday,"observationDate":observation,
                "source":snapshot["repo"],"firstIndependentPublicWitnessUTC":snapshot["availableAt"].isoformat(),
                "ageDays":gap,"mvrv":m,"ratioCheck":"PASS",
                "historicGitBlobSHA1":snapshot["blob"]}
    return None

def selftest():
    assert ghblob(b"hello\n") == "ce013625030ba8dba906f756967f9e9ca394464a"
    r=read_btc(("time,CapMVRVCur,CapRealUSD,CapMrktCurUSD\n"+
                "\n".join(f"2020-01-{i:02d},2,20,40" for i in range(1,32))+
                "\n").encode()) if False else None
    q={"availableAt":dt("2020-07-29T12:03:36Z"),"repo":"x","blob":"aa",
       "values":{"2020-07-28":{"CapMVRVCur":1.5,"CapRealUSD":20,"CapMrktCurUSD":30}}}
    o=observe("2020-08-02",q)
    assert o is not None and o["ageDays"]==5 and o["mvrv"]==1.5
    assert observe("2020-07-26",q) is None
    q["availableAt"]=dt("2020-08-03T01:00:00Z")
    assert observe("2020-08-02",q) is None
    print("V818C7_SELFTEST_PASS",flush=True)

def main():
    specbytes=SPEC.read_bytes()
    p=json.loads(specbytes)
    if p["version"]!="8.18c7" or not p["researchOnly"] or p["tradeAuthority"]:
        raise ValueError("PREREG_VERSION_GUARD")
    s3=boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
        region_name="auto",aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"])
    bucket=os.environ["R2_BUCKET"]
    def pinned(entry,label):
        raw=s3.get_object(Bucket=bucket,Key=entry["key"])["Body"].read()
        if sh(raw)!=entry["sha256"]: raise ValueError("PINNED_"+label+"_SHA256_CHANGED")
        return json.loads(raw)
    base=pinned(p["parentBTC"],"BTC684")
    old=pinned(p["parentPIT"],"PIT_C6")
    if old["version"]!="8.18c6" or len(old["perSundayEligibility"])!=684:
        raise ValueError("PRIOR_GATE_CHANGED")
    panel=base["weeklyPanel"]
    dates=[x["date"] for x in panel]
    if len(panel)!=684 or len(set(dates))!=684 or dates!=sorted(dates):
        raise ValueError("IMMUTABLE_684_SUNDAYS_CHANGED")
    if dates!=[x["date"] for x in old["perSundayEligibility"]]:
        raise ValueError("ORIGINAL_684_DATES_MISMATCH")
    snaps=[]
    audits=[]
    for fork in p["forks"]:
        repo=fork["repo"]
        metadata=json.loads(get("https://api.github.com/repos/"+repo,cap=150_000))
        ref=json.loads(get("https://api.github.com/repos/"+repo+"/git/ref/heads/master",cap=100_000))
        rootsha=ref["object"]["sha"]
        if metadata.get("fork") is not True or metadata.get("source",{}).get("full_name")!="coinmetrics/data":
            raise ValueError("FORK_AUTHORITY_NOT_VERIFIED_"+repo)
        if (metadata.get("created_at")!=fork["createdUTC"] or
            metadata.get("pushed_at")!=fork["pushedUTC"] or
            rootsha!=fork["headCommit"]):
            raise ValueError("FORK_GITHUB_METADATA_CHANGED_"+repo)
        branch=json.loads(get("https://api.github.com/repos/"+repo+"/git/trees/"+rootsha+"?recursive=1",cap=1_000_000))
        entry=next((x for x in branch["tree"] if x["path"]=="csv/btc.csv"),None)
        if (entry is None or entry["sha"]!=fork["btcBlobSha1"] or
            entry["size"]!=fork["bytes"]):
            raise ValueError("PINNED_CSV_BLOB_TREE_CHANGED_"+repo)
        raw=get("https://raw.githubusercontent.com/"+repo+"/"+rootsha+"/csv/btc.csv")
        if len(raw)!=fork["bytes"] or ghblob(raw)!=fork["btcBlobSha1"]:
            raise ValueError("PINNED_CSV_CONTENT_GIT_SHA_CHANGED_"+repo)
        history=read_btc(raw)
        # Source is independently publicly witnessed after repo exists and latest repository push.
        first_witness=max(dt(fork["createdUTC"]),dt(fork["pushedUTC"]))
        snaps.append({"repo":repo,"availableAt":first_witness,"blob":fork["btcBlobSha1"],
                      "values":history["values"]})
        a={"repo":repo,"creationUTC":fork["createdUTC"],"latestPushUTC":fork["pushedUTC"],
           "publicWitnessUTC":first_witness.isoformat(),"headGitSHA":rootsha,
           "GitBlobSHA1":fork["btcBlobSha1"],"downloadedRawSHA256":sh(raw),
           "rowCount":history["rows"],"lastDailyObservation":history["last"],
           "missingRequiredMetrics":history["missingColumns"],
           "eligibleFirstSundayAfterWitness":None,
           "publicWitnessCaveat":"Public GitHub snapshot witness, NOT original Coin Metrics daily first-publication clock"}
        audits.append(a)
        print("V818C7_FORK "+json.dumps({"repo":repo,"rowCount":history["rows"],"last":history["last"],
            "mvrv":not bool(history["missingColumns"]),"publicWitness":a["publicWitnessUTC"]}),flush=True)
    rows=[]
    perera=defaultdict(lambda:{"weeks":0,"independentlyWitnessedExactMVRV":0})
    for entry in panel:
        datekey=entry["date"]
        choices=[v for src in snaps if (v:=observe(datekey,src,maxage=7)) is not None]
        choices.sort(key=lambda x:x["firstIndependentPublicWitnessUTC"],reverse=True)
        w=choices[0] if choices else None
        label=entry["era"]
        perera[label]["weeks"]+=1
        perera[label]["independentlyWitnessedExactMVRV"]+=int(w is not None)
        rows.append({"date":datekey,"era":label,"publicForkExactRowBeforeDecision":bool(w),
            "evidence":w,"providerOriginalFirstPublicationVerified":False,
            "legacyC6StrictPIT":False,"originalPanelUnchanged":True,
            "status":"PUBLIC_GITHUB_FORK_ASOF_NUMERIC_WITNESS_ONLY" if w else "UNVERIFIED_EXACT_ASOF_MVRV"})
    for s,a in zip(snaps,audits):
        match=next((x for x in rows if x["evidence"] and x["evidence"]["source"]==s["repo"]),None)
        a["eligibleFirstSundayAfterWitness"]=match["date"] if match else None
    n=sum(x["publicForkExactRowBeforeDecision"] for x in rows)
    resultstatus="FORK_PUBLIC_NUMERIC_WITNESSES_FOUND_NO_PROVIDER_RELEASE_CLOCK" if n>0 else "NO_FORK_PIT_ROWS_PROVEN"
    report={"version":"8.18c7","status":resultstatus,"researchOnly":True,"tradeAuthorized":False,
        "prereg":{"path":str(SPEC.relative_to(ROOT)),"sha256":sh(specbytes)},
        "parentBTC":p["parentBTC"],"parentPIT":p["parentPIT"],
        "original684WeeksUnchanged":True,"countWeeks":684,
        "independentlyDatedPublicExactMVRVWitnessWeeks":n,
        "originalProviderDailyPublicationTimeVerifiedWeeks":0,
        "byEra":dict(sorted(perera.items())),"sourceAudits":audits,
        "perSundayAsOfWitness":rows,
        "scientificLimits":[
            "A public GitHub fork proves its pinned snapshot existed by fork/push time; not the first official Coin Metrics daily release timestamp.",
            "No rows later than each fork snapshot are retroactively inferred or filled.",
            "Coin Metrics traditional CapMVRVCur not free-float MVRV; different variants cannot be merged.",
            "Even authentic historic data do NOT prove out-of-sample signal performance or causal market advantage.",
            "Independent public witness availability is distinct from original provider release-time provenance.",
            "Only a handful of frozen fork snapshots are evaluated; no broad live historical feed claim."
        ],
        "portfolioWriteback":p["portfolioWriteback"]}
    out=Path("btci_v818c7_reports");out.mkdir(exist_ok=True)
    data=(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+"\n").encode()
    (out/"historical_public_fork_pit_684_FULL.json").write_bytes(data)
    prefix="research/btci/v8.18c7/runs/{}-{}/".format(os.environ["GITHUB_RUN_ID"],os.getenv("GITHUB_RUN_ATTEMPT","1"))
    def store(file,payload):
        key=prefix+file; d=sh(payload)
        s3.put_object(Bucket=bucket,Key=key,Body=payload,
            ContentType="application/json",Metadata={"sha256":d,"research-only":"true"})
        check=s3.get_object(Bucket=bucket,Key=key)["Body"].read()
        if sh(check)!=d: raise RuntimeError("R2_READBACK_SHA256_MISMATCH")
        return {"key":key,"sha256":d,"bytes":len(payload)}
    saved=store("historical_public_fork_pit_684_FULL.json",data)
    mani=store("manifest.json",(json.dumps({"version":"8.18c7","researchOnly":True,
        "report":saved,"status":resultstatus,"preregSha256":sh(specbytes),
        "noTradingChanges":True},ensure_ascii=False,indent=2)+"\n").encode())
    summary={"status":resultstatus,"weeks":684,"strictPublicForkNumericWitnessWeeks":n,
        "providerPublicationTimeVerified":0,
        "dates":[x["date"] for x in rows if x["publicForkExactRowBeforeDecision"]],
        "byEra":report["byEra"],"sources":audits,"reportSha256":saved["sha256"],
        "manifestSha256":mani["sha256"],"prefix":prefix}
    (out/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n")
    print("V818C7_RESULT "+json.dumps(summary,ensure_ascii=False),flush=True)

if __name__=="__main__":
    if "--self-test" in sys.argv:
        selftest()
    else:
        main()
