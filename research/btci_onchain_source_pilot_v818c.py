#!/usr/bin/env python3
"""BTCI v8.18c. Coin Metrics BTC realized cap/MVRV availability only.
HISTORICAL VALUES ARE RETROSPECTIVE RECONSTRUCTIONS, NOT POINT-IN-TIME VINTAGES.
"""
import datetime as dt,hashlib,json,math,os,urllib.parse,urllib.request,urllib.error
from pathlib import Path
import boto3
ROOT=Path(__file__).resolve().parents[1]
PRE="research/btci_v818c_onchain_vintage_integrity_prereg_2026-10-19.json"
def sha(raw):return hashlib.sha256(raw).hexdigest()
def client():
 return boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
 aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
def put(s,b,key,raw,typ="application/json"):
 if not isinstance(raw,bytes):raw=json.dumps(raw,ensure_ascii=False,indent=2).encode()
 h=sha(raw)
 s.put_object(Bucket=b,Key=key,Body=raw,ContentType=typ,Metadata={"sha256":h,"research-only":"true"})
 if sha(s.get_object(Bucket=b,Key=key)["Body"].read())!=h:raise SystemExit("V818C_R2_READBACK_FAIL")
 return h
def get_one(d):
 q={"assets":"btc","metrics":"CapRealUSD,CapMVRVCur",
    "frequency":"1d","start_time":d,"end_time":d,
    "page_size":"1000"}
 url="https://community-api.coinmetrics.io/v4/timeseries/asset-metrics?"+urllib.parse.urlencode(q)
 req=urllib.request.Request(url,headers={"User-Agent":"BTCI historical community noncommercial research 8.18c","Accept":"application/json"})
 try:
  with urllib.request.urlopen(req,timeout=35) as r:
   raw=r.read(250001);status=r.status
  if len(raw)>250000:raise ValueError("SOURCE_TOO_LARGE")
  obj=json.loads(raw)
  obs=[x for x in obj.get("data",[]) if x.get("asset")=="btc" and x.get("time","")[:10]==d]
  if len(obs)!=1:raise ValueError("NO_UNIQUE_DAILY_DATA_AT_DATE")
  values={}
  for id in ("CapRealUSD","CapMVRVCur"):
   v=obs[0].get(id)
   if v is None:values[id]=None
   else:
    n=float(v)
    if not math.isfinite(n) or n<=0:raise ValueError("INVALID_METRIC_VALUE")
    values[id]=n
  return {"date":d,"status":"HISTORICAL_BACKFILL_AVAILABLE_NOT_PIT",
   "httpStatus":status,"values":values,
   "PIT":"UNVERIFIED_ASOF_ORIGINAL_PUBLICATION",
   "rawSHA":sha(raw),"requiresOriginalVintageBeforeModelUse":True},raw
 except urllib.error.HTTPError as exc:
  return {"date":d,"status":"HTTP_ERROR","httpStatus":exc.code,"PIT":"UNVERIFIED"},None
 except Exception as exc:
  return {"date":d,"status":"SOURCE_NOT_VALIDATED","reason":type(exc).__name__+":"+str(exc)[:140],"PIT":"UNVERIFIED"},None
def main():
 raw=(ROOT/PRE).read_bytes();pr=json.loads(raw)
 if pr["version"]!="8.18c" or len(pr["testDates"])!=7:raise SystemExit("V818C_SPEC_CHANGED")
 s=client();bucket=os.environ["R2_BUCKET"]
 root=f"research/btci/v8.18c/runs/{os.environ.get('GITHUB_RUN_ID','manual')}-{os.environ.get('GITHUB_RUN_ATTEMPT','1')}/"
 entries=[]
 for d in pr["testDates"]:
  val,body=get_one(d)
  if body is not None:
   key=root+f"source/coinmetrics_btc_mvrv_realized_{d}.json"
   dig=put(s,bucket,key,body)
   val["r2Key"]=key
   if val["rawSHA"]!=dig:raise SystemExit("V818C_BODY_HASH_CHANGED")
  entries.append(val)
  print("V818C_SOURCE",d,val["status"],flush=True)
 report={"version":"8.18c","researchOnly":True,
   "status":"ONCHAIN_SOURCE_AVAILABILITY_ONLY_NOT_PIT",
   "prereg":{"path":PRE,"sha256":sha(raw)},
   "samples":entries,
   "fetched":sum(x["status"]=="HISTORICAL_BACKFILL_AVAILABLE_NOT_PIT" for x in entries),
   "vintageStatus":"PIT_NOT_VERIFIED",
   "preventSignalUse":True,
   "warnings":["Current historical CoinMetrics CapMVRVCur and CapRealUSD may have been reconstructed and revised since historic publication.",
    "A 2013 metric value retrievable today does not imply original observers in 2013 knew or could calculate it then.",
    "No BTC 13/26/52wk model scoring, no headline detection, no actual original publication snapshots, no trading.",
    "2018 origin and older periods require source provenance to avoid historical feature look-ahead."],
   "portfolioChanged":False}
 out=Path("btci_v818c_reports");out.mkdir(exist_ok=True)
 payload=json.dumps(report,ensure_ascii=False,indent=2).encode()
 (out/"onchain_source_audit.json").write_bytes(payload)
 h=put(s,bucket,root+"onchain_source_audit.json",payload)
 m=put(s,bucket,root+"manifest.json",{"version":"8.18c","researchOnly":True,
   "reportSha256":h,"preregSha256":sha(raw),"status":report["status"]})
 (out/"summary.json").write_text(json.dumps({"prefix":root,"reportSha256":h,"manifestSha256":m,
    "samples":entries},ensure_ascii=False,indent=2))
 print("V818C_RESULT "+json.dumps({"status":"V818C_SOURCE_AUDIT_R2_VERIFIED",
    "prefix":root,"sha256":h,"manifestSha256":m,"fetched":report["fetched"],
    "samples":entries},ensure_ascii=False),flush=True)
if __name__=="__main__":main()
