#!/usr/bin/env python3
"""BTCI v8.12: controlled SAME-COHORT early warning comparison, 2020-2026.
No calibrated probabilities / no point-in-time economic vintage certification.
"""
import datetime as dt,hashlib,json,os,statistics
from collections import Counter
from pathlib import Path
import boto3
ROOT=Path(__file__).resolve().parents[1]
SPEC="research/btci_v812_early_warning_prereg_2026-10-18.json"
PARENT=("research/btci/v8.11/runs/39147565584-1/four_lens.json",
"742d693504f44fbf21165cd6773c0a5450ea424821befb7622c7af034d7ae44b")
KEYS=("A","B","C","D","E","F")
def sha(b):return hashlib.sha256(b).hexdigest()
def round6(a):return round(float(a),6) if a is not None else None
def r2():
 return boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
 aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
 aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
def read(s,b,key,expected):
 body=s.get_object(Bucket=b,Key=key)["Body"].read()
 if sha(body)!=expected:raise SystemExit("V812_FROZEN_PARENT_SHA_MISMATCH")
 return json.loads(body)
def write(s,b,key,data):
 raw=data if isinstance(data,bytes) else json.dumps(data,ensure_ascii=False,indent=2).encode()
 dig=sha(raw)
 s.put_object(Bucket=b,Key=key,Body=raw,ContentType="application/json",
 Metadata={"sha256":dig,"research-only":"true"})
 if sha(s.get_object(Bucket=b,Key=key)["Body"].read())!=dig:
  raise SystemExit("V812_R2_VERIFIED_READBACK_FAILED")
 return dig
def confusion(rows,which,target):
 tp=sum(z["warnings"][which] and z[target] for z in rows)
 fp=sum(z["warnings"][which] and not z[target] for z in rows)
 fn=sum(not z["warnings"][which] and z[target] for z in rows)
 tn=sum(not z["warnings"][which] and not z[target] for z in rows)
 precision=tp/(tp+fp) if tp+fp else None
 sensitivity=tp/(tp+fn) if tp+fn else None
 specificity=tn/(tn+fp) if tn+fp else None
 ba=(sensitivity+specificity)/2 if sensitivity is not None and specificity is not None else None
 return {"TP":tp,"FP":fp,"FN":fn,"TN":tn,"alarms":tp+fp,
  "precision":round6(precision),"recall":round6(sensitivity),
  "specificity":round6(specificity),"balancedAccuracy":round6(ba)}
def aggregate(rows):
 data={"n":len(rows),"expansionWithin13w":sum(x["newExpansionBy13w"] for x in rows),
   "positiveBTC13w":sum(x["btcReturnPositive13w"] for x in rows),
   "adverse20BTC13w":sum(x["btcAdverse20Next13w"] for x in rows),
   "overallMedianBTC13wPct":round6(statistics.median(
      [x["btcReturn13wPct"] for x in rows])) if rows else None}
 for k in KEYS+("INVERT_B","INVERT_C"):
  chosen=[x for x in rows if x["warnings"][k]]
  returns=[x["btcReturn13wPct"] for x in chosen]
  data[k]={"expansion":confusion(rows,k,"newExpansionBy13w"),
   "btcPositive":confusion(rows,k,"btcReturnPositive13w"),
   "selectedWithAdverse20":sum(x["btcAdverse20Next13w"] for x in chosen),
   "selectedAdverse20Rate":round6(sum(x["btcAdverse20Next13w"] for x in chosen)/len(chosen)) if chosen else None,
   "medianSelectedBTC13wPct":round6(statistics.median(returns)) if returns else None}
 return data
def episodes(rows):
 output={}
 for k in KEYS:
  entries=[];prev=False;last_date=None
  for x in rows:
   today=dt.date.fromisoformat(x["date"])
   has=x["warnings"][k]
   spaced=last_date is None or (today-last_date).days!=7
   if has and (not prev or spaced):entries.append(x)
   prev=has;last_date=today
  output[k]={"entries":len(entries),"expansion13w":sum(x["newExpansionBy13w"] for x in entries),
   "positive13w":sum(x["btcReturnPositive13w"] for x in entries),
   "medianReturn13wPct":round6(statistics.median([x["btcReturn13wPct"] for x in entries])) if entries else None,
   "firstEightDates":[x["date"] for x in entries[:8]],
   "episodeDefinition":"first eligible week of a run of consecutive eligible Sundays with the warning"}
 return output
