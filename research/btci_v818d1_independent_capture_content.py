#!/usr/bin/env python3
"""BTCI v8.18d1: independently archived CSV-body availability, not original Coin Metrics publication-time proof."""
import csv
import hashlib
import io
import json
import math
import os
import sys
import time
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import boto3

ROOT=Path(__file__).resolve().parents[1]
SPEC=ROOT/"research/btci_v818d1_independent_capture_content_prereg_2026-10-19.json"

def digest(b):
    return hashlib.sha256(b).hexdigest()

def git_blob(b):
    return hashlib.sha1(b"blob "+str(len(b)).encode()+b"\0"+b).hexdigest()

def stamp(s):
    return datetime.fromisoformat(str(s).replace("Z","+00:00"))

def retrieve(url,cap=20_000_000):
    err=None
    for attempt in range(2):
        try:
            q=Request(url,headers={"User-Agent":"BTCI-Independent-Historic-Archive/1.0","Accept":"*/*"})
            with urlopen(q,timeout=30) as r:
                body=r.read(cap+1)
                ctype=r.headers.get("Content-Type","")
                actual=r.geturl()
            if len(body)>cap:raise ValueError("ARCHIVE_BODY_EXCEEDS_CAP")
            return {"ok":True,"body":body,"contentType":ctype,"resolvedURL":actual,"error":None}
        except (HTTPError,URLError,TimeoutError,ValueError,OSError) as e:
            err=type(e).__name__+":"+str(e)[:250]
            if isinstance(e,HTTPError) and e.code in (400,401,403,404,429):break
            if attempt==0:time.sleep(2)
    return {"ok":False,"body":None,"error":err}

def parse_csv_fixed(b,targets):
    try:
        reader=csv.DictReader(io.StringIO(b.decode("utf-8-sig")))
        fields=reader.fieldnames or []
    except (UnicodeDecodeError,csv.Error):
        return {"status":"BODY_NOT_UTF8_CSV"}
    dk="time" if "time" in fields else "date" if "date" in fields else None
    required=("CapMVRVCur","CapRealUSD","CapMrktCurUSD")
    if not dk or not all(k in fields for k in required):
        return {"status":"BODY_NOT_COINMETRICS_MVRV_CSV","fieldsPreview":fields[:8]}
    dates=set()
    for day in targets:
        root=date.fromisoformat(day)
        for offset in range(2,8):
            dates.add((root-timedelta(days=offset)).isoformat())
    sample={}
    n=0
    try:
        for row in reader:
            n+=1
            d=(row.get(dk) or "")[:10]
            if d not in dates:continue
            try:
                a=float(row["CapMVRVCur"])
                market=float(row["CapMrktCurUSD"])
                realized=float(row["CapRealUSD"])
            except (ValueError,TypeError):
                continue
            if (min(a,market,realized)>0 and all(math.isfinite(x) for x in (a,market,realized))
                    and math.isclose(a,market/realized,rel_tol=0.000005,abs_tol=0.000005)):
                sample[d]={"mvrv":a,"ratioArithmeticVerified":True}
    except csv.Error:
        return {"status":"CSV_PARSE_ERROR"}
    return {"status":"VALID_MVRV_CSV" if n>3500 else "TRUNCATED_MVRV_CSV",
            "rows":n,"matchingFixedOldDateRows":sample}

def swh_snapshot(visit):
    snap=visit["snapshot"]
    u="https://archive.softwareheritage.org/api/1/snapshot/"+snap+"/"
    ret=retrieve(u,cap=1_800_000)
    out={"visitDate":visit["date"],"visitStatus":visit["status"],
         "snapshotId":snap,"lookupURL":u,"httpOrNetworkOk":ret["ok"],
         "error":ret["error"],"masterRevision":None,
         "actualCSVFileBytesVerified":False}
    if ret["ok"]:
        out["responseSHA256"]=digest(ret["body"])
        try:
            obj=json.loads(ret["body"])
            branches=obj.get("branches") or {}
            ref=branches.get("refs/heads/master",{})
            if isinstance(ref,dict):
                out["masterRevision"]=ref.get("target")
                out["masterTargetType"]=ref.get("target_type")
        except (ValueError,AttributeError):
            out["error"]="UNPARSEABLE_SOFTWARE_HERITAGE_SNAPSHOT"
    return out

