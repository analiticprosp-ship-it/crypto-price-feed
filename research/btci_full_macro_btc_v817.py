#!/usr/bin/env python3
"""BTCI v8.17: Long-history original-as-of NFCI/ANFCI, archived Fed releases,
BTC reference 2011-2026, independent rising and falling future paths.
No execution, market-data trading or future-data leakage in features.
"""
import bisect,base64,collections,concurrent.futures,datetime as dt,hashlib,json,math,os,statistics,time,urllib.parse,urllib.request,urllib.error
from pathlib import Path
import boto3
ROOT=Path(__file__).resolve().parents[1]
PRE="research/btci_v817_full_macro_btc_history_prereg_2026-10-19.json"
PB=("research/btci/v8.6/runs/39130315439-1/extended_history.json","9af82767fa8139685e784c131c075cec553298c4718ed4a40ac41412144248ca")
PC=("research/btci/v8.9/runs/39138844921-1/multiscale.json","4b8822e929aff5569fa9cd105404c02b110927a970aed33db68910925c111b73")
PF=("research/btci/v8.10.1/runs/39141047403-1/macro_study.json","230f5c2eebdba583dbadf4a44d50123fb85f93c39b318f5d4fcbb7cb7480fb81")
PP=("research/btci/v8.15/runs/39169803298-1/confluence.json","b0c9f37d535c7636a08fd5b056926ad3e5e6004bd8a988c4bc7dd51060bfaaba")
MM=("A","F","N","J","STRICT_MACRO","STRICT_ALL","BTC_FED","NEG_MACRO","NEG_ALL","FED_TIGHT","FINANCE_TIGHT")
TARGETS=("UP13","UP26","UP52","DOWN13","DOWN26","DOWN52","POSITIVE13","POSITIVE26","POSITIVE52")
def digest(raw):return hashlib.sha256(raw).hexdigest()
def d(x):return dt.date.fromisoformat(x)
def r6(x):return round(float(x),6) if x is not None else None
def r2():
 return boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
def get(s,b,k,sha):
 raw=s.get_object(Bucket=b,Key=k)["Body"].read()
 if digest(raw)!=sha:raise SystemExit("V817_FROZEN_PARENT_SHA_MISMATCH")
 return json.loads(raw)
def put(s,b,k,raw,kind="application/json"):
 if not isinstance(raw,bytes):raw=json.dumps(raw,ensure_ascii=False,indent=2).encode()
 h=digest(raw)
 s.put_object(Bucket=b,Key=k,Body=raw,ContentType=kind,Metadata={"sha256":h,"research-only":"true"})
 if digest(s.get_object(Bucket=b,Key=k)["Body"].read())!=h:raise SystemExit("V817_CLOUD_SHA_READBACK_FAIL")
 return {"r2Key":k,"sha256":h,"size":len(raw)}
def vintage(symbol,sunday,api_key):
 now=d(sunday)
 args={"series_id":symbol,"api_key":api_key,"file_type":"json","realtime_start":sunday,"realtime_end":sunday,
  "observation_start":(now-dt.timedelta(weeks=16)).isoformat(),"observation_end":sunday,"limit":"1000"}
 url="https://api.stlouisfed.org/fred/series/observations?"+urllib.parse.urlencode(args)
 for attempt in range(5):
  try:
   with urllib.request.urlopen(urllib.request.Request(url,headers={"Accept":"application/json","User-Agent":"BTCI 8.17 macro vintage"}),timeout=40) as response:
    raw=response.read(500001)
   if len(raw)>500000:raise ValueError("RESPONSE_TOO_BIG")
   x=json.loads(raw)
   if x.get("realtime_start")!=sunday or x.get("realtime_end")!=sunday:raise ValueError("INCORRECT_REALTIME_ASOF")
   val=[]
   for z in x.get("observations",[]):
    if z.get("value") in (".",None,""):continue
    if z["realtime_start"]>sunday or z["realtime_end"]<sunday or z["date"]>sunday:
     raise ValueError("FUTURE_VINTAGE_LEAKAGE")
    v=float(z["value"])
    if not math.isfinite(v):raise ValueError("NONFINITE")
    val.append((z["date"],v))
   val.sort()
   if len(val)<5 or len(set(x[0] for x in val))!=len(val):raise ValueError("MISSING_5_WEEKS")
   lag=(now-d(val[-1][0])).days
   span=(d(val[-1][0])-d(val[-5][0])).days
   if not 6<=lag<=18 or not 27<=span<=35:raise ValueError("STALE_GAPPED_OR_FUTURE_WEEK")
   audit={"status":"AVAILABLE_ASOF_DATE","series":symbol,"date":sunday,"value":r6(val[-1][1]),
      "fourWeekDelta":r6(val[-1][1]-val[-5][1]),"latestObs":val[-1][0],
      "fourthBeforeObs":val[-5][0],"ageDays":lag,"rawSha256":digest(raw),
      "intradayPublicationClockVerified":False}
   return audit,raw
  except urllib.error.HTTPError as e:
   if e.code in (429,500,502,503,504) and attempt<4:
    time.sleep(1.5*(attempt+1));continue
   return {"status":"HTTP_ERROR","httpStatus":e.code,"series":symbol,"date":sunday},None
  except Exception as e:
   return {"status":"VALIDATION_FAILED","reason":type(e).__name__+":"+str(e)[:120],"series":symbol,"date":sunday},None
 return {"status":"RETRY_EXHAUSTED","series":symbol,"date":sunday},None
