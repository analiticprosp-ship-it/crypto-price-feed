#!/usr/bin/env python3
"""BTCI v8.4 | Frozen weekly BTC-first / alt-breadth lead-lag analysis.
Historical descriptive ONLY. No NAV, Futures, trading or operational state.
"""
from __future__ import annotations
import datetime as dt
import hashlib,json,os,statistics
from collections import Counter
from pathlib import Path
import boto3

ROOT=Path(__file__).resolve().parents[1]
PREREG="research/btci_v84_leadlag_prereg_2026-10-18.json"
SOURCE="research/btci/v8.3/runs/39126819412-1/panel.json"
SOURCE_SHA="9f90e6974e43f74a3af0bdf562d5e865b56c01565cb83d9b177aae2f81cc5479"
CATS={
"N":"BTC_WEEKLY_CONFIRMED_NARROW",
"B":"BTC_WEEKLY_CONFIRMED_PLUS_BROAD_PARTICIPATION",
"F":"BTC_WEEKLY_NOT_CONFIRMED",
"U":"INSUFFICIENT_DATA"}
WINDOWS=(4,13,26)

def sha(b):return hashlib.sha256(b).hexdigest()
def f6(x):return round(float(x),6) if x is not None else None
def client():
 return boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
  aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
  aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
def get(s,b,key,h):
 blob=s.get_object(Bucket=b,Key=key)["Body"].read()
 if sha(blob)!=h:raise SystemExit("V84_FROZEN_PARENT_SHA_MISMATCH")
 return json.loads(blob)
def write(s,b,key,obj):
 raw=obj if isinstance(obj,bytes) else json.dumps(obj,ensure_ascii=False,indent=2).encode()
 digest=sha(raw)
 s.put_object(Bucket=b,Key=key,Body=raw,ContentType="application/json",
  Metadata={"sha256":digest,"research-only":"true"})
 if sha(s.get_object(Bucket=b,Key=key)["Body"].read())!=digest:
  raise SystemExit("V84_R2_READBACK_FAILED")
 return digest

def summarise_outcomes(events):
 result={"totalEpisodes":len(events)}
 for h in (4,13,26):
  scores=[e["outcomes"][str(h)]["closeReturnPct"] for e in events
          if e["outcomes"][str(h)]["status"]=="OBSERVED"]
  dd=[e["outcomes"][str(h)]["maxAdverseClosePct"] for e in events
          if e["outcomes"][str(h)]["status"]=="OBSERVED"]
  result[str(h)]={"n":len(scores),"rightCensored":len(events)-len(scores),
    "positiveCount":sum(x>0 for x in scores),
    "medianPct":f6(statistics.median(scores)) if scores else None,
    "meanPct":f6(statistics.mean(scores)) if scores else None,
    "medianMaxAdversePct":f6(statistics.median(dd)) if dd else None,
    "evidence":"LOW_SAMPLE" if len(scores)<20 else "DESCRIPTIVE_ONLY"}
 return result

def outcome_to(events, horizon, target):
 states=[]
 for e in events:
  z=e["targets"][str(horizon)][target]
  states.append(z["status"])
 return dict(Counter(states))

