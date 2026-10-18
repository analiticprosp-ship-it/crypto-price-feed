#!/usr/bin/env python3
"""Research v8.0: full historical phase transition review using fixed v7.9 rules.
Only closed UTC market bars; no orders, trading system, NAV, futures or portfolio changes.
"""
import argparse,ast,calendar,csv,hashlib,io,json,os,statistics,sys,zipfile
from datetime import datetime,timedelta,date,timezone
from pathlib import Path
from collections import Counter,defaultdict
import boto3

ROOT=Path(__file__).resolve().parents[1]
ASSETS=("BTC","ETH","SOL","BNB","LINK","XRP","ADA","DOGE")
ALTS=("SOL","BNB","LINK","XRP","ADA","DOGE")
HORIZONS=(7,14,30,90,180,365)
PREREG="research/detector_v80_phase_transition_prereg_2026-10-18.json"
REFS={
"v75":("research/detector/v7.5/runs/39115280960-1/combined/comparison.json","07fccb39f6973c2f6f4fb297dc4d3d95cd6e3c06fca154a503c97e242f080e8f"),
"v76":("research/detector/v7.6/runs/39115615591-1/combined/comparison.json","1d8fd630f7fc0aec6e8308128a79f66344343b0d8a5b14280b6a58507340a95c"),
"v79":("research/detector/v7.9/runs/39123839080-1/combined/regime.json","f0ab8e67b10823d7ad30dce83187392b614f7ed6926888be588322796520cd9b")
}
DATE_END=date(2026,10,17)
PHASES=("BTC_BULL_PRICE_TREND","BTC_BEAR_PRICE_TREND","RECOVERY_NOT_CONFIRMED","CONSOLIDATION_OR_TRANSITION")
RISKS=("RISK_ON_PRICE_PROXY","RISK_OFF_PRICE_PROXY","MIXED_PRICE_PROXY")
def sha(raw):return hashlib.sha256(raw).hexdigest()
def round6(x):return round(float(x),6) if x is not None else None
def pref():return f"research/detector/v8.0/runs/{os.environ['GITHUB_RUN_ID']}-{os.environ.get('GITHUB_RUN_ATTEMPT','1')}/"
def s3():
 return boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
 aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
 aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
def get(s,b,key,digest):
 raw=s.get_object(Bucket=b,Key=key)["Body"].read()
 if sha(raw)!=digest:raise SystemExit("V80_BAD_SHA:"+key)
 return json.loads(raw)
def write(s,b,key,content):
 raw=content if isinstance(content,bytes) else json.dumps(content,ensure_ascii=False,indent=2).encode()
 h=sha(raw)
 s.put_object(Bucket=b,Key=key,Body=raw,ContentType="application/json",
 Metadata={"sha256":h,"research-only":"true"})
 if sha(s.get_object(Bucket=b,Key=key)["Body"].read())!=h:raise SystemExit("V80_BAD_R2_READBACK:"+key)
 return h
def prereg():
 raw=(ROOT/PREREG).read_bytes()
 j=json.loads(raw)
 if j["version"]!="8.0" or j["market"]!=list(ASSETS) or list(j["sourceReports"])!=["v75","v76","v79"]:
  raise SystemExit("V80_PREREG_CHANGED")
 for k in REFS:
  if (j["sourceReports"][k]["key"],j["sourceReports"][k]["sha256"])!=REFS[k]:
   raise SystemExit("V80_PINNED_REFERENCE_CHANGED")
 return sha(raw)
def references(s,b):
 v75=get(s,b,*REFS["v75"])
 v76=get(s,b,*REFS["v76"])
 v79=get(s,b,*REFS["v79"])
 if (v75["version"],v76["version"],v79["version"])!=("7.5","7.6","7.9"):
  raise SystemExit("V80_BAD_REF_VERSIONS")
 return v75,v76,v79
def read_month_fn():
 t=ast.parse((ROOT/"research/detector_matched_controls_v65.py").read_text())
 f=next(x for x in t.body if isinstance(x,ast.FunctionDef) and x.name=="read_month")
 globals_={"hashlib":hashlib,"csv":csv,"io":io,"zipfile":zipfile,"P5":300000}
 exec(compile(ast.Module(body=[f],type_ignores=[]),"<fixed-v65-month-reader>","exec"),globals_)
 return globals_["read_month"]
