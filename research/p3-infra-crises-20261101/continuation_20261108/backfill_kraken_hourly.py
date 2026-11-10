#!/usr/bin/env python3
"""P3 bounded hourly Kraken backfill, raw bytes preserved; research only."""
import argparse,datetime as dt,hashlib,json,os,pathlib,urllib.error,urllib.parse,urllib.request,time
p=argparse.ArgumentParser();p.add_argument("--day",required=True);p.add_argument("--start-hour",type=int,default=0);p.add_argument("--end-hour",type=int,default=23);p.add_argument("--out",required=True);p.add_argument("--max-file-mb",type=int,default=80);a=p.parse_args()
assert 0<=a.start_hour<=a.end_hour<=23
out=pathlib.Path(a.out);out.mkdir(parents=True,exist_ok=True);key=os.environ.get("CRYPTOHFTDATA_API_KEY");rows=[]
for hour in range(a.start_hour,a.end_hour+1):
 for symbol in ("BTC_USD","ETH_USD"):
  path=f"kraken_spot/{a.day}/{hour:02d}/{symbol}_orderbook.parquet"
  query={"file":path}
  if key:query["api_key"]=key
  row={"day":a.day,"hour_utc":hour,"venue":"kraken_spot","symbol":symbol,"path":path,"status":"NOT_CHECKED"}
  target=out/f"{a.day}_{hour:02d}_{symbol}.parquet"
  try:
   with urllib.request.urlopen(urllib.request.Request("https://api.cryptohftdata.com/v1/download?"+urllib.parse.urlencode(query),headers={"User-Agent":"P3-Kraken-hourly-backfill/1"}),timeout=65) as resp:
    row["http_status"]=resp.status;n=0;sha=hashlib.sha256()
    with target.open("wb") as f:
     while True:
      b=resp.read(1048576)
      if not b:break
      n+=len(b)
      if n>a.max_file_mb*1048576:raise ValueError("FILE_LIMIT")
      sha.update(b);f.write(b)
    if n<4:raise ValueError("EMPTY")
    row.update(status="DOWNLOADED_UNVALIDATED_L2",bytes=n,sha256=sha.hexdigest(),local_file=target.name)
  except urllib.error.HTTPError as e:row.update(status="HTTP_ERROR",http_status=e.code)
  except Exception as e:row.update(status="DOWNLOAD_ERROR",error_type=type(e).__name__)
  if row["status"]!="DOWNLOADED_UNVALIDATED_L2":target.unlink(missing_ok=True)
  rows.append(row);print(a.day,hour,symbol,row["status"],flush=True);time.sleep(.12)
manifest={"schema":"P3_KRAKEN_HOURLY_BACKFILL_V1","generated_at_utc":dt.datetime.now(dt.timezone.utc).isoformat(),"scope":"RAW_ONLY_NOT_REPLAY_VALIDATED","rows":rows}
(out/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
