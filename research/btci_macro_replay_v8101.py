#!/usr/bin/env python3
"""BTCI v8.10.1 source-backed dated H41 header correction.
Replays *only* archived blocked pages. Never overwrites v8.10 baseline results.
"""
import datetime as dt,hashlib,json,os,statistics
from collections import Counter
from pathlib import Path
from btci_h41_full_history_v810 import (
 cloud,get,write,parse,classify_week,eventstat,V89
)
ROOT=Path(__file__).resolve().parents[1]
PREREG="research/btci_v8101_date_layout_correction_prereg_2026-10-18.json"
POLD=("research/btci/v8.10/runs/39140665477-1/combined/macro_study.json",
 "b370a96b62452fc87ca3db792562d6b240c39acc2af61bf0d2b0fc00800a93f1")
def sha(v):return hashlib.sha256(v).hexdigest()
def main():
 pre=(ROOT/PREREG).read_bytes();pr=json.loads(pre)
 if (pr["version"]!="8.10.1" or
 pr["immutableParents"]!={"originalStudy":{"key":POLD[0],"sha256":POLD[1]},
   "btcRegime":{"key":V89[0],"sha256":V89[1]}}):
  raise SystemExit("V8101_PREREG_CHANGED")
 s=cloud();b=os.environ["R2_BUCKET"]
 old=get(s,b,*POLD);btc=get(s,b,*V89)
 if old["version"]!="8.10" or len(old["yearlySourceManifest"])!=16 or btc["switchCount"]!=29:
  raise SystemExit("V8101_PARENT_STRUCTURE_CHANGED")
 # Every annual source report already written to R2, pinned from baseline study.
 originals=[];recovered=[];blocked=[];baseline_details=[]
 for src in old["yearlySourceManifest"]:
  yr=get(s,b,src["key"],src["sha256"])
  if yr["year"]!=src["year"] or yr["kind"]!="YEAR":
   raise SystemExit("V8101_YEAR_PROVENANCE_CHANGED")
  for rec in yr["releases"]:
   if rec["status"]=="PARSED":
    originals.append(rec["value"])
    continue
   if rec["status"]=="PARSE_BLOCKED" and rec.get("r2Key") and rec.get("htmlSha256"):
    raw=s.get_object(Bucket=b,Key=rec["r2Key"])["Body"].read()
    if sha(raw)!=rec["htmlSha256"]:
     raise SystemExit("V8101_ARCHIVED_RAW_SOURCE_SHA_CHANGED:"+rec["date"])
    try: val=parse(raw,rec["date"])
    except Exception as exc:
     blocked.append({"date":rec["date"],"kind":"PARSE_STILL_BLOCKED",
       "reason":str(type(exc).__name__)+":"+str(exc)[:160],
       "originalSha":rec["htmlSha256"],"rawKey":rec["r2Key"]})
    else:
     originals.append(val)
     recovered.append({"date":rec["date"],"sourceKey":rec["r2Key"],
        "rawSha256":rec["htmlSha256"],"values":val})
   else:
    blocked.append({"date":rec["date"],"kind":rec["status"],"reason":rec.get("error"),
       "sourceURL":rec.get("url")})
 allDates=[r["releaseDate"] for r in originals]
 if len(allDates)!=len(set(allDates)):raise SystemExit("V8101_DUPLICATE_OFFICIAL_RELEASE")
 originals.sort(key=lambda x:x["releaseDate"])
 if len(originals)<old["parsedRows"]+30:
  raise SystemExit("V8101_RECOVERY_INSUFFICIENT:"+str(len(recovered)))
 # Frozen BTC-only phase labels and returns (one per Sunday).
 rows=[]
 for x in btc["pastOnlyWeeklyContext"]:
  day=dt.date.fromisoformat(x["date"])
  macro=classify_week(originals,day)
  rows.append({"date":x["date"],"structural":x["confirmed"],
   "rawStructural":x["raw"],"weeklyTrend":x["weeklyTrend"],
   "breadthAvailable":x["breadth"]["status"]=="AVAILABLE",
   "macro":macro})
 if len(rows)!=750 or rows[-1]["date"]!="2026-10-11":
  raise SystemExit("V8101_BTC_WEEKLY_PANEL_CHANGED")
 mapped={x["date"]:x for x in rows}
 events=[]
 for e in btc["switches"]:
  macros=mapped[e["date"]]["macro"]
  events.append({"date":e["date"],"from":e["from"],"to":e["to"],
    "macro":macros,"future":{"13":e["future"]["13"],"26":e["future"]["26"]}})
 cats=("STRUCTURAL_EXPANSION_PRICE_PROXY","STRUCTURAL_CONTRACTION_PRICE_PROXY",
 "TRANSITION_OR_REBOUND_PRICE_PROXY")
 byswitch={}
 for cat in cats:
  subset=[x for x in events if x["to"]==cat]
  byswitch[cat]={sg:eventstat([r for r in subset if r["macro"].get("macroDirection")==sg])
     for sg in ("UP","DOWN","FLAT")}
  byswitch[cat]["MISSING"]={"n":sum(x["macro"]["status"]!="AVAILABLE" for x in subset)}
 bystate={}
 for cat in cats:
  z=[x for x in rows if x["structural"]==cat]
  bystate[cat]={"n":len(z),
   "macroDirectionCounts":dict(Counter(x["macro"].get("macroDirection","UNKNOWN") for x in z))}
 current=rows[-1]
 if current["macro"]["status"]=="AVAILABLE" and current["macro"]["lastReleaseDate"]<"2026-10-01":
  raise SystemExit("V8101_CURRENT_STILL_USES_STALE_SEPT_RELEASE")
 report={"version":"8.10.1","status":"DATED_H41_SOURCE_REPLAY_RESEARCH_ONLY",
  "researchOnly":True,"noTradingAuthority":True,
  "original":{"key":POLD[0],"sha256":POLD[1]},
  "BTCParent":{"key":V89[0],"sha256":V89[1]},
  "preregistration":{"path":PREREG,"sha256":sha(pre)},
  "baselineAcceptedRows":old["parsedRows"],
  "acceptedArchivedRowsAfterCorrection":len(originals),
  "recoveredRows":len(recovered),"unavailableRows":len(blocked),
  "remainingProblems":blocked,
  "replayAudit":recovered,
  "sourceYearManifests":old["yearlySourceManifest"],
  "publicationSourceVintage":"CURRENT_COPY_OF_HISTORICAL_DATED_RELEASE_UNVERIFIED_IF_REVISED",
  "allHistoricalReleaseObservations":originals,
  "macroMethod":"Dated Fed total assets minus TGA minus total RRPA (millions USD); 4-release delta; no true market net liquidity claim.",
  "weeklyStructuralCoverage":{"total":len(rows),"available":sum(x["macro"]["status"]=="AVAILABLE" for x in rows),
    "unknown":dict(Counter(x["macro"]["status"] for x in rows if x["macro"]["status"]!="AVAILABLE"))},
  "regimes":bystate,
  "switches":byswitch,"events":events,
  "asofWeeklyRows":rows,"current":current,
  "limitations":[
    "Not authenticated immutable original publication vintages; pages retrieved retrospectively",
    "Dated pages do not establish availability of numerical revisions within the same day",
    "NFCI Chicago Fed economic conditions not yet joined with vintage data",
    "Fed balance minus TGA minus total reverse repos not a causal measure of market available liquidity",
    "Past BTC price regimes and macro policy coevolve, observed returns overlap",
    "Very few structural switches per macro sign; no calibrated probability, backtest alpha or causal attribution",
    "No orders or Spot/Futures/NAV/P&L/reserve/capital/trading limit/MASTER changes"]}
 folder=Path("btci_v8101_reports");folder.mkdir(exist_ok=True)
 raw=json.dumps(report,ensure_ascii=False,indent=2).encode()
 (folder/"corrected_macro_study.json").write_bytes(raw)
 r2prefix=f"research/btci/v8.10.1/runs/{os.environ['GITHUB_RUN_ID']}-{os.environ.get('GITHUB_RUN_ATTEMPT','1')}/"
 rd=write(s,b,r2prefix+"macro_study.json",raw)
 md=write(s,b,r2prefix+"manifest.json",{
  "version":"8.10.1","researchOnly":True,
  "status":"DATED_H41_ARCHIVE_REPLAY_PASS","reportSha256":rd,
  "parentSha256":POLD[1],"BTCParentSha256":V89[1]})
 summary={"status":"V8101_H41_DATE_REPLAY_PASS_WRITEBACK_VERIFIED",
  "r2Prefix":r2prefix,"reportSha256":rd,"manifestSha256":md,
  "rowsBefore":old["parsedRows"],"rowsAfter":len(originals),
  "recoveredCount":len(recovered),"unavailable":blocked[:6],
  "coverage":report["weeklyStructuralCoverage"],
  "regimes":bystate,"switches":byswitch,"current":current,
  "last15RecoveredDates":[x["date"] for x in recovered[-15:]]}
 (folder/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2))
 print("V8101_RESULT "+json.dumps(summary,ensure_ascii=False),flush=True)
if __name__=="__main__":main()
