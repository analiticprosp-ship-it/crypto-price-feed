#!/usr/bin/env python3
"""BTCI 8.18b, as-of-vintage US real yields, term spread, broad-dollar (2019+).
Non-fitted hypotheses; immutable v8.17.1 BTC strong up/down 26wk outcomes.
Historical research only. No trade or portfolio authority.
"""
import base64,collections,datetime as dt,hashlib,json,math,os,statistics,time,urllib.parse,urllib.request,urllib.error
from pathlib import Path
import boto3
ROOT=Path(__file__).resolve().parents[1]
PRE="research/btci_v818b_independent_macro_prereg_2026-10-19.json"
PARENT=("research/btci/v8.17.1/runs/39212878778-1/full_historical_rise_fall.json","539bcc1817a2120287497c2814d0344aae5d62714b4f35a36f30c2425e5d3091")
SOURCES=("DFII10","T10Y2Y","DTWEXBGS")
def sha(x):return hashlib.sha256(x).hexdigest()
def day(x):return dt.date.fromisoformat(x)
def rnd(x):return round(float(x),6) if x is not None else None
def client():
 return boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
def get(s,b,k,h):
 raw=s.get_object(Bucket=b,Key=k)["Body"].read()
 if sha(raw)!=h:raise SystemExit("V818B_PINNED_PARENT_MISMATCH")
 return json.loads(raw)
def put(s,b,k,blob,ctype="application/json"):
 raw=blob if isinstance(blob,bytes) else json.dumps(blob,ensure_ascii=False,indent=2).encode()
 h=sha(raw)
 s.put_object(Bucket=b,Key=k,Body=raw,ContentType=ctype,Metadata={"sha256":h,"research-only":"true"})
 if sha(s.get_object(Bucket=b,Key=k)["Body"].read())!=h:raise SystemExit("V818B_R2_READBACK_FAIL")
 return {"key":k,"sha256":h,"bytes":len(raw)}
def download(sym,vdates,key,batch):
 start=(day(vdates[0])-dt.timedelta(days=67)).isoformat()
 end=vdates[-1]
 args={"series_id":sym,"api_key":key,"file_type":"json","observation_start":start,"observation_end":end,
 "limit":"100000"}
 if batch:args.update(output_type="2",vintage_dates=",".join(vdates))
 else:args.update(realtime_start=vdates[0],realtime_end=vdates[0])
 url="https://api.stlouisfed.org/fred/series/observations?"+urllib.parse.urlencode(args)
 for attempt in range(6):
  try:
   request=urllib.request.Request(url,headers={"Accept":"application/json","User-Agent":"BTCI 8.18b original macro historical research"})
   with urllib.request.urlopen(request,timeout=60) as response:
    body=response.read(15000001)
   if len(body)>15000000:raise ValueError("FRED_RESPONSE_EXCEEDS_15MB")
   obj=json.loads(body)
   if not isinstance(obj.get("observations"),list) or obj.get("output_type")!= (2 if batch else 1):
    raise ValueError("API_RESPONSE_TYPE_UNEXPECTED")
   if obj["count"]>obj["limit"] or obj["count"]!=len(obj["observations"]):
    raise ValueError("API_LIMIT_OR_TRUNCATION")
   return obj,body
  except urllib.error.HTTPError as exc:
   if exc.code in (429,500,502,503,504) and attempt<5:
    time.sleep([3,6,12,24,42][attempt]);continue
   raise RuntimeError("FRED_HTTP_STATUS_"+str(exc.code)) from None
 raise RuntimeError("FRED_SOURCE_RETRY_EXHAUSTED")
def derive(sym,asof,rows,batch):
 if batch:
  col=sym+"_"+asof.replace("-","")
  values=[(z["date"],float(z[col])) for z in rows if col in z and z[col] not in (".","",None)]
 else:
  values=[(z["date"],float(z["value"])) for z in rows if z.get("value") not in (".","",None)]
 values.sort()
 if not values:return {"status":"NO_VINTAGE_OBSERVATIONS"}
 if len(values)<3:return {"status":"INSUFFICIENT_VINTAGE_OBSERVATIONS"}
 if len(set(z[0] for z in values))!=len(values):raise ValueError("DUPLICATE_OBSERVATION_DATE")
 if any(z[0]>asof or not math.isfinite(z[1]) for z in values):raise ValueError("FUTURE_DATE_OR_NONFINITE")
 last=values[-1]
 lag=(day(asof)-day(last[0])).days
 if not 2<=lag<=10:return {"status":"STALE_OR_FUTURE_LAST_OBSERVATION","latest":last[0],"lagDays":lag}
 prev=[z for z in values if 25<=(day(last[0])-day(z[0])).days<=35]
 if not prev:return {"status":"MISSING_PRIOR_4_WEEK_REFERENCE","latest":last[0]}
 before=min(prev,key=lambda z:(abs((day(last[0])-day(z[0])).days-28),-day(z[0]).toordinal()))
 delta=last[1]-before[1]
 return {"status":"ASOF_DATE_VERIFIED","asOf":asof,"series":sym,
  "latestDate":last[0],"latestValue":rnd(last[1]),"latestLagDays":lag,
  "priorDate":before[0],"priorValue":rnd(before[1]),"fourWeekDelta":rnd(delta),
  "fourWeekPct":rnd(100*delta/before[1]) if before[1]!=0 else None,
  "originalPublicationClockVerified":False}
