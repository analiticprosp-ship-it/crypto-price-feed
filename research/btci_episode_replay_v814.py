#!/usr/bin/env python3
"""BTCI v8.14: measure ANFCI independent-opportunity effect, not pseudo-N
from overlapping 13-week weekly targets. Retrospective research only.
"""
import datetime as dt,hashlib,json,os,statistics
from collections import Counter
from pathlib import Path
import boto3

ROOT=Path(__file__).resolve().parents[1]
PRE="research/btci_v814_episode_replay_prereg_2026-10-18.json"
PARENT=("research/btci/v8.13/runs/39150999581-1/nfci_anfci_historical.json",
"94c5f520e5cf449a5b739c5639d4349c44c7d60819f67c56e43ce4427c218d57")
MODELS=("A","C","NFCI_IMPROVE4","ANFCI_IMPROVE4","ANFCI_AND_FED","ANFCI_WORSEN4","ANFCI_ANY_CHANGE")
EVENT_MODELS=("A","C","NFCI_IMPROVE4","ANFCI_IMPROVE4","ANFCI_AND_FED")

def sha(b):return hashlib.sha256(b).hexdigest()
def day(z):return dt.date.fromisoformat(z)
def round6(x):return round(float(x),6) if x is not None else None
def median(arr):return round6(statistics.median(arr)) if arr else None
def r2():
 return boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
 aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
 aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
def get(s,b,k,dg):
 raw=s.get_object(Bucket=b,Key=k)["Body"].read()
 if sha(raw)!=dg:raise SystemExit("V814_PARENT_SOURCE_HASH_CHANGED")
 return json.loads(raw)
def save(s,b,k,payload):
 raw=payload if isinstance(payload,bytes) else json.dumps(payload,ensure_ascii=False,indent=2).encode()
 dg=sha(raw)
 s.put_object(Bucket=b,Key=k,Body=raw,ContentType="application/json",
  Metadata={"research-only":"true","sha256":dg})
 if sha(s.get_object(Bucket=b,Key=k)["Body"].read())!=dg:
  raise SystemExit("V814_CLOUD_REREAD_SHA_MISMATCH")
 return dg

def score(rows):
 n=len(rows);r=[x["btcReturn13wPct"] for x in rows]
 up=sum(x["newExpansionBy13w"] for x in rows)
 pos=sum(x["btcReturnPositive13w"] for x in rows)
 bad=sum(x["btcAdverse20Next13w"] for x in rows)
 return {"n":n,"followedByStructuralExpansion13w":up,
   "btcReturnPositive13w":pos,"btcAdverseDailyClose20Within13w":bad,
   "fractionExpansion":round6(up/n) if n else None,
   "fractionBTCPositive":round6(pos/n) if n else None,
   "fractionAdverse20":round6(bad/n) if n else None,
   "medianReturn13wPct":median(r),
   "note":"NOT_INDEPENDENT_CYCLE_PVALUES; descriptive; n<20" if n<20 else "DEPENDENT_ECONOMIC_EPISODES"}
def simple(r):
 return {"date":r["date"],"era":r["era"],
  "structuralExpansion13w":r["newExpansionBy13w"],
  "btcReturnPositive13w":r["btcReturnPositive13w"],
  "btcAdverse20Within13w":r["btcAdverse20Next13w"],
  "btcReturn13wPct":r["btcReturn13wPct"]}
def flagged(r,m):
 if m=="ANFCI_WORSEN4":return r["ANFCI"]["deltaFourWeeks"]>0
 if m=="ANFCI_ANY_CHANGE":return r["ANFCI"]["deltaFourWeeks"]!=0
 return bool(r["newModels"][m])
def groupblocks(rows):
 blocks=[];current=[];prev=None
 for r in rows:
  now=day(r["date"])
  if prev is not None and (now-prev).days!=7:
   if current:blocks.append(current)
   current=[]
  current.append(r);prev=now
 if current:blocks.append(current)
 return blocks
def firstfour(block,m):
 allowed=block[:4]
 assert all((day(y["date"])-day(x["date"])).days==7 for x,y in zip(allowed,allowed[1:]))
 for idx,r in enumerate(allowed):
  if flagged(r,m):return idx,r
 return None,None

def nonoverlap(rows,m,lockWeeks):
 selected=[];last=None
 for r in rows:
  now=day(r["date"])
  if not flagged(r,m):continue
  if last is not None and (now-last).days<7*(lockWeeks+1):continue
  selected.append(r);last=now
 assert all((day(y["date"])-day(x["date"])).days>=7*(lockWeeks+1) for x,y in zip(selected,selected[1:]))
 return selected

