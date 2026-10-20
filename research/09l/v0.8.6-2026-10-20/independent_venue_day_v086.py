#!/usr/bin/env python3
"""09L v0.8.6: preregistered *historical* independent venue/date microstructure robustness. SHADOW ONLY."""
import argparse,bisect,collections,csv,datetime,gzip,hashlib,io,json,math,sys,time,urllib.request
from pathlib import Path
MATRIX={
 "bybit_sep":("bybit","BTCUSDT","2026-09-01"),
 "okx_oct":("okex-swap","BTC-USDT-SWAP","2026-10-01")
}
CLOCKS=("07:24:30","08:32:30","13:49:30","14:19:30","15:10:30","15:49:30","17:28:30","18:38:30")
PHASES=("pre30","post30","post60","post300")
BASE="https://datasets.tardis.dev/v1"
parser=argparse.ArgumentParser()
parser.add_argument("--study",required=True,choices=MATRIX)
A=parser.parse_args();VENUE,SYMBOL,DATE=MATRIX[A.study]; y,mo,d=DATE.split("-")
T0=int(datetime.datetime(int(y),int(mo),int(d),tzinfo=datetime.timezone.utc).timestamp()*1000000)
stamp=lambda s:T0+(int(s[:2])*3600+int(s[3:5])*60+int(s[6:8]))*1_000_000
ALL=[]
for hh in CLOCKS:ALL.append({"case_id":"clock_"+hh,"group":"fixed_clock","t0":stamp(hh),"side":"none",
 "anchor_description":"FIXED_UTC_CLOCK_INDEPENDENT_OF_NEW_DAY_PRICE_OR_LIQ"})
P=Path("research/09l/v0.8.6-2026-10-20/derived");P.mkdir(parents=True,exist_ok=True)
SOURCES=[];QA=collections.Counter();CLOCK_LIMIT=450_000_000;TIME_LIMIT_SECS=900
class Tap:
 def __init__(self,f):self.f=f;self.sha=hashlib.sha256();self.n=0
 def read(self,n=-1):
  b=self.f.read(n);self.n+=len(b);self.sha.update(b)
  if self.n>CLOCK_LIMIT:raise RuntimeError("COMPRESSED_SOURCE_BYTE_LIMIT_450MB")
  return b
def rows(typ,sy):
 u=f"{BASE}/{VENUE}/{typ}/{y}/{mo}/{d}/{sy}.csv.gz"
 o={"kind":typ,"source_symbol":sy,"url":u}
 try:
  t=time.monotonic()
  h=urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":"09L-v086-historical-shadow"}),timeout=100)
  if h.status!=200:raise RuntimeError("HTTP_"+str(h.status))
  tap=Tap(h);reader=csv.reader(io.TextIOWrapper(gzip.GzipFile(fileobj=tap),encoding="utf8",newline=""))
  header=next(reader);ix={a:i for i,a in enumerate(header)}
  needed={"symbol","local_timestamp","price","amount","side"}
  if typ=="incremental_book_L2":needed.add("is_snapshot")
  if not needed.issubset(ix):raise ValueError("MISSING_COLUMNS_"+repr(sorted(needed-set(ix))))
  yield ("__header__",ix)
  n=0;selected=0;invalid=0;out_of_date=0;prev_ts=None;nonmonotonic=0
  for r in reader:
   n+=1
   if r[ix["symbol"]]!=SYMBOL:continue
   selected+=1
   try:
    ts=int(r[ix["local_timestamp"]]);price=float(r[ix["price"]]);qty=float(r[ix["amount"]]);side=r[ix["side"]].lower()
    if not(math.isfinite(price) and math.isfinite(qty)) or price<=0 or qty<0:raise ValueError()
    if typ=="incremental_book_L2" and side not in ("bid","ask"):raise ValueError()
    if typ!="incremental_book_L2" and side not in ("buy","sell"):raise ValueError()
    if not T0<=ts<T0+86400_000_000:out_of_date+=1;continue
   except (ValueError,TypeError,IndexError):invalid+=1;continue
   if prev_ts is not None and ts<prev_ts:nonmonotonic+=1
   prev_ts=ts
   yield(ts,price,qty,side,(r[ix["is_snapshot"]].lower()=="true") if typ=="incremental_book_L2" else False)
  o.update(status="OK",raw_rows=n,target_symbol_rows=selected,invalid_rows=invalid,out_of_date_rows=out_of_date,
    local_timestamp_nonmonotonic=nonmonotonic,compressed_sha256=tap.sha.hexdigest(),
    compressed_bytes=tap.n,seconds=round(time.monotonic()-t,2))
  if nonmonotonic>0:o["status"]="QA_FAIL_NONMONOTONIC_TIME"
  if invalid>0:o["status"]="QA_FAIL_INVALID_ROW"
 except Exception as e:
  o.update(status="SOURCE_UNAVAILABLE",reason=type(e).__name__+": "+str(e)[:270])
 finally:
  SOURCES.append(o);print(typ,o["status"],o.get("target_symbol_rows"),flush=True)
