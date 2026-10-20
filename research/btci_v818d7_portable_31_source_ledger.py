#!/usr/bin/env python3
"""BTCI v8.18d7: portable 31 dated MVRV witnesses, immutable 684-week scientific source metadata only."""
import hashlib
import json
import math
import os
import sys
from collections import Counter,defaultdict
from datetime import date,datetime,timedelta,timezone
from pathlib import Path
import boto3
ROOT=Path(__file__).resolve().parents[1]
SPEC=ROOT/"research/btci_v818d7_portable_31_source_ledger_prereg_2026-10-20.json"

def sha(raw):return hashlib.sha256(raw).hexdigest()
def utc(s):return datetime.fromisoformat(str(s).replace("Z","+00:00"))
def before(sun,seen,obs,value):
    sund=date.fromisoformat(sun)
    cutoff=datetime.combine(sund,datetime.min.time(),timezone.utc)
    days=(sund-date.fromisoformat(obs)).days
    return (sund.weekday()==6 and utc(seen)<cutoff and 2<=days<=7
           and math.isfinite(float(value)) and float(value)>0)
def separated(days,w):
    result=[]
    for s in sorted(days):
        if not result or date.fromisoformat(s)>=date.fromisoformat(result[-1])+timedelta(weeks=w):
            result.append(s)
    return result

def selftest():
    assert before("2024-05-26","2024-05-25T01:53:26Z","2024-05-23",2.303426)
    assert not before("2024-05-26","2024-05-26T00:01:00Z","2024-05-23",2.3)
    assert not before("2024-05-26","2024-05-25T01:53:26Z","2024-05-25",2.3)
    assert sha(b"hello")==hashlib.sha256(b"hello").hexdigest()
    print("V818D7_SELFTEST_PASS",flush=True)

