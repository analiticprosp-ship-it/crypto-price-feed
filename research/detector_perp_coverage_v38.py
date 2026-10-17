#!/usr/bin/env python3
"""v3.8: perpetual historical coverage reconnaissance (not spot, no fake backfill).
Tardis free sample availability is probed monthly; only HEAD/streamed GET status,
no claim of full paid archives. Produces a coverage matrix and explicit blockers."""
import csv,json,urllib.request,urllib.error,datetime as dt,concurrent.futures,collections
from pathlib import Path
O=Path("detector_perp_coverage_v38_results");O.mkdir(exist_ok=True)
CASES=[("binance-futures","BTCUSDT","2019-01"),("binance-futures","ETHUSDT","2019-12"),("bybit","BTCUSDT","2020-01"),("bybit","SOLUSDT","2020-08"),("okex-swap","BTC-USDT-SWAP","2019-01"),("okex-swap","SOL-USDT-SWAP","2020-08"),("okex-swap","HYPE-USDT-SWAP","2025-01"),("bybit","HYPEUSDT","2025-01"),("binance-futures","BNBUSDT","2020-01"),("binance-futures","LINKUSDT","2020-01"),("binance-futures","XRPUSDT","2020-01"),("binance-futures","AVAXUSDT","2020-09"),("binance-futures","AAVEUSDT","2020-10"),("binance-futures","INJUSDT","2020-10"),("binance-futures","NEARUSDT","2020-10"),("binance-futures","LDOUSDT","2022-05"),("binance-futures","APTUSDT","2022-10"),("binance-futures","SUIUSDT","2023-05"),("binance-futures","ENAUSDT","2024-04")]
END=dt.date(2026,10,1)
def months(start):
 y,m=map(int,start.split("-"))
 while (y,m)<=(END.year,END.month):
  yield y,m
  m+=1
  if m==13:y,m=y+1,1
def check(item):
 ex,sym,y,m=item;day=f"{y:04d}-{m:02d}-01";url=f"https://datasets.tardis.dev/v1/{ex}/trades/{y:04d}/{m:02d}/01/{sym}.csv.gz"
 req=urllib.request.Request(url,method="HEAD",headers={"User-Agent":"detector-perpetual-coverage-research-v38"})
 try:
  with urllib.request.urlopen(req,timeout=12) as r:
   status=r.status;size=r.headers.get("Content-Length","")
 except urllib.error.HTTPError as e:status=e.code;size=""
 except Exception as e:return {"exchange":ex,"symbol":sym,"date":day,"status":"ERROR","error":type(e).__name__}
 return {"exchange":ex,"symbol":sym,"date":day,"status":str(status),"content_length":size}
jobs=[(ex,sym,y,m) for ex,sym,start in CASES for y,m in months(start)]
rows=[]
with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
 for row in pool.map(check,jobs):rows.append(row)
with (O/"monthly_first_day_samples.csv").open("w",newline="") as f:
 keys=["exchange","symbol","date","status","content_length","error"];w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(rows)
summary=[]
for ex,sym,start in CASES:
 x=[r for r in rows if r["exchange"]==ex and r["symbol"]==sym];found=[r["date"] for r in x if r["status"]=="200"]
 summary.append({"exchange":ex,"symbol":sym,"first_probe_month":start,"months_probed":len(x),"sample_day_http_200":len(found),"first_available_sample_day":min(found) if found else "","last_available_sample_day":max(found) if found else "","coverage_gate":"NOT_FULL_HISTORY","warning":"Only 1st-day free sample HTTP HEAD; does not imply full monthly access or full trading history"})
with (O/"coverage_summary.csv").open("w",newline="") as f:
 w=csv.DictWriter(f,fieldnames=summary[0].keys());w.writeheader();w.writerows(summary)
(O/"manifest.json").write_text(json.dumps({"version":"3.8","probe_count":len(rows),"symbols":len(CASES),"status_counts":dict(collections.Counter(r["status"] for r in rows)),"research_gate":"DISCOVERY_ONLY","no_false_claims":["A monthly first-day sample is NOT a month of historical trades","A 200 HEAD does NOT confirm complete 24h file integrity","No trade side/unit parity with native taker aggregates","No historical OI/funding parity","No 5-7 year backtest, no P&L or win rate","Listing month not inferred from first sample without primary venue evidence"],"next":"Identify complete historical perpetual OHLCV and taker-volume sources with as-of provenance; license/cost assessment before replay","no_live_changes":True},indent=2))
print(json.dumps({"probes":len(rows),"statuses":dict(collections.Counter(r["status"] for r in rows))}))
