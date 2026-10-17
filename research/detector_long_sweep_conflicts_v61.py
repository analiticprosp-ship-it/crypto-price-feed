#!/usr/bin/env python3
"""v6.1: explain sweep vs non-sweep LONGs and conflict cases, read-only R2."""
import csv,hashlib,io,json,os,sys,zipfile
from collections import Counter
from pathlib import Path
import boto3
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from detector_signal_engine import direction_models
P5=300000
def imbalance(b):
 total=b["buy"]+b["sell"]
 return {"buyBase":b["buy"],"sellBase":b["sell"],"imbalance":round((b["buy"]-b["sell"])/total,6) if total else None}
def state(bars,i):
 b=bars[i];prev=bars[i-1];past=bars[i-14:i]
 assert len(past)==14 and all(x["endMs"]<=b["t"] for x in past)
 low=min(x["l"] for x in past);high=max(x["h"] for x in past)
 features={"status":"OHLCV_PROXY_ONLY","gapsInLast14":0,"localStructure":{"sweptLowReclaimed":b["l"]<low and b["c"]>low,"sweptHighRejected":b["h"]>high and b["c"]<high}}
 flow={"current":imbalance(b),"previous":imbalance(prev),"matchedStartMs":b["t"],"matchedEndMs":b["endMs"],"sameWindow":True}
 s,reason=direction_models(b,features,flow)
 if s is None:raise ValueError(reason)
 return {"eventEndMs":b["endMs"],"long":s["LONG"]["status"],"short":s["SHORT"]["status"],"sweepLow":features["localStructure"]["sweptLowReclaimed"],"sweepHigh":features["localStructure"]["sweptHighRejected"],"longPrice":s["LONG"]["families"]["PRICE_STRUCTURE"]["supportsHypothesis"],"longFlow":s["LONG"]["families"]["TAKER_VOLUME"]["supportsHypothesis"],"longContext":s["LONG"]["context"],"shortContext":s["SHORT"]["context"],"imbalance":flow["current"]["imbalance"],"previousImbalance":flow["previous"]["imbalance"]}
s3=boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
reports=[]
for sym in ("BTC","ETH"):
 result={"symbol":sym,"status":"BLOCKED"}
 try:
  key=f"binance/usdm/5m/{sym}USDT/2026-09.zip"
  h=s3.head_object(Bucket=os.environ["R2_BUCKET"],Key=key)
  raw=s3.get_object(Bucket=os.environ["R2_BUCKET"],Key=key)["Body"].read()
  if hashlib.sha256(raw).hexdigest()!=h["Metadata"].get("sha256") or h["Metadata"].get("quality")!="full":raise ValueError("SOURCE_GUARD")
  with zipfile.ZipFile(io.BytesIO(raw)) as z:
   if z.testzip():raise ValueError("ZIP_CRC")
   names=[n for n in z.namelist() if n.endswith(".csv")]
   if len(names)!=1:raise ValueError("CSV_COUNT")
   data=[]
   with z.open(names[0]) as f:
    for r in csv.reader(io.TextIOWrapper(f,encoding="utf-8-sig")):
     if not r or not r[0].isdigit():continue
     t=int(r[0]);o,hi,lo,c,v,buy=map(float,[r[1],r[2],r[3],r[4],r[5],r[9]])
     if not(0<lo<=min(o,c)<=max(o,c)<=hi and 0<=buy<=v):raise ValueError("BAD_BAR")
     if data and t-data[-1][0]!=P5:raise ValueError("GAP")
     data.append((t,o,hi,lo,c,v,buy))
  if len(data)%3:raise ValueError("INCOMPLETE_15M")
  bars=[]
  for j in range(0,len(data),3):
   x=data[j:j+3];t=x[0][0]
   if t%900000 or [b[0] for b in x]!=[t,t+P5,t+2*P5]:raise ValueError("MISALIGNED")
   vol=sum(b[5] for b in x);buy=sum(b[6] for b in x)
   bars.append({"t":t,"endMs":t+900000,"o":x[0][1],"h":max(b[2] for b in x),"l":min(b[3] for b in x),"c":x[-1][4],"buy":buy,"sell":vol-buy})
  obs=[state(bars,i) for i in range(14,len(bars))]
  candidate=[x for x in obs if x["long"]=="EARLY_CANDIDATE_SHADOW"]
  sweep=[x for x in candidate if x["sweepLow"]]
  no_sweep=[x for x in candidate if not x["sweepLow"]]
  conflicts=[x for x in obs if x["long"]=="CONFLICT" or x["short"]=="CONFLICT"]
  # Validate no future data on each candidate and each conflict using prefix replay.
  check_indices=[i for i,x in enumerate(obs,14) if x in candidate or x in conflicts]
  prefix_failures=[i for i in check_indices if state(bars[:i+1],i)!=obs[i-14]]
  if prefix_failures:raise ValueError("PREFIX_INVARIANCE_FAIL")
  result.update(status="RESEARCH_DIAGNOSTIC_PASS",sourceSha256=hashlib.sha256(raw).hexdigest(),evaluated=len(obs),longCandidates=len(candidate),longWithSweep=len(sweep),longWithoutSweep=len(no_sweep),conflicts=len(conflicts),prefixChecks=len(check_indices),prefixFailures=0,reasonCounts=dict(Counter(reason for x in candidate for reason in x["longContext"])),sweepCandidates=sweep,nonSweepCandidates=no_sweep,conflictEvents=conflicts)
 except Exception as ex:result["error"]=str(ex)
 reports.append(result)
os.makedirs("detector_v61_reports",exist_ok=True)
with open("detector_v61_reports/long_sweep_conflicts.json","w") as f:json.dump({"version":"6.1","researchOnly":True,"notTradeApproval":True,"tradesEmitted":0,"parity":"NOT_ESTABLISHED","featuresProvenance":"14-bar sweep research proxy; original detectorFeatures exact implementation NOT FOUND/NOT VERIFIED","limitations":["No measured signal quality, returns or hit rate","Original detectorFeatures implementation not proven equivalent","Conflict means both directional hypotheses compete, not an executable setup","Binance USD-M futures not spot; historical OI/funding missing","No trading authorization"],"results":reports},f,indent=2)
print(json.dumps([{k:v for k,v in r.items() if k not in ("sweepCandidates","nonSweepCandidates","conflictEvents")} for r in reports],indent=2))
if any(r["status"]!="RESEARCH_DIAGNOSTIC_PASS" for r in reports):raise SystemExit(1)