# Select the first BTC liquidation message after each fixed session bucket (not selected on size/future price).
liq_seen=[]
for z in rows("liquidations","PERPETUALS"):
 if z[0]=="__header__":continue
 ts,price,qty,side,_=z
 liq_seen.append((ts,side,qty))
for session in ("06:00:00","12:00:00","18:00:00"):
 start=stamp(session); hit=next((r for r in liq_seen if r[0]>=start),None)
 if hit:
  ts,side,amount=hit
  ALL.append({"case_id":"first_liq_after_"+session,"group":"first_liq_per_session","t0":ts,"side":side,
   "source_liquidation_qty_raw":amount,"anchor_description":"FIRST_OBSERVED_LIQ_AFTER_FIXED_UTC_SESSION"})
else_source_liq=next((v for v in SOURCES if v["kind"]=="liquidations"),{})
if else_source_liq.get("status")!="OK":
 ALL=[e for e in ALL if e["group"]=="fixed_clock"]
# Complete event-time prior reference price by looking BACK no more than 5 seconds.
for e in ALL:e.update(price_t0=None,price_t0_ts=None,trades=[],decs=[],gross=collections.Counter())
for z in rows("trades",SYMBOL):
 if z[0]=="__header__":continue
 ts,px,qty,side,_=z
 for e in ALL:
  anchor=e["t0"]
  if anchor-5_000_000<=ts<=anchor and (e["price_t0_ts"] is None or ts>=e["price_t0_ts"]):
   e["price_t0"]=px;e["price_t0_ts"]=ts
  if anchor-31_000_000<=ts<anchor+301_000_000:
   e["trades"].append((ts,px,qty,side))
for e in ALL:
 px=e["price_t0"]
 if px is not None:e["low"]=px*.9975;e["high"]=px*1.0025
 else:QA["NO_ASOF_PRICE"]+=1
# Reconstruct full historical absolute L2 sizes to compute changes, reset initial snapshot.
book={"bid":{},"ask":{}};initialized=False;prev_snapshot=False;reset=0;pre_snapshot=0
for z in rows("incremental_book_L2",SYMBOL):
 if z[0]=="__header__":continue
 ts,price,qty,side,snapshot=z
 if snapshot and not prev_snapshot:
  book={"bid":{},"ask":{}};reset+=1;initialized=True
 prev_snapshot=snapshot
 if not initialized:pre_snapshot+=1;continue
 d=book[side];old=d.get(price,0.0)
 if qty==0:d.pop(price,None)
 else:d[price]=qty
 if snapshot or old==qty:continue
 change=qty-old
 for e in ALL:
  if "low" not in e or price<e["low"] or price>e["high"] or not e["t0"]-30_000_000<=ts<e["t0"]+300_000_000:continue
  rel=ts-e["t0"]
  if change<0:e["decs"].append((ts,price,-change,side))
  for period,a,b in (("pre30",-30,0),("post30",0,30),("post60",0,60),("post300",0,300)):
   if a*1e6<=rel<b*1e6:
    e["gross"][(period,side,"up" if change>0 else "down")]+=abs(change)
# Always rebuild trade capacity per placebo to avoid reuse.
def match_one(e,scenario):
 trades=collections.defaultdict(list)
 for ts,price,amount,side in e["trades"]:
  if not(e["low"]<=price<=e["high"]):continue
  altered_ts=ts+5_000_000 if scenario=="shift_5s" else ts
  trades[(price,side)].append([altered_ts,amount])
 stamps={}
 for k,v in trades.items():
  v.sort(key=lambda x:x[0]);stamps[k]=[r[0] for r in v]
 totals=collections.Counter()
 for ts,price,qty,bkside in sorted(e["decs"],key=lambda x:(x[0],x[1],x[3])):
  totals[bkside+"_decrement"]+=qty
  side=("sell" if bkside=="bid" else "buy")
  if scenario=="flipped":side="buy" if side=="sell" else "sell"
  key=(price,side);v=trades.get(key,[]);tlist=stamps.get(key,[])
  L=bisect.bisect_left(tlist,ts-1_000_000);R=bisect.bisect_right(tlist,ts+1_000_000)
  remaining=qty
  if L<R:
   for i in sorted(range(L,R),key=lambda i:(abs(ts-tlist[i]),tlist[i],i)):
    if remaining<1e-9:break
    available=v[i][1]
    if available<=0:continue
    used=min(remaining,available);v[i][1]-=used;remaining-=used
    lag=abs(ts-tlist[i])
    b="50" if lag<=50_000 else "200" if lag<=200_000 else "1000"
    totals[bkside+"_matched_"+b]+=used
  totals[bkside+"_unpaired"]+=max(0,remaining)
 summary={}
 for s in ("bid","ask"):
  base=totals[s+"_decrement"]
  vals={b:round(totals[s+"_matched_"+b],6) for b in ("50","200","1000")}
  matched=sum(vals.values())
  summary[s]={"total_decrement":round(base,6),"matched":round(matched,6),
    "share_pct":round(matched/base*100,4) if base else None,
    "disjoint_lag_raw_quantities":vals,"unpaired":round(totals[s+"_unpaired"],6)}
 allbase=sum(summary[s]["total_decrement"] for s in ("bid","ask"))
 allmatch=sum(summary[s]["matched"] for s in ("bid","ask"))
 summary["combined"]={"total_decrement":round(allbase,6),"matched":round(allmatch,6),
  "share_pct":round(100*allmatch/allbase,4) if allbase else None}
 return summary
