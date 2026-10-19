#!/usr/bin/env python3
"""BTCI v8.18c9: Git-committer chronological candidate calendar, explicitly NOT independently published PIT."""
import csv
import hashlib
import io
import json
import math
import os
import sys
import time
from datetime import datetime,date,timedelta,timezone
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError,URLError
from collections import Counter,defaultdict
import boto3

ROOT=Path(__file__).resolve().parents[1]
PREREG=ROOT/"research/btci_v818c9_historical_commit_calendar_prereg_2026-10-19.json"
USERAGENT="BTCI-v818c9-research-only-historical-Git-provenance"

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def git_sha1(raw):
    return hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()

def timestamp(s):
    return datetime.fromisoformat(s.replace("Z","+00:00"))

def get(url,maximum=25_000_000,attempts=3):
    headers={"User-Agent":USERAGENT,"Accept":"application/vnd.github+json"}
    if url.startswith("https://api.github.com/") and os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"]="Bearer "+os.environ["GITHUB_TOKEN"]
    last=""
    for n in range(attempts):
        try:
            req=Request(url,headers=headers)
            with urlopen(req,timeout=55) as fh:
                raw=fh.read(maximum+1)
            if len(raw)>maximum: raise ValueError("SOURCE_TOO_LARGE")
            return raw
        except (HTTPError,URLError,TimeoutError) as exc:
            last=str(exc)
            if n+1<attempts:time.sleep(2*(n+1))
    raise RuntimeError("HTTP_SOURCE_UNAVAILABLE "+last)

def read_numeric(s):
    if s is None or str(s).strip().lower() in ("","null","none","nan","na"):
        return None
    val=float(s)
    return val if math.isfinite(val) else None

def fixed_window(raw,sunday):
    rd=csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    headers=rd.fieldnames or []
    datekey="time" if "time" in headers else "date" if "date" in headers else None
    if datekey is None:
        raise ValueError("NO_DATE_COLUMN")
    names=("CapMVRVCur","CapRealUSD","CapMrktCurUSD")
    have={x:x in headers for x in names}
    start=date.fromisoformat(sunday)
    dates={(start-timedelta(days=offset)).isoformat():offset for offset in range(2,8)}
    choices={}
    rowcount=0
    lastdate=None
    for row in rd:
        rowcount+=1
        observed=(row.get(datekey) or "")[:10]
        date.fromisoformat(observed)
        lastdate=observed
        if observed in dates:
            if observed in choices:
                raise ValueError("DUPLICATE_DATE_IN_ARCHIVE")
            values={x:read_numeric(row.get(x)) for x in names}
            choices[observed]={"observationDate":observed,"ageDays":dates[observed],
                               "mvrv":values["CapMVRVCur"],"realCap":values["CapRealUSD"],
                               "marketCap":values["CapMrktCurUSD"]}
    chosen=None
    if all(have.values()):
        for d in sorted(choices,reverse=True):
            vals=choices[d]
            m,r,c=vals["mvrv"],vals["realCap"],vals["marketCap"]
            if any(x is None or x<=0 for x in (m,r,c)):
                continue
            if not math.isclose(m,c/r,rel_tol=0.000005,abs_tol=0.000005):
                continue
            chosen=vals
            break
    return {"rowCount":rowcount,"lastObservationInFile":lastdate,"columns":have,
            "eligibleOldObservation":chosen is not None,
            "observation":chosen,"fixedWindowHadRows":len(choices)}

def selftest():
    assert git_sha1(b"hello\n")=="ce013625030ba8dba906f756967f9e9ca394464a"
    rd=b"time,CapMVRVCur,CapRealUSD,CapMrktCurUSD\n2020-07-03T00:00:00Z,1.5,20,30\n2020-07-04T00:00:00Z,1.8,20,36\n"
    v=fixed_window(rd,"2020-07-05")
    assert v["eligibleOldObservation"] and v["observation"]["observationDate"]=="2020-07-03"
    assert fixed_window(rd,"2020-07-12")["eligibleOldObservation"] is False
    print("V818C9_SELFTEST_PASS",flush=True)

