#!/usr/bin/env python3
"""P3 venue discovery: bounded requests, manifest receipts, no secret logging."""
import argparse,datetime as dt,hashlib,json,os,pathlib,time,urllib.error,urllib.parse,urllib.request
SLOTS=[("kraken_spot","BTC_USD"),("kraken_spot","ETH_USD"),("kraken_spot","XBTUSD"),("kraken_spot","ETHUSD"),("binance_spot","BTCUSDT")]
def main():
 p=argparse.ArgumentParser();p.add_argument("--out",required=True);p.add_argument("--day",default="2026-10-30");p.add_argument("--hour",type=int,default=12);p.add_argument("--max-bytes",type=int,default=100_000_000);a=p.parse_args()
 out=pathlib.Path(a.out);out.mkdir(parents=True,exist_ok=True);key=os.getenv("CRYPTOHFTDATA_API_KEY");rows=[]
 for venue,symbol in SLOTS:
  path=f"{venue}/{a.day}/{a.hour:02d}/{symbol}_orderbook.parquet"
  row={"venue":venue,"symbol":symbol,"path":path,"status":"NOT_CHECKED","http_status":None}
  query={"file":path}
  if key:query["api_key"]=key
  url="https://api.cryptohftdata.com/v1/download?"+urllib.parse.urlencode(query)
  try:
   req=urllib.request.Request(url,headers={"User-Agent":"P3-L2-venue-discovery/1"})
   with urllib.request.urlopen(req,timeout=60) as resp:
    row["http_status"]=resp.status
    h=hashlib.sha256();n=0;target=out/(hashlib.sha256(path.encode()).hexdigest()[:20]+".parquet")
    with target.open("wb") as f:
     while True:
      block=resp.read(1024*1024)
      if not block:break
      n+=len(block)
      if n>a.max_bytes:raise ValueError("MAX_BYTES_EXCEEDED")
      h.update(block);f.write(block)
    if n<4:raise ValueError("EMPTY_RESPONSE")
    row.update(status="DOWNLOADED_UNVALIDATED_L2",bytes=n,sha256=h.hexdigest(),local_file=str(target))
  except urllib.error.HTTPError as e:
   row.update(http_status=e.code,status="HTTP_ERROR",error_code=e.code)
  except Exception as e:row.update(status="DOWNLOAD_ERROR",error_type=type(e).__name__,note=str(e)[:100] if "api_key" not in str(e) else "REDACTED")
  rows.append(row);print(venue,symbol,row["status"],flush=True)
  time.sleep(1.1)
 manifest={"schema":"P3_KRAKEN_SYMBOL_DISCOVERY_V1","generated_at_utc":dt.datetime.now(dt.timezone.utc).isoformat(),"rows":rows}
 (out/"discovery_manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
if __name__=="__main__":main()
