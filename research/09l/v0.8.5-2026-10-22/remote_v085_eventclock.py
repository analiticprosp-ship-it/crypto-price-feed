#!/usr/bin/env python3
"""09L v0.8.5: preregistered event-clock replay of 2026-10-01 Tardis Bybit free datasets.
Research-only. No PIT liquidation clusters, no dealer sign, no trading authority.
"""
import bisect,csv,datetime as dt,gzip,hashlib,io,json,os,urllib.request
from pathlib import Path
D="2026-10-01"; BASE="https://datasets.tardis.dev/v1/bybit"
DEST=Path("research/09l/v0.8.5-2026-10-22/derived/eventclock_2026-10-01.json")
TYPES=[("liquidations","PERPETUALS"),("trades","BTCUSDT"),("quotes","BTCUSDT"),("book_snapshot_5","BTCUSDT")]
EXPECTED={"liquidations":"e236aca7b8e0ba0b32e39779bcf243f08747785c14e6d18539c551f3b4f040b5","trades":"abf7e614b2d6b45dbfa85bdc79432228fa034cbbdba9b7a470078d14abf3c7b6","quotes":"021c7cd3437b0ba14331a387de00dea7d622098964e0a268e865896584f8781a","book_snapshot_5":"b143c170e6a36c1f6cdbe7727b50c36fa3495eaa2d2b9612737e9a6c1d88f8d1"}
FROZEN=[("07:24","sell",-3.9949),("08:32","sell",23.5641),("13:49","control",31.0037),("14:19","control",7.2551),("15:10","control",16.3971),("15:49","control",-16.8132),("17:28","buy",-6.1382),("18:38","buy",-38.6436)]
def minute_us(h):
 return int(dt.datetime.fromisoformat(D+"T"+h+":00+00:00").timestamp()*1_000_000)
def num(s):
 try:return float(s) if s not in ("",None) else None
 except (ValueError,TypeError):return None
CASES=[{"minute":h,"side":side,"prior_minute_close_return_5m_bps":ret,"start":minute_us(h),"t0":minute_us(h)+30_000_000 if side=="control" else None,"data":{k:[] for k,_ in TYPES}} for h,side,ret in FROZEN]
BEG=[c["start"]-30_000_000 for c in CASES]
END=[c["start"]+360_000_000 for c in CASES]
assert all(END[i]<BEG[i+1] for i in range(len(CASES)-1))
def ci(t):
 i=bisect.bisect_right(BEG,t)-1
 return i if i>=0 and t<END[i] else None
class HashTap:
 def __init__(self,s):self.s=s;self.h=hashlib.sha256();self.n=0
 def read(self,n=-1):
  b=self.s.read(n);self.n+=len(b)
  if self.n>190_000_000:raise RuntimeError("COMPRESSED_CAP")
  self.h.update(b);return b
PROV=[]
for kind,symbol in TYPES:
 url=f"{BASE}/{kind}/2026/10/01/{symbol}.csv.gz"
 p={"kind":kind,"url":url,"status":"INCOMPLETE","raw_rows":0,"btc_rows":0,"case_rows":0}
 try:
  req=urllib.request.Request(url,headers={"User-Agent":"09L-Research-Only-v085"})
  with urllib.request.urlopen(req,timeout=150) as resp:
   if resp.status!=200:raise RuntimeError("HTTP_"+str(resp.status))
   hs=HashTap(resp)
   reader=csv.DictReader(io.TextIOWrapper(gzip.GzipFile(fileobj=hs),encoding="utf-8",newline=""))
   cols=set(reader.fieldnames or [])
   need={"symbol","local_timestamp"}
   if kind in ("liquidations","trades"):need|={"price","amount","side"}
   if kind=="quotes":need|={"bid_price","ask_price","bid_amount","ask_amount"}
   if kind=="book_snapshot_5":need|={"bids[0].price","asks[0].price","bids[0].amount","asks[0].amount"}
   if not need.issubset(cols):raise RuntimeError("MISSING_SCHEMA_"+str(sorted(need-cols)))
   for r in reader:
    p["raw_rows"]+=1
    if r["symbol"]!="BTCUSDT":continue
    p["btc_rows"]+=1
    try:t=int(r["local_timestamp"])
    except (TypeError,ValueError):continue
    idx=ci(t)
    if idx is None:continue
    case=CASES[idx];side=(r.get("side") or "").lower()
    if kind=="liquidations":
     if case["side"] in ("buy","sell") and case["start"]<=t<case["start"]+60_000_000 and side==case["side"]:
      case["t0"]=min(case["t0"] or t,t)
     record=(t,side,num(r["amount"]))
    elif kind=="trades":record=(t,side,num(r["amount"]),num(r["price"]))
    elif kind=="quotes":record=(t,num(r["bid_price"]),num(r["ask_price"]),num(r["bid_amount"]),num(r["ask_amount"]))
    else:
     bd=[num(r.get(f"bids[{i}].amount")) for i in range(5)]
     ad=[num(r.get(f"asks[{i}].amount")) for i in range(5)]
     record=(t,num(r["bids[0].price"]),num(r["asks[0].price"]),sum(v for v in bd if v is not None),sum(v for v in ad if v is not None))
    case["data"][kind].append(record);p["case_rows"]+=1
   p["compressed_sha256"]=hs.h.hexdigest();p["compressed_bytes"]=hs.n
  p["sha_match_v083"]=p["compressed_sha256"]==EXPECTED[kind]
  p["status"]="OK" if p["sha_match_v083"] else "SOURCE_SHA_DRIFT"
 except Exception as e:
  p["status"]="SOURCE_ERROR";p["error"]=type(e).__name__+":"+str(e)[:250]
 PROV.append(p);print(kind,p["status"],p["raw_rows"],p["case_rows"],flush=True)
