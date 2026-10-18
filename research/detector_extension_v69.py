#!/usr/bin/env python3
"""Research-only v6.9: fixed-window out-of-sample extension; no live trading."""
import ast,hashlib,json,os,statistics,sys
from pathlib import Path
from datetime import datetime,timezone
import boto3
ROOT=Path(__file__).resolve().parents[1]
# Import reusable v6.8 definitions without executing its R2 writeback main().
v65=ast.parse((ROOT/"research/detector_matched_controls_v65.py").read_text())
v65keep=[n for n in v65.body if isinstance(n,(ast.Import,ast.ImportFrom,ast.FunctionDef,ast.Assign)) and not (isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id in ("s3","out") for t in n.targets))]
ns={"__file__":str(ROOT/"research/detector_matched_controls_v65.py")}
exec(compile(ast.Module(body=v65keep,type_ignores=[]),"<v65 definitions>","exec"),ns)
src=ast.parse((ROOT/"research/detector_fixed_windows_v68.py").read_text())
v68funcs=[n for n in src.body if isinstance(n,ast.FunctionDef) and n.name in ("avg","rounded","percentile","analyze")]
ns.update(H={"4h":16,"24h":96},SEED=6808)
exec(compile(ast.Module(body=v68funcs,type_ignores=[]),"<v68 functions>","exec"),ns)
read_month,analyze=ns["read_month"],ns["analyze"]
BASE=("2024-09","2025-03","2025-09","2026-03","2026-09")
EXT=("2026-02","2026-04","2026-05","2026-06","2026-07","2026-08")
def aggregate(rows):
 out={"months":len(rows),"candidates":sum(r["totalCandidates"] for r in rows),"firstCandidates":sum(r["firstCandidates"] for r in rows),"firstSweep":sum(r["firstSweep"] for r in rows),"daysWithSweep":sum(r["daysWithSweep"] for r in rows)}
 for horizon in ("4h","24h"):
  a=[];b=[];monthly=[]
  for r in rows:
   h=r["firstCandidateComparison"]["horizons"][horizon]
   if h["groupA"] and h["groupB"]:
    a.append((h["groupA"],h["meanA"]));b.append((h["groupB"],h["meanB"]))
    monthly.append({"symbol":r["symbol"],"month":r["month"],"differencePctPoints":h["differencePctPoints"]})
  def weighted(z):return sum(n*x for n,x in z)/sum(n for n,x in z) if z else None
  ma,mb=weighted(a),weighted(b)
  out[horizon]={"firstSweepN":sum(n for n,_ in a),"firstNonSweepN":sum(n for n,_ in b),"differencePctPoints":round(ma-mb,6) if ma is not None and mb is not None else None,"monthsWithBothGroups":len(monthly),"monthsPositive":sum(x["differencePctPoints"]>0 for x in monthly),"monthsNegative":sum(x["differencePctPoints"]<0 for x in monthly),"note":"Descriptive, event-weighted difference; not causal or independent significance"}
 return out
