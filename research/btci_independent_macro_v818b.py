#!/usr/bin/env python3
"""BTCI v8.18b. Historical as-of US real yields, broad dollar and 2s10s curve
versus *frozen* BTC 2012-25 +50% & -35% future paths.
Research only: no trading/portfolio writes. Never fills a missing vintage.
"""
import base64,collections,concurrent.futures,datetime as dt,hashlib,json,math,os,re,statistics,threading,time
import urllib.parse,urllib.request,urllib.error
from pathlib import Path
import boto3
ROOT=Path(__file__).resolve().parents[1]
PRE="research/btci_v818b_rates_dollar_curve_full_prereg_2026-10-19.json"
BASE=("research/btci/v8.17.1/runs/39212878778-1/full_historical_rise_fall.json",
      "539bcc1817a2120287497c2814d0344aae5d62714b4f35a36f30c2425e5d3091")
PILOT=("research/btci/v8.18a2/runs/39222222797-1/source_audit.json",
       "f81b4102fa530974b9ef9654a79dfb2ef789739fcf7750e4c0407b2878ed93a7")
MODELS=("BASE_BTC","BASE_STRICT","BASE_NEG","R_TIGHT","D_STRONG","C_FLAT",
        "R_EASE","D_EASE","C_STEEP","RISK2","RISK3","RECOVERY2",
        "BULL_CLEAN","BULL_WITH_STRESS","BTC_CLEAN","BTC_STRESS","NEG_ADD_STRESS")
OUTCOMES=("UP13","UP26","UP52","DOWN13","DOWN26","DOWN52","POSITIVE13","POSITIVE26","POSITIVE52")
def sha(b):return hashlib.sha256(b).hexdigest()
def day(z):return dt.date.fromisoformat(z)
def num(z):return round(float(z),6)
def div(a,b):return num(a/b) if b else None
def med(arr):return num(statistics.median(arr)) if arr else None
def cloud():
 return boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
 aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
def parent(s,b,k,dig):
 raw=s.get_object(Bucket=b,Key=k)["Body"].read()
 if sha(raw)!=dig:raise SystemExit("V818B_PINNED_PARENT_SHA_CHANGED:"+k)
 return json.loads(raw)
def put(s,b,k,raw,kind="application/json"):
 if not isinstance(raw,bytes):raw=json.dumps(raw,ensure_ascii=False,indent=2).encode()
 dg=sha(raw)
 s.put_object(Bucket=b,Key=k,Body=raw,ContentType=kind,Metadata={"sha256":dg,"research-only":"true"})
 if sha(s.get_object(Bucket=b,Key=k)["Body"].read())!=dg:raise SystemExit("V818B_R2_READBACK_SHA_MISMATCH")
 return {"key":k,"sha256":dg,"bytes":len(raw)}
LOCK=threading.Lock()
LAST=[0.0]
def pace():
 with LOCK:
  t=time.monotonic();waiting=max(0,0.55-(t-LAST[0]))
  if waiting:time.sleep(waiting)
  LAST[0]=time.monotonic()
