#!/usr/bin/env python3
"""09L v0.8.5: matched trade and L2 quote-size decreases, isolated research only.
All timing in Tardis local_timestamp UTC usec. Never infer verified cancels, fills, or dealer inventory.
"""
import csv,gzip,io,hashlib,urllib.request,json,datetime,bisect,math,collections,time
from pathlib import Path
ROOT=Path("research/09l")
SRC="https://datasets.tardis.dev/v1/bybit"
OLD=json.loads((ROOT/"v0.8.4-2026-10-20/derived/bybit_2026-10-01_event_time_casebook.json").read_text())
OLD_L2=json.loads((ROOT/"v0.8.4-2026-10-20/derived/bybit_2026-10-01_full_l2_fixed_band.json").read_text())
EXPECTED={"trades":"abf7e614b2d6b45dbfa85bdc79432228fa034cbbdba9b7a470078d14abf3c7b6",
"incremental_book_L2":"f8f65353fa369d98e1a4ae990dc42eb21cea8dda16b9cb941c3e92d64daefa53"}
EVENTS=[]
for prior in OLD["event_rows"]:
 t=int(datetime.datetime.fromisoformat(prior["event_t0_utc"]).timestamp()*1_000_000)
 mid=prior["t0"]["mid"]
 EVENTS.append(dict(label=prior["minute_utc"],side=prior["event_side"],t0=t,mid=mid,band_low=mid*.9975,
   band_high=mid*1.0025,trades=[],decs=[],gross=collections.defaultdict(float),older=prior))
old_by_label={e["minute_utc"]:e for e in OLD_L2["events"]}
class Tap:
 def __init__(self,stream):self.f=stream;self.n=0;self.sha=hashlib.sha256()
 def read(self,n=-1):
  b=self.f.read(n);self.n+=len(b);self.sha.update(b)
  if self.n>180_000_000:raise RuntimeError("COMPRESSED_CAP_180MB")
  return b
provenance=[];qa=collections.Counter()
def scan(kind,symbol):
 url=f"{SRC}/{kind}/2026/10/01/{symbol}.csv.gz"
 item={"type":kind,"url":url}
 try:
  stream=urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"09L-v085-microstructure-research"}),timeout=90)
  if stream.status!=200:raise RuntimeError("HTTP_"+str(stream.status))
  tap=Tap(stream);r=csv.reader(io.TextIOWrapper(gzip.GzipFile(fileobj=tap),encoding="utf8",newline=""))
  hdr=next(r);pos={col:i for i,col in enumerate(hdr)}
  needed={"symbol","local_timestamp","price","amount","side"}
  if kind=="incremental_book_L2":needed.add("is_snapshot")
  if not needed.issubset(pos):raise ValueError("REQUIRED_COLUMNS_MISSING "+str(needed-set(pos)))
  yield ("__columns__",pos)
  n=0;btc=0;invalid=0
  for row in r:
   n+=1
   if row[pos["symbol"]]!="BTCUSDT":continue
   btc+=1
   try:
    ts=int(row[pos["local_timestamp"]]);price=float(row[pos["price"]]);qty=float(row[pos["amount"]])
    side=row[pos["side"]].lower()
    if not math.isfinite(price) or not math.isfinite(qty) or qty<0 or price<=0:raise ValueError()
    if kind=="trades" and side not in ("buy","sell"):raise ValueError()
    if kind!="trades" and side not in ("bid","ask"):raise ValueError()
   except (ValueError,OverflowError):
    invalid+=1;continue
   yield (ts,price,qty,side,row[pos["is_snapshot"]].lower()=="true" if kind!="trades" else False)
  item.update(status="OK",raw_rows=n,btc_rows=btc,invalid_rows=invalid,compressed_bytes=tap.n,compressed_sha256=tap.sha.hexdigest())
  if tap.sha.hexdigest()!=EXPECTED[kind]:item["status"]="SOURCE_HASH_MISMATCH"
 except Exception as ex:item.update(status="SOURCE_UNAVAILABLE_OR_ERROR",error=type(ex).__name__+": "+str(ex)[:200])
 finally:
  provenance.append(item)
  print(kind,item.get("status"),item.get("btc_rows"),flush=True)
