#!/usr/bin/env python3
"""v6.8 fixed UTC-day windows and versioned Cloudflare R2 research writeback."""
import ast,hashlib,json,os,random,statistics,sys
from datetime import datetime,timezone
from pathlib import Path
import boto3
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
src=(ROOT/"research/detector_matched_controls_v65.py").read_text()
tree=ast.parse(src)
keep=[n for n in tree.body if isinstance(n,(ast.Import,ast.ImportFrom,ast.FunctionDef,ast.Assign)) and not (isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id in ("s3","out") for t in n.targets))]
scope={"__file__":str(ROOT/"research/detector_matched_controls_v65.py")}
exec(compile(ast.Module(body=keep,type_ignores=[]),"<v65 definitions>","exec"),scope)
read_month,evaluate,regime,forward=(scope[x] for x in ("read_month","evaluate","regime","forward"))
MONTHS=("2024-09","2025-03","2025-09","2026-03","2026-09")
H={"4h":16,"24h":96}
SEED=6808
def avg(xs):return statistics.mean(xs) if xs else None
def rounded(x):return round(x,6) if x is not None else None
def percentile(xs,p):
 if not xs:return None
 a=sorted(xs);v=(len(a)-1)*p;j=int(v)
 return a[j]+(a[min(j+1,len(a)-1)]-a[j])*(v-j)
def analyze(bars):
 # Eligible bars have a full trailing 24h regime and forward 24h price.
 days={}
 for i in range(96,len(bars)-96):
  status,sweep=evaluate(bars,i)
  if status!="EARLY_CANDIDATE_SHADOW":continue
  day=datetime.fromtimestamp(bars[i]["t"]/1000,timezone.utc).strftime("%Y-%m-%d")
  days.setdefault(day,[]).append({"i":i,"sweep":bool(sweep),"regime":regime(bars,i)})
 # First candidate is a prospective rule. Sweep observed later in day is descriptive only.
 first=[e[0] for e in days.values()]
 first_sweep=[e for e in first if e["sweep"]]
 first_non=[e for e in first if not e["sweep"]]
 # Secondary prospective sweep-first policy: only acts at the first sweep, never uses future selection.
 sweep_first=[next((e for e in es if e["sweep"]),None) for es in days.values()]
 sweep_first=[e for e in sweep_first if e is not None]
 def compare(a,b,label):
  out={}
  for h,n in H.items():
   aa=[forward(bars,e["i"],n) for e in a]
   bb=[forward(bars,e["i"],n) for e in b]
   rng=random.Random(SEED+n+len(a)*17+len(b)*31)
   boot=[]
   if aa and bb:
    for _ in range(1000):
     boot.append(avg([rng.choice(aa) for _ in aa])-avg([rng.choice(bb) for _ in bb]))
   out[h]={"groupA":len(aa),"groupB":len(bb),"meanA":rounded(avg(aa)),"meanB":rounded(avg(bb)),"differencePctPoints":rounded(avg(aa)-avg(bb)) if aa and bb else None,"bootstrapP025":rounded(percentile(boot,.025)),"bootstrapP975":rounded(percentile(boot,.975))}
  return {"comparison":label,"horizons":out}
 # Matched non-sweep LONG controls within same month and past-only regime, on different UTC days.
 # This is explicitly exploratory: a sampled control day may overlap another signal's forward horizon.
 pools={}
 for day,es in days.items():
  for e in es:
   if not e["sweep"]:pools.setdefault(e["regime"],[]).append((day,e))
 matched={}
 for h,n in H.items():
  rng=random.Random(SEED+n)
  draws=[]
  for rep in range(500):
   paired=[]
   for day,es in days.items():
    sweep=next((e for e in es if e["sweep"]),None)
    if sweep is None:continue
    candidates=[e for d,e in pools.get(sweep["regime"],[]) if d!=day]
    if not candidates:continue
    control=rng.choice(candidates)
    paired.append(forward(bars,sweep["i"],n)-forward(bars,control["i"],n))
   if paired:draws.append(avg(paired))
  matched[h]={"repeats":len(draws),"meanDifferencePctPoints":rounded(avg(draws)),"controlDrawP025":rounded(percentile(draws,.025)),"controlDrawP975":rounded(percentile(draws,.975)),"note":"Randomization range, NOT confidence interval"}
 return {"utcDaysWithCandidates":len(days),"totalCandidates":sum(map(len,days.values())),"firstCandidates":len(first),"firstSweep":len(first_sweep),"firstNonSweep":len(first_non),"daysWithSweep":len(sweep_first),"firstCandidateComparison":compare(first_sweep,first_non,"First LONG per UTC day: sweep vs non-sweep"),"sweepFirstMatchedNonSweep":matched}
