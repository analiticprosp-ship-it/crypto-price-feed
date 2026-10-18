#!/usr/bin/env python3
"""Metadata and small gzip-prefix probe of free first-of-month Tardis Binance OI.

One-shot only: no billing, API keys, unrestricted datasets, or historical
causality claims. CSV derivative_ticker represents Tardis-captured REST OI
snapshots, not necessarily Binance 5-minute archive series.
"""
import datetime as dt,hashlib,json,os,urllib.error,urllib.request,zlib
from pathlib import Path
OUT=Path("detector_tardis_oi_probe");OUT.mkdir(parents=True,exist_ok=True)
LIMIT=16_384
def request(url,limit=LIMIT):
 req=urllib.request.Request(url,headers={"User-Agent":"Detector-H1H10-Research/1.0","Accept":"*/*"})
 try:
  with urllib.request.urlopen(req,timeout=16) as resp:
   return {"http":resp.status,"data":resp.read(limit+1),"content_type":resp.headers.get("Content-Type"),
           "content_length":resp.headers.get("Content-Length")}
 except urllib.error.HTTPError as exc:return {"http":exc.code,"error":"HTTP_ERROR","data":b""}
 except Exception as exc:return {"http":None,"error":type(exc).__name__,"data":b""}
def catalog():
 url="https://api.tardis.dev/v1/exchanges/binance-futures"
 ans=request(url,200_000)
 result={"purpose":"official Tardis exchange catalog","http":ans["http"]}
 if ans["http"]==200:
  try:
   payload=json.loads(ans["data"])
   d=payload.get("datasets",{})
   symbols=d.get("symbols",[])
   result.update({"supports_datasets":payload.get("supportsDatasets"),
                  "catalog_symbol_count":len(symbols),
                  "available_until":d.get("exportedUntil"),
                  "symbol_types":{sym:next((x.get("dataTypes",[]) for x in symbols if x.get("id")==sym),[])
                        for sym in ("BTCUSDT","ETHUSDT","SOLUSDT")}})
  except Exception as exc:result["status"]="CATALOG_PARSE_FAILURE";result["error_type"]=type(exc).__name__
 else:result["status"]=ans.get("error","CATALOG_UNAVAILABLE")
 return result
def sample(day,sym):
 y,m,d=day.split("-")
 url=f"https://datasets.tardis.dev/v1/binance-futures/derivative_ticker/{y}/{m}/{d}/{sym}.csv.gz"
 ans=request(url)
 row={"date":day,"symbol":sym,"http":ans["http"],"sample_path":"binance-futures/derivative_ticker",
      "prefix_bytes":len(ans["data"]),"content_length":ans.get("content_length")}
 if ans["http"]!=200:
  row["status"]=ans.get("error","SAMPLE_NOT_READ")
  return row
 data=ans["data"]
 if data[:2]!=b"\\x1f\\x8b":
  row["status"]="NOT_GZIP";return row
 try:
  dec=zlib.decompressobj(16+zlib.MAX_WBITS).decompress(data)
  lines=dec.decode("utf-8-sig",errors="replace").splitlines()
  header=lines[0].split(",") if lines else []
  row.update({"status":"GZIP_PREFIX_VALID","header":header[:32],
     "local_timestamp_column_present":"local_timestamp" in header,
     "open_interest_column_present":"open_interest" in header,
     "first_data_line_available":len(lines)>1,
     "gzip_compressed_prefix_sha256":hashlib.sha256(data).hexdigest()})
 except Exception as exc:row.update({"status":"GZIP_PREFIX_PARSE_ERROR","error_type":type(exc).__name__})
 return row
def main():
 checks=[("2020-06-01","BTCUSDT"),("2024-01-01","BTCUSDT"),
         ("2026-09-01","BTCUSDT"),("2026-10-01","BTCUSDT"),
         ("2026-10-01","ETHUSDT"),("2026-10-01","SOLUSDT")]
 results=[sample(*item) for item in checks]
 report={"schema":"detector-tardis-binance-oi-catalog-probe-v1",
   "checked_utc":dt.datetime.now(dt.timezone.utc).isoformat(),
   "catalog":catalog(),"samples":results,
   "status":"SAMPLE_PREFIX_CONFIRMED" if any(x["status"]=="GZIP_PREFIX_VALID" for x in results) else "SAMPLE_ACCESS_NOT_CONFIRMED",
   "scope":"probe-only, no paid access; data are Tardis REST snapshots, not Binance 5m metrics rows",
   "no_historical_publication_claim":True}
 (OUT/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
 print("TARDIS_OI_CATALOG_PROBE",json.dumps(report,ensure_ascii=False),flush=True)
 if os.environ.get("GITHUB_STEP_SUMMARY"):
  with open(os.environ["GITHUB_STEP_SUMMARY"],"a",encoding="utf-8") as fp:
   fp.write("## Tardis Binance OI catalog and sample probe\n\n")
   fp.write(f"- {report['status']}\n- Catalog HTTP: {report['catalog']['http']}\n")
   for x in results:fp.write(f"- {x['date']} {x['symbol']}: {x['status']} HTTP {x['http']}\n")
if __name__=="__main__":main()
