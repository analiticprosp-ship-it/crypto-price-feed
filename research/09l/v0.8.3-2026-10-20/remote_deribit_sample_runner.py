#!/usr/bin/env python3
"""09L Deribit 2026-10-01 frozen free-sample runner. Shadow only, no raw vendor redistribution."""
import csv, gzip, io, urllib.request, hashlib, json, datetime, math
from pathlib import Path
from collections import defaultdict
DATE="2026-10-01"; SYMBOL="BTC-PERPETUAL"; BASE="https://datasets.tardis.dev/v1"
TYPES=[("liquidations","PERPETUALS"),("trades",SYMBOL),("quotes",SYMBOL),("book_snapshot_5",SYMBOL)]
CAP=175*1024*1024
t0=int(datetime.datetime(2026,10,1,tzinfo=datetime.timezone.utc).timestamp()//60)
data=defaultdict(dict); provenance=[];counts=defaultdict(int)
def F(s):
    try:return float(s) if s is not None and s!="" else None
    except (ValueError,TypeError):return None
def at(m,k,default=None):return data.get(m,{}).get(k,default)
class Tap:
    def __init__(self,stream):self.stream=stream;self.n=0;self.hash=hashlib.sha256()
    def read(self,n=-1):
        b=self.stream.read(n);self.n+=len(b);self.hash.update(b)
        if self.n>CAP:raise RuntimeError("COMPRESSED_SIZE_CAP_EXCEEDED")
        return b
for kind,sym in TYPES:
    url=f"{BASE}/deribit/{kind}/2026/10/01/{sym}.csv.gz"
    item={"kind":kind,"symbol":sym,"url":url}
    try:
        rq=urllib.request.Request(url,headers={"User-Agent":"09L-research-only-v083"})
        response=urllib.request.urlopen(rq,timeout=70)
        if response.status!=200:raise RuntimeError("HTTP_"+str(response.status))
        tap=Tap(response)
        rd=csv.DictReader(io.TextIOWrapper(gzip.GzipFile(fileobj=tap),encoding="utf-8",newline=""))
        cols=rd.fieldnames or []
        required={"symbol","local_timestamp"}
        if kind in ("trades","liquidations"):required|={"amount","side","price"}
        elif kind=="quotes":required|={"bid_price","ask_price","bid_amount","ask_amount"}
        else:required|={"asks[0].price","asks[0].amount","bids[0].price","bids[0].amount"}
        if not required.issubset(set(cols)):raise ValueError("MISSING_COLUMNS_"+repr(sorted(required-set(cols))))
        for row in rd:
            counts[kind+"_raw"]+=1
            if row["symbol"]!=SYMBOL:continue
            try:m=int(row["local_timestamp"])//60000000
            except:counts[kind+"_invalid_time"]+=1;continue
            if m<t0 or m>=t0+1440:counts[kind+"_out_of_date"]+=1;continue
            counts[kind+"_btc"]+=1
            x=data[m]
            if kind=="trades":
                p=F(row["price"]);q=F(row["amount"])
                if p is None or p<=0 or q is None or q<0:continue
                x["price"]=p;x["trades"]=x.get("trades",0)+1
                side=row["side"].lower()
                if side in ("buy","sell"):x["taker_"+side]=x.get("taker_"+side,0)+q
            elif kind=="liquidations":
                a=F(row["amount"]);side=row["side"].lower()
                if a is None or a<0:continue
                x["liq_events"]=x.get("liq_events",0)+1
                if side in ("buy","sell"):x["liq_"+side]=x.get("liq_"+side,0)+a
            elif kind=="quotes":
                a=F(row["ask_price"]);b=F(row["bid_price"])
                if a and b and a>b:
                    x["spread_bps"]=10000*(a-b)/((a+b)/2);x["quote_observations"]=x.get("quote_observations",0)+1
                    x["best_ask_amt"]=F(row["ask_amount"]);x["best_bid_amt"]=F(row["bid_amount"])
            else:
                a=F(row["asks[0].price"]);b=F(row["bids[0].price"])
                if a and b and a>b:
                    x["top5_spread_bps"]=10000*(a-b)/((a+b)/2)
                    for side in ("asks","bids"):
                        levels=[F(row.get(f"{side}[{i}].amount")) for i in range(5)]
                        x["top5_"+side+"_raw"]=sum(v for v in levels if v is not None)
                    x["top5_updates"]=x.get("top5_updates",0)+1
        item.update(status="OK",compressed_sha256=tap.hash.hexdigest(),compressed_bytes=tap.n,raw_rows=counts[kind+"_raw"],btc_rows=counts[kind+"_btc"])
    except Exception as e:item.update(status="SOURCE_UNAVAILABLE_OR_ERROR",error=type(e).__name__+": "+str(e)[:300])
    provenance.append(item)
    print(kind,item["status"],counts[kind+"_btc"],flush=True)
def price(m):
    for k in (m,m-1,m-2):
        if at(k,"price") is not None:return at(k,"price")
    return None
ranked=sorted(((at(m,"liq_"+side,0),m,side) for m in range(t0,t0+1440) for side in ("buy","sell") if at(m,"liq_"+side,0)>0),reverse=True)
events=[]
for size,m,side in ranked:
    if sum(e["side"]==side for e in events)>=2 or any(abs(m-e["m"])<30 for e in events):continue
    events.append({"m":m,"side":side,"size":size})
controls=sorted((m for m in range(t0,t0+1440) if at(m,"trades",0)>0 and at(m,"liq_events",0)==0),key=lambda m:-at(m,"trades",0))
for m in controls:
    if sum(e["side"]=="control" for e in events)>=4:break
    if any(abs(m-e["m"])<30 for e in events):continue
    events.append({"m":m,"side":"control","size":None})
cases=[]
for e in sorted(events,key=lambda a:a["m"]):
    m,side=e["m"],e["side"];p0=price(m);p5=price(m+5);p15=price(m+15)
    r5=round((p5/p0-1)*1e4,4) if p0 and p5 else None
    r15=round((p15/p0-1)*1e4,4) if p0 and p15 else None
    after=sum(at(j,"liq_"+side,0) for j in range(m+1,m+6)) if side!="control" else None
    direct=1 if side=="buy" else -1 if side=="sell" else 0
    label=("CONTROL_NO_OBSERVED_LIQ_MESSAGE" if side=="control" else
           "UNCLASSIFIABLE_PRICE_MISSING" if r5 is None else
           "OBSERVED_LIQ_WITHOUT_5M_EXTENSION" if direct*r5<20 else
           "OBSERVED_LIQ_AND_DIRECTIONAL_EXTENSION" if after>0 else
           "OBSERVED_LIQ_WITH_5M_EXTENSION_NO_FOLLOWON_LIQ")
    cases.append({"minute_utc":datetime.datetime.fromtimestamp(m*60,datetime.timezone.utc).isoformat(),"side":side,
      "liq_amount_raw":e["size"],"taker_signed_amount_raw":at(m,"taker_buy",0)-at(m,"taker_sell",0),
      "observed_trade_count":at(m,"trades",0),"liq_events_count":at(m,"liq_events",0),"price":p0,
      "price_5m":p5,"return_5m_bps":r5,"return_15m_bps":r15,
      "observed_same_side_liq_next5_raw":after,"top5_spread_bps":at(m,"top5_spread_bps"),
      "top5_asks_amount_raw":at(m,"top5_asks_raw"),"top5_bids_amount_raw":at(m,"top5_bids_raw"),
      "mechanics_label":label,"cascade_verified":False,"cluster_touch":"NOT_OBSERVED","dealer_gamma":"UNKNOWN"})
gates={"full_sources_ok":all(x["status"]=="OK" for x in provenance),
       "liquidations_BTC_rows":counts["liquidations_btc"],"trades_BTC_rows":counts["trades_btc"],
       "quotes_BTC_rows":counts["quotes_btc"],"book5_BTC_rows":counts["book_snapshot_5_btc"],
       "historical_cluster_pit":False,"dealer_signed_gamma":False}
status="SAMPLE_MECHANICS_ONLY" if gates["full_sources_ok"] and all(counts[k+"_btc"]>0 for k,_ in TYPES) else "DATA_INCOMPLETE"
obj={"study":"09L v0.8.3","date":DATE,"status":status,"type":"RETROSPECTIVE_EXPLORATORY",
     "provenance":provenance,"counts":dict(counts),"gates":gates,"cases":cases,
     "disclaimers":["No PIT heatmap or verified cluster first touch","No true P(cascade|touch)",
     "Liquidation volume is observed source events; feed is not guaranteed exhaustive",
     "Source amounts kept raw, contract units not inferred","Top5 changes do not establish OFI or cancellation/replenishment",
     "No dealer gamma signed inventory","Synthetic code test does not establish market evidence"],
     "canonical_trading_files_touched":False}
p=Path("research/09l/v0.8.3-2026-10-20/derived");p.mkdir(parents=True,exist_ok=True)
(p/"2026-10-01_tardis_sample_audit.json").write_text(json.dumps(obj,ensure_ascii=False,indent=2)+"\n")
print(json.dumps({"status":status,"events":len(cases),"n_liquidations":counts["liquidations_btc"]}),flush=True)
