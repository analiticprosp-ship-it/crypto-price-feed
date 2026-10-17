#!/usr/bin/env python3
"""v3.8.1: validate Tardis historical free samples with streamed GET, not HEAD.
Known-good controls first; small batches, retries; no paid-history inference."""
import csv,json,time,urllib.request,urllib.error,datetime as dt,collections
from pathlib import Path
O=Path("detector_perp_coverage_v381_results");O.mkdir(exist_ok=True)
CONTROLS=[("binance-futures","BTCUSDT","2021-06-01"),("bybit","BTCUSDT","2021-06-01"),("okex-swap","BTC-USDT-SWAP","2021-06-01"),("bybit","SOLUSDT","2024-06-01"),("okex-swap","SOL-USDT-SWAP","2024-06-01"),("okex-swap","HYPE-USDT-SWAP","2026-09-01")]
PROBES=[("binance-futures","BTCUSDT","2020-01-01"),("binance-futures","BTCUSDT","2022-01-01"),("binance-futures","BTCUSDT","2024-01-01"),("binance-futures","BTCUSDT","2026-01-01"),("bybit","SOLUSDT","2021-01-01"),("bybit","SOLUSDT","2022-01-01"),("bybit","SOLUSDT","2023-01-01"),("bybit","SOLUSDT","2025-01-01"),("okex-swap","BTC-USDT-SWAP","2020-01-01"),("okex-swap","BTC-USDT-SWAP","2022-01-01"),("okex-swap","BTC-USDT-SWAP","2024-01-01"),("okex-swap","BTC-USDT-SWAP","2026-01-01"),("okex-swap","HYPE-USDT-SWAP","2025-01-01"),("okex-swap","HYPE-USDT-SWAP","2026-01-01"),("bybit","HYPEUSDT","2025-01-01"),("bybit","HYPEUSDT","2026-01-01")]
def get_probe(ex,sym,day):
 y,m,d=day.split("-");url=f"https://datasets.tardis.dev/v1/{ex}/trades/{y}/{m}/{d}/{sym}.csv.gz"
 for attempt in range(2):
  try:
   req=urllib.request.Request(url,headers={"User-Agent":"detector-historical-coverage-v381","Accept":"application/octet-stream"})
   with urllib.request.urlopen(req,timeout=25) as response:
    chunk=response.read(1024)
    return {"exchange":ex,"symbol":sym,"date":day,"status":"GET_200_STREAM","http":response.status,"bytes_read":len(chunk),"gzip_magic":chunk[:2]==b"\\x1f\\x8b","content_type":response.headers.get("Content-Type",""),"attempts":attempt+1}
  except urllib.error.HTTPError as e:
   if e.code in (401,403,404,451):return {"exchange":ex,"symbol":sym,"date":day,"status":"HTTP_"+str(e.code),"attempts":attempt+1}
   failure="HTTP_"+str(e.code)
  except Exception as e:failure=type(e).__name__
  time.sleep(1+attempt)
 return {"exchange":ex,"symbol":sym,"date":day,"status":"NETWORK_"+failure,"attempts":2}
rows=[]
for i,item in enumerate(CONTROLS):
 r=get_probe(*item);r["group"]="known_good_control";rows.append(r);print("CONTROL",i+1,r["status"],flush=True)
controls_ok=sum(x["status"]=="GET_200_STREAM" and x.get("gzip_magic") for x in rows)
if controls_ok>=4:
 for i,item in enumerate(PROBES):
  r=get_probe(*item);r["group"]="limited_month_probe";rows.append(r);print("PROBE",i+1,r["status"],flush=True)
else:print("STOP: fewer than 4 known-good controls passed; avoid false absence inference",flush=True)
with (O/"get_coverage_probe.csv").open("w",newline="") as f:
 keys=list(dict.fromkeys(k for x in rows for k in x));w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(rows)
(O/"manifest.json").write_text(json.dumps({"version":"v3.8.1","controls_passed":controls_ok,"controls_total":len(CONTROLS),"probes_attempted":len(rows)-len(CONTROLS),"status_counts":dict(collections.Counter(x["status"] for x in rows)),"coverage_gate":"PROBE_ONLY" if controls_ok>=4 else "CONTROL_FAILURE","semantics":["GET 200 and gzip magic verify sample stream accessible, NOT full-day completeness","404 on monthly first-day free sample does NOT prove no full historical dataset","Network timeout is NOT evidence of absence","Paid historical availability and licensing not determined","No spot substitution, no signals, no live changes"]},indent=2))