# Ingestion is by source capture order. Events (far apart) do not overlap windows.
for v in scan("trades","BTCUSDT"):
 if v[0]=="__columns__":continue
 ts,px,qty,side,_=v
 for e in EVENTS:
  if e["t0"]-31_000_000<=ts<=e["t0"]+301_000_000 and e["band_low"]<=px<=e["band_high"]:
   e["trades"].append((ts,px,qty,side))
book={"bid":{},"ask":{}};in_snapshot=False;initialized=False;resets=0;prior_ts=None;monotonic=0;pre_snapshot=0
for v in scan("incremental_book_L2","BTCUSDT"):
 if v[0]=="__columns__":continue
 ts,px,qty,side,snap=v
 if prior_ts is not None and ts<prior_ts:monotonic+=1
 prior_ts=ts
 if snap and not in_snapshot:
  book={"bid":{},"ask":{}};initialized=True;resets+=1
 in_snapshot=snap
 if not initialized:
  pre_snapshot+=1;continue
 d=book[side];prev=d.get(px,0.0)
 if qty==0:d.pop(px,None)
 else:d[px]=qty
 if snap or qty==prev:continue
 change=qty-prev
 for e in EVENTS:
  rel=ts-e["t0"]
  if not (-30_000_000<=rel<300_000_000 and e["band_low"]<=px<=e["band_high"]):continue
  if 0<=rel<30_000_000:
   e["gross"][side+"_up30" if change>0 else side+"_down30"]+=abs(change)
  if change<0:
   e["decs"].append((ts,px,abs(change),side))
# Replay quality: 30-second fixed band bid/ask updates must reproduce v0.8.4D
for e in EVENTS:
 earlier=old_by_label[e["label"]]["fixed_band_displayed_changes"]["post30"]
 for side in ("bid","ask"):
  for direction in ("up","down"):
   observed=e["gross"][side+"_"+direction+"30"]
   expected=earlier[side+"_"+direction]
   if abs(observed-expected)>0.000005:qa["fixed_band_30s_mismatch"]+=1
def matcher(e,flipped=False):
 # Every run uses independent trade quantity budget, prevent re-use within scenario.
 # Can match only same price. Use separate time sequences by price and aggressor side.
 lookup=collections.defaultdict(list)
 for ts,px,qty,side in e["trades"]:
  lookup[(px,side)].append([ts,qty])
 seq={}
 for k,vs in lookup.items():
  vs.sort(key=lambda v:v[0]);seq[k]=[v[0] for v in vs]
 summary={k:0.0 for k in ("bid_decrease","ask_decrease","bid_matched_50","bid_matched_200","bid_matched_1000",
  "ask_matched_50","ask_matched_200","ask_matched_1000","bid_unmatched","ask_unmatched")}
 counts=collections.Counter()
 for ts,px,size,bkside in sorted(e["decs"],key=lambda x:(x[0],x[1],x[3])):
  summary[bkside+"_decrease"]+=size;remaining=size
  taker=("sell" if bkside=="bid" else "buy")
  if flipped:taker="buy" if taker=="sell" else "sell"
  key=(px,taker);v=lookup.get(key)
  if v:
   times=seq[key]
   lo=bisect.bisect_left(times,ts-1_000_000)
   hi=bisect.bisect_right(times,ts+1_000_000)
   if lo<hi:
    order=sorted(range(lo,hi),key=lambda i:(abs(times[i]-ts),times[i],i))
    for i in order:
     if remaining<1e-10:break
     lag=abs(times[i]-ts)
     if lag<=50_000:bucket="50"
     elif lag<=200_000:bucket="200"
     else:bucket="1000"
     unused=v[i][1]
     if unused<=0:continue
     allocated=min(unused,remaining)
     v[i][1]-=allocated;remaining-=allocated
     summary[bkside+"_matched_"+bucket]+=allocated
     counts[bkside+"_"+bucket+"_links"]+=1
  summary[bkside+"_unmatched"]+=max(0,remaining)
 for k in summary:summary[k]=round(summary[k],6)
 for side in ("bid","ask"):
  matched=sum(summary[side+"_matched_"+bucket] for bucket in ("50","200","1000"))
  denom=summary[side+"_decrease"]
  summary[side+"_matched_total"]=round(matched,6)
  summary[side+"_match_share_pct"]=round(100*matched/denom,4) if denom>0 else None
 return {"quantity":summary,"links":dict(counts)}