def main():
 raw_spec=(ROOT/SPEC).read_bytes();spec=json.loads(raw_spec)
 if spec["version"]!="8.12" or spec["parent"]!={"key":PARENT[0],"sha256":PARENT[1]}:
  raise SystemExit("V812_PREREG_FROZEN_MISMATCH")
 s=r2();bucket=os.environ["R2_BUCKET"]
 original=read(s,bucket,*PARENT)
 if original["version"]!="8.11" or original["dataset"]["commonEligibleWeeks"]!=138:
  raise SystemExit("V812_UNEXPECTED_POPULATION")
 base=original["completeCasePanel"]
 if len(base)!=138 or base[0]["date"]!="2020-05-10" or base[-1]["date"]!="2026-07-12":
  raise SystemExit("V812_INPUT_DATE_MISMATCH")
 rows=[]
 for x in base:
  a=bool(x["weeklyTrend"])
  b=x["breadth"]["ethVsBtcPct"]>0 and x["breadth"]["outperformingAlts"]>=4
  c=x["financial"]["deltaFourReleaseMillionUSD"]>0
  if b!=x["breadth"]["broadParticipation"]:
   raise SystemExit("V812_INVALID_BREADTH")
  if x["models"]!={"A":a,"B":a and b,"C":a and c,"D":a and b and c}:
   raise SystemExit("V812_PARENT_OLD_MODELS_INCONSISTENT")
  if x["financial"]["vintageStatus"]!="PIT_REVISION_UNVERIFIED":
   raise SystemExit("V812_MACRO_VINTAGE_UNEXPECTED")
  warn={"A":a,"B":b,"C":c,"D":b and c,"E":b or c,"F":a or (b and c),
        "INVERT_B":not b,"INVERT_C":not c}
  rows.append({"date":x["date"],"era":"2020-2023" if x["date"]<"2024-01-01" else "2024-2026",
   "initialStructural":x["startingStructural"],
   "warnings":warn,
   "breadth":x["breadth"],"financial":x["financial"],
   "newExpansionBy13w":x["newExpansionBy13w"],
   "btcReturnPositive13w":x["btcReturnPositive13w"],
   "btcAdverse20Next13w":x["btcAdverse20Next13w"],
   "btcReturn13wPct":x["btcReturn13wPct"]})
 era={"2020-2023":[z for z in rows if z["era"]=="2020-2023"],
      "2024-2026":[z for z in rows if z["era"]=="2024-2026"]}
 anchor=[z for i,z in enumerate(rows) if i%13==0]
 events=[]
 for prev in original["confirmedStructuralExpansionEvents2020On"]:
  d=dt.date.fromisoformat(prev["expansionConfirmation"])
  past=[x for x in rows if d-dt.timedelta(weeks=13)<=dt.date.fromisoformat(x["date"])<d]
  trig={}
  for k in KEYS:
   dates=[q["date"] for q in past if q["warnings"][k]]
   trig[k]={"observed":bool(dates),
     "earliest":dates[0] if dates else None,
     "leadWeeks":(d-dt.date.fromisoformat(dates[0])).days//7 if dates else None}
  events.append({"expansionDate":prev["expansionConfirmation"],"eligiblePriorWeeks":len(past),"triggers":trig})
 report={"version":"8.12","status":"EARLY_WARNING_GATE_ABLATION_RESEARCH_ONLY",
  "researchOnly":True,"noTradingAuthority":True,
  "input":{"key":PARENT[0],"sha256":PARENT[1]},
  "preregistration":{"path":SPEC,"sha256":sha(raw_spec)},
  "commonCohort":{"n":len(rows),"first":rows[0]["date"],"last":rows[-1]["date"],
   "last13wOutcomesFullyObserved":True},
  "models":spec["definitions"],
  "allWeeks":aggregate(rows),"eras":{k:aggregate(v) for k,v in era.items()},
  "fixed13thEligibleWeekAnchor":aggregate(anchor),
  "warningEpisodeStarts":episodes(rows),
  "prior13wByStructuralExpansionEvent":events,
  "rows":rows,
  "NFCIVintageStatus":"NOT_JOINED_AWAIT_AUTHENTIC_ALFRED_POINT_IN_TIME_DATA",
  "interpretation":[
   "A warning is not a trading signal; a negative control using inverse breadth/macro UP is not a learned indicator.",
   "Macro Fed pages now archived by date may have changed since historic publication.",
   "Target structural expansion is defined by BTC price, not an exogenous market regime.",
   "Overlapping 13w outcomes are dependent, even same-cohort confusion metrics are biased as prospective estimates.",
   "Alts 8 fixed surviving assets, not market-wide breadth.",
   "Earlier warning via fewer conditions may have higher false alarm rate; no fitted optimum from study.",
   "No true 2024+ holdout because data already studied by v8.11.",
   "Independent historical NFCI/ANFCI release-vintage API requires separate data acquisition and exact as-of validation."],
  "operations":{"tradesEmitted":0,"modifiedMaster":False,"modifiedSpot":False,
   "modifiedFutures":False,"modifiedNAV":False,"changedLimits":False}}
 folder=Path("btci_v812_reports");folder.mkdir(exist_ok=True)
 body=json.dumps(report,ensure_ascii=False,indent=2).encode()
 (folder/"early_warning.json").write_bytes(body)
 path=f"research/btci/v8.12/runs/{os.environ.get('GITHUB_RUN_ID','manual')}-{os.environ.get('GITHUB_RUN_ATTEMPT','1')}/"
 h=write(s,bucket,path+"early_warning.json",body)
 m=write(s,bucket,path+"manifest.json",{
  "version":"8.12","researchOnly":True,"status":"EARLY_WARNING_ABLATION_RESEARCH_PASS",
  "input":PARENT[0],"inputSha256":PARENT[1],
  "reportSha256":h,"preregSha256":sha(raw_spec)})
 brief={"status":"V812_EARLY_WARNING_PASS_R2_VERIFIED","prefix":path,
  "reportSha256":h,"manifestSha256":m,
  "overall":report["allWeeks"],"eras":report["eras"],
  "anchor":report["fixed13thEligibleWeekAnchor"],
  "episodes":report["warningEpisodeStarts"],"events":events}
 (folder/"summary.json").write_text(json.dumps(brief,ensure_ascii=False,indent=2))
 print("V812_RESULT "+json.dumps(brief,ensure_ascii=False),flush=True)
if __name__=="__main__":main()
