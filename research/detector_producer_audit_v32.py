#!/usr/bin/env python3
"""v3.2 original SHADOW producer audit. Report evidence, not assumed formulas."""
import ast,csv,json,subprocess,collections,re
from pathlib import Path
O=Path("detector_producer_audit_v32_results");O.mkdir(exist_ok=True)
paths=[p for p in Path(".").rglob("*") if p.is_file() and ".git" not in p.parts and (p.suffix in (".py",".yml",".yaml",".json")) and len(p.parts)<7]
terms={"signal_status":r"EARLY_CANDIDATE_SHADOW|NO_EDGE","price_family":r"PRICE_STRUCTURE|CLOSED_15M_OHLCV_AND_RELATIVE_PRICE","flow_family":r"TAKER_VOLUME|SAME_VENUE_3X5M_AGGREGATE|TAKER_IMBALANCE_IMPROVING","oi_context":r"POST_PRICE_BAR_CONTEXT_ONLY|withAlignedOI15m","producer_output":r"detector-candidates\.json","source_inputs":r"detector-rest-flow\.json|market-summary\.json"}
rows=[]
for p in paths:
 if p.stat().st_size>2000000:continue
 try:t=p.read_text(encoding="utf-8")
 except Exception:continue
 for name,pat in terms.items():
  for i,line in enumerate(t.splitlines(),1):
   if re.search(pat,line,re.I):
    rows.append({"path":str(p),"line":i,"family":name,"excerpt":line.strip()[:280],"executable":p.suffix==".py"})
with (O/"producer_evidence.csv").open("w",newline="") as f:
 w=csv.DictWriter(f,fieldnames=["path","line","family","excerpt","executable"]);w.writeheader();w.writerows(rows)
candidates=Path("detector-candidates.json")
status={"candidate_file_exists":candidates.exists(),"evidence_lines":len(rows),"candidate_formula_verified":False,"source_files":[]}
if candidates.exists():
 d=json.loads(candidates.read_text())
 status["current_features"]=d.get("features");status["current_source_provenance"]=d.get("sourceProvenance");status["current_candidate_count"]=len(d.get("candidates",[]))
producer_paths=sorted({r["path"] for r in rows if r["family"]=="producer_output" and r["executable"]})
status["potential_producers"]=producer_paths
# Textual evidence only; do not claim formula equivalence without human/code audit.
status["audit_gate"]="NEEDS_FORMULA_REVIEW" if producer_paths else "PRODUCER_NOT_FOUND"
status["constraints"]=["No synthetic signals or thresholds","Tardis OI/funding do not substitute aggregated taker flow","No guarantee same-venue Tardis trades match original aggregation","Preserve observed firstDetectedAt latency and no future data","Listing dates define eligible historical universe","All days, including zero-signal days, required in eventual replay","No changes to live Detector/Futures/P&L"]
(O/"audit_manifest.json").write_text(json.dumps(status,ensure_ascii=False,indent=2))
print(json.dumps({"audit_gate":status["audit_gate"],"potential_producers":producer_paths,"evidence_lines":len(rows)},ensure_ascii=False))