def count_eras(rows):
 result={}
 for era in ("2020-2023","2024-2026"):
  subset=[x for x in rows if x["era"]==era]
  result[era]=score(subset)
 return result

def main():
 rawpre=(ROOT/PRE).read_bytes();p=json.loads(rawpre)
 if p["version"]!="8.14" or p["parent"]!={"key":PARENT[0],"sha256":PARENT[1]}:
  raise SystemExit("V814_FROZEN_SPEC_MISMATCH")
 s=r2();bucket=os.environ["R2_BUCKET"];old=get(s,bucket,*PARENT)
 if old["version"]!="8.13" or old["commonPopulation"]["fullyValidatedN"]!=137:
  raise SystemExit("V814_PARENT_UNEXPECTED")
 rows=old["weeklyPanel"]
 if len(rows)!=137 or rows[0]["date"]!="2020-05-10" or rows[-1]["date"]!="2026-07-12":
  raise SystemExit("V814_PANEL_BOUNDARY_UNEXPECTED")
 if len(old["phaseEventPrior13Weeks"])!=6:
  raise SystemExit("V814_STRUCTURAL_EVENTS_CHANGED")
 if any("ANFCI_IMPROVE4" not in r["newModels"] or
   r["ANFCI"]["status"]!="PIT_ASOF_DATE_VERIFIED" or
   r["NFCI"]["status"]!="PIT_ASOF_DATE_VERIFIED" for r in rows):
  raise SystemExit("V814_UNVERIFIED_VINTAGE")
 blocks=groupblocks(rows)
 if len(blocks)!=9:raise SystemExit("V814_ELIGIBILITY_BLOCK_COUNT_CHANGED")
 if sum(map(len,blocks))!=137:raise SystemExit("V814_BLOCK_COVERAGE_MISMATCH")
 blockdesc=[]
 for i,b in enumerate(blocks):
  anchors={m:bool(flagged(b[0],m)) for m in MODELS}
  blockdesc.append({"block":i+1,"first":b[0]["date"],"last":b[-1]["date"],
   "eligibleSundays":len(b),"startWarnings":anchors,
   "startFuture":simple(b[0]),"firstFourWarning":{
    m:({"date":r["date"],"delayWeeks":ix,
       "future":simple(r)} if r else None) for m in MODELS
     for ix,r in [firstfour(b,m)]}})
 starts=[b[0] for b in blocks]
 primary={"blocksN":len(blocks),"firstSundaySample":score(starts),
  "firstSundayByEra":count_eras(starts),
  "byModel":{}}
 fourweek={"blocksN":len(blocks),"byModel":{}}
 for m in MODELS:
  r=[b[0] for b in blocks if flagged(b[0],m)]
  primary["byModel"][m]={"outcomes":score(r),"byEra":count_eras(r),
    "dates":[simple(x) for x in r]}
  hits=[firstfour(b,m) for b in blocks]
  alert=[x for _,x in hits if x is not None]
  weeks=[idx for idx,x in hits if x is not None]
  fourweek["byModel"][m]={"withinFirstFourWeeks":len(alert),"missedBlocks":len(blocks)-len(alert),
    "alertDelayWeeks":weeks,"outcomesFromActualWarningDate":score(alert),
    "byEra":count_eras(alert),"alerts":[simple(r) for r in alert]}
 locked={}
 for lock in (13,26):
  locksummary={"lockWeeks":lock,"byModel":{}}
  for m in MODELS:
   selected=nonoverlap(rows,m,lock)
   locksummary["byModel"][m]={"outcomes":score(selected),
     "byEra":count_eras(selected),
     "alerts":[simple(z) for z in selected],
     "notes":"Model-specific lockout, selected event dates differ between models. These are not matched forecasts."}
  locked[str(lock)]=locksummary

 events=[]
 for e in old["phaseEventPrior13Weeks"]:
  date=e["expansionDate"]
  dates={}
  for m in EVENT_MODELS:
   obs=e["earliestWarning"].get(m)
   dates[m]={"observed":obs is not None,
    "date":obs,"leadWeeks":e["leadWeeks"].get(m)}
  if "ANFCI_WORSEN4" not in dates:
   ref=day(date);prior=[x for x in rows
    if ref-dt.timedelta(weeks=13)<=day(x["date"])<ref]
   bad=next((x for x in prior if flagged(x,"ANFCI_WORSEN4")),None)
   dates["ANFCI_WORSEN4"]={"observed":bad is not None,
     "date":bad["date"] if bad else None,
     "leadWeeks":(ref-day(bad["date"])).days//7 if bad else None}
  events.append({"confirmedStructuralExpansionDate":date,
    "priorEligibleWeeks":e["eligiblePriorWeeks"],"signals":dates})
 eventstats={}
 for m in (*EVENT_MODELS,"ANFCI_WORSEN4"):
  d=[x["signals"][m] for x in events]
  lead=[q["leadWeeks"] for q in d if q["leadWeeks"] is not None]
  eventstats[m]={"eventsWithWarning":sum(z["observed"] for z in d),
   "numberOfConfirmedExpansionEvents":len(events),
   "medianLeadWeeksAmongObserved":median(lead),
   "leadWeeks":lead,
   "warningMisses":len(events)-len(lead)}

 report={"version":"8.14","status":"MARKET_EPISODE_AND_LOCKOUT_RESEARCH_ONLY",
  "researchOnly":True,"noTradingAuthorization":True,
  "sourceParent":{"key":PARENT[0],"sha256":PARENT[1]},
  "preregistration":{"path":PRE,"sha256":sha(rawpre)},
  "asOfLastSundayWith13wFuture":"2026-07-12",
  "observedWeeklyN":len(rows),"eligibilityBlockN":len(blocks),
  "blockDefinition":"maximal contiguous 7-calendar-day eligible Sunday runs, not independent macro bull/bear cycles",
  "models":list(MODELS),
  "firstBlockSunday":primary,"withinFirst4WeeksOfBlock":fourweek,
  "modelSpecific14WeekAnd27WeekLockout":locked,
  "confirmedStructuralExpansionEvents":events,
  "confirmedExpansionEventCoverage":eventstats,
  "completeBlockData":blockdesc,
  "publicationCaveat":"FRED historical as-of Sunday vintages; intraday original release clocks not separately validated.",
  "limitations":[
   "This study was designed after 2011–2026 market history had been repeatedly inspected; not OOS or prospective forecast.",
   "Nine eligibility runs and six structural-expansion events are exceptionally few for generalizable predictive probabilities.",
   "Grouping is based on being in non-expansion BTC structural state, which is price-derived and cannot serve as independent ground truth.",
   "Four-week scanning delays the date a warning becomes available; future outcome starts from actual alert, not block start.",
   "Lockouts reduce overlap but not common-market regime dependence, and warning-selected dates vary by model.",
   "A model with no warnings cannot have numeric precision=100%; no p-values/accuracy promotions.",
   "2024–26 is NOT a held-out period because prior versions already reviewed it.",
   "Index observation release intraday timing unverified; as-of Sunday and lag>=6d are conservative.",
   "No trade simulation, fees, market liquidity, positions, NAV or execution outcomes."],
  "operationalWriteback":{"Spot":False,"Futures":False,"NAV":False,"capital":False,
     "PnL":False,"reserve":False,"MASTER":False,"tradeLimits":False,"liveDetector":False}}
 prefix=f"research/btci/v8.14/runs/{os.environ.get('GITHUB_RUN_ID','manual')}-{os.environ.get('GITHUB_RUN_ATTEMPT','1')}/"
 out=Path("btci_v814_reports");out.mkdir(exist_ok=True)
 raw=json.dumps(report,ensure_ascii=False,indent=2).encode()
 (out/"episode_replay.json").write_bytes(raw)
 dg=save(s,bucket,prefix+"episode_replay.json",raw)
 manifest={"version":"8.14","status":"EPISODE_REPLAY_PASS_SOURCE_R2_READBACK",
    "researchOnly":True,"reportSha256":dg,
    "parentSha256":PARENT[1],"preregistrationSha256":sha(rawpre)}
 mh=save(s,bucket,prefix+"manifest.json",manifest)
 brief={"status":"V814_EPISODE_REPLAY_PASS_CLOUD_WRITEBACK_VERIFIED",
    "r2Prefix":prefix,"reportSha256":dg,"manifestSha256":mh,
    "blocks":len(blocks),"blockDates":[{"first":b[0]["date"],"last":b[-1]["date"],"n":len(b)} for b in blocks],
    "first":primary,"fourWeek":fourweek,
    "lock13":locked["13"],"lock26":locked["26"],
    "eventCoverage":eventstats}
 (out/"summary.json").write_text(json.dumps(brief,ensure_ascii=False,indent=2))
 print("V814_RESULT "+json.dumps(brief,ensure_ascii=False),flush=True)
 if os.environ.get("GITHUB_STEP_SUMMARY"):
  with open(os.environ["GITHUB_STEP_SUMMARY"],"a",encoding="utf-8") as f:
   f.write(f"# BTCI v8.14 — episode-level research, not real OOS\n\n"
      f"Eligible Sundays {len(rows)}, contiguous blocks {len(blocks)}, expansion events {len(events)}.\n\n"
      f"R2 {prefix}\n\nSHA256 {dg}\n")
if __name__=="__main__":main()
