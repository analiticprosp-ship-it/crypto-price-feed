#!/usr/bin/env python3
"""v6.0 independent historical price-structure and prefix-invariance test."""
import csv,hashlib,io,json,os,sys,zipfile
from pathlib import Path
import boto3
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from detector_signal_engine import direction_models
P5=300000
def features_at(candles,i):
    assert i>=14
    current=candles[i];past=candles[i-14:i]
    assert all(b["endMs"]<=current["t"] for b in past)
    lo=min(b["l"] for b in past);hi=max(b["h"] for b in past)
    return {"status":"OHLCV_PROXY_ONLY","gapsInLast14":0,"localStructure":{"sweptLowReclaimed":current["l"]<lo and current["c"]>lo,"sweptHighRejected":current["h"]>hi and current["c"]<hi}}
def flow_of(b):
    total=b["buy"]+b["sell"]
    return {"buyBase":b["buy"],"sellBase":b["sell"],"imbalance":round((b["buy"]-b["sell"])/total,6) if total else None}
def evaluate(candles,i):
    bar=candles[i];prev=candles[i-1]
    flow={"current":flow_of(bar),"previous":flow_of(prev),"matchedStartMs":bar["t"],"matchedEndMs":bar["endMs"],"sameWindow":True}
    f=features_at(candles,i)
    states,reason=direction_models(bar,f,flow)
    if states is None:raise ValueError(reason)
    return {"eventEndMs":bar["endMs"],"long":states["LONG"]["status"],"price":states["LONG"]["families"]["PRICE_STRUCTURE"]["supportsHypothesis"],"flow":states["LONG"]["families"]["TAKER_VOLUME"]["supportsHypothesis"],"sweepLow":f["localStructure"]["sweptLowReclaimed"],"sweepHigh":f["localStructure"]["sweptHighRejected"],"context":states["LONG"]["context"]}
s3=boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
results=[]
for sym in ("BTC","ETH"):
 report={"symbol":sym,"status":"BLOCKED"}
 try:
  key=f"binance/usdm/5m/{sym}USDT/2026-09.zip"
  h=s3.head_object(Bucket=os.environ["R2_BUCKET"],Key=key)
  raw=s3.get_object(Bucket=os.environ["R2_BUCKET"],Key=key)["Body"].read()
  if hashlib.sha256(raw).hexdigest()!=h["Metadata"].get("sha256") or h["Metadata"].get("quality")!="full":raise ValueError("SOURCE_GUARD")
  with zipfile.ZipFile(io.BytesIO(raw)) as z:
   if z.testzip():raise ValueError("CRC")
   names=[n for n in z.namelist() if n.endswith(".csv")]
   if len(names)!=1:raise ValueError("CSV_COUNT")
   data=[]
   with z.open(names[0]) as f:
    for row in csv.reader(io.TextIOWrapper(f,encoding="utf-8-sig")):
     if not row or not row[0].isdigit():continue
     t=int(row[0]);o,hi,lo,c,v,buy=map(float,[row[1],row[2],row[3],row[4],row[5],row[9]])
     if not(0<lo<=min(o,c)<=max(o,c)<=hi and 0<=buy<=v):raise ValueError("BAD_BAR")
     if data and t-data[-1][0]!=P5:raise ValueError("GAP")
     data.append((t,o,hi,lo,c,v,buy))
  if len(data)%3:raise ValueError("PARTIAL")
  candles=[]
  for i in range(0,len(data),3):
   x=data[i:i+3];t=x[0][0]
   if t%900000 or [b[0] for b in x]!=[t,t+P5,t+2*P5]:raise ValueError("MISALIGNED")
   volume=sum(b[5] for b in x);buy=sum(b[6] for b in x)
   candles.append({"t":t,"endMs":t+900000,"o":x[0][1],"h":max(b[2] for b in x),"l":min(b[3] for b in x),"c":x[-1][4],"buy":buy,"sell":volume-buy})
  observations=[evaluate(candles,i) for i in range(14,len(candles))]
  # Independent prefix replay: each historical decision must remain identical
  # when all subsequent candles are removed.
  prefix_failures=[]
  for i in range(14,len(candles)):
   if evaluate(candles[:i+1],i)!=observations[i-14]:prefix_failures.append(i)
  if prefix_failures:raise ValueError("LOOKAHEAD_PREFIX_INVARIANCE_FAILURE")
  counts={k:sum(x["long"]==k for x in observations) for k in ("EARLY_CANDIDATE_SHADOW","WATCH","NO_EDGE","CONFLICT")}
  report.update(status="PREFIX_INVARIANCE_PASS",closed15m=len(candles),evaluated=len(observations),longStatusCounts=counts,sweepLowCount=sum(x["sweepLow"] for x in observations),sweepHighCount=sum(x["sweepHigh"] for x in observations),prefixComparisons=len(observations),prefixFailures=0,candidates=[x for x in observations if x["long"]=="EARLY_CANDIDATE_SHADOW"],sourceSha256=hashlib.sha256(raw).hexdigest())
 except Exception as ex:report["error"]=str(ex)
 results.append(report)
os.makedirs("detector_v60_reports",exist_ok=True)
with open("detector_v60_reports/structure_prefix_replay.json","w") as f:json.dump({"version":"6.0","researchOnly":True,"notTradeApproval":True,"originalDetectorParity":"NOT_ESTABLISHED","tradesEmitted":0,"sweepDefinition":"14 preceding CLOSED 15m bars; current wick breaks prior extreme, current close reclaims/rejects; research proxy only","limitations":["Sweep definition is a research proxy; not proven equal to original detectorFeatures implementation","Price and taker volume correlated; not independent evidence","Binance USD-M futures, not spot","Historical OI/funding unavailable","Prefix invariance tests only this implementation; no cross-engine parity"],"results":results},f,indent=2)
print(json.dumps([{k:v for k,v in r.items() if k!="candidates"} for r in results],indent=2))
if any(r["status"]!="PREFIX_INVARIANCE_PASS" for r in results):raise SystemExit(1)
