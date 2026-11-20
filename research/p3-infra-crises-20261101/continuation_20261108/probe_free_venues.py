#!/usr/bin/env python3
"""Research-only free CryptoHFTData venue discovery, no assumptions of availability."""
import datetime as dt,hashlib,json,os,pathlib,time,urllib.error,urllib.parse,urllib.request
out=pathlib.Path("/tmp/p3-free-venue-probe");out.mkdir(parents=True,exist_ok=True)
key=os.environ.get("CRYPTOHFTDATA_API_KEY","")
venues={
 "coinbase_spot":["BTC_USD","ETH_USD","BTC-USD","ETH-USD"],
 "gateio_spot":["BTC_USDT","ETH_USDT","BTCUSDT","ETHUSDT"],
 "gate_spot":["BTC_USDT","ETH_USDT"],
 "mexc_spot":["BTC_USDT","ETH_USDT","BTCUSDT","ETHUSDT"],
 "cryptocom_spot":["BTC_USDT","ETH_USDT","BTC_USD","ETH_USD"],
 "crypto_com_spot":["BTC_USDT","ETH_USDT"],
}
rows=[]
for venue,symbols in venues.items():
 for symbol in symbols:
  path=f"{venue}/2026-10-29/12/{symbol}_orderbook.parquet"
  url="https://api.cryptohftdata.com/v1/download?"+urllib.parse.urlencode({"file":path,**({"api_key":key} if key else {})})
  row={"venue":venue,"symbol":symbol,"path":path,"status":"NOT_CHECKED"}
  try:
   with urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"P3-free-venue-probe/1"}),timeout=25) as resp:
    row["http_status"]=resp.status
    target=out/(venue+"_"+symbol.replace("/","-")+".parquet")
    size=0;sha=hashlib.sha256()
    with target.open("wb") as f:
     while True:
      chunk=resp.read(1024*1024)
      if not chunk:break
      size+=len(chunk)
      if size>70*1024*1024:raise ValueError("PROBE_LIMIT_70_MIB")
      sha.update(chunk);f.write(chunk)
    if size<4:raise ValueError("EMPTY")
    row.update(status="DOWNLOADED_UNVALIDATED_L2",bytes=size,sha256=sha.hexdigest(),local_file=target.name)
  except urllib.error.HTTPError as e:row.update(status="HTTP_ERROR",http_status=e.code)
  except Exception as e:row.update(status="DOWNLOAD_ERROR",error_type=type(e).__name__)
  if row["status"]!="DOWNLOADED_UNVALIDATED_L2":(out/(venue+"_"+symbol.replace("/","-")+".parquet")).unlink(missing_ok=True)
  rows.append(row);print(venue,symbol,row["status"],row.get("http_status"),flush=True)
  time.sleep(.1)
(out/"manifest.json").write_text(json.dumps({"schema":"P3_FREE_VENUE_PROBE_V1","date":"2026-10-29","hour_utc":12,"rows":rows,"generated_at_utc":dt.datetime.now(dt.timezone.utc).isoformat(),"note":"HTTP 404 does not prove nonexistence: venue ID or path may differ."},indent=2))
