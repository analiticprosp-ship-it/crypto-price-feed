#!/usr/bin/env python3
"""BTCI v8.18d5 — frozen 684-week research-only provenance, temporal spacing, no price outcomes."""
import hashlib
import json
import os
import sys
from collections import Counter,defaultdict
from datetime import date,datetime,timedelta,timezone
from pathlib import Path
import boto3

ROOT=Path(__file__).resolve().parents[1]
PREREG=ROOT/"research/btci_v818d5_26week_provenance_and_independence_prereg_2026-10-19.json"

def sha(b):
    return hashlib.sha256(b).hexdigest()

def utc(s):
    d=datetime.fromisoformat(s.replace("Z","+00:00"))
    if d.utcoffset()!=timedelta(0):
        raise ValueError("TIMESTAMP_NOT_UTC")
    return d

def cutoff(day):
    d=date.fromisoformat(day)
    if d.weekday()!=6:raise ValueError("NOT_SUNDAY")
    return datetime.combine(d,datetime.min.time(),timezone.utc)

def validate(obs,sunday,firstseen,mvrv):
    lag=(date.fromisoformat(sunday)-date.fromisoformat(obs)).days
    if not (2<=lag<=7 and utc(firstseen)<cutoff(sunday) and float(mvrv)>0):
        raise ValueError("FAIL_HISTORICAL_AVAILABILITY_OR_AGE_GUARD_"+sunday)
    return lag

def spaced_dates(days,h):
    chosen=[]
    for ds in sorted(days):
        d=date.fromisoformat(ds)
        if not chosen or d>=date.fromisoformat(chosen[-1])+timedelta(days=h*7):
            chosen.append(ds)
    return chosen

def research_parent_allowed(parent):
    # Historical BTCI parent does not require an explicit tradeAuthorized key.
    # An explicit True always blocks; missing is interpreted as no authority.
    return parent.get("researchOnly") is True and parent.get("tradeAuthorized",False) is not True

def selftest():
    assert research_parent_allowed({"researchOnly":True})
    assert research_parent_allowed({"researchOnly":True,"tradeAuthorized":False})
    assert not research_parent_allowed({"researchOnly":True,"tradeAuthorized":True})
    assert not research_parent_allowed({"researchOnly":False})
    assert sha(b"test")==hashlib.sha256(b"test").hexdigest()
    assert validate("2024-05-23","2024-05-26","2024-05-25T01:53:26+00:00",2.303)>0
    dates=["2020-01-05","2020-04-05","2020-04-12","2020-07-05"]
    assert spaced_dates(dates,13)==["2020-01-05","2020-04-05","2020-07-05"]
    assert spaced_dates(dates,26)==["2020-01-05","2020-07-05"]
    try:
        validate("2024-05-25","2024-05-26","2024-05-25T01:53:26Z",2.303)
        raise AssertionError("SATURDAY_OBSERVATION_SHOULD_FAIL")
    except ValueError:pass
    print("V818D5_SELFTEST_PASS",flush=True)

