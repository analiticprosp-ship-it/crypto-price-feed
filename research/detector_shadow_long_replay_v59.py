#!/usr/bin/env python3
"""v5.9: historical shadow LONG hypothesis replay; never trade signals."""
import csv,hashlib,io,json,os,sys,zipfile
from pathlib import Path
import boto3
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from detector_signal_engine import direction_models
P5=300000
s3=boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
results=[]
for sym in ("BTC","ETH"):
 key=f"binance/usdm/5m/{sym}USDT/2026-09.zip"
 report={"symbol":sym,"month":"2026-09","status":"BLOCKED","researchOnly":True,"notTradeApproval":True}
 try:
  h=s3.head_object(Bucket=os.environ["R2_BUCKET"],Key=key)
  raw=s3.get_object(Bucket=os.environ["R2_BUCKET"],Key=key)["Body"].read()
  if hashlib.sha256(raw).hexdigest()!=h["Metadata"].get("sha256"):raise ValueError("SHA256_MISMATCH")
  if h["Metadata"].get("quality")!="full":raise ValueError("NOT_FULL")
  with zipfile.ZipFile(io.BytesIO(raw)) as z:
   if z.testzip():raise ValueError("CRC")
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
  if len(data)%3:raise ValueError("PARTIAL_15M")
  candles=[]
  for i in range(0,len(data),3):
   x=data[i:i+3];t=x[0][0]
   if t%900000 or [b[0] for b in x]!=[t,t+P5,t+2*P5]:raise ValueError("MISALIGNED")
   vol=sum(b[5] for b in x);buy=sum(b[6] for b in x)
   candles.append({"t":t,"endMs":t+900000,"o":x[0][1],"h":max(b[2] for b in x),"l":min(b[3] for b in x),"c":x[-1][4],"buy":buy,"sell":vol-buy})
  candidates=[];counts={"EARLY_CANDIDATE_SHADOW":0,"WATCH":0,"NO_EDGE":0,"CONFLICT":0}
  for i in range(14,len(candles)):
   bar=candles[i];prev=candles[i-1]
   def aggregate(b):
    total=b["buy"]+b["sell"]
    return {"buyBase":b["buy"],"sellBase":b["sell"],"imbalance":round((b["buy"]-b["sell"])/total,6) if total else None}
   flow={"current":aggregate(bar),"previous":aggregate(prev),"matchedStartMs":bar["t"],"matchedEndMs":bar["endMs"],"sameWindow":True}
   features={"status":"OHLCV_PROXY_ONLY","gapsInLast14":0,"localStructure":{"sweptLowReclaimed":False,"sweptHighRejected":False}}
   states,reason=direction_models(bar,features,flow)
   if states is None:raise ValueError(reason)
   status=states["LONG"]["status"];counts[status]+=1
   if status=="EARLY_CANDIDATE_SHADOW":
    candidates.append({"eventEndMs":bar["endMs"],"status":"EARLY_CANDIDATE_SHADOW","close":bar["c"],"priceAndFlowFamilies":2,"originalDetectorParity":"NOT_ESTABLISHED"})
  report.update(status="SHADOW_HYPOTHESES_ONLY",closed15m=len(candles),warmup15m=14,evaluated15m=sum(counts.values()),longStatusCounts=counts,longCandidates=candidates,sourceSha256=hashlib.sha256(raw).hexdigest(),sweepDetection="DISABLED_NOT_REPRODUCED",oiFunding="UNAVAILABLE",spotParity="NOT_ESTABLISHED",lookahead="NO_FORWARD_BARS_READ_IN_DECISION_LOOP")
 except Exception as ex:report["error"]=str(ex)
 results.append(report)
os.makedirs("detector_v59_reports",exist_ok=True)
with open("detector_v59_reports/shadow_long_replay.json","w") as f:json.dump({"version":"5.9","researchOnly":True,"notTradeApproval":True,"notOriginalDetectorSignals":True,"tradesEmitted":0,"limitations":["Only existing direction_models qualitative LONG heuristic","Sweep detection deliberately disabled; price feature is proxy, not parity","Futures 5m taker volume differs from original spot signal","Historical OI and funding unavailable","No return metrics, win rate, orders or execution levels"],"results":results},f,indent=2)
print(json.dumps([{k:v for k,v in r.items() if k!="longCandidates"} for r in results],indent=2))
if any(r["status"]=="BLOCKED" for r in results):raise SystemExit(1)