def archived_hashes(s,b,sym,v75,v76):
 if sym in ("BTC","ETH"):
  rows=[]
  for record in v75["sourceYears"]:
   rows.extend(get(s,b,record["prefix"]+"records.json",record["recordsSha256"]))
 else:
  source=next(x for x in v76["sources"] if x["symbol"]==sym)
  rows=get(s,b,source["prefix"]+"records.json",source["recordsSha256"])
  if len(rows)!=v76["sourceCoverage"][sym]["fullValidated"]:
   raise SystemExit("V80_ALT_VALIDATED_MONTHS_CHANGED")
 data={x["month"]:x["sourceSha256"] for x in rows if x["symbol"]==sym}
 if len(data)!=81 and sym in ("BTC","ETH"):raise SystemExit("V80_BTC_ETH_INCOMPLETE")
 return data
def eachasset(sym):
 ps=prereg();s=s3();b=os.environ["R2_BUCKET"]
 v75,v76,v79=references(s,b)
 old=archived_hashes(s,b,sym,v75,v76)
 reader=read_month_fn()
 daily={};sources=[]
 for month,digest_expected in sorted(old.items()):
  data,digest=reader(s,b,sym,month)
  if digest!=digest_expected:raise SystemExit("V80_ARCHIVE_SHA_MISMATCH:"+sym+"/"+month)
  y,m=map(int,month.split("-"))
  future=f"{y+1}-01" if m==12 else f"{y}-{m+1:02d}"
  if (datetime.fromtimestamp(data[0]["t"]/1000,timezone.utc)!=datetime.fromisoformat(month+"-01").replace(tzinfo=timezone.utc) or
      datetime.fromtimestamp(data[-1]["endMs"]/1000,timezone.utc)!=datetime.fromisoformat(future+"-01").replace(tzinfo=timezone.utc)):
   raise SystemExit("V80_MONTH_NOT_FULL:"+sym+"/"+month)
  bucket={}
  for bar in data:
   day=datetime.fromtimestamp((bar["endMs"]-1)/1000,timezone.utc).date().isoformat()
   bucket[day]=bar["c"]
  if len(bucket)!=calendar.monthrange(y,m)[1]:raise SystemExit("V80_NOT_ALL_DAYS")
  daily.update(bucket)
  sources.append({"month":month,"sha256":digest})
 # Reuse a separately verified v7.9 source for the Oct1-17 2026 closed daily candles.
 src=next(x for x in v79["provenance"] if x["symbol"]==sym)
 root="research/detector/v7.9/runs/39123839080-1/assets/"+sym+"/"
 v79series=get(s,b,root+"daily_closes.json",src["sha256"])
 if v79series[-1]["day"]!="2026-10-17":raise SystemExit("V80_CURRENT_CUTOFF_MISMATCH")
 nmatch=0
 for point in v79series:
  day=point["day"]
  if day in daily:
   if abs(daily[day]-point["close"])>0.0000001:raise SystemExit("V80_V79_OVERLAP_CROSSCHECK:"+sym+"/"+day)
   nmatch+=1
  elif day.startswith("2026-10-") and day<="2026-10-17":
   daily[day]=point["close"]
  elif day>= "2025-10-01" and day <= "2026-09-30":
   raise SystemExit("V80_SNAPSHOT_OVERLAP_ARCHIVE_MISSING:"+sym+"/"+day)
 if nmatch!=365:
  raise SystemExit("V80_BAD_V79_OVERLAP_DAY_COUNT:"+sym+"/"+str(nmatch))
 if sym in ("BTC","ETH") and len(daily)!= (DATE_END-date(2020,1,1)).days+1:
  raise SystemExit("V80_BTC_ETH_DAYS_MISSING:"+sym)
 values=[{"day":key,"close":daily[key]} for key in sorted(daily)]
 if values[-1]["day"]!="2026-10-17":raise SystemExit("V80_NO_CURRENT_DAY:"+sym)
 root=pref()+"assets/"+sym+"/"
 dsha=write(s,b,root+"daily.json",values)
 meta={"version":"8.0","asset":sym,"researchOnly":True,"dailySha256":dsha,
   "validatedMonths":len(old),"v79OverlapDays":nmatch,"dayCount":len(values),
   "preregSha256":ps,"sources":sources,"v79DailySeriesSha256":src["sha256"],"prefix":root}
 msha=write(s,b,root+"manifest.json",meta)
 out={"status":"V80_FULL_SOURCE_PASS","asset":sym,"dayCount":len(values),
  "validatedMonths":len(old),"manifestSha256":msha,"prefix":root}
 folder=Path("detector_v80_reports");folder.mkdir(exist_ok=True)
 (folder/(sym+".json")).write_text(json.dumps(out,ensure_ascii=False,indent=2))
 print(json.dumps(out,ensure_ascii=False),flush=True)
