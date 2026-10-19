#!/usr/bin/env python3
"""BTCI v8.18d0: read-only independent historical archive index feasibility, RESEARCH_ONLY."""
import hashlib
import json
import os
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
import boto3

ROOT=Path(__file__).resolve().parents[1]
SPEC=ROOT/"research/btci_v818d0_independent_web_archive_probe_prereg_2026-10-19.json"

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def get_json(url,tries=2):
    errors=[]
    for i in range(tries):
        req=Request(url,headers={
            "User-Agent":"BTCI-Research-Independent-Archive-Feasibility/1.0 (research-only)",
            "Accept":"application/json"})
        try:
            with urlopen(req,timeout=25) as resp:
                code=resp.status
                raw=resp.read(1_500_001)
            if len(raw)>1_500_000:
                raise RuntimeError("SOURCE_RESPONSE_TOO_BIG")
            value=json.loads(raw)
            return {"http":code,"rawSHA256":sha(raw),"payload":value,"error":None}
        except HTTPError as e:
            errors.append("HTTP_"+str(e.code))
            if e.code in (400,401,403,404):
                break
        except (URLError,TimeoutError,OSError,ValueError,RuntimeError) as e:
            errors.append(type(e).__name__+":"+str(e)[:180])
        if i+1<tries:
            time.sleep(1+i)
    return {"http":None,"rawSHA256":None,"payload":None,"error":" | ".join(errors)}

def capture_swh(origin,spec):
    enc=quote(origin,safe="") 
    u=spec["sourceA"]["apiBase"]+"origin/"+enc+"/visits/?"+urlencode({"per_page":spec["sourceA"]["maxResultsPerOrigin"]})
    v=get_json(u)
    out={"archive":"software_heritage","origin":origin,"requestedURL":u,
         "http":v["http"],"indexSHA256":v["rawSHA256"],"error":v["error"],
         "parsedVisits":[],"valueMatchedToGitBlob":False}
    if v["payload"] is not None:
        data=v["payload"]
        rows=data if isinstance(data,list) else data.get("results",data.get("visits",[])) if isinstance(data,dict) else []
        if not isinstance(rows,list):
            out["error"]="UNEXPECTED_SWH_PAYLOAD_STRUCTURE"
        else:
            for visit in rows[:spec["sourceA"]["maxResultsPerOrigin"]]:
                if not isinstance(visit,dict):
                    continue
                out["parsedVisits"].append({k:visit.get(k) for k in ("date","visit","status","snapshot","type")})
    out["visitCountSampled"]=len(out["parsedVisits"])
    return out

def capture_cdx(target,spec):
    params={
        "url":target,"output":"json","from":str(spec["sourceB"]["fromYear"]),
        "to":str(spec["sourceB"]["toYear"]),
        "filter":"statuscode:200",
        "fl":"timestamp,original,statuscode,digest",
        "collapse":"timestamp:4",
        "limit":str(spec["sourceB"]["maxCapturesPerUrl"])
    }
    u=spec["sourceB"]["apiBase"]+"?"+urlencode(params)
    v=get_json(u)
    out={"archive":"wayback_cdx","target":target,"requestedURL":u,
        "http":v["http"],"indexSHA256":v["rawSHA256"],"error":v["error"],
        "parsedCaptures":[],"valueMatchedToGitBlob":False}
    if v["payload"] is not None:
        rows=v["payload"]
        if isinstance(rows,list) and rows and isinstance(rows[0],list):
            head=rows[0]
            if all(k in head for k in ("timestamp","original","statuscode","digest")):
                out["parsedCaptures"]=[
                    {k:line[head.index(k)] if head.index(k)<len(line) else None for k in head}
                    for line in rows[1:spec["sourceB"]["maxCapturesPerUrl"]+1]
                    if isinstance(line,list)]
            else:
                out["error"]="CDX_HEADER_MISSING_EXPECTED_COLUMNS"
        elif isinstance(rows,list) and len(rows)==0:
            out["parsedCaptures"]=[]
        else:
            out["error"]="UNEXPECTED_CDX_JSON_STRUCTURE"
    out["captureCountSampled"]=len(out["parsedCaptures"])
    return out

def selftest():
    assert sha(b"test")==hashlib.sha256(b"test").hexdigest()
    assert quote("https://github.com/coinmetrics/data",safe="")=="https%3A%2F%2Fgithub.com%2Fcoinmetrics%2Fdata"
    assert date.fromisoformat("2020-08-02").weekday()==6
    print("V818D0_SELFTEST_PASS",flush=True)

