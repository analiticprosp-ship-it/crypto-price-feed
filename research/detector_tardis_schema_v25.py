#!/usr/bin/env python3
"""SHADOW v2.5: catalog-grounded Tardis free sample CSV inspection.
Only first-day-of-month samples; never fabricate absent OI/funding/flow."""
import csv,json,urllib.request,urllib.error,gzip,io,time
from pathlib import Path
from collections import Counter
OUT=Path("detector_tardis_schema_v25_results");OUT.mkdir(exist_ok=True)
EXCHANGES=["binance-futures","bybit","okex-swap","binance"]
TARGETS=[("binance-futures","BTCUSDT","2021-06-01"),("bybit","BTCUSDT","2021-06-01"),("okex-swap","BTC-USDT-SWAP","2021-06-01"),("binance","BTCUSDT","2021-06-01"),("okex-swap","SOL-USDT-SWAP","2024-06-01"),("bybit","SOLUSDT","2024-06-01"),("okex-swap","HYPE-USDT-SWAP","2026-09-01")]
def request(url,maxbytes=1200000):
 try:
  req=urllib.request.Request(url,headers={"User-Agent":"detector-shadow-sample-schema/2.5","Accept-Encoding":"identity"})
  with urllib.request.urlopen(req,timeout=30) as r:return r.status,r.read(maxbytes+1),dict(r.headers),""
 except urllib.error.HTTPError as e:return e.code,e.read(400),{},"HTTP_ERROR"
 except Exception as e:return "NETWORK_ERROR",b"",{},str(e)[:150]
catalog={}
for exchange in EXCHANGES:
 http,body,headers,error=request("https://api.tardis.dev/v1/exchanges/"+exchange,maxbytes=5000000)
 if http==200:
  try:catalog[exchange]=json.loads(body)
  except Exception as e:print("catalog parse",exchange,e)
 else:print("catalog failed",exchange,http,error)
rows=[]
for exchange,symbol,day in TARGETS:
 datasets=catalog.get(exchange,{}).get("datasets",{}).get("symbols",[])
 entry=next((x for x in datasets if x.get("id")==symbol),None)
 for kind in ("trades","derivative_ticker"):
  r=dict(exchange=exchange,symbol=symbol,day=day,kind=kind,catalog_symbol=bool(entry),catalog_type=kind in (entry or {}).get("dataTypes",[]),http="NOT_RUN",status="NOT_RUN",header="",sample_rows=0,nonempty_fields="",error="",url="")
  if not entry:r["status"]="NOT_IN_CATALOG";rows.append(r);continue
  if kind not in entry.get("dataTypes",[]):r["status"]="TYPE_NOT_IN_CATALOG";rows.append(r);continue
  if day+"T00:00:00.000Z"<entry.get("availableSince",""):r["status"]="BEFORE_LISTING";rows.append(r);continue
  y,m,d=day.split("-");url=f"https://datasets.tardis.dev/v1/{exchange}/{kind}/{y}/{m}/{d}/{symbol}.csv.gz";r["url"]=url
  http,body,headers,error=request(url);r["http"]=http;r["error"]=error
  if http not in (200,206):r["status"]="HTTP_ERROR";rows.append(r);print(exchange,kind,http,flush=True);continue
  # Bounded read: do not fully download large trades files.
  try:
   with gzip.GzipFile(fileobj=io.BytesIO(body)) as gz:
    raw=gz.read(150000)
   lines=raw.decode("utf-8-sig",errors="replace").splitlines()
   reader=csv.DictReader(lines)
   sample=list(reader)[:20]
   r["header"]="|".join(reader.fieldnames or [])
   r["sample_rows"]=len(sample)
   r["nonempty_fields"]="|".join(k for k in (reader.fieldnames or []) if any(row.get(k) not in ("",None) for row in sample))
   r["status"]="SAMPLE_PARSED" if sample else "HEADER_ONLY"
  except (EOFError,OSError,ValueError) as e:
   # A truncated compressed response may still have a valid CSV header; never claim complete validation.
   try:
    decompressor=gzip.decompress(body);r["header"]=decompressor.decode(errors="replace").splitlines()[0]
   except Exception:pass
   r["status"]="BOUNDED_GZIP_INCOMPLETE";r["error"]=str(e)[:150]
  rows.append(r);print(exchange,kind,r["status"],r["sample_rows"],flush=True)
with (OUT/"sample_schema_checks.csv").open("w",newline="") as f:
 w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
manifest={"stage":"v2.5","status_counts":dict(Counter(r["status"] for r in rows)),"sample_rows_only":True,"no_full_archive_integrity":True,"no_signal_replay":True,"no_live_changes":True,"warnings":["Bounded gzip reads may fail on large archives; this is not proof data absent","Catalog datasets are provider claims, not confirmed historical field availability","First-day-of-month samples do not establish continuous coverage"]}
(OUT/"manifest.json").write_text(json.dumps(manifest,indent=2))
