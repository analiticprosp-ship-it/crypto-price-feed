#!/usr/bin/env python3
"""BTCI v8.18a point-in-time availability (NOT a BTC forecast).
Probes genuine as-of historical FRED vintages of official Fed H15/H10 rates/USD.
"""
import datetime as dt,hashlib,json,math,os,urllib.parse,urllib.request,urllib.error,time
from pathlib import Path
import boto3
ROOT=Path(__file__).resolve().parents[1]
PRE="research/btci_v818a_independent_rate_dollar_source_prereg_2026-10-19.json"
PARENT=("research/btci/v8.17.1/runs/39212878778-1/full_historical_rise_fall.json",
"539bcc1817a2120287497c2814d0344aae5d62714b4f35a36f30c2425e5d3091")
def sha(b):return hashlib.sha256(b).hexdigest()
def day(x):return dt.date.fromisoformat(x)
def s3():
 return boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
   aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
def get(s,b,key,h):
 raw=s.get_object(Bucket=b,Key=key)["Body"].read()
 if sha(raw)!=h:raise SystemExit("V818A_PARENT_SOURCE_CHANGED")
 return json.loads(raw)
def put(s,b,key,raw,ctype="application/json"):
 if not isinstance(raw,bytes):raw=json.dumps(raw,ensure_ascii=False,indent=2).encode()
 h=sha(raw)
 s.put_object(Bucket=b,Key=key,Body=raw,ContentType=ctype,Metadata={"sha256":h,"research-only":"true"})
 if sha(s.get_object(Bucket=b,Key=key)["Body"].read())!=h:
  raise SystemExit("V818A_R2_SHA_REREAD_FAILED")
 return h
def probe(series,sunday,key):
 begin=day(sunday)-dt.timedelta(days=65)
 q={"series_id":series,"api_key":key,"file_type":"json","realtime_start":sunday,"realtime_end":sunday,
 "observation_start":begin.isoformat(),"observation_end":sunday,"limit":1000}
 url="https://api.stlouisfed.org/fred/series/observations?"+urllib.parse.urlencode(q)
 for attempt in range(4):
  try:
   req=urllib.request.Request(url,headers={"Accept":"application/json","User-Agent":"BTCI official vintage 8.18a"})
   with urllib.request.urlopen(req,timeout=40) as response:raw=response.read(500001)
   if len(raw)>500000:raise ValueError("API_RESPONSE_TOO_LONG")
   x=json.loads(raw)
   if x.get("realtime_start")!=sunday or x.get("realtime_end")!=sunday:
    raise ValueError("REALTIME_PERIOD_MISMATCH")
   data=[]
   for z in x.get("observations",[]):
    v=z.get("value")
    if v in (".",None,""):continue
    if z["date"]>sunday or z["realtime_start"]>sunday or z["realtime_end"]<sunday:
     raise ValueError("FUTURE_DATA_OR_UNKNOWN_REVISION")
    value=float(v)
    if not math.isfinite(value):raise ValueError("NONFINITE")
    data.append((z["date"],value))
   data.sort()
   if not data:return {"status":"NO_HISTORICAL_VINTAGE_AVAILABLE","series":series,"asOf":sunday},raw
   lag=(day(sunday)-day(data[-1][0])).days
   if len(data)<3 or not 2<=lag<=10:
    raise ValueError("MISSING_3_DAILY_VALUES_OR_BAD_PUBLISH_LAG")
   older=[z for z in data if 25<=(day(data[-1][0])-day(z[0])).days<=35]
   delta=(data[-1][1]-older[-1][1]) if older else None
   return {"status":"PIT_ASOF_DATE_VERIFIED","series":series,"asOf":sunday,"lastObs":data[-1][0],
     "lastValue":round(data[-1][1],6),"fourWeekDelta":round(delta,6) if delta is not None else None,
     "observations":len(data),"latestLagDays":lag,"rawSha256":sha(raw),
     "intradayPublicationClockVerified":False},raw
  except urllib.error.HTTPError as e:
   if e.code in (429,500,502,503) and attempt<3:
    time.sleep(3*(attempt+1));continue
   return {"status":"HTTP_ERROR","asOf":sunday,"series":series,"httpStatus":e.code},None
  except Exception as e:
   return {"status":"SOURCE_QA_FAILED","asOf":sunday,"series":series,
     "reason":type(e).__name__+":"+str(e)[:130]},None

