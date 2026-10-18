#!/usr/bin/env python3
"""Produce a reproducible research index from local verified v6.8 report.
No R2 credentials, no public publishing, no trading decisions.
"""
import hashlib,json,os
from pathlib import Path
p=Path("detector_v68_reports")
report_bytes=(p/"fixed_windows.json").read_bytes()
report=json.loads(report_bytes)
manifest=json.loads((p/"manifest.json").read_text())
digest=hashlib.sha256(report_bytes).hexdigest()
if manifest["status"]!="RESEARCH_PASS" or manifest["reportSha256"]!=digest:
 raise SystemExit("REPORT_INTEGRITY_BLOCKED")
rows=report["results"]
if len(rows)!=10 or any(r.get("status")!="RESEARCH_PASS" for r in rows):
 raise SystemExit("RESEARCH_COMPLETENESS_BLOCKED")
if len({(r["symbol"],r["month"]) for r in rows})!=10:
 raise SystemExit("DUPLICATE_SOURCE_BLOCKED")
run=os.environ.get("GITHUB_RUN_ID","manual")
attempt=os.environ.get("GITHUB_RUN_ATTEMPT","1")
prefix=f"research/detector/v6.8/runs/{run}-{attempt}/"
summary={"version":"6.8","researchOnly":True,"originalLiveDetectorParity":"NOT_ESTABLISHED","writebackStatus":"RESEARCH_PASS_WRITEBACK_VERIFIED","runId":run,"runAttempt":attempt,"r2Prefix":prefix,"reportSha256":digest,"sets":len(rows),"candidates":sum(r["totalCandidates"] for r in rows),"firstCandidates":sum(r["firstCandidates"] for r in rows),"firstSweep":sum(r["firstSweep"] for r in rows),"daysWithSweep":sum(r["daysWithSweep"] for r in rows),"perAssetMonth":[{"symbol":r["symbol"],"month":r["month"],"candidates":r["totalCandidates"],"firstCandidates":r["firstCandidates"],"firstSweep":r["firstSweep"],"daysWithSweep":r["daysWithSweep"],"first4hDifferencePctPoints":r["firstCandidateComparison"]["horizons"]["4h"]["differencePctPoints"],"first24hDifferencePctPoints":r["firstCandidateComparison"]["horizons"]["24h"]["differencePctPoints"]} for r in rows],"limitations":["Per-month effects are not independent significance tests","No trading edge established","No actual execution or live detector parity"]}
(p/"research_index.json").write_text(json.dumps(summary,indent=2,ensure_ascii=False))
lines=["# Detector v6.8 — проверенный исследовательский отчёт","",f"**Статус:** RESEARCH_PASS_WRITEBACK_VERIFIED",f"**Run:** {run}-{attempt}",f"**R2:** \`{prefix}\`",f"**SHA-256:** \`{digest}\`",f"**Наборов:** {summary['sets']}; **LONG:** {summary['candidates']}; **первых LONG в сутки:** {summary['firstCandidates']}; **Sweep среди первых:** {summary['firstSweep']}","","| Актив | Месяц | LONG | Первый LONG | Sweep среди первых | Δ4h (п.п.) | Δ24h (п.п.) |","|---|---|---:|---:|---:|---:|---:|"]
for r in summary["perAssetMonth"]:
 lines.append(f"| {r['symbol']} | {r['month']} | {r['candidates']} | {r['firstCandidates']} | {r['firstSweep']} | {r['first4hDifferencePctPoints']} | {r['first24hDifferencePctPoints']} |")
lines+=["","Δ — разница Sweep и non-Sweep среди первых LONG в сутки. Это описательная статистика, **не торговый P&L и не доказательство преимущества**.","","Live Detector parity: NOT_ESTABLISHED. Торговые правила не изменены."]
markdown="\n".join(lines)+"\n"
(p/"research_summary.md").write_text(markdown)
if os.environ.get("GITHUB_STEP_SUMMARY"):
 with open(os.environ["GITHUB_STEP_SUMMARY"],"a") as f:f.write(markdown)
print("RESEARCH_INDEX_VERIFIED "+json.dumps({"run":run,"sha256":digest,"sets":len(rows),"candidates":summary["candidates"],"firstSweep":summary["firstSweep"],"r2Prefix":prefix}))
