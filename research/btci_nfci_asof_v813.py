#!/usr/bin/env python3
"""BTCI v8.13 NFCI/ANFCI exact-as-of historical vintages vs BTC phase,
 research-only. Uses no future economic observations and no trading/accounting.
"""
import base64,collections,datetime as dt,hashlib,json,math,os,statistics,time,urllib.parse,urllib.request,urllib.error
from pathlib import Path
import boto3

ROOT=Path(__file__).resolve().parents[1]
PRE="research/btci_v813_nfci_anfci_vintage_prereg_2026-10-18.json"
P812=("research/btci/v8.12/runs/39148350442-1/early_warning.json",
"17f98e1a0eac6c0fd8b77adb806844981239fdecc11dc84744183784d3d5ab6b")
P812A=("research/btci/v8.12a/runs/39150700703-1/source_audit.json",
"5d44a3895c72b57893c4ba1370eee72be9be3241abaca647990089e27732d5c6")
KEYS=("A","C","NFCI_IMPROVE4","ANFCI_IMPROVE4","NFCI_EASY_LEVEL","ANFCI_EASY_LEVEL","NFCI_AND_FED","ANFCI_AND_FED","NFCI_OR_ANFCI")
def sha(v):return hashlib.sha256(v).hexdigest()
def f6(v):return round(float(v),6) if v is not None else None
def cal(s):return dt.date.fromisoformat(s)
def r2():
 return boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
 aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
 aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
def checked_get(s,b,k,dig):
 raw=s.get_object(Bucket=b,Key=k)["Body"].read()
 if sha(raw)!=dig:raise SystemExit("V813_FROZEN_PARENT_SHA_MISMATCH")
 return json.loads(raw)
def save(s,b,k,blob,typ="application/json"):
 raw=blob if isinstance(blob,bytes) else json.dumps(blob,ensure_ascii=False,indent=2).encode()
 dig=sha(raw)
 s.put_object(Bucket=b,Key=k,Body=raw,ContentType=typ,
  Metadata={"sha256":dig,"research-only":"true"})
 if sha(s.get_object(Bucket=b,Key=k)["Body"].read())!=dig:
  raise SystemExit("V813_WRITEBACK_SHA_READ_ERROR")
 return dig