cases=[]
for e in EVENTS:
 real=matcher(e,False);placebo=matcher(e,True)
 cases.append({"minute_utc":e["label"],"side":e["side"],"t0_utc":e["older"]["event_t0_utc"],
 "source_mid":e["mid"],"price_band_bps_each_side":25,"n_trades_in_band":len(e["trades"]),
 "n_l2_decrements_in_band":len(e["decs"]),"correct_side_mapping":real,"flipped_side_placebo":placebo,
 "forward_5min_bps_FROM_v084b":e["older"]["quote_return_5m_bps"],
 "cascade_confirmed":False,"cluster_touch_status":"NOT_TESTED",
 "unit_status":"SAME_VENDOR_RAW_QUANTITIES_CONTRACT_MULTIPLIER_NOT_AUDITED"})
status=("SOURCE_UNAVAILABLE_OR_ERROR" if any(x["status"]=="SOURCE_UNAVAILABLE_OR_ERROR" for x in provenance)
 else "SOURCE_HASH_MISMATCH" if any(x["status"]=="SOURCE_HASH_MISMATCH" for x in provenance)
 else "BOOK_NOT_INITIALIZED" if not initialized or resets==0
 else "QA_FAILURE" if monotonic or qa["fixed_band_30s_mismatch"] else "MATCHING_EXPLORATORY_COMPLETE")
obj={"study":"09L v0.8.5 trade-L2 same-price matching","date_run_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
 "source_date_utc":"2026-10-01","status":status,"scope":"RETROSPECTIVE_SHADOW_NOT_TRADEABLE",
 "timestamp":"Tardis local_timestamp capture microseconds UTC","windows_abs_lag_ms":["[0,50]","(50,200]","(200,1000]"],
 "source_provenance":provenance,"quality":{"book_resets":resets,"pre_snapshot_discarded":pre_snapshot,
 "l2_nonmonotonic_rows":monotonic,"qa":dict(qa),"n_events":len(cases)},
 "results":cases,
 "limitations":["Events selected retrospectively on observed liquidation size in v0.8.3, not independent OOS",
 "L2 is limited provider captured venue book, not all orders including all RPI",
 "Price-and-arrival-time match plus greedy amount allocation is an ambiguous execution-associated proxy, not demonstrated fills or cancellations",
 "Side-flipped placebo is a sanity comparison, not independent statistical evidence",
 "The 8 event windows do not establish historical CoinGlass first-hit or true cluster lifecycle",
 "No signed dealer gamma, counterparty identity, or identified futures/spot hedge strategy",
 "Tardis trade and book arrival timestamps may differ from matching-engine timestamps",
 "No calibrated probabilities, impact regression, or trade permissions"],"canon_writeback":"NONE"}
out=ROOT/"v0.8.5-2026-10-20/derived"
out.mkdir(parents=True,exist_ok=True)
(out/"bybit_2026-10-01_price_time_trade_l2_matching.json").write_text(json.dumps(obj,ensure_ascii=False,indent=2)+"\n")
print(json.dumps({"status":status,"events":len(cases),"qa":dict(qa),
 "cases":[{"time":x["minute_utc"],"side":x["side"],
 "bid_correct_pct":x["correct_side_mapping"]["quantity"]["bid_match_share_pct"],
 "bid_placebo_pct":x["flipped_side_placebo"]["quantity"]["bid_match_share_pct"],
 "ask_correct_pct":x["correct_side_mapping"]["quantity"]["ask_match_share_pct"],
 "ask_placebo_pct":x["flipped_side_placebo"]["quantity"]["ask_match_share_pct"]} for x in cases]}),flush=True)
