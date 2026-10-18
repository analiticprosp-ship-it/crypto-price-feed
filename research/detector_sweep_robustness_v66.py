#!/usr/bin/env python3
"""v6.6 sweep robustness: 100 repeated regime-matched controls, paired month reporting.
Research-only; no execution or live detector modification.
"""
import ast,hashlib,json,os,random,statistics,sys
from pathlib import Path
import boto3
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
# Reuse exactly v6.5 parsing, signal, and regime logic without running its top-level job.
source=(ROOT/"research/detector_matched_controls_v65.py").read_text()
tree=ast.parse(source)
keep=[n for n in tree.body if isinstance(n,(ast.Import,ast.ImportFrom,ast.FunctionDef,ast.Assign)) and not (isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id in ("s3","out") for t in n.targets))]
scope={"__file__":str(ROOT/"research/detector_matched_controls_v65.py")}
exec(compile(ast.Module(body=keep,type_ignores=[]),"<v65 definitions>","exec"),scope)
read_month=scope["read_month"];evaluate=scope["evaluate"];regime=scope["regime"];forward=scope["forward"]
MONTHS=("2024-09","2025-03","2025-09","2026-03","2026-09")
H={"15m":1,"1h":4,"4h":16,"24h":96}
REPEATS=100
def mean(xs):return statistics.mean(xs) if xs else None
def q(xs,p):
 s=sorted(xs);return s[round((len(s)-1)*p)] if s else None
def summarize(xs):
 return {"n":len(xs),"mean":round(mean(xs),6) if xs else None,"p025":round(q(xs,.025),6) if xs else None,"p975":round(q(xs,.975),6) if xs else None,"fractionPositive":round(sum(x>0 for x in xs)/len(xs),4) if xs else None}
def analyze(bars,sym,month):
 eligible=range(96,len(bars)-96)
 pools={"UP":[],"DOWN":[],"SIDEWAYS":[]}
 events=[]
 for i in eligible:
  r=regime(bars,i);pools[r].append(i)
  status,sweep=evaluate(bars,i)
  if status=="EARLY_CANDIDATE_SHADOW":events.append({"i":i,"regime":r,"sweep":bool(sweep)})
 # Independent 24h non-overlap greedy candidate set.
 selected=[];last=-999
 for e in events:
  if e["i"]-last>=96:selected.append(e);last=e["i"]
 # Precompute forward outcomes once, preserving v6.5 exact return definition.
 outcomes={h:[forward(bars,i,n) for i in eligible] for h,n in H.items()}
 idx=lambda i:i-96
 results={}
 for selection_name,selection in (("all",events),("nonOverlap24h",selected)):
  results[selection_name]={}
  for group in ("sweep","nonSweep","all"):
   chosen=[e for e in selection if group=="all" or e["sweep"]==(group=="sweep")]
   result={}
   for h in H:
    signal=mean([outcomes[h][idx(e["i"])] for e in chosen])
    # Repeat controls, excluding the candidate timestamp. Sampling with replacement.
    draws=[]
    for rep in range(REPEATS):
     seed=int(hashlib.sha256(f"v66/{sym}/{month}/{selection_name}/{group}/{h}/{rep}".encode()).hexdigest()[:15],16)
     rng=random.Random(seed)
     ctrl=[]
     for e in chosen:
      pool=pools[e["regime"]]
      if len(pool)<2:raise ValueError("NO_CONTROL")
      c=rng.choice(pool)
      while c==e["i"]:c=rng.choice(pool)
      ctrl.append(outcomes[h][idx(c)])
     if ctrl:draws.append(signal-mean(ctrl))
    result[h]={"n":len(chosen),"signalMeanPct":round(signal,6) if signal is not None else None,"controlAdvantagePctPoints":summarize(draws)}
   results[selection_name][group]=result
 return {"candidates":len(events),"sweepCandidates":sum(e["sweep"] for e in events),"nonOverlapCandidates":len(selected),"results":results}
s3=boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
out=[]
for sym in ("BTC","ETH"):
 for month in MONTHS:
  r={"symbol":sym,"month":month,"status":"BLOCKED"}
  try:
   bars,sha=read_month(s3,os.environ["R2_BUCKET"],sym,month)
   r.update(analyze(bars,sym,month),sourceSha256=sha,status="RESEARCH_PASS")
  except Exception as exc:r["error"]=str(exc)
  out.append(r)
folder=Path("detector_v66_reports");folder.mkdir(exist_ok=True)
(folder/"sweep_robustness.json").write_text(json.dumps({"version":"6.6","researchOnly":True,"tradesEmitted":0,"originalLiveDetectorParity":"NOT_ESTABLISHED","repeats":REPEATS,"source":"verified Binance USD-M futures 5m R2; original detector_features + direction_models","method":"100 independently seeded random matched controls per asset/month/group/horizon, matching trailing 24h regime, replacement allowed, excluding identical candidate bar","uncertainty":"2.5-97.5 percentiles of control randomization only; NOT a statistical confidence interval; overlapping events, month regime and market selection uncertainty NOT captured","limitations":["Control pool may include other signal events","Selection of 5 historical months not a blind holdout","24h greedy non-overlap not independent random sample","No actual trades, OI, fees, slippage, live detector parity or causal identification"],"results":out},indent=2))
print(json.dumps([{"symbol":r["symbol"],"month":r["month"],"status":r["status"],"candidates":r.get("candidates"),"sweep":r.get("sweepCandidates"),"error":r.get("error")} for r in out],indent=2))
if any(r["status"]!="RESEARCH_PASS" for r in out):raise SystemExit(1)
