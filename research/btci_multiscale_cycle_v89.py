#!/usr/bin/env python3
"""BTCI v8.9 52wk structural BTC price regime and weekly alt breadth:
past-only classification, 4-week delayed confirmation, episode diagnostics.
Research-only, never an executable price or validated macro/cycle model.
"""
import os,json,hashlib,statistics,datetime as dt
from collections import Counter,defaultdict
from pathlib import Path
import boto3
ROOT=Path(__file__).resolve().parents[1]
PREREG="research/btci_v89_multiscale_cycle_prereg_2026-10-18.json"
P86=("research/btci/v8.6/runs/39130315439-1/extended_history.json",
"9af82767fa8139685e784c131c075cec553298c4718ed4a40ac41412144248ca")
P87=("research/btci/v8.7/runs/39131902527-1/episodes.json",
"260d7991a6567aa370cbef92c8b7294b520c5a6a1b626872c4c55ae9e6a3d5b8")
P88=("research/btci/v8.8/runs/39137791544-1/comparison.json",
"4aa4cd2f53d670c440775022de23b50fde14a2b3b9c5fd20e624a265932a4d88")
EXP="STRUCTURAL_EXPANSION_PRICE_PROXY"
CON="STRUCTURAL_CONTRACTION_PRICE_PROXY"
MID="TRANSITION_OR_REBOUND_PRICE_PROXY"
def sha(x):return hashlib.sha256(x).hexdigest()
def f6(x):return round(float(x),6) if x is not None else None
def client():
 return boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
 aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
 aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
def read(s,b,key,expected):
 raw=s.get_object(Bucket=b,Key=key)["Body"].read()
 if sha(raw)!=expected:raise SystemExit("V89_PARENT_SHA_MISMATCH:"+key)
 return json.loads(raw)
def write(s,b,key,obj):
 raw=obj if isinstance(obj,bytes) else json.dumps(obj,ensure_ascii=False,indent=2).encode()
 expected=sha(raw)
 s.put_object(Bucket=b,Key=key,Body=raw,ContentType="application/json",
 Metadata={"sha256":expected,"research-only":"true"})
 if sha(s.get_object(Bucket=b,Key=key)["Body"].read())!=expected:
  raise SystemExit("V89_CLOUD_READBACK_MISMATCH")
 return expected
def prereg():
 raw=(ROOT/PREREG).read_bytes();p=json.loads(raw)
 expect={"v86":{"key":P86[0],"sha256":P86[1]},
         "v87":{"key":P87[0],"sha256":P87[1]},
         "v88":{"key":P88[0],"sha256":P88[1]}}
 if p.get("version")!="8.9" or p["parent"]!=expect:
  raise SystemExit("V89_FROZEN_SPEC_CHANGED")
 return sha(raw)
def describe_events(events,h):
 ready=[e["future"][str(h)] for e in events if e["future"][str(h)]["status"]=="OBSERVED"]
 returns=[z["returnPct"] for z in ready]
 bad=[z["worstDailyClosePct"] for z in ready]
 return {"n":len(events),"observed":len(returns),"rightCensored":len(events)-len(returns),
  "medianFutureReturnPct":f6(statistics.median(returns)) if returns else None,
  "positiveCount":sum(v>0 for v in returns),
  "medianWorstDailyClosePct":f6(statistics.median(bad)) if bad else None,
  "sampleGate":"LOW_SAMPLE" if len(returns)<20 else "RETROSPECTIVE_DESCRIPTIVE_ONLY"}
