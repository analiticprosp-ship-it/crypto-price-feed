#!/usr/bin/env python3
"""P3 cross-venue historical L2 availability probe. Read-only, fail-closed."""
import argparse, datetime as dt, hashlib, json, os, pathlib, urllib.request, urllib.error

DATES=("2026-10-28","2026-10-30","2026-11-04")
VENUES={
 "binance_spot":("BTCUSDT","ETHUSDT"),
 "okx_spot":("BTC-USDT","ETH-USDT"),
 "bybit_spot":("BTCUSDT","ETHUSDT"),
 "bitget_spot":("BTCUSDT","ETHUSDT"),
 "kraken_spot":("XBT/USD","ETH/USD"),
}
# Provider symbol mapping must be verified with symbols endpoint; never assume a path is valid.
def main():
 p=argparse.ArgumentParser()
 p.add_argument("--out",required=True)
 p.add_argument("--hour",type=int,default=12)
 p.add_argument("--api-key-env",default="CRYPTOHFTDATA_API_KEY")
 p.add_argument("--max-bytes",type=int,default=500_000_000)
 args=p.parse_args()
 if not 0<=args.hour<=23: p.error("hour must be 0..23")
 out=pathlib.Path(args.out);out.mkdir(parents=True,exist_ok=True)
 key=os.getenv(args.api_key_env)
 rows=[]
 for venue,symbols in VENUES.items():
  for day in DATES:
   for symbol in symbols:
    path=f"{venue}/{day}/{args.hour:02d}/{symbol}_orderbook.parquet.zst"
    row={"provider":"CryptoHFTData","venue":venue,"date":day,"hour_utc":args.hour,"symbol_candidate":symbol,"path_candidate":path,"status":"NOT_PROBED","sha256":None,"bytes":None,"http_status":None,"note":None}
    if not key:
     row["status"]="AUTH_REQUIRED";row["note"]="Provider requires API key; no request made"
    else:
     from urllib.parse import urlencode
     url="https://api.cryptohftdata.com/download?"+urlencode({"file":path,"api_key":key})
     try:
      req=urllib.request.Request(url,headers={"User-Agent":"P3-research-L2-probe/1"})
      with urllib.request.urlopen(req,timeout=40) as resp:
       row["http_status"]=resp.status
       content_type=resp.headers.get("Content-Type","")
       if "json" in content_type or "html" in content_type: raise ValueError("non-binary response: "+content_type)
       h=hashlib.sha256();n=0
       filename=out/(hashlib.sha256(path.encode()).hexdigest()[:20]+".parquet.zst")
       with filename.open("wb") as f:
        while True:
         chunk=resp.read(1024*1024)
         if not chunk: break
         n+=len(chunk)
         if n>args.max_bytes: raise ValueError("max bytes exceeded")
         h.update(chunk);f.write(chunk)
       row.update(status="DOWNLOADED_UNVALIDATED_L2",sha256=h.hexdigest(),bytes=n,local_file=str(filename))
     except urllib.error.HTTPError as e:
      row["http_status"]=e.code
      row["status"]="ACCESS_DENIED" if e.code in (401,403,451) else "HTTP_ERROR"
      row["note"]=str(e)
     except Exception as e:
      row["status"]="PROBE_ERROR";row["note"]=str(e)
    rows.append(row)
    print(venue,day,symbol,row["status"],flush=True)
 manifest={"schema":"P3_L2_SAMPLE_PROBE_V1","generated_at_utc":dt.datetime.now(dt.timezone.utc).isoformat(),"scope":"PROBE_ONLY_NOT_REPLAY_OR_DEPTH_VALIDATION","rows":rows}
 (out/"probe_manifest.json").write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+"\n")
 print(json.dumps({"total":len(rows),"statuses":{s:sum(r["status"]==s for r in rows) for s in sorted(set(r["status"] for r in rows))}}))
if __name__=="__main__": main()