def phase(dte):
 return "2012" if dte<"2013-01-01" else "2013-2016" if dte<"2017-01-01" else "2017-2019" if dte<"2020-01-01" else "2020-2023" if dte<"2024-01-01" else "2024-2025"
def stats(rows):
 ans={"n":len(rows),"targets":{k:sum(z["outcomes"][k] for z in rows) for k in TARGETS},
      "models":{}}
 for name in MM:
  hit=[x for x in rows if x["flags"][name]]
  result={"selected":len(hit),"medianReturn13Pct":r6(statistics.median([z["returns"]["13"] for z in hit])) if hit else None,
    "medianReturn26Pct":r6(statistics.median([z["returns"]["26"] for z in hit])) if hit else None,
    "medianReturn52Pct":r6(statistics.median([z["returns"]["52"] for z in hit])) if hit else None,
    "targets":{}}
  for k in TARGETS:
   tp=sum(z["outcomes"][k] for z in hit);fp=len(hit)-tp;fn=ans["targets"][k]-tp;tn=len(rows)-len(hit)-fn
   result["targets"][k]={"TP":tp,"FP":fp,"FN":fn,"TN":tn,"precision":r6(tp/len(hit)) if hit else None,
     "recall":r6(tp/ans["targets"][k]) if ans["targets"][k] else None}
  ans["models"][name]=result
 return ans
def spaced(rows,m,lock):
 out=[];last=None
 for x in rows:
  now=d(x["date"])
  if x["flags"][m] and (last is None or (now-last).days>=7*(lock+1)):
   out.append(x);last=now
 return out