def fetch_asof(symbol,sunday,key):
 day=cal(sunday)
 # Only past 16 weeks observed, as known at Sunday. Weekly observation labels
 # denote Friday; the preceding Wednesday is next week's original release.
 query={
  "series_id":symbol,"api_key":key,"file_type":"json",
  "realtime_start":sunday,"realtime_end":sunday,
  "observation_start":(day-dt.timedelta(weeks=16)).isoformat(),
  "observation_end":sunday,"limit":"1000"}
 url="https://api.stlouisfed.org/fred/series/observations?"+urllib.parse.urlencode(query)
 for attempt in range(4):
  try:
   with urllib.request.urlopen(urllib.request.Request(url,
      headers={"Accept":"application/json","User-Agent":"BTCI vintage research v8.13"}),
      timeout=40) as response:
    raw=response.read(500001)
   if len(raw)>500000:raise ValueError("API_RESPONSE_TOO_BIG")
   info=json.loads(raw)
   if info.get("realtime_start")!=sunday or info.get("realtime_end")!=sunday:
    raise ValueError("API_REALTIME_ASOF_NOT_CONFIRMED")
   candidates=[]
   for z in info.get("observations",[]):
    val=z.get("value")
    if val in (".",None,""):continue
    date=z.get("date","")
    rstart=z.get("realtime_start","")
    rend=z.get("realtime_end","")
    if date>sunday or rstart>sunday or rend<sunday:raise ValueError("VINTAGE_FUTURE_OR_WRONG_VALIDITY")
    value=float(val)
    if not math.isfinite(value):raise ValueError("NONFINITE_NFCI_VALUE")
    candidates.append((date,value))
   candidates.sort()
   if len(candidates)<5:raise ValueError("NOT_FIVE_OBSERVATIONS")
   if len(set(d for d,_ in candidates))!=len(candidates):
    raise ValueError("DUPLICATE_WEEKLY_OBS")
   last=candidates[-1]
   prev=candidates[-5]
   age=(day-cal(last[0])).days
   gap=(cal(last[0])-cal(prev[0])).days
   if age<6 or age>18 or not 27<=gap<=35:
    raise ValueError("VINTAGE_OBSERVATION_TOO_RECENT_STALE_OR_GAPPED")
   audit={
    "status":"PIT_ASOF_DATE_VERIFIED","series":symbol,"asOfSunday":sunday,
    "lastObs":last[0],"lastValue":f6(last[1]),
    "fourWeeksAgoObs":prev[0],"fourWeeksAgoValue":f6(prev[1]),
    "deltaFourWeeks":f6(last[1]-prev[1]),
    "observationAgeDays":age,"observationIntervalDays":gap,
    "historicObservationCount":len(candidates),
    "rawSha256":sha(raw),"realtimeAsOfDateVerified":True,
    "intradayPublicationTimeVerified":False}
   return audit,raw
  except urllib.error.HTTPError as exc:
   status=exc.code
   if status in (429,500,502,503,504) and attempt<3:
    time.sleep(2*(attempt+1));continue
   return {"status":"SOURCE_HTTP_BLOCKED","series":symbol,"asOfSunday":sunday,
       "httpStatus":status},None
  except Exception as exc:
   return {"status":"SOURCE_VALIDATION_BLOCKED","series":symbol,
      "asOfSunday":sunday,"reason":type(exc).__name__+":"+str(exc)[:160]},None
 return {"status":"SOURCE_FETCH_RETRIES_EXHAUSTED","series":symbol,"asOfSunday":sunday},None

def confusion(rows,model,target):
 tp=sum(z["newModels"][model] and z[target] for z in rows)
 fp=sum(z["newModels"][model] and not z[target] for z in rows)
 fn=sum(not z["newModels"][model] and z[target] for z in rows)
 tn=sum(not z["newModels"][model] and not z[target] for z in rows)
 def div(a,b):return f6(a/b) if b else None
 sensitivity=div(tp,tp+fn);specificity=div(tn,tn+fp)
 return {"TP":tp,"FP":fp,"FN":fn,"TN":tn,"selected":tp+fp,
   "precision":div(tp,tp+fp),"recall":sensitivity,"specificity":specificity,
   "balancedAccuracy":f6((sensitivity+specificity)/2) if sensitivity is not None and specificity is not None else None}
def group(rows):
 out={"n":len(rows),"structuralExpansion13w":sum(x["newExpansionBy13w"] for x in rows),
      "btcPositive13w":sum(x["btcReturnPositive13w"] for x in rows)}
 for key in KEYS:
  selected=[r for r in rows if r["newModels"][key]]
  r=[z["btcReturn13wPct"] for z in selected]
  out[key]={"structuralExpansion13w":confusion(rows,key,"newExpansionBy13w"),
   "btcPositive13w":confusion(rows,key,"btcReturnPositive13w"),
   "adverse20AmongSelected":sum(z["btcAdverse20Next13w"] for z in selected),
   "medianSelectedReturn13wPct":f6(statistics.median(r)) if r else None}
 return out
