#!/usr/bin/env python3
"""BTCI v8.18c6: 684-week historical source eligibility audit; never a trading signal."""
import csv
import hashlib
import io
import json
import math
import os
import sys
import time
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import boto3

ROOT=Path(__file__).resolve().parents[1]
SPEC=ROOT/"research/btci_v818c6_684week_mvrv_pit_eligibility_prereg_2026-10-19.json"

def sha256(raw):
    return hashlib.sha256(raw).hexdigest()

def gitsha(raw):
    return hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()

def number(x):
    if x is None or str(x).strip().lower() in ("","nan","null","none","na"):
        return None
    z=float(x)
    return z if math.isfinite(z) else None

def parse_metric(raw):
    r=csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    fields=r.fieldnames or []
    key="time" if "time" in fields else "date" if "date" in fields else None
    if key is None:
        raise ValueError("INVALID_COINMETRICS_DATE_SCHEMA")
    exists="CapMVRVCur" in fields
    real="CapRealUSD" in fields
    vals={}
    first,last=None,None
    for row in r:
        d=(row.get(key) or "")[:10]
        date.fromisoformat(d)
        if d in vals:
            raise ValueError("DUPLICATE_HISTORIC_DATE")
        vals[d]=number(row.get("CapMVRVCur")) if exists else None
        first=d if first is None else first
        last=d
    if len(vals)<1000:
        raise ValueError("TRUNCATED_HISTORICAL_ARCHIVE")
    return {"rows":len(vals),"first":first,"last":last,"mvrvColumn":exists,
            "realCapColumn":real,"values":vals}

def get_csv(info,owner,repo):
    u=f"https://raw.githubusercontent.com/{owner}/{repo}/{info['sha']}/csv/btc.csv"
    err=None
    for attempt in range(3):
        try:
            with urlopen(Request(u,headers={"User-Agent":"BTCI-v818c6-asof-audit"}),timeout=50) as rsp:
                raw=rsp.read(13_000_000)
            if len(raw)!=info["bytes"] or gitsha(raw)!=info["blob"]:
                raise ValueError("PINNED_COINMETRICS_GIT_BLOB_MISMATCH")
            return raw
        except (HTTPError,URLError,TimeoutError) as exc:
            err=str(exc)
            if attempt<2:
                time.sleep(2*(attempt+1))
    raise RuntimeError("SOURCE_NOT_RECOVERABLE "+str(err))

def classify(day,snapshots,maxage=7):
    t=date.fromisoformat(day)
    if t.weekday()!=6:
        raise ValueError("NOT_SUNDAY")
    # This is a candidate, not independently verified original public first-seen.
    obsmax=t-timedelta(days=2)
    hist=[]
    for source in snapshots:
        if date.fromisoformat(source["label"]) >= t or not source["mvrvColumn"]:
            continue
        possible=[]
        for off in range(2,maxage+1):
            dt=(t-timedelta(days=off)).isoformat()
            val=source["values"].get(dt)
            if val is not None:
                possible.append((off,dt))
                break
        if possible:
            hist.append((date.fromisoformat(source["label"]),source,possible[0]))
    if not hist:
        return {"candidate":False,"source":None,"observedAt":None,"ageDays":None}
    hist.sort(key=lambda x:x[0],reverse=True)
    _,src,(age,obs)=hist[0]
    if date.fromisoformat(obs)>obsmax:
        raise ValueError("LOOKAHEAD_OBSERVATION_DATE")
    return {"candidate":True,"source":src["label"],"observedAt":obs,"ageDays":age}

def selftest():
    assert gitsha(b"hello\n")=="ce013625030ba8dba906f756967f9e9ca394464a"
    src={"label":"2020-01-31","mvrvColumn":True,
         "values":{"2020-01-30":1.3,"2020-01-31":2.4,"2020-02-01":3.2}}
    q=classify("2020-02-02",[src])
    assert q["candidate"] and q["observedAt"]=="2020-01-30" and q["ageDays"]==3
    assert not classify("2020-01-26",[src])["candidate"]
    assert not classify("2020-02-09",[src])["candidate"]
    print("V818C6_SELFTEST_PASS",flush=True)

