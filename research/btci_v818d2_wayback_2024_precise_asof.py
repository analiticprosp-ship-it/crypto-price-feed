#!/usr/bin/env python3
"""BTCI v8.18d2 exact Wayback 2024-05-25 archived BTC MVRV as-of verification, RESEARCH_ONLY."""
import csv
import hashlib
import io
import json
import math
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import boto3

ROOT=Path(__file__).resolve().parents[1]
PREREG=ROOT/"research/btci_v818d2_wayback_2024_precise_asof_prereg_2026-10-19.json"

def sha(b):return hashlib.sha256(b).hexdigest()
def gitsha(b):return hashlib.sha1(b"blob "+str(len(b)).encode()+b"\0"+b).hexdigest()
def dateutc(s):return datetime.fromisoformat(s.replace("Z","+00:00"))

def retrieve(url):
    last=None
    for i in range(2):
        try:
            with urlopen(Request(url,headers={"User-Agent":"BTCI-v818d2-Exact-Archived-2024-MVRV"}),timeout=45) as u:
                b=u.read(20_000_001)
            if len(b)>20_000_000:raise ValueError("ARCHIVED_CSV_TOO_LARGE")
            return b
        except (HTTPError,URLError,TimeoutError,OSError) as e:
            last=str(e)
            if i==0:time.sleep(2)
    raise RuntimeError("ARCHIVE_EXACT_CSV_NOT_AVAILABLE "+str(last))

def numeric(s):
    if s is None or str(s).strip().lower() in ("","nan","null","none"):
        return None
    n=float(s)
    return n if math.isfinite(n) else None

def parse_btc(b):
    try:
        rd=csv.DictReader(io.StringIO(b.decode("utf-8-sig")))
    except UnicodeDecodeError:
        raise ValueError("NOT_UTF8_CSV")
    cols=rd.fieldnames or []
    k="time" if "time" in cols else "date" if "date" in cols else None
    expected=("CapMVRVCur","CapMrktCurUSD","CapRealUSD")
    if k is None or any(q not in cols for q in expected):
        raise ValueError("COIN_METRICS_MVRV_REQUIRED_COLUMNS_MISSING")
    rows={}
    for r in rd:
        day=(r.get(k) or "")[:10]
        date.fromisoformat(day)
        if day in rows:raise ValueError("DUPLICATE_ORIGINAL_ARCHIVE_DATE")
        rows[day]={q:numeric(r.get(q)) for q in expected}
    if len(rows)<3500:raise ValueError("TRUNCATED_ORIGINAL_CSV")
    return rows

def assess(sunday,source,available):
    d=date.fromisoformat(sunday)
    if d.weekday()!=6:raise ValueError("NOT_SUNDAY")
    decision=datetime.combine(d,datetime.min.time(),timezone.utc)
    if available>=decision:return None
    for off in range(2,8):
        obs=(d-timedelta(days=off)).isoformat()
        if obs not in source:continue
        row=source[obs]
        m=row["CapMVRVCur"];cap=row["CapMrktCurUSD"];real=row["CapRealUSD"]
        if any(x is None or x<=0 for x in (m,cap,real)):continue
        if not math.isclose(m,cap/real,rel_tol=0.000005,abs_tol=0.000005):continue
        return {"date":sunday,"observedUTCDate":obs,"ageDays":off,"MVRV":m,
                "ratioArithmeticVerified":True,"publicCaptureUTC":available.isoformat()}
    return None

def selftest():
    assert gitsha(b"hello\n")=="ce013625030ba8dba906f756967f9e9ca394464a"
    a={"2024-05-24":{"CapMVRVCur":1.5,"CapMrktCurUSD":150,"CapRealUSD":100}}
    c=dateutc("2024-05-25T01:53:26Z")
    assert assess("2024-05-26",a,c)["observedUTCDate"]=="2024-05-24"
    assert assess("2024-06-02",a,c) is None
    assert assess("2024-05-19",a,c) is None
    print("V818D2_SELFTEST_PASS",flush=True)

