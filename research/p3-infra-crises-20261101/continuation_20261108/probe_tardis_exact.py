#!/usr/bin/env python3
"""P3 exact Tardis dataset URL and access audit; sample download only if authorized."""
import datetime as dt,hashlib,json,os,pathlib,urllib.error,urllib.parse,urllib.request
OUT=pathlib.Path("/tmp/p3-tardis-exact");OUT.mkdir(parents=True,exist_ok=True)
VENUES=("coinbase","gate-io","mexc","crypto-com")
KEY=os.getenv("TARDIS_API_KEY","");ROWS=[]
for venue in VENUES:
 row={"venue":venue,"date":"2026-10-29","status":"NOT_CHECKED","candidates":[]}
 try:
  with urllib.request.urlopen("https://api.tardis.dev/v1/exchanges/"+venue,timeout=25) as resp:meta=json.load(resp)
  ds=meta.get("datasets") or {};symbols=ds.get("symbols") or []
  eligible=[s for s in symbols if isinstance(s,dict) and "incremental_book_L2" in (s.get("dataTypes") or []) and any(x in s.get("id","").upper() for x in ("BTC","ETH"))]
  row["supportsDatasets"]=meta.get("supportsDatasets");row["exportedUntil"]=ds.get("exportedUntil");row["candidate_count"]=len(eligible)
  selected=[]
  for asset in ("BTC","ETH"):
   opts=[s for s in eligible if asset in s.get("id","").upper() and ("USD" in s.get("id","").upper() or "USDT" in s.get("id","").upper())]
   if opts:selected.append(opts[0]["id"])
  row["selected_symbols"]=selected
  for symbol in selected:
   safe=symbol.upper().replace("/","-").replace(":","-")
   url=f"https://datasets.tardis.dev/v1/{venue}/incremental_book_L2/2026/10/29/{urllib.parse.quote(safe,safe='-')}.csv.gz"
   item={"symbol":symbol,"url":url,"status":"NOT_CHECKED"}
   headers={"User-Agent":"P3-research-exact-tardis-dataset/1"}
   if KEY:headers["Authorization"]="Bearer "+KEY
   try:
    with urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=45) as response:
     item["http_status"]=response.status;item["content_type"]=response.headers.get("Content-Type")
     # Do not silently turn a 200 into complete archive: bounded response and verify gzip.
     target=OUT/f"{venue}_{safe}.csv.gz";h=hashlib.sha256();size=0;limit=32*1024*1024
     with target.open("wb") as f:
      while True:
       chunk=response.read(1024*1024)
       if not chunk:break
       size+=len(chunk)
       if size>limit:raise ValueError("PROBE_LIMIT_32_MIB")
       f.write(chunk);h.update(chunk)
     import gzip
     with gzip.open(target,"rb") as g:header=g.readline(2000).decode("utf-8")
     item.update(status="DOWNLOADED_GZIP_HEADER_CHECKED",bytes=size,sha256=h.hexdigest(),csv_header=header.strip(),local_file=target.name)
   except urllib.error.HTTPError as e:item.update(status="HTTP_ERROR",http_status=e.code)
   except Exception as e:item.update(status="DOWNLOAD_OR_FORMAT_ERROR",error_type=type(e).__name__,note=str(e)[:100])
   if item["status"]!="DOWNLOADED_GZIP_HEADER_CHECKED":(OUT/f"{venue}_{safe}.csv.gz").unlink(missing_ok=True)
   row["candidates"].append(item)
  row["status"]="METADATA_AND_DATASET_URLS_CHECKED"
 except Exception as e:row.update(status="METADATA_ERROR",error_type=type(e).__name__,note=str(e)[:120])
 ROWS.append(row);print(venue,row["status"],[(x["symbol"],x["status"],x.get("http_status")) for x in row["candidates"]],flush=True)
(OUT/"manifest.json").write_text(json.dumps({"schema":"P3_TARDIS_EXACT_ACCESS_V1","generated_at_utc":dt.datetime.now(dt.timezone.utc).isoformat(),"api_key_present":bool(KEY),"caveat":"Gzip header check is not full order book replay; file probe capped at 32MiB.","rows":ROWS},indent=2))
