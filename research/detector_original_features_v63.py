#!/usr/bin/env python3
"""v6.3: historical replay with imported original detector_features; research only."""
import csv,hashlib,io,json,os,sys,zipfile
from collections import Counter
from pathlib import Path
import boto3
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from build_market_summary import detector_features
from detector_signal_engine import direction_models
P5=300000
def imb(b):
 v=b["buy"]+b["sell"]
 return {"buyBase":b["buy"],"sellBase":b["sell"],"imbalance":round((b["buy"]-b["sell"])/v,6) if v else None}
def evaluate(bars,i,mode):
 bar=bars[i];prev=bars[i-1]
 if mode=="original":
  f=detector_features(bars[:i+1],"15m")
  if f.get("sourceBarClosedAt")!=bar["endMs"]:raise ValueError("FEATURE_TIMESTAMP_MISMATCH")
 else:
  prior=bars[i-14:i]
  low=min(x["l"] for x in prior);high=max(x["h"] for x in prior)
  f={"status":"OHLCV_PROXY_ONLY","gapsInLast14":0,"localStructure":{"sweptLowReclaimed":bar["l"]<low and bar["c"]>low,"sweptHighRejected":bar["h"]>high and bar["c"]<high}}
 flow={"current":imb(bar),"previous":imb(prev),"matchedStartMs":bar["t"],"matchedEndMs":bar["endMs"],"sameWindow":True}
 states,reason=direction_models(bar,f,flow)
 if states is None:raise ValueError(reason)
 return {"endMs":bar["endMs"],"long":states["LONG"]["status"],"short":states["SHORT"]["status"],"sweepLow":f["localStructure"]["sweptLowReclaimed"],"sweepHigh":f["localStructure"]["sweptHighRejected"],"context":states["LONG"]["context"]}
s3=boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
results=[]
for sym in ("BTC","ETH"):
 report={"symbol":sym,"status":"BLOCKED"}
 try:
  key=f"binance/usdm/5m/{sym}USDT/2026-09.zip"
  head=s3.head_object(Bucket=os.environ["R2_BUCKET"],Key=key)
  raw=s3.get_object(Bucket=os.environ["R2_BUCKET"],Key=key)["Body"].read()
  if head["Metadata"].get("quality")!="full" or hashlib.sha256(raw).hexdigest()!=head["Metadata"].get("sha256"):raise ValueError("SOURCE_GUARD")
  data=[]
  with zipfile.ZipFile(io.BytesIO(raw)) as z:
   if z.testzip():raise ValueError("CRC")
   names=[n for n in z.namelist() if n.endswith(".csv")]
   if len(names)!=1:raise ValueError("CSV_COUNT")
   with z.open(names[0]) as f:
    for row in csv.reader(io.TextIOWrapper(f,encoding="utf-8-sig")):
     if not row or not row[0].isdigit():continue
     t=int(row[0]);o,h,l,c,v,buy=map(float,[row[1],row[2],row[3],row[4],row[5],row[9]])
     if not(0<l<=min(o,c)<=max(o,c)<=h and 0<=buy<=v):raise ValueError("BAD_BAR")
     if data and t-data[-1][0]!=P5:raise ValueError("GAP")
     data.append((t,o,h,l,c,v,buy))
  if len(data)%3:raise ValueError("INCOMPLETE_15M")
  bars=[]
  for j in range(0,len(data),3):
   x=data[j:j+3];t=x[0][0]
   if t%900000 or [b[0] for b in x]!=[t,t+P5,t+2*P5]:raise ValueError("ALIGNMENT")
   vol=sum(b[5] for b in x);buy=sum(b[6] for b in x)
   bars.append({"t":t,"endMs":t+900000,"o":x[0][1],"h":max(b[2] for b in x),"l":min(b[3] for b in x),"c":x[-1][4],"v":vol,"buy":buy,"sell":vol-buy})
  # Both modes share identical 14-bar warmup and identical flow inputs.
  original=[evaluate(bars,i,"original") for i in range(14,len(bars))]
  proxy=[evaluate(bars,i,"proxy") for i in range(14,len(bars))]
  changes=[{"endMs":a["endMs"],"original":a,"proxy":b} for a,b in zip(original,proxy) if a!=b]
  orig_candidates={x["endMs"] for x in original if x["long"]=="EARLY_CANDIDATE_SHADOW"}
  proxy_candidates={x["endMs"] for x in proxy if x["long"]=="EARLY_CANDIDATE_SHADOW"}
  orig_conflicts={x["endMs"] for x in original if x["long"]=="CONFLICT"}
  proxy_conflicts={x["endMs"] for x in proxy if x["long"]=="CONFLICT"}
  # Recompute every changed decision from the history prefix.
  prefix_fail=[x["endMs"] for x in changes if evaluate(bars[:next(i for i,b in enumerate(bars) if b["endMs"]==x["endMs"])+1],next(i for i,b in enumerate(bars) if b["endMs"]==x["endMs"]),"original")!=x["original"]]
  if prefix_fail:raise ValueError("PREFIX_INVARIANCE_FAIL")
  report.update(status="ORIGINAL_FEATURE_FUNCTION_REPLAY_PASS",sourceSha256=hashlib.sha256(raw).hexdigest(),evaluated=len(original),originalLongCandidates=len(orig_candidates),proxyLongCandidates=len(proxy_candidates),retainedLongCandidates=len(orig_candidates&proxy_candidates),originalOnlyLong=len(orig_candidates-proxy_candidates),proxyOnlyLong=len(proxy_candidates-orig_candidates),originalConflicts=len(orig_conflicts),proxyConflicts=len(proxy_conflicts),retainedConflicts=len(orig_conflicts&proxy_conflicts),changedEvents=len(changes),prefixChecks=len(changes),prefixFailures=0,originalSweepLow=sum(x["sweepLow"] for x in original),proxySweepLow=sum(x["sweepLow"] for x in proxy),changes=changes)
 except Exception as ex:report["error"]=str(ex)
 results.append(report)
os.makedirs("detector_v63_reports",exist_ok=True)
with open("detector_v63_reports/original_feature_parity.json","w") as f:json.dump({"version":"6.3","researchOnly":True,"notTradeApproval":True,"tradesEmitted":0,"featureFunction":"scripts/build_market_summary.py::detector_features (direct import)","featureFunctionParity":"DIRECT_IMPORT_FOR_REPLAY","originalLiveDetectorParity":"NOT_ESTABLISHED","limitations":["Historical Binance USD-M futures OHLCV, not spot","Original feature function imported, but live input venue/time/freshness parity not established","Historical OI/funding unavailable","No outcome, trade, or P&L claims"],"results":results},f,indent=2)
print(json.dumps([{k:v for k,v in r.items() if k!="changes"} for r in results],indent=2))
if any(r["status"]!="ORIGINAL_FEATURE_FUNCTION_REPLAY_PASS" for r in results):raise SystemExit(1)
