#!/usr/bin/env python3
"""Detector v3.9: bounded continuity and full-history-access audit.
No historical data purchased, no trading signals, no inference from sample URL to full archive."""
import csv,json,urllib.request,urllib.error,datetime as dt,collections,time,gzip,io
from pathlib import Path
OUT=Path("detector_perp_continuity_v39_results");OUT.mkdir(exist_ok=True)
CASES=[("binance-futures","BTCUSDT",2020,2026),("okex-swap","BTC-USDT-SWAP",2020,2026),("bybit","SOLUSDT",2022,2026),("bybit","HYPEUSDT",2025,2026),("okex-swap","HYPE-USDT-SWAP",2025,2026)]
# Quarterly anchors: first day of quarter. Check adjacent day and mid-month for bounded continuity.
DATES=[]
for ex,sym,start,end in CASES:
 for year in range(start,end+1):
  for month in (1,4,7,10):
   if year==2026 and month>10:continue
   DATES.append((ex,sym,dt.date(year,month,1),"quarter_anchor"))
# Bound to recent and older anchors evenly (avoid excessive requests).
anchors=[]
for ex,sym,_,_ in CASES:
 group=[x for x in DATES if x[0]==ex and x[1]==sym]
 if len(group)>14:
  idx=sorted(set(round(i*(len(group)-1)/13) for i in range(14)))
  group=[group[i] for i in idx]
 anchors+=group
tasks=[]
for ex,sym,date,kind in anchors:
 for offset,label in [(0,"anchor"),(1,"adjacent_day"),(14,"mid_month")]:
  day=date+dt.timedelta(days=offset)
  if day>dt.date(2026,10,17):continue
  tasks.append((ex,sym,day,label))
def probe(ex,sym,day,label):
 url=f"https://datasets.tardis.dev/v1/{ex}/trades/{day:%Y/%m/%d}/{sym}.csv.gz"
 for attempt in range(2):
  try:
   req=urllib.request.Request(url,headers={"User-Agent":"detector-perp-continuity-v39","Accept":"*/*"})
   with urllib.request.urlopen(req,timeout=22) as r:
    data=r.read(4096);ctype=r.headers.get("Content-Type","")
    # Some endpoints transparently decompress; 200 + CSV header or gzip magic counts as sample accessible.
    valid=data.startswith(b"\\x1f\\x8b") or b"exchange" in data[:300].lower() or b"timestamp" in data[:300].lower()
    return {"exchange":ex,"symbol":sym,"date":day.isoformat(),"probe_type":label,"status":"SAMPLE_ACCESSIBLE" if valid else "HTTP_200_UNKNOWN_FORMAT","http":r.status,"content_type":ctype,"sample_bytes":len(data),"attempts":attempt+1}
  except urllib.error.HTTPError as e:
   if e.code in (400,401,403,404,451):
    return {"exchange":ex,"symbol":sym,"date":day.isoformat(),"probe_type":label,"status":"HTTP_"+str(e.code),"attempts":attempt+1}
   err="HTTP_"+str(e.code)
  except Exception as e:err=type(e).__name__
  time.sleep(0.5)
 return {"exchange":ex,"symbol":sym,"date":day.isoformat(),"probe_type":label,"status":"NETWORK_"+err,"attempts":2}
rows=[]
for i,task in enumerate(tasks):
 r=probe(*task);rows.append(r)
 if i%12==0:print(i+1,"/",len(tasks),r["status"],flush=True)
def write(name,items):
 fields=list(dict.fromkeys(k for x in items for k in x))
 with (OUT/name).open("w",newline="") as f:
  w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(items)
write("sample_day_continuity_probes.csv",rows)
summ=[]
for ex,sym,_,_ in CASES:
 x=[r for r in rows if r["exchange"]==ex and r["symbol"]==sym]
 for label in ("anchor","adjacent_day","mid_month"):
  y=[r for r in x if r["probe_type"]==label]
  summ.append({"exchange":ex,"symbol":sym,"probe_type":label,"checked":len(y),"sample_accessible":sum(r["status"]=="SAMPLE_ACCESSIBLE" for r in y),"http_400":sum(r["status"]=="HTTP_400" for r in y),"http_404":sum(r["status"]=="HTTP_404" for r in y),"network_or_other":sum(r["status"] not in ("SAMPLE_ACCESSIBLE","HTTP_400","HTTP_404") for r in y),"full_archive_access":"NOT_TESTED","complete_multiyear_history":"NOT_PROVEN"})
write("continuity_summary.csv",summ)
(OUT/"manifest.json").write_text(json.dumps({"version":"3.9","probes":len(rows),"status_counts":dict(collections.Counter(r["status"] for r in rows)),"gate":"DISCOVERY_ONLY","limitations":["Sample-day GET cannot prove full monthly/day continuity or paid archive availability","HTTP 400/404 do not establish no historical exchange listing","Only first 4096 bytes read; full-day integrity not checked","No authentication or purchase; licensing and cost not confirmed","No historical parity of perpetual OHLCV and taker aggregate","No backtest, P&L, or trading signals"],"next":"Use official Tardis catalog/pricing or authenticated access for continuous historical dataset; independently validate full-day and month coverage","live_system_unchanged":True},indent=2))
print("DONE",len(rows),flush=True)
