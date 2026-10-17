#!/usr/bin/env python3
"""Bounded reproducible historical spot/perpetual 1m sample; research only."""
import csv,datetime as dt,hashlib,io,json,pathlib,urllib.request,zipfile
root=pathlib.Path("detector_h1_h10_sample");root.mkdir(exist_ok=True)
results=[]
day="2026-10-01"
for market,part in [("spot","spot"),("perp","futures/um")]:
 for symbol in ["BTCUSDT","ETHUSDT","SOLUSDT"]:
  url=f"https://data.binance.vision/data/{part}/daily/klines/{symbol}/1m/{symbol}-1m-{day}.zip"
  record={"market":market,"symbol":symbol,"day":day,"source":url,"status":"UNVERIFIED"}
  try:
   with urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"Detector-H1-H10/1.0"}),timeout=45) as r:
    size=0;chunks=[]
    while True:
     chunk=r.read(1024*1024)
     if not chunk:break
     size+=len(chunk)
     if size>12*1024*1024:raise ValueError("MAX_ARCHIVE_BYTES_EXCEEDED")
     chunks.append(chunk)
   raw=b"".join(chunks);record["zip_sha256"]=hashlib.sha256(raw).hexdigest();record["zip_bytes"]=len(raw)
   with zipfile.ZipFile(io.BytesIO(raw)) as z:
    names=[n for n in z.namelist() if n.endswith(".csv")]
    if len(names)!=1:raise ValueError("UNEXPECTED_CSV_COUNT")
    with z.open(names[0]) as f:
     data=f.read(32*1024*1024+1)
    if len(data)>32*1024*1024:raise ValueError("MAX_CSV_BYTES_EXCEEDED")
   lines=data.decode("utf-8-sig").splitlines()
   rows=list(csv.reader(lines))
   if rows and rows[0] and not rows[0][0].isdigit():rows=rows[1:]
   times=[int(row[0]) for row in rows if len(row)>=6 and row[0].isdigit()]
   # Binance archives may encode timestamps in milliseconds or microseconds.
   unit="us" if times and times[0]>10**14 else "ms"
   norm=[t//1000 if unit=="us" else t for t in times]
   expected=int(dt.datetime(2026,10,1,tzinfo=dt.timezone.utc).timestamp()*1000)
   gaps=sum(b-a!=60000 for a,b in zip(norm,norm[1:]))
   record.update(status="VERIFIED" if len(rows)==1440 and len(norm)==1440 and norm[0]==expected and gaps==0 else "PARTIAL",rows=len(rows),first_ts_ms=norm[0] if norm else None,last_ts_ms=norm[-1] if norm else None,non_1m_gaps=gaps,source_timestamp_unit=unit,csv_sha256=hashlib.sha256(data).hexdigest())
   # Preserve only bounded 1m OHLCV sample; no trade decisions.
   target=root/f"{market}_{symbol}_{day}.csv"
   target.write_bytes(data)
  except Exception as e:record["status"]="ERROR";record["error"]=str(e)[:300]
  results.append(record);print(json.dumps({k:record.get(k) for k in ("market","symbol","status","rows","error")}))
(root/"manifest.json").write_text(json.dumps({"date_utc":dt.datetime.now(dt.timezone.utc).isoformat(),"sample_day":day,"data_type":"1m_ohlcv","research_only":True,"results":results},ensure_ascii=False,indent=2))