def main():
 raw=(ROOT/PREREG).read_bytes()
 p=json.loads(raw)
 if p.get("version")!="8.4" or p.get("immutableV83")!={"key":SOURCE,"sha256":SOURCE_SHA}:
  raise SystemExit("V84_PREREG_CHANGE")
 s=client();b=os.environ["R2_BUCKET"]
 source=get(s,b,SOURCE,SOURCE_SHA)
 rows=source["weeklyPanel"]
 if source["version"]!="8.3" or len(rows)!=321 or rows[-1]["sundayClosedUTC"]!="2026-10-11":
  raise SystemExit("V84_SOURCE_CHANGED")
 ds=[dt.date.fromisoformat(z["sundayClosedUTC"]) for z in rows]
 if len(set(ds))!=len(ds) or any(y-x!=dt.timedelta(days=7) for x,y in zip(ds,ds[1:])):
  raise SystemExit("V84_WEEKLY_GAP")
 byname={name:key for key,name in CATS.items()}
 if any(z["category"] not in byname for z in rows):
  raise SystemExit("V84_WRONG_WEEK_CATEGORY")
 entries=[]
 for i in range(1,len(rows)):
  cur=rows[i]["category"];previous=rows[i-1]["category"]
  if cur==previous:continue
  next_i=next((j for j in range(i+1,len(rows)) if rows[j]["category"]!=cur),None)
  end_index=next_i if next_i is not None else len(rows)
  duration_weeks=end_index-i
  e={"entryWeekUTC":rows[i]["sundayClosedUTC"],
     "from":byname[previous],"to":byname[cur],
     "index":i,
     "durationWeeks":duration_weeks,
     "episodeRightCensored":next_i is None,
     "firstExitCategory":byname[rows[next_i]["category"]] if next_i is not None else None,
     "firstExitWeekUTC":rows[next_i]["sundayClosedUTC"] if next_i is not None else None,
     "pastOnlyPhaseAtEntry":rows[i]["v80ConfirmedPhase"],
     "pastOnlyRiskAtEntry":rows[i]["v80ConfirmedRisk"],
     "outcomes":{str(h):rows[i]["future"][str(h)] for h in WINDOWS},
     "targets":{}}
  for h in WINDOWS:
   if i+h>=len(rows):
    e["targets"][str(h)]={"B":{"status":"RIGHT_CENSORED"},"F":{"status":"RIGHT_CENSORED"}}
    continue
   window=rows[i+1:i+h+1]
   assert len(window)==h
   notknown=any(q["category"]==CATS["U"] for q in window)
   z={}
   for key in ("B","F"):
    indices=[j for j,q in enumerate(window,1) if q["category"]==CATS[key]]
    if indices:
     z[key]={"status":"EVENT_OBSERVED","weeksFromEntry":indices[0],
             "firstDate":window[indices[0]-1]["sundayClosedUTC"]}
    elif key=="B" and notknown:
     z[key]={"status":"DATA_CENSORED_BREADTH"}
    else:
     z[key]={"status":"NOT_OBSERVED"}
   e["targets"][str(h)]=z
  entries.append(e)
 for e in entries:
  for h in WINDOWS:
   t=e["targets"][str(h)]
   if t["B"]["status"]=="EVENT_OBSERVED" and t["F"]["status"]=="EVENT_OBSERVED":
    if t["B"]["weeksFromEntry"]<t["F"]["weeksFromEntry"]:
     t["firstEventAmongBroadAndFailure"]="BROAD"
    elif t["F"]["weeksFromEntry"]<t["B"]["weeksFromEntry"]:
     t["firstEventAmongBroadAndFailure"]="NOT_CONFIRMED"
    else:raise SystemExit("V84_MUTUALLY_EXCLUSIVE_SAME_WEEK")
   elif t["B"]["status"]=="EVENT_OBSERVED":t["firstEventAmongBroadAndFailure"]="BROAD"
   elif t["F"]["status"]=="EVENT_OBSERVED":t["firstEventAmongBroadAndFailure"]="NOT_CONFIRMED"
   elif t["B"]["status"]=="RIGHT_CENSORED":t["firstEventAmongBroadAndFailure"]="RIGHT_CENSORED"
   elif t["B"]["status"]=="DATA_CENSORED_BREADTH":t["firstEventAmongBroadAndFailure"]="DATA_CENSORED_BREADTH"
   else:t["firstEventAmongBroadAndFailure"]="NEITHER"
 narrow=[e for e in entries if e["to"]=="N"]
 broad=[e for e in entries if e["to"]=="B"]
 no=[e for e in entries if e["to"]=="F"]
 def episode_stats(items):
  episodes=[x["durationWeeks"] for x in items if not x["episodeRightCensored"]]
  return {"episodes":len(items),"closedEpisodes":len(episodes),
     "rightCensoredEpisodes":len(items)-len(episodes),
     "medianDurationWeeks":f6(statistics.median(episodes)) if episodes else None,
     "countWithDurationAtLeast4w":sum(x>=4 for x in episodes),
     "outcomes":summarise_outcomes(items)}
 def narrow_stats(items):
  return {"episodes":len(items),"episodesAfter2024":sum(e["entryWeekUTC"]>="2024-01-01" for e in items),
    "duration":episode_stats(items),
    "byHorizon":{str(h):{
       "broader":outcome_to(items,h,"B"),"lostWeeklyTrend":outcome_to(items,h,"F"),
       "firstChange":dict(Counter(e["targets"][str(h)]["firstEventAmongBroadAndFailure"] for e in items))}
      for h in WINDOWS}}
 anchor=[];lastidx=-9999
 for e in narrow:
  if e["index"]-lastidx>=13:
   anchor.append(e);lastidx=e["index"]
 groups={"2020-2023":[e for e in narrow if e["entryWeekUTC"]<"2024-01-01"],
         "2024-2026":[e for e in narrow if e["entryWeekUTC"]>="2024-01-01"]}
 byera={key:narrow_stats(es) for key,es in groups.items()}
 recent=[{k:v for k,v in e.items() if k in ("entryWeekUTC","from","to","durationWeeks","firstExitCategory","episodeRightCensored",
      "firstExitWeekUTC","pastOnlyRiskAtEntry")} for e in entries[-18:]]
 p83=source["latestFullyClosedWeek"]
 current={
 "lastFullWeek":"2026-10-11","latestCategory":byname[p83["category"]],
 "lastKnownDailyCheckpoint":source["currentDay31Checkpoint"]["checkpointUTC"],
 "weeklyConfirmed":p83["weekly"]["weeklyTrendConfirmed"],
 "breadthNumber":p83["breadth"].get("altsOutperformBTC30d"),
 "lastNarrowEntry":next((e["entryWeekUTC"] for e in reversed(narrow)),None),
 "lastBroadEntry":next((e["entryWeekUTC"] for e in reversed(broad)),None),
 "lastWeeklyTrendChange":next((e["entryWeekUTC"] for e in reversed(entries) if e["to"]=="F" or e["from"]=="F"),None)}
 report={"version":"8.4","status":"BTC_LEAD_ALT_BREADTH_EPISODES_RESEARCH_ONLY",
  "researchOnly":True,"tradesEmitted":0,"cutoff":"2026-10-11",
  "preregistration":{"path":PREREG,"sha256":sha(raw)},
  "source":{"key":SOURCE,"sha256":SOURCE_SHA},
  "totalWeeks":len(rows),"transitionCount":len(entries),
  "categoryTransitionCounts":dict(Counter(e["to"] for e in entries)),
  "episodes":{"narrow":episode_stats(narrow),"broad":episode_stats(broad),
              "notConfirmed":episode_stats(no)},
  "narrowLeadLag":narrow_stats(narrow),
  "narrow13WeekSpaced":narrow_stats(anchor),
  "narrowByEra":byera,
  "narrowEpisodes":narrow,
  "allEntries":entries,
  "latest":current,"recentEntries":recent,
  "externalPIT":{"FarsideETF":"PIT_UNVERIFIED_NOT_BACKTESTED","FedH41":"RELEASE_CALENDAR_ONLY_NOT_BACKTESTED",
    "ETFHistoryStart":"2024-01","noHistoricalETForMacroJoined":True},
  "inference":{"validatedPredictiveEdge":False,"status":"EXPLORATORY_HISTORICAL_ONLY",
    "note":"Episodes can be interdependent and overlap. A later broad category is a different contemporaneous classification, not automatically profitable altcoin entry. Both signal family and BTC performance are driven by prices.",
    "sampleSizeGate":"Fewer than 20 independent episodes per relevant era means no probability claim."},
  "limitations":["Not a blinded prospective test and weekly breadth uses only selected surviving assets",
    "Broad participation can be a lagging marker of late-cycle strength, not a universal tops predictor",
    "No real-time ETF PIT vintage, macro point-in-time model, costs or cross-venue confirmation",
    "A break in weekly narrow category does not necessarily break BTC's weekly trend",
    "Weeks since latest full Sunday and phase since latest confirmed day have different cutoffs",
    "No operational trading/portfolio authority; no NAV/Spot/Futures/MASTER/limit change"]}
 folder=Path("btci_v84_reports");folder.mkdir(exist_ok=True)
 blob=json.dumps(report,ensure_ascii=False,indent=2).encode()
 (folder/"leadlag.json").write_bytes(blob)
 root=f"research/btci/v8.4/runs/{os.environ.get('GITHUB_RUN_ID','manual')}-{os.environ.get('GITHUB_RUN_ATTEMPT','1')}/"
 dig=write(s,b,root+"leadlag.json",blob)
 man=write(s,b,root+"manifest.json",{"version":"8.4","researchOnly":True,
    "status":"BTC_LEADLAG_RESEARCH_PASS","reportSha256":dig,"prefix":root})
 brief={"status":"V84_BTC_LEADLAG_PASS_WRITEBACK_VERIFIED","reportSha256":dig,"manifestSha256":man,
  "prefix":root,"weeks":len(rows),"transitions":len(entries),"byCategory":report["categoryTransitionCounts"],
  "episodes":report["episodes"],"narrow":report["narrowLeadLag"],
  "narrowSpacing":report["narrow13WeekSpaced"],"eras":byera,"recent":recent,"current":current}
 (folder/"summary.json").write_text(json.dumps(brief,ensure_ascii=False,indent=2))
 print("V84_RESULT "+json.dumps(brief,ensure_ascii=False),flush=True)
 if os.getenv("GITHUB_STEP_SUMMARY"):
  with open(os.environ["GITHUB_STEP_SUMMARY"],"a",encoding="utf-8") as f:
   f.write(f"# BTCI v8.4 — недельное лидерство BTC / расширение альтов\n\n"
    f"RESEARCH_ONLY. Narrow episodes: {len(narrow)}, broad episodes: {len(broad)}\n\n"
    f"R2: {root}\n\nSHA-256: {dig}\n")
if __name__=="__main__":main()
