#!/usr/bin/env python3
"""09L v0.8.4D full-day incremental L2 reconstruction, derivations only, shadow-only."""
import csv,gzip,io,urllib.request,hashlib,json,bisect,datetime,time,math,collections
from pathlib import Path
ROOT=Path("research/09l/v0.8.4-2026-10-20/derived")
prev=json.loads((ROOT/"bybit_2026-10-01_event_time_casebook.json").read_text())
events=[]
for item in prev["event_rows"]:
 if not item.get("event_t0_utc") or item["t0"]["mid"] is None:continue
 t=int(datetime.datetime.fromisoformat(item["event_t0_utc"]).timestamp()*1e6)
 s=item["t0"]["mid"]
 e={"minute":item["minute_utc"],"side":item["event_side"],"t":t,"reference_mid":s,
    "band_low":s*.9975,"band_high":s*1.0025,"deltas":{},"samples":{},"reference":item}
 for phase in ("pre30","post30","post60","post300"):
  e["deltas"][phase]={"bid_up":0.0,"bid_down":0.0,"ask_up":0.0,"ask_down":0.0,
     "changed_rows_bid":0,"changed_rows_ask":0}
 events.append(e)
queries=sorted((e["t"]+offset*1000000,i,offset) for i,e in enumerate(events) for offset in (-30,-1,0,30,60,300))
qi=0
books={"bid":{},"ask":{}}
have_snapshot=False;prior_snapshot=False;last_ts=None;count=0;invalid=0;ignored=0;resets=0;nonmonotonic=0;crossed=0
MAX_COMPRESSED=165*1024*1024
class Tap:
 def __init__(self,stream):self.stream=stream;self.n=0;self.h=hashlib.sha256()
 def read(self,n=-1):
  s=self.stream.read(n);self.n+=len(s);self.h.update(s)
  if self.n>MAX_COMPRESSED:raise RuntimeError("COMPRESSED_BYTE_CAP_165MIB")
  return s
def sample_for_query(i,offset,target):
 e=events[i];k=str(offset);out={"book_age_s":None,"bid5":None,"ask5":None,"spread_bps":None,"top5_imbalance":None,"source_reference_bid5":None,"source_reference_ask5":None,"bid5_difference":None,"ask5_difference":None}
 if last_ts is not None and have_snapshot and 0<=target-last_ts<=2_000_000:
  bids=sorted(books["bid"].keys(),reverse=True)[:5];asks=sorted(books["ask"].keys())[:5]
  if bids and asks:
   bprice=bids[0];aprice=asks[0]
   if bprice>=aprice:
    out["crossed_book"]=True
   else:
    bidqty=sum(books["bid"][z] for z in bids);askqty=sum(books["ask"][z] for z in asks)
    out.update(book_age_s=round((target-last_ts)/1e6,6),bid5=round(bidqty,6),
               ask5=round(askqty,6),spread_bps=round(10000*(aprice-bprice)/((aprice+bprice)/2),6),
               top5_imbalance=round((bidqty-askqty)/(bidqty+askqty),6) if bidqty+askqty>0 else None)
 ref=e["reference"]["t"+str(offset)]
 out["source_reference_bid5"]=ref["bid_top5_raw"];out["source_reference_ask5"]=ref["ask_top5_raw"]
 if out["bid5"] is not None and ref["bid_top5_raw"] is not None:
  out["bid5_difference"]=round(out["bid5"]-ref["bid_top5_raw"],6)
 if out["ask5"] is not None and ref["ask_top5_raw"] is not None:
  out["ask5_difference"]=round(out["ask5"]-ref["ask_top5_raw"],6)
 e["samples"][k]=out
