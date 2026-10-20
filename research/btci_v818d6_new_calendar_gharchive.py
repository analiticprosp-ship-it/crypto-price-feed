#!/usr/bin/env python3
"""BTCI v8.18d6: independent as-of original CoinMetrics GitHub PushEvent, eight frozen hours, no outcome models."""
import json
import os
import sys
from collections import Counter
from datetime import date,datetime,timedelta,timezone
from pathlib import Path
import boto3

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"research"))
from btci_v818c10_gharchive_push_event import event_hour,original_source,sha,selftest as old_selftest

SPEC=ROOT/"research/btci_v818d6_new_calendar_gharchive_prereg_2026-10-20.json"

def utc(s):
    return datetime.fromisoformat(s.replace("Z","+00:00"))

def spaced(days,weekcount):
    result=[]
    for x in sorted(days):
        if not result or date.fromisoformat(x)>=date.fromisoformat(result[-1])+timedelta(weeks=weekcount):
            result.append(x)
    return result

def selftest():
    old_selftest()
    assert len(spaced(["2020-01-05","2020-04-05","2020-04-12","2020-07-05"],13))==3
    assert len(spaced(["2020-01-05","2020-04-05","2020-04-12","2020-07-05"],26))==2
    assert utc("2020-09-05T13:07:00Z")<datetime(2020,9,6,tzinfo=timezone.utc)
    print("V818D6_SELFTEST_PASS",flush=True)

