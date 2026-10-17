#!/usr/bin/env python3
"""H1-H10 pilot: verified Binance aggTrades, spot vs perp 15m flow. Research only."""
import csv,hashlib,io,json,math,os,statistics,urllib.request,zipfile
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path
DATE="2026-10-01"
START=int(datetime(2026,10,1,tzinfo=timezone.utc).timestamp()*1000)
END=START+86400000
SOURCES={
 ("spot","BTCUSDT"):("43c878d893f8ffdb5404581e249ad4a69a3d1495b8256499405b5bbdcf30009d",799179),
 ("spot","ETHUSDT"):("196d019484b7c82db9d8dc62f60afbb26a758b1cee76f76a24fdc11daad79144",592281),
 ("spot","SOLUSDT"):("3d2a0ce177bbbd26376a3d1406abd2555823dacf0c6240f5e911f477e0b4176d",157510),
 ("perp","BTCUSDT"):("d2c73612e3c43d6481b39bbb25678bc7a58a841315f66e4c5996bb4a60532bf2",1235396),
 ("perp","ETHUSDT"):("acca9bf46c51f08fa63ca8f89a2e58bf3502aece850a4839bc6e7a6654d1ee59",1065814),
 ("perp","SOLUSDT"):("08dfd2a5645eefce70f3e29e3f39701d07d987b6236690ad7cf98a19a98f5e49",248215)}
def load(market,sym,sha,expected):
 segment="spot" if market=="spot" else "futures/um"
 url=f"https://data.binance.vision/data/{segment}/daily/aggTrades/{sym}/{sym}-aggTrades-{DATE}.zip"
 req=urllib.request.Request(url,headers={"User-Agent":"research-replay/1.0"})
 with urllib.request.urlopen(req,timeout=120) as response:raw=response.read()
 if hashlib.sha256(raw).hexdigest()!=sha:raise ValueError("ARCHIVE_SHA_MISMATCH "+market+sym)
 slots=defaultdict(lambda:[0,0.0,0.0,0.0,0.0])
 count=0
 with zipfile.ZipFile(io.BytesIO(raw)) as z:
  if z.testzip():raise ValueError("ZIP_CRC")
  names=[n for n in z.namelist() if n.endswith(".csv")]
  if len(names)!=1:raise ValueError("CSV_COUNT")
  with z.open(names[0]) as file:
   for row in csv.reader(io.TextIOWrapper(file,encoding="utf-8-sig")):
    if not row or not row[0].isdigit():continue
    # Binance aggTrades: aggregateId, price, quantity, firstId, lastId, timestamp, isBuyerMaker, isBestMatch
    if len(row)<7:raise ValueError("BAD_ROW_WIDTH")
    price=float(row[1]);qty=float(row[2]);ts=int(row[5])
    if ts>=10**15:ts//=1000
    if not(START<=ts<END and price>0 and qty>0):raise ValueError("INVALID_TRADE")
    maker=row[6].strip().lower()
    if maker not in ("true","false"):raise ValueError("INVALID_MAKER_FLAG")
    b=slots[(ts-START)//300000];b[0]+=1
    if maker=="false":b[1]+=qty;b[3]+=qty*price
    else:b[2]+=qty;b[4]+=qty*price
    count+=1
 if count!=expected or len(slots)!=288:raise ValueError("COUNT_OR_COVERAGE")
 return slots,{"market":market,"symbol":sym,"trades":count,"sha256":sha,"slots":len(slots)}
def agg15(slots):
 out=[]
 for k in range(96):
  vals=[slots[3*k+i] for i in range(3)]
  buy=sum(v[3] for v in vals);sell=sum(v[4] for v in vals)
  total=buy+sell
  out.append({"startMs":START+k*900000,"buyQuote":buy,"sellQuote":sell,"totalQuote":total,"deltaQuote":buy-sell,"imbalance":(buy-sell)/total if total else None,"trades":sum(v[0] for v in vals)})
 return out
def pearson(a,b):
 if len(a)<3:return None
 ma=statistics.mean(a);mb=statistics.mean(b)
 da=[v-ma for v in a];db=[v-mb for v in b]
 den=math.sqrt(sum(v*v for v in da)*sum(v*v for v in db))
 return sum(x*y for x,y in zip(da,db))/den if den else None
all_data={};sources=[]
for (market,sym),(sha,count) in SOURCES.items():
 slots,src=load(market,sym,sha,count)
 all_data[(market,sym)]=agg15(slots);sources.append(src)
results=[]
for sym in ("BTCUSDT","ETHUSDT","SOLUSDT"):
 spot=all_data[("spot",sym)];perp=all_data[("perp",sym)]
 if any(a["startMs"]!=b["startMs"] or a["imbalance"] is None or b["imbalance"] is None for a,b in zip(spot,perp)):raise ValueError("ALIGNMENT_OR_ZERO_VOLUME")
 disagreements=[];deltas=[];pairs=[]
 for s,p in zip(spot,perp):
  si=s["imbalance"];pi=p["imbalance"]
  divergent=si*pi<0
  if divergent:disagreements.append(s["startMs"])
  deltas.append(si-pi)
  pairs.append({"startMs":s["startMs"],"spotImbalance":round(si,8),"perpImbalance":round(pi,8),"difference":round(si-pi,8),"oppositeSign":divergent,"spotDeltaQuote":round(s["deltaQuote"],4),"perpDeltaQuote":round(p["deltaQuote"],4)})
 results.append({"symbol":sym,"status":"FLOW_ALIGNMENT_PASS","closed15m":96,"oppositeSignCount":len(disagreements),"oppositeSignPct":round(100*len(disagreements)/96,4),"meanImbalanceDifference":round(statistics.mean(deltas),8),"imbalanceCorrelation":round(pearson([x["imbalance"] for x in spot],[x["imbalance"] for x in perp]),6),"pairs":pairs,"oiStatus":"NOT_AVAILABLE","priceStructureStatus":"NOT_EVALUATED","signalValidation":"NOT_ESTABLISHED"})
out={"version":"H1-H10-FLOW-PILOT-1.0","date":DATE,"researchOnly":True,"tradesEmitted":0,"sourceArchiveVerification":"SHA256_MATCHES_USER_PILOT_MANIFEST","sourceMetadata":sources,"definitions":{"imbalance":"(aggressive_buy_quote - aggressive_sell_quote) / total_quote","oppositeSign":"spotImbalance * perpImbalance < 0","correlation":"Pearson of contemporaneous 15m imbalances"},"limits":["Only one day; no predictive performance claims","No synchronized OI or validated historical price structure","Spot and perpetual flow are correlated measurements, not independent proofs","No live detector modifications, trade signals or P&L"],"results":results}
Path("detector_h1_h10_flow_reports").mkdir(exist_ok=True)
Path("detector_h1_h10_flow_reports/flow_alignment.json").write_text(json.dumps(out,indent=2))
print(json.dumps([{k:v for k,v in x.items() if k!="pairs"} for x in results],indent=2))
