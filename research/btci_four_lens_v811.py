#!/usr/bin/env python3
"""BTCI 8.11: fixed, same-cohort exploratory ablation of BTC price trend,
historical alt breadth and release-lagged Fed H.4.1 monetary proxy.
NO trained models, no historical PIT vintage verification, no live trading.
"""
import bisect,collections,datetime as dt,hashlib,json,os,statistics
from pathlib import Path
import boto3

ROOT=Path(__file__).resolve().parents[1]
PREREG="research/btci_v811_four_lens_comparison_prereg_2026-10-18.json"
P86=("research/btci/v8.6/runs/39130315439-1/extended_history.json",
     "9af82767fa8139685e784c131c075cec553298c4718ed4a40ac41412144248ca")
P89=("research/btci/v8.9/runs/39138844921-1/multiscale.json",
     "4b8822e929aff5569fa9cd105404c02b110927a970aed33db68910925c111b73")
PM=("research/btci/v8.10.1/runs/39141047403-1/macro_study.json",
    "230f5c2eebdba583dbadf4a44d50123fb85f93c39b318f5d4fcbb7cb7480fb81")
EXP="STRUCTURAL_EXPANSION_PRICE_PROXY"
CATS=("A","B","C","D")
def hash(raw):return hashlib.sha256(raw).hexdigest()
def round6(n):return round(float(n),6) if n is not None else None
def parse(d):return dt.date.fromisoformat(d)
def r2():
 return boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
 aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
def checked(s,b,key,sha):
 raw=s.get_object(Bucket=b,Key=key)["Body"].read()
 if hash(raw)!=sha:raise SystemExit("V811_FROZEN_SOURCE_DIGEST_CHANGED:"+key)
 return json.loads(raw)
def write(s,b,key,obj):
 raw=obj if isinstance(obj,bytes) else json.dumps(obj,ensure_ascii=False,indent=2).encode()
 dg=hash(raw)
 s.put_object(Bucket=b,Key=key,Body=raw,ContentType="application/json",
  Metadata={"sha256":dg,"research-only":"true"})
 if hash(s.get_object(Bucket=b,Key=key)["Body"].read())!=dg:
  raise SystemExit("V811_R2_READBACK_MISMATCH:"+key)
 return dg
def truth_metrics(rows, model, target):
 t=sum(r[target] and r["models"][model] for r in rows)
 fp=sum(not r[target] and r["models"][model] for r in rows)
 fn=sum(r[target] and not r["models"][model] for r in rows)
 tn=sum(not r[target] and not r["models"][model] for r in rows)
 precision=t/(t+fp) if t+fp else None
 recall=t/(t+fn) if t+fn else None
 specificity=tn/(tn+fp) if tn+fp else None
 balanced=(recall+specificity)/2 if recall is not None and specificity is not None else None
 return {"TP":t,"FP":fp,"FN":fn,"TN":tn,"selected":t+fp,"total":len(rows),
  "precision":round6(precision),"recall":round6(recall),
  "specificity":round6(specificity),"balancedAccuracy":round6(balanced)}
def describe(rows):
 out={"n":len(rows),"futureStructuralExpansionWithin13w":sum(x["newExpansionBy13w"] for x in rows),
  "btcPositiveNext13w":sum(x["btcReturnPositive13w"] for x in rows),
  "btcAdverse20Next13w":sum(x["btcAdverse20Next13w"] for x in rows)}
 for m in CATS:
  selected=[x for x in rows if x["models"][m]]
  r=[x["btcReturn13wPct"] for x in selected]
  no=[x["btcReturn13wPct"] for x in rows if not x["models"][m]]
  out[m]={"newExpansionWithin13w":truth_metrics(rows,m,"newExpansionBy13w"),
   "btcPositive13w":truth_metrics(rows,m,"btcReturnPositive13w"),
   "amongSelectedPositive13w":sum(v>0 for v in r),
   "amongSelectedAdverse20":sum(x["btcAdverse20Next13w"] for x in selected),
   "medianSelectedReturn13wPct":round6(statistics.median(r)) if r else None,
   "medianNotSelectedReturn13wPct":round6(statistics.median(no)) if no else None}
 return out
