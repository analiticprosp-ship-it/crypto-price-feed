#!/usr/bin/env python3
"""v6.7 event-cluster replay; historical research only."""
import ast,hashlib,json,os,random,statistics,sys
from pathlib import Path
import boto3
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
tree=ast.parse((ROOT/"research/detector_matched_controls_v65.py").read_text())
keep=[n for n in tree.body if isinstance(n,(ast.Import,ast.ImportFrom,ast.FunctionDef,ast.Assign)) and not (isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id in ("s3","out") for t in n.targets))]
scope={"__file__":str(ROOT/"research/detector_matched_controls_v65.py")}
exec(compile(ast.Module(body=keep,type_ignores=[]),"<v65 definitions>","exec"),scope)
read_month=scope["read_month"];evaluate=scope["evaluate"];regime=scope["regime"];forward=scope["forward"]
MONTHS=("2024-09","2025-03","2025-09","2026-03","2026-09")
H={"4h":16,"24h":96}
GAPS=(16,96)
REPEATS=500
def mean(a):return statistics.mean(a) if a else None
def quantile(a,p):
 if not a:return None
 b=sorted(a);j=(len(b)-1)*p;k=int(j);return b[k]+(b[min(k+1,len(b)-1)]-b[k])*(j-k)
def ci(a):
 return {"mean":round(mean(a),6),"p025":round(quantile(a,.025),6),"p975":round(quantile(a,.975),6)}
def clusters(events,gap):
 groups=[]
 for e in events:
  if not groups or e["i"]-groups[-1][-1]["i"]>gap:groups.append([e])
  else:groups[-1].append(e)
 return groups
def choose(group,rule):
 if rule=="first":return group[0]
 if rule=="last":return group[-1]
 if rule=="firstSweepElseFirst":return next((e for e in group if e["sweep"]),group[0])
 raise ValueError(rule)
def analyze(bars,sym,month):
 eligible=range(96,len(bars)-96)
 events=[]
 for i in eligible:
  status,sweep=evaluate(bars,i)
  if status=="EARLY_CANDIDATE_SHADOW":events.append({"i":i,"sweep":bool(sweep),"regime":regime(bars,i)})
 out={}
 for gap in GAPS:
  groups=clusters(events,gap)
  policies={}
  for rule in ("first","last","firstSweepElseFirst"):
   chosen=[choose(g,rule) for g in groups]
   sweep=[e for e in chosen if e["sweep"]]
   non=[e for e in chosen if not e["sweep"]]
   byreg={r:[e for e in non if e["regime"]==r] for r in ("UP","DOWN","SIDEWAYS")}
   comparison={}
   for horizon,n in H.items():
    sr=[forward(bars,e["i"],n) for e in sweep]
    nr=[forward(bars,e["i"],n) for e in non]
    # Matched non-sweep LONG control, from a different episode. Without replacement not guaranteed.
    diffs=[]
    seed=int(hashlib.sha256(f"v67/{sym}/{month}/{gap}/{rule}/{horizon}".encode()).hexdigest()[:15],16)
    rng=random.Random(seed)
    if sr and all(byreg[e["regime"]] for e in sweep):
     for _ in range(REPEATS):
      controls=[forward(bars,rng.choice(byreg[e["regime"]])["i"],n) for e in sweep]
      diffs.append(mean(sr)-mean(controls))
    # Cluster bootstrap on selected episode outcomes (not iid 15m candles).
    boot=[]
    if sr and nr:
     for _ in range(REPEATS):
      ss=[rng.choice(sr) for _ in sr];nn=[rng.choice(nr) for _ in nr]
      boot.append(mean(ss)-mean(nn))
    comparison[horizon]={"sweepN":len(sr),"nonSweepN":len(nr),"sweepMeanPct":round(mean(sr),6) if sr else None,"nonSweepMeanPct":round(mean(nr),6) if nr else None,"unmatchedDifferencePctPoints":round(mean(sr)-mean(nr),6) if sr and nr else None,"clusterBootstrapDifference":ci(boot) if boot else None,"matchedNonSweepLongDifference":ci(diffs) if diffs else None,"matchingStatus":"OK" if diffs else "INSUFFICIENT_REGIME_MATCH"}
   policies[rule]={"selectedEpisodes":len(chosen),"sweepSelected":len(sweep),"horizons":comparison}
  out[str(gap)]={"gapBars":gap,"episodes":len(groups),"multiEventEpisodes":sum(len(g)>1 for g in groups),"maxEpisodeEvents":max(map(len,groups),default=0),"policies":policies}
 return {"candidateCount":len(events),"sweepCount":sum(e["sweep"] for e in events),"clusterResults":out}
s3=boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
results=[]
for sym in ("BTC","ETH"):
 for month in MONTHS:
  r={"symbol":sym,"month":month,"status":"BLOCKED"}
  try:
   bars,sha=read_month(s3,os.environ["R2_BUCKET"],sym,month)
   r.update(analyze(bars,sym,month),sourceSha256=sha,status="RESEARCH_PASS")
  except Exception as exc:r["error"]=str(exc)
  results.append(r)
p=Path("detector_v67_reports");p.mkdir(exist_ok=True)
(p/"event_independence.json").write_text(json.dumps({"version":"6.7","researchOnly":True,"tradesEmitted":0,"originalLiveDetectorParity":"NOT_ESTABLISHED","method":"cluster consecutive LONG candidates with gaps <=4h or <=24h; compare first/last/first-sweep policy; matched controls are non-sweep LONG from other selected episodes, same trailing-24h regime","resamples":REPEATS,"limitations":["Cluster resampling is within month and not a confidence interval across market regimes/years","Different episode policies are sensitivity analyses, not tradeable selection without validation","First-sweep policy is retrospective and cannot be treated as real-time execution","Last-event policy has lookahead selection bias","Control matching with replacement and small episode samples can be unstable","No live detector parity, independent OI, trading costs, or execution P&L"],"results":results},indent=2))
print(json.dumps([{"symbol":r["symbol"],"month":r["month"],"status":r["status"],"events":r.get("candidateCount"),"error":r.get("error")} for r in results],indent=2))
if any(r["status"]!="RESEARCH_PASS" for r in results):raise SystemExit(1)
