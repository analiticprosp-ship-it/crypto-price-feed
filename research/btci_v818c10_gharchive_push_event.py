#!/usr/bin/env python3
"""BTCI v8.18c10 — independent GH Archive PushEvent verification, research-only."""
import csv
import gzip
import hashlib
import io
import json
import math
import os
import sys
import time
from datetime import date,datetime,timedelta,timezone
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError,URLError
import boto3

ROOT=Path(__file__).resolve().parents[1]
SPEC=ROOT/"research/btci_v818c10_gharchive_push_event_prereg_2026-10-19.json"

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def git_blob_sha(raw):
    return hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()

def timestamp(s):
    return datetime.fromisoformat(s.replace("Z","+00:00"))

def number(s):
    if s is None or str(s).strip().lower() in ("","null","nan","none","na"):
        return None
    v=float(s)
    return v if math.isfinite(v) else None

class Meter:
    def __init__(self,fh,limit):
        self.fh=fh
        self.limit=limit
        self.length=0
        self.hash=hashlib.sha256()
    def read(self,n=-1):
        raw=self.fh.read(n)
        self.length+=len(raw)
        if self.length>self.limit:
            raise ValueError("GHARCHIVE_COMPRESSED_SIZE_OVER_LIMIT")
        self.hash.update(raw)
        return raw

def match_event(evt,expected,sunday,datekey,hour):
    if evt.get("type")!="PushEvent" or evt.get("repo",{}).get("name")!="coinmetrics/data":
        return None
    pub=timestamp(evt["created_at"])
    if pub.date().isoformat()!=datekey or pub.hour!=hour or pub>=datetime.combine(date.fromisoformat(sunday),datetime.min.time(),timezone.utc):
        return None
    payload=evt.get("payload") or {}
    refs=[payload.get("head"),payload.get("after")]
    refs.extend(x.get("sha") for x in payload.get("commits",[]) if isinstance(x,dict))
    if expected not in refs:
        return None
    return {"eventId":str(evt.get("id")),"createdAtUTC":pub.isoformat(),
            "repo":evt["repo"]["name"],"type":evt["type"],
            "head":payload.get("head"),"ref":payload.get("ref"),
            "matchedSha":expected,"commitCount":len(payload.get("commits",[])),
            "matchFrom":"payload HEAD, after, or listed commit SHA"}

def get_json(url,limit=4_000_000):
    with urlopen(Request(url,headers={"User-Agent":"btci-v818c10-source-forensics"}),timeout=45) as f:
        r=f.read(limit+1)
    if len(r)>limit:
        raise ValueError("GIT_METADATA_TOO_LARGE")
    return json.loads(r)

def original_source(s,obs):
    repo=s["gitArchiveRepo"]
    commit=s["expectedCommitSha"]
    tree=get_json("https://api.github.com/repos/"+repo+"/git/trees/"+commit+"?recursive=1",10_000_000)
    file=next((v for v in tree["tree"] if v.get("path")=="csv/btc.csv"),None)
    if not file:
        raise ValueError("SOURCE_BTC_CSV_NOT_IN_COMMIT")
    link="https://raw.githubusercontent.com/"+repo+"/"+commit+"/csv/btc.csv"
    with urlopen(Request(link,headers={"User-Agent":"btci-v818c10-source-forensics"}),timeout=55) as f:
        raw=f.read(15_000_000)
    if len(raw)!=file.get("size") or git_blob_sha(raw)!=file["sha"]:
        raise ValueError("SOURCE_CSV_GIT_BLOB_SHA_MISMATCH")
    reader=csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    fields=reader.fieldnames or []
    datefield="time" if "time" in fields else "date" if "date" in fields else None
    required=("CapMVRVCur","CapRealUSD","CapMrktCurUSD")
    if not datefield or any(x not in fields for x in required):
        return {"status":"TRIAD_NOT_IN_ARCHIVED_SOURCE","gitBlob":file["sha"],"sha256":sha(raw)}
    day=date.fromisoformat(s["sunday"])
    allowed={(day-timedelta(days=k)).isoformat():k for k in range(2,8)}
    valid=[]
    for r in reader:
        d=(r.get(datefield) or "")[:10]
        if d not in allowed:
            continue
        mv,real,cap=(number(r.get(x)) for x in required)
        if any(x is None or x<=0 for x in (mv,real,cap)):
            continue
        if math.isclose(mv,cap/real,rel_tol=0.000005,abs_tol=0.000005):
            valid.append((d,mv,allowed[d]))
    if not valid:
        return {"status":"NO_CONSISTENT_FRIDAY_TO_7D_OBSERVATION","gitBlob":file["sha"],"sha256":sha(raw)}
    d,mvrv,lag=max(valid)
    return {"status":"ORIGINAL_GIT_BLOB_AND_MVRV_TRIAD_PASS",
            "observation":d,"lagDays":lag,"mvrv":mvrv,
            "sourceRepo":repo,"sourceCommit":commit,
            "gitBlob":file["sha"],"sourceSha256":sha(raw)}