def main():
 s3=boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
 bucket=os.environ["R2_BUCKET"];rows=[];errors=[]
 for sym in ("BTC","ETH"):
  for month in BASE+EXT:
   try:
    bars,sha=read_month(s3,bucket,sym,month)
    start=datetime.fromtimestamp(bars[0]["t"]/1000,timezone.utc)
    end=datetime.fromtimestamp(bars[-1]["endMs"]/1000,timezone.utc)
    year,m=map(int,month.split("-"))
    nxt=f"{year+1}-01" if m==12 else f"{year}-{m+1:02d}"
    if start!=datetime.fromisoformat(month+"-01").replace(tzinfo=timezone.utc) or end!=datetime.fromisoformat(nxt+"-01").replace(tzinfo=timezone.utc):
     raise ValueError("PARTIAL_MONTH")
    rows.append({"symbol":sym,"month":month,"cohort":"baseline" if month in BASE else "extension", "sourceSha256":sha,**analyze(bars),"status":"RESEARCH_PASS"})
   except Exception as e:errors.append({"symbol":sym,"month":month,"error":str(e)[:200]})
 folder=Path("detector_v69_reports");folder.mkdir(exist_ok=True)
 if errors or len(rows)!=22:
  (folder/"blocked.json").write_text(json.dumps({"status":"BLOCKED","errors":errors},indent=2))
  raise SystemExit("V69_SOURCE_OR_REPLAY_BLOCKED "+json.dumps(errors))
 baseline=[r for r in rows if r["cohort"]=="baseline"]
 extension=[r for r in rows if r["cohort"]=="extension"]
 combined={"baseline":aggregate(baseline),"extension":aggregate(extension),"all":aggregate(rows)}
 report={"version":"6.9","researchOnly":True,"tradesEmitted":0,"originalLiveDetectorParity":"NOT_ESTABLISHED","cohorts":{"baselineMonths":list(BASE),"extensionMonths":list(EXT)},"comparison":combined,"limitations":["Selected six extension months are not a random out-of-sample period","Adjacent UTC day 24h returns can overlap","Small sweep counts and cross-month dependence limit inference","Within-month bootstrap is not a multi-month confidence interval","No execution, costs, OI, funding or full live Detector parity","No trade recommendation"],"results":rows}
 data=json.dumps(report,indent=2,ensure_ascii=False).encode()
 (folder/"comparison.json").write_bytes(data)
 digest=hashlib.sha256(data).hexdigest()
 run=os.environ.get("GITHUB_RUN_ID","manual");attempt=os.environ.get("GITHUB_RUN_ATTEMPT","1")
 prefix=f"research/detector/v6.9/runs/{run}-{attempt}/"
 manifest={"version":"6.9","status":"RESEARCH_PASS","researchOnly":True,"reportSha256":digest,"resultsCount":len(rows),"prefix":prefix,"githubSha":os.environ.get("GITHUB_SHA")}
 (folder/"manifest.json").write_text(json.dumps(manifest,indent=2))
 for name in ("comparison.json","manifest.json"):
  blob=(folder/name).read_bytes();key=prefix+name;sha=hashlib.sha256(blob).hexdigest()
  s3.put_object(Bucket=bucket,Key=key,Body=blob,ContentType="application/json",Metadata={"sha256":sha,"research-only":"true"})
  if hashlib.sha256(s3.get_object(Bucket=bucket,Key=key)["Body"].read()).hexdigest()!=sha:raise SystemExit("V69_WRITEBACK_VERIFICATION_FAILED")
 summary={"status":"V69_RESEARCH_PASS_WRITEBACK_VERIFIED","run":run,"reportSha256":digest,"prefix":prefix,"cohorts":combined}
 print(json.dumps(summary,ensure_ascii=False))
 lines=["# Detector v6.9 — исследовательское сравнение","",f"**Статус:** {summary['status']}",f"**R2:** \`{prefix}\`",f"**SHA-256:** \`{digest}\`","","| Выборка | Наборы | LONG | Первый LONG | Sweep первых | Δ4h п.п. | Δ24h п.п. |","|---|---:|---:|---:|---:|---:|---:|"]
 for name in ("baseline","extension","all"):
  x=combined[name]
  lines.append(f"| {name} | {x['months']} | {x['candidates']} | {x['firstCandidates']} | {x['firstSweep']} | {x['4h']['differencePctPoints']} | {x['24h']['differencePctPoints']} |")
 lines+=["","Разницы описательные, без доказанного торгового преимущества. Live Detector и торговые правила не изменены."]
 md="\n".join(lines)+"\n"
 (folder/"summary.md").write_text(md)
 if os.environ.get("GITHUB_STEP_SUMMARY"):
  with open(os.environ["GITHUB_STEP_SUMMARY"],"a") as f:f.write(md)
if __name__=="__main__":main()