def main():
 specraw=(ROOT/PREREG).read_bytes()
 spec=json.loads(specraw)
 exp={"btcWeekly":{"key":P86[0],"sha256":P86[1]},
      "btcStructure":{"key":P89[0],"sha256":P89[1]},
      "macroFed":{"key":PM[0],"sha256":PM[1]}}
 if spec["version"]!="8.11" or spec["parents"]!=exp:
  raise SystemExit("V811_PREREGISTRATION_MISMATCH")
 s=r2();bucket=os.environ["R2_BUCKET"]
 p86=checked(s,bucket,*P86);p89=checked(s,bucket,*P89);macro=checked(s,bucket,*PM)
 if (len(p86["weeklyRows"]),len(p89["pastOnlyWeeklyContext"]),len(macro["asofWeeklyRows"]))!=(814,750,750):
  raise SystemExit("V811_FROZEN_PANEL_LENGTH_CHANGED")
 if (p86["version"],p89["version"],macro["version"])!=("8.6","8.9","8.10.1"):
  raise SystemExit("V811_PARENT_VERSION_CHANGED")
 btc={x["date"]:x for x in p86["weeklyRows"]}
 contexts=p89["pastOnlyWeeklyContext"]
 mrows={x["date"]:x for x in macro["asofWeeklyRows"]}
 if len(set(x["date"] for x in contexts))!=750 or set(mrows)!=set(x["date"] for x in contexts):
  raise SystemExit("V811_WEEKLY_SOURCE_DATE_ALIGNMENT_CHANGED")
 mm=sorted(macro["allHistoricalReleaseObservations"],key=lambda z:z["releaseDate"])
 if len(mm)!=821:raise SystemExit("V811_MACRO_RELEASE_COUNT_CHANGED")
 dates=[parse(z["releaseDate"]) for z in mm]
 if len(dates)!=len(set(dates)):raise SystemExit("V811_MACRO_RELEASE_DUPLICATE")
 missing=sorted(parse(z["date"]) for z in macro["remainingProblems"])
 panel=[];exclusions=collections.Counter()
 for i,row in enumerate(contexts):
  day=parse(row["date"])
  if day.year<2020:
   exclusions["BEFORE_2020"]+=1;continue
  if row["confirmed"]==EXP:
   exclusions["ALREADY_EXPANSION"]+=1;continue
  bread=row["breadth"]
  if bread["status"]!="AVAILABLE":
   exclusions["ALT_BREADTH_UNAVAILABLE"]+=1;continue
  fed=mrows[row["date"]]["macro"]
  if fed["status"]!="AVAILABLE":
   exclusions["FED_FEATURE_UNAVAILABLE"]+=1;continue
  target=btc.get(row["date"])
  if target is None or target["future"]["13"]["status"]!="OBSERVED":
   exclusions["FORWARD_13_WEEK_RIGHT_CENSORED"]+=1;continue
  if i+13>=len(contexts):
   exclusions["STRUCTURAL_13_WEEK_RIGHT_CENSORED"]+=1;continue
  if contexts[i+13]["date"]!=(
   day+dt.timedelta(weeks=13)).isoformat():
   raise SystemExit("V811_NONCONSECUTIVE_WEEKS")
  # Any publication that fails archive completeness in the exact five-report
  # period makes the financial feature unknown, NOT a silently skipped week.
  cutoff=day-dt.timedelta(days=3)
  k=bisect.bisect_right(dates,cutoff)
  if k<5:exclusions["MACRO_LESS_THAN_5_REPORTS"]+=1;continue
  lastfive=mm[k-5:k]
  fed_dates=[parse(z["releaseDate"]) for z in lastfive]
  if any((b-a).days>10 for a,b in zip(fed_dates,fed_dates[1:])):
   exclusions["GAPPED_5_FED_RELEASE_WINDOW"]+=1;continue
  if any(fed_dates[0]<=m<=fed_dates[-1] for m in missing):
   exclusions["KNOWN_MISSING_RELEASE_IN_FIVE"]+=1;continue
  delta=lastfive[-1]["simplifiedFedMinusTGAMinusRRP_MillionUSD"]-lastfive[0]["simplifiedFedMinusTGAMinusRRP_MillionUSD"]
  if delta!=fed["deltaFourReleasesMillionUSD"] or fed_dates[-1].isoformat()!=fed["lastReleaseDate"]:
   raise SystemExit("V811_MACRO_FROZEN_DELTA_REPLAY_MISMATCH:"+row["date"])
  broad=(bread["ethVsBtcPct"]>0 and bread["outperformingAlts"]>=4)
  if broad!=bread["broadParticipation"]:raise SystemExit("V811_FROZEN_BREADTH_INVALID")
  alpha=row["weeklyTrend"]
  macro_up=delta>0
  models={"A":bool(alpha),"B":bool(alpha and broad),
   "C":bool(alpha and macro_up),"D":bool(alpha and broad and macro_up)}
  future_rows=contexts[i+1:i+14]
  becomesexp=any(z["confirmed"]==EXP for z in future_rows)
  f13=target["future"]["13"]
  panel.append({"date":row["date"],"ageInWeeks":len(contexts)-i-1,
    "startingStructural":row["confirmed"],"weeklyTrend":bool(alpha),
    "breadth":{"ethVsBtcPct":bread["ethVsBtcPct"],
      "outperformingAlts":bread["outperformingAlts"],"broadParticipation":broad},
    "financial":{"lastFedRelease":fed["lastReleaseDate"],
      "deltaFourReleaseMillionUSD":delta,"direction":fed["macroDirection"],
      "sourceDateGapMaxDays":max((b-a).days for a,b in zip(fed_dates,fed_dates[1:])),
      "vintageStatus":"PIT_REVISION_UNVERIFIED"},
    "models":models,
    "newExpansionBy13w":bool(becomesexp),
    "btcReturn13wPct":f13["returnPct"],
    "btcReturnPositive13w":f13["returnPct"]>0,
    "btcAdverse20Next13w":f13["worstDailyClosePct"]<=-20,
    "btcWorstDailyClose13wPct":f13["worstDailyClosePct"]})
 if not panel:raise SystemExit("V811_NO_FULL_COMMON_PANEL")
 eras={"2020-2023":[x for x in panel if x["date"]<"2024-01-01"],
       "2024-2026":[x for x in panel if x["date"]>="2024-01-01"]}
 anchor=[row for i,row in enumerate(panel) if i%13==0]
 raw_exps=[e for e in p89["switches"] if e["to"]==EXP and e["date"]>="2020-01-01"]
 event_recall=[]
 for ex in raw_exps:
  d=parse(ex["date"])
  lookback=[x for x in panel if d-dt.timedelta(weeks=13)<=parse(x["date"])<d]
  candidates={m:[x["date"] for x in lookback if x["models"][m]] for m in CATS}
  event_recall.append({"expansionConfirmation":ex["date"],
   "retrospectivePrior13wEligible":len(lookback),
   "hasModelInPrior13w":{m:bool(candidates[m]) for m in CATS},
   "earliestModelTriggerDate":{m:(candidates[m][0] if candidates[m] else None) for m in CATS},
   "notAConfirmedTrueMacroBull":True})
 report={"version":"8.11","status":"FOUR_LENS_COMPARISON_EXPLORATORY_NO_OOS",
  "researchOnly":True,"tradePermissionsGranted":False,
  "sources":{"v86":{"key":P86[0],"sha256":P86[1]},
    "v89":{"key":P89[0],"sha256":P89[1]},
    "macro":{"key":PM[0],"sha256":PM[1]}},
  "preregistration":{"path":PREREG,"sha256":hash(specraw)},
  "lastClosedSunday":"2026-10-11",
  "dataset":{"commonEligibleWeeks":len(panel),"firstSunday":panel[0]["date"],
    "lastSunday":panel[-1]["date"],"excluded":dict(exclusions),
    "censoredLast13WeeksCount":exclusions.get("FORWARD_13_WEEK_RIGHT_CENSORED",0),
    "dateGapMacroFilter":"5 consecutive accepted H4.1 releases, max10 days apart, no missing date inside window"},
  "models":spec["fourModels"],"target1":spec["target1"],"target2":spec["target2"],
  "allEligible":describe(panel),"byEra":{k:describe(v) for k,v in eras.items()},
  "fixed13thWeekAnchor":describe(anchor),
  "confirmedStructuralExpansionEvents2020On":event_recall,
  "completeCasePanel":panel,
  "macroVintage":"SOURCE_PAGE_RETRIEVED_2026_ORIGINAL_PUBLICATION_REVISIONS_NOT_VERIFIED",
  "limitations":[
   "Historical conditions for all model labels selected after research looked at historical market data; NOT true OOS or pre-2020 pre-registration",
   "Four filters simply intersect fixed features; better selected-row outcomes would reflect selection and exposure differences, not proven added predictive value",
   "Historical sample 2020-2026 short and overlapping 13wk outcomes heavily correlated; anchor every13th eligible row still cycle-correlated",
   "Outcome confirmed 52wk expansion is itself computed from BTC price, not independent externally determined macro bull cycle",
   "Fed original archival page viewed now might have been edited historically; real published vintages remain unverified",
   "H4.1 total assets minus TGA minus all consolidated RRP is a proxy, not a complete liquidity measure",
   "Eight asset basket has survivorship and listing selection, no broad market cap weighted alt universe",
   "NFCI/ANFCI historical vintages not yet joined; ETF source is likewise PIT unverified",
   "No P&L, trading fees, liquidity at execution, positions or sizing. Research does NOT authorize trades",
   "No change to Spot, Futures, NAV, P&L, reserve, capital, leverage, MASTER or risk limits"]}
 dest=Path("btci_v811_reports");dest.mkdir(exist_ok=True)
 raw=json.dumps(report,ensure_ascii=False,indent=2).encode()
 (dest/"four_lens.json").write_bytes(raw)
 root=f"research/btci/v8.11/runs/{os.environ.get('GITHUB_RUN_ID','manual')}-{os.environ.get('GITHUB_RUN_ATTEMPT','1')}/"
 resultsha=write(s,bucket,root+"four_lens.json",raw)
 manifest={"version":"8.11","status":"FOUR_LENS_EXPLORATORY_COMPLETED",
  "researchOnly":True,"reportSha256":resultsha,
  "inputSha256":{x:y[1] for x,y in (("v86",P86),("v89",P89),("macro",PM))},
  "preregistrationSha256":hash(specraw),"prefix":root}
 manifestsha=write(s,bucket,root+"manifest.json",manifest)
 summary={"status":"V811_FOUR_LENS_WRITEBACK_VERIFIED",
  "sha256":resultsha,"manifestSha256":manifestsha,"prefix":root,
  "dataset":report["dataset"],"all":report["allEligible"],
  "eras":report["byEra"],"anchor":report["fixed13thWeekAnchor"],
  "events":event_recall}
 (dest/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2))
 print("V811_RESULT "+json.dumps(summary,ensure_ascii=False),flush=True)
 if os.getenv("GITHUB_STEP_SUMMARY"):
  with open(os.environ["GITHUB_STEP_SUMMARY"],"a",encoding="utf-8") as f:
   f.write(f"# BTCI v8.11 — сравнение A/B/C/D на одинаковых датах\n\n"
    f"Все {len(panel)} дат; n 2020–2023 = {len(eras['2020-2023'])};"
    f" n 2024–26 = {len(eras['2024-2026'])}. RESEARCH ONLY.\n\n"
    f"R2: {root}\n\nSHA-256: {resultsha}\n")
if __name__=="__main__":main()
