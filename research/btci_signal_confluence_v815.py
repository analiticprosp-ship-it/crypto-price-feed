#!/usr/bin/env python3
"""BTCI v8.15: preregistered simultaneous and lagged confluence of price,
Fed H.4.1 and as-of-vintage NFCI/ANFCI. Research only, no trading authority.
"""
import datetime as dt,hashlib,json,os,statistics
from collections import Counter
from pathlib import Path
import boto3
ROOT=Path(__file__).resolve().parents[1]
P="research/btci_v815_signal_confluence_prereg_2026-10-18.json"
P813=("research/btci/v8.13/runs/39150999581-1/nfci_anfci_historical.json",
      "94c5f520e5cf449a5b739c5639d4349c44c7d60819f67c56e43ce4427c218d57")
P814=("research/btci/v8.14/runs/39169052651-1/episode_replay.json",
      "6a6a0e62f4502e05d561ccd7da32ef0e433ae128b88b5969b4447fc159209269")
MS=("K2_RAW","K3_RAW","K4_RAW","FAMILY2_STRICT","FAMILY2_LOOSE",
    "MACRO2_STRICT","MACRO2_LOOSE","BTC_AND_FINANCE","BTC_AND_FED",
    "ANY_TWO_MACRO_RAW","EARLY_MACRO_NO_BTC",
    "MACRO_FIRST_TWO_FAMILIES_LAST4W")
BASE=("A","F","N","J")

def sha(x):return hashlib.sha256(x).hexdigest()
def r6(v):return round(float(v),6) if v is not None else None
def date(z):return dt.date.fromisoformat(z)
def r2():
 return boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
   aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
   aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
def read(s,b,key,digest):
 raw=s.get_object(Bucket=b,Key=key)["Body"].read()
 if sha(raw)!=digest:raise SystemExit("V815_PARENT_SHA_MISMATCH:"+key)
 return json.loads(raw)
def write(s,b,key,payload):
 raw=payload if isinstance(payload,bytes) else json.dumps(payload,ensure_ascii=False,indent=2).encode()
 dg=sha(raw)
 s.put_object(Bucket=b,Key=key,Body=raw,ContentType="application/json",
    Metadata={"sha256":dg,"research-only":"true"})
 if sha(s.get_object(Bucket=b,Key=key)["Body"].read())!=dg:raise SystemExit("V815_R2_READBACK_MISMATCH")
 return dg
def median(x):return r6(statistics.median(x)) if x else None
def groups(rows):
 bs=[];now=[];prev=None
 for r in rows:
  d=date(r["date"])
  if prev is not None and (d-prev).days!=7:
   if now:bs.append(now)
   now=[]
  now.append(r);prev=d
 if now:bs.append(now)
 return bs
def condition(row):
 old=row["newModels"]
 if row["NFCI"]["status"]!="PIT_ASOF_DATE_VERIFIED" or row["ANFCI"]["status"]!="PIT_ASOF_DATE_VERIFIED":
  raise SystemExit("V815_INVALID_VINTAGE")
 a=bool(old["A"]);f=bool(old["C"])
 n=bool(old["NFCI_IMPROVE4"]);j=bool(old["ANFCI_IMPROVE4"])
 if n!=(row["NFCI"]["deltaFourWeeks"]<0) or j!=(row["ANFCI"]["deltaFourWeeks"]<0):
  raise SystemExit("V815_ALFRED_VINTAGE_SIGN_MISMATCH")
 if f!=(row["FedDelta4"]>0):
  raise SystemExit("V815_FED_SIGN_MISMATCH")
 q=n and j
 cnt=int(a)+int(f)+int(n)+int(j)
 fam=int(a)+int(f)+int(q)
 famloose=int(a)+int(f)+int(n or j)
 return {"A":a,"F":f,"N":n,"J":j,"Q":q,
  "K2_RAW":cnt>=2,"K3_RAW":cnt>=3,"K4_RAW":cnt==4,
  "FAMILY2_STRICT":fam>=2,"FAMILY2_LOOSE":famloose>=2,
  "MACRO2_STRICT":f and q,"MACRO2_LOOSE":f and (n or j),
  "BTC_AND_FINANCE":a and q,"BTC_AND_FED":a and f,
  "ANY_TWO_MACRO_RAW":int(f)+int(n)+int(j)>=2,
  "EARLY_MACRO_NO_BTC":f and q and not a,
  "MACRO_FIRST_TWO_FAMILIES_LAST4W":False}