RESULTS=[]
for e in ALL:
 item={"case_id":e["case_id"],"group":e["group"],"utc_anchor":datetime.datetime.fromtimestamp(e["t0"]/1e6,datetime.timezone.utc).isoformat(),
 "liquidation_side_if_observed":e["side"],"price_asof":e["price_t0"],"price_age_s":round((e["t0"]-e["price_t0_ts"])/1e6,6) if e["price_t0_ts"] is not None else None,
 "selected_on_future_price":False,"n_trade_rows_window":len(e["trades"]),"n_decrements_band":len(e["decs"])}
 if "low" in e and e["decs"]:
  for k in ("correct","flipped","shift_5s"):item[k]=match_one(e,k)
  item["state"]="EVALUATED"
 else:item["state"]="NO_ASOF_PRICE" if "low" not in e else "NO_L2_DECREMENTS"
 RESULTS.append(item)
required=[v for v in SOURCES if v["kind"] in ("trades","incremental_book_L2")]
status="ROBUSTNESS_EXPLORATORY_COMPLETE" if len(required)==2 and all(v["status"]=="OK" and v.get("target_symbol_rows",0)>0 for v in required) and reset>=1 and len([v for v in RESULTS if v["state"]=="EVALUATED" and v["group"]=="fixed_clock"])==8 else "DATA_INCOMPLETE"
FIXED=[x for x in RESULTS if x["group"]=="fixed_clock" and x["state"]=="EVALUATED"]
def aggregate(xs,kind):
 b=sum(x[kind]["combined"]["total_decrement"] for x in xs);n=sum(x[kind]["combined"]["matched"] for x in xs)
 return {"raw_decrement":round(b,6),"raw_matched":round(n,6),"match_share_pct":round(100*n/b,4) if b else None}
SUMMARY={"fixed_window_count":len(FIXED),"correct":aggregate(FIXED,"correct") if FIXED else None,
"flipped":aggregate(FIXED,"flipped") if FIXED else None,"shift_5s":aggregate(FIXED,"shift_5s") if FIXED else None}
if FIXED:
 SUMMARY["positive_correct_over_flipped_n"]=sum(x["correct"]["combined"]["share_pct"]>x["flipped"]["combined"]["share_pct"] for x in FIXED)
 SUMMARY["positive_correct_over_shift_n"]=sum(x["correct"]["combined"]["share_pct"]>x["shift_5s"]["combined"]["share_pct"] for x in FIXED)
obj={"study":"09L v0.8.6 historical independent-date cross-venue robustness","id":A.study,"venue":VENUE,"symbol":SYMBOL,"date":DATE,"status":status,
"design":"8_FIXED_UTC_CLOCK_PRESELECTED_IN_OLD_STUDY_PLUS_FIRST_3_SESSION_LIQ_MIXED_IF_AVAILABLE",
"sources":SOURCES,"quality":{"reconstruction_snapshot_resets":reset,"discarded_before_initial_snapshot":pre_snapshot,"qa_flags":dict(QA)},
"fixed_primary_aggregate":SUMMARY,"casebook":RESULTS,
"scientific_limits":["Fixed windows are not genuine independent random samples; historical day preselected before this replay but not prospective forecast",
"Correct side versus flipped side is microstructure sanity, not causal evidence or proof of order execution matching",
"Greedy same-price L2 decrease vs trade association with 1s capture lag is not maker cancel/fill/replenishment identity",
"Shift_5s uses no future information for signal; it is a retrospective falsification only",
"Source raw quantity unit/contract multiplier not cross-exchange normalized; never compare raw volumes between venues",
"First-day-of-month Tardis free historical samples; generalization to other dates or all venues untested",
"Missing liquidation messages do not prove absence of liquidations; no historical CoinGlass cluster PIT, no dealer signed gamma",
"No first-hit/cascade probability, no predictive OOS, no trade signal or accepted canonical revisions"],"trade_canon_mutation":False}
path=P/f"09L_v086_{A.study}_fixed_clock_robustness.json";path.write_text(json.dumps(obj,indent=2,ensure_ascii=False)+"\n")
print(json.dumps({"status":status,"study":A.study,"quality":obj["quality"],"fixed_primary_aggregate":SUMMARY,"liq_status":else_source_liq.get("status"),"cases":len(RESULTS)}),flush=True)