def wayback_body(row,targets,maximum=20_000_000):
    iso=row["timestamp"]
    origin=row["original"]
    u="https://web.archive.org/web/"+iso+"id_/"+origin
    if not origin.startswith("http"):
        u="https://web.archive.org/web/"+iso+"id_/https://"+origin
    ret=retrieve(u,cap=maximum)
    out={"captureTimestamp":iso,"original":origin,"archiveURL":u,
         "archivedBodyAvailable":ret["ok"],"error":ret["error"],
         "verifiedNumericRowCount":0,"newEligibleWeekDates":[],
         "originalCoinMetricsFirstSeenClockKnown":False}
    if ret["ok"]:
        body=ret["body"]
        out.update({"bodySHA256":digest(body),"gitBlobSHA1":git_blob(body),
                    "bytes":len(body),"responseContentType":ret["contentType"]})
        check=parse_csv_fixed(body,targets)
        out["parsedContentStatus"]=check["status"]
        values=check.get("matchingFixedOldDateRows",{})
        out["verifiedNumericRowCount"]=len(values)
        capture=datetime.strptime(iso,"%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
        for sunday in targets:
            decision=datetime.combine(date.fromisoformat(sunday),datetime.min.time(),timezone.utc)
            if capture>=decision:continue
            if any((date.fromisoformat(sunday)-timedelta(days=g)).isoformat() in values for g in range(2,8)):
                out["newEligibleWeekDates"].append(sunday)
        out["sampleOldValues"]={k:v for k,v in sorted(values.items())[:8]}
    return out

def selftest():
    assert git_blob(b"hello\n")=="ce013625030ba8dba906f756967f9e9ca394464a"
    test=b"time,CapMVRVCur,CapRealUSD,CapMrktCurUSD\n2020-07-31T00:00:00Z,2,10,20\n"
    r=parse_csv_fixed(test,["2020-08-02"])
    assert r["status"]=="TRUNCATED_MVRV_CSV" and r["matchingFixedOldDateRows"]["2020-07-31"]["mvrv"]==2
    print("V818D1_SELFTEST_PASS",flush=True)

def main():
    sraw=SPEC.read_bytes()
    p=json.loads(sraw)
    if p["version"]!="8.18d1" or p["scope"]!="RESEARCH_ONLY" or not p["noTradeAuthority"]:
        raise RuntimeError("PREREG_INVALID")
    s3=boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
    bucket=os.environ["R2_BUCKET"]
    def pinned(k):
        v=p["parents"][k]
        raw=s3.get_object(Bucket=bucket,Key=v["key"])["Body"].read()
        if digest(raw)!=v["sha256"]:raise ValueError("PARENT_SHA_MISMATCH_"+k)
        return json.loads(raw)
    prior=pinned("d0")
    old=pinned("c8")
    panel=pinned("btc")["weeklyPanel"]
    if len(panel)!=684 or len(prior["sources"])!=6 or len(old["allWitnessDates"])!=11:
        raise RuntimeError("PARENT_INVARIANTS_FAILED")
    paneldates={x["date"] for x in panel}
    targets=p["frozenTargets"]
    if any(day not in paneldates for day in targets):
        raise RuntimeError("FROZEN_DATES_NOT_IN_PANEL")
    visits=[]
    cdx=[]
    for source in prior["sources"]:
        if source["archive"]=="software_heritage" and source["origin"]=="https://github.com/coinmetrics/data":
            for v in source.get("parsedVisits",[]):
                if v.get("snapshot") and v.get("date") and "2019"<=v["date"][:4]<="2025":
                    visits.append(v)
        elif source["archive"]=="wayback_cdx" and "coinmetrics/data" in source.get("target",""):
            cdx.extend(source.get("parsedCaptures",[]))
    visits.sort(key=lambda v:v["date"])
    cdx.sort(key=lambda v:v["timestamp"])
    maxS=p["exactVerification"]["limits"]["maxSwhSnapshots"]
    maxC=p["exactVerification"]["limits"]["maxWaybackCsvBodies"]
    selectedVisits=visits[:maxS]
    selectedCaptures=cdx[:maxC]
    records=[]
    work=[("swh",v) for v in selectedVisits]+[("wayback",v) for v in selectedCaptures]
    with ThreadPoolExecutor(max_workers=3) as ex:
        futures={ex.submit(swh_snapshot,v) if kind=="swh" else
                 ex.submit(wayback_body,v,targets,p["exactVerification"]["limits"]["maxCSVBytes"]):(kind,v)
                 for kind,v in work}
        for f in as_completed(futures):
            kind,v=futures[f]
            try:
                detail=f.result()
            except Exception as e:
                detail={"error":type(e).__name__+":"+str(e)[:250],
                        "archivedBodyAvailable":False}
            records.append({"source":kind,"detail":detail})
            print("V818D1_SOURCE "+json.dumps({
                "type":kind,"time":v.get("date",v.get("timestamp")),
                "ok":detail.get("httpOrNetworkOk",detail.get("archivedBodyAvailable",False)),
                "status":detail.get("parsedContentStatus"),
                "verifiedRows":detail.get("verifiedNumericRowCount",0),
                "newWeeks":detail.get("newEligibleWeekDates",[]),
                "error":detail.get("error")},ensure_ascii=False),flush=True)
    records.sort(key=lambda x:(x["source"],str(x["detail"].get("captureTimestamp",x["detail"].get("visitDate","")))))
    dated={x for r in records if r["source"]=="wayback" for x in r["detail"].get("newEligibleWeekDates",[])}
    errors=sum(bool(r["detail"].get("error")) for r in records)
    status="ARCHIVED_NUMERIC_CAPTURE_CONFIRMED" if dated else "NO_NEW_CONTENT_MATCH_FROM_FROZEN_ARCHIVE_PROBES"
    report={
        "version":"8.18d1","status":status,"researchOnly":True,"tradeAuthorized":False,
        "prereg":{"path":str(SPEC.relative_to(ROOT)),"sha256":digest(sraw)},
        "pinnedParents":p["parents"],
        "original684WeeksUnchanged":True,"priorPublicForkAsOfWitnesses":11,
        "originalCoinMetricsFirstPublicationClockVerified":0,
        "swhSourceVisitCandidates":len(visits),"cdxBtcFileCaptureCandidates":len(cdx),
        "testedSwhSnapshots":len(selectedVisits),"testedWaybackBodies":len(selectedCaptures),
        "results":records,
        "newIndependentArchivedContentEligibleWeeks":sorted(dated),
        "failedSourceTests":errors,
        "limitations":[
            "A Software Heritage Git revision target without verified BTC CSV file bytes remains metadata-level only.",
            "A CDX capture digest alone cannot establish exact Coin Metrics MVRV content or original provider release time.",
            "A dated independent archive body must precede Sunday and contain internally consistent MVRV observation rows.",
            "Zero new matches does not prove no historical public MVRV data existed.",
            "No model training, BTC outcomes, trading signals, live account or production modification."
        ],"portfolioWriteback":p["portfolioWriteback"]
    }
    folder=Path("btci_v818d1_reports");folder.mkdir(exist_ok=True)
    raw=(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+"\n").encode()
    (folder/"archive_exact_content_audit_FULL.json").write_bytes(raw)
    prefix="research/btci/v8.18d1/runs/{}-{}/".format(os.environ["GITHUB_RUN_ID"],os.getenv("GITHUB_RUN_ATTEMPT","1"))
    def store(name,payload):
        key=prefix+name;d=digest(payload)
        s3.put_object(Bucket=bucket,Key=key,Body=payload,ContentType="application/json",
                      Metadata={"sha256":d,"research-only":"true"})
        if digest(s3.get_object(Bucket=bucket,Key=key)["Body"].read())!=d:
            raise RuntimeError("R2_SHA_READBACK_FAIL")
        return {"key":key,"sha256":d,"bytes":len(payload)}
    saved=store("archive_exact_content_audit_FULL.json",raw)
    manifest=store("manifest.json",(json.dumps({"version":"8.18d1","status":status,
        "researchOnly":True,"report":saved,"preregSha256":digest(sraw),
        "noPortfolioChanges":True},ensure_ascii=False,indent=2)+"\n").encode())
    summary={"status":status,"SWHVisitsConsidered":len(visits),"CDXFileCapturesConsidered":len(cdx),
        "snapshotsTested":len(selectedVisits),"bodiesTested":len(selectedCaptures),
        "newContentMatchedDates":sorted(dated),"sourceErrors":errors,
        "publicForkAsOfWitnessesUnchanged":11,"reportSha256":saved["sha256"],
        "manifestSha256":manifest["sha256"],"prefix":prefix}
    (folder/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n")
    print("V818D1_RESULT "+json.dumps(summary,ensure_ascii=False),flush=True)

if __name__=="__main__":
    if "--self-test" in sys.argv:
        selftest()
    else:
        main()