def validate_single(sym,asof,batched,api_key):
 obj,raw=download(sym,[asof],api_key,False)
 single=derive(sym,asof,obj["observations"],False)
 if single!=batched:
  raise ValueError("BATCH_VINTAGE_NOT_EQUAL_INDIVIDUAL_SUNDAY_"+sym+"_"+asof)
 return sha(raw)
def report_stats(rows,models):
 targets=("UP26","DOWN26","POSITIVE26")
 base={"n":len(rows),"targetTotals":{t:sum(z["outcomes"][t] for z in rows) for t in targets},
 "baseRates":{t:rnd(sum(z["outcomes"][t] for z in rows)/len(rows)) if rows else None for t in targets},
 "models":{}}
 for name in models:
  sel=[r for r in rows if r["signals"][name]]
  part={"nSignals":len(sel),"medianBTC26weekPct":rnd(statistics.median(z["returns"]["26"] for z in sel)) if sel else None,"targets":{}}
  for tar in targets:
   tp=sum(x["outcomes"][tar] for x in sel);fp=len(sel)-tp;fn=base["targetTotals"][tar]-tp;tn=len(rows)-len(sel)-fn
   part["targets"][tar]={"TP":tp,"FP":fp,"FN":fn,"TN":tn,
    "precision":rnd(tp/len(sel)) if sel else None,
    "recall":rnd(tp/base["targetTotals"][tar]) if base["targetTotals"][tar] else None}
  base["models"][name]=part
 return base
def intervals(rows,model,lock):
 out=[];last=None
 for r in rows:
  if not r["signals"][model]:continue
  now=day(r["date"])
  if last is None or (now-last).days>=7*(lock+1):
   out.append(r);last=now
 return out