def fetch(symbol,sunday,key):
 today=day(sunday)
 params={"series_id":symbol,"api_key":key,"file_type":"json",
  "realtime_start":sunday,"realtime_end":sunday,
  "observation_start":(today-dt.timedelta(days=65)).isoformat(),
  "observation_end":sunday,"limit":1000}
 uri="https://api.stlouisfed.org/fred/series/observations?"+urllib.parse.urlencode(params)
 for i in range(7):
  try:
   pace()
   with urllib.request.urlopen(urllib.request.Request(uri,headers={
     "Accept":"application/json","User-Agent":"BTCI 8.18b original vintage economic research"}),
     timeout=35) as response: raw=response.read(550001)
   if len(raw)>550000:raise ValueError("RESPONSE_TOO_BIG")
   obj=json.loads(raw)
   if obj.get("realtime_start")!=sunday or obj.get("realtime_end")!=sunday:
    raise ValueError("FRED_REALTIME_SUNDAY_NOT_CONFIRMED")
   obs=[]
   for x in obj.get("observations",[]):
    if x.get("value") in ("",None,"."):continue
    if x["date"]>sunday or x["realtime_start"]>sunday or x["realtime_end"]<sunday:
     raise ValueError("FRED_FUTURE_VINTAGE_OR_WRONG_DATE")
    v=float(x["value"])
    if not math.isfinite(v):raise ValueError("NON_FINITE")
    obs.append((x["date"],v))
   obs.sort()
   if len(obs)<3 or len({z[0] for z in obs})!=len(obs):
    raise ValueError("MISSING_THREE_UNIQUE_OBSERVATIONS")
   lag=(today-day(obs[-1][0])).days
   if not 2<=lag<=10:raise ValueError("SOURCE_STALE_OR_TOO_RECENT")
   old=[z for z in obs[:-1] if 25<=(day(obs[-1][0])-day(z[0])).days<=35]
   if not old:raise ValueError("FOUR_WEEK_COMPARATOR_NOT_AVAILABLE")
   compare=min(old,key=lambda z:abs((day(obs[-1][0])-day(z[0])).days-28))
   audit={"status":"ASOF_VINTAGE_VALID","symbol":symbol,"sunday":sunday,
    "lastObs":obs[-1][0],"lastValue":num(obs[-1][1]),
    "oldObs":compare[0],"oldValue":num(compare[1]),
    "delta4":num(obs[-1][1]-compare[1]),
    "pct4":num(100*(obs[-1][1]/compare[1]-1)) if compare[1]!=0 else None,
    "rawSha256":sha(raw),"ageDays":lag,"intradayClockVerified":False}
   return audit,raw
  except urllib.error.HTTPError as e:
   if e.code in (429,500,502,503,504) and i<6:
    time.sleep(min(25,3*(i+1)));continue
   return {"status":"HTTP_ERROR","httpStatus":e.code,"symbol":symbol,"sunday":sunday},None
  except Exception as e:
   return {"status":"SOURCE_QA_FAILED","symbol":symbol,"sunday":sunday,
      "reason":type(e).__name__+":"+str(e)[:130]},None
 return {"status":"RETRY_EXHAUSTED","symbol":symbol,"sunday":sunday},None
def datesource(sunday):
 if sunday <"2014-02-02": return ["DFII10","DGS10","DGS2"]
 if sunday <"2014-03-23": return ["DFII10","T10Y2Y"]
 if sunday <"2019-02-10": return ["DFII10","T10Y2Y","DTWEXB"]
 # The 2019 new index was first published February 4.
 # No 4-week new-index rate until 2019-03-03 to avoid unknown seam.
 if sunday <"2019-03-03": return ["DFII10","T10Y2Y"]
 return ["DFII10","T10Y2Y","DTWEXBGS"]
def features(row,source):
 sunday=row["date"]
 rr=source.get(("DFII10",sunday))
 if rr is None or rr["status"]!="ASOF_VINTAGE_VALID":return None,"REAL_YIELD_UNVERIFIED"
 if sunday <"2014-02-02":
  y10=source.get(("DGS10",sunday));y2=source.get(("DGS2",sunday))
  if not y10 or not y2 or any(z["status"]!="ASOF_VINTAGE_VALID" for z in (y10,y2)):
   return None,"ORIGINAL_CURVE_CONSTITUENT_MISSING"
  curve=y10["lastValue"]-y2["lastValue"]
  curve_old=y10["oldValue"]-y2["oldValue"]
  curve={"status":"ASOF_TWO_H15_COMPONENTS","symbol":"DGS10_MINUS_DGS2",
     "lastValue":num(curve),"delta4":num(curve-curve_old),
     "sourceSymbol":["DGS10","DGS2"],
     "observationDateMismatchDays":abs((day(y10["lastObs"])-day(y2["lastObs"])).days)}
  if curve["observationDateMismatchDays"]>2:return None,"TREASURY_CONSTITUENT_DATES_MISMATCHED"
 else:
  curve=source.get(("T10Y2Y",sunday))
  if curve is None or curve["status"]!="ASOF_VINTAGE_VALID":return None,"CURVE_VINTAGE_UNVERIFIED"
 sym="DTWEXB" if sunday<"2019-02-10" else "DTWEXBGS"
 dollar=None
 if sunday>="2014-03-23" and not ("2019-02-10"<=sunday<"2019-03-03"):
  dollar=source.get((sym,sunday))
  if dollar is None or dollar["status"]!="ASOF_VINTAGE_VALID":dollar=None
 return {"R":rr,"D":dollar,"C":curve,
    "usdSymbol":sym if dollar is not None else None,
    "strictDollarComparable":dollar is not None},None
