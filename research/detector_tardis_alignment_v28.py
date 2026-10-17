#!/usr/bin/env python3
"""Detector SHADOW v2.8: point-in-time 5m alignment audit, NOT a trading replay.
Timestamp is exchange event time, NOT proof of publication/receipt time."""
import csv,gzip,io,json,urllib.request,datetime as dt,collections,bisect,math
from pathlib import Path
O=Path("detector_tardis_alignment_v28_results");O.mkdir(exist_ok=True)
UTC=dt.timezone.utc
CASES=[("binance-futures","BTCUSDT","2021-06-01"),("bybit","BTCUSDT","2021-06-01"),("okex-swap","BTC-USDT-SWAP","2021-06-01"),("bybit","SOLUSDT","2024-06-01"),("okex-swap","SOL-USDT-SWAP","2024-06-01"),("okex-swap","HYPE-USDT-SWAP","2026-09-01")]
def ts(x):
 x=str(x).strip()
 try:
  n=float(x)
  if not math.isfinite(n):raise ValueError("bad timestamp")
  return dt.datetime.fromtimestamp(n/(1e9 if abs(n)>=1e17 else 1e6 if abs(n)>=1e14 else 1e3 if abs(n)>=1e11 else 1),UTC)
 except ValueError:
  v=dt.datetime.fromisoformat(x.replace("Z","+00:00"))
  if v.tzinfo is None:raise ValueError("naive timestamp")
  return v.astimezone(UTC)
def source(e,s,d,k):
 y,m,day=d.split("-");url=f"https://datasets.tardis.dev/v1/{e}/{k}/{y}/{m}/{day}/{s}.csv.gz"
 req=urllib.request.Request(url,headers={"User-Agent":"detector-shadow-align-v28"})
 with urllib.request.urlopen(req,timeout=100) as f:
  with gzip.GzipFile(fileobj=f) as gz:
   for row in csv.DictReader(io.TextIOWrapper(gz,encoding="utf-8-sig",newline="",errors="replace")):yield row
def number(s):
 try:
  if s is None or str(s).strip()=="":return None
  x=float(s)
  return x if math.isfinite(x) else None
 except (ValueError,TypeError):return None
def audit(e,s,d):
 start=dt.datetime.fromisoformat(d).replace(tzinfo=UTC);end=start+dt.timedelta(days=1)
 tick=[];counts=collections.Counter();last_raw=None
 for row in source(e,s,d,"derivative_ticker"):
  counts["ticker_rows"]+=1
  try:t=ts(row.get("timestamp"))
  except Exception:counts["ticker_bad_ts"]+=1;continue
  if last_raw is not None and t<last_raw:counts["ticker_reversals"]+=1
  last_raw=t
  if not(start<=t<end):counts["ticker_outside"]+=1;continue
  oi=number(row.get("open_interest"));fund=number(row.get("funding_rate"))
  if oi is not None:counts["oi_nonempty"]+=1
  if fund is not None:counts["fund_nonempty"]+=1
  tick.append((t,oi,fund))
 tick.sort(key=lambda x:x[0])
 # Each feature is independently updated; missing field never clears prior value.
 feature={}
 for i,label in ((1,"oi"),(2,"fund")):
  seq=[];prev=object()
  for row in tick:
   value=row[i]
   if value is None:continue
   if value!=prev:seq.append((row[0],value));prev=value
  feature[label]=seq
  counts[label+"_distinct_updates"]=len(seq)
 # Trades sampled only: NO inference about full-day trade volume.
 sample=[];last_raw=None
 for row in source(e,s,d,"trades"):
  if counts["trades_sample_rows"]>=12000:break
  counts["trades_sample_rows"]+=1
  try:t=ts(row.get("timestamp"))
  except Exception:counts["trade_bad_ts"]+=1;continue
  if last_raw is not None and t<last_raw:counts["trade_reversals"]+=1
  last_raw=t
  if not(start<=t<end):counts["trades_outside"]+=1;continue
  side=(row.get("side") or "").lower()
  if side in ("buy","sell"):counts["trade_"+side]+=1
  else:counts["trade_other"]+=1
  sample.append((t,side))
 # Use last *completed* 5m bucket as-of each cutoff, not future rows.
 output=[]
 for minute in range(5,1441,5):
  cutoff=start+dt.timedelta(minutes=minute)
  rec={"exchange":e,"symbol":s,"day":d,"cutoff_utc":cutoff.isoformat(),"ticker_rows_in_day":len(tick),"trades_sample_only":True}
  for label in ("oi","fund"):
   seq=feature[label];times=[x[0] for x in seq];idx=bisect.bisect_left(times,cutoff)-1
   if idx>=0:
    age=(cutoff-seq[idx][0]).total_seconds()
    rec[label+"_age_seconds"]=round(age,3);rec[label+"_available_eventtime"]=age<=3600
    rec[label+"_value"]=seq[idx][1] if age<=3600 else ""
   else:
    rec[label+"_age_seconds"]="";rec[label+"_available_eventtime"]=False;rec[label+"_value"]=""
  output.append(rec)
 return counts,output
summary=[];allrows=[]
for e,s,d in CASES:
 try:
  counts,rows=audit(e,s,d)
  r={"exchange":e,"symbol":s,"day":d,"status":"AUDITED","note":"Event-time only, not proven receipt-time; no prior-day warmup; 60min max staleness; sample trades cannot supply full-day flow",**counts}
  r["oi_5m_coverage"]=sum(x["oi_available_eventtime"] for x in rows)
  r["fund_5m_coverage"]=sum(x["fund_available_eventtime"] for x in rows)
  summary.append(r);allrows+=rows
  print(e,s,r["oi_5m_coverage"],r["fund_5m_coverage"],flush=True)
 except Exception as ex:
  summary.append({"exchange":e,"symbol":s,"day":d,"status":"ERROR","note":str(ex)[:300]});print("ERROR",e,s,ex,flush=True)
def save(path,rows):
 cols=list(dict.fromkeys(k for r in rows for k in r))
 with (O/path).open("w",newline="") as f:
  w=csv.DictWriter(f,fieldnames=cols);w.writeheader();w.writerows(rows)
save("alignment_summary.csv",summary);save("five_minute_asof.csv",allrows)
(O/"manifest.json").write_text(json.dumps({"version":"v2.8","status_counts":dict(collections.Counter(x["status"] for x in summary)),"point_in_time_rule":"strict event timestamp < 5m cutoff, never future; <=3600s age","limits":["Event timestamp is NOT observed/publication timestamp","No prior-day warmup, first intervals may lack values","Only 12000 trade rows per source; no full-day taker flow","Tardis historical ticker not automatically original Detector OI or funding feature","No signals, fills, profitability or trading changes"]},indent=2))