def evaluate(raw,idx):
 btc=raw["BTC"]
 if idx<230 or any(btc.get(idx-j) is None for j in range(0,231)):
  return None
 def getbtc(back):return btc[idx-back]
 close=getbtc(0)
 def avg(n,shift=0):return sum(btc[idx-shift-i] for i in range(n))/n
 m50=avg(50);m200=avg(200);m200prior=avg(200,30)
 slope=100*(m200/m200prior-1)
 r30=100*(close/getbtc(30)-1)
 r90=100*(close/getbtc(90)-1)
 ddbars=min(idx+1,365)
 drawdown=100*(close/max(btc[idx-j] for j in range(ddbars))-1)
 higher_h=max(btc[idx-i] for i in range(30))>max(btc[idx-i] for i in range(30,60))
 higher_l=min(btc[idx-i] for i in range(30))>min(btc[idx-i] for i in range(30,60))
 if close>m200 and slope>0 and r90>0:
  phase="RECOVERY_NOT_CONFIRMED" if drawdown<=-25 else "BTC_BULL_PRICE_TREND"
 elif close<m200 and slope<0 and r90<0:phase="BTC_BEAR_PRICE_TREND"
 elif close<m200 and r90>0:phase="RECOVERY_NOT_CONFIRMED"
 else:phase="CONSOLIDATION_OR_TRANSITION"
 prior_btc=btc[idx-30]
 risk="RISK_UNAVAILABLE"
 v=None;score=None;rs=None;outperf=None;up=None
 if (raw["ETH"].get(idx) is not None and raw["ETH"].get(idx-30) is not None and
  all(raw[s].get(idx) is not None and raw[s].get(idx-30) is not None for s in ALTS)):
  eth_ret=raw["ETH"][idx]/raw["ETH"][idx-30]-1
  btc_ret=close/prior_btc-1
  rs={"ETH":100*((1+eth_ret)/(1+btc_ret)-1)}
  for s in ALTS:
   r=raw[s][idx]/raw[s][idx-30]-1
   rs[s]=100*((1+r)/(1+btc_ret)-1)
  outperf=sum(rs[s]>0 for s in ALTS)
  up=sum(raw[s][idx]>raw[s][idx-30] for s in ALTS)
  v={"btcPriceMomentum":1 if close>m50 and r30>0 else (-1 if close<m50 and r30<0 else 0),
      "ETHvsBTC30d":1 if rs["ETH"]>0 else -1,
      "altBreadthVsBTC":1 if outperf>=4 else (-1 if outperf<=2 else 0),
      "altUSDPositiveBreadth":1 if up>=4 else (-1 if up<=2 else 0)}
  score=sum(v.values())
  risk="RISK_ON_PRICE_PROXY" if score>=3 else ("RISK_OFF_PRICE_PROXY" if score<=-2 else "MIXED_PRICE_PROXY")
 return {"phase":phase,"risk":risk,"riskScore":score,
  "phaseIndicators":{"closeFuturesNonExecutable":close,"sma50":round6(m50),"sma200":round6(m200),
    "sma200Slope30Pct":round6(slope),"return30Pct":round6(r30),"return90Pct":round6(r90),
    "drawdown365ClosePct":round6(drawdown),"drawdownWindowDays":ddbars,
    "higher30dHigh":higher_h,"higher30dLow":higher_l},
  "riskVotes":v,"altOutperformCount":outperf,"altUSDPositiveCount":up,
  "ethRelative30Pct":round6(rs["ETH"]) if rs else None}
def collect_state(records,key,unknown=None):
 """Confirm a transition on day 7 of a continuous observed new raw state.
 No backdating to candidate day. Missing suspends but does not rewrite old state.
 """
 confirmed=None;rawprev=None;streak=0
 transitions=[];confirmedByDay={}
 for i,rec in enumerate(records):
  if rec is None:
   rawprev=None;streak=0;continue
  raw=rec[key]
  if raw is None or raw==unknown:
   rawprev=None;streak=0
   confirmedByDay[i]=confirmed
   continue
  if raw!=rawprev:rawprev=raw;streak=1
  else:streak+=1
  if streak==7 and raw!=confirmed:
   transitions.append({"idx":i,"date":rec["date"],"from":confirmed,"to":raw,
                       "confirmedConsecutiveDays":7})
   confirmed=raw
  confirmedByDay[i]=confirmed
 return transitions,confirmedByDay