def metric(rows,model,target):
 p=[x for x in rows if x["flags"][model]]
 n=len(p);tp=sum(x["outcomes"][target] for x in p)
 total=sum(x["outcomes"][target] for x in rows)
 fn=total-tp;fp=n-tp;tn=len(rows)-total-fp
 return {"nSample":len(rows),"nSignals":n,"TP":tp,"FP":fp,"FN":fn,"TN":tn,
  "precision":div(tp,n),"recall":div(tp,total),"baselineRate":div(total,len(rows))}
def summary(rows):
 out={"n":len(rows),"eraCounts":dict(collections.Counter(z["era"] for z in rows)),
      "targetBase":{t:sum(x["outcomes"][t] for x in rows) for t in OUTCOMES},
      "models":{}}
 for m in MODELS:
  selected=[x for x in rows if x["flags"][m]]
  out["models"][m]={"signals":len(selected),"outcomes":{t:metric(rows,m,t) for t in ("UP13","UP26","DOWN13","DOWN26","DOWN52","POSITIVE26")},
    "median13wkReturnPct":med([x["returns"]["13"] for x in selected]),
    "median26wkReturnPct":med([x["returns"]["26"] for x in selected]),
    "median52wkReturnPct":med([x["returns"]["52"] for x in selected])}
 return out
def spaced(rows,model,weeks):
 res=[];last=None
 for x in rows:
  now=day(x["date"])
  if x["flags"][model] and (last is None or (now-last).days>=7*(weeks+1)):
   res.append(x);last=now
 return res