def main():
 prraw=(ROOT/PRE).read_bytes();pr=json.loads(prraw)
 expected={"btc":{"key":PB[0],"sha256":PB[1]},"cycle":{"key":PC[0],"sha256":PC[1]},
 "fed":{"key":PF[0],"sha256":PF[1]},"previous":{"key":PP[0],"sha256":PP[1]}}
 if pr["version"]!="8.17" or pr["parents"]!=expected:raise SystemExit("V817_PREREG_MISMATCH")
 key=os.getenv("FRED_API_KEY","")
 import re
 if not re.fullmatch("[a-z0-9]{32}",key):raise SystemExit("NO_SECURE_FRED_API_KEY")
 s=r2();b=os.environ["R2_BUCKET"]
 btc=get(s,b,*PB);cyc=get(s,b,*PC);fed=get(s,b,*PF);previous=get(s,b,*PP)
 if btc["version"]!="8.6" or cyc["version"]!="8.9" or fed["version"]!="8.10.1" or previous["version"]!="8.15":
  raise SystemExit("SOURCE_VERSION_UNEXPECTED")
 w={x["date"]:x for x in btc["weeklyRows"]}
 ctx=cyc["pastOnlyWeeklyContext"]
 if len(ctx)!=750 or len(fed["allHistoricalReleaseObservations"])!=821:raise SystemExit("PARENT_COHORT_CHANGED")
 dates=[x["date"] for x in ctx]
 if dates!=sorted(set(dates)):raise SystemExit("BTC_CONTEXT_UNSORTED")
 reports=sorted(fed["allHistoricalReleaseObservations"],key=lambda x:x["releaseDate"])
 datesfed=[d(x["releaseDate"]) for x in reports]
 badpub={d(x["date"]) for x in fed["remainingProblems"]}
 potential=[];excluded=collections.Counter()
 for row in ctx:
  day=d(row["date"])
  wrow=w.get(row["date"])
  if wrow is None:excluded["BTC_MISSING"]+=1;continue
  if wrow["future"]["52"]["status"]!="OBSERVED":excluded["FORWARD_52W_RIGHT_CENSOR"]+=1;continue
  cutoff=day-dt.timedelta(days=3)
  k=bisect.bisect_right(datesfed,cutoff)
  if k<5:excluded["FEWER_THAN_FIVE_H41"]+=1;continue
  last5=reports[k-5:k]
  lastdates=[d(x["releaseDate"]) for x in last5]
  if any((bb-aa).days>10 for aa,bb in zip(lastdates,lastdates[1:])) or any(lastdates[0]<=v<=lastdates[-1] for v in badpub):
   excluded["FED_PUBLISHED_MISSING_OR_GAP"]+=1;continue
  fdel=last5[-1]["simplifiedFedMinusTGAMinusRRP_MillionUSD"]-last5[0]["simplifiedFedMinusTGAMinusRRP_MillionUSD"]
  possible={"date":row["date"],"ctx":row,"btc":wrow,
    "fed":{"delta4MillionUSD":fdel,"latestDatedRelease":last5[-1]["releaseDate"]}}
  potential.append(possible)
 if not potential or potential[0]["date"]>"2013-01-01":raise SystemExit("HISTORY_EXPANSION_DID_NOT_REACH_EARLY_PERIOD")
 print("V817_CANDIDATE_DATES",len(potential),potential[0]["date"],potential[-1]["date"],flush=True)
 unique_dates=[x["date"] for x in potential]
 prefix=f"research/btci/v8.17/runs/{os.environ['GITHUB_RUN_ID']}-{os.environ.get('GITHUB_RUN_ATTEMPT','1')}/"
 all_v={}
 archives={}
 for symbol in ("NFCI","ANFCI"):
  vals={};saved={}
  with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
   futures={pool.submit(vintage,symbol,sday,key):sday for sday in unique_dates}
   for count,future in enumerate(concurrent.futures.as_completed(futures),1):
    Sunday=futures[future];audit,body=future.result()
    vals[Sunday]=audit
    saved[Sunday]={"asof":Sunday,"audit":audit}
    if body is not None:saved[Sunday]["responseBase64"]=base64.b64encode(body).decode()
    if count%125==0:
     print("V817_PROGRESS",symbol,count,len(unique_dates),"valid",sum(z["status"]=="AVAILABLE_ASOF_DATE" for z in vals.values()),flush=True)
  all_v[symbol]=vals
  archive=("\n".join(json.dumps(saved[t],ensure_ascii=False,separators=(",",":")) for t in unique_dates)+"\n").encode()
  arch=put(s,b,prefix+f"sources/{symbol}_asof_sundays.jsonl",archive,"application/x-ndjson")
  archives[symbol]={**arch,"valid":sum(z["status"]=="AVAILABLE_ASOF_DATE" for z in vals.values()),
    "requested":len(unique_dates)}
  print("V817_VINTAGE_ARCHIVE",symbol,archives[symbol]["valid"],flush=True)
 panel=[];missing=[]
 # weekly structural close is price-only contextual and reference only
 for x in potential:
  sday=x["date"];n=all_v["NFCI"][sday];j=all_v["ANFCI"][sday]
  if n["status"]!="AVAILABLE_ASOF_DATE" or j["status"]!="AVAILABLE_ASOF_DATE":
   missing.append({"date":sday,"NFCI":n,"ANFCI":j});continue
  a=bool(x["btc"]["weeklyTrendConfirmed"])
  fdel=x["fed"]["delta4MillionUSD"];nv=n["fourWeekDelta"];jv=j["fourWeekDelta"]
  F=fdel>0;N=nv<0;J=jv<0
  flags={"A":a,"F":F,"N":N,"J":J,
   "STRICT_MACRO":F and N and J,"STRICT_ALL":a and F and N and J,"BTC_FED":a and F,
   "NEG_MACRO":fdel<0 and nv>0 and jv>0,"NEG_ALL":not a and fdel<0 and nv>0 and jv>0,
   "FED_TIGHT":fdel<0,"FINANCE_TIGHT":nv>0 and jv>0}
  i=dates.index(sday)
  price=x["btc"]["btcFixingPriceUSD"]
  nxt=[]
  for k in range(1,53):
   future_day=(d(sday)+dt.timedelta(weeks=k)).isoformat()
   if future_day not in w:raise SystemExit("V817_WEEKLY_PRICE_MISSING")
   nxt.append(w[future_day]["btcFixingPriceUSD"])
  outs={
    "UP13":max(nxt[:13])>=price*1.2,
    "UP26":max(nxt[:26])>=price*1.5,
    "UP52":max(nxt)>=price*2,
    "DOWN13":x["btc"]["future"]["13"]["worstDailyClosePct"]<=-20,
    "DOWN26":x["btc"]["future"]["26"]["worstDailyClosePct"]<=-35,
    "DOWN52":x["btc"]["future"]["52"]["worstDailyClosePct"]<=-50,
    "POSITIVE13":x["btc"]["future"]["13"]["returnPct"]>0,
    "POSITIVE26":x["btc"]["future"]["26"]["returnPct"]>0,
    "POSITIVE52":x["btc"]["future"]["52"]["returnPct"]>0}
  row={"date":sday,"era":phase(sday),"startingStructural":x["ctx"]["confirmed"],
   "btcPriceReferenceUSD":price,"NFCI":n,"ANFCI":j,"fed":x["fed"],"flags":flags,
   "outcomes":outs,
   "returns":{z:x["btc"]["future"][z]["returnPct"] for z in ("13","26","52")},
   "worstDailyFromStart":{z:x["btc"]["future"][z]["worstDailyClosePct"] for z in ("13","26","52")}}
  panel.append(row)
 if len(panel)<480:raise SystemExit("NOT_ENOUGH_VALID_2012_TO_2025_HISTORICAL_VINTAGES:"+str(len(panel)))
 if not any(z["date"]<"2013-01-01" for z in panel):raise SystemExit("NO_2012_HISTORICAL_ROWS")
 btc_only=[x for x in btc["weeklyRows"] if x["future"]["52"]["status"]=="OBSERVED"]
 basic={"n":len(btc_only),"first":btc_only[0]["date"],"last":btc_only[-1]["date"],
  "availableDailyStart":"2010-07-18","btcWeeklyTrendUp":sum(z["weeklyTrendConfirmed"] for z in btc_only),
  "btc13wClosePositive":sum(z["future"]["13"]["returnPct"]>0 for z in btc_only),
  "btc52wClosePositive":sum(z["future"]["52"]["returnPct"]>0 for z in btc_only)}
 byera={}
 for er in ("2012","2013-2016","2017-2019","2020-2023","2024-2025"):
  byera[er]=stats([x for x in panel if x["era"]==er])
 nonexp=[z for z in panel if z["startingStructural"]!="STRUCTURAL_EXPANSION_PRICE_PROXY"]
 locked={str(k):{m:stats(spaced(panel,m,k)) for m in MM} for k in (13,26)}
 risky=[x for x in panel if x["flags"]["STRICT_MACRO"] and x["outcomes"]["DOWN13"]]
 biggest=sorted(risky,key=lambda z:z["worstDailyFromStart"]["13"])[:16]
 falls=[x for x in panel if x["outcomes"]["DOWN26"]]
 shifts={"all":stats(panel),"notExpansion":stats(nonexp),"eras":byera,"lockout":locked,
   "btcPriceOnly":basic,"casesMacroBullButDown13":[{"date":z["date"],"return13":z["returns"]["13"],
    "drawdown13":z["worstDailyFromStart"]["13"],"flags":z["flags"]} for z in biggest],
   "casesDown26WithoutStrictNegative":sum(not x["flags"]["NEG_MACRO"] for x in falls),
   "deepFallsTotal26":len(falls)}
 report={"version":"8.17","status":"EXTENDED_HISTORICAL_FRED_VINTAGE_RISE_FALL_RESEARCH_ONLY",
   "researchOnly":True,"tradeApproval":False,"preregSha256":digest(prraw),
   "parents":expected,
   "historicalPriceOnlyBaseline":basic,"inputCoverage":{"macroCandidates":len(potential),
     "commonComplete":len(panel),"excluded":dict(excluded),"vintageFailures":missing,
     "first":panel[0]["date"],"last":panel[-1]["date"],
     "latestFullyObserved52wkOutcome":"2026-10-17"},
   "vintageArchives":archives,"results":shifts,
   "weeklyPanel":panel,
   "vintageCaveat":"FRED realtime Sunday as-of historical verified but intra-day original release timestamp not separately verified; weekly observations lag>=6d",
   "interpretation":["This is a retrospective previously inspected history, not a new OOS dataset or calibrated predictive forecast",
     "BTC PriceUSD is a reference fixing, not executable price; revisions to CoinMetrics historical fixings not original publication PIT verified",
     "A 52-week positive price-derived label is NOT a uniquely defined macro bull cycle",
     "14wk lockout does not imply independent global macro-regime observations",
     "2010 BTC daily observations available but 34wk weekly MA cannot be calculated until 2011, and FRED NFCI publication starts in 2011",
     "A positive macro signal before -20% drop is a model failure NOT a prediction of crash",
     "Declines measured vs signal Sunday price (NOT high-water peak-to-trough); forecasts across 13,26,52 windows not causally independent",
     "No trading simulation, no fees/slippage/risk sizing; liquidity proxy H4.1 archived pages may have been revised since historic publication",
     "No modification to MASTER Detector Spot Futures NAV P&L reserve capital risk limits"],
   "operationalChanged":{"Spot":False,"Futures":False,"NAV":False,"MASTER":False,
     "Detector":False,"Pnl":False,"limits":False}}
 folder=Path("btci_v817_reports");folder.mkdir(exist_ok=True)
 blob=json.dumps(report,ensure_ascii=False,indent=2).encode()
 (folder/"full_historical_rise_fall.json").write_bytes(blob)
 outfile=put(s,b,prefix+"full_historical_rise_fall.json",blob)
 manifest=put(s,b,prefix+"manifest.json",{"version":"8.17","researchOnly":True,
    "status":"BTC_LONG_HISTORY_MACRO_VINTAGE_PASS","preregSha256":digest(prraw),
    "parents":expected,"reportSha256":outfile["sha256"],"rawVintageArchiveSha256":archives})
 brief={"status":"V817_FULL_HISTORY_ASOF_PASS_READBACK_VERIFIED","prefix":prefix,
   "report":outfile,"manifest":manifest,"coverage":report["inputCoverage"],
   "btcOnly":basic,"results":{k:v for k,v in shifts.items() if k not in ("lockout",)},
   "locked":{p:{m:{"n":z["n"],"macroStrongRise":z["targets"]["UP26"],
     "crash":z["targets"]["DOWN26"],
     "model":z["models"][m]} for m,z in metrics.items()} for p,metrics in locked.items()}}
 (folder/"summary.json").write_text(json.dumps(brief,ensure_ascii=False,indent=2))
 print("V817_RESULT "+json.dumps({"status":brief["status"],"prefix":prefix,"reportSha256":outfile["sha256"],
   "manifestSha256":manifest["sha256"],"coverage":{k:v for k,v in report["inputCoverage"].items() if k!="vintageFailures"},
   "btcOnly":basic,"byera":{k:{"n":z["n"],"targets":z["targets"],
    "macro":{m:{"selected":z["models"][m]["selected"],"UP26":z["models"][m]["targets"]["UP26"],
      "DOWN26":z["models"][m]["targets"]["DOWN26"]} for m in ("A","STRICT_MACRO","STRICT_ALL","NEG_MACRO")}} for k,z in byera.items()},
   "all":{m:{"selected":shifts["all"]["models"][m]["selected"],
    "UP26":shifts["all"]["models"][m]["targets"]["UP26"],
    "DOWN26":shifts["all"]["models"][m]["targets"]["DOWN26"]} for m in MM},
   "downExamples":shifts["casesMacroBullButDown13"][:8]},ensure_ascii=False),flush=True)
if __name__=="__main__":main()