def main():
 rawpre=(ROOT/PRE).read_bytes();spec=json.loads(rawpre)
 if spec["version"]!="8.13" or spec["parents"]!={
 "sample":{"key":P812[0],"sha256":P812[1]},
 "sourcePilot":{"key":P812A[0],"sha256":P812A[1]}}:
  raise SystemExit("V813_PREREG_INVALID")
 key=os.environ.get("FRED_API_KEY","")
 import re
 if not re.fullmatch(r"[a-z0-9]{32}",key):raise SystemExit("V813_SECURE_FRED_API_KEY_NOT_CONFIGURED")
 s=r2();b=os.environ["R2_BUCKET"]
 sample=checked_get(s,b,*P812)
 pil=checked_get(s,b,*P812A)
 if sample["version"]!="8.12" or pil["vintageSampleSuccess"]!=8:
  raise SystemExit("V813_PARENT_NOT_FULLY_VERIFIED")
 records=sample["rows"]
 if len(records)!=138 or records[0]["date"]!="2020-05-10" or records[-1]["date"]!="2026-07-12":
  raise SystemExit("V813_COMMON_PANEL_CHANGED")
 prefix=f"research/btci/v8.13/runs/{os.environ.get('GITHUB_RUN_ID','manual')}-{os.environ.get('GITHUB_RUN_ATTEMPT','1')}/"
 source={};archives={}
 for sym in ("NFCI","ANFCI"):
  source[sym]={};backups=[]
  for i,rec in enumerate(records,1):
   date=rec["date"]
   value,body=fetch_asof(sym,date,key)
   source[sym][date]=value
   saved={"asOfSunday":date,"audit":value}
   if body is not None:saved["rawB64"]=base64.b64encode(body).decode()
   backups.append(json.dumps(saved,ensure_ascii=False,separators=(",",":")))
   # Limit request pacing under possible public API rate limits.
   time.sleep(0.42)
   if i%35==0:print(f"V813_SOURCE_PROGRESS {sym} {i}/{len(records)} valid={sum(x['status']=='PIT_ASOF_DATE_VERIFIED' for x in source[sym].values())}",flush=True)
  raw=("\n".join(backups)+"\n").encode()
  path=prefix+f"source/{sym}_historical_asof_138_sundays.jsonl"
  h=save(s,b,path,raw,"application/x-ndjson")
  archives[sym]={"r2Key":path,"sha256":h,"bytes":len(raw),
    "requested":len(records),
    "valid":sum(x["status"]=="PIT_ASOF_DATE_VERIFIED" for x in source[sym].values())}
  print("V813_ARCHIVE_SOURCE",sym,archives[sym]["valid"],flush=True)
 panel=[];missing=[]
 for x in records:
  date=x["date"];n=source["NFCI"][date];a=source["ANFCI"][date]
  if n["status"]!="PIT_ASOF_DATE_VERIFIED" or a["status"]!="PIT_ASOF_DATE_VERIFIED":
   missing.append({"date":date,"NFCI":n,"ANFCI":a});continue
  up=x["financial"]["deltaFourReleaseMillionUSD"]>0
  ni=n["deltaFourWeeks"]<0;ai=a["deltaFourWeeks"]<0
  new={"A":x["warnings"]["A"],"C":up,
    "NFCI_IMPROVE4":ni,"ANFCI_IMPROVE4":ai,
    "NFCI_EASY_LEVEL":n["lastValue"]<0,
    "ANFCI_EASY_LEVEL":a["lastValue"]<0,
    "NFCI_AND_FED":ni and up,
    "ANFCI_AND_FED":ai and up,
    "NFCI_OR_ANFCI":ni or ai}
  panel.append({"date":date,"era":x["era"],"newModels":new,
    "NFCI":n,"ANFCI":a,"FedDelta4":x["financial"]["deltaFourReleaseMillionUSD"],
    "newExpansionBy13w":x["newExpansionBy13w"],
    "btcReturnPositive13w":x["btcReturnPositive13w"],
    "btcAdverse20Next13w":x["btcAdverse20Next13w"],
    "btcReturn13wPct":x["btcReturn13wPct"]})
 if len(panel)<100:raise SystemExit("V813_TOO_FEW_FULLY_MATCHED_VINTAGES:"+str(len(panel)))
 split={"2020-2023":[z for z in panel if z["era"]=="2020-2023"],
        "2024-2026":[z for z in panel if z["era"]=="2024-2026"]}
 anchors=[z for i,z in enumerate(panel) if i%13==0]
 events=[]
 for ex in sample["prior13wByStructuralExpansionEvent"]:
  targetdate=cal(ex["expansionDate"])
  prior=[x for x in panel if targetdate-dt.timedelta(weeks=13)<=cal(x["date"])<targetdate]
  earliest={name:next((z["date"] for z in prior if z["newModels"][name]),None) for name in KEYS}
  events.append({"expansionDate":ex["expansionDate"],"eligiblePriorWeeks":len(prior),
    "earliestWarning":earliest,
    "leadWeeks":{name:(targetdate-cal(date)).days//7 if date else None for name,date in earliest.items()}})
 report={"version":"8.13","status":"NFCI_ANFCI_HISTORICAL_ASOF_FROZEN_COHORT_RESEARCH",
  "researchOnly":True,"tradingApproved":False,
  "parent":{"v812":{"key":P812[0],"sha256":P812[1]},
            "pilot":{"key":P812A[0],"sha256":P812A[1]}},
  "preregistration":{"path":PRE,"sha256":sha(rawpre)},
  "asOfSourceArchive":archives,
  "commonPopulation":{"parentN":len(records),"fullyValidatedN":len(panel),"missingN":len(missing),
     "lastSundayWith13WeekOutcome":records[-1]["date"]},
  "excludedDueToVintageQuality":missing,
  "all":group(panel),"eras":{k:group(v) for k,v in split.items()},
  "fixedEvery13thValid":group(anchors),
  "phaseEventPrior13Weeks":events,"weeklyPanel":panel,
  "currentBTCAsOf":"2026-07-12 (last observed 13-week outcome; NOT live current market)",
  "realtimeVintageCaveat":"FRED API realtime as-of Sunday certified; individual publication intraday timestamp not certified. Past reference observation at least 6 days old.",
  "limitations":[
   "139? Cohort frozen at exactly 138 Sunday observations from previously inspected historical outcomes, no new independent OOS",
   "The target is a price-based structural expansion not an independently certified market bull regime",
   "NFCI/ANFCI finance indexes are correlated with Fed monetary conditions and BTC outcomes, not causal exposure",
   "Overlapping forward 13wk windows depend on same market episodes, 13th-week anchor very small",
   "Source data archived as exact response bytes in base64-encoded JSONL with per-response SHA, plus aggregate SHA and readback",
   "Not a live BTC trading signal, no backtest execution, fills, fees or leverage",
   "No Spot/Futures/NAV/capital/P&L/reserve/MASTER/limits or live Detector changes"]}
 folder=Path("btci_v813_reports");folder.mkdir(exist_ok=True)
 raw=json.dumps(report,ensure_ascii=False,indent=2).encode()
 (folder/"nfci_anfci_historical.json").write_bytes(raw)
 reportsha=save(s,b,prefix+"nfci_anfci_historical.json",raw)
 man={"version":"8.13","status":"FULL_HISTORICAL_VINTAGE_ABLATION_PASS",
   "reportSha256":reportsha,"sourceArchives":archives,
   "researchOnly":True,"preregSha256":sha(rawpre)}
 mansha=save(s,b,prefix+"manifest.json",man)
 brief={"status":"V813_FULL_HISTORICAL_ASOF_RESEARCH_PASS_READBACK_VERIFIED",
   "prefix":prefix,"reportSha256":reportsha,"manifestSha256":mansha,
   "coverage":report["commonPopulation"],"sources":archives,
   "all":report["all"],"eras":report["eras"],
   "anchor":report["fixedEvery13thValid"],"events":events}
 (folder/"summary.json").write_text(json.dumps(brief,ensure_ascii=False,indent=2))
 print("V813_RESULT "+json.dumps(brief,ensure_ascii=False),flush=True)
if __name__=="__main__":main()