def main():
    specraw=PREREG.read_bytes()
    spec=json.loads(specraw)
    if spec["version"]!="8.18d2" or not spec["researchOnly"] or spec["tradeAuthorized"]:
        raise ValueError("PREREG_VERSION_GUARD_FAILED")
    s3=boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
        region_name="auto",aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"])
    bucket=os.environ["R2_BUCKET"]
    def parent(k):
        p=spec["parents"][k]
        raw=s3.get_object(Bucket=bucket,Key=p["key"])["Body"].read()
        if sha(raw)!=p["sha256"]:raise ValueError("PARENT_SHA_MISMATCH_"+k)
        return json.loads(raw)
    previous=parent("d1")
    c8=parent("c8")
    btc=parent("btc")
    panel=btc["weeklyPanel"]
    if len(panel)!=684 or len(c8["perSundayEvidence"])!=684:
        raise RuntimeError("ORIGINAL_684_PANEL_CHANGED")
    prevdates={r["date"] for r in c8["perSundayEvidence"] if r["publicGitHubForkMvrvEvidence"]}
    if len(prevdates)!=11:raise RuntimeError("INHERITED_11_PUBLIC_FORK_DATES_CHANGED")
    candidates=[r["detail"] for r in previous["results"]
                if r["source"]=="wayback" and r["detail"].get("captureTimestamp")==spec["captureTimestamp"]]
    if len(candidates)!=1:raise ValueError("PINNED_WAYBACK_CAPTURE_NOT_UNIQUE")
    rec=candidates[0]
    if rec.get("parsedContentStatus")!="VALID_MVRV_CSV" or not rec.get("archivedBodyAvailable"):
        raise ValueError("PRIOR_WAYBACK_VERIFIED_CSV_MISSING")
    raw=retrieve(rec["archiveURL"])
    if sha(raw)!=rec["bodySHA256"] or gitsha(raw)!=rec["gitBlobSHA1"]:
        raise ValueError("INDEPENDENT_ARCHIVE_BYTE_HASH_CHANGED")
    content=parse_btc(raw)
    capture=dateutc(spec["captureUTC"])
    expected=datetime.strptime(spec["captureTimestamp"],"%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
    if capture!=expected:raise ValueError("FROZEN_CAPTURE_TIMES_DIFFER")
    all_sundays=[r["date"] for r in panel]
    if all_sundays!=sorted(all_sundays) or len(set(all_sundays))!=684:
        raise ValueError("ORIGINAL_PANEL_DATES_CHANGED")
    evals=[assess(d,content,capture) for d in all_sundays]
    found=[r for r in evals if r is not None]
    new=[r for r in found if r["date"] not in prevdates]
    missing=[t for t in spec["frozenEvaluation"]["calendarCheckDates"] if t not in all_sundays]
    resultstatus="INDEPENDENT_ARCHIVED_CSV_NUMERIC_ASOF_WEEK_CONFIRMED" if new else "WAYBACK_CSV_VALID_NO_NEW_PANEL_ASOF"
    report={
        "version":"8.18d2","status":resultstatus,"researchOnly":True,"tradeAuthorized":False,
        "prereg":{"path":str(PREREG.relative_to(ROOT)),"sha256":sha(specraw)},
        "pinnedParents":spec["parents"],
        "original684WeeksPreserved":True,
        "archivedCSV":{"captureUTC":spec["captureUTC"],"url":rec["archiveURL"],
            "SHA256":sha(raw),"gitBlobSHA1":gitsha(raw),"bytes":len(raw),
            "rows":len(content),"firstObservation":min(content),"lastObservation":max(content)},
        "previousIndependentGitHubForkWitnesses":11,
        "verifiedArchivedIndependentCSVAsOfRows":found,
        "newIndependentWaybackNumericWitnesses":new,
        "totalIndependentWitnessDateUnion":len(prevdates|{r["date"] for r in new}),
        "explicitCheckSundaysOutside684":missing,
        "originalProviderFirstPublicationClockVerified":False,
        "scientificInterpretation":[
            "The Wayback capture proves this archived CSV body existed no later than its independent capture timestamp.",
            "Only numerical MVRV older than two days and no older than seven days at the specific Sunday decision time can qualify.",
            "This is not proof of original Coin Metrics daily first publication time, nor an independent predictive-performance test.",
            "MVRV values on dates years before the capture are retrospective within the capture and NOT proven contemporaneously available.",
            "No BTC return outcomes, risk limits, trade orders or portfolio accounting were changed."
        ],
        "portfolioWriteback":spec["portfolioWriteback"]}
    out=Path("btci_v818d2_reports");out.mkdir(exist_ok=True)
    data=(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+"\n").encode()
    (out/"wayback_mvrv_2024_684_asof_FULL.json").write_bytes(data)
    prefix="research/btci/v8.18d2/runs/{}-{}/".format(os.environ["GITHUB_RUN_ID"],os.getenv("GITHUB_RUN_ATTEMPT","1"))
    def write(name,data):
        key=prefix+name
        dig=sha(data)
        s3.put_object(Bucket=bucket,Key=key,Body=data,ContentType="application/json",
            Metadata={"sha256":dig,"research-only":"true"})
        read=s3.get_object(Bucket=bucket,Key=key)["Body"].read()
        if sha(read)!=dig:raise RuntimeError("R2_SHA_MISMATCH")
        return {"key":key,"sha256":dig,"bytes":len(data)}
    row=write("wayback_mvrv_2024_684_asof_FULL.json",data)
    manifest=write("manifest.json",(json.dumps({"version":"8.18d2","status":resultstatus,
        "researchOnly":True,"report":row,"preregSHA256":sha(specraw),
        "noPortfolioWriteback":True},ensure_ascii=False,indent=2)+"\n").encode())
    summary={
        "status":resultstatus,"captureDate":"2024-05-25",
        "fileLastObservation":max(content),"checkedSundays":684,
        "eligibleSundays":[r["date"] for r in found],
        "newDates":[r["date"] for r in new],
        "newValues":[{"date":r["date"],"observed":r["observedUTCDate"],"MVRV":r["MVRV"]} for r in new],
        "missingCalendarCheckDates":missing,"priorCount":11,
        "newTotal":report["totalIndependentWitnessDateUnion"],
        "providerReleaseClockVerified":False,
        "reportSha256":row["sha256"],"manifestSha256":manifest["sha256"],"prefix":prefix}
    (out/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n")
    print("V818D2_RESULT "+json.dumps(summary,ensure_ascii=False),flush=True)
if __name__=="__main__":
    if "--self-test" in sys.argv:selftest()
    else:main()