def event_hour(case,limits):
    day=case["date"];hour=case["hourUTC"]
    url=f"https://data.gharchive.org/{day}-{hour}.json.gz"
    result={"url":url,"status":"UNRESOLVED","totalEvents":0,
            "originalRepoPushEvents":0,"matchedEvents":[],"compressedBytes":0,
            "compressedSha256":None,"sourceError":None}
    try:
        req=Request(url,headers={"User-Agent":"BTCI-v818c10-audit/1.0"})
        with urlopen(req,timeout=limits["perUrlTimeoutSeconds"]) as response:
            met=Meter(response,limits["maxCompressedBytesEach"])
            with gzip.GzipFile(fileobj=met,mode="rb") as gz:
                for line in gz:
                    result["totalEvents"]+=1
                    if result["totalEvents"]>limits["maxJsonEventLinesEach"]:
                        raise ValueError("GHARCHIVE_EVENT_LIMIT")
                    if b"coinmetrics/data" not in line or b"PushEvent" not in line:
                        continue
                    ev=json.loads(line)
                    if ev.get("type")=="PushEvent" and ev.get("repo",{}).get("name")=="coinmetrics/data":
                        result["originalRepoPushEvents"]+=1
                    matched=match_event(ev,case["expectedCommitSha"],case["sunday"],day,hour)
                    if matched is not None:
                        result["matchedEvents"].append(matched)
            result["compressedBytes"]=met.length
            result["compressedSha256"]=met.hash.hexdigest()
        result["status"]="MATCHED_ORIGINAL_REPO_PUSH_EVENT" if result["matchedEvents"] else "NO_MATCH_IN_ARCHIVED_HOUR_NOT_ABSENCE_PROOF"
    except Exception as exc:
        result["status"]="ARCHIVE_UNAVAILABLE_OR_INVALID_NOT_NEGATIVE_EVIDENCE"
        result["sourceError"]=(str(type(exc).__name__)+": "+str(exc))[:350]
    return result

def selftest():
    assert git_blob_sha(b"hello\n")=="ce013625030ba8dba906f756967f9e9ca394464a"
    case={"id":"abc","type":"PushEvent","created_at":"2020-04-04T13:10:00Z",
          "repo":{"name":"coinmetrics/data"},"payload":{"head":"abcd","commits":[]}}
    assert match_event(case,"abcd","2020-04-05","2020-04-04",13)
    assert not match_event(case,"abcd","2020-04-05","2020-04-03",13)
    assert not match_event(case,"nothere","2020-04-05","2020-04-04",13)
    assert not match_event(case,"abcd","2020-04-05","2020-04-04",12)
    print("V818C10_SELFTEST_PASS",flush=True)