def asof(records,t,age=15_000_000,price_ix=1):
 valid=[r for r in records if t-age<=r[0]<=t and r[price_ix] is not None and r[price_ix]>0]
 return valid[-1] if valid else None
def totals(records,start,end):
 a=[r for r in records if start<=r[0]<end and r[2] is not None and r[2]>=0]
 b=sum(r[2] for r in a if r[1]=="buy");s=sum(r[2] for r in a if r[1]=="sell")
 return {"message_count":len(a),"buy_amount_raw":round(b,6),"sell_amount_raw":round(s,6),"buy_minus_sell_raw":round(b-s,6)}
def level(records,t):
 r=asof(records,t,15_000_000,1)
 if r is None or r[2] is None or r[2]<=r[1]:return None
 return {"spread_bps":round(10000*(r[2]-r[1])/((r[2]+r[1])/2),5),"bid":r[1],"ask":r[2],"bid_qty_raw":r[3],"ask_qty_raw":r[4],"staleness_ms":round((t-r[0])/1000,3)}
RESULT=[]
for c in CASES:
 t=c["t0"];d=c["data"];side=c["side"]
 x={"minute_utc":D+"T"+c["minute"]+":00Z","side":side,"prior_minute_close_return_5m_bps":c["prior_minute_close_return_5m_bps"],"clock":"first_observed_same_side_liquidation_local_timestamp" if side!="control" else "minute_plus_30s_control","t0_utc":dt.datetime.fromtimestamp(t/1e6,dt.timezone.utc).isoformat() if t else None,"cluster_first_hit_verified":False,"dealer_signed_gamma":"UNKNOWN","case_source_rows":{k:len(v) for k,v in d.items()}}
 if t is None:x["status"]="MISSING_OBSERVED_SAME_SIDE_T0";RESULT.append(x);continue
 for k in d:d[k].sort(key=lambda y:y[0])
 for nam,a,b in [("pre30",t-30_000_000,t),("post30",t,t+30_000_000),("post60",t,t+60_000_000),("post300",t,t+300_000_000)]:
  x["trades_"+nam]=totals(d["trades"],a,b);x["liq_"+nam]=totals(d["liquidations"],a,b)
 start=asof(d["trades"],t,30_000_000,3);x["p0"]=start[3] if start else None
 for sec in [30,60,300]:
  rr=asof(d["trades"],t+sec*1_000_000,15_000_000,3)
  x[f"p{sec}"]=rr[3] if rr else None
  x[f"return_{sec}s_bps"]=round(10000*(rr[3]/start[3]-1),4) if rr and start else None
 for sec in [0,30,60,300]:
  x[f"quote_{sec}s"]=level(d["quotes"],t+sec*1_000_000)
  x[f"top5_{sec}s"]=level(d["book_snapshot_5"],t+sec*1_000_000)
 v=x.get("return_300s_bps");sign=1 if side=="buy" else -1 if side=="sell" else None
 x["same_direction_20bps_5m_descriptive"]=sign*v>=20 if v is not None and sign is not None else None
 x["minute_vs_event_return_diff_bps"]=round(v-c["prior_minute_close_return_5m_bps"],4) if v is not None else None
 x["status"]="MECHANICS_ONLY" if v is not None else "MISSING_CLOCK_PRICES"
 RESULT.append(x)
complete=all(q["status"]=="OK" for q in PROV) and all(c["t0_utc"] and c["status"]=="MECHANICS_ONLY" for c in RESULT)
obj={"research":"09L","version":"v0.8.5","source_date":D,"run_at_utc":dt.datetime.now(dt.timezone.utc).isoformat(),"status":"EVENTCLOCK_EXPLORATORY_COMPLETE" if complete else "DATA_INCOMPLETE","source_provenance":PROV,"frozen_cases":RESULT,"case_count":len(RESULT),"verified_cluster_first_touch":False,"dealer_gamma_sign":"UNKNOWN","causal_inference":False,"controls_confirmed_liquidation_free":False,"no_trade_authority":True,"limitations":["Retrospective case selection, one sample day, no OOS","No historical Model2 point-in-time cluster states","No signed dealer inventory or first-hit","Zero observed liquidation messages does not mean zero actual liquidations","Top5 snapshots do not reveal cancellation vs replenishment","Events anchored to observed message capture, not necessarily first real exchange liquidation"]}
DEST.parent.mkdir(parents=True,exist_ok=True)
DEST.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+"\n")
print(json.dumps({"status":obj["status"],"case_count":len(RESULT),"out":str(DEST)}),flush=True)
if not complete:raise SystemExit(2)