def main():
    preregbytes=SPEC.read_bytes()
    spec=json.loads(preregbytes)
    if spec["version"]!="8.18c6" or spec["mode"]!="RESEARCH_ONLY":
        raise ValueError("UNREGISTERED_VERSION")
    s3=boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
                   aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
                   aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
    bucket=os.environ["R2_BUCKET"]
    parent={}
    for name,entry in spec["parent"].items():
        raw=s3.get_object(Bucket=bucket,Key=entry["key"])["Body"].read()
        if sha256(raw)!=entry["sha256"]:
            raise ValueError("PARENT_SHA_MISMATCH_"+name)
        parent[name]=json.loads(raw)
    base=parent["btcPanel"]
    panel=base["weeklyPanel"]
    if len(panel)!=spec["parent"]["btcPanel"]["expectedSundays"]:
        raise ValueError("684_PANEL_COUNT_CHANGED")
    dates=[r["date"] for r in panel]
    if len(set(dates))!=684 or dates!=sorted(dates):
        raise ValueError("684_PANEL_UNSORTED_OR_DUPLICATED")
    if any(date.fromisoformat(d).weekday()!=6 for d in dates):
        raise ValueError("PANEL_HAS_NON_SUNDAY")
    if base["version"]!="8.17.1":
        raise ValueError("PARENT_VERSION_CHANGED")
    if parent["gitAudit"]["version"]!="8.18c3" or parent["anchorMismatch"]["version"]!="8.18c4" or parent["fiveDayDiagnosis"]["version"]!="8.18c5":
        raise ValueError("AUDIT_PARENTS_INVALID")
    known=parent["gitAudit"]["vintages"]
    verified_by_commit={v["commitSHA"]:v for v in known}
    snaps=[]
    sources=[]
    ss=spec["vintageSources"]
    for info in ss["samples"]:
        raw=get_csv(info,ss["owner"],ss["repo"])
        parsed=parse_metric(raw)
        old=verified_by_commit.get(info["sha"])
        if old is None or old["contentSHA256"]!=sha256(raw) or old["rowCount"]!=parsed["rows"]:
            raise ValueError("GIT_AUDIT_PARENT_REPLAY_DIFF_"+info["label"])
        snaps.append({"label":info["label"],"mvrvColumn":parsed["mvrvColumn"],"values":parsed["values"]})
        sources.append({"label":info["label"],"gitCommit":info["sha"],
            "gitBlobSha1":info["blob"],"sha256":sha256(raw),"bytes":len(raw),
            "records":parsed["rows"],"firstObservation":parsed["first"],"lastObservation":parsed["last"],
            "MVRV":parsed["mvrvColumn"],"CapRealUSD":parsed["realCapColumn"],
            "independentOriginalFirstSeenVerified":False})
        print("V818C6_SOURCE "+json.dumps({"label":info["label"],"rows":parsed["rows"],
                 "MVRV":parsed["mvrvColumn"],"CapRealUSD":parsed["realCapColumn"]}),flush=True)
    rows=[]
    eras=defaultdict(lambda:{"weeks":0,"gitVintageCandidates":0,"strictPIT":0})
    for idx,r in enumerate(panel):
        d=r["date"]
        assessment=classify(d,snaps,maxage=spec["study"]["maxAgeDays"])
        strict=False  # Pre-registered: no independently proven exact first-seen source per Sunday.
        er=r["era"]
        eras[er]["weeks"]+=1
        eras[er]["gitVintageCandidates"]+=int(assessment["candidate"])
        eras[er]["strictPIT"]+=int(strict)
        row={"date":d,"era":er,"sourceAgeDays":assessment["ageDays"],
             "historicalGitCandidate":assessment["candidate"],
             "historicalSnapshotDate":assessment["source"],
             "dailyObservationDate":assessment["observedAt"],
             "originalFirstAvailableAtUTC":None,"strictPITEligible":strict,
             "classification":("GIT_COMMIT_RECONSTRUCTION_ONLY_PUBLIC_FIRST_SEEN_UNVERIFIED"
                               if assessment["candidate"] else
                               "NO_TIME_ELIGIBLE_VERIFIED_VINTAGE_SAMPLE")}
        rows.append(row)
    n=sum(r["historicalGitCandidate"] for r in rows)
    strictcount=sum(r["strictPITEligible"] for r in rows)
    assert strictcount==0 and len(rows)==684
    bysource=dict(Counter(x["historicalSnapshotDate"] for x in rows if x["historicalGitCandidate"]))
    report={
        "version":"8.18c6","status":"PIT_GATING_AUDIT_COMPLETE_ZERO_STRICT_VERIFIED_MVRV",
        "researchOnly":True,"tradeAuthorized":False,
        "prereg":{"path":str(SPEC.relative_to(ROOT)),"sha256":sha256(preregbytes)},
        "pinnedParents":spec["parent"],"numWeeks":684,
        "panelFirst":dates[0],"panelLast":dates[-1],"originalPanelUnchanged":True,
        "sourceAudit":sources,"sourceVintageGitCandidateWeeks":n,
        "sourceVintageGitCandidateBySource":bysource,
        "strictOriginalPublicationVerifiedWeeks":strictcount,
        "weeksWithoutCandidate":684-n,
        "byEra":dict(sorted(eras.items())),
        "perSundayEligibility":rows,
        "contemporaneousAnchor":{"publicationDate":"2020-01-01","printed":1.33,
            "CSV2019_12_30":1.29751611,"CSV2019_12_29":1.32663778,
            "dateMapping":"UNVERIFIED","usableAsExactDailyAlignedFeature":False},
        "reason":"For these seven pre-specified Git archives, original public first-seen timestamp and exact method-aligned MVRV values are unverified per Sunday. A git object and its commit-time metadata are not sufficient.",
        "studyInterpretation":["Zero strict PIT means zero proved eligible with CURRENT EVIDENCE, not that zero actual historical public MVRV existed.",
            "Candidate count is sparse fixed frozen Git vintage availability; not general full original Git history coverage.",
            "Even a 2d lag on observation only prevents observation-date lookahead, not publication-date lookahead.",
            "The Jan 2020 public 1.33 article is a single rounded publication point with date discrepancy.",
            "Do not use the 684 retrospective 2026 MVRV columns as a causally known ex ante signal.",
            "No outcomes retested, model coefficients, thresholds, independent OOS, or expected trading edge."],
        "portfolioWriteback":{x:False for x in spec["prohibitions"]}
    }
    folder=Path("btci_v818c6_reports")
    folder.mkdir(exist_ok=True)
    raw=(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+"\n").encode()
    (folder/"mvrv_684_week_pit_eligibility_FULL.json").write_bytes(raw)
    prefix="research/btci/v8.18c6/runs/{}-{}/".format(os.environ["GITHUB_RUN_ID"],os.environ.get("GITHUB_RUN_ATTEMPT","1"))
    def put(file,data):
        key=prefix+file
        s3.put_object(Bucket=bucket,Key=key,Body=data,ContentType="application/json",
                      Metadata={"sha256":sha256(data),"research-only":"true"})
        echo=s3.get_object(Bucket=bucket,Key=key)["Body"].read()
        if sha256(echo)!=sha256(data):
            raise RuntimeError("R2_WRITEBACK_READ_SHA_MISMATCH")
        return {"key":key,"sha256":sha256(data),"bytes":len(data)}
    saved=put("mvrv_684_week_pit_eligibility_FULL.json",raw)
    manifest=put("manifest.json",(json.dumps({"version":"8.18c6","researchOnly":True,
        "status":report["status"],"report":saved,"preregSHA256":sha256(preregbytes),
        "parentBTC684SHA256":spec["parent"]["btcPanel"]["sha256"],
        "license":"Source numerical bulk CSV NOT reposted"},ensure_ascii=False,indent=2)+"\n").encode())
    summary={"status":report["status"],"weeklyDates":684,"candidateWeeks":n,
        "strictPITVerifiedWeeks":strictcount,"perEra":report["byEra"],
        "byVintage":bysource,"reportSha256":saved["sha256"],
        "manifestSha256":manifest["sha256"],"prefix":prefix}
    (folder/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n")
    print("V818C6_RESULT "+json.dumps(summary,ensure_ascii=False),flush=True)

if __name__=="__main__":
    if "--self-test" in sys.argv:
        selftest()
    else:
        main()