def main():
    specraw=SPEC.read_bytes()
    s=json.loads(specraw)
    if s["version"]!="8.18d7" or not s["researchOnly"] or s["noTradeAuthority"] is not True:
        raise RuntimeError("INVALID_FROZEN_PREREG")
    client=boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
    bucket=os.environ["R2_BUCKET"]
    def parent(name):
        p=s["parents"][name]
        raw=client.get_object(Bucket=bucket,Key=p["key"])["Body"].read()
        if sha(raw)!=p["sha256"]:raise RuntimeError("PINNED_PARENT_SHA_CHANGED_"+name)
        obj=json.loads(raw)
        if not obj.get("researchOnly") or obj.get("tradeAuthorized",False):
            raise RuntimeError("INVALID_PARENT_AUTHORITY_"+name)
        return obj
    btc=parent("fullBTC")
    prev=parent("portable26")
    recent=parent("calendar8")
    original=btc["weeklyPanel"]
    inherited=prev["weeklyProvenance"]
    days=[r["date"] for r in original]
    if (len(days)!=684 or days!=sorted(set(days)) or len(inherited)!=684
        or days!=[r["date"] for r in inherited]):
        raise ValueError("ORIGINAL_684_DATE_COHORT_CHANGED")
    sourceEvidence={}
    for item in inherited:
        if item["hasIndependentlyDatedNumericMvrv"]:
            for e in item["asofEvidence"]:
                if not before(item["date"],e["availableUTC"],e["observed"],e["mvrv"]):
                    raise ValueError("INHERITED_MVRV_ASOF_SOURCE_INVALID")
            sourceEvidence[item["date"]]=list(item["asofEvidence"])
    if len(sourceEvidence)!=s["expected"]["initialWitnesses"]:
        raise ValueError("INITIAL_DATED_MVRV_WITNESSES_CHANGED")
    if len(recent["individualFrozenSourceHours"])!=s["parents"]["calendar8"]["frozenHours"]:
        raise ValueError("EIGHT_FROZEN_CASES_MODIFIED")
    new=[]
    negative=[]
    for e in recent["individualFrozenSourceHours"]:
        day=e["date"]
        if e["providerOriginalGitHubPublicPushWitness"] is False:
            negative.append({"date":day,"status":e["independentGHArchive"]["status"],
                             "sourceStatus":e["sourceResult"]["status"],
                             "interpretation":"no matched PushEvent in frozen sampled hour, not proof original data unavailable"})
            continue
        gh=e["independentGHArchive"]
        original_src=e["sourceResult"]
        frozen=e["expectedCommitSHA"]
        if (gh["status"]!="MATCHED_ORIGINAL_REPO_PUSH_EVENT"
            or original_src["status"]!="ORIGINAL_GIT_BLOB_AND_MVRV_TRIAD_PASS"
            or original_src["sourceCommit"]!=frozen or not original_src.get("sourceSha256")):
            raise ValueError("NEW_ORIGINAL_GITHUB_EVENT_SOURCE_INCOMPLETE")
        valid=[x for x in gh["matchedEvents"] if x.get("matchedSha")==frozen
               and x.get("repo")=="coinmetrics/data"]
        if not valid:raise ValueError("EXTERNAL_GHARCHIVE_SHA_NOT_MATCHED")
        ev=min(valid,key=lambda x:utc(x["createdAtUTC"]))
        if not before(day,ev["createdAtUTC"],original_src["observation"],original_src["mvrv"]):
            raise ValueError("NEW_PUBLIC_SOURCE_AFTER_WEEKLY_CUTOFF_OR_BAD_MVRV")
        if day in sourceEvidence or day not in days:
            raise ValueError("NEW_PUBLIC_SOURCE_DATE_OVERLAP_OR_NOT_ORIGINAL_PANEL")
        sourceEvidence[day]=[{"date":day,"type":"GHArchive_original_github_PushEvent",
             "source":"coinmetrics/data","availableUTC":ev["createdAtUTC"],
             "observed":original_src["observation"],"mvrv":original_src["mvrv"],
             "sourceHash":original_src["sourceSha256"],"commitSHA":frozen,
             "GHArchiveEventId":ev.get("eventId"),"verifiedParent":"v8.18d6 calendar-eight"}]
        new.append(day)
    if (sorted(new)!=recent["newPublicAsOfMVRVDates"]
        or len(new)!=s["expected"]["newWitnesses"]
        or len(sourceEvidence)!=s["expected"]["total"]):
        raise ValueError("FROZEN_31_UNION_MISMATCH")
    counts=dict(sorted(Counter(e["type"] for sources in sourceEvidence.values() for e in sources).items()))
    if counts!=s["expected"]["sourceBreakdown"]:
        raise ValueError("SOURCE_TYPE_COUNTS_NOT_REPRODUCIBLE")
    era=defaultdict(lambda:{"weeks":0,"historicPublicAsOfMVRVWitnesses":0})
    full=[]
    for row in original:
        day=row["date"];refs=sourceEvidence.get(day,[])
        era[row["era"]]["weeks"]+=1
        era[row["era"]]["historicPublicAsOfMVRVWitnesses"]+=int(bool(refs))
        full.append({"date":day,"era":row["era"],
            "historicalMVRVNumericPublicAsOfVerified":bool(refs),
            "sourceEvidence":refs,"providerOriginalMetricAPIReleaseClockVerified":False,
            "priceOutcomeRecomputed":False,"tradingUsePermitted":False})
    spacings={str(h):{"weeks":h,"timeSeparatedCount":len(separated(sourceEvidence.keys(),h)),
         "timeSeparatedDates":separated(sourceEvidence.keys(),h),
         "independentMarketEventsClaimed":False}
         for h in s["expected"]["horizonsWeeks"]}
    if [spacings[str(h)]["timeSeparatedCount"] for h in s["expected"]["horizonsWeeks"]]!=s["expected"]["greedyNonOverlap"]:
        raise ValueError("TIME_SPACING_PRE_REGISTERED_REFERENCE_CHANGED")
    report={"version":"8.18d7","researchOnly":True,"tradeAuthorized":False,
        "status":"PORTABLE_31_DATED_MVRV_NUMERIC_SOURCE_LEDGER_NO_FORECAST_EDGE",
        "prereg":{"path":str(SPEC.relative_to(ROOT)),"sha256":sha(specraw)},
        "pinnedParents":s["parents"],"original684DatesUnchanged":True,
        "totalWeekDates":684,"publicAsOfMVRVDates":len(sourceEvidence),
        "withoutIndependentSourceProvenance":684-len(sourceEvidence),
        "sourceEvidenceByType":counts,"newIndependentDates":sorted(new),
        "allIndependentDates":sorted(sourceEvidence),
        "frozenCalendarEightNegativeCases":negative,
        "byEra":dict(sorted(era.items())),"nonoverlapCalendarOnly":spacings,
        "originalProviderMetricAPIReleaseClockVerified":0,
        "full684WeekMVRVSourceLedger":full,
        "limits":[
          "31 independently dated source witnesses are sparse and not representative of 684 weeks.",
          "Original Coin Metrics API release clock was not established; GitHub and web archives document source availability only.",
          "Failure to match a frozen GHArchive hour is not proof the publication never occurred.",
          "17/10/5 H-week separated cohorts are only time separations, not independent BTC market episodes or effective samples.",
          "No BTC price outcome examined or predictive test conducted; trading systems and crypto portfolio files unchanged."
        ],
        "portfolioWriteback":s["portfolioWriteback"]}
    out=Path("btci_v818d7_reports");out.mkdir(exist_ok=True)
    data=(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+"\n").encode()
    (out/"portable_MVRV_31_684week_asof_FULL.json").write_bytes(data)
    prefix="research/btci/v8.18d7/runs/{}-{}/".format(os.environ["GITHUB_RUN_ID"],os.getenv("GITHUB_RUN_ATTEMPT","1"))
    def put(name,raw):
        key=prefix+name;d=sha(raw)
        client.put_object(Bucket=bucket,Key=key,Body=raw,
            ContentType="application/json",Metadata={"sha256":d,"research-only":"true"})
        r=client.get_object(Bucket=bucket,Key=key)["Body"].read()
        if sha(r)!=d:raise RuntimeError("R2_SHA256_READBACK_MISMATCH")
        return {"key":key,"sha256":d,"bytes":len(raw)}
    saved=put("portable_MVRV_31_684week_asof_FULL.json",data)
    manifest=put("manifest.json",(json.dumps({"version":"8.18d7","status":report["status"],
        "researchOnly":True,"report":saved,"preregSHA256":sha(specraw),
        "noTradingWriteback":True},ensure_ascii=False,indent=2)+"\n").encode())
    summary={"status":report["status"],"weeks":684,"publicAsOf":len(sourceEvidence),
         "notVerified":684-len(sourceEvidence),"newDates":sorted(new),"negatives":negative,
         "byType":counts,"byEra":report["byEra"],"nonOverlap":spacings,
         "originalProviderAPIClockVerified":0,"reportSHA256":saved["sha256"],
         "manifestSHA256":manifest["sha256"],"prefix":prefix}
    (out/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n")
    print("V818D7_RESULT "+json.dumps(summary,ensure_ascii=False),flush=True)

if __name__=="__main__":
    selftest() if "--self-test" in sys.argv else main()
