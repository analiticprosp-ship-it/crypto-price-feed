#!/usr/bin/env python3
"""v6.5 research-only matched-control replay, across fixed historical months."""
import csv,hashlib,io,json,os,random,statistics,sys,zipfile
from pathlib import Path
import boto3
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from build_market_summary import detector_features
from detector_signal_engine import direction_models
MONTHS=("2024-09","2025-03","2025-09","2026-03","2026-09")
H={"15m":1,"1h":4,"4h":16,"24h":96}
P5=300000
def read_month(s3,bucket,sym,month):
 key=f"binance/usdm/5m/{sym}USDT/{month}.zip"
 head=s3.head_object(Bucket=bucket,Key=key)
 raw=s3.get_object(Bucket=bucket,Key=key)["Body"].read()
 sha=hashlib.sha256(raw).hexdigest()
 if head["Metadata"].get("quality")!="full" or head["Metadata"].get("sha256")!=sha:raise ValueError("SOURCE_GUARD")
 rows=[]
 with zipfile.ZipFile(io.BytesIO(raw)) as z:
  if z.testzip():raise ValueError("ZIP_CRC")
  names=[n for n in z.namelist() if n.endswith(".csv")]
  if len(names)!=1:raise ValueError("CSV_COUNT")
  with z.open(names[0]) as f:
   for x in csv.reader(io.TextIOWrapper(f,encoding="utf-8-sig")):
    if not x or not x[0].isdigit():continue
    t=int(x[0]);o,h,l,c,v,buy=map(float,[x[1],x[2],x[3],x[4],x[5],x[9]])
    if not(0<l<=min(o,c)<=max(o,c)<=h and 0<=buy<=v):raise ValueError("BAD_5M_BAR")
    if rows and t-rows[-1][0]!=P5:raise ValueError("GAP_5M")
    rows.append((t,o,h,l,c,v,buy))
 if len(rows)%3 or not rows:raise ValueError("INCOMPLETE_15M")
 bars=[]
 for j in range(0,len(rows),3):
  x=rows[j:j+3];t=x[0][0]
  if t%900000 or [r[0] for r in x]!=[t,t+P5,t+2*P5]:raise ValueError("MISALIGNED")
  v=sum(r[5] for r in x);buy=sum(r[6] for r in x)
  bars.append(dict(t=t,endMs=t+900000,o=x[0][1],h=max(r[2] for r in x),l=min(r[3] for r in x),c=x[-1][4],v=v,buy=buy,sell=v-buy))
 return bars,sha
def imb(b):
 v=b["buy"]+b["sell"]
 return dict(buyBase=b["buy"],sellBase=b["sell"],imbalance=round((b["buy"]-b["sell"])/v,6) if v else None)
def evaluate(bars,i):
 b=bars[i];f=detector_features(bars[:i+1],"15m")
 if f.get("sourceBarClosedAt")!=b["endMs"]:raise ValueError("FEATURE_TIME")
 flow=dict(current=imb(b),previous=imb(bars[i-1]),matchedStartMs=b["t"],matchedEndMs=b["endMs"],sameWindow=True)
 states,reason=direction_models(b,f,flow)
 if states is None:raise ValueError(reason)
 return states["LONG"]["status"],f["localStructure"]["sweptLowReclaimed"]
def regime(bars,i):
 # Past-only 24h trend; not based on future returns.
 if i<96:return "UNAVAILABLE"
 pct=100*(bars[i]["c"]/bars[i-96]["c"]-1)
 if pct>1:return "UP"
 if pct< -1:return "DOWN"
 return "SIDEWAYS"
def stats(values):
 if not values:return dict(n=0,meanPct=None,medianPct=None,positivePct=None)
 return dict(n=len(values),meanPct=round(statistics.mean(values),6),medianPct=round(statistics.median(values),6),positivePct=round(100*sum(v>0 for v in values)/len(values),4))
