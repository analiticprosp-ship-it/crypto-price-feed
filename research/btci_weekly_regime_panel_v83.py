#!/usr/bin/env python3
"""BTCI 8.3 weekly BTC + 6-alt breadth regime panel: retrospective research only.

Reuses unchanged frozen v8.2 weekly/relative-strength scoring. No account access,
no trading or live Detector modifications. All timestamps are UTC closed days.
"""
import datetime as dt,hashlib,json,os,statistics
from collections import Counter,defaultdict
from pathlib import Path

from btci_weekly_recovery_v82 import (
 weekly_at,breadth_at,classify,checked_get,checked_write,client,sha
)
ROOT=Path(__file__).resolve().parents[1]
PREREG="research/btci_v83_weekly_regime_panel_prereg_2026-10-18.json"
V80_KEY="research/detector/v8.0/runs/39124773092-1/combined/phase_transitions.json"
V80_SHA="b4fb7e7bb0640e052c9c95dc405da8f406d3b051b476f56226abb7a813e86f10"
V82_KEY="research/btci/v8.2/runs/39126594551-1/comparison.json"
V82_SHA="b6069ba19a026db16f7af8f79f20527e5a2d4c175ef1b464726ff2650be2e47c"
ASSETS=("BTC","ETH","SOL","BNB","LINK","XRP","ADA","DOGE")
CATS=("BTC_WEEKLY_CONFIRMED_PLUS_BROAD_PARTICIPATION",
"BTC_WEEKLY_CONFIRMED_NARROW","BTC_WEEKLY_NOT_CONFIRMED","INSUFFICIENT_DATA")
HORIZONS=(4,13,26,52)
BASE_DATE=dt.date(2020,1,1)
LAST_DATE=dt.date(2026,10,17)
SOURCE_ROOT="research/detector/v8.0/runs/39124773092-1/assets/"

def six(x):return round(float(x),6) if x is not None else None
def ensure_prereg():
 raw=(ROOT/PREREG).read_bytes();spec=json.loads(raw)
 if spec["version"]!="8.3" or spec["parent"]!={"v80":{"key":V80_KEY,"sha256":V80_SHA},
   "v82":{"key":V82_KEY,"sha256":V82_SHA}}:
  raise SystemExit("V83_PREREG_NOT_FROZEN")
 return sha(raw)
def future_on(btc,week,h):
 end=week+dt.timedelta(weeks=h)
 if end>LAST_DATE or end not in btc:return {"status":"RIGHT_CENSORED"}
 base=btc[week];window=[]
 for k in range(1,h*7+1):
  d=week+dt.timedelta(days=k)
  if d not in btc:raise SystemExit("V83_FUTURE_MISSING_BTC_DAILY")
  window.append(btc[d])
 return {"status":"OBSERVED",
  "closeReturnPct":six(100*(window[-1]/base-1)),
  "maxAdverseClosePct":six(100*(min(window)/base-1)),
  "maxFavorableClosePct":six(100*(max(window)/base-1))}
def describe(rows):
 out={"weeklyObservations":len(rows)}
 for h in HORIZONS:
  ar=[r["future"][str(h)] for r in rows]
  observed=[z for z in ar if z["status"]=="OBSERVED"]
  ret=[z["closeReturnPct"] for z in observed]
  adverse=[z["maxAdverseClosePct"] for z in observed]
  out[str(h)]={"n":len(ret),"rightCensored":len(ar)-len(ret),
    "medianReturnPct":six(statistics.median(ret)) if ret else None,
    "meanReturnPct":six(statistics.mean(ret)) if ret else None,
    "positiveCount":sum(x>0 for x in ret),
    "positiveSharePct":six(100*sum(x>0 for x in ret)/len(ret)) if ret else None,
    "medianWorstDrawdownPct":six(statistics.median(adverse)) if adverse else None,
    "interpretation":"LOW_SAMPLE" if len(ret)<20 else "OVERLAPPING_DESCRIPTIVE_ONLY"}
 return out
