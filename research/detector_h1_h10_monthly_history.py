#!/usr/bin/env python3
"""Read-only 2024-2026 monthly 1h Spot/USDT perp OHLCV archive collection."""
import csv,datetime as dt,hashlib,io,json,os,pathlib,time,urllib.request,urllib.error,zipfile
ROOT=pathlib.Path("detector_h1_h10_monthly");ROOT.mkdir(exist_ok=True)
START=dt.date(2024,1,1);END=dt.date(2026,10,1)
months=[];y,m=START.year,START.month
while (y,m)<(END.year,END.month):
 months.append(f"{y:04d}-{m:02d}");m+=1
 if m==13:y,m=y+1,1
symbols=["BTCUSDT","ETHUSDT","SOLUSDT"]
markets=[("spot","spot"),("perp","futures/um")]
records=[]
for ym in months:
 for market,path in markets:
  for symbol in symbols:
   url=f"https://data.binance.vision/data/{path}/monthly/klines/{symbol}/1h/{symbol}-1h-{ym}.zip"
   rec={"month":ym,"market":market,"symbol":symbol,"url":url,"status":"UNVERIFIED"}
   try:
    req=urllib.request.Request(url,headers={"User-Agent":"Detector-H1-H10-research/1.0"})
    with urllib.request.urlopen(req,timeout=30) as response:
     chunks=[];total=0
     while True:
      chunk=response.read(1024*1024)
      if not chunk:break
      total+=len(chunk)
      if total>8*1024*1024:raise ValueError("ZIP_SIZE_LIMIT")
      chunks.append(chunk)
    raw=b"".join(chunks)
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
     names=[n for n in z.namelist() if n.endswith(".csv")]
     if len(names)!=1:raise ValueError("UNEXPECTED_ZIP_STRUCTURE")
     data=z.read(names[0])
     if len(data)>20*1024*1024:raise ValueError("CSV_SIZE_LIMIT")
    rows=list(csv.reader(io.StringIO(data.decode("utf-8-sig"))))
    if rows and rows[0] and not rows[0][0].isdigit():rows=rows[1:]
    times=[int(row[0]) for row in rows if len(row)>=6 and row[0].isdigit()]
    unit="us" if times and times[0]>10**14 else "ms"
    ts=[x//1000 if unit=="us" else x for x in times]
    start=dt.datetime.strptime(ym,"%Y-%m").replace(tzinfo=dt.timezone.utc)
    ny,nm=(start.year+1,1) if start.month==12 else (start.year,start.month+1)
    end=dt.datetime(ny,nm,1,tzinfo=dt.timezone.utc)
    expected=int((end-start).total_seconds()/3600)
    gaps=sum(b-a!=3600000 for a,b in zip(ts,ts[1:]))
    valid=len(ts)==expected and len(rows)==expected and bool(ts) and ts[0]==int(start.timestamp()*1000) and ts[-1]==int((end-dt.timedelta(hours=1)).timestamp()*1000) and gaps==0
    rec.update(status="VERIFIED" if valid else "PARTIAL",rows=len(rows),expected=expected,first_ts_ms=ts[0] if ts else None,last_ts_ms=ts[-1] if ts else None,gaps=gaps,timestamp_unit=unit,zip_sha256=hashlib.sha256(raw).hexdigest(),csv_sha256=hashlib.sha256(data).hexdigest())
    if valid:
     # Keep only compact 1h OHLCV columns and normalized UTC timestamps.
     out=ROOT/f"{market}_{symbol}_{ym}_1h.csv"
     with out.open("w",newline="") as f:
      w=csv.writer(f);w.writerow(["open_time_ms","open","high","low","close","volume"])
      for row,t in zip(rows,ts):w.writerow([t,*row[1:6]])
   except Exception as exc:rec.update(status="ERROR",error=str(exc)[:240])
   records.append(rec)
   print(json.dumps({k:rec.get(k) for k in ("month","market","symbol","status","rows","error")}),flush=True)
   # Persist manifest after every item so partial failures remain auditable.
   (ROOT/"manifest.json").write_text(json.dumps({"generated_at_utc":dt.datetime.now(dt.timezone.utc).isoformat(),"scope":"2024-01 through 2026-09, monthly 1h spot/perp OHLCV","records":records},indent=2))
summary={"total":len(records),"verified":sum(r["status"]=="VERIFIED" for r in records),"partial":sum(r["status"]=="PARTIAL" for r in records),"errors":sum(r["status"]=="ERROR" for r in records)}
(ROOT/"summary.json").write_text(json.dumps(summary,indent=2));print("SUMMARY",json.dumps(summary))