def main():
 prraw=(ROOT/PRE).read_bytes();p=json.loads(prraw)
 if p["version"]!="8.18a" or p["parentHistory"]!={"key":PARENT[0],"sha256":PARENT[1]}:
  raise SystemExit("V818A_PREREG_CHANGED")
 import re
 key=os.environ.get("FRED_API_KEY","")
 if not re.fullmatch("[a-z0-9]{32}",key):raise SystemExit("V818A_SECURE_FRED_KEY_MISSING")
 s=s3();b=os.environ["R2_BUCKET"]
 base=get(s,b,*PARENT)
 if base["version"]!="8.17.1" or len(base["weeklyPanel"])!=684:
  raise SystemExit("V818A_ORIGINAL_684_SOURCE_CHANGED")
 prefix=f"research/btci/v8.18a/runs/{os.environ.get('GITHUB_RUN_ID','manual')}-{os.environ.get('GITHUB_RUN_ATTEMPT','1')}/"
 items=[]
 for ser in p["inputSeries"]:
  for asof in p["probeAsOfSundays"]:
   audit,blob=probe(ser["id"],asof,key)
   if blob is not None:
    key_src=prefix+f"source/{ser['id']}_{asof}.json"
    checksum=put(s,b,key_src,blob)
    audit={**audit,"rawSha256":checksum,"r2Key":key_src}
   items.append(audit)
   print("V818A_SOURCE",ser["id"],asof,audit["status"],flush=True)
   time.sleep(0.7)
 result={"version":"8.18a","researchOnly":True,"status":"SOURCE_DATE_PILOT_COMPLETED",
  "parentSource":{"key":PARENT[0],"sha256":PARENT[1]},
  "preregistration":{"path":PRE,"sha256":sha(prraw)},
  "sourceAccessTests":items,
  "coverageBySeries":{s0["id"]:{"requested":len(p["probeAsOfSundays"]),
    "passed":sum(z["status"]=="PIT_ASOF_DATE_VERIFIED" for z in items if z["series"]==s0["id"]),
    "dateVintages":[{"asOf":z["asOf"],"status":z["status"],"value":z.get("lastValue"),
      "fourWeekDelta":z.get("fourWeekDelta")} for z in items if z["series"]==s0["id"]]}
     for s0 in p["inputSeries"]},
  "note":"Source audit ONLY; no BTC signal/confluence/forecast tested or promoted. Historical index rebasing and initial publication date may preclude naive joins.",
  "licence":"Do not archive or redistribute copyright-limited ICE OAS/Moody credit or CBOE VIX without appropriate permission.",
  "unchanged":{"Spot":True,"Futures":True,"NAV":True,"PnL":True,"MASTER":True,"Detector":True,"riskLimits":True}}
 out=Path("btci_v818a_reports");out.mkdir(exist_ok=True)
 raw=json.dumps(result,ensure_ascii=False,indent=2).encode()
 (out/"factor_source_audit.json").write_bytes(raw)
 rh=put(s,b,prefix+"source_audit.json",raw)
 mh=put(s,b,prefix+"manifest.json",{"version":"8.18a","researchOnly":True,"status":result["status"],
    "reportSha256":rh,"preregSha256":sha(prraw)})
 (out/"summary.json").write_text(json.dumps({"prefix":prefix,"reportSha256":rh,
   "manifestSha256":mh,"coverage":result["coverageBySeries"]},ensure_ascii=False,indent=2))
 print("V818A_RESULT "+json.dumps({"status":"V818A_R2_READBACK_VERIFIED",
  "prefix":prefix,"reportSha256":rh,"manifestSha256":mh,
  "coverage":result["coverageBySeries"]},ensure_ascii=False),flush=True)
if __name__=="__main__":main()
