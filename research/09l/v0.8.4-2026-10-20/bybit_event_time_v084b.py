#!/usr/bin/env python3
"""09L v0.8.4B historical Bybit BTCUSDT event-time replay; exploratory, research-only."""
import csv,gzip,io,urllib.request,hashlib,json,bisect,datetime,math,collections
from pathlib import Path
DAY="2026-10-01"; URL="https://datasets.tardis.dev/v1/bybit"; SYM="BTCUSDT"
CASES=[("07:24","sell"),("08:32","sell"),("13:49","control"),("14:19","control"),("15:10","control"),("15:49","control"),("17:28","buy"),("18:38","buy")]
DAY0=datetime.datetime(2026,10,1,tzinfo=datetime.timezone.utc)
as_us=lambda hhmm:int((DAY0+datetime.timedelta(hours=int(hhmm[:2]),minutes=int(hhmm[3:]))).timestamp()*1_000_000)
E=[dict(label=t,side=s,minute_us=as_us(t),data={f:[] for f in ["trades","quotes","book_snapshot_5","liquidations"]}) for t,s in CASES]
p=Path("research/09l/v0.8.4-2026-10-20/derived");p.mkdir(parents=True,exist_ok=True)
sources=[];qa=collections.Counter();MAX=135*1024*1024
class R:
 def __init__(self,f):self.f=f;self.h=hashlib.sha256();self.n=0
 def read(self,n=-1):
  s=self.f.read(n);self.n+=len(s);self.h.update(s)
  if self.n>MAX:raise RuntimeError("COMPRESSED_FILE_LIMIT_135MB")
  return s
def xfloat(s):
 try:
  z=float(s)
  return z if math.isfinite(z) else None
 except (TypeError,ValueError):return None
def rows(kind,symbol):
 u=f"{URL}/{kind}/2026/10/01/{symbol}.csv.gz"; info={"feed":kind,"url":u}
 try:
  rq=urllib.request.Request(u,headers={"User-Agent":"09L-v084b-shadow-study"})
  stream=urllib.request.urlopen(rq,timeout=85)
  if stream.status!=200:raise RuntimeError(f"HTTP_{stream.status}")
  rd=R(stream)
  reader=csv.DictReader(io.TextIOWrapper(gzip.GzipFile(fileobj=rd),encoding="utf8",newline=""))
  keys=set(reader.fieldnames or [])
  required={"symbol","local_timestamp"}
  if kind in ("liquidations","trades"):required|={"side","amount","price"}
  elif kind=="quotes":required|={"bid_price","ask_price","bid_amount","ask_amount"}
  else:required|={"bids[0].price","asks[0].price","bids[0].amount","asks[0].amount"}
  if not required.issubset(keys):raise ValueError("MISSING_COLUMNS "+str(required-keys))
  n=0;nb=0
  for a in reader:
   n+=1
   if a["symbol"]!=SYM:continue
   nb+=1
   try:ts=int(a["local_timestamp"])
   except (ValueError,TypeError):qa[kind+"_bad_ts"]+=1;continue
   yield (ts,a)
  info.update(status="OK",compressed_bytes=rd.n,compressed_sha256=rd.h.hexdigest(),raw_rows=n,btc_rows=nb)
 except Exception as exc:info.update(status="SOURCE_UNAVAILABLE_OR_ERROR",error=type(exc).__name__+": "+str(exc)[:220])
 finally:
  sources.append(info)
  print(kind,info["status"],info.get("btc_rows",0),flush=True)

liq_all=list(rows("liquidations","PERPETUALS"))
for e in E:
 if e["side"]=="control":e["t0"]=e["minute_us"]+30_000_000;continue
 eligible=[(t,a) for t,a in liq_all if e["minute_us"]<=t<e["minute_us"]+60_000_000 and a["side"].lower()==e["side"]]
 e["t0"]=min((t for t,a in eligible),default=None)
 if e["t0"] is None:qa["LIQ_ANCHOR_MISSING"]+=1
for kind in ("liquidations","trades","quotes","book_snapshot_5"):
 if kind=="liquidations":iterable=liq_all
 else:iterable=rows(kind,SYM)
 for ts,a in iterable:
  if a["symbol"]!=SYM:continue
  for e in E:
   t0=e["t0"]
   if t0 is None or not t0-120_000_000<=ts<=t0+301_000_000:continue
   if kind in ("liquidations","trades"):
    amount=xfloat(a["amount"]);price=xfloat(a["price"]);side=a["side"].lower()
    if amount is None or amount<0 or side not in ("buy","sell"):continue
    e["data"][kind].append((ts,side,amount,price))
   elif kind=="quotes":
    bid=xfloat(a["bid_price"]);ask=xfloat(a["ask_price"])
    if bid and ask and ask>bid:
     e["data"][kind].append((ts,(bid+ask)/2,10000*(ask-bid)/((bid+ask)/2)))
   else:
    bids=[xfloat(a.get(f"bids[{i}].amount")) for i in range(5)]
    asks=[xfloat(a.get(f"asks[{i}].amount")) for i in range(5)]
    b=xfloat(a["bids[0].price"]);ask=xfloat(a["asks[0].price"])
    if b and ask and ask>b and all(v is not None and v>=0 for v in bids+asks):
     biddep=sum(bids);askdep=sum(asks)
     e["data"][kind].append((ts,biddep,askdep,(biddep-askdep)/(biddep+askdep) if biddep+askdep else None,10000*(ask-b)/((ask+b)/2)))
for e in E:
 for kind,v in e["data"].items():v.sort(key=lambda a:a[0])