def main():
 s3=boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
 bucket=os.environ["R2_BUCKET"]
 results=[]
 for sym in ("BTC","ETH"):
  for month in MONTHS:
   record={"symbol":sym,"month":month,"status":"BLOCKED"}
   try:
    bars,sha=read_month(s3,bucket,sym,month)
    record.update(analyze(bars),sourceSha256=sha,status="RESEARCH_PASS")
   except Exception as exc:record["error"]=str(exc)
   results.append(record)
 folder=Path("detector_v68_reports");folder.mkdir(exist_ok=True)
 report={"version":"6.8","researchOnly":True,"tradesEmitted":0,"originalLiveDetectorParity":"NOT_ESTABLISHED","method":"fixed UTC calendar-day buckets; first eligible LONG per day; first sweep on day separately matched to non-sweep LONG from other days in same month/regime","limitations":["First sweep in day is prospective only if waiting for sweep; it is not the first LONG","Bootstrap within each asset-month does not capture month/year selection uncertainty","Calendar-day windows and 24h outcomes can still overlap across adjacent days","Control selection with replacement and same-regime matching are descriptive, not causal","No execution, costs, independent OI or full live parity"],"results":results}
 payload=json.dumps(report,indent=2,ensure_ascii=False).encode()
 (folder/"fixed_windows.json").write_bytes(payload)
 ok=all(r["status"]=="RESEARCH_PASS" for r in results)
 manifest={"version":"6.8","researchOnly":True,"status":"RESEARCH_PASS" if ok else "BLOCKED","reportSha256":hashlib.sha256(payload).hexdigest(),"sourceSha256":{r["symbol"]+"/"+r["month"]:r.get("sourceSha256") for r in results},"githubSha":os.environ.get("GITHUB_SHA"),"runId":os.environ.get("GITHUB_RUN_ID"),"resultsCount":len(results)}
 (folder/"manifest.json").write_text(json.dumps(manifest,indent=2))
 if not ok:
  print(json.dumps([{"symbol":r["symbol"],"month":r["month"],"error":r.get("error")} for r in results if r["status"]!="RESEARCH_PASS"],indent=2))
  raise SystemExit("SOURCE_OR_RESEARCH_BLOCKED: no R2 writeback")
 # Versioned immutable-by-convention run path; never overwrite historical source keys.
 run=os.environ.get("GITHUB_RUN_ID","manual")
 attempt=os.environ.get("GITHUB_RUN_ATTEMPT","1")
 prefix=f"research/detector/v6.8/runs/{run}-{attempt}/"
 for filename in ("fixed_windows.json","manifest.json"):
  data=(folder/filename).read_bytes()
  key=prefix+filename
  s3.put_object(Bucket=bucket,Key=key,Body=data,ContentType="application/json",Metadata={"sha256":hashlib.sha256(data).hexdigest(),"research-only":"true"})
  head=s3.head_object(Bucket=bucket,Key=key)
  if head.get("Metadata",{}).get("sha256")!=hashlib.sha256(data).hexdigest():raise ValueError("WRITEBACK_VERIFICATION_FAILED")
 print(json.dumps({"status":"RESEARCH_PASS_WRITEBACK_VERIFIED","prefix":prefix,"reportSha256":manifest["reportSha256"],"results":len(results)}))
if __name__=="__main__":main()
