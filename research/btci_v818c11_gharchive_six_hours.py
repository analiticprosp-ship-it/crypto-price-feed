#!/usr/bin/env python3
"""BTCI v8.18c11: six additional frozen original GitHub PushEvent historical proofs; nontrading."""
import json
import os
import sys
from pathlib import Path
import boto3
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"research"))
from btci_v818c10_gharchive_push_event import (event_hour,original_source,sha,selftest as parent_selftest)
SPEC=ROOT/"research/btci_v818c11_gharchive_six_hours_prereg_2026-10-19.json"

def selftest():
    parent_selftest()
    print("V818C11_SELFTEST_PASS",flush=True)

def main():
    preraw=SPEC.read_bytes()
    reg=json.loads(preraw)
    if reg["version"]!="8.18c11" or not reg["researchOnly"] or reg["tradeAuthorized"]:
        raise ValueError("PREREG_FAIL")
    s3=boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
        region_name="auto",aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"])
    bucket=os.environ["R2_BUCKET"]
    def pinned(entry):
        data=s3.get_object(Bucket=bucket,Key=entry["key"])["Body"].read()
        if sha(data)!=entry["sha256"]:
            raise ValueError("PARENT_SHA256_MISMATCH")
        return json.loads(data)
    p10=pinned(reg["parents"]["pilotC10"])
    panel=pinned(reg["parents"]["btcPanel"])["weeklyPanel"]
    if p10["version"]!="8.18c10" or len(panel)!=684:
        raise ValueError("PARENT_VERSION_OR_684_PANEL_CHANGED")
    dates={r["date"] for r in panel}
    if any(c["sunday"] not in dates for c in reg["frozenTestCases"]):
        raise ValueError("CASE_NOT_IN_IMMUTABLE_PANEL")
    if len(reg["frozenTestCases"])!=6:
        raise ValueError("FROZEN_SIX_CASES_CHANGED")
    records=[]
    for case in reg["frozenTestCases"]:
        external=event_hour(case,reg["sourceBoundaries"])
        try:
            archive=original_source(case,case["sunday"])
        except Exception as exc:
            archive={"status":"ORIGINAL_GIT_SOURCE_UNAVAILABLE","sourceError":str(exc)[:350]}
        accepted=external["status"]=="MATCHED_ORIGINAL_REPO_PUSH_EVENT" and archive["status"]=="ORIGINAL_GIT_BLOB_AND_MVRV_TRIAD_PASS"
        rec={"date":case["sunday"],"fixedHour":case["date"]+"T13:00:00Z",
             "expectedCommitSHA":case["expectedCommitSha"],
             "originalGitArchive":archive,"independentThirdPartyEventArchive":external,
             "originalPublicGithubPushBeforeDecision":accepted,
             "providerApiFirstReleaseClockProven":False}
        records.append(rec)
        print("V818C11_CASE "+json.dumps({"date":rec["date"],
            "status":external["status"],"events":external["totalEvents"],
            "matched":len(external["matchedEvents"]),"sourceStatus":archive["status"],
            "pushProof":accepted,"error":external["sourceError"]},ensure_ascii=False),flush=True)
    newdates=[r["date"] for r in records if r["originalPublicGithubPushBeforeDecision"]]
    previousdates=p10["originalRepoPublicPushWitnessDates"]
    union=sorted(set(newdates)|set(previousdates))
    if len(union)!=len(newdates)+len(previousdates):
        raise ValueError("FROZEN_WINDOWS_OVERLAP")
    report={
        "version":"8.18c11","status":"SIX_HOUR_INDEPENDENT_GITHUB_PUBLICATION_WITNESS_AUDIT_COMPLETED",
        "researchOnly":True,"tradeAuthorized":False,
        "preregSHA256":sha(preraw),"parents":reg["parents"],
        "original684SundayPanelUnchanged":True,
        "historicalOriginalGitHubPushWitnessesPriorC10":previousdates,
        "additionalIndependentOriginalGitHubPushWitnessDates":newdates,
        "cumulativeOriginalGitHubPushWitnessDates":union,
        "originalCoinMetricsAPIReleaseTimeVerified":0,
        "sixFrozenSourceHours":records,
        "limitations":[
            "Independent GH Archive PushEvent confirms original GitHub repository public push at archived timestamp only; it does not prove official Coin Metrics API daily release timing.",
            "Archived hourly event is not expected to include every event; absence is NOT evidence of non-publication.",
            "Source must have matching frozen exact original Git commit and valid historical MVRV arithmetic; no future observation dates.",
            "This is a source-origin publication pilot, not a 684-week PIT backtest and no predictive BTC results.",
            "Original BTCI 684 weekly panel, macro factors, existing 11 fork as-of witnesses and all trading files remain unchanged."
        ],
        "portfolioWriteback":reg["portfolioWriteback"]
    }
    d=Path("btci_v818c11_reports");d.mkdir(exist_ok=True)
    raw=(json.dumps(report,ensure_ascii=False,indent=2)+"\n").encode()
    (d/"original_public_push_6hours_FULL.json").write_bytes(raw)
    prefix="research/btci/v8.18c11/runs/{}-{}/".format(os.environ["GITHUB_RUN_ID"],os.getenv("GITHUB_RUN_ATTEMPT","1"))
    def write(name,payload):
        key=prefix+name;hash=sha(payload)
        s3.put_object(Bucket=bucket,Key=key,Body=payload,ContentType="application/json",
            Metadata={"sha256":hash,"research-only":"true"})
        got=s3.get_object(Bucket=bucket,Key=key)["Body"].read()
        if sha(got)!=hash:raise RuntimeError("R2_SHA256_GET_RECHECK_MISMATCH")
        return {"key":key,"sha256":hash,"bytes":len(payload)}
    saved=write("original_public_push_6hours_FULL.json",raw)
    mani=write("manifest.json",(json.dumps({"version":"8.18c11",
        "researchOnly":True,"status":report["status"],"report":saved,
        "preregSha256":sha(preraw),"sourceHours":6},ensure_ascii=False,indent=2)+"\n").encode())
    summary={"status":report["status"],"sixHours":6,"priorOriginalPublicPushCount":len(previousdates),
        "newIndependentOriginalPublicPushCount":len(newdates),"newDates":newdates,
        "cumulativeIndependentOriginalPushCount":len(union),"cumulativeDates":union,
        "originalProviderApiReleaseClockVerified":0,
        "cases":[{"date":r["date"],"status":r["independentThirdPartyEventArchive"]["status"],
                  "compressedBytes":r["independentThirdPartyEventArchive"]["compressedBytes"],
                  "sourceStatus":r["originalGitArchive"]["status"]} for r in records],
        "reportSha256":saved["sha256"],"manifestSha256":mani["sha256"],"prefix":prefix}
    (d/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n")
    print("V818C11_RESULT "+json.dumps(summary,ensure_ascii=False),flush=True)
if __name__=="__main__":
    selftest() if "--self-test" in sys.argv else main()