src="https://datasets.tardis.dev/v1/bybit/incremental_book_L2/2026/10/01/BTCUSDT.csv.gz"
source={"url":src,"status":"UNTESTED"};t_start=time.monotonic()
try:
 r=urllib.request.urlopen(urllib.request.Request(src,headers={"User-Agent":"09L-v084d-shadow"}),timeout=90)
 if r.status!=200:raise RuntimeError("HTTP_"+str(r.status))
 tap=Tap(r)
 f=io.TextIOWrapper(gzip.GzipFile(fileobj=tap),encoding="utf8",newline="")
 names=f.readline().strip().split(",");pos={x:i for i,x in enumerate(names)}
 req={"symbol","local_timestamp","is_snapshot","side","price","amount"}
 if not req.issubset(pos):raise ValueError("MISSING_COLUMNS "+str(req-set(pos)))
 for line in f:
  count+=1; v=line.strip().split(",")
  if v[pos["symbol"]]!="BTCUSDT":ignored+=1;continue
  try:
   ts=int(v[pos["local_timestamp"]]);side=v[pos["side"]];px=float(v[pos["price"]]);amt=float(v[pos["amount"]]);snap=v[pos["is_snapshot"]].lower()=="true"
   if side not in books or not math.isfinite(px) or not math.isfinite(amt) or px<=0 or amt<0:invalid+=1;continue
  except (ValueError,IndexError):invalid+=1;continue
  if last_ts is not None and ts<last_ts:nonmonotonic+=1
  # Measurements at target are complete only after the previous capture-ts group is finished.
  while qi<len(queries) and queries[qi][0]<ts:
   target,ei,offset=queries[qi];sample_for_query(ei,offset,target);qi+=1
  if snap and not prior_snapshot:
   books={"bid":{},"ask":{}};have_snapshot=True;resets+=1
  prior_snapshot=snap
  if not have_snapshot:ignored+=1;last_ts=ts;continue
  d=books[side];old=d.get(px,0.)
  if amt==0:d.pop(px,None)
  else:d[px]=amt
  if not snap and old!=amt:
   diff=amt-old
   # Fixed price bins remove moving-top-5 level selection from quote-change denominator.
   for e in events:
    if px<e["band_low"] or px>e["band_high"]:continue
    rel=ts-e["t"]
    phases=[]
    if -30_000_000<=rel<0:phases.append("pre30")
    if 0<=rel<30_000_000:phases.append("post30")
    if 0<=rel<60_000_000:phases.append("post60")
    if 0<=rel<300_000_000:phases.append("post300")
    for ph in phases:
     z=e["deltas"][ph];z[f"changed_rows_{side}"]+=1
     z[f"{side}_{'up' if diff>0 else 'down'}"]+=abs(diff)
  last_ts=ts
 while qi<len(queries):
  target,ei,offset=queries[qi];sample_for_query(ei,offset,target);qi+=1
 source.update(status="OK",compressed_bytes=tap.n,compressed_sha256=tap.h.hexdigest(),rows=count,
               invalid_rows=invalid,ignored_pre_snapshot_or_wrong_symbol=ignored,
               snapshot_resets=resets,local_timestamp_nonmonotonic=nonmonotonic,elapsed_secs=round(time.monotonic()-t_start,2))
except Exception as exc:
 source.update(status="INCREMENTAL_SOURCE_FAILURE",error=type(exc).__name__+": "+str(exc)[:300],rows_seen=count,
               elapsed_secs=round(time.monotonic()-t_start,2))
summary=[]
for e in events:
 for ph,z in e["deltas"].items():
  for key,val in z.items():
   if isinstance(val,float):z[key]=round(val,6)
 support="bid" if e["side"]=="sell" else "ask" if e["side"]=="buy" else None
 z={"minute_utc":e["minute"],"side":e["side"],"price_band_mid":e["reference_mid"],
    "price_band_bps_each_side":25,"t0_utc":e["reference"]["event_t0_utc"],"support_side":support,
    "fixed_band_displayed_changes":e["deltas"],"incremental_samples":e["samples"]}
 diffs=[]
 for it in e["samples"].values():
  for key in ("bid5_difference","ask5_difference"):
   if it.get(key)is not None:diffs.append(abs(it[key]))
 z["comparison_n"]=len(diffs);z["comparison_max_abs_raw_depth_diff"]=round(max(diffs),6) if diffs else None
 summary.append(z)
o={"study":"09L v0.8.4D fixed-band full incremental L2","date":"2026-10-20",
   "scope":"RETROSPECTIVE_SHADOW_ONLY","status":"L2_RECONSTRUCTED" if source["status"]=="OK" and resets>=1 and nonmonotonic==0 else "INCOMPLETE",
   "source":source,"events":summary,
   "guards":["Amount is absolute level amount; increases/decreases alone cannot identify add/cancel/fill",
   "No transaction-level match or true replenishment attribution",
   "Fixed ±25bps band around historical event-time quote mid, not a CoinGlass cluster",
   "Snapshot reset excluded from positive/negative quote changes",
   "Third-party provider reconstructed top5 levels may differ due to crossing and timing",
   "No PIT heatmap, signed gamma, first touch, or predictive probabilities","No trades, limits, NAV or Futures mutations"]}
fn=ROOT/"bybit_2026-10-01_full_l2_fixed_band.json"
fn.write_text(json.dumps(o,indent=2,ensure_ascii=False)+"\n")
print(json.dumps({"status":o["status"],"rows":count,"elapsed_secs":source["elapsed_secs"],
 "snapshots":resets,"comp_bytes":source.get("compressed_bytes"),"cases":len(summary),
 "samples":[(x["minute_utc"],x["comparison_n"],x["comparison_max_abs_raw_depth_diff"]) for x in summary]}),flush=True)