def main():
    preg=SPEC.read_bytes()
    p=json.loads(preg)
    if p["version"]!="8.18d6" or not p["researchOnly"] or p["tradeAuthorized"]:
        raise ValueError("RESEARCH_ONLY_PREREG_GUARD")
    s3=boto3.client("s3",
        endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto")
    bucket=os.environ["R2_BUCKET"]
    def parent(which):
        entry=p["parents"][which]
        raw=s3.get_object(Bucket=bucket,Key=entry["key"])["Body"].read()
        if sha(raw)!=entry["sha256"]:
            raise RuntimeError("PARENT_SHA256_CHANGED_"+which)
        obj=json.loads(raw)
        if obj.get("researchOnly") is not True or obj.get("tradeAuthorized",False) is True:
            raise ValueError("PARENT_NOT_RESEARCH_ONLY_"+which)
        return obj
    portable=parent("portableD5")
    temporal=parent("temporalD5")
    panel=parent("btcPanel")["weeklyPanel"]
    dates=[r["date"] for r in panel]
    inherited=portable["verifiedDates"]
    if (len(dates)!=684 or dates!=sorted(set(dates))
       or len(inherited)!=26 or inherited!=temporal["allWitnessDates"]
       or any(r["date"]!=d for r,d in zip(portable["weeklyProvenance"],dates))
       or any(date.fromisoformat(d).weekday()!=6 for d in dates)):
        raise ValueError("INVARIANT_684_AND_26_FAILED")
    expectedSpacings={13:17,26:10,52:5}
    for h,n in expectedSpacings.items():
        if (temporal["temporalSpacingOnlyNotModelEvents"][str(h)]["greedyTimeSeparatedWeeks"]!=n
            or len(spaced(inherited,h))!=n):
            raise ValueError("PARENT_TEMPORAL_SPACING_CHANGED")
    cases=p["frozenTestCases"]
    if (len(cases)!=8 or len({c["sunday"] for c in cases})!=8
       or any(c["sunday"] in inherited or c["sunday"] not in dates for c in cases)):
        raise ValueError("NEW_FROZEN_TEST_DATE_CHANGED_OR_OVERLAPS")
    rows=[]
    accepted=[]
    for case in cases:
        archived=event_hour(case,p["sourceLimit"])
        try:
            source=original_source(case,case["sunday"])
        except Exception as e:
            source={"status":"PINNED_HISTORIC_GIT_SOURCE_UNAVAILABLE",
                    "sourceError":type(e).__name__+":"+str(e)[:200]}
        matches=[x for x in archived.get("matchedEvents",[])
                 if x.get("repo")=="coinmetrics/data" and x.get("matchedSha")==case["expectedCommitSha"]]
        passes=archived["status"]=="MATCHED_ORIGINAL_REPO_PUSH_EVENT" and len(matches)>0 and source["status"]=="ORIGINAL_GIT_BLOB_AND_MVRV_TRIAD_PASS"
        if passes:
            if source["sourceCommit"]!=case["expectedCommitSha"]:
                raise ValueError("ORIGINAL_COMMIT_MATCH_CHANGED")
            ev=min(matches,key=lambda x:utc(x["createdAtUTC"]))
            if utc(ev["createdAtUTC"])>=datetime.combine(date.fromisoformat(case["sunday"]),datetime.min.time(),timezone.utc):
                raise ValueError("PUBLIC_EVENT_TIME_NOT_PRE_DECISION")
            age=(date.fromisoformat(case["sunday"])-date.fromisoformat(source["observation"])).days
            if not(2<=age<=7 and age==source["lagDays"] and float(source["mvrv"])>0 and source.get("sourceSha256")):
                raise ValueError("HISTORICAL_MVRV_AGE_OR_SOURCE_GUARD")
            accepted.append({"date":case["sunday"],"observation":source["observation"],
                 "mvrv":source["mvrv"],"publicWitnessUTC":ev["createdAtUTC"],
                 "originalCommitSHA":case["expectedCommitSha"],
                 "sourceSHA256":source["sourceSha256"],"eventId":ev.get("eventId")})
        rows.append({"date":case["sunday"],"frozenHourUTC":case["date"]+"T13:00:00Z",
            "expectedCommitSHA":case["expectedCommitSha"],"sourceResult":source,
            "independentGHArchive":archived,
            "providerOriginalGitHubPublicPushWitness":passes,
            "sourceNotProvenIsNotProofOfAbsence":True,
            "originalProviderMetricAPIFirstPublicationTimeVerified":False})
        print("V818D6_CASE "+json.dumps({"date":case["sunday"],"archived":archived["status"],
            "originalCSV":source["status"],"originalPushWitness":passes,
            "matched":len(matches),"sourceError":archived.get("sourceError")},ensure_ascii=False),flush=True)
    new=[x["date"] for x in accepted]
    union=sorted(set(inherited)|set(new))
    if len(union)!=len(inherited)+len(new):
        raise ValueError("DUPLICATE_ASOF_WEEK")
    sep={str(h):{"horizonWeeks":h,"timeSeparatedWeeks":len(spaced(union,h)),
         "chosenDates":spaced(union,h),"independentEventsNotProved":True}
         for h in (13,26,52)}
    report={"version":"8.18d6","researchOnly":True,"tradeAuthorized":False,
        "status":"NEW_EIGHT_FROZEN_GHARCHIVE_SOURCE_WINDOWS_AUDITED_NO_MODEL_TEST",
        "prereg":{"path":str(SPEC.relative_to(ROOT)),"sha256":sha(preg)},
        "parents":p["parents"],"original684BTCIWeeksUnchanged":True,
        "frozenHours":8,"verifiedOriginalRepoPublicPushCount":len(new),
        "newPublicAsOfMVRVDates":new,"priorIndependentlyWitnMVRVWeeks":26,
        "unionAsOfNumericWeeks":len(union),"unionDates":union,
        "temporalSpacingOnly":sep,"individualFrozenSourceHours":rows,
        "originalProviderCoinMetricsMetricAPIFirstReleaseVerified":0,
        "notes":[
            "A found GHArchive PushEvent matches a specific public original Coin Metrics GitHub repository commit and a historical Friday-or-older MVRV raw Git blob.",
            "Missing archived event from exactly sampled Saturday 13 UTC is nonproof, not an absent-publication claim.",
            "A GitHub PushEvent is independent evidence of GitHub public source availability, NOT a verified original Coin Metrics API data publish clock.",
            "Only preselected eight dates tested. This cannot establish original 684-week source availability nor historical predictive performance.",
            "H=13/26/52 greedy spacing is a calendar separation diagnostic, not independent observations or statistically effective sample size.",
            "BTC price outcomes and labels, model score, macro research baselines and any trading settings were not accessed or changed."
        ],"portfolioWriteback":p["portfolioWriteback"]}
    out=Path("btci_v818d6_reports");out.mkdir(exist_ok=True)
    raw=(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+"\n").encode()
    (out/"gharchive_8_frozen_hours_FULL.json").write_bytes(raw)
    prefix="research/btci/v8.18d6/runs/{}-{}/".format(os.environ["GITHUB_RUN_ID"],os.getenv("GITHUB_RUN_ATTEMPT","1"))
    def put(name,data):
        key=prefix+name;d=sha(data)
        s3.put_object(Bucket=bucket,Key=key,Body=data,ContentType="application/json",
            Metadata={"sha256":d,"research-only":"true"})
        if sha(s3.get_object(Bucket=bucket,Key=key)["Body"].read())!=d:
            raise RuntimeError("R2_REPORT_SHA256_READBACK_FAILED")
        return {"key":key,"sha256":d,"bytes":len(data)}
    saved=put("gharchive_8_frozen_hours_FULL.json",raw)
    manifest=put("manifest.json",(json.dumps({"version":"8.18d6",
        "researchOnly":True,"report":saved,"preregSHA256":sha(preg),"noTradingWriteback":True},
        indent=2,ensure_ascii=False)+"\n").encode())
    summary={"status":report["status"],"frozenHours":8,"newIndependentOriginalPushWeeks":len(new),
        "newDates":new,"totalIndependentlyDatedMVRVWeeks":len(union),
        "temporalSpacing":sep,"originalProviderMetricAPIPublishTimeProven":0,
        "reportSHA256":saved["sha256"],"manifestSHA256":manifest["sha256"],"prefix":prefix}
    (out/"summary.json").write_text(json.dumps(summary,indent=2,ensure_ascii=False)+"\n")
    print("V818D6_RESULT "+json.dumps(summary,ensure_ascii=False),flush=True)

if __name__=="__main__":
    selftest() if "--self-test" in sys.argv else main()