def main():
 preregsha=ensure_prereg();s=client();bucket=os.environ["R2_BUCKET"]
 v80=checked_get(s,bucket,V80_KEY,V80_SHA)
 v82=checked_get(s,bucket,V82_KEY,V82_SHA)
 if v80["version"]!="8.0" or v82["version"]!="8.2":
  raise SystemExit("V83_PARENT_VERSION_MISMATCH")
 if v82["current"]["checkpointUTC"]!="2026-10-17":
  raise SystemExit("V83_PARENT_CURRENT_MISMATCH")
 prices={};lineage={}
 for asset in ASSETS:
  expected=v80["sources"]["assets"][asset]["sourceDailySha256"]
  raw=checked_get(s,bucket,SOURCE_ROOT+asset+"/daily.json",expected)
  values={dt.date.fromisoformat(z["day"]):z["close"] for z in raw}
  if len(values)!=len(raw):raise SystemExit("V83_DUPLICATE_SOURCE_DAILY")
  prices[asset]=values
  lineage[asset]={"sha256":expected,"days":len(raw)}
 if prices["BTC"].get(LAST_DATE)!=v80["latest"]["indicators"]["closeFuturesNonExecutable"]:
  raise SystemExit("V83_LATEST_BTC_CHANGED")
 days=[BASE_DATE+dt.timedelta(days=i) for i in range((LAST_DATE-BASE_DATE).days+1)]
 if any(day not in prices["BTC"] for day in days):
  raise SystemExit("V83_NO_GAPLESS_BTC")
 lastSunday=LAST_DATE-dt.timedelta(days=(LAST_DATE.weekday()+1)%7)
 sundays=[d for d in days if d.weekday()==6 and d<=lastSunday]
 pastday={dt.date.fromisoformat(z["date"]):z for z in v80["pastOnlyDailyTimelines"]}
 panel=[]
 for sunday in sundays:
  weekly=weekly_at(prices["BTC"],sunday)
  if weekly["status"]!="AVAILABLE":continue
  breadth=breadth_at(prices,sunday)
  category=classify(weekly,breadth)
  source_past=pastday.get(sunday)
  panel.append({"sundayClosedUTC":sunday.isoformat(),
    "btcWeeklyClose":prices["BTC"][sunday],
    "weekly":weekly,"breadth":breadth,"category":category,
    "v80ConfirmedPhase":source_past["phaseConfirmed"] if source_past else None,
    "v80ConfirmedRisk":source_past["riskConfirmed"] if source_past else None,
    "future":{str(h):future_on(prices["BTC"],sunday,h) for h in HORIZONS}})
 if not panel or panel[-1]["sundayClosedUTC"]!="2026-10-11":
  raise SystemExit("V83_LAST_COMPLETE_SUNDAY_MISMATCH")
 anchor=[p for i,p in enumerate(panel) if i%13==0]
 if any(dt.date.fromisoformat(b["sundayClosedUTC"])-dt.date.fromisoformat(a["sundayClosedUTC"])!=dt.timedelta(weeks=13)
  for a,b in zip(anchor,anchor[1:])):
  raise SystemExit("V83_ANCHOR_NOT_13_WEEKS")
 def group(rows):
  result={"baseline":describe(rows),
   "byCategory":{cat:describe([r for r in rows if r["category"]==cat]) for cat in CATS},
   "byEra":{"2020-2023":{cat:describe([r for r in rows if r["category"]==cat and r["sundayClosedUTC"]<"2024-01-01"]) for cat in CATS},
            "2024-2026":{cat:describe([r for r in rows if r["category"]==cat and r["sundayClosedUTC"]>="2024-01-01"]) for cat in CATS}}}
  return result
 transitions=[]
 last=None
 for r in panel:
  cur=r["weekly"]["weeklyTrendConfirmed"]
  if last is not None and cur!=last:
   transitions.append({"date":r["sundayClosedUTC"],"wasConfirmed":last,
      "nowConfirmed":cur,"category":r["category"],"future13w":r["future"]["13"]})
  last=cur
 # Verification: last complete week 2026-10-11 is precisely the weekly input used in v8.2.
 reference=v82["current"]["weekly"]
 last_week=panel[-1]["weekly"]
 for key in ("weekEndingUTC","weekCloseFuturesNonExecutable","sma30Week",
  "sma30WeekSlope4WeekPct","weeklyTrendConfirmed"):
  if last_week[key]!=reference[key]:
   raise SystemExit("V83_REPLAY_V82_LAST_WEEK_MISMATCH:"+key)
 latest=v82["current"]
 report={"version":"8.3","status":"WEEKLY_ALL_HISTORY_PANEL_RESEARCH_ONLY",
  "researchOnly":True,"tradesEmitted":0,
  "asOfUTC":"2026-10-17","lastClosedWeeklySunday":"2026-10-11",
  "preregSha256":preregsha,
  "sources":{"v80":{"key":V80_KEY,"sha256":V80_SHA},
   "v82":{"key":V82_KEY,"sha256":V82_SHA},"assets":lineage},
  "population":{"firstEligibleSunday":panel[0]["sundayClosedUTC"],
   "lastEligibleSunday":panel[-1]["sundayClosedUTC"],
   "totalWeeklyRows":len(panel),"nonoverlap13wAnchorRows":len(anchor),
   "anchorRule":"every 13th eligible Sunday starting from first eligible Sunday, fixed before calculation"},
  "fullWeekly":group(panel),
  "nonoverlapAnchor13w":group(anchor),
  "trendTransitions":transitions,
  "recentTransitions":transitions[-12:],
  "latestFullyClosedWeek":panel[-1],
  "currentDay31Checkpoint":latest,
  "weeklyPanel":panel,
  "limitations":[
   "All 2020-26 historical analysis is retrospective; model thresholds not trained prospectively",
   "BTC market phase state and weekly trend are correlated price-derived indicators; not two independent pieces of causal evidence",
   "Alts are a fixed surviving basket and absent before historical listings",
   "All-week 4/13/26/52w forward returns overlap heavily and cannot be treated as independent observations",
   "13-week anchor also has serial correlations, selection depends on anchor date and later horizons overlap",
   "Weighted liquidity, ETF flows, Fed monetary policy and stock-market risk are NOT included in this panel",
   "Weekly high/low indicators use weekly CLOSE extremes, not full OHLC high and low",
   "No order execution, spread, funding, or validated P&L; this research does not authorize trades",
   "Historical performance of the label does not imply causal predictability or a probability of bull transition"]}
 folder=Path("btci_v83_reports");folder.mkdir(exist_ok=True)
 raw=json.dumps(report,ensure_ascii=False,indent=2).encode()
 (folder/"panel.json").write_bytes(raw)
 root=f"research/btci/v8.3/runs/{os.environ.get('GITHUB_RUN_ID','manual')}-{os.environ.get('GITHUB_RUN_ATTEMPT','1')}/"
 rsha=checked_write(s,bucket,root+"panel.json",raw)
 msha=checked_write(s,bucket,root+"manifest.json",{
   "version":"8.3","researchOnly":True,"status":"WEEKLY_REGIME_PANEL_PASS",
   "reportSha256":rsha,"preregSha256":preregsha,"prefix":root})
 brief={"status":"V83_WEEKLY_REGIME_PANEL_PASS_WRITEBACK_VERIFIED",
   "weeks":len(panel),"anchorWeeks":len(anchor),
   "first":panel[0]["sundayClosedUTC"],"last":panel[-1]["sundayClosedUTC"],
   "full":report["fullWeekly"],"anchors":report["nonoverlapAnchor13w"],
   "trendTransitionCount":len(transitions),"recentTransitions":transitions[-8:],
   "latestClosedWeek":panel[-1]["weekly"],"currentDay31":latest,
   "reportSha256":rsha,"manifestSha256":msha,"prefix":root}
 (folder/"summary.json").write_text(json.dumps(brief,ensure_ascii=False,indent=2))
 print("V83_RESULT "+json.dumps(brief,ensure_ascii=False),flush=True)
 if os.getenv("GITHUB_STEP_SUMMARY"):
  with open(os.environ["GITHUB_STEP_SUMMARY"],"a",encoding="utf-8") as f:
   f.write("# BTCI v8.3 — историческая недельная панель\n\n"
   "Только исследование, никаких торговых полномочий.\n\n"
   f"Недель: {len(panel)}; 13-недельных контрольных точек: {len(anchor)}\n\n"
   f"R2: {root}\n\nSHA-256: {rsha}\n")
if __name__=="__main__":main()
