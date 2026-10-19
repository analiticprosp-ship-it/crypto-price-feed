#!/usr/bin/env python3
"""BTCI v8.18c raw Bitcoin onchain source discovery only.
Coin Metrics current historical reconstructions are NOT point-in-time forecasts.
"""
import datetime as dt,hashlib,json,os,time,urllib.parse,urllib.request,urllib.error
from pathlib import Path
import boto3
ROOT=Path(__file__).resolve().parents[1]
PRE="research/btci_v818c_onchain_pit_source_audit_prereg_2026-10-19.json"
BASE="https://community-api.coinmetrics.io/v4/"
def sha(x):return hashlib.sha256(x).hexdigest()
def cloud():
 return boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
 aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
 aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
def put(s,b,key,raw,content_type="application/json"):
 blob=raw if isinstance(raw,bytes) else json.dumps(raw,ensure_ascii=False,indent=2).encode()
 h=sha(blob)
 s.put_object(Bucket=b,Key=key,Body=blob,ContentType=content_type,
 Metadata={"sha256":h,"research-only":"true"})
 if sha(s.get_object(Bucket=b,Key=key)["Body"].read())!=h:
  raise SystemExit("V818C_R2_READBACK_MISMATCH")
 return {"key":key,"sha256":h,"bytes":len(blob)}
def req(path,args,size=1500000):
 params=urllib.parse.urlencode(args)
 url=BASE+path+"?"+params
 for attempt in range(3):
  try:
   rq=urllib.request.Request(url,headers={"Accept":"application/json","User-Agent":"BTCI onchain source audit 8.18c"})
   with urllib.request.urlopen(rq,timeout=35) as response:raw=response.read(size+1)
   if len(raw)>size:raise ValueError("RESPONSE_TOO_BIG")
   obj=json.loads(raw)
   if "data" not in obj:raise ValueError("API_MISSING_DATA")
   return {"status":"DATA_RETURNED","responseSize":len(raw)},raw,obj
  except urllib.error.HTTPError as e:
   if e.code in (429,500,502,503) and attempt<2:
    time.sleep(4*(attempt+1));continue
   return {"status":"HTTP_DENIED_OR_UNAVAILABLE","code":e.code},None,None
  except Exception as e:
   return {"status":"SOURCE_ERROR","message":type(e).__name__+":"+str(e)[:180]},None,None
 return {"status":"RETRIES_EXHAUSTED"},None,None

def main():
 prraw=(ROOT/PRE).read_bytes();p=json.loads(prraw)
 if p["version"]!="8.18c-source":raise SystemExit("V818C_PREREG_CHANGED")
 s=cloud();bucket=os.environ["R2_BUCKET"]
 prefix=f"research/btci/v8.18c/runs/{os.environ['GITHUB_RUN_ID']}-{os.environ.get('GITHUB_RUN_ATTEMPT','1')}/"
 catalogStatus,catalogRaw,catalog=req("catalog/asset-metrics",{"assets":"btc"},3500000)
 if catalogRaw:
  archiveCatalog=put(s,bucket,prefix+"source/coinmetrics_btc_catalog.json",catalogRaw)
 else:archiveCatalog=None
 found=[]
 if catalog and isinstance(catalog.get("data"),list):
  for a in catalog["data"]:
   if a.get("asset")=="btc":
    for met in a.get("metrics",[]):
     if isinstance(met,str):found.append(met)
     elif isinstance(met,dict):found.append(met.get("metric") or met.get("metric_id") or "")
 found=set(found)
 outcome={}
 for met in p["proposedMetrics"]:
  available=met in found
  rows=[];sampled=[]
  if available:
   for period in p["historicalWindows"]:
    start,end=period.split("..")
    status,raw,obj=req("timeseries/asset-metrics",{
      "assets":"btc","metrics":met,"frequency":"1d",
      "start_time":start,"end_time":end,"page_size":200})
    archive=None
    if raw:
     archive=put(s,bucket,prefix+f"source/{met}_{start}.json",raw)
     rows_observed=[x for x in obj["data"] if isinstance(x,dict) and x.get("time","")[:10]>=start and x.get("time","")[:10]<=end]
     data_points=len(rows_observed)
     if data_points:
      if met not in rows_observed[0]:raise SystemExit("API_METRIC_FIELD_MISSING")
     sample={"period":period,"status":status["status"],"n":data_points,
      "first":rows_observed[0].get("time") if rows_observed else None,
      "last":rows_observed[-1].get("time") if rows_observed else None,
      "archive":archive}
    else:
     sample={"period":period,"status":status["status"],"error":status.get("code") or status.get("message")}
    sampled.append(sample)
    time.sleep(0.75)
  outcome[met]={"inOfficialCommunityCatalog":available,
   "latestCatalogMetricCount":len(found),"historicalSamplePeriods":sampled,
   "realtimeVintageAuthenticated":False}
  print("V818C_METRIC",met,"catalog",available,
    "windows",len(sampled),"rows",[x.get("n",0) for x in sampled],flush=True)
 report={"version":"8.18c-source","researchOnly":True,
  "status":"ONCHAIN_COMMUNITY_SOURCE_DISCOVERY_NO_POINT_IN_TIME_CERTIFICATION",
  "preregistration":{"path":PRE,"sha256":sha(prraw)},
  "catalog":{"status":catalogStatus,"archive":archiveCatalog,"metricCount":len(found)},
  "onchainFactors":outcome,
  "historicalPITStatus":"NOT_VERIFIED_AND_MUST_NOT_USE_FOR_ASOF_2012_TRADING_SIGNAL",
  "glassnodePIT":"AUTHORIZED_API_ACCESS_NOT_VERIFIED; DOCUMENTED_POINT_IN_TIME_ENDPOINTS_NOT_FETCHED",
  "interpretation":["Historical observed date is not a timestamp proving metric value was published then.",
    "Coin Metrics realized capitalization was discussed/introduced circa 2018, so current 2012 reconstruction does not imply 2012 public availability.",
    "On-chain raw blockchain facts and backfilled derived market-cost metrics must be distinguished.",
    "Samples check source availability only and are not predictions; no BTC future outcome analysis.",
    "No historical data rights or quota bypass attempted."],
  "changes":{"Spot":False,"Futures":False,"NAV":False,"PnL":False,
   "capital":False,"reserve":False,"MASTER":False,"Detector":False,"riskLimits":False}}
 folder=Path("btci_v818c_reports");folder.mkdir(exist_ok=True)
 raw=json.dumps(report,ensure_ascii=False,indent=2).encode()
 (folder/"onchain_source_audit.json").write_bytes(raw)
 rh=put(s,bucket,prefix+"onchain_source_audit.json",raw)
 mh=put(s,bucket,prefix+"manifest.json",{"version":"8.18c-source","researchOnly":True,
  "reportSha256":rh["sha256"],"preregSha256":sha(prraw)})
 summary={"status":"V818C_SOURCE_AUDIT_R2_READBACK_PASS","prefix":prefix,
   "reportSha256":rh["sha256"],"manifestSha256":mh["sha256"],
   "catalogStatus":catalogStatus,"metricReport":{
     m:{"catalog":v["inOfficialCommunityCatalog"],
      "periods":[{"period":q["period"],"n":q.get("n"),"status":q["status"]} for q in v["historicalSamplePeriods"]]}
     for m,v in outcome.items()}}
 (folder/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2))
 print("V818C_RESULT "+json.dumps(summary,ensure_ascii=False),flush=True)
if __name__=="__main__":main()
