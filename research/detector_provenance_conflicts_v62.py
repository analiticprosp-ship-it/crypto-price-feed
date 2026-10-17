#!/usr/bin/env python3
"""v6.2 research-only provenance audit and LONG/SHORT conflict attribution."""
import ast,json,re,subprocess
from collections import Counter
from pathlib import Path
root=Path(__file__).resolve().parents[1]
report_path=root/"detector_v61_reports/long_sweep_conflicts.json"
out=root/"detector_v62_reports"
out.mkdir(exist_ok=True)
source=json.loads(report_path.read_text())
def tracked():
 p=subprocess.run(["git","ls-files","--","*.py","*.js","*.ts","*.mjs","*.cjs"],cwd=root,capture_output=True,text=True,check=True)
 return [root/x for x in p.stdout.splitlines()]
files=tracked()
occ=[]
for path in files:
 try:s=path.read_text(encoding="utf-8")
 except (OSError,UnicodeError):continue
 for n,line in enumerate(s.splitlines(),1):
  if "detectorFeatures" in line or "sweptLowReclaimed" in line or "sweptHighRejected" in line:
   occ.append({"path":str(path.relative_to(root)),"line":n,"snippet":line.strip()[:220]})
# Exact original producer is NOT automatically established by text matches.
# Require separate semantic equivalence review; do not infer from a matching name.
audit={"references":occ,"filesScanned":len(files),"originalProducer":"NOT_VERIFIED","exactFeatureParity":"NOT_ESTABLISHED","reviewRequired":True}
result=[]
for r in source["results"]:
 if r.get("status")!="RESEARCH_DIAGNOSTIC_PASS":
  result.append({"symbol":r.get("symbol"),"status":"BLOCKED","reason":"V61_INPUT_NOT_PASS"});continue
 events=r["conflictEvents"]
 breakdown=Counter()
 detail=[]
 for e in events:
  if e["long"]!="CONFLICT" or e["short"]!="CONFLICT":raise ValueError("CONFLICT_STATE_INCONSISTENT")
  if not(e["longPrice"] and e["longFlow"]):raise ValueError("LONG_CONFLICT_FAMILY_INCONSISTENT")
  reasons=[]
  if e["sweepLow"]:reasons.append("SWEEP_LOW")
  if e["sweepHigh"]:reasons.append("SWEEP_HIGH")
  if e["sweepLow"] and e["sweepHigh"]:breakdown["DUAL_SWEEP"]+=1
  elif e["sweepLow"]:breakdown["LOW_SWEEP_ONLY"]+=1
  elif e["sweepHigh"]:breakdown["HIGH_SWEEP_ONLY"]+=1
  else:breakdown["NO_SWEEP"]+=1
  imbalance=e.get("imbalance")
  if imbalance is None:breakdown["MISSING_IMBALANCE"]+=1
  elif imbalance>0:breakdown["POSITIVE_IMBALANCE"]+=1
  elif imbalance<0:breakdown["NEGATIVE_IMBALANCE"]+=1
  else:breakdown["ZERO_IMBALANCE"]+=1
  detail.append({"eventEndMs":e["eventEndMs"],"pricePattern":reasons or ["BODY_OR_CLOSE_LOCATION"],"imbalance":imbalance,"previousImbalance":e.get("previousImbalance"),"longContext":e["longContext"],"shortContext":e["shortContext"],"tradeEligible":False})
 if len(events)!=r["conflicts"]:raise ValueError("CONFLICT_COUNT_MISMATCH")
 if r["longWithSweep"]+r["longWithoutSweep"]!=r["longCandidates"]:raise ValueError("LONG_SPLIT_MISMATCH")
 result.append({"symbol":r["symbol"],"status":"DIAGNOSTIC_PASS","longCandidates":r["longCandidates"],"longWithSweep":r["longWithSweep"],"longWithoutSweep":r["longWithoutSweep"],"conflicts":len(events),"breakdown":dict(breakdown),"conflictEvents":detail,"sourceSha256":r["sourceSha256"]})
output={"version":"6.2","researchOnly":True,"notTradeApproval":True,"tradesEmitted":0,"source":"v6.1 R2-derived diagnostic artifact regenerated in same workflow","originalDetectorParity":"NOT_ESTABLISHED","provenanceAudit":audit,"limitations":["Textual source search does not prove feature semantics or parity","Conflicts remain non-executable","Historical Binance USD-M futures are not spot","No P&L, outcome study, or trade authorization"],"results":result}
(out/"provenance_conflict_audit.json").write_text(json.dumps(output,indent=2,ensure_ascii=False))
print(json.dumps({"filesScanned":audit["filesScanned"],"featureReferences":len(occ),"parity":audit["exactFeatureParity"],"summary":[{k:v for k,v in r.items() if k!="conflictEvents"} for r in result]},indent=2))
if any(r["status"]!="DIAGNOSTIC_PASS" for r in result):raise SystemExit(1)