def summary(values):
 if not values:return {"n":0,"mean":None,"median":None,"positivePct":None}
 return {"n":len(values),"mean":round6(statistics.mean(values)),
    "median":round6(statistics.median(values)),
    "positivePct":round6(100*sum(v>0 for v in values)/len(values))}
def outcomes(transitions, btc, horizon):
 for item in transitions:
  i=item["idx"];base=btc[i]
  result={}
  for days in horizon:
   if i+days>=len(btc):
    result[str(days)]={"status":"RIGHT_CENSORED"}
   else:
    f=btc[i+days]
    window=btc[i+1:i+days+1]
    result[str(days)]={"status":"OBSERVED","returnPct":round6(100*(f/base-1)),
      "maxAdverseClosePct":round6(100*(min(window)/base-1)),
      "maxFavorableClosePct":round6(100*(max(window)/base-1))}
  item["future"]=result
def event_summary(items):
 out={"totalEvents":len(items)}
 for h in HORIZONS:
  nums=[e["future"][str(h)]["returnPct"] for e in items if e["future"][str(h)]["status"]=="OBSERVED"]
  out[str(h)]={**summary(nums),"censored":len(items)-len(nums)}
  if len(nums)<20:out[str(h)]["inferenceStatus"]="LOW_SAMPLE_NO_PREDICTIVE_CLAIM"
  else:out[str(h)]["inferenceStatus"]="RETROSPECTIVE_DESCRIPTIVE_ONLY"
 return out
