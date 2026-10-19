#!/usr/bin/env python3
"""BTCI v8.18b original FRED as-of 2012-2025 real yields / USD / yield curve.
Retrospective independent macro factors vs pinned BTC rise/fall. No trading.
"""
import base64,collections,concurrent.futures,datetime as dt,hashlib,json,math,os,statistics,threading,time,urllib.error,urllib.parse,urllib.request
from pathlib import Path
import boto3

ROOT=Path(__file__).resolve().parents[1]
SPEC="research/btci_v818b_three_factor_pit_comparison_prereg_2026-10-19.json"
HISTORY=("research/btci/v8.17.1/runs/39212878778-1/full_historical_rise_fall.json","539bcc1817a2120287497c2814d0344aae5d62714b4f35a36f30c2425e5d3091")
TARGETS=("UP13","UP26","UP52","DOWN13","DOWN26","DOWN52","POSITIVE13","POSITIVE26","POSITIVE52")
BASE=("BTC_A","BTC_FED","MACRO_STRICT","ALL_OLD","DOWN_OLD")
RATES=("REAL_EASE","REAL_TIGHT","BTC_REAL_EASE","BTC_FED_REAL_EASE","ALL_OLD_REAL_EASE","DOWN_OLD_REAL_TIGHT","REAL_TIGHT_NO_BTC")
USD=("DOLLAR_SOFT","DOLLAR_STRONG","ALL_OLD_USD_SOFT","DOWN_OLD_USD_STRONG","REAL_AND_USD_TIGHT","REAL_AND_USD_TIGHT_NO_BTC","REAL_AND_USD_EASE","ALL_OLD_REAL_USD_EASE")
CURVE=("SPREAD_INVERTED","SPREAD_FLATTEN","DOWN_OLD_SPREAD_INVERTED","ALL_OLD_SPREAD_NOT_INVERTED")
KEYS=BASE+RATES+USD+CURVE

def sha(v):return hashlib.sha256(v).hexdigest()
def day(x):return dt.date.fromisoformat(x)
def r6(z):return round(float(z),6) if z is not None else None
def median(z):return r6(statistics.median(z)) if z else None
def s3():
 return boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
 aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
 aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
def get(s,b,k,dg):
 raw=s.get_object(Bucket=b,Key=k)["Body"].read()
 if sha(raw)!=dg:raise SystemExit("V818B_HISTORY_SHA_MISMATCH")
 return json.loads(raw)
def put(s,b,k,data,typ="application/json"):
 raw=data if isinstance(data,bytes) else json.dumps(data,ensure_ascii=False,indent=2).encode()
 dg=sha(raw)
 s.put_object(Bucket=b,Key=k,Body=raw,ContentType=typ,
  Metadata={"sha256":dg,"research-only":"true"})
 if sha(s.get_object(Bucket=b,Key=k)["Body"].read())!=dg:raise SystemExit("V818B_R2_READBACK_MISMATCH")
 return {"key":k,"sha256":dg,"bytes":len(raw)}

LOCK=threading.Lock()
NEXT_ALLOWED=[0.]
def throttle():
 with LOCK:
  now=time.monotonic()
  wait=max(0.,NEXT_ALLOWED[0]-now)
  NEXT_ALLOWED[0]=max(now,NEXT_ALLOWED[0])+1.1
 if wait:time.sleep(wait)