def forward(bars,i,n):return 100*(bars[i+n]["c"]/bars[i]["c"]-1)
def analyze(bars,seed):
 # Restrict signals and controls to indices with complete 24h future and past 24h regime.
 # Prevent month-edge censoring from differing between groups.
 eligible=list(range(96,len(bars)-96))
 by_regime={r:[] for r in ("UP","DOWN","SIDEWAYS")}
 events=[]
 for i in eligible:
  r=regime(bars,i);by_regime[r].append(i)
  status,sweep=evaluate(bars,i)
  if status=="EARLY_CANDIDATE_SHADOW":
   events.append(dict(i=i,regime=r,sweep=sweep))
 rng=random.Random(seed)
 controls=[]
 for e in events:
  pool=by_regime[e["regime"]]
  # Match asset, month, and past-only regime; exclude the exact candidate bar.
  choices=[i for i in pool if i!=e["i"]]
  if not choices:raise ValueError("NO_MATCHED_CONTROL")
  controls.append(dict(i=rng.choice(choices),regime=e["regime"],sweep=e["sweep"]))
 def evaluate_group(items):
  out={}
  for r in ("ALL","UP","DOWN","SIDEWAYS"):
   subset=[e for e in items if r=="ALL" or e["regime"]==r]
   out[r]={}
   for k,n in H.items():
    out[r][k]={group:stats([forward(bars,e["i"],n) for e in subset if group=="all" or (group=="sweep" and e["sweep"]) or (group=="nonSweep" and not e["sweep"])]) for group in ("all","sweep","nonSweep")}
  return out
 # Non-overlap sample: earliest event followed by at least 96 bars, matched controls for those events.
 selected=[];last=-999
 for j,e in enumerate(events):
  if e["i"]-last>=96:
   selected.append(j);last=e["i"]
 prefix_fail=sum(evaluate(bars[:e["i"]+1],e["i"])!=("EARLY_CANDIDATE_SHADOW",e["sweep"]) for e in events)
 if prefix_fail:raise ValueError("PREFIX_FAIL")
 return dict(eligibleBars=len(eligible),candidates=len(events),sweepCandidates=sum(e["sweep"] for e in events),nonOverlapCandidates=len(selected),prefixChecks=len(events),prefixFailures=0,signals=evaluate_group(events),matchedControls=evaluate_group(controls),nonOverlapSignals=evaluate_group([events[j] for j in selected]),nonOverlapControls=evaluate_group([controls[j] for j in selected]),controlMethod="fixed-seed random matching with replacement by asset, month and trailing 24h regime; excludes same index",regimeMethod="trailing 24h close-to-close: UP >1%, DOWN < -1%, SIDEWAYS otherwise")
s3=boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
out=[]
for sym in ("BTC","ETH"):
 for month in MONTHS:
  r=dict(symbol=sym,month=month,status="BLOCKED")
  try:
   bars,sha=read_month(s3,os.environ["R2_BUCKET"],sym,month)
   r.update(analyze(bars,seed=int(hashlib.sha256(f"{sym}/{month}/v65".encode()).hexdigest()[:12],16)),sourceSha256=sha,status="MATCHED_CONTROL_RESEARCH_PASS")
  except Exception as exc:r["error"]=str(exc)
  out.append(r)
os.makedirs("detector_v65_reports",exist_ok=True)
with open("detector_v65_reports/matched_controls.json","w") as f:
 json.dump(dict(version="6.5",researchOnly=True,tradesEmitted=0,originalLiveDetectorParity="NOT_ESTABLISHED",months=list(MONTHS),source="Binance USD-M futures historical 5m",limitations=["Control is random matched observation, not a causal counterfactual","Regime defined only from past 24h return; not comprehensive market state","Matched control may itself be a signal and may be selected repeatedly","One fixed draw per event; no uncertainty interval or significance claim","24h non-overlap is chronological greedy selection, not independent sampling","No actual execution, fees, slippage, trading P&L or out-of-sample validation","Each month analyzed independently with 24h warmup and future window; edge bars excluded"],results=out),f,indent=2)
print(json.dumps([{k:v for k,v in r.items() if k not in ("signals","matchedControls","nonOverlapSignals","nonOverlapControls")} for r in out],indent=2))
if any(r["status"]!="MATCHED_CONTROL_RESEARCH_PASS" for r in out):raise SystemExit(1)
