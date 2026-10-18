#!/usr/bin/env python3
"""BTCI v8.10.2: conservative H41 missing official release in 4-release lookback.
Research-only. Parent reports immutable and SHA-verified.
"""
import datetime as dt,hashlib,json,os
from collections import Counter
from pathlib import Path
from btci_h41_full_history_v810 import cloud,get,write,eventstat
ROOT=Path(__file__).resolve().parents[1]
P="research/btci_v8102_missing_release_guard_prereg_2026-10-18.json"
OLD=("research/btci/v8.10.1/runs/39141047403-1/macro_study.json",
 "230f5c2eebdba583dbadf4a44d50123fb85f93c39b318f5d4fcbb7cb7480fb81")
BTC=("research/btci/v8.9/runs/39138844921-1/multiscale.json",
 "4b8822e929aff5569fa9cd105404c02b110927a970aed33db68910925c111b73")
def sha(b):return hashlib.sha256(b).hexdigest()
def main():
 prereg=(ROOT/P).read_bytes();pp=json.loads(prereg)
 if pp["version"]!="8.10.2" or pp["parents"]!={"sourceVerifiedV8101":{"key":OLD[0],"sha256":OLD[1]},
   "frozenBTCV89":{"key":BTC[0],"sha256":BTC[1]}}:
  raise SystemExit("V8102_PREREG_CHANGED")
 s=cloud();b=os.environ["R2_BUCKET"]
 old=get(s,b,*OLD);btc=get(s,b,*BTC)
 if len(old["asofWeeklyRows"])!=750 or len(old["remainingProblems"])!=3 or btc["switchCount"]!=29:
  raise SystemExit("V8102_PARENT_CHANGED")
 official=[dt.date.fromisoformat(x["releaseDate"]) for x in old["allHistoricalReleaseObservations"]]
 gaps=[dt.date.fromisoformat(x["date"]) for x in old["remainingProblems"]]
 official.sort()
 adjusted=[];changed=[]
 for row in old["asofWeeklyRows"]:
  day=dt.date.fromisoformat(row["date"]);cutoff=day-dt.timedelta(days=3)
  accepted=[x for x in official if x<=cutoff]
  macro=dict(row["macro"])
  missing=[]
  if len(accepted)>=5:
   anchor=accepted[-5]
   missing=[x.isoformat() for x in gaps if anchor<=x<=cutoff]
  if missing:
   changed.append({"date":row["date"],"old":macro,"gaps":missing})
   macro={"status":"RELEASE_UNAVAILABLE_IN_LOOKBACK","missingPublishedDate":missing,
     "strictPIT":False}
  adjusted.append({**row,"macro":macro})
 if not changed:raise SystemExit("V8102_EXPECTED_BLOCKED_RELEASES_MISSING")
 mapped={x["date"]:x for x in adjusted}
 categories=("STRUCTURAL_EXPANSION_PRICE_PROXY","STRUCTURAL_CONTRACTION_PRICE_PROXY",
 "TRANSITION_OR_REBOUND_PRICE_PROXY")
 states={}
 for k in categories:
  g=[x for x in adjusted if x["structural"]==k]
  states[k]={"weeks":len(g),"directions":dict(Counter(z["macro"].get("macroDirection","UNAVAILABLE") for z in g))}
 transitions=[]
 for e in btc["switches"]:
  transitions.append({"date":e["date"],"to":e["to"],"from":e["from"],
   "macro":mapped[e["date"]]["macro"],"future":{"13":e["future"]["13"],"26":e["future"]["26"]}})
 sw={}
 for k in categories:
  z=[x for x in transitions if x["to"]==k]
  sw[k]={d:eventstat([x for x in z if x["macro"].get("macroDirection")==d])
   for d in ("UP","DOWN","FLAT")}
  sw[k]["MISSING"]={"n":sum(x["macro"]["status"]!="AVAILABLE" for x in z)}
 curr=adjusted[-1]
 if curr["date"]!="2026-10-11" or curr["macro"].get("lastReleaseDate")!="2026-10-08" or curr["macro"].get("macroDirection")!="DOWN":
  raise SystemExit("V8102_CURRENT_CONTEXT_CHANGED")
 report={"version":"8.10.2","status":"H41_MACRO_SOURCE_GAP_GUARD_RESEARCH_ONLY",
  "researchOnly":True,"tradingAuthorityGranted":False,"asOfUTC":"2026-10-11",
  "source":{"key":OLD[0],"sha256":OLD[1]},"BTCParent":{"key":BTC[0],"sha256":BTC[1]},
  "preregistration":{"path":P,"sha256":sha(prereg)},
  "sourceReleasesAccepted":old["acceptedArchivedRowsAfterCorrection"],
  "sourceDateCandidates":old["acceptedArchivedRowsAfterCorrection"]+len(old["remainingProblems"]),
  "blockedReleasePages":old["remainingProblems"],
  "staleQuarantineWeeks":changed,
  "weeklyCoverage":{"total":len(adjusted),
   "usable":sum(x["macro"]["status"]=="AVAILABLE" for x in adjusted),
   "unavailable":dict(Counter(x["macro"]["status"] for x in adjusted if x["macro"]["status"]!="AVAILABLE"))},
  "longBTCStateWithLiquidity":states,
  "structuralTransitionsWithLiquidity":sw,
  "transitions":transitions,"panel":adjusted,"current":curr,
  "provenanceLimitations":["Pages are currently retrieved historical dated HTML, not authenticated original revisions",
   "Historical H41 observed Wednesday and publication date not the same; source 3-day publication lag applied",
   "No original NFCI financial conditions vintages in this report",
   "Use no macro value if 4-release window includes an expected inaccessible official publication",
   "Total Fed assets minus TGA minus aggregate reverse repos is a descriptive simplified balance proxy, not true net liquidity",
   "Same large Bitcoin cycles induce dependence; observed 13w windows overlap, no causal inference, calibrated probability or trading signals",
   "No Spot, Futures, NAV, capital, P&L, reserve, trading limit, live Detector or MASTER updates"]}
 folder=Path("btci_v8102_reports");folder.mkdir(exist_ok=True)
 blob=json.dumps(report,ensure_ascii=False,indent=2).encode()
 (folder/"macro_final.json").write_bytes(blob)
 keyroot=f"research/btci/v8.10.2/runs/{os.environ['GITHUB_RUN_ID']}-{os.environ.get('GITHUB_RUN_ATTEMPT','1')}/"
 dg=write(s,b,keyroot+"macro_final.json",blob)
 md=write(s,b,keyroot+"manifest.json",{
  "version":"8.10.2","status":"H41_MACRO_GAP_GUARD_PASS","reportSha256":dg,"researchOnly":True,"sourceSha256":OLD[1]})
 summary={"status":"V8102_GAP_GUARD_REPORT_PASS_WRITEBACK_VERIFIED",
  "r2Prefix":keyroot,"reportSha256":dg,"manifestSha256":md,
  "sourceCount":report["sourceReleasesAccepted"],"sourceCandidates":report["sourceDateCandidates"],
  "coverage":report["weeklyCoverage"],"gapDates":[x.isoformat() for x in gaps],
  "quarantinedWeeks":[x["date"] for x in changed],"states":states,
  "switchStudy":sw,"current":curr}
 (folder/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2))
 print("V8102_RESULT "+json.dumps(summary,ensure_ascii=False),flush=True)
if __name__=="__main__":main()
