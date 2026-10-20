#!/usr/bin/env python3
"""BTCI v8.18d6 — 8 frozen adjacent GH Archive hours, post-hoc 2020/2021 source diagnostic only."""
import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from collections import Counter
import boto3

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"research"))
from btci_v818c10_gharchive_push_event import event_hour,original_source,sha,selftest as upstream_selftest

SPEC=ROOT/"research/btci_v818d6_early_2020_21_gharchive_adjacency_prereg_2026-10-20.json"

def selftest():
    upstream_selftest()
    assert datetime.fromisoformat("2020-04-04T14:22:00+00:00") < datetime.fromisoformat("2020-04-05T00:00:00+00:00")
    print("V818D6_SELFTEST_PASS",flush=True)

def main():
    specraw=SPEC.read_bytes()
    cfg=json.loads(specraw)
    if cfg["version"]!="8.18d6" or cfg["mode"]!="RESEARCH_ONLY" or cfg["tradeAuthorized"]:
        raise RuntimeError("RESEARCH_AUTHORITY_GUARD")
    if len(cfg["frozenCases"])!=4 or cfg["frozenAdjacentHoursUTC"]!=[12,14]:
        raise RuntimeError("FROZEN_CASES_OR_HOURS_MODIFIED")
    s3=boto3.client("s3",
        endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
        region_name="auto",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"])
    bucket=os.environ["R2_BUCKET"]
    def pinned(n):
        source=cfg["parents"][n]
        raw=s3.get_object(Bucket=bucket,Key=source["key"])["Body"].read()
        if sha(raw)!=source["sha256"]:
            raise ValueError("PARENT_SHA_MISMATCH_"+n)
        parsed=json.loads(raw)
        if not parsed.get("researchOnly") or parsed.get("tradeAuthorized",False):
            raise ValueError("UPSTREAM_NOT_RESEARCH_ONLY_"+n)
        return parsed
    older10=pinned("c10")
    older11=pinned("c11")
    carried=pinned("d5")
    original=pinned("btc")
    dates=[r["date"] for r in original["weeklyPanel"]]
    if len(dates)!=684 or dates!=sorted(set(dates)):
        raise ValueError("BTC684_CHANGED")
    if carried["asOfNumericWitnessWeeks"]!=26 or len(carried["allWitnessDates"])!=26:
        raise ValueError("PRIOR_26_NUMERIC_WEEKS_CHANGED")
    previous10={x["sunday"]:x for x in older10["cases"]}
    previous11={x["date"]:x for x in older11["sixFrozenSourceHours"]}
    reportRows=[]
    for c in cfg["frozenCases"]:
        day=c["sunday"]
        if day not in dates:raise ValueError("SOURCE_CASE_NOT_IMMUTABLE_SUNDAY_"+day)
        if day in previous10:
            prev=previous10[day]
            gh=prev["archive"]
            parentCommit=prev["expectedGitCommit"]
            parentSource=prev["originalGitSource"]
        elif day in previous11:
            prev=previous11[day]
            gh=prev["independentThirdPartyEventArchive"]
            parentCommit=prev["expectedCommitSHA"]
            parentSource=prev["originalGitArchive"]
        else:
            raise ValueError("SOURCE_CASE_NOT_IN_PREVIOUS_MISS_"+day)
        if (gh["status"]!="NO_MATCH_IN_ARCHIVED_HOUR_NOT_ABSENCE_PROOF"
            or parentCommit!=c["expectedCommitSha"]
            or parentSource["status"]!="ORIGINAL_GIT_BLOB_AND_MVRV_TRIAD_PASS"):
            raise ValueError("FROZEN_ORIGINAL_HOUR13_NEGATIVE_CONTROL_CHANGED_"+day)
        originalCheck=original_source({**c,"hourUTC":13},day)
        if (originalCheck["status"]!="ORIGINAL_GIT_BLOB_AND_MVRV_TRIAD_PASS"
            or originalCheck["sourceCommit"]!=c["expectedCommitSha"]
            or originalCheck["sourceSha256"]!=parentSource["sourceSha256"]):
            raise ValueError("ORIGINAL_HISTORICAL_SOURCE_REPLAY_CHANGED_"+day)
        hh=[]
        qualifying=[]
        for h in cfg["frozenAdjacentHoursUTC"]:
            hour={**c,"hourUTC":h}
            archive=event_hour(hour,cfg["sourceBoundaries"])
            matching=archive["status"]=="MATCHED_ORIGINAL_REPO_PUSH_EVENT"
            verified=[]
            if matching:
                verified=[x for x in archive["matchedEvents"] if
                    x.get("repo")=="coinmetrics/data" and x.get("matchedSha")==c["expectedCommitSha"]]
                if not verified:
                    raise ValueError("GHARCHIVE_MATCHING_SHA_INCONSISTENT")
                for event in verified:
                    event_t=datetime.fromisoformat(event["createdAtUTC"].replace("Z","+00:00"))
                    deadline=datetime.combine(date.fromisoformat(day),datetime.min.time(),timezone.utc)
                    if event_t>=deadline:
                        raise ValueError("PUBLIC_EVENT_LOOKAHEAD")
                    qualifying.append({"hour":h,"publicEvent":event})
            hh.append({
                "hourUTC":h,"archiveStatus":archive["status"],
                "totalEvents":archive["totalEvents"],
                "originalRepoPushEvents":archive["originalRepoPushEvents"],
                "matchedEvents":archive["matchedEvents"],
                "compressedBytes":archive["compressedBytes"],
                "compressedSHA256":archive["compressedSha256"],
                "error":archive["sourceError"]
            })
            print("V818D6_HOUR "+json.dumps({"date":day,"hourUTC":h,
                "status":archive["status"],"originalRepoPushEvents":archive["originalRepoPushEvents"],
                "matchedCount":len(archive["matchedEvents"]),
                "networkError":archive["sourceError"]},ensure_ascii=False),flush=True)
        reportRows.append({
            "date":day,"expectedCommitSha":c["expectedCommitSha"],
            "oldHour13Status":gh["status"],
            "originalSourceReplay":originalCheck,
            "newHours":hh,
            "matchedAnyAdjacentHours":bool(qualifying),
            "qualifyingPublicPushEvents":qualifying,
            "alreadyInHistorical26":day in carried["allWitnessDates"]
        })
    new=sorted(x["date"] for x in reportRows if x["matchedAnyAdjacentHours"] and not x["alreadyInHistorical26"])
    errors=sum(bool(h["error"]) for row in reportRows for h in row["newHours"])
    state=("EARLY_ARCHIVE_ADJACENT_PUBLIC_PUSH_FOUND_POSTHOC"
           if new else "NO_EARLY_ADJACENT_PUSH_PROOF_POSTHOC")
    report={
       "version":"8.18d6","status":state,"researchOnly":True,"tradeAuthorized":False,
       "experiment":"POST_HOC_AFTER_PREVIOUS_13UTC_NEGATIVES_NONCONFIRMATORY",
       "preregSHA256":sha(specraw),"pinnedParents":cfg["parents"],
       "unchangedOriginalBTC684":True,"oldDatedAsOfWeeks":26,
       "originalMetricApiReleaseClockVerified":0,
       "newEarlySourceWitnessDates":new,
       "candidatesTested":4,"adjacentHoursTested":8,
       "archiveErrorCount":errors,
       "caseReports":reportRows,
       "interpretation":[
          "Source provenance only; adjacent hours selected after 13 UTC source evidence misses, never confirmatory validation.",
          "A GH Archive original coinmetrics/data PushEvent with exact Git SHA proves only source GitHub public availability, not Coin Metrics API first-release UTC.",
          "No match in these hours does not prove MVRV was not published; archived hourly coverage or event encoding may be incomplete.",
          "The original 684 BTCI weeks and 26 previously witnessed MVRV numerical weeks were unchanged, no outcome labels or models inspected.",
          "No trading, master, reserves, portfolio or signal changes."
       ],"portfolioWriteback":cfg["portfolioWriteback"]
    }
    output=Path("btci_v818d6_reports")
    output.mkdir(exist_ok=True)
    payload=(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+"\n").encode()
    (output/"early_GHArchive_adjacent_hour_source_audit_FULL.json").write_bytes(payload)
    prefix="research/btci/v8.18d6/runs/{}-{}/".format(os.environ["GITHUB_RUN_ID"],os.getenv("GITHUB_RUN_ATTEMPT","1"))
    def put(name,bytes_):
        key=prefix+name
        checksum=sha(bytes_)
        s3.put_object(Bucket=bucket,Key=key,Body=bytes_,ContentType="application/json",
            Metadata={"sha256":checksum,"research-only":"true"})
        check=s3.get_object(Bucket=bucket,Key=key)["Body"].read()
        if sha(check)!=checksum:raise RuntimeError("R2_SHA256_GET_READBACK_FAILED")
        return {"key":key,"sha256":checksum,"bytes":len(bytes_)}
    stored=put("early_GHArchive_adjacent_hour_source_audit_FULL.json",payload)
    manifest=put("manifest.json",(json.dumps({"version":"8.18d6","researchOnly":True,
        "status":state,"report":stored,"preregSha256":sha(specraw),
        "noTradingChanges":True},ensure_ascii=False,indent=2)+"\n").encode())
    summary={"status":state,"caseCount":4,"hours":8,"newDatedSourceWitnesses":new,
        "priorAsOfWitnesses":26,"postHoc":True,"errorCount":errors,
        "sampledHours":[{"date":r["date"],"statuses":[{"hour":h["hourUTC"],
            "status":h["archiveStatus"],"originalRepoEvents":h["originalRepoPushEvents"]}
            for h in r["newHours"]]} for r in reportRows],
        "reportSHA256":stored["sha256"],"manifestSHA256":manifest["sha256"],
        "prefix":prefix}
    (output/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n")
    print("V818D6_RESULT "+json.dumps(summary,ensure_ascii=False),flush=True)

if __name__=="__main__":
    if "--self-test" in sys.argv:selftest()
    else:main()