def main():
    spec_raw=SPEC.read_bytes();spec=json.loads(spec_raw)
    if spec["version"]!="8.18c10" or not spec["researchOnly"] or spec["tradeAuthorized"]:
        raise ValueError("PREREG_GUARD")
    s3=boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
                    region_name="auto",aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
                    aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"])
    bucket=os.environ["R2_BUCKET"]
    def pinned(entry):
        raw=s3.get_object(Bucket=bucket,Key=entry["key"])["Body"].read()
        if sha(raw)!=entry["sha256"]:
            raise ValueError("PINNED_PARENT_SHA256_INVALID")
        return json.loads(raw)
    parent=pinned(spec["parent"]["c9Report"]);btc=pinned(spec["parent"]["btcPanel"])
    dates=[r["date"] for r in btc["weeklyPanel"]]
    if len(dates)!=684 or len(set(dates))!=684 or parent["version"]!="8.18c9":
        raise ValueError("684_PANEL_OR_PARENT_CHANGED")
    if any(c["sunday"] not in dates for c in spec["frozenTestCases"]):
        raise ValueError("NOT_FROZEN_BTCI_SUNDAY")
    cases=[]
    for idx,case in enumerate(spec["frozenTestCases"],1):
        gh=event_hour(case,spec["sourceBoundaries"])
        source=original_source(case,case["sunday"])
        genuine=(gh["status"]=="MATCHED_ORIGINAL_REPO_PUSH_EVENT" and
                 source["status"]=="ORIGINAL_GIT_BLOB_AND_MVRV_TRIAD_PASS")
        record={"sunday":case["sunday"],"date":case["date"],"hourUTC":case["hourUTC"],
                "expectedGitCommit":case["expectedCommitSha"],"archive":gh,
                "originalGitSource":source,
                "independentOriginalRepoPublicPushWitnessBeforeDecision":genuine,
                "interpretation":"Original GitHub public PushEvent and matched archived MVRV" if genuine else
                "NOT_QUALIFIED: missing or incomplete independent source proof"}
        cases.append(record)
        print("V818C10_CASE "+json.dumps({"case":idx,"sunday":case["sunday"],
                "archiveStatus":gh["status"],"sourceStatus":source["status"],
                "matchedEvents":len(gh["matchedEvents"]),"publicPushWitness":genuine,
                "archiveError":gh["sourceError"]},ensure_ascii=False),flush=True)
    found=[c["sunday"] for c in cases if c["independentOriginalRepoPublicPushWitnessBeforeDecision"]]
    report={"version":"8.18c10","status":"INDEPENDENT_GH_ARCHIVE_PUSH_EVENT_PILOT_COMPLETED",
        "researchOnly":True,"tradeAuthorized":False,
        "preregSHA256":sha(spec_raw),"parent":spec["parent"],"original684WeeksUnchanged":True,
        "totalFrozenHours":len(cases),"originalRepoPublicPushWitnessDates":found,
        "originalProviderAPIReleaseClockVerified":0,
        "cases":cases,
        "constraints":[
            "GH Archive historical public PushEvent is independent timestamp evidence for one original GitHub commit, not Coin Metrics API publication clock.",
            "Three preselected Saturday 13:00 UTC hours only; no shifting windows to force match.",
            "Absence from GH Archive is nonproof, not proof event never happened.",
            "Even proven historical public availability does not prove BTCI predictive value or historical trading utility.",
            "Original 684 panel and 11 independently as-of fork witnesses are unchanged; no signal backtest performed."
        ],"portfolioWriteback":spec["portfolioWriteback"]}
    raw=(json.dumps(report,ensure_ascii=False,indent=2)+"\n").encode()
    folder=Path("btci_v818c10_reports");folder.mkdir(exist_ok=True)
    (folder/"gharchive_push_event_pilot_FULL.json").write_bytes(raw)
    prefix="research/btci/v8.18c10/runs/{}-{}/".format(
        os.environ["GITHUB_RUN_ID"],os.getenv("GITHUB_RUN_ATTEMPT","1"))
    def save(name,payload):
        key=prefix+name;dg=sha(payload)
        s3.put_object(Bucket=bucket,Key=key,Body=payload,
                      ContentType="application/json",Metadata={"sha256":dg,"research-only":"true"})
        echo=s3.get_object(Bucket=bucket,Key=key)["Body"].read()
        if sha(echo)!=dg:raise RuntimeError("R2_SHA_READBACK_FAILURE")
        return {"key":key,"sha256":dg,"bytes":len(payload)}
    out=save("gharchive_push_event_pilot_FULL.json",raw)
    manifest=save("manifest.json",(json.dumps({"version":"8.18c10","researchOnly":True,
        "report":out,"preregSHA256":sha(spec_raw),"noTradeAuthority":True},
        ensure_ascii=False,indent=2)+"\n").encode())
    summary={"status":report["status"],"frozenHours":len(cases),"independentProviderGitHubPushWitnesses":found,
        "providerOriginalAPIReleaseClockVerified":0,
        "cases":[{"date":c["sunday"],"status":c["archive"]["status"],
                  "compressedBytes":c["archive"]["compressedBytes"],
                  "events":c["archive"]["totalEvents"],
                  "sourceStatus":c["originalGitSource"]["status"],
                  "error":c["archive"]["sourceError"]} for c in cases],
        "reportSha256":out["sha256"],"manifestSha256":manifest["sha256"],"prefix":prefix}
    (folder/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n")
    print("V818C10_RESULT "+json.dumps(summary,ensure_ascii=False),flush=True)
if __name__=="__main__":
    selftest() if "--self-test" in sys.argv else main()
