#!/usr/bin/env python3
"""BTCI v8.18d5: portable 684-week independent MVRV asof witness ledger; research only."""
import hashlib
import json
import math
import os
import sys
from collections import Counter,defaultdict
from datetime import date,datetime,timezone
from pathlib import Path
import boto3

ROOT=Path(__file__).resolve().parents[1]
SPEC=ROOT/"research/btci_v818d5_consolidated_684week_MVRV_asof_register_prereg_2026-10-19.json"

def sha(b): return hashlib.sha256(b).hexdigest()

def to_utc(t):return datetime.fromisoformat(t.replace("Z","+00:00"))

def verify_source(item):
    day=item["date"]
    d=date.fromisoformat(day)
    if d.weekday()!=6:raise ValueError("NOT_SUNDAY")
    cutoff=datetime.combine(d,datetime.min.time(),timezone.utc)
    pub=to_utc(item["availableUTC"])
    lag=(d-date.fromisoformat(item["observed"])).days
    if not(pub<cutoff and 2<=lag<=7 and math.isfinite(float(item["mvrv"])) and float(item["mvrv"])>0):
        raise ValueError("INVALID_PIT_TIMESTAMP_OR_MVRV_"+day)
    return item

def selftest():
    x={"date":"2024-05-26","availableUTC":"2024-05-25T01:53:26Z","observed":"2024-05-23","mvrv":2.2}
    assert verify_source(x)==x
    try:verify_source({**x,"availableUTC":"2024-05-26T02:00:00Z"})
    except ValueError:pass
    else:raise AssertionError("FUTURE_TIME_NOT_REJECTED")
    print("V818D5_SELFTEST_PASS",flush=True)