def fetch(symbol,sunday,api_key,lagmax):
 asof=day(sunday)
 params={"series_id":symbol,"api_key":api_key,"file_type":"json",
  "realtime_start":sunday,"realtime_end":sunday,
  "observation_start":(asof-dt.timedelta(days=66)).isoformat(),
  "observation_end":sunday,"limit":"1000"}
 url="https://api.stlouisfed.org/fred/series/observations?"+urllib.parse.urlencode(params)
 for attempt in range(5):
  throttle()
  try:
   req=urllib.request.Request(url,headers={"User-Agent":"BTCI research historical vintage 8.18b","Accept":"application/json"})
   with urllib.request.urlopen(req,timeout=38) as response:
    raw=response.read(350001)
   if len(raw)>350000:raise ValueError("OVER_MAX_RESPONSE")
   obj=json.loads(raw)
   if obj.get("realtime_start")!=sunday or obj.get("realtime_end")!=sunday:
    raise ValueError("REALTIME_ASOF_WRONG")
   records=[]
   for q in obj.get("observations",[]):
    val=q.get("value")
    if val in (None,"","."):continue
    if q.get("date","9999")>sunday or q.get("realtime_start","9999")>sunday or q.get("realtime_end","0000")<sunday:
     raise ValueError("FUTURE_OBS_OR_VINTAGE")
    value=float(val)
    if not math.isfinite(value):raise ValueError("NONFINITE_OBS")
    records.append((q["date"],value))
   records.sort()
   if len(records)<3 or len(set(q[0] for q in records))!=len(records):
    raise ValueError("LESS_THAN_3_OR_DUPLICATED_OBSERVATIONS")
   latest=records[-1]
   lag=(asof-day(latest[0])).days
   if lag<2 or lag>lagmax:raise ValueError("PUBLICATION_TOO_FRESH_OR_STALE")
   earlier=[v for v in records if 25<=(day(latest[0])-day(v[0])).days<=35]
   if not earlier:raise ValueError("NO_PRIOR_FOUR_WEEK_ANCHOR")
   previous=earlier[-1]
   audit={"status":"ASOF_HISTORICAL_VALID","symbol":symbol,"sunday":sunday,
    "lastObservedDate":latest[0],"lastValue":r6(latest[1]),
    "monthPriorObservedDate":previous[0],"monthPriorValue":r6(previous[1]),
    "changeFourWeek":r6(latest[1]-previous[1]),
    "lastObsLagDays":lag,"rawSha256":sha(raw),
    "validity":str(obj.get("realtime_start"))+":"+str(obj.get("realtime_end")),
    "intradayOriginalPublicationTimeVerified":False}
   return audit,raw
  except urllib.error.HTTPError as e:
   if e.code in (429,500,502,503,504) and attempt<4:
    time.sleep(4*(attempt+1));continue
   return {"status":"HTTP_BLOCKED","symbol":symbol,"sunday":sunday,"httpStatus":e.code},None
  except (urllib.error.URLError,TimeoutError) as e:
   if attempt<4:
    time.sleep(3*(attempt+1));continue
   return {"status":"NETWORK_BLOCKED","symbol":symbol,"sunday":sunday,"reason":type(e).__name__},None
  except Exception as e:
   return {"status":"SOURCE_QA_BLOCKED","symbol":symbol,"sunday":sunday,
    "reason":type(e).__name__+":"+str(e)[:140]},None
 return {"status":"RETRY_EXHAUSTED","symbol":symbol,"sunday":sunday},None

def flags(old,by):
 a=old["flags"]["A"];f=old["flags"]["F"]
 ms=old["flags"]["STRICT_MACRO"];allold=old["flags"]["STRICT_ALL"];neg=old["flags"]["NEG_ALL"]
 real=by.get("DFII10");usd=by.get("DTWEXBGS");curve=by.get("T10Y2Y")
 rv=real["changeFourWeek"] if real else None
 uv=usd["changeFourWeek"] if usd else None
 cv=curve["changeFourWeek"] if curve else None
 cl=curve["lastValue"] if curve else None
 v={"BTC_A":a,"BTC_FED":old["flags"]["BTC_FED"],"MACRO_STRICT":ms,"ALL_OLD":allold,"DOWN_OLD":neg}
 if rv is not None:
  v.update({"REAL_EASE":rv<0,"REAL_TIGHT":rv>0,
   "BTC_REAL_EASE":a and rv<0,"BTC_FED_REAL_EASE":a and f and rv<0,
   "ALL_OLD_REAL_EASE":allold and rv<0,
   "DOWN_OLD_REAL_TIGHT":neg and rv>0,
   "REAL_TIGHT_NO_BTC":rv>0 and not a})
 if uv is not None:
  v.update({"DOLLAR_SOFT":uv<0,"DOLLAR_STRONG":uv>0,
   "ALL_OLD_USD_SOFT":allold and uv<0,
   "DOWN_OLD_USD_STRONG":neg and uv>0})
 if rv is not None and uv is not None:
  v.update({"REAL_AND_USD_TIGHT":rv>0 and uv>0,
   "REAL_AND_USD_TIGHT_NO_BTC":rv>0 and uv>0 and not a,
   "REAL_AND_USD_EASE":rv<0 and uv<0,
   "ALL_OLD_REAL_USD_EASE":allold and rv<0 and uv<0})
 if cv is not None:
  v.update({"SPREAD_INVERTED":cl<0,"SPREAD_FLATTEN":cv<0,
   "DOWN_OLD_SPREAD_INVERTED":neg and cl<0,
   "ALL_OLD_SPREAD_NOT_INVERTED":allold and cl>=0})
 return v

