#!/usr/bin/env python3
"""BTCI v8.18d4: independent original-repo Coin Metrics GH Archive public PushEvent source proof; research only."""
import json
import os
import sys
from datetime import datetime,date,timezone
from pathlib import Path
import boto3
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"research"))
from btci_v818c10_gharchive_push_event import (
    event_hour,original_source,sha,selftest as base_selftest)
SPEC=ROOT/"research/btci_v818d4_gharchive_nine_hours_prereg_2026-10-19.json"

def selftest():
    base_selftest()
    assert datetime.fromisoformat("2023-10-01T00:00:00+00:00")>datetime.fromisoformat("2023-09-30T13:05:00+00:00")
    print("V818D4_SELFTEST_PASS",flush=True)

def main():
    rawreg=SPEC.read_bytes()
    reg=json.loads(rawreg)
    if reg["version"]!="8.18d4" or not reg["researchOnly"] or reg["tradeAuthorized"]:
        raise ValueError("FROZEN_PREREG_RESEARCH_ONLY_GUARD")
    s3=boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
    bucket=os.environ["R2_BUCKET"]
    def parent(name):
        p=reg["parents"][name]
        b=s3.get_object(Bucket=bucket,Key=p["key"])["Body"].read()
        if sha(b)!=p["sha256"]:raise ValueError("PINNED_PARENT_SHA_CHANGED_"+name)
        j=json.loads(b)
        if not j.get("researchOnly") or j.get("tradeAuthorized"):
            raise ValueError("PARENT_NOT_RESEARCH_ONLY_"+name)
        return j
    c11=parent("c11")
    d3=parent("d3")
    btc=parent("btc")
    dates=[r["date"] for r in btc["weeklyPanel"]]
    assert len(dates)==684 and dates==sorted(set(dates)) and len(c11["cumulativeOriginalGitHubPushWitnessDates"])==5
    assert len(d3["witnessDates"])==17
    cases=reg["frozenTestCases"]
    if len(cases)!=9 or len({c["sunday"] for c in cases})!=9 or any(c["sunday"] not in dates for c in cases):
        raise ValueError("NINE_PRESELECTED_CASES_NOT_IN_FROZEN_684")
    old=set(d3["witnessDates"])
    sourceproof=[]
    archived=[]
    for c in cases:
        gh=event_hour(c,reg["limits"])
        try:
            original=original_source(c,c["sunday"])
        except Exception as e:
            original={"status":"ORIGINAL_ARCHIVED_GIT_SOURCE_UNAVAILABLE",
                      "error":type(e).__name__+":"+str(e)[:220]}
        matched=gh["status"]=="MATCHED_ORIGINAL_REPO_PUSH_EVENT" and original["status"]=="ORIGINAL_GIT_BLOB_AND_MVRV_TRIAD_PASS"
        public=[]
        if matched:
            public=[x for x in gh["matchedEvents"]
                    if x.get("repo")=="coinmetrics/data" and x.get("matchedSha")==c["expectedCommitSha"]]
            if not public:raise ValueError("MATCHED_ARCHIVE_EVENT_MISSING_ORIGINAL_REPO_SHA")
            for x in public:
                if datetime.fromisoformat(x["createdAtUTC"])>=datetime.combine(date.fromisoformat(c["sunday"]),datetime.min.time(),timezone.utc):
                    raise ValueError("PUBLIC_EVENT_AFTER_WEEKLY_DECISION")
            if original["sourceCommit"]!=c["expectedCommitSha"] or not 2<=int(original["lagDays"])<=7:
                raise ValueError("ORIGINAL_SOURCE_MVRV_SHA_LAG_INVALID")
            sourceproof.append(c["sunday"])
        rec={"sunday":c["sunday"],"frozenHour":c["date"]+"T13:00:00Z",
             "expectedSHA":c["expectedCommitSha"],"externalGHArchive":gh,
             "originalCoinMetricsArchivedGitSource":original,
             "originalPublicGitHubPushAsOfWitness":matched,
             "originalProviderDailyApiFirstReleaseClockKnown":False,
             "alreadyInV818d3":c["sunday"] in old}
        archived.append(rec)
        print("V818D4_CASE "+json.dumps({
            "date":c["sunday"],"archiveStatus":gh["status"],"events":gh["totalEvents"],
            "originalStatus":original["status"],"matched":len(gh["matchedEvents"]),
            "independentOriginalRepoPushProof":matched,
            "error":gh["sourceError"]},ensure_ascii=False),flush=True)
    new=sorted(set(sourceproof)-old)
    union=sorted(old|set(sourceproof))
    report={
       "version":"8.18d4",
       "status":"NINE_FROZEN_HOURS_ORIGINAL_PROVIDER_GITHUB_PUSH_AUDIT_COMPLETE",
       "researchOnly":True,"tradeAuthorized":False,
       "preregSHA256":sha(rawreg),"pinnedParents":reg["parents"],
       "original684BTCISundayDatesUnchanged":True,
       "priorIndependentlyDatedNumericMVRVWeeks":17,
       "frozenGhArchiveSourceHours":9,
       "additionalOriginalRepoPublicGitHubPushWitnesses":sourceproof,
       "newUniqueIndependentlyDatedNumericWeeks":new,
       "totalUniqueWeeksAfterUnion":len(union),
       "newUnionDates":union,
       "originalProviderDailyAPIReleaseClockVerified":0,
       "cases":archived,
       "constraints":[
           "GH Archive independent hourly original-repo PushEvents with matching exact Git SHA and internally consistent MVRV provide public GitHub source timing, not an original provider API metric release guarantee.",
           "Nine frozen Saturday 13 UTC hours only. Missing event in that hour does not prove none elsewhere.",
           "No profit models, no MACRO or BTC future outcome retraining, no trade authority.",
           "All 684 frozen BTCI Sundays preserved, no source interpolation or retrospective first-seen assumption."
       ],
       "portfolioWriteback":reg["portfolioWriteback"]}
    out=Path("btci_v818d4_reports");out.mkdir(exist_ok=True)
    payload=(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+"\n").encode()
    (out/"original_repo_push_nine_hours_FULL.json").write_bytes(payload)
    prefix="research/btci/v8.18d4/runs/{}-{}/".format(os.environ["GITHUB_RUN_ID"],os.getenv("GITHUB_RUN_ATTEMPT","1"))
    def put(name,data):
        key=prefix+name;checksum=sha(data)
        s3.put_object(Bucket=bucket,Key=key,Body=data,ContentType="application/json",
            Metadata={"sha256":checksum,"research-only":"true"})
        if sha(s3.get_object(Bucket=bucket,Key=key)["Body"].read())!=checksum:
            raise RuntimeError("R2_PUT_GET_SHA_MISMATCH")
        return {"key":key,"sha256":checksum,"bytes":len(data)}
    saved=put("original_repo_push_nine_hours_FULL.json",payload)
    mani=put("manifest.json",(json.dumps({
        "version":"8.18d4","researchOnly":True,"report":saved,
        "status":report["status"],"preregSHA256":sha(rawreg),
        "noPortfolioChanges":True},ensure_ascii=False,indent=2)+"\n").encode())
    summary={"status":report["status"],"frozenHours":9,"originalPublicPushProven":len(sourceproof),
        "newUniqueAsOfDates":new,"totalUnionWeeks":len(union),
        "allWitnessDates":union,
        "cases":[{"date":c["sunday"],"matched":c["originalPublicGitHubPushAsOfWitness"],
                  "status":c["externalGHArchive"]["status"]} for c in archived],
        "originalProviderAPIReleaseClockVerified":0,
        "reportSha256":saved["sha256"],"manifestSha256":mani["sha256"],"prefix":prefix}
    (out/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n")
    print("V818D4_RESULT "+json.dumps(summary,ensure_ascii=False),flush=True)
if __name__=="__main__":
    if "--self-test" in sys.argv:selftest()
    else:main()