def main():
    rawspec=SPEC.read_bytes()
    spec=json.loads(rawspec)
    if spec["version"]!="8.18d0" or spec["scope"]!="RESEARCH_ONLY" or spec["noTradeAuthority"] is not True:
        raise RuntimeError("PREREG_GUARD_FAILED")
    s3=boto3.client("s3",
        endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
        region_name="auto",aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"])
    bucket=os.environ["R2_BUCKET"]
    prior={}
    for label,entry in spec["parents"].items():
        raw=s3.get_object(Bucket=bucket,Key=entry["key"])["Body"].read()
        if sha(raw)!=entry["sha256"]:
            raise RuntimeError("PARENT_SHA_CHANGED_"+label)
        prior[label]=json.loads(raw)
    panel=prior["btc"]["weeklyPanel"]
    if len(panel)!=684 or len({x["date"] for x in panel})!=684:
        raise RuntimeError("ORIGINAL_BTCI_684_PANEL_CHANGED")
    old=prior["c8"]
    if len(old["allWitnessDates"])!=11:
        raise RuntimeError("ORIGINAL_C8_11_WITNESSES_CHANGED")
    if prior["c9"]["quarterly26SampledSundays"]!=26:
        raise RuntimeError("C9_26_SAMPLES_CHANGED")
    if not all(t in {r["date"] for r in panel} for t in spec["targets"]):
        raise RuntimeError("FROZEN_TARGETS_NOT_IN_PARENT_684")
    work=[]
    for origin in spec["sourceA"]["origins"]:
        work.append(("swh",origin))
    for target in spec["sourceB"]["urls"]:
        work.append(("cdx",target))
    results=[]
    with ThreadPoolExecutor(max_workers=3) as pool:
        future={pool.submit(capture_swh,v,spec) if category=="swh" else
            pool.submit(capture_cdx,v,spec):(category,v) for category,v in work}
        for f in as_completed(future):
            category,origin=future[f]
            try:
                r=f.result()
            except Exception as ex:
                r={"archive":"software_heritage" if category=="swh" else "wayback_cdx",
                   "target":origin,"error":type(ex).__name__+":"+str(ex)[:250],
                   "http":None,"parsedCaptures":[],"parsedVisits":[],"valueMatchedToGitBlob":False}
            results.append(r)
            print("V818D0_SOURCE "+json.dumps({
                "type":r["archive"],"target":origin,"http":r["http"],
                "visitCount":len(r.get("parsedVisits",[])),
                "captureCount":len(r.get("parsedCaptures",[])),
                "error":r["error"]},ensure_ascii=False),flush=True)
    results.sort(key=lambda r:(r["archive"],r.get("origin",r.get("target",""))))
    visits=sum(len(r.get("parsedVisits",[])) for r in results)
    captures=sum(len(r.get("parsedCaptures",[])) for r in results)
    failed=sum(r.get("error") is not None for r in results)
    status=("INDEPENDENT_ARCHIVE_INDEX_RECORDS_FOUND_NOT_EXACT_FILE_PROOF"
            if visits+captures>0 else
            "INDEPENDENT_ARCHIVE_SOURCE_UNAVAILABLE_OR_EMPTY")
    report={
        "version":"8.18d0","status":status,"researchOnly":True,"tradeAuthorized":False,
        "prereg":{"path":str(SPEC.relative_to(ROOT)),"sha256":sha(rawspec)},
        "pinnedParentSources":spec["parents"],"original684PanelUnchanged":True,
        "frozenTargets":spec["targets"],"sources":results,
        "softwareHeritageVisitsSampled":visits,"waybackCapturesSampled":captures,
        "sourceFailures":failed,
        "independentExactContentHashMatches":0,
        "originalProviderDailyPublicationClockVerified":0,
        "priorIndependentGitHubForkAsOfWitnessesUnchanged":11,
        "asOfWitnessesUpgraded":0,
        "scientificInterpretation":[
            "SWH visit metadata or CDX capture metadata without exact immutable CSV content correspondence do not confirm historic daily MVRV values.",
            "Any historic Git committer timestamp by itself is weaker than independent public hosting evidence.",
            "API 403/404/timeout and empty indexes are sources not available to this audit, not evidence that no archive exists.",
            "No claim of forecasting accuracy, PIT expansion, broad 2020-2025 data coverage, or tradable signal.",
            "No BTC return targets, 684-week cohort values, model criteria or trading settings changed."
        ],
        "portfolioWriteback":spec["portfolioWriteback"]
    }
    folder=Path("btci_v818d0_reports");folder.mkdir(exist_ok=True)
    raw=(json.dumps(report,ensure_ascii=False,indent=2)+"\n").encode()
    (folder/"independent_archives_index_audit_FULL.json").write_bytes(raw)
    prefix="research/btci/v8.18d0/runs/{}-{}/".format(os.environ["GITHUB_RUN_ID"],os.environ.get("GITHUB_RUN_ATTEMPT","1"))
    def put(name,data):
        key=prefix+name
        dg=sha(data)
        s3.put_object(Bucket=bucket,Key=key,Body=data,ContentType="application/json",
            Metadata={"sha256":dg,"research-only":"true"})
        check=s3.get_object(Bucket=bucket,Key=key)["Body"].read()
        if sha(check)!=dg:
            raise RuntimeError("R2_READBACK_MISMATCH")
        return {"key":key,"sha256":dg,"bytes":len(data)}
    saved=put("independent_archives_index_audit_FULL.json",raw)
    manifest=put("manifest.json",(json.dumps({
        "version":"8.18d0","status":status,"researchOnly":True,
        "report":saved,"preregSha256":sha(rawspec),
        "previousElevenPreserved":True,
        "noPortfolioWriteback":True},ensure_ascii=False,indent=2)+"\n").encode())
    summary={"status":status,"sources":len(results),
        "visits":visits,"captures":captures,"sourceErrors":failed,
        "exactFileMatches":0,"previousAsOfWitnesses":11,"newAsOfWitnesses":0,
        "reportSha256":saved["sha256"],"manifestSha256":manifest["sha256"],"prefix":prefix}
    (folder/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n")
    print("V818D0_RESULT "+json.dumps(summary,ensure_ascii=False),flush=True)

if __name__=="__main__":
    if "--self-test" in sys.argv:
        selftest()
    else:
        main()
