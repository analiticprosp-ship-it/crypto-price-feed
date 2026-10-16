#!/usr/bin/env python3
"""Stage 1 historical source coverage: factual public Binance spot monthly 5m archives.
No historical detector signals are reconstructed by this script."""
import csv,json,urllib.request,urllib.error,datetime as dt,time
from pathlib import Path
from collections import defaultdict
out=Path("detector_historical_coverage_v20_results");out.mkdir(exist_ok=True)
events=json.loads(Path("detector-signal-events.json").read_text()).get("events",[])
symbols=sorted({e.get("symbol","") for e in events if e.get("symbol")})
# Monthly probes: only mark months actually checked, never infer gaps are filled.
months=[(y,m) for y in range(2019,2027) for m in range(1,13) if (y,m)<=(2026,10)]
rows=[]
for sym in symbols:
 for year,month in months:
  pair=sym.replace("-","").replace("/","")+"USDT"
  url=f"https://data.binance.vision/data/spot/monthly/klines/{pair}/5m/{pair}-5m-{year}-{month:02d}.zip"
  status="UNKNOWN";size=""
  for attempt in range(3):
   try:
    req=urllib.request.Request(url,method="HEAD",headers={"User-Agent":"research-coverage-audit/2.0"})
    with urllib.request.urlopen(req,timeout=15) as res:
     status="AVAILABLE" if res.status==200 else "HTTP_"+str(res.status)
     size=res.headers.get("Content-Length","")
    break
   except urllib.error.HTTPError as ex:
    status="NOT_FOUND" if ex.code==404 else "HTTP_"+str(ex.code)
    if ex.code==404:break
   except Exception as ex:status="ERROR_"+type(ex).__name__
   time.sleep(1+attempt)
  rows.append({"symbol":sym,"pair":pair,"year":year,"month":month,"status":status,"content_length_bytes":size,"source_url":url})
  if len(rows)%50==0:print("probed",len(rows),flush=True)
with (out/"monthly_spot_5m_coverage.csv").open("w",newline="") as f:
 w=csv.DictWriter(f,fieldnames=list(rows[0]) if rows else ["symbol"]);w.writeheader();w.writerows(rows)
by=defaultdict(list)
for r in rows:
 if r["status"]=="AVAILABLE":by[r["symbol"]].append(f'{r["year"]}-{r["month"]:02d}')
summary=[]
for sym in symbols:
 dates=sorted(by[sym])
 summary.append({"symbol":sym,"available_months":len(dates),"earliest_verified":dates[0] if dates else "",
 "latest_verified":dates[-1] if dates else "","unavailable_or_unverified_months":sum(r["symbol"]==sym and r["status"]!="AVAILABLE" for r in rows)})
with (out/"coverage_summary.csv").open("w",newline="") as f:
 w=csv.DictWriter(f,fieldnames=list(summary[0]) if summary else ["symbol"]);w.writeheader();w.writerows(summary)
manifest={"stage":"HISTORICAL_DATA_COVERAGE_ONLY","mode":"SHADOW_RESEARCH","symbols":symbols,
 "checked_months_per_symbol":len(months),"coverage_source":"Binance public spot monthly 5m archives",
 "status_counts":{s:sum(r["status"]==s for r in rows) for s in sorted({r["status"] for r in rows})},
 "limitations":["Availability via HTTP HEAD is not verification of ZIP integrity or candle continuity",
 "Exchange spot listings differ from original OKX SWAP Detector sources",
 "OHLCV availability does not imply OI, taker flow, funding, BTC RS or exact Detector replay availability",
 "No signals, performance, fills, historical timestamps or market regimes reconstructed",
 "No lookahead, no invented pre-listing data, no changes to live Detector/Futures"]}
(out/"manifest.json").write_text(json.dumps(manifest,indent=2))
print(json.dumps(manifest,indent=2))