def calc(rows,fields):
 cohort=[r for r in rows if all(k in r["flags"] for k in fields)]
 n=len(cohort)
 ans={"n":n,"first":cohort[0]["date"] if n else None,"last":cohort[-1]["date"] if n else None,
  "targetBaseRates":{t:r6(sum(r["outcomes"][t] for r in cohort)/n) if n else None for t in TARGETS},
  "models":{}}
 for k in fields:
  chosen=[r for r in cohort if r["flags"][k]]
  num=len(chosen)
  metrics={"selected":num,"selectedFraction":r6(num/n) if n else None,
   "median26WeekReturnPct":median([r["returns"]["26"] for r in chosen]),
   "target":{}}
  for t in TARGETS:
   tp=sum(r["outcomes"][t] for r in chosen)
   base=sum(r["outcomes"][t] for r in cohort)
   fp=num-tp;fn=base-tp;tn=n-num-fn
   metrics["target"][t]={"TP":tp,"FP":fp,"FN":fn,"TN":tn,
     "precision":r6(tp/num) if num else None,"recall":r6(tp/base) if base else None}
  ans["models"][k]=metrics
 return ans

def lock(rows,key,weeks):
 kept=[];previous=None
 for r in rows:
  if key not in r["flags"] or not r["flags"][key]:continue
  v=day(r["date"])
  if previous is None or (v-previous).days>=7*(weeks+1):
   kept.append(r);previous=v
 return kept
def lockSummary(rows,n,fields):
 result={}
 for m in fields:
  cohort=[r for r in rows if m in r["flags"]]
  signals=lock(cohort,m,n)
  result[m]={"lockOutWeeks":n,"count":len(signals),
   "down26":sum(r["outcomes"]["DOWN26"] for r in signals),
   "up26":sum(r["outcomes"]["UP26"] for r in signals),
   "pos26":sum(r["outcomes"]["POSITIVE26"] for r in signals),
   "dates":[r["date"] for r in signals]}
 return result