def main():
    rawspec=SPEC.read_bytes();spec=json.loads(rawspec)
    if spec["version"]!="8.18d5" or not spec["researchOnly"] or spec["tradeAuthorized"]:
        raise ValueError("PREREG_GUARD")
    client=boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
    bucket=os.environ["R2_BUCKET"]
    def parent(k):
        p=spec["parents"][k]
        raw=client.get_object(Bucket=bucket,Key=p["key"])["Body"].read()
        if sha(raw)!=p["sha256"]:raise ValueError("PARENT_SHA256_MISMATCH_"+k)
        j=json.loads(raw)
        if j.get("tradeAuthorized") or not j.get("researchOnly"):raise ValueError("INVALID_RESEARCH_PARENT")
        return j
    original=parent("full684")["weeklyPanel"]
    earlier=parent("cumulativeD3")
    latest=parent("newD4")
    prior=earlier["perSundayEvidence"]
    dates=[x["date"] for x in original]
    if len(dates)!=684 or dates!=sorted(set(dates)) or dates!=[x["date"] for x in prior]:
        raise ValueError("FROZEN_684_COHORT_DIFFERS")
    if len(earlier["witnessDates"])!=17 or latest["totalUniqueWeeksAfterUnion"]!=26:
        raise ValueError("PARENT_WITNESS_COUNT_CHANGED")
    bydate=defaultdict(list)
    for r in prior:
        for evidence in r["independentSources"]:
            v=verify_source(evidence)
            if v["date"]!=r["date"]:raise ValueError("PRIOR_DATE_ASSOCIATION_BROKEN")
            bydate[v["date"]].append(v)
    if len(bydate)!=17:raise ValueError("PRIOR_17_SOURCE_LOST")
    fresh=[]
    for r in latest["cases"]:
        if not r["originalPublicGitHubPushAsOfWitness"]:continue
        pub=r["externalGHArchive"]
        original_git=r["originalCoinMetricsArchivedGitSource"]
        if pub["status"]!="MATCHED_ORIGINAL_REPO_PUSH_EVENT" or original_git["status"]!="ORIGINAL_GIT_BLOB_AND_MVRV_TRIAD_PASS":
            raise ValueError("INVALID_ORIGINAL_PROVIDER_SOURCE")
        candidates=[e for e in pub["matchedEvents"] if
            e.get("repo")=="coinmetrics/data" and e.get("matchedSha")==r["expectedSHA"]]
        if not candidates or original_git["sourceCommit"]!=r["expectedSHA"]:
            raise ValueError("GITHUB_ORIGINAL_PROVIDER_EVENT_SHA_MISMATCH")
        ev=min(candidates,key=lambda e:e["createdAtUTC"])
        item=verify_source({"date":r["sunday"],
            "type":"GHArchive_original_github_PushEvent",
            "source":"coinmetrics/data",
            "availableUTC":ev["createdAtUTC"],
            "observed":original_git["observation"],"mvrv":original_git["mvrv"],
            "sourceHash":original_git["sourceSha256"],
            "commitSHA":r["expectedSHA"],
            "GHArchiveEventId":ev.get("eventId"),
            "sourceVerifiedInParent":"v8.18d4"})
        if item["date"] in bydate:raise ValueError("ADDITIONAL_DATE_OVERLAPS_PARENT")
        bydate[item["date"]].append(item)
        fresh.append(item["date"])
    expected=spec["expected"]
    if (len(fresh)!=expected["newAsOfNumericWitnessWeeks"] or len(bydate)!=expected["totalDistinctAsOfNumericWitnessWeeks"]
        or sorted(bydate)!=latest["newUnionDates"]):
        raise ValueError("FROZEN_26_DATES_INCONSISTENT")
    counttypes=Counter()
    perera=defaultdict(lambda:{"weeks":0,"asofNumericWitnesses":0})
    conflicts=[]
    rows=[]
    for p in original:
        day=p["date"];era=p["era"]
        witness=bydate[day] if day in bydate else []
        if witness and len(witness)>1:
            vals=[float(x["mvrv"]) for x in witness]
            if max(vals)-min(vals)>0.000005:
                conflicts.append({"date":day,"MVRVs":vals})
        for w in witness:counttypes[w["type"]]+=1
        perera[era]["weeks"]+=1
        perera[era]["asofNumericWitnesses"]+=int(bool(witness))
        rows.append({"date":day,"era":era,"hasIndependentlyDatedNumericMvrv":bool(witness),
            "asofEvidence":witness,
            "originalCoinMetricsAPIFirstReleaseClockVerified":False,
            "historyRecomputed":False,
            "classification":"PUBLIC_ASOF_NUMERIC_EVIDENCE_ONLY" if witness else "UNVERIFIED_HISTORICAL_PUBLIC_ASOF"})
    result={
        "version":"8.18d5","status":"CONSOLIDATED_684_WEEK_26_DATED_MVRV_WITNESSES_NO_MODEL_EDGE",
        "researchOnly":True,"tradeAuthorized":False,
        "prereg":{"path":str(SPEC.relative_to(ROOT)),"sha256":sha(rawspec)},
        "parents":spec["parents"],"unchangedOriginalBTCI684WeekPanel":True,
        "original684Weeks":684,"independentlyDatedMvrvWeeks":len(bydate),
        "unverifiedWeeks":684-len(bydate),"verifiedDates":sorted(bydate),
        "evidenceTypeCounts":dict(sorted(counttypes.items())),
        "perEra":dict(sorted(perera.items())),"numericConflicts":conflicts,
        "providerOriginalCoinMetricsDailyAPIFirstReleaseVerified":0,
        "weeklyProvenance":rows,
        "limitations":[
            "This 26-date union consists of independent public GitHub snapshot witnesses, independently archived original GitHub provider PushEvents, and a Wayback captured numeric CSV, not daily original provider API first-published timestamps.",
            "26 opportunistic sparse witnesses are not a statistically representative 684-week forecasting panel.",
            "658 additional weeks remain UNKNOWN by these source rules, not necessarily historically unpublished.",
            "No backtesting, BTC outcome evaluation, threshold fitting, model-training or performance claim.",
            "No canonical portfolio, Detector, Futures, NAV, P&L, MASTER, risk, capital or order writeback."],
        "portfolioWriteback":spec["portfolioWriteback"]}
    out=Path("btci_v818d5_reports");out.mkdir(exist_ok=True)
    body=(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+"\n").encode()
    (out/"portable_MVRV_684week_asof_evidence_FULL.json").write_bytes(body)
    prefix="research/btci/v8.18d5/runs/{}-{}/".format(os.environ["GITHUB_RUN_ID"],os.getenv("GITHUB_RUN_ATTEMPT","1"))
    def put(name,data):
        k=prefix+name;d=sha(data)
        client.put_object(Bucket=bucket,Key=k,Body=data,ContentType="application/json",
            Metadata={"sha256":d,"research-only":"true"})
        if sha(client.get_object(Bucket=bucket,Key=k)["Body"].read())!=d:
            raise RuntimeError("R2_PUT_GET_SHA_READBACK_MISMATCH")
        return {"key":k,"sha256":d,"bytes":len(data)}
    report=put("portable_MVRV_684week_asof_evidence_FULL.json",body)
    manifest=put("manifest.json",(json.dumps({"version":"8.18d5","status":result["status"],
        "researchOnly":True,"report":report,"preregSha256":sha(rawspec),"noTradingMutation":True},
        ensure_ascii=False,indent=2)+"\n").encode())
    summary={"status":result["status"],"weeks":684,"asofWeeks":len(bydate),
        "unverifiedWeeks":684-len(bydate),"byType":result["evidenceTypeCounts"],
        "byEra":result["perEra"],"conflicts":len(conflicts),
        "originalProviderApiReleaseClockVerified":0,
        "reportSha256":report["sha256"],"manifestSha256":manifest["sha256"],"prefix":prefix}
    (out/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n")
    print("V818D5_RESULT "+json.dumps(summary,ensure_ascii=False),flush=True)
if __name__=="__main__":
    if "--self-test" in sys.argv:selftest()
    else:main()