def main():
 prraw=(ROOT/PRE).read_bytes();reg=json.loads(prraw)
 if reg["version"]!="8.18b" or reg["parent"]!={"btcLong":{"key":BASE[0],"sha256":BASE[1]},
  "pilot":{"key":PILOT[0],"sha256":PILOT[1]}}:raise SystemExit("V818B_PREREG_MISMATCH")
 key=os.environ.get("FRED_API_KEY","")
 if not re.fullmatch("[a-z0-9]{32}",key):raise SystemExit("V818B_FRED_SECRET_INVALID")
 s=cloud();bucket=os.environ["R2_BUCKET"]
 base=parent(s,bucket,*BASE);pilot=parent(s,bucket,*PILOT)
 if base["version"]!="8.17.1" or pilot["version"]!="8.18a2" or len(base["weeklyPanel"])!=684:
  raise SystemExit("V818B_PARENT_VERSION_OR_684_MISMATCH")
 rows=base["weeklyPanel"]
 assert [x["date"] for x in rows]==sorted(x["date"] for x in rows)
 assert rows[0]["date"]=="2012-06-03" and rows[-1]["date"]<="2025-10-19"
 allcalls=[(sym,x["date"]) for x in rows for sym in datesource(x["date"])]
 if len(allcalls)!=len(set(allcalls)):raise SystemExit("V818B_DUPLICATE_SOURCE_TASK")
 print("V818B_REQUESTS",len(allcalls),"DATES",len(rows),"FIRST",rows[0]["date"],flush=True)
 prefix=f"research/btci/v8.18b/runs/{os.environ['GITHUB_RUN_ID']}-{os.environ.get('GITHUB_RUN_ATTEMPT','1')}/"
 audits={};files={};count=0
 with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
  pending={pool.submit(fetch,sym,sunday,key):(sym,sunday) for sym,sunday in allcalls}
  for future in concurrent.futures.as_completed(pending):
   sym,sunday=pending[future];audit,body=future.result()
   audits[(sym,sunday)]=audit
   files[(sym,sunday)]={"sunday":sunday,"symbol":sym,"audit":audit}
   if body is not None:files[(sym,sunday)]["rawB64"]=base64.b64encode(body).decode()
   count+=1
   if count%150==0:print("V818B_FETCH_PROGRESS",count,len(allcalls),
    "valid",sum(x["status"]=="ASOF_VINTAGE_VALID" for x in audits.values()),flush=True)
 history=collections.Counter(z["status"] for z in audits.values())
 print("V818B_FETCH_OUTCOME",json.dumps(dict(history)),flush=True)
 archives={}
 for sym in ("DFII10","DGS10","DGS2","T10Y2Y","DTWEXB","DTWEXBGS"):
  dates=sorted(dte for sym0,dte in files if sym0==sym)
  if not dates:continue
  archive=("\n".join(json.dumps(files[(sym,dte)],ensure_ascii=False,separators=(",",":")) for dte in dates)+"\n").encode()
  storage=put(s,bucket,prefix+f"source/{sym}_historical_asof.jsonl",archive,"application/x-ndjson")
  archives[sym]={**storage,"requested":len(dates),
    "valid":sum(audits[(sym,z)]["status"]=="ASOF_VINTAGE_VALID" for z in dates)}
 full=[];rateonly=[];sourceMiss=collections.Counter()
 for original in rows:
  obj,err=features(original,audits)
  if err:sourceMiss[err]+=1;continue
  r=obj["R"]["delta4"];c=obj["C"]["delta4"]
  dollar=obj["D"]["delta4"] if obj["D"] else None
  A=bool(original["flags"]["A"]);F=bool(original["flags"]["F"])
  N=bool(original["flags"]["N"]);J=bool(original["flags"]["J"])
  all4=A and F and N and J
  neg=bool(original["flags"]["NEG_ALL"])
  r_tight=r>0
  d_tight=dollar>0 if dollar is not None else None
  c_flat=c<0
  flags={"BASE_BTC":A,"BASE_STRICT":all4,"BASE_NEG":neg,
    "R_TIGHT":r_tight,"D_STRONG":bool(d_tight) if d_tight is not None else False,
    "C_FLAT":c_flat,"R_EASE":r<0,
    "D_EASE":(dollar<0) if dollar is not None else False,
    "C_STEEP":c>0,
    "RISK2":(int(r_tight)+int(bool(d_tight))+int(c_flat))>=2 if d_tight is not None else False,
    "RISK3":r_tight and bool(d_tight) and c_flat if d_tight is not None else False,
    "RECOVERY2":r<0 and (dollar<0) if dollar is not None else False,
    "BULL_CLEAN":all4 and not r_tight and not d_tight if d_tight is not None else False,
    "BULL_WITH_STRESS":all4 and (r_tight or d_tight) if d_tight is not None else False,
    "BTC_CLEAN":A and not r_tight and not d_tight if d_tight is not None else False,
    "BTC_STRESS":A and (r_tight or d_tight) if d_tight is not None else False,
    "NEG_ADD_STRESS":neg and (r_tight or d_tight) if d_tight is not None else False}
  derived={"date":original["date"],"era":original["era"],"outcomes":original["outcomes"],
   "returns":original["returns"],"worstDailyFromStart":original["worstDailyFromStart"],
   "flags":flags,
   "factors":{"DFII10":{"value":obj["R"]["lastValue"],"delta4":r},
    "slope10minus2":{"value":obj["C"]["lastValue"],"delta4":c,"originalSymbol":obj["C"]["symbol"]},
    "dollar":{"originalSymbol":obj["usdSymbol"],"delta4":dollar},
    "publicationCutoffDate":original["date"]}}
  rateonly.append(derived)
  if d_tight is not None:full.append(derived)
 # Missing source always UNKNOWN and NEVER used in control sample
 if len(rateonly)<600 or len(full)<480:raise SystemExit("V818B_NOT_ENOUGH_VINTAGE_COVERAGE")
 epochs={era:summary([q for q in full if q["era"]==era]) for era in
   ("2012","2013-2016","2017-2019","2020-2023","2024-2025")}
 first=summary(full)
 riskByBtc={}
 for factor in ("BTC_CLEAN","BTC_STRESS","BULL_CLEAN","BULL_WITH_STRESS","BASE_NEG","NEG_ADD_STRESS"):
  cohort=[x for x in full if x["flags"][factor]]
  riskByBtc[factor]={"n":len(cohort),"UP26":sum(x["outcomes"]["UP26"] for x in cohort),
    "DOWN26":sum(x["outcomes"]["DOWN26"] for x in cohort),
    "DOWN13":sum(x["outcomes"]["DOWN13"] for x in cohort),
    "medianReturn26":med([x["returns"]["26"] for x in cohort])}
 lockout={}
 for week in (13,26):
  lockout[str(week)]={model:{"outcomes":summary(spaced(full,model,week)),
       "firstEightSignalDates":[x["date"] for x in spaced(full,model,week)][:8]}
     for model in ("BASE_BTC","BTC_CLEAN","BTC_STRESS","BASE_STRICT","BULL_CLEAN","BULL_WITH_STRESS",
                  "BASE_NEG","NEG_ADD_STRESS")}
 report={"version":"8.18b","status":"INDEPENDENT_US_MACRO_PIT_RISK_STUDY_RESEARCH_ONLY",
  "researchOnly":True,"notTradingApproved":True,
  "parents":{"btcLong":BASE,"pilot":PILOT},
  "preregistration":{"path":PRE,"sha256":sha(prraw)},
  "sourceArchives":archives,"sourceStatusCounts":dict(history),
  "coverage":{"frozenBaseN":len(rows),"realsAndTreasuryN":len(rateonly),"allThreeFactorsN":len(full),
    "excludedByReason":dict(sourceMiss),"earliestCommon":full[0]["date"],"latestCommon":full[-1]["date"],
    "allThreeFactorEra":dict(collections.Counter(z["era"] for z in full))},
  "allMatched":first,
  "rateAndTreasuryOnlyNoUSD":summary(rateonly),
  "epochs":epochs,"mostRelevantSubsets":riskByBtc,
  "lockouts":lockout,
  "weekLevel":full,
  "limitations":[
   "2012–2014 USD index was not originally released then: no FULL three-factor claim for those dates.",
   "2014–2019 DTWEXB goods-only and 2019+ DTWEXBGS goods/services have different methodologies, no level splice; sign comparison only within original as-of vintage and source.",
   "FRED realtime date as-of vintage does not prove intraday release clock, Sunday cutoff and minimum 2d observation age used.",
   "Source HTTP errors and missing historical values are UNKNOWN, never negative indicators.",
   "No thresholds trained on old history, but older BTCI stages inspected the same cycles; not OOS or predictive validation.",
   "Overlapping 26-week outcomes, calendar time dependence, and small independent regime counts; locked warning dates differ across models.",
   "Even if conditional crash rate falls, a positive market warning is NOT a near-term BTC executable trade or hedging decision.",
   "FRED H.4.1 historic official pages may have undergone revisions since 2012; macro features not 100% genuine publication-vintage attested.",
   "No Spot/Futures/NAV/P&L/capital/reserve/MASTER/Detector/trade limits writes."],
  "operationsChanged":{}}
 folder=Path("btci_v818b_reports");folder.mkdir(exist_ok=True)
 blob=json.dumps(report,ensure_ascii=False,indent=2).encode()
 (folder/"independent_factors.json").write_bytes(blob)
 fp=put(s,bucket,prefix+"independent_factors.json",blob)
 mp=put(s,bucket,prefix+"manifest.json",{"version":"8.18b","researchOnly":True,
   "status":"COMPLETE_PIT_FACTOR_ABLATION_SOURCE_VERIFIED","preregSha256":sha(prraw),
   "parentBtcSha256":BASE[1],"fullReportSha256":fp["sha256"],"sourceArchives":archives})
 brief={"status":"V818B_HISTORICAL_US_REAL_YIELDS_DOLLAR_CURVE_PASS_R2_READBACK_VERIFIED",
  "prefix":prefix,"reportSha256":fp["sha256"],"manifestSha256":mp["sha256"],
  "coverage":report["coverage"],"sourceCounts":dict(history),"byEra":{
    era:{"n":v["n"],"base":{"UP26":v["targetBase"]["UP26"],"DOWN26":v["targetBase"]["DOWN26"]},
    "selected":{m:{"n":v["models"][m]["signals"],
       "UP26":v["models"][m]["outcomes"]["UP26"]["TP"],
       "DOWN26":v["models"][m]["outcomes"]["DOWN26"]["TP"]}
      for m in ("BASE_BTC","BTC_CLEAN","BTC_STRESS","BASE_STRICT","BULL_CLEAN","BASE_NEG","NEG_ADD_STRESS")}}
    for era,v in epochs.items()},
  "all":riskByBtc,
  "main":{"sample":first["n"],"base":first["targetBase"],
     "selected":{m:{"n":first["models"][m]["signals"],
      "UP26":first["models"][m]["outcomes"]["UP26"]["TP"],
      "DOWN26":first["models"][m]["outcomes"]["DOWN26"]["TP"],
      "DOWN13":first["models"][m]["outcomes"]["DOWN13"]["TP"]}
    for m in ("BASE_BTC","BASE_STRICT","BTC_CLEAN","BTC_STRESS","BULL_CLEAN",
       "BULL_WITH_STRESS","BASE_NEG","NEG_ADD_STRESS","RISK2","RISK3")}}}
 (folder/"summary.json").write_text(json.dumps(brief,ensure_ascii=False,indent=2))
 print("V818B_RESULT "+json.dumps(brief,ensure_ascii=False),flush=True)
if __name__=="__main__":main()