def main():
 rawpr=(ROOT/SPEC).read_bytes();spec=json.loads(rawpr)
 if spec["version"]!="8.18b" or spec["history"]!={"key":HISTORY[0],"sha256":HISTORY[1]}:
  raise SystemExit("V818B_SPEC_OR_PIN_MISMATCH")
 import re
 secret=os.getenv("FRED_API_KEY","")
 if not re.fullmatch(r"[a-z0-9]{32}",secret):
  raise SystemExit("V818B_SECURE_FRED_KEY_UNAVAILABLE")
 cloud=s3();bucket=os.environ["R2_BUCKET"]
 history=get(cloud,bucket,*HISTORY)
 if history["version"]!="8.17.1" or len(history["weeklyPanel"])!=684:
  raise SystemExit("V818B_HISTORY_NOT_684")
 rows=history["weeklyPanel"]
 if rows[0]["date"]!="2012-06-03" or rows[-1]["date"]>"2025-10-19":
  raise SystemExit("V818B_FROZEN_DATES_INVALID")
 prefix=f"research/btci/v8.18b/runs/{os.environ['GITHUB_RUN_ID']}-{os.environ.get('GITHUB_RUN_ATTEMPT','1')}/"
 auditBySymbol={};archiveBySymbol={}
 for series in ("DFII10","DTWEXBGS","T10Y2Y"):
  setting=spec["sources"][series]
  requested=[r["date"] for r in rows if r["date"]>=setting["eligibleSince"]]
  results={};bodies={}
  with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
   jobs={pool.submit(fetch,series,sunday,secret,setting["lagDaysAllowed"][1]):sunday for sunday in requested}
   for count,f in enumerate(concurrent.futures.as_completed(jobs),1):
    sunday=jobs[f]
    audit,original=f.result()
    results[sunday]=audit
    record={"asOf":sunday,"audit":audit}
    if original:record["rawBase64"]=base64.b64encode(original).decode()
    bodies[sunday]=record
    if count%110==0 or count==len(requested):
     print("V818B_FETCH_PROGRESS",series,count,"/",len(requested),
       "valid",sum(v["status"]=="ASOF_HISTORICAL_VALID" for v in results.values()),flush=True)
  raw=("\n".join(json.dumps(bodies[d],ensure_ascii=False,separators=(",",":")) for d in requested)+"\n").encode()
  digest=put(cloud,bucket,prefix+f"source/{series}_sunday_asof.jsonl",raw,"application/x-ndjson")
  errors=collections.Counter(v["status"] for v in results.values())
  archiveBySymbol[series]={**digest,"requested":len(requested),
   "validated":errors["ASOF_HISTORICAL_VALID"],"qualityStatusCounts":dict(errors)}
  auditBySymbol[series]=results
  print("V818B_SOURCE_ARCHIVED",series,archiveBySymbol[series]["validated"],"of",len(requested),flush=True)
 corrected=[dict(r) for r in rows]
 for i,r in enumerate(corrected):
  d=r["date"]
  factors={sym:auditBySymbol[sym][d] for sym in auditBySymbol
    if d in auditBySymbol[sym] and auditBySymbol[sym][d]["status"]=="ASOF_HISTORICAL_VALID"}
  r["newMacroFactors"]=factors
  r["flags"]=flags(rows[i],factors)
  if r["date"]!=rows[i]["date"] or r["outcomes"]!=rows[i]["outcomes"]:
   raise SystemExit("V818B_ORIGINAL_OUTCOMES_MUTATED")
 # Never claim full joint 684. Factor exact matched cohorts.
 sets={"REAL_RATE":BASE+RATES,
   "DOLLAR":BASE+("DOLLAR_SOFT","DOLLAR_STRONG","ALL_OLD_USD_SOFT","DOWN_OLD_USD_STRONG"),
   "CURVE":BASE+CURVE,
   "REAL_AND_USD":BASE+RATES+USD}
 summary={}
 for study,fields in sets.items():
  s=calc(corrected,fields)
  split={era:calc([r for r in corrected if r["era"]==era],fields) for era in ("2012","2013-2016","2017-2019","2020-2023","2024-2025")}
  matching=[r for r in corrected if all(k in r["flags"] for k in fields)]
  summary[study]={"all":s,"eras":split,"lock13":lockSummary(matching,13,fields),
   "lock26":lockSummary(matching,26,fields)}
 # Fail if incomplete FRED rate access due infrastructure limitation, do not silently promote.
 broken={series:sum(v["status"] in ("HTTP_BLOCKED","NETWORK_BLOCKED","RETRY_EXHAUSTED")
   for v in info.values()) for series,info in auditBySymbol.items()}
 if any(value>0 for value in broken.values()):
  print("V818B_SOURCE_PARTIAL_WARNING",json.dumps(broken),flush=True)
  status="PARTIAL_SOURCE_RECOVERY_REQUIRED"
 else:status="THREE_FACTOR_SOURCE_AUDIT_COMPLETED_RESEARCH_ONLY"
 report={"version":"8.18b","status":status,"researchOnly":True,"tradeAuthorized":False,
  "historyParent":{"key":HISTORY[0],"sha256":HISTORY[1]},
  "preregistration":{"path":SPEC,"sha256":sha(rawpr)},
  "officialFedHistoricalAsOfArchives":archiveBySymbol,
  "qualityUnresolvedTransient":broken,
  "studyResults":summary,
  "all684ResearchRows":corrected,
  "interpretation":["All models untrained and directionally frozen precompute; NOT OOS, NOT independently predictive or investment strategy.",
  "Compare factor with baseline BTC on EXACT matched cohort; dollar series does not have original as-of values for 2012–2018.",
  "An inverted yield curve is not an immediate crash forecast and real-rate increases do not imply BTC causality.",
  "14/27-week lockout reduces horizon overlap but not historical cycle dependence.",
  "FRED historical as-of Sunday original vintage dates verified; precise initial daily source publication clock not verified.",
  "Missing vintage series recorded UNKNOWN not false; no 2026 current value used retrospectively.",
  "BTC PriceUSD CoinMetrics fixing retrospective and not executable; no P&L/fees/funding/slippage."],
  "operations":{"MASTER":False,"Spot":False,"Futures":False,"NAV":False,
     "PnL":False,"capital":False,"reserve":False,"Detector":False,"riskLimits":False}}
 out=Path("btci_v818b_reports");out.mkdir(exist_ok=True)
 blob=json.dumps(report,ensure_ascii=False,indent=2).encode()
 (out/"independent_factors.json").write_bytes(blob)
 digest=put(cloud,bucket,prefix+"independent_factors.json",blob)
 manifest=put(cloud,bucket,prefix+"manifest.json",{"version":"8.18b","researchOnly":True,
   "reportStatus":status,"reportSha256":digest["sha256"],"preregSha256":sha(rawpr),
   "archives":archiveBySymbol})
 simple={"status":"V818B_REPORT_R2_READBACK_VERIFIED","reportStatus":status,
  "prefix":prefix,"reportSha256":digest["sha256"],"manifestSha256":manifest["sha256"],
  "sources":archiveBySymbol,"transientErrors":broken,
  "byStudy":{label:{"n":v["all"]["n"],"baseUP26":v["all"]["targetBaseRates"]["UP26"],
    "baseDOWN26":v["all"]["targetBaseRates"]["DOWN26"],
    "models":{m:{"count":x["selected"],"up26":x["target"]["UP26"],
     "down26":x["target"]["DOWN26"],
     "median26Pct":x["median26WeekReturnPct"]} for m,x in v["all"]["models"].items()},
    "eraCount":{k:t["n"] for k,t in v["eras"].items()},
    "lock13":{m:{"n":a["count"],"up26":a["up26"],"down26":a["down26"]}
     for m,a in v["lock13"].items()}}
   for label,v in summary.items()}}
 (out/"summary.json").write_text(json.dumps(simple,ensure_ascii=False,indent=2))
 print("V818B_RESULT "+json.dumps(simple,ensure_ascii=False),flush=True)
if __name__=="__main__":main()