def combine():
 ps=prereg();s=s3();b=os.environ["R2_BUCKET"]
 v75,v76,v79=references(s,b)
 series={};metas={}
 start=date(2020,1,1);dates=[(start+timedelta(days=i)).isoformat() for i in range((DATE_END-start).days+1)]
 for sym in ASSETS:
  root=pref()+"assets/"+sym+"/"
  meta=json.loads(s.get_object(Bucket=b,Key=root+"manifest.json")["Body"].read())
  if meta["version"]!="8.0" or meta["preregSha256"]!=ps or meta["asset"]!=sym:
   raise SystemExit("V80_BAD_ASSET_MANIFEST")
  rows=get(s,b,root+"daily.json",meta["dailySha256"])
  series[sym]={x["day"]:x["close"] for x in rows}
  metas[sym]={"sourceDailySha256":meta["dailySha256"],
     "validMonths":meta["validatedMonths"],"validDays":meta["dayCount"]}
 btc=[series["BTC"].get(day) for day in dates]
 if any(x is None for x in btc):raise SystemExit("V80_BTC_GAP")
 raw={sym:{i:series[sym][d] for i,d in enumerate(dates) if d in series[sym]}
      for sym in ASSETS}
 recs=[]
 for i,day in enumerate(dates):
  result=evaluate(raw,i)
  recs.append({"date":day,**result} if result else None)
 ready=[x for x in recs if x is not None]
 if not ready:raise SystemExit("V80_NO_RESEARCH_PERIOD")
 main_trans,phase_byday=collect_state(recs,"phase")
 risk_trans,risk_byday=collect_state(recs,"risk","RISK_UNAVAILABLE")
 for collection in (main_trans,risk_trans):outcomes(collection,btc,HORIZONS)
 for collection in (main_trans,risk_trans):
  for j,e in enumerate(collection):
   e["durationUntilNextConfirmationDays"]=(collection[j+1]["idx"]-e["idx"]
           if j<len(collection)-1 else None)
   e["phaseAtTransition"]=phase_byday.get(e["idx"])
   e["riskAtTransition"]=risk_byday.get(e["idx"])
   e["btcPriceNonExecutable"]=round6(btc[e["idx"]])
   e["revertedWithin30Days"]=(
       collection[j+1]["idx"]-e["idx"]<=30 if j<len(collection)-1 else None)
 # 7-close SMA200 price crossover baseline (same delay)
 reference=[None]*len(btc)
 for i in range(199,len(btc)):
  m=sum(btc[i-199:i+1])/200
  reference[i]={"date":dates[i],"cross":"ABOVE200" if btc[i]>m else "BELOW200"}
 base_events,_=collect_state(reference,"cross")
 outcomes(base_events,btc,HORIZONS)
 daily=[]
 lastphase=lastrisk=None
 for i,row in enumerate(recs):
  if row is None:continue
  confirmed_phase=phase_byday.get(i)
  confirmed_risk=risk_byday.get(i)
  daily.append({"date":row["date"],"phaseRaw":row["phase"],
   "phaseConfirmed":confirmed_phase,"riskRaw":row["risk"],
   "riskConfirmed":confirmed_risk,
   "riskScore":row["riskScore"],"sma200":row["phaseIndicators"]["sma200"],
   "price":row["phaseIndicators"]["closeFuturesNonExecutable"],
   "return90Pct":row["phaseIndicators"]["return90Pct"],
   "drawdown365ClosePct":row["phaseIndicators"]["drawdown365ClosePct"],
   "drawdownWindowDays":row["phaseIndicators"]["drawdownWindowDays"]})
 latest=recs[-1]
 if latest["date"]!="2026-10-17" or any(latest["phaseIndicators"][k] is None for k in ("sma200","return90Pct")):
  raise SystemExit("V80_LATEST_INCOMPLETE")
 # Verify identical fixed-v79 current raw phase and risk without any tuning
 if latest["phase"]!=v79["btcPhase"] or latest["risk"]!=v79["riskAppetiteProxy"]:
  raise SystemExit("V80_V79_CURRENT_PHASE_PARITY_FAILED")
 if latest["riskScore"]!=v79["riskScore"]:
  raise SystemExit("V80_V79_RISK_SCORE_PARITY_FAILED")
 byyear={}
 for year in range(2020,2027):
  subset=[x for x in daily if x["date"].startswith(str(year))]
  byyear[str(year)]={"eligibleDays":len(subset),
     "rawPhaseCounts":dict(Counter(x["phaseRaw"] for x in subset)),
     "confirmedPhaseCounts":dict(Counter(x["phaseConfirmed"] for x in subset)),
     "rawRiskCounts":dict(Counter(x["riskRaw"] for x in subset))}
 byphase={}
 for phase in PHASES:
  byphase[phase]=event_summary([e for e in main_trans if e["to"]==phase])
 by_risk={}
 for risk in RISKS:
  by_risk[risk]=event_summary([e for e in risk_trans if e["to"]==risk])
 table=defaultdict(int)
 for e in main_trans:table[e["to"]+" / "+str(e.get("riskAtTransition"))]+=1
 durations={phase:summary([e["durationUntilNextConfirmationDays"] for e in main_trans
  if e["to"]==phase and e["durationUntilNextConfirmationDays"] is not None]) for phase in PHASES}
 latest_p=phase_byday.get(len(dates)-1)
 latest_r=risk_byday.get(len(dates)-1)
 latest_phase_event=next((e for e in reversed(main_trans) if e["to"]==latest_p),None)
 latest_risk_event=next((e for e in reversed(risk_trans) if e["to"]==latest_r),None)
 # Historical 'max adverse' after transitions can be strongly negative despite positive later horizons.
 out={"version":"8.0","status":"FULL_HISTORICAL_PHASE_TRANSITIONS_RESEARCH_ONLY",
  "researchOnly":True,"tradesEmitted":0,"lookaheadProtection":"Daily stage calculated solely from closed bars at UTC day t, 7-day persistence confirmed only at 7th day, future used only in outcomes",
  "preregistration":{"path":PREREG,"sha256":ps},
  "sources":{"v75":REFS["v75"],"v76":REFS["v76"],"v79":REFS["v79"],"assets":metas},
  "window":{"firstDataUTC":"2020-01-01","lastDataUTC":"2026-10-17",
   "firstEligiblePhaseUTC":daily[0]["date"],
   "eligiblePhaseDays":len(daily),
   "earlyDrawdownContext":"Rolling365 high has incomplete lookback in first 365 days and is explicitly marked per day",
   "lastUtcDayClosed":True},
  "latest":{"date":latest["date"],"rawPhase":latest["phase"],"confirmedPhase":latest_p,
   "rawRisk":latest["risk"],"confirmedRisk":latest_r,
   "currentRiskScore":latest["riskScore"],
   "indicators":latest["phaseIndicators"],
   "riskVotes":latest["riskVotes"],"outperformingAlts":latest["altOutperformCount"],
   "positiveAlts":latest["altUSDPositiveCount"],
   "lastConfirmedPhaseTransition":{k:v for k,v in latest_phase_event.items() if k not in ("future","idx")} if latest_phase_event else None,
   "lastConfirmedRiskTransition":{k:v for k,v in latest_risk_event.items() if k not in ("future","idx")} if latest_risk_event else None},
  "transitions":{"phaseCount":len(main_trans),
     "riskCount":len(risk_trans),"phaseEvents":main_trans,
     "riskEvents":risk_trans,
     "phaseTransitionMatrix":dict(table),
     "phaseDurationsUntilNextConfirmation":durations},
  "outcomeComparisons":{"byConfirmedPhaseEntry":byphase,
   "byConfirmedRiskEntry":by_risk,
   "naiveSevenDayAboveBelowSMA200":{"count":len(base_events),
       "byAbove":event_summary([e for e in base_events if e["to"]=="ABOVE200"]),
       "byBelow":event_summary([e for e in base_events if e["to"]=="BELOW200"])},
   "horizonsDays":list(HORIZONS),
   "rightCensoringRule":"Future horizon not computed unless entire future closed-day window available",
   "inference":"No causal profits, no statistically independent forward holdout"},
  "annualCounts":byyear,
  "pastOnlyDailyTimelines":daily,
  "limitations":["Fixed v7.9 classification is an exploratory heuristic created after inspecting the market; NOT a prospective out-of-sample signal",
   "Only one Binance USDM futures market, not multi-venue spot, and no executable price or fee model",
   "Five years after 2020 have full 365d rolling context; earliest eligible 2020 labels have shortened drawdown window",
   "Future returns of transitions overlap and are correlated; low transition counts should not be used as probabilities",
   "Risk appetite is an eight-asset PRICE proxy, not authenticated macro liquidity, institutional allocations or ETF flows",
   "Alt archive gaps before listing create RISK_UNAVAILABLE, not imputed scores",
   "Cycle and risk labels are related but not identical, and no trading authority is granted",
   "No NAV, capital, reserve, Spot/Futures or live Detector writes"]}
 folder=Path("detector_v80_reports");folder.mkdir(exist_ok=True)
 full=json.dumps(out,ensure_ascii=False,indent=2).encode()
 (folder/"phase_transitions.json").write_bytes(full)
 brief={"version":"8.0","status":"V80_PHASE_TRANSITIONS_RESEARCH_PASS_WRITEBACK_VERIFIED",
  "latest":out["latest"],"phaseEvents":len(main_trans),"riskEvents":len(risk_trans),
  "byPhase":byphase,"byRisk":by_risk,"phaseCountByYear":byyear,
  "recentPhaseTransitions":[{k:v for k,v in e.items() if k in ("date","from","to","durationUntilNextConfirmationDays","btcPriceNonExecutable","riskAtTransition")} for e in main_trans[-12:]],
  "recentRiskTransitions":[{k:v for k,v in e.items() if k in ("date","from","to","durationUntilNextConfirmationDays","btcPriceNonExecutable","phaseAtTransition")} for e in risk_trans[-12:]],
  "sourceMonths":{s:metas[s]["validMonths"] for s in ASSETS},
  "eligiblePhaseDays":len(daily),"firstEligiblePhaseDate":daily[0]["date"]}
 root=pref()+"combined/"
 reportsha=write(s,b,root+"phase_transitions.json",full)
 manifests=write(s,b,root+"manifest.json",{"version":"8.0","researchOnly":True,
  "status":"PHASE_TRANSITION_RESEARCH_PASS","reportSha256":reportsha,"prefix":root,
  "preregSha256":ps})
 brief.update(reportSha256=reportsha,manifestSha256=manifests,prefix=root)
 (folder/"summary.json").write_text(json.dumps(brief,ensure_ascii=False,indent=2))
 print("V80_RESULT "+json.dumps(brief,ensure_ascii=False),flush=True)
 if os.getenv("GITHUB_STEP_SUMMARY"):
  with open(os.environ["GITHUB_STEP_SUMMARY"],"a",encoding="utf-8") as f:
   f.write(f"# Исследование фаз v8.0 (только Research)\n\n"
    f"Дата: 2026-10-17 UTC\n\nФаза BTC: {latest_p}\n\n"
    f"Склонность к риску: {latest_r}\n\n"
    f"Переходов фаз: {len(main_trans)}, режимов риска: {len(risk_trans)}.\n\n"
    f"R2: {root}\n\nSHA-256: {reportsha}\n")
def main():
 a=argparse.ArgumentParser()
 a.add_argument("--asset",choices=ASSETS)
 a.add_argument("--combine",action="store_true")
 x=a.parse_args()
 if x.asset:eachasset(x.asset)
 elif x.combine:combine()
 else:raise SystemExit("V80_ARGS_INVALID")
if __name__=="__main__":main()
