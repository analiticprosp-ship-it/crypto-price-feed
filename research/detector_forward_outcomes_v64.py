#!/usr/bin/env python3
"""v6.4: forward price outcomes of shadow LONG hypotheses, no trade simulation."""
import csv,hashlib,io,json,os,sys,zipfile,statistics
from pathlib import Path
import boto3
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from build_market_summary import detector_features
from detector_signal_engine import direction_models
P5=300000
HORIZONS={"15m":1,"1h":4,"4h":16,"24h":96}
def imbalance(b):
 vol=b["buy"]+b["sell"]
 return {"buyBase":b["buy"],"sellBase":b["sell"],"imbalance":round((b["buy"]-b["sell"])/vol,6) if vol else None}
def signal(bars,i):
 bar=bars[i]
 f=detector_features(bars[:i+1],"15m")
 if f.get("sourceBarClosedAt")!=bar["endMs"]:raise ValueError("FEATURE_TIMESTAMP_MISMATCH")
 flow={"current":imbalance(bar),"previous":imbalance(bars[i-1]),"matchedStartMs":bar["t"],"matchedEndMs":bar["endMs"],"sameWindow":True}
 states,reason=direction_models(bar,f,flow)
 if states is None:raise ValueError(reason)
 return states["LONG"]["status"],bool(f["localStructure"]["sweptLowReclaimed"])
def summary(rows):
 if not rows:return {"n":0,"meanPct":None,"medianPct":None,"positivePct":None,"minPct":None,"maxPct":None}
 return {"n":len(rows),"meanPct":round(statistics.mean(rows),6),"medianPct":round(statistics.median(rows),6),"positivePct":round(100*sum(x>0 for x in rows)/len(rows),4),"minPct":round(min(rows),6),"maxPct":round(max(rows),6)}
s3=boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
results=[]
for sym in ("BTC","ETH"):
 report={"symbol":sym,"status":"BLOCKED"}
 try:
  key=f"binance/usdm/5m/{sym}USDT/2026-09.zip"
  head=s3.head_object(Bucket=os.environ["R2_BUCKET"],Key=key)
  raw=s3.get_object(Bucket=os.environ["R2_BUCKET"],Key=key)["Body"].read()
  sha=hashlib.sha256(raw).hexdigest()
  if head["Metadata"].get("quality")!="full" or sha!=head["Metadata"].get("sha256"):raise ValueError("SOURCE_GUARD")
  data=[]
  with zipfile.ZipFile(io.BytesIO(raw)) as z:
   if z.testzip():raise ValueError("ZIP_CRC")
   names=[n for n in z.namelist() if n.endswith(".csv")]
   if len(names)!=1:raise ValueError("CSV_COUNT")
   with z.open(names[0]) as f:
    for row in csv.reader(io.TextIOWrapper(f,encoding="utf-8-sig")):
     if not row or not row[0].isdigit():continue
     t=int(row[0]);o,h,l,c,v,buy=map(float,[row[1],row[2],row[3],row[4],row[5],row[9]])
     if not(0<l<=min(o,c)<=max(o,c)<=h and 0<=buy<=v):raise ValueError("BAD_BAR")
     if data and t-data[-1][0]!=P5:raise ValueError("GAP")
     data.append((t,o,h,l,c,v,buy))
  if len(data)%3:raise ValueError("PARTIAL_15M")
  bars=[]
  for j in range(0,len(data),3):
   x=data[j:j+3];t=x[0][0]
   if t%900000 or [b[0] for b in x]!=[t,t+P5,t+2*P5]:raise ValueError("MISALIGNED")
   v=sum(b[5] for b in x);buy=sum(b[6] for b in x)
   bars.append({"t":t,"endMs":t+900000,"o":x[0][1],"h":max(b[2] for b in x),"l":min(b[3] for b in x),"c":x[-1][4],"v":v,"buy":buy,"sell":v-buy})
  events=[]
  for i in range(14,len(bars)):
   status,sweep=signal(bars,i)
   if status=="EARLY_CANDIDATE_SHADOW":
    events.append({"i":i,"endMs":bars[i]["endMs"],"referenceClose":bars[i]["c"],"sweepLow":sweep})
  # Deterministic greedy selection by chronological event order, per asset.
  # A selected event excludes candidates in the next 96 15m bars.
  independent=[];last=-100000
  for e in events:
   if e["i"]-last>=96:
    independent.append(e);last=e["i"]
  def outcomes(group):
   out={}
   for horizon,steps in HORIZONS.items():
    eligible=[e for e in group if e["i"]+steps<len(bars)]
    excluded=len(group)-len(eligible)
    buckets={"all":[],"sweep":[],"nonSweep":[]}
    for e in eligible:
     pct=100*(bars[e["i"]+steps]["c"]/e["referenceClose"]-1)
     buckets["all"].append(pct)
     buckets["sweep" if e["sweepLow"] else "nonSweep"].append(pct)
    out[horizon]={"censored":excluded,**{k:summary(v) for k,v in buckets.items()}}
   return out
  # Prefix invariance for every emitted candidate, no future candles in signal generation.
  prefix_fails=[e["endMs"] for e in events if signal(bars[:e["i"]+1],e["i"])!=("EARLY_CANDIDATE_SHADOW",e["sweepLow"])]
  if prefix_fails:raise ValueError("LOOKAHEAD_PREFIX_FAILURE")
  report.update(status="FORWARD_OUTCOME_RESEARCH_PASS",sourceSha256=sha,closed15m=len(bars),evaluated=len(bars)-14,allCandidates=len(events),allSweep=sum(e["sweepLow"] for e in events),nonOverlapping24hCandidates=len(independent),nonOverlappingSweep=sum(e["sweepLow"] for e in independent),prefixChecks=len(events),prefixFailures=0,selectionRule="greedy chronological, next candidate >=96 closed 15m bars after prior selected candidate",referencePrice="candidate 15m close (not execution price)",horizons=outcomes(events),nonOverlapping24h=outcomes(independent),events=[{"eventEndMs":e["endMs"],"sweepLow":e["sweepLow"],"outcomePct":{h:round(100*(bars[e["i"]+steps]["c"]/e["referenceClose"]-1),6) if e["i"]+steps<len(bars) else None for h,steps in HORIZONS.items()}} for e in events])
 except Exception as ex:report["error"]=str(ex)
 results.append(report)
os.makedirs("detector_v64_reports",exist_ok=True)
with open("detector_v64_reports/forward_price_outcomes.json","w") as f:json.dump({"version":"6.4","researchOnly":True,"notTradeApproval":True,"tradesEmitted":0,"originalLiveDetectorParity":"NOT_ESTABLISHED","source":"Binance USD-M perpetual futures 5m, September 2026","limitations":["Outcome measured as future close-to-signal-close percentage, not trade P&L","No fees, spread, slippage, fills or risk controls","24h non-overlap selection introduces chronological sampling bias; no independence guarantee","Events near month end censored; no next-month data","No statistical significance or out-of-sample validation","Taker volume is futures, not spot; historical OI/funding absent"],"results":results},f,indent=2)
print(json.dumps([{k:v for k,v in r.items() if k!="events"} for r in results],indent=2))
if any(r["status"]!="FORWARD_OUTCOME_RESEARCH_PASS" for r in results):raise SystemExit(1)