def compute(rows):
 # Each rolling past4 interval ends at t, cannot bridge missing eligible dates.
 for k,row in enumerate(rows):
  row["signals"]=condition(row)
  last=[row];idx=k
  while len(last)<4 and idx>0:
   if (date(rows[idx]["date"])-date(rows[idx-1]["date"])).days!=7:break
   idx-=1
   last.append(rows[idx])
  both_f=any(x["signals"]["F"] for x in last)
  both_q=any(x["signals"]["Q"] for x in last)
  row["signals"]["MACRO_FIRST_TWO_FAMILIES_LAST4W"]=(
   both_f and both_q and (row["signals"]["F"] or row["signals"]["Q"]))
  row["confluenceCountRaw"]=sum(row["signals"][k] for k in BASE)
  row["independentFamilyCountStrict"]=(
   int(row["signals"]["A"])+int(row["signals"]["F"])+int(row["signals"]["Q"]))
 return rows
def metric(rows,m):
 tp=sum(r["signals"][m] and r["newExpansionBy13w"] for r in rows)
 fp=sum(r["signals"][m] and not r["newExpansionBy13w"] for r in rows)
 fn=sum(not r["signals"][m] and r["newExpansionBy13w"] for r in rows)
 tn=sum(not r["signals"][m] and not r["newExpansionBy13w"] for r in rows)
 hits=[r for r in rows if r["signals"][m]]
 rvals=[r["btcReturn13wPct"] for r in hits]
 positive=sum(r["btcReturnPositive13w"] for r in hits)
 adverse=sum(r["btcAdverse20Next13w"] for r in hits)
 def div(n,d):return r6(n/d) if d else None
 return {"n":len(rows),"selected":len(hits),"TP":tp,"FP":fp,"FN":fn,"TN":tn,
  "precision":div(tp,tp+fp),"recall":div(tp,tp+fn),
  "specificity":div(tn,tn+fp),"positive13wSelected":positive,
  "adverse20Selected":adverse,"adverse20FractionSelected":div(adverse,len(hits)),
  "median13wReturnPct":median(rvals)}
def summarize(rows):
 return {"n":len(rows),
  "baseExpansionWeeks":sum(r["newExpansionBy13w"] for r in rows),
  "btcPositiveWeeks":sum(r["btcReturnPositive13w"] for r in rows),
  "results":{m:metric(rows,m) for m in (*BASE,*MS)}}
def slim(r):
 return {"date":r["date"],"era":r["era"],
 "btc13wPct":r["btcReturn13wPct"],
 "structuralExpansion13w":r["newExpansionBy13w"],
 "adverse20":r["btcAdverse20Next13w"],
 "signals":{m:r["signals"][m] for m in (*BASE,*MS)}}
def lock(rows,m,weeks):
 o=[];last=None
 for x in rows:
  if not x["signals"][m]:continue
  d=date(x["date"])
  if last is None or (d-last).days>=7*(weeks+1):
   o.append(x);last=d
 return o

