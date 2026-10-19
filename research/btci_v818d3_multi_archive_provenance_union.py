#!/usr/bin/env python3
"""BTCI v8.18d3: independently witnessed MVRV as-of source ledger; no trading authority."""
import hashlib
import json
import os
import sys
from collections import Counter,defaultdict
from datetime import date,datetime,timezone
from pathlib import Path
import boto3

ROOT=Path(__file__).resolve().parents[1]
PREREG=ROOT/"research/btci_v818d3_multi_archive_provenance_union_prereg_2026-10-19.json"

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def asutc(s):
    return datetime.fromisoformat(s.replace("Z","+00:00"))

def sunday_cutoff(day):
    d=date.fromisoformat(day)
    if d.weekday()!=6:
        raise ValueError("EXPECTED_SUNDAY_"+day)
    return datetime.combine(d,datetime.min.time(),timezone.utc)

def count_days(day,obs):
    return (date.fromisoformat(day)-date.fromisoformat(obs)).days

def accept(item):
    day=item["date"]
    cutoff=sunday_cutoff(day)
    when=asutc(item["availableUTC"])
    lag=count_days(day,item["observed"])
    val=float(item["mvrv"])
    if not (when<cutoff and 2<=lag<=7 and val>0):
        raise ValueError("FAIL_CUTOFF_LAG_OR_MVRV_"+item["type"]+"_"+day)
    return item

def fork(row):
    evidence=row["numericEvidence"]
    if not evidence or not row["publicGitHubForkMvrvEvidence"]:
        raise ValueError("FALSE_FORK_WITNESS")
    return accept({"date":row["date"],"type":"public_github_fork_snapshot",
        "source":evidence["source"],"availableUTC":evidence["publicWitnessUTC"],
        "observed":evidence["observedDate"],"mvrv":evidence["mvrv"],
        "sourceHash":evidence.get("gitBTCBlob"),
        "sourceVerifiedInParent":"v8.18c8"})

def archive_wayback(wayback):
    if wayback["archivedCSV"]["captureUTC"]!="2024-05-25T01:53:26Z":
        raise ValueError("WAYBACK_CAPTURE_IDENTITY_CHANGED")
    if not wayback["archivedCSV"]["SHA256"] or not wayback["archivedCSV"]["gitBlobSHA1"]:
        raise ValueError("WAYBACK_PINNED_CSV_HASH_MISSING")
    result=[]
    for x in wayback["newIndependentWaybackNumericWitnesses"]:
        if x["publicCaptureUTC"] not in ("2024-05-25T01:53:26+00:00","2024-05-25T01:53:26Z"):
            raise ValueError("WAYBACK_PUBLIC_TIME_CHANGED")
        if not x["ratioArithmeticVerified"]:
            raise ValueError("WAYBACK_MVRV_RATIO_NOT_VERIFIED")
        result.append(accept({"date":x["date"],"type":"internet_archive_CSV_bytes",
            "source":wayback["archivedCSV"]["url"],"availableUTC":x["publicCaptureUTC"],
            "observed":x["observedUTCDate"],"mvrv":x["MVRV"],
            "sourceHash":wayback["archivedCSV"]["SHA256"],
            "sourceVerifiedInParent":"v8.18d2"}))
    return result

def push_event(record,sourceversion):
    if sourceversion=="v8.18c10":
        datekey=record["sunday"]
        proof=record["independentOriginalRepoPublicPushWitnessBeforeDecision"]
        source=record["originalGitSource"]
        archive=record["archive"]
        expected=record["expectedGitCommit"]
    else:
        datekey=record["date"]
        proof=record["originalPublicGithubPushBeforeDecision"]
        source=record["originalGitArchive"]
        archive=record["independentThirdPartyEventArchive"]
        expected=record["expectedCommitSHA"]
    if not proof:
        return None
    if source["status"]!="ORIGINAL_GIT_BLOB_AND_MVRV_TRIAD_PASS":
        raise ValueError("GHARCHIVE_ORIGINAL_MVRV_SOURCE_UNVERIFIED")
    if source["sourceCommit"]!=expected:
        raise ValueError("GHARCHIVE_SOURCE_COMMIT_MISMATCH")
    if archive["status"]!="MATCHED_ORIGINAL_REPO_PUSH_EVENT" or not archive["matchedEvents"]:
        raise ValueError("GHARCHIVE_INDEPENDENT_PUSH_EVENT_UNVERIFIED")
    matches=[e for e in archive["matchedEvents"] if
        e.get("repo")=="coinmetrics/data" and e.get("matchedSha")==expected]
    if not matches:
        raise ValueError("ORIGINAL_GITHUB_PUSH_SHA_NOT_MATCHED")
    witnessed=min(matches,key=lambda e:e["createdAtUTC"])
    if source["lagDays"]!=count_days(datekey,source["observation"]):
        raise ValueError("ARCHIVED_ORIGINAL_MVRV_OBSERVATION_AGE_CHANGED")
    return accept({"date":datekey,"type":"GHArchive_original_github_PushEvent",
        "source":"coinmetrics/data",
        "availableUTC":witnessed["createdAtUTC"],
        "observed":source["observation"],"mvrv":source["mvrv"],
        "sourceHash":source["sourceSha256"],
        "commitSHA":expected,"GHArchiveEventId":witnessed.get("eventId"),
        "sourceVerifiedInParent":sourceversion})