def main():
 psha=prereg()
 s=client();bucket=os.environ["R2_BUCKET"]
 old=read(s,bucket,*P86)
 entries=read(s,bucket,*P87)
 p88=read(s,bucket,*P88)
 weekly=old["weeklyRows"]
 if len(weekly)!=814 or entries["trendTransitions"]!=77 or len(entries["allEvents"])!=77 or p88["version"]!="8.8":
  raise SystemExit("V89_FROZEN_PARENT_STRUCTURE_MISMATCH")
 if weekly[0]["date"]!="2011-03-13" or weekly[-1]["date"]!="2026-10-11":
  raise SystemExit("V89_WEEKLY_CUTOFF_CHANGED")
 d=[dt.date.fromisoformat(x["date"]) for x in weekly]
 if any(b-a!=dt.timedelta(days=7) for a,b in zip(d,d[1:])):
  raise SystemExit("V89_DATE_GAPS")
 vals=[x["btcFixingPriceUSD"] for x in weekly]
 scored=[None]*len(weekly)
 for i in range(64,len(weekly)):
  ma52=sum(vals[i-51:i+1])/52
  previous=sum(vals[i-64:i-12])/52
  r26=100*(vals[i]/vals[i-26]-1)
  slope13=100*(ma52/previous-1)
  if vals[i]>ma52 and ma52>previous and r26>0:raw=EXP
  elif vals[i]<ma52 and ma52<previous and r26<0:raw=CON
  else:raw=MID
  scored[i]={"date":weekly[i]["date"],"i":i,"raw":raw,
      "ma52":f6(ma52),"slope52w13Pct":f6(slope13),
      "trailing26wReturnPct":f6(r26),"aboveSma52":vals[i]>ma52,
      "sma52SlopeUp":ma52>previous,
      "weeklyTrend":weekly[i]["weeklyTrendConfirmed"],
      "breadth":weekly[i]["altBreadth"],
      "futuresLinked":False}
 # Phase switches are confirmed only at the END of fourth consecutive RAW week.
 streak=0;prev=None;confirmed=None
 switches=[];valid=[]
 for i,row in enumerate(scored):
  if row is None:continue
  raw=row["raw"]
  if raw==prev:streak+=1
  else:prev=raw;streak=1
  row["rawConsecutiveWeeks"]=streak
  row["pendingTransition"]=raw!=confirmed
  if streak==4 and raw!=confirmed:
   switches.append({"idx":i,"date":row["date"],"from":confirmed,"to":raw,
      "confirmationDelayWeeks":3,"pastOnly":True})
   confirmed=raw
  row["confirmed"]=confirmed
  row["pendingTransition"]=raw!=confirmed
  valid.append(row)
 for j,e in enumerate(switches):
  e["durationUntilNextConfirmationWeeks"]=(
   switches[j+1]["idx"]-e["idx"] if j<len(switches)-1 else None)
  e["rightCensoredDuration"]=j==len(switches)-1
  start=weekly[e["idx"]]
  e["future"]={str(k):start["future"][str(k)] for k in (4,13,26,52)}
  e["breadthAtConfirmation"]=start["altBreadth"]
  e["weeklyTrendAtConfirmation"]=start["weeklyTrendConfirmed"]
 change_lookup={e["idx"]:e for e in switches}
 weekly_entries=[e for e in entries["allEvents"] if e["event"]=="TREND_ENTER"]
 joined=[]
 for e in weekly_entries:
  i=e["index"]
  row=scored[i]
  if row is None:
   state="UNAVAILABLE_WARMUP";raw=None;breadth="UNKNOWN"
  else:
   state=row["confirmed"] if row["confirmed"] else "UNCONFIRMED_INITIAL"
   raw=row["raw"]
   breadth=weekly[i]["altBreadth"]["status"]
  joined.append({"date":e["date"],"structuralStateAtEntry":state,
    "rawStructuralAtEntry":raw,"weeklyEntry":e["event"],
    "breadthCoverageAtEntry":breadth,
    "future":{str(k):e["future"][str(k)] for k in (13,26)},
    "trendSurvived13w":e["survivedWithoutOppositeByWeek"]["13"]})
 keyorder=(EXP,CON,MID,"UNAVAILABLE_WARMUP","UNCONFIRMED_INITIAL")
 grouped={key:{"n":sum(x["structuralStateAtEntry"]==key for x in joined),
   "next13w":describe_events([x for x in joined if x["structuralStateAtEntry"]==key],13),
   "next26w":describe_events([x for x in joined if x["structuralStateAtEntry"]==key],26),
   "entriesKeepingWeeklyTrend13w":sum(x["trendSurvived13w"] is True for x in joined if x["structuralStateAtEntry"]==key),
   "unknownBreadth":sum(x["breadthCoverageAtEntry"]!="AVAILABLE" for x in joined if x["structuralStateAtEntry"]==key)
  } for key in keyorder}
 swsummary={key:{"switches":sum(e["to"]==key for e in switches),
  "completedSpells":sum(e["to"]==key and e["durationUntilNextConfirmationWeeks"] is not None for e in switches),
  "medianCompletedDurationWeeks":f6(statistics.median(
    [e["durationUntilNextConfirmationWeeks"] for e in switches
     if e["to"]==key and e["durationUntilNextConfirmationWeeks"] is not None]
    )) if any(e["to"]==key and e["durationUntilNextConfirmationWeeks"] is not None for e in switches) else None,
  "next13w":describe_events([e for e in switches if e["to"]==key],13)
  } for key in (EXP,CON,MID)}
 # Summarize BTC fast-weekly trend churn within each confirmed structural regime.
 stateweeks={key:{"weeks":sum(x["confirmed"]==key for x in valid),
   "weeklyUp":sum(x["confirmed"]==key and x["weeklyTrend"] for x in valid),
   "weeklyDown":sum(x["confirmed"]==key and not x["weeklyTrend"] for x in valid),
   "breadthEligible":sum(x["confirmed"]==key and x["breadth"]["status"]=="AVAILABLE" for x in valid),
   "broadAltWeeks":sum(x["confirmed"]==key and x["breadth"]["status"]=="AVAILABLE" and x["breadth"].get("broadParticipation",False) for x in valid)}
   for key in (EXP,CON,MID)}
 def era_name(x):
  if x["date"]<"2017-01-01":return "2011-2016"
  if x["date"]<"2020-01-01":return "2017-2019"
  if x["date"]<"2024-01-01":return "2020-2023"
  return "2024-2026"
 byera={}
 for era in ("2011-2016","2017-2019","2020-2023","2024-2026"):
  subset=[x for x in valid if era_name(x)==era]
  entries_sub=[x for x in joined if (
   ("2011-2016" if x["date"]<"2017-01-01" else
    "2017-2019" if x["date"]<"2020-01-01" else
    "2020-2023" if x["date"]<"2024-01-01" else "2024-2026"))==era]
  byera[era]={"weeks":len(subset),
    "confirmedWeeks":dict(Counter(x["confirmed"] for x in subset)),
    "structuralTransitions":sum(era_name(e)==era for e in switches),
    "weeklyTrendEntries":len(entries_sub),
    "weeklyEntriesByStructural":dict(Counter(x["structuralStateAtEntry"] for x in entries_sub))}
 current=valid[-1]
 if current["date"]!="2026-10-11":raise SystemExit("V89_CURRENT_WEEK_CHANGED")
 report={"version":"8.9","status":"MULTISCALE_STRUCTURAL_PRICE_CONTEXT_RESEARCH_ONLY",
 "researchOnly":True,"tradePermissionsGranted":False,
 "cutoffUTC":"2026-10-11","input":{"v86":P86,"v87":P87,"v88":P88},
 "preregSha256":psha,
 "method":{"price":"Coin Metrics BTC PriceUSD historical reference fixing",
  "SMA52":"52 fully completed Sundays inclusive",
  "slope":"current SMA52 greater than value 13 Sundays previously",
  "trendReturn":"trailing 26 completed Sunday closes positive / negative",
  "confirmation":"4 consecutive same raw structural labels; confirm at week 4, never backdate",
  "expansion":EXP,"contraction":CON,"transition":MID,
  "notEconomicGroundTruth":True},
 "eligibleWeeks":len(valid),"firstEligibleWeek":valid[0]["date"],
 "lastEligibleWeek":current["date"],"switchCount":len(switches),
 "switchSummary":swsummary,"confirmedStateWeekCounts":stateweeks,
 "weeklyEntryLinks":grouped,"eraSummary":byera,
 "current":{"date":current["date"],"rawStructural":current["raw"],
    "confirmedStructural":current["confirmed"],"rawWeeks":current["rawConsecutiveWeeks"],
    "pending":current["pendingTransition"],
    "weeklyTrendUp":current["weeklyTrend"],
    "btcReferenceClose":weekly[-1]["btcFixingPriceUSD"],
    "sma52":current["ma52"],"sma52Slope13Pct":current["slope52w13Pct"],
    "btcTrailing26wReturnPct":current["trailing26wReturnPct"],
    "altBreadth":current["breadth"],"lastSwitch":switches[-1]},
 "switches":switches,"weeklyEntries":joined,"pastOnlyWeeklyContext":valid,
 "limits":["Heuristic structural PRICE phases are not verified bull/bear economic regimes",
 "SMA52 and short-term flag are correlated BTC price data, not independent confirmation",
 "Selected current surviving asset basket has survivorship bias and is incomplete early history",
 "Macro H4.1 and NFCI data not joined without point-in-time published vintage",
 "An unchanged structural state during short-term weekly flag loss does NOT prove future trend persistence",
 "All outputs observational on previously inspected history; not true holdout or calibrated predictive power",
 "No NAV, Spot, Futures, P&L, capital, reserve, trading limits, live Detector or MASTER writes"]}
 root=f"research/btci/v8.9/runs/{os.environ.get('GITHUB_RUN_ID','manual')}-{os.environ.get('GITHUB_RUN_ATTEMPT','1')}/"
 folder=Path("btci_v89_reports");folder.mkdir(exist_ok=True)
 raw=json.dumps(report,ensure_ascii=False,indent=2).encode()
 (folder/"multiscale.json").write_bytes(raw)
 digest=write(s,bucket,root+"multiscale.json",raw)
 msha=write(s,bucket,root+"manifest.json",{
  "version":"8.9","status":"MULTISCALE_RESEARCH_PASS","researchOnly":True,
  "reportSha256":digest,"prefix":root,"preregSha256":psha})
 brief={"status":"V89_MULTISCALE_RESEARCH_PASS_WRITEBACK_VERIFIED",
  "sha":digest,"manifestSha":msha,"prefix":root,
  "weeks":len(valid),"switches":len(switches),
  "byPhase":swsummary,"weeklyEntryGroups":grouped,"confirmedWeeks":stateweeks,
  "era":byera,"current":report["current"],
  "last10":switches[-10:]}
 (folder/"summary.json").write_text(json.dumps(brief,ensure_ascii=False,indent=2))
 print("V89_RESULT "+json.dumps(brief,ensure_ascii=False),flush=True)
 if os.getenv("GITHUB_STEP_SUMMARY"):
  with open(os.environ["GITHUB_STEP_SUMMARY"],"a",encoding="utf-8") as f:
   f.write("# BTCI 8.9 — 52-недельный ценовой контекст / фаза цикла\n\n"
    f"Research only. Eligible weeks: {len(valid)}; confirmed changes: {len(switches)}\n\n"
    f"Current: {current['confirmed']}; raw: {current['raw']}\n\nR2: {root}\n\nSHA: {digest}\n")
if __name__=="__main__":main()
