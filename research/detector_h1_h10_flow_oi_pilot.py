#!/usr/bin/env python3
"""Research-only OI notional plausibility and aggTrades archive accessibility pilot."""
import collections,csv,datetime as dt,io,json,math,pathlib,statistics,urllib.request,urllib.error,zipfile
root=pathlib.Path("detector_h1_h10_masked_sorted")
out=pathlib.Path("detector_h1_h10_flow_oi_pilot");out.mkdir(exist_ok=True)
report={"method":"Compare implied USD/base (OI value / OI quantity) with last CLOSED 1h perp price, not an exact contemporaneous benchmark. Archive metadata only for aggTrades; no claim that flow was downloaded.","oi":{},"trades":[]}
for sym in ("BTCUSDT","ETHUSDT","SOLUSDT"):
 vals=[];n=collections.Counter();examples=[]
 with (root/f"{sym}_research_5m.csv").open(newline="") as f:
  for r in csv.DictReader(f):
   try:
    qty=float(r["sum_open_interest"]);notional=float(r["sum_open_interest_value"]);close=float(r["perp_1h_close"])
    if not (math.isfinite(qty) and math.isfinite(notional) and math.isfinite(close) and qty>0 and close>0 and notional>=0):raise ValueError()
    implied=notional/qty;relative=implied/close-1
    vals.append(relative);n["valid"]+=1
    if abs(relative)>0.10 and len(examples)<10:examples.append({"timestamp":r["timestamp_utc"],"implied_price":round(implied,4),"prior_closed_hour_price":close,"deviation_pct":round(relative*100,3)})
   except (ValueError,TypeError,ZeroDivisionError):n["not_comparable"]+=1
 vals.sort()
 report["oi"][sym]={"comparisons":len(vals),"not_comparable":n["not_comparable"],"median_deviation_pct":round(statistics.median(vals)*100,4) if vals else None,"p01_deviation_pct":round(vals[int((len(vals)-1)*.01)]*100,4) if vals else None,"p99_deviation_pct":round(vals[int((len(vals)-1)*.99)]*100,4) if vals else None,"deviation_over_10pct":sum(abs(v)>.10 for v in vals),"examples_over_10pct":examples,"semantic_status":"PLAUSIBILITY_ONLY_NOT_PROVEN"}
 print("OI",sym,json.dumps(report["oi"][sym]),flush=True)
for day in ("2024-01-01","2026-10-01"):
 for market in ("spot","futures"):
  for sym in ("BTCUSDT","ETHUSDT","SOLUSDT"):
   prefix="data/spot/daily/aggTrades" if market=="spot" else "data/futures/um/daily/aggTrades"
   url=f"https://data.binance.vision/{prefix}/{sym}/{sym}-aggTrades-{day}.zip"
   item={"market":market,"symbol":sym,"date":day,"url":url}
   try:
    req=urllib.request.Request(url,method="HEAD",headers={"User-Agent":"Detector-Research/1.0"})
    with urllib.request.urlopen(req,timeout=25) as resp:
     item["status"]="AVAILABLE_METADATA_ONLY" if resp.status==200 else "HTTP_"+str(resp.status)
     item["size_bytes"]=int(resp.headers.get("Content-Length","0"))
   except Exception as e:item["status"]="ERROR";item["error"]=str(e)[:180]
   report["trades"].append(item);print("TRADES",json.dumps(item),flush=True)
(out/"pilot_report.json").write_text(json.dumps(report,indent=2,ensure_ascii=False))
print("SUMMARY",json.dumps({"oi_symbols":len(report["oi"]),"trade_archive_head_ok":sum(x["status"]=="AVAILABLE_METADATA_ONLY" for x in report["trades"]),"trade_archive_checks":len(report["trades"])}),flush=True)