def main():
 freeze=(ROOT/PRE).read_bytes();pr=json.loads(freeze)
 if pr["version"]!="8.18b" or pr["parentKey"]!=PARENT[0] or pr["parentSha256"]!=PARENT[1]:
  raise SystemExit("V818B_PREREGISTRATION_MISMATCH")
 key=os.environ["FRED_API_KEY"]
 import re
 if not re.fullmatch("[a-z0-9]{32}",key):raise SystemExit("V818B_FRED_API_KEY_BAD_SECRET")
 s=client();b=os.environ["R2_BUCKET"]
 p=get(s,b,*PARENT)
 if p["version"]!="8.17.1" or len(p["weeklyPanel"])!=684:raise SystemExit("V818B_PARENT_HISTORY_NOT_FROZEN")
 rawrows=p["weeklyPanel"]
 dates=[z["date"] for z in rawrows]
 if dates!=sorted(set(dates)) or dates[0]>"2012-12-31" or dates[-1]<"2025-01-01":
  raise SystemExit("V818B_PARENT_DATES_INVALID")
 prefix=f"research/btci/v8.18b/runs/{os.environ['GITHUB_RUN_ID']}-{os.environ.get('GITHUB_RUN_ATTEMPT','1')}/"
 sources={};archives={};access={};singles={}
 for sym in SOURCES:
  eligible=[dte for dte in dates if sym!="DTWEXBGS" or dte>="2019-02-10"]
  derived={};records=[];blocked=collections.Counter()
  for at in range(0,len(eligible),32):
   group=eligible[at:at+32]
   result,raw=download(sym,group,key,True)
   for sunday in group:
    v=derive(sym,sunday,result["observations"],True)
    derived[sunday]=v
    if v["status"]!="ASOF_DATE_VERIFIED":blocked[v["status"]]+=1
   records.append({"vintages":group,"responseSha256":sha(raw),
    "responseBase64":base64.b64encode(raw).decode()})
   time.sleep(0.7)
  for check in (("2018-10-07" if sym!="DTWEXBGS" else "2020-10-11"),"2024-10-06"):
   if check in derived:
    # Independently re-query same official vintage to guard multi-output schema mismatch.
    v,raw=download(sym,[check],key,False)
    single=derive(sym,check,v["observations"],False)
    if derived[check]!=single:raise SystemExit("V818B_BATCH_VS_SINGLE_MISMATCH_"+sym+"_"+check)
    singles[sym+"_"+check]=sha(raw)
  archive=("\n".join(json.dumps(z,ensure_ascii=False,separators=(",",":")) for z in records)+"\n").encode()
  ap=put(s,b,prefix+"source/"+sym+"_batched_vintages.jsonl",archive,"application/x-ndjson")
  archives[sym]={**ap,"chunks":len(records),"requested":len(eligible),
   "validated":sum(x["status"]=="ASOF_DATE_VERIFIED" for x in derived.values()),
   "rejected":dict(blocked)}
  sources[sym]=derived
  print("V818B_SERIES",sym,archives[sym]["validated"],"/",len(eligible),
   "chunks",len(records),"rejected",dict(blocked),flush=True)
  if archives[sym]["validated"]< min(200,int(len(eligible)*.6)):
   raise SystemExit("V818B_SOURCE_COVERAGE_TOO_LOW_"+sym)
 output=[]
 for r in rawrows:
  D=r["date"];rate=sources["DFII10"].get(D);curve=sources["T10Y2Y"].get(D)
  usd=sources["DTWEXBGS"].get(D)
  if not rate or rate["status"]!="ASOF_DATE_VERIFIED":continue
  if not curve or curve["status"]!="ASOF_DATE_VERIFIED":continue
  A=bool(r["flags"]["A"]);F=bool(r["flags"]["F"]);N=bool(r["flags"]["N"]);J=bool(r["flags"]["J"])
  down=rate["fourWeekDelta"]<0;rise=rate["fourWeekDelta"]>0
  uok=usd is not None and usd["status"]=="ASOF_DATE_VERIFIED"
  udn=uok and usd["fourWeekDelta"]<0;uup=uok and usd["fourWeekDelta"]>0
  signal={
    "A":A,"BASE_MACRO_ALL":A and F and N and J,"R_EASE":down,"R_TIGHT":rise,
    "A_R_EASE":A and down,"A_F_R_EASE":A and F and down,
    "A_ALL_R_EASE":A and F and N and J and down,
    "NOA_R_TIGHT":not A and rise,
    "NOA_ALL_TIGHT":not A and not F and not N and not J,
    "NOA_ALL_TIGHT_R":not A and not F and not N and not J and rise,
    "YC_FLATTEN":curve["fourWeekDelta"]<0,
    "YC_INVERTED":curve["latestValue"]<0,
    "A_R_USD_EASE":A and down and udn,
    "NOA_R_USD_TIGHT":not A and rise and uup,
    "USD_TIGHT":bool(uup),"USD_EASE":bool(udn)
  }
  output.append({"date":D,"era":r["era"],"signals":signal,
    "realYield":rate,"treasurySpread":curve,
    "dollar":usd if uok else {"status":"UNAVAILABLE_AT_DATE"},
    "outcomes":{k:r["outcomes"][k] for k in ("UP13","UP26","UP52","DOWN13","DOWN26","DOWN52","POSITIVE13","POSITIVE26","POSITIVE52")},
    "returns":r["returns"],"priceOnlyRisk":{"A":A,"F":F,"N":N,"J":J}})
 if len(output)<450:raise SystemExit("V818B_TOO_FEW_COMPLETE_RATE_CURVE_DATES_"+str(len(output)))
 early=[z for z in output if z["date"]<"2019-02-10"]
 newer=[z for z in output if z["dollar"]["status"]=="ASOF_DATE_VERIFIED"]
 if len(newer)<180:raise SystemExit("V818B_TOO_FEW_PIT_USD_DATES_"+str(len(newer)))
 names_basic=("A","BASE_MACRO_ALL","R_EASE","R_TIGHT","A_R_EASE","A_F_R_EASE",
 "A_ALL_R_EASE","NOA_R_TIGHT","NOA_ALL_TIGHT","NOA_ALL_TIGHT_R",
 "YC_FLATTEN","YC_INVERTED")
 names_new=names_basic+("USD_TIGHT","USD_EASE","A_R_USD_EASE","NOA_R_USD_TIGHT")
 allstat=report_stats(output,names_basic)
 dollarstat=report_stats(newer,names_new)
 byera={t:report_stats([z for z in output if z["era"]==t],names_basic)
        for t in ("2012","2013-2016","2017-2019","2020-2023","2024-2025")}
 lock={}
 for gap in (13,26):
  lock[str(gap)]={name:{"firstSignalDates":[z["date"] for z in selected],
    "outcomes":report_stats(selected,(name,))} for name in names_basic
    for selected in [intervals(output,name,gap)]}
 comparisons={}
 for dataset_name,dataset in (("full_rates",output),("2019plus_dollar",newer)):
  baseA=[z for z in dataset if z["signals"]["A"]]
  rateA=[z for z in baseA if z["signals"]["R_EASE"]]
  comparisons[dataset_name]={
    "A_selected":len(baseA),"A_and_R_EASE_selected":len(rateA),
    "A_conditional_down26":rnd(sum(x["outcomes"]["DOWN26"] for x in baseA)/len(baseA)) if baseA else None,
    "A_R_EASE_conditional_down26":rnd(sum(x["outcomes"]["DOWN26"] for x in rateA)/len(rateA)) if rateA else None,
    "A_conditional_up26":rnd(sum(x["outcomes"]["UP26"] for x in baseA)/len(baseA)) if baseA else None,
    "A_R_EASE_conditional_up26":rnd(sum(x["outcomes"]["UP26"] for x in rateA)/len(rateA)) if rateA else None
  }
 report={"version":"8.18b","status":"ORIGINAL_FRED_INDEPENDENT_RATE_CURVE_USD_FACTOR_ABLATION_RESEARCH",
  "researchOnly":True,"noTradingAuthority":True,
  "parent":{"key":PARENT[0],"sha256":PARENT[1]},
  "preregistration":{"path":PRE,"sha256":sha(freeze)},
  "sample":{"parentWeeks":len(rawrows),"completeRateAndCurve":len(output),
    "valid2019DollarSubset":len(newer),"rateCurveBefore2019":len(early),
    "start":output[0]["date"],"end":output[-1]["date"]},
  "historicalSourceArchives":archives,"batchComparedAgainstIndividualHistoricalSundays":singles,
  "metrics":{"ratesAndCurve":allstat,"withDollarFrom2019":dollarstat,
    "historicalEras":byera,"nonoverlapLockouts":lock,
    "A_baselineVsRealRate":comparisons},
  "weeklyPanel":output,
  "methodCaveats":[
   "FRED original Sunday as-of vintages verified, but original intraday publication times not separately checked.",
   "DTWEXBGS first appeared in 2019 and is NOT an available historical predictor for 2012-2018 despite retrospective observation labels.",
   "Spread inversion may not be a BTC crash signal; sign and thresholds frozen before scoring.",
   "Real yield and dollar may co-move with risk appetite, not independent of Chicago Fed conditions.",
   "No real out-of-sample years; macro outcomes still overlap in 13,26,52 week windows. Lockouts reduce overlap but small event count.",
   "BTC price reference is CoinMetrics historical PriceUSD, not trade execution; no performance simulation fees/leverage/slippage.",
   "No trading orders or changes to Spot Futures NAV PnL MASTER capital reserve or limits."],
  "operations":{"Spot":False,"Futures":False,"NAV":False,"Pnl":False,"capital":False,
   "reserve":False,"MASTER":False,"Detector":False,"limits":False}}
 directory=Path("btci_v818b_reports");directory.mkdir(exist_ok=True)
 blob=json.dumps(report,ensure_ascii=False,indent=2).encode()
 (directory/"rate_curve_usd_research.json").write_bytes(blob)
 report_item=put(s,b,prefix+"rate_curve_usd_research.json",blob)
 man=put(s,b,prefix+"manifest.json",{
  "version":"8.18b","status":"HISTORICAL_RATE_CURVE_DOLLAR_ABLATION_PASS",
  "reportSha256":report_item["sha256"],"preregSha256":sha(freeze),
  "parents":[PARENT[0]],"sourceArchives":archives,"researchOnly":True})
 brief={"status":"V818B_ABLATION_PASS_R2_READBACK_VERIFIED","prefix":prefix,"report":report_item,
  "manifest":man,"sample":report["sample"],"archives":archives,"comparisons":comparisons,
  "full":{name:{"selected":z["nSignals"],"up":z["targets"]["UP26"],
          "down":z["targets"]["DOWN26"]} for name,z in allstat["models"].items()},
  "dollar":{name:{"selected":z["nSignals"],"up":z["targets"]["UP26"],
          "down":z["targets"]["DOWN26"]} for name,z in dollarstat["models"].items()},
  "eras":{name:{"n":v["n"],"A":v["models"]["A"],
    "A_R_EASE":v["models"]["A_R_EASE"],"NOA_R_TIGHT":v["models"]["NOA_R_TIGHT"]}
    for name,v in byera.items()}}
 (directory/"summary.json").write_text(json.dumps(brief,ensure_ascii=False,indent=2))
 print("V818B_RESULT "+json.dumps(brief,ensure_ascii=False),flush=True)
if __name__=="__main__":main()
