#!/usr/bin/env python3
"""Research-only BTC/ETH historical 5m->15m replay readiness; NOT signal parity."""
import argparse,csv,hashlib,io,json,os,zipfile
from collections import Counter
import boto3
p=argparse.ArgumentParser()
p.add_argument("--month",default="2026-09")
a=p.parse_args()
assert a.month in [f"{y}-{m:02d}" for y in range(2020,2027) for m in range(1,13) if (y,m)<=(2026,9)]
s3=boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
bucket=os.environ["R2_BUCKET"]
results=[]
for symbol in ("BTC","ETH"):
 key=f"binance/usdm/5m/{symbol}USDT/{a.month}.zip"
 item={"symbol":symbol,"month":a.month,"r2_key":key,"researchOnly":True,"notTradeApproval":True,"signalParity":"NOT_ESTABLISHED"}
 try:
  h=s3.head_object(Bucket=bucket,Key=key);metadata=h.get("Metadata",{})
  raw=s3.get_object(Bucket=bucket,Key=key)["Body"].read()
  sha=hashlib.sha256(raw).hexdigest()
  if sha!=metadata.get("sha256"):raise ValueError("SHA256_MISMATCH")
  if metadata.get("quality")!="full":raise ValueError("MONTH_NOT_FULL")
  with zipfile.ZipFile(io.BytesIO(raw)) as z:
   if z.testzip():raise ValueError("ZIP_CRC")
   names=[n for n in z.namelist() if n.endswith(".csv")]
   if len(names)!=1:raise ValueError("CSV_COUNT")
   bars=[]
   with z.open(names[0]) as f:
    for r in csv.reader(io.TextIOWrapper(f,encoding="utf-8-sig")):
     if not r or not r[0].isdigit():continue
     t=int(r[0]);o,hi,lo,c,v=map(float,r[1:6]);buy=float(r[9])
     if not(0<lo<=min(o,c)<=max(o,c)<=hi and 0<=buy<=v):raise ValueError("INVALID_SOURCE_BAR")
     if bars and t-bars[-1][0]!=300000:raise ValueError("SOURCE_GAP")
     bars.append((t,o,hi,lo,c,v,buy))
  if len(bars)%3:raise ValueError("INCOMPLETE_15M")
  candles=[]
  for i in range(0,len(bars),3):
   a3=bars[i:i+3];t=a3[0][0]
   if t%900000 or [b[0] for b in a3]!=[t,t+300000,t+600000]:raise ValueError("MISALIGNED_15M")
   total=sum(b[5] for b in a3);buy=sum(b[6] for b in a3)
   candles.append({"startMs":t,"endMs":t+900000,"o":a3[0][1],"h":max(b[2] for b in a3),"l":min(b[3] for b in a3),"c":a3[-1][4],"volumeBase":total,"takerBuyBase":buy,"takerSellBase":total-buy})
  item.update(status="REPLAY_INPUT_READY_NOT_SIGNAL_VALIDATED",source5m=len(bars),closed15m=len(candles),sha256=sha,first15m=candles[0],last15m=candles[-1],guards=["No future bars","Exact 3x5m aggregation","OI/funding unavailable","Original spot LONG signal parity unproven","Futures klines are not spot market data"])
 except Exception as e:item.update(status="BLOCKED",error=str(e)[:200])
 results.append(item)
os.makedirs("detector_v58_reports",exist_ok=True)
with open("detector_v58_reports/replay_readiness.json","w") as f:json.dump({"version":"5.8","results":results,"signals_emitted":0,"trades_emitted":0,"note":"This is a data readiness smoke test, not an original detector replay or backtest."},f,indent=2)
print(json.dumps(results,indent=2))
if any(r["status"]=="BLOCKED" for r in results):raise SystemExit(1)
