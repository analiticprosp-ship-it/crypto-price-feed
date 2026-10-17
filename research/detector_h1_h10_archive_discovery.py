#!/usr/bin/env python3
"""Read-only historical availability probe for Detector H1-H10. No trading."""
import csv, datetime as dt, hashlib, json, os, pathlib, urllib.request, urllib.error
ROOT=pathlib.Path("detector_h1_h10_inventory");ROOT.mkdir(exist_ok=True)
symbols=["BTCUSDT","ETHUSDT","SOLUSDT"]
sources=[
 ("binance_spot","https://data.binance.vision/data/spot/monthly/klines/{s}/1m/{s}-1m-{ym}.zip"),
 ("binance_perp","https://data.binance.vision/data/futures/um/monthly/klines/{s}/1m/{s}-1m-{ym}.zip"),
 ("binance_spot_trades","https://data.binance.vision/data/spot/monthly/trades/{s}/{s}-trades-{ym}.zip"),
 ("binance_perp_trades","https://data.binance.vision/data/futures/um/monthly/trades/{s}/{s}-trades-{ym}.zip"),
]
# HEAD-only existence and metadata checks; never download large archives in discovery stage.
months=["2024-01","2025-01","2026-01","2026-09"]
rows=[]
for venue,tmpl in sources:
 for sym in symbols:
  for ym in months:
   url=tmpl.format(s=sym,ym=ym)
   status="UNKNOWN";size="";modified="";error=""
   try:
    req=urllib.request.Request(url,method="HEAD",headers={"User-Agent":"Detector-H1-H10-research/1.0"})
    with urllib.request.urlopen(req,timeout=20) as response:
     status="AVAILABLE" if response.status==200 else f"HTTP_{response.status}"
     size=response.headers.get("Content-Length","")
     modified=response.headers.get("Last-Modified","")
   except urllib.error.HTTPError as e: status=f"HTTP_{e.code}";error=str(e)
   except Exception as e: status="UNVERIFIED";error=repr(e)[:200]
   rows.append({"source":venue,"symbol":sym,"month":ym,"status":status,"bytes":size,"last_modified":modified,"url":url,"error":error})
with (ROOT/"inventory.csv").open("w",newline="") as f:
 w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
report={"generated_at_utc":dt.datetime.now(dt.timezone.utc).isoformat(),"mode":"HEAD_ONLY_NO_DATA_DOWNLOADED","count":len(rows),"available":sum(x["status"]=="AVAILABLE" for x in rows),"rows":rows}
(ROOT/"inventory.json").write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps({"count":len(rows),"available":report["available"],"status":"DISCOVERY_ONLY"}))