def main():
    spec_raw=PREREG.read_bytes()
    spec=json.loads(spec_raw)
    if spec["version"]!="8.18c9" or not spec["researchOnly"] or spec["tradeAuthority"]:
        raise RuntimeError("FROZEN_PREREG_INVALID")
    s3=boto3.client("s3",
        endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto")
    bucket=os.environ["R2_BUCKET"]
    def parent(entry):
        raw=s3.get_object(Bucket=bucket,Key=entry["key"])["Body"].read()
        if sha(raw)!=entry["sha256"]: raise RuntimeError("PINNED_PARENT_SHA256_MISMATCH")
        return json.loads(raw)
    parents=spec["parents"]
    panel=parent(parents["v8171"])["weeklyPanel"]
    c8=parent(parents["c8"])
    if len(panel)!=684 or len(c8["perSundayEvidence"])!=684:
        raise RuntimeError("IMMUTABLE_684_PANEL_CHANGED")
    alldates=[row["date"] for row in panel]
    if alldates!=[row["date"] for row in c8["perSundayEvidence"]] or alldates!=sorted(alldates):
        raise RuntimeError("INHERITED_684_DATES_MISMATCH")
    strictly_dated=[r["date"] for r in c8["perSundayEvidence"] if r["publicGitHubForkMvrvEvidence"]]
    if len(strictly_dated)!=11:
        raise RuntimeError("PIT_EVIDENCE_11_FROZEN_BASELINE_CHANGED")
    frozen=spec["frozenAnchorSundays"]
    if len(frozen)!=26 or len(set(frozen))!=len(frozen):
        raise RuntimeError("FROZEN_ANCHORS_INVALID")
    if any(d not in alldates for d in frozen):
        raise RuntimeError("ANCHOR_NOT_IN_684_PANEL")
    audits=[]
    statuses=Counter()
    for anchor in frozen:
        t=datetime.combine(date.fromisoformat(anchor),datetime.min.time(),tzinfo=timezone.utc)
        past=anchor+"T00:00:00Z"
        rep="croque-m/coinmetrics-data" if anchor<"2025-01-01" else "wds33817/data"
        commit_api="https://api.github.com/repos/"+rep+"/commits?path=csv/btc.csv&until="+past+"&per_page=1"
        out={"Sunday":anchor,"archiveRepo":rep,"chronologyTier":"B_GIT_COMMIT_NO_INDEPENDENT_PUBLIC_PUSH_PROOF",
             "isIndependentlyPITProven":anchor in strictly_dated,"sourceError":None}
        try:
            commits=json.loads(get(commit_api,1_000_000))
            if not commits:
                out["status"]="NO_HISTORIC_COMMIT_BEFORE_DECISION"
            else:
                commit=commits[0]
                h=commit["sha"]
                committer=timestamp(commit["commit"]["committer"]["date"])
                if committer>=t:
                    raise RuntimeError("GIT_COMMIT_TIMESTAMP_AFTER_DECISION")
                tree_api="https://api.github.com/repos/"+rep+"/git/trees/"+h+"?recursive=1"
                tree=json.loads(get(tree_api,3_000_000))
                file=next((x for x in tree["tree"] if x["path"]=="csv/btc.csv"),None)
                if not file:raise RuntimeError("CSV_NOT_IN_PINNED_COMMIT")
                raw_url="https://raw.githubusercontent.com/"+rep+"/"+h+"/csv/btc.csv"
                raw=get(raw_url,20_000_000)
                if git_sha1(raw)!=file["sha"] or len(raw)!=file.get("size"):
                    raise RuntimeError("GIT_BLOB_RAW_CONTENT_MISMATCH")
                source=fixed_window(raw,anchor)
                out.update({"originalCommitSha":h,"committerUTC":committer.isoformat(),
                    "commitAgeHours":round((t-committer).total_seconds()/3600,3),
                    "gitBlobSha1":file["sha"],"sourceSha256":sha(raw),
                    "rawFileSize":len(raw),"sourceRowCount":source["rowCount"],
                    "lastFileObservation":source["lastObservationInFile"],
                    "requiredMetricColumns":source["columns"],
                    "fixedWindowHadRows":source["fixedWindowHadRows"],
                    "verifiedOldObservation":source["observation"]})
                if not all(source["columns"].values()):
                    out["status"]="MISSING_REQUIRED_TRIAD_IN_OLD_GIT_COMMIT"
                elif not source["eligibleOldObservation"]:
                    out["status"]="NO_VALID_FRIDAY_TO_7D_SOURCE_ROW"
                elif (t-committer).total_seconds()>7*86400:
                    out["status"]="STALE_HISTORICAL_GIT_COMMIT_OLDER_THAN_7D"
                else:
                    out["status"]="SOURCE_OBJECT_AND_COMMIT_TIMELINE_MATCH_NOT_PUBLIC_FIRST_SEEN"
        except Exception as exc:
            out["status"]="SOURCE_AUDIT_FAILED"
            out["sourceError"]=str(exc)[:350]
        audits.append(out)
        statuses[out["status"]]+=1
        print("V818C9_ANCHOR "+json.dumps({"date":anchor,"status":out["status"],
            "commitAgeHours":out.get("commitAgeHours"),
            "observation":out.get("verifiedOldObservation",{}).get("observationDate") if out.get("verifiedOldObservation") else None,
            "error":out["sourceError"]},ensure_ascii=False),flush=True)
    eligible=sum(a["status"]=="SOURCE_OBJECT_AND_COMMIT_TIMELINE_MATCH_NOT_PUBLIC_FIRST_SEEN" for a in audits)
    missing=sum(a["status"]=="SOURCE_AUDIT_FAILED" for a in audits)
    resultstatus="RESEARCH_GIT_COMMIT_HISTORY_ONLY_NO_NEW_PIT_PROOF" if missing==0 else "PARTIAL_HISTORY_SOURCE_AUDIT_FAILURE"
    report={"version":"8.18c9","status":resultstatus,
        "researchOnly":True,"tradeAuthorized":False,
        "preregSha256":sha(spec_raw),"parentPins":parents,
        "originalPanel684Preserved":True,
        "strictDatedForkAsOfCountUnchanged":11,
        "originalCoinMetricsProviderFirstSeenValidated":0,
        "quarterly26SampledSundays":len(frozen),
        "historicalCommitCandidates":eligible,
        "sourceAuditFailures":missing,
        "classifications":dict(statuses),
        "eachFrozenSunday":audits,
        "interpretation":[
            "The original frozen Git history preserved by later forks may show a highly regular commit schedule, but historical Git committer date is NOT an independent original public push date.",
            "26 frozen Sundays are a diagnostic subsample, never a new 684-week continuous PIT panel.",
            "The 11 independent archived public fork witnesses from v8.18c8 remain the sole high-confidence as-of numeric snapshot evidence under these rules.",
            "First Coin Metrics original metric API release clock and possible historical revisions are still unverified.",
            "Data cannot be safely promoted to backtested predictive BTCI model using only these older commit timestamps.",
            "No future BTC outcome labels, performance tests, trading signals, metric thresholds or position changes."
        ],
        "portfolioWriteback":{x:False for x in ("Spot","Futures","NAV","PnL","capital","reserve","MASTER","Detector","tradingLimits","orders")}
    }
    output=Path("btci_v818c9_reports")
    output.mkdir(exist_ok=True)
    full=(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+"\n").encode()
    (output/"git_historical_calendar_FULL.json").write_bytes(full)
    prefix="research/btci/v8.18c9/runs/{}-{}/".format(
        os.environ["GITHUB_RUN_ID"],os.getenv("GITHUB_RUN_ATTEMPT","1"))
    def write(name,raw):
        key=prefix+name
        checksum=sha(raw)
        s3.put_object(Bucket=bucket,Key=key,Body=raw,ContentType="application/json",
            Metadata={"sha256":checksum,"research-only":"true"})
        read=s3.get_object(Bucket=bucket,Key=key)["Body"].read()
        if sha(read)!=checksum:raise RuntimeError("R2_SHA256_READBACK_FAILURE")
        return {"key":key,"sha256":checksum,"bytes":len(raw)}
    record=write("git_historical_calendar_FULL.json",full)
    manifest=write("manifest.json",(json.dumps({"version":"8.18c9","researchOnly":True,
        "report":record,"status":resultstatus,"preregSHA256":sha(spec_raw),
        "strictPrior11Immutable":True},ensure_ascii=False,indent=2)+"\n").encode())
    summary={"status":resultstatus,"original684":684,"anchors":len(frozen),
        "candidateOriginalGitChronology":eligible,"strictPublicPITUnchanged":11,
        "originalProviderPublicationClockVerified":0,"sourceFailures":missing,
        "statuses":dict(statuses),"reportSha256":record["sha256"],
        "manifestSha256":manifest["sha256"],"prefix":prefix}
    (output/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n")
    print("V818C9_RESULT "+json.dumps(summary,ensure_ascii=False),flush=True)

if __name__=="__main__":
    if "--self-test" in sys.argv:selftest()
    else:main()