def selftest():
    assert digest(b"test")==hashlib.sha256(b"test").hexdigest()
    a={"date":"2024-05-26","availableUTC":"2024-05-25T01:53:26+00:00",
       "observed":"2024-05-23","mvrv":2.3,"type":"test"}
    assert accept(a)==a
    try:
        accept({**a,"availableUTC":"2024-05-26T00:00:01Z"})
        raise AssertionError("FUTURE_PUBLISH_SHOULD_FAIL")
    except ValueError:pass
    try:
        accept({**a,"observed":"2024-05-25"})
        raise AssertionError("SATURDAY_LOOKAHEAD_SHOULD_FAIL")
    except ValueError:pass
    print("V818D3_SELFTEST_PASS",flush=True)

def main():
    preregraw=PREREG.read_bytes()
    reg=json.loads(preregraw)
    if reg["version"]!="8.18d3" or not reg["researchOnly"] or reg["tradeAuthorized"]:
        raise RuntimeError("FROZEN_PREREG_AUTHORITY_GUARD")
    s3=boto3.client("s3",
        endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
        region_name="auto",aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"])
    bucket=os.environ["R2_BUCKET"]
    def pinned(k):
        p=reg["parents"][k]
        raw=s3.get_object(Bucket=bucket,Key=p["key"])["Body"].read()
        if digest(raw)!=p["sha256"]:
            raise ValueError("PINNED_PARENT_SHA_CHANGED_"+k)
        data=json.loads(raw)
        if not data.get("researchOnly") or data.get("tradeAuthorized"):
            raise ValueError("SOURCE_NOT_RESEARCH_ONLY_"+k)
        return data
    btc=pinned("btc")
    c8=pinned("github_forks")
    wayback=pinned("wayback")
    c10=pinned("gharchive_pilot")
    c11=pinned("gharchive_expansion")
    panel=btc["weeklyPanel"]
    dates=[x["date"] for x in panel]
    if (len(dates)!=684 or len(set(dates))!=684 or dates!=sorted(dates)
       or dates!=[x["date"] for x in c8["perSundayEvidence"]]):
        raise ValueError("ORIGINAL_BTCI_684_PANEL_CHANGED")
    if any(date.fromisoformat(d).weekday()!=6 for d in dates):
        raise ValueError("ORIGINAL_PANEL_NOT_SUNDAYS")
    index=defaultdict(list)
    for row in c8["perSundayEvidence"]:
        if row["publicGitHubForkMvrvEvidence"]:
            a=fork(row)
            index[a["date"]].append(a)
    g=reg["frozenExpected"]
    if len(index)!=g["baselineGitHubForks"]:
        raise ValueError("PRIOR_FORK_SOURCE_COUNT_CHANGED")
    wb=archive_wayback(wayback)
    if len(wb)!=g["independentWayback"]:
        raise ValueError("WAYBACK_NEW_COUNT_CHANGED")
    for a in wb:index[a["date"]].append(a)
    gp=[]
    for c in c10["cases"]:
        x=push_event(c,"v8.18c10")
        if x:gp.append(x)
    for c in c11["sixFrozenSourceHours"]:
        x=push_event(c,"v8.18c11")
        if x:gp.append(x)
    if (len(gp)!=g["originalGitHubPushEvents"] or
        sorted(x["date"] for x in gp)!=g["originalGitHubPushSundays"]):
        raise ValueError("EXACT_ORIGINAL_PROVIDER_PUSH_WITNESSES_CHANGED")
    for a in gp:index[a["date"]].append(a)
    if set(index)-set(dates):
        raise ValueError("WITNESS_DATE_NOT_ORIGINAL_BTCI_WEEK")
    if len(index)!=g["totalUnique"]:
        raise ValueError("FROZEN_PRE_REGISTERED_INDEPENDENT_UNION_COUNT_MISMATCH")
    conflicts=[]
    for day,items in index.items():
        values=[x["mvrv"] for x in items]
        if len(values)>1 and any(abs(v-values[0])>0.000005 for v in values[1:]):
            conflicts.append({"date":day,"mvrvValues":values,"sources":[a["type"] for a in items]})
    rows=[]
    perera=defaultdict(lambda:{"weeks":0,"independentAsOfNumericWitnesses":0})
    for original in panel:
        day=original["date"]
        witness=index.get(day,[])
        era=original["era"]
        perera[era]["weeks"]+=1
        perera[era]["independentAsOfNumericWitnesses"]+=int(bool(witness))
        rows.append({"date":day,"era":era,"hasIndependentPublicNumericMVRVWitness":bool(witness),
                     "independentSources":witness,
                     "originalProviderDailyAPIReleaseClockVerified":False,
                     "btcPriceOutcomeOrMacroModelRetested":False})
    counts=dict(Counter(x["type"] for items in index.values() for x in items))
    report={"version":"8.18d3","researchOnly":True,"tradeAuthorized":False,
        "status":"MULTI_ARCHIVE_ASOF_PROVENANCE_JOIN_VERIFIED_NOT_MODEL_EDGE",
        "prereg":{"path":str(PREREG.relative_to(ROOT)),"sha256":digest(preregraw)},
        "pinnedParents":reg["parents"],
        "originalBTCI684PanelUnchanged":True,"weeklyDates":684,
        "independentPublicAsOfMVRVWeekCount":len(index),
        "independentAsOfByEvidenceType":counts,
        "originalProviderDailyAPIReleaseClockVerified":0,
        "witnessDates":sorted(index),
        "overlappingWitnesses":[] if not any(len(v)>1 for v in index.values()) else
            [k for k,v in index.items() if len(v)>1],
        "numericConflicts":conflicts,
        "perEra":dict(sorted(perera.items())),"perSundayEvidence":rows,
        "interpretation":[
            "A public GitHub snapshot or independently archived original GitHub PushEvent indicates numeric historical availability in a public Git repository; a Wayback body independently witnesses archived bytes.",
            "GH Archive original repository public PushEvent is stronger than an original Git commit author timestamp, but does not prove Coin Metrics API release clock.",
            "All 17 weeks are independent existence witnesses for the original dated source values; neither the original provider daily API release time nor an OOS market prediction is proved.",
            "Original 684 weekly labels, BTC price outcomes and macro features were not examined or recomputed.",
            "No thresholds tuned or signals produced; no position, portfolio or trading authority change."
        ],
        "portfolioWriteback":reg["portfolioWriteback"]}
    folder=Path("btci_v818d3_reports");folder.mkdir(exist_ok=True)
    body=(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+"\n").encode()
    (folder/"multi_archive_684_MVRV_provenance_FULL.json").write_bytes(body)
    prefix="research/btci/v8.18d3/runs/{}-{}/".format(os.environ["GITHUB_RUN_ID"],os.environ.get("GITHUB_RUN_ATTEMPT","1"))
    def write(name,raw):
        key=prefix+name
        checksum=digest(raw)
        s3.put_object(Bucket=bucket,Key=key,Body=raw,ContentType="application/json",
            Metadata={"sha256":checksum,"research-only":"true"})
        got=s3.get_object(Bucket=bucket,Key=key)["Body"].read()
        if digest(got)!=checksum:
            raise RuntimeError("R2_UPLOAD_READBACK_SHA256_FAIL")
        return {"key":key,"sha256":checksum,"bytes":len(raw)}
    saved=write("multi_archive_684_MVRV_provenance_FULL.json",body)
    manifest=write("manifest.json",(json.dumps({
        "version":"8.18d3","researchOnly":True,"report":saved,
        "status":report["status"],"preregSHA256":digest(preregraw),
        "noTradingOrProductionWriteback":True},ensure_ascii=False,indent=2)+"\n").encode())
    summary={"status":report["status"],"originalPanelWeeks":684,
        "unionIndependentlyDatedMVRVWeeks":len(index),"byEvidenceType":counts,
        "dates":report["witnessDates"],"numericConflicts":len(conflicts),
        "perEra":report["perEra"],"providerFirstReleaseClockVerified":0,
        "reportSha256":saved["sha256"],"manifestSha256":manifest["sha256"],"prefix":prefix}
    (folder/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n")
    print("V818D3_RESULT "+json.dumps(summary,ensure_ascii=False),flush=True)

if __name__=="__main__":
    if "--self-test" in sys.argv:selftest()
    else:main()