def prev(event,feed,delta,stale_sec=2):
 vals=event["data"][feed];ts=event["t0"]+int(delta*1e6)
 if not vals:return (None,None)
 ix=bisect.bisect_right(vals,(ts,float("inf")))-1 if feed=="quotes" else bisect.bisect_right([r[0] for r in vals],ts)-1
 # binary search on timestamps; stale check blocks forward-looking data
 if ix<0 or ts-vals[ix][0]>stale_sec*1e6:return (None,None)
 return vals[ix],round((ts-vals[ix][0])/1e6,6)
def agg(v,ts,a,b):
 out={"n":0,"buy":0.0,"sell":0.0}
 for r in v:
  if ts+a*1e6<=r[0]<ts+b*1e6:
   out["n"]+=1;out[r[1]]+=r[2]
 return {k:round(n,8) if isinstance(n,float) else n for k,n in out.items()}
def roundnull(x,n=5):return round(x,n) if x is not None and math.isfinite(x) else None
result=[]
for e in E:
 d={"minute_utc":"2026-10-01T"+e["label"]+":00Z","event_side":e["side"],"event_t0_utc":datetime.datetime.fromtimestamp(e["t0"]/1e6,datetime.timezone.utc).isoformat() if e["t0"] else None}
 if not e["t0"]:result.append({**d,"status":"EVENT_ANCHOR_MISSING"});continue
 for period,a,b in [("prior30",-30,0),("post30",0,30),("post60",0,60),("post300",0,300)]:
  d["trades_"+period]=agg(e["data"]["trades"],e["t0"],a,b)
  d["liqs_"+period]=agg(e["data"]["liquidations"],e["t0"],a,b)
 for delta in (-30,-1,0,5,15,30,60,300):
  q,qage=prev(e,"quotes",delta)
  b,bage=prev(e,"book_snapshot_5",delta)
  d["t"+str(delta)]={"mid":roundnull(q[1],4) if q else None,"quote_spread_bps":roundnull(q[2],4) if q else None,"quote_age_s":qage,
                      "bid_top5_raw":roundnull(b[1],6) if b else None,"ask_top5_raw":roundnull(b[2],6) if b else None,
                      "top5_imbalance":roundnull(b[3],5) if b else None,
                      "book_spread_bps":roundnull(b[4],4) if b else None,"book_age_s":bage}
  if q and b and abs(q[2]-b[4])>2:qa["quote_vs_book_spread_discrepancy_gt2bps"]+=1
 q0=d["t0"]["mid"];q300=d["t300"]["mid"];q60=d["t60"]["mid"]
 d["quote_return_5m_bps"]=roundnull(10000*(q300/q0-1),4) if q0 and q300 else None
 d["quote_return_1m_bps"]=roundnull(10000*(q60/q0-1),4) if q0 and q60 else None
 if e["side"]!="control":
  support="bid_top5_raw" if e["side"]=="sell" else "ask_top5_raw"
  a=d["t-1"][support];b=d["t30"][support];c=d["t60"][support]
  d["support_side"]=support
  d["support_depth_change_30s_pct"]=roundnull((b/a-1)*100,3) if a and b is not None else None
  d["support_depth_change_60s_pct"]=roundnull((c/a-1)*100,3) if a and c is not None else None
  r5=d["quote_return_5m_bps"]
  d["same_side_extension_20bp"]=bool(r5*(1 if e["side"]=="buy" else -1)>=20) if r5 is not None else None
  d["interpretation"]="OBSERVED_LIQ_MICROSTRUCTURE_ONLY"
 else:d["interpretation"]="HIGH_TRADE_MINUTE_NO_LIQ_MESSAGE_IN_SELECTED_MINUTE_NOT_TRUE_NEGATIVE"
 d["source_row_counts"]={k:len(v) for k,v in e["data"].items()}
 result.append(d)
complete=all(z.get("status")=="OK" and z.get("btc_rows",0)>0 for z in sources)
obj={"study":"09L v0.8.4B event-time Bybit","capture_date":"2026-10-01","computed_at_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
     "scope":"RETROSPECTIVE_EXPLORATORY_SHADOW_ONLY","status":"EVENT_TIME_COMPLETE" if complete and all(x.get("event_t0_utc") for x in result) else "DATA_INCOMPLETE",
     "local_capture_clock":"local_timestamp UTC usec","max_book_quote_staleness_sec":2,
     "source_provenance":sources,"quality_audit":dict(qa),"event_rows":result,
     "guardrails":{"coinglass_pit":"MISSING","cluster_first_touch":"NOT_TESTED","dealer_signed_gamma":"UNKNOWN",
                    "verified_cascades":0,"replenishment_vs_cancel_execution":"NOT_IDENTIFIABLE_FROM_TOP5",
                    "predictive_lift":"NOT_TESTED","trading_changes":"NONE"},
     "notices":["Same 8 retrospectively preselected v0.8.3 minutes; not independent holdout",
                "For controls, no observed liquidation message in selected minute does not prove zero forced liquidations",
                "Book top5 is provider reconstructed snapshots; never interpret positive changes as proof of market maker refill",
                "Raw sizes in venue-specific units, no USD conversion",
                "Quote sample uses only earlier timestamps with max 2 seconds of staleness",
                "Observed liquidations can be non-exhaustive","No option gamma inventory sign"]}
fn=p/"bybit_2026-10-01_event_time_casebook.json"
fn.write_text(json.dumps(obj,indent=2,ensure_ascii=False)+"\n")
print(json.dumps({"status":obj["status"],"events":len(result),"complete":complete,
 "selected_liq_count":[(x["minute_utc"],x["liqs_post30"]["n"],x["quote_return_5m_bps"],x.get("support_depth_change_30s_pct")) for x in result if x["event_side"]!="control"]}),flush=True)