def main():
 pre=(ROOT/P).read_bytes();pr=json.loads(pre)
 expect={"v813":{"key":P813[0],"sha256":P813[1]},
         "v814":{"key":P814[0],"sha256":P814[1]}}
 if pr["version"]!="8.15" or pr["parents"]!=expect:
  raise SystemExit("V815_FROZEN_PREREG_CHANGED")
 s=r2();b=os.environ["R2_BUCKET"]
 base=read(s,b,*P813);old=read(s,b,*P814)
 if base["version"]!="8.13" or old["version"]!="8.14" or len(base["weeklyPanel"])!=137 or old["eligibilityBlockN"]!=9:
  raise SystemExit("V815_PARENT_STRUCTURE_CHANGED")
 orig=base["weeklyPanel"]
 if orig[0]["date"]!="2020-05-10" or orig[-1]["date"]!="2026-07-12":raise SystemExit("V815_DATES_CHANGED")
 rows=compute([{**r} for r in orig])
 blocks=groups(rows)
 if len(blocks)!=9 or [len(x) for x in blocks]!=[x["eligibleSundays"] for x in old["completeBlockData"]]:
  raise SystemExit("V815_BLOCK_BOUNDARIES_CHANGED")
 if [x[0]["date"] for x in blocks]!=[x["first"] for x in old["completeBlockData"]]:
  raise SystemExit("V815_BLOCK_DATES_CHANGED")
 first=[b[0] for b in blocks]
 first4={}
 for m in (*BASE,*MS):
  accepted=[];missed=[];delay=[]
  for i,block in enumerate(blocks):
   idx=next((k for k,x in enumerate(block[:4]) if x["signals"][m]),None)
   if idx is None:missed.append(block[0]["date"])
   else:accepted.append(block[idx]);delay.append(idx)
  first4[m]={"blockWarnings":len(accepted),"missedBlocks":missed,
   "delays":delay,"metricsOnActualFirstWarningDate":metric(accepted,m),
   "dates":[slim(z) for z in accepted]}
 lock={}
 for n in (13,26):
  lock[str(n)]={m:{"n":len(pick:=lock_rows),"metrics":metric(pick,m),
       "dates":[slim(z) for z in pick]}
       for m in (*BASE,*MS) for lock_rows in [globals()["lock"](rows,m,n)]}
 events=[]
 for e in old["confirmedStructuralExpansionEvents"]:
  date_target=e["confirmedStructuralExpansionDate"]
  start=date(date_target)-dt.timedelta(weeks=13)
  look=[z for z in rows if start<=date(z["date"])<date(date_target)]
  if len(look)!=e["priorEligibleWeeks"]:
   raise SystemExit("V815_UNCHANGED_EVENT_WINDOW_CHANGED:"+date_target)
  found={}
  for m in (*BASE,*MS):
   firsthit=next((z for z in look if z["signals"][m]),None)
   found[m]={"firstWarning":firsthit["date"] if firsthit else None,
      "leadWeeks":(date(date_target)-date(firsthit["date"])).days//7 if firsthit else None}
  events.append({"confirmedExpansion":date_target,"priorEligibleWeeks":len(look),
     "signals":found})
 summaryevent={m:{"found":sum(x["signals"][m]["firstWarning"] is not None for x in events),
   "total":len(events),
   "medianLeadWeeks":median([z["signals"][m]["leadWeeks"] for z in events
      if z["signals"][m]["leadWeeks"] is not None])} for m in (*BASE,*MS)}
 era={"2020-2023":[x for x in rows if x["date"]<"2024-01-01"],
      "2024-2026":[x for x in rows if x["date"]>="2024-01-01"]}
 chart=[{"numberOfRawWarnings":k,"weeks":sum(x["confluenceCountRaw"]==k for x in rows),
         "expansionNext13w":sum(x["newExpansionBy13w"] for x in rows if x["confluenceCountRaw"]==k),
         "btcPositive13w":sum(x["btcReturnPositive13w"] for x in rows if x["confluenceCountRaw"]==k)}
        for k in range(5)]
 chart_family=[{"familyCount":k,"weeks":sum(x["independentFamilyCountStrict"]==k for x in rows),
          "expansionNext13w":sum(x["newExpansionBy13w"] for x in rows if x["independentFamilyCountStrict"]==k)}
       for k in range(4)]
 report={"version":"8.15","status":"CONFLUENCE_SAME_COHORT_EPISODE_RESEARCH_ONLY",
  "researchOnly":True,"tradeApproval":False,"asOfDate":"2026-07-12",
  "parents":{"v813":{"key":P813[0],"sha256":P813[1]},
             "v814":{"key":P814[0],"sha256":P814[1]}},
  "preregistration":{"path":P,"sha256":sha(pre)},
  "definitions":pr["combinations"],"dependencyPolicy":pr["dependencyPolicy"],
  "population":{"weeks":len(rows),"contiguousBlocks":len(blocks),"expansionEvents":len(events)},
  "weekly":summarize(rows),"byEra":{k:summarize(v) for k,v in era.items()},
  "rawFourIndicatorCountDistribution":chart,
  "independentFamilyCountStrictDistribution":chart_family,
  "firstBlockSunday":summarize(first),
  "withinFirstFourBlockWeeks":first4,
  "nonoverlapLockouts":lock,
  "sixExpansionEvents":events,"sixEventCoverage":summaryevent,
  "blockBoundaries":[{"from":x[0]["date"],"to":x[-1]["date"],"n":len(x)} for x in blocks],
  "rowLevelFlags":[slim(x) for x in rows],
  "findingsAreNotPredictions":True,
  "limitations":["NFCI and ANFCI are correlated; naive raw 2/4 counts overstate independently confirming sources.",
   "Same 137 previously inspected Sundays; not untouched test data; thresholds fixed at v8.15 only.",
   "Target future BTC structural expansion is price-defined, not independent economic bull/market stage.",
   "First-block and 14-week lockout reduce but do not eliminate macrocycle dependence, and small n restricts inference.",
   "First-four-week window may delay warning and must not backdate outcome or sign.",
   "As-of Sunday FRED vintage data verified but precise original intra-day release time not independently proven.",
   "No market-executable price, no trading P&L, no transaction costs. No live signaling authority."],
  "unchanged":{"MASTER":True,"Spot":True,"Futures":True,"NAV":True,"capital":True,
  "PnL":True,"reserve":True,"tradeLimits":True,"Detector":True}}
 prefix=f"research/btci/v8.15/runs/{os.environ['GITHUB_RUN_ID']}-{os.environ.get('GITHUB_RUN_ATTEMPT','1')}/"
 folder=Path("btci_v815_reports");folder.mkdir(exist_ok=True)
 raw=json.dumps(report,ensure_ascii=False,indent=2).encode()
 (folder/"confluence.json").write_bytes(raw)
 digest=write(s,b,prefix+"confluence.json",raw)
 manifest=write(s,b,prefix+"manifest.json",{"version":"8.15","researchOnly":True,
  "status":"CONFLUENCE_RESEARCH_PASS","sourceSha256":{"v813":P813[1],"v814":P814[1]},
  "reportSha256":digest,"preregSha256":sha(pre)})
 brief={"status":"V815_CONFLUENCE_PASS_R2_READBACK_VERIFIED","prefix":prefix,
  "reportSha256":digest,"manifestSha256":manifest,
  "weekly":report["weekly"],"eras":report["byEra"],
  "rawCount":chart,"familyCount":chart_family,
  "firstBlock":report["firstBlockSunday"],
  "first4":{m:{k:v for k,v in out.items() if k!="dates"} for m,out in first4.items()},
  "lock13":{m:{"n":z["n"],"metrics":z["metrics"]} for m,z in lock["13"].items()},
  "lock26":{m:{"n":z["n"],"metrics":z["metrics"]} for m,z in lock["26"].items()},
  "eventSummary":summaryevent,"events":events}
 (folder/"summary.json").write_text(json.dumps(brief,ensure_ascii=False,indent=2))
 print("V815_RESULT "+json.dumps(brief,ensure_ascii=False),flush=True)
if __name__=="__main__":main()