def main():
    preg=PREREG.read_bytes()
    reg=json.loads(preg)
    if reg["version"]!="8.18d5" or reg["authority"]!="RESEARCH_ONLY" or reg["tradeAuthorized"]:
        raise ValueError("PREREG_RESEARCH_GUARD")
    s3=boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
         region_name="auto",aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
         aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"])
    bucket=os.environ["R2_BUCKET"]
    def pinned(x):
        p=reg["parents"][x]
        raw=s3.get_object(Bucket=bucket,Key=p["key"])["Body"].read()
        if sha(raw)!=p["sha256"]:raise RuntimeError("SOURCE_REPORT_SHA256_DIFFERS_"+x)
        j=json.loads(raw)
        if not research_parent_allowed(j):
            raise RuntimeError("UPSTREAM_NOT_RESEARCH_ONLY_"+x)
        return j
    btc=pinned("btc")
    d3=pinned("d3")
    d4=pinned("d4")
    weeks=btc["weeklyPanel"]
    dates=[x["date"] for x in weeks]
    if (len(dates)!=684 or len(set(dates))!=684 or dates!=sorted(dates)
        or dates!=[x["date"] for x in d3["perSundayEvidence"]]):
        raise RuntimeError("IMMUTABLE_684_PANEL_OR_D3_DATES_MODIFIED")
    for d in dates:cutoff(d)
    witnesses=defaultdict(list)
    for row in d3["perSundayEvidence"]:
        if not row["hasIndependentPublicNumericMVRVWitness"]:
            continue
        day=row["date"]
        for e in row["independentSources"]:
            firstseen=e["availableUTC"]
            obs=e["observed"]
            val=e["mvrv"]
            validate(obs,day,firstseen,val)
            witnesses[day].append({
                "type":e["type"],"source":e["source"],
                "observedUTCDate":obs,"mvrv":val,
                "independentPublicAsOfUTC":firstseen,
                "contentOrCommitSHA":e.get("sourceHash"),
                "parentEvidence":"v8.18d3"
            })
    if len(witnesses)!=reg["frozenExpected"]["old"]:
        raise RuntimeError("D3_PUBLIC_SOURCE_COUNT_CHANGED")
    new=[]
    for event in d4["cases"]:
        if not event["originalPublicGitHubPushAsOfWitness"]:
            continue
        sunday=event["sunday"]
        src=event["originalCoinMetricsArchivedGitSource"]
        gh=event["externalGHArchive"]
        if src["status"]!="ORIGINAL_GIT_BLOB_AND_MVRV_TRIAD_PASS" or gh["status"]!="MATCHED_ORIGINAL_REPO_PUSH_EVENT":
            raise RuntimeError("PUBLIC_GHARCHIVE_OR_SOURCE_NOT_VALID")
        if src["sourceCommit"]!=event["expectedSHA"]:
            raise RuntimeError("GHARCHIVE_GIT_SOURCE_COMMIT_MISMATCH")
        hits=[h for h in gh["matchedEvents"]
             if h["repo"]=="coinmetrics/data" and h["matchedSha"]==event["expectedSHA"]]
        if not hits:raise RuntimeError("PUBLIC_GHARCHIVE_SOURCE_SHA_NOT_REPRODUCIBLE")
        hit=min(hits,key=lambda z:utc(z["createdAtUTC"]))
        lag=validate(src["observation"],sunday,hit["createdAtUTC"],src["mvrv"])
        if lag!=src["lagDays"] or not src["sourceSha256"]:
            raise RuntimeError("PUBLIC_MVRV_NUMERIC_SOURCE_INCOMPLETE")
        witnesses[sunday].append({
            "type":"GHArchive_original_github_PushEvent",
            "source":"coinmetrics/data",
            "observedUTCDate":src["observation"],"mvrv":src["mvrv"],
            "independentPublicAsOfUTC":hit["createdAtUTC"],
            "contentOrCommitSHA":src["sourceSha256"],
            "originalCommitSHA":event["expectedSHA"],
            "eventID":hit["eventId"],
            "parentEvidence":"v8.18d4"
        })
        new.append(sunday)
    if len(new)!=9 or len(set(new))!=9:
        raise RuntimeError("NINE_PUBLIC_PUSH_WITNESSES_CHANGED")
    if set(witnesses)-set(dates):
        raise RuntimeError("DATE_ADDED_TO_IMMUTABLE_PANEL")
    if len(witnesses)!=reg["frozenExpected"]["union"]:
        raise RuntimeError("PUBLISHED_WITNESS_UNION_NOT_26")
    if len(d4["newUniqueIndependentlyDatedNumericWeeks"])!=9 or sorted(new)!=d4["newUniqueIndependentlyDatedNumericWeeks"]:
        raise RuntimeError("NEW_WITNESS_DATES_CHANGED")
    numeric_conflicts=[]
    for day,w in witnesses.items():
        if len(w)>1:
            values=[float(x["mvrv"]) for x in w]
            if max(values)-min(values)>0.000005:
                numeric_conflicts.append({"date":day,"differentMVRVValues":values})
    byera=defaultdict(lambda:{"weeks":0,"asOfMVRVWitnessWeeks":0})
    records=[]
    for row in weeks:
        day=row["date"]
        group=witnesses.get(day,[])
        era=row["era"]
        byera[era]["weeks"]+=1
        byera[era]["asOfMVRVWitnessWeeks"]+=int(bool(group))
        records.append({
            "date":day,"era":era,"independentlyWitnAsOfMVRV":bool(group),
            "numericWitnesses":group,"originalCoinMetricsAPIReleaseClockVerified":False,
            "outcomesExamined":False,"modelRetested":False
        })
    spacings={}
    for h in reg["frozenExpected"]["horizonsInWeeks"]:
        chosen=spaced_dates(witnesses.keys(),h)
        spacings[str(h)]={"horizonWeeks":h,"greedyTimeSeparatedWeeks":len(chosen),
            "chosenDates":chosen,"definition":"Next observation at least H*7 days after last; chronological spacing only, not independent market events"}
    types=dict(sorted(Counter(e["type"] for group in witnesses.values() for e in group).items()))
    result="PUBLIC_NUMERIC_PROVENANCE_26_COMBINED_NO_PREDICTIVE_TEST"
    report={
        "version":"8.18d5","status":result,"researchOnly":True,"tradeAuthorized":False,
        "prereg":{"path":str(PREREG.relative_to(ROOT)),"sha256":sha(preg)},
        "parents":reg["parents"],"original684WeeksUnchanged":True,
        "asOfNumericWitnessWeeks":len(witnesses),"asOfSourcesByType":types,
        "newOriginalRepoPushEventDates":sorted(new),
        "allWitnessDates":sorted(witnesses),
        "noOriginalMetricProviderAPIClockProof":True,
        "temporalSpacingOnlyNotModelEvents":spacings,
        "byEra":dict(sorted(byera.items())),"numericConflicts":numeric_conflicts,
        "complete684SourceLedger":records,
        "limits":[
            "Public GitHub source availability of an authentic dated MVRV value, not original Coin Metrics per-metric API publication time.",
            "Time-separated H-week anchor dates do not imply statistically independent price outcomes or independent cycles.",
            "No predictive model, BTC price labels, response variable, threshold estimation or trading analysis computed.",
            "No claim that other 658 weeks lacked true MVRV; provenance just not independently shown here.",
            "No live model, NAV, Spot/Futures, P&L, trading risk, reserves or orders changed."
        ],
        "portfolioWriteback":reg["portfolioWriteback"]
    }
    folder=Path("btci_v818d5_reports");folder.mkdir(exist_ok=True)
    payload=(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+"\n").encode()
    (folder/"mvrv_26witness_684_ledger_FULL.json").write_bytes(payload)
    prefix="research/btci/v8.18d5/runs/{}-{}/".format(os.environ["GITHUB_RUN_ID"],os.getenv("GITHUB_RUN_ATTEMPT","1"))
    def store(name,raw):
        key=prefix+name
        checksum=sha(raw)
        s3.put_object(Bucket=bucket,Key=key,Body=raw,ContentType="application/json",
                      Metadata={"sha256":checksum,"research-only":"true"})
        retrieved=s3.get_object(Bucket=bucket,Key=key)["Body"].read()
        if sha(retrieved)!=checksum:
            raise RuntimeError("R2_READBACK_SHA256_MISMATCH")
        return {"key":key,"sha256":checksum,"bytes":len(raw)}
    saved=store("mvrv_26witness_684_ledger_FULL.json",payload)
    manifest=store("manifest.json",(json.dumps({"version":"8.18d5","status":result,"researchOnly":True,
        "preregSha256":sha(preg),"report":saved,"noLiveTradingWriteback":True},ensure_ascii=False,indent=2)+"\n").encode())
    summary={"status":result,"originalBTCIWeeks":684,
        "independentlyDatedMVRVWeeks":len(witnesses),"newWeeks":sorted(new),
        "allWeeks":sorted(witnesses),"witnessTypes":types,
        "timeSpacing":spacings,"perEra":report["byEra"],
        "numericConflicts":numeric_conflicts,
        "originalProviderFirstPublicationUTCVerified":0,
        "reportSHA256":saved["sha256"],"manifestSHA256":manifest["sha256"],
        "prefix":prefix}
    (folder/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n")
    print("V818D5_RESULT "+json.dumps(summary,ensure_ascii=False),flush=True)

if __name__=="__main__":
    if "--self-test" in sys.argv:selftest()
    else:main()
