#!/usr/bin/env python3
"""SHADOW v2.4: Tardis public first-of-month archive availability probe.
HEAD and bounded GET only; never treats file availability as validated candle or signal data."""
import csv,json,urllib.request,urllib.error,time,datetime as dt
from pathlib import Path
from collections import Counter
out=Path("detector_tardis_samples_v24_results");out.mkdir(exist_ok=True)
# Representative instruments/dates, including a young token after listing.
checks=[
 ("binance-futures","trades","BTCUSDT","2021-06-01"),
 ("binance-futures","derivative_ticker","BTCUSDT","2021-06-01"),
 ("binance-futures","trades","ETHUSDT","2024-06-01"),
 ("binance-futures","derivative_ticker","ETHUSDT","2024-06-01"),
 ("bybit","trades","BTCUSDT","2021-06-01"),
 ("bybit","derivative_ticker","BTCUSDT","2021-06-01"),
 ("bybit","trades","SOLUSDT","2024-06-01"),
 ("bybit","derivative_ticker","SOLUSDT","2024-06-01"),
 ("okex-swap","trades","BTC-USDT-SWAP","2024-06-01"),
 ("okex-swap","derivative_ticker","BTC-USDT-SWAP","2024-06-01"),
 ("binance","trades","BTCUSDT","2021-06-01"),
 ("binance","trades","SOLUSDT","2024-06-01"),
 ("bybit","trades","HYPEUSDT","2026-09-01"),
]
def req(url,method):
 for attempt in range(2):
  try:
   headers={"User-Agent":"detector-shadow-archive-probe/2.4"}
   if method=="GET":headers["Range"]="bytes=0-2047"
   with urllib.request.urlopen(urllib.request.Request(url,method=method,headers=headers),timeout=20) as r:
    body=r.read(2048) if method=="GET" else b""
    return r.status,r.headers.get("Content-Length",""),r.headers.get("Content-Range",""),body[:20].hex(),""
  except urllib.error.HTTPError as e:return e.code,"","","",e.read(160).decode(errors="replace")
  except Exception as e:
   if attempt:return "NETWORK_ERROR","","","",str(e)[:140]
   time.sleep(1)
rows=[]
for exchange,kind,symbol,day in checks:
 y,m,d=day.split("-")
 url=f"https://datasets.tardis.dev/v1/{exchange}/{kind}/{y}/{m}/{d}/{symbol}.csv.gz"
 http,size,range_header,magic,error=req(url,"HEAD")
 # GET only when HEAD reports plausible existence; bound read avoids large archives.
 get_http,get_size,get_range,get_magic,get_error=("NOT_RUN","","","","")
 if http==200:
  get_http,get_size,get_range,get_magic,get_error=req(url,"GET")
 status=("HEAD_AVAILABLE" if http==200 else "NOT_FOUND" if http==404 else "ACCESS_DENIED" if http in (401,403) else "UNKNOWN")
 if http==200 and get_http not in (200,206):status="HEAD_ONLY_GET_FAILED"
 rows.append(dict(exchange=exchange,data_type=kind,symbol=symbol,day=day,url=url,head_http=http,get_http=get_http,status=status,content_length=size,content_range=get_range,first_bytes_hex=get_magic,error=(error or get_error)[:150]))
 print(exchange,kind,symbol,day,status,flush=True)
with (out/"tardis_archive_probes.csv").open("w",newline="") as f:
 w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
manifest={"stage":"v2.4","probe_count":len(rows),"statuses":dict(Counter(r["status"] for r in rows)),
 "scope":"Representative public first-day-of-month archive URL checks only",
 "important":["No complete CSV downloaded or validated","No assumption that derivative_ticker fields contain OI/funding until actual schema inspection","HEAD success does not establish multi-year coverage","No exact historical Detector replay or generated trading signals","No live changes"]}
(out/"manifest.json").write_text(json.dumps(manifest,indent=2))
