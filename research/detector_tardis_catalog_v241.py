#!/usr/bin/env python3
"""SHADOW v2.4.1: discover Tardis catalog before probing archive paths.
No trade signals. Never treat guessed URL 404 as proof of absent historical data."""
import json,csv,time,urllib.request,urllib.error,urllib.parse
from pathlib import Path
from collections import Counter
OUT=Path("detector_tardis_catalog_v241_results");OUT.mkdir(exist_ok=True)
BASE="https://api.tardis.dev/v1/exchanges"
def request(url):
 for attempt in range(2):
  try:
   with urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"detector-shadow-catalog/2.4.1","Accept":"application/json"}),timeout=22) as r:
    return {"http":r.status,"body":r.read(4000000).decode("utf-8",errors="replace"),"error":""}
  except urllib.error.HTTPError as e:
   return {"http":e.code,"body":e.read(1500).decode(errors="replace"),"error":"HTTP_ERROR"}
  except Exception as e:
   if attempt:return {"http":"NETWORK_ERROR","body":"","error":str(e)[:200]}
   time.sleep(1)
targets=["binance","binance-futures","bybit","okex","okex-swap"]
rows=[];raw={}
for exchange in ["ALL"]+targets:
 url=BASE if exchange=="ALL" else BASE+"/"+urllib.parse.quote(exchange)
 result=request(url);raw[exchange]=result
 parsed=None
 if result["http"]==200:
  try:parsed=json.loads(result["body"])
  except Exception:pass
 def walk(x):
  if isinstance(x,dict):
   for k,v in x.items():
    if k in ("id","name","symbol","type","availableSince","availableTo","dataTypes","datasets","exchange","exchangeId","firstAvailableDate","lastAvailableDate"):
     if isinstance(v,(str,int,float)):yield str(k)+":"+str(v)
     elif isinstance(v,list) and k in ("dataTypes","datasets"):yield str(k)+":"+str(v)[:180]
    yield from walk(v)
  elif isinstance(x,list):
   for v in x:yield from walk(v)
 details=list(walk(parsed)) if parsed is not None else []
 rows.append(dict(exchange=exchange,url=url,http=result["http"],json_valid=parsed is not None,top_level_type=type(parsed).__name__ if parsed is not None else "",top_level_keys=",".join(list(parsed)[:30]) if isinstance(parsed,dict) else "",catalog_mentions=" | ".join(details[:120])[:9000],error=result["error"] or result["body"][:200] if result["http"]!=200 else ""))
 print(exchange,result["http"],"JSON" if parsed is not None else "NOT_JSON",flush=True)
 # Preserve raw catalog JSON, no secret values in response requested.
 if parsed is not None:(OUT/("catalog_"+exchange.replace("-","_")+".json")).write_text(json.dumps(parsed,ensure_ascii=False,indent=2)[:2000000])
with (OUT/"catalog_status.csv").open("w",newline="") as f:
 w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
(OUT/"manifest.json").write_text(json.dumps({"stage":"v2.4.1","statuses":dict(Counter(str(r["http"]) for r in rows)),"catalog_first":True,"sample_downloads":False,"exact_replay":False,"notes":["No guessed archive URL probes; inspect provider catalog first","Catalog availability is not proof of archived CSV contents","If access blocked, record HTTP status without assuming archives absent","No changes to live Detector/Futures/P&L"]},indent=2))
