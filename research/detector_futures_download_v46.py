#!/usr/bin/env python3
"""Detector v4.6 — staged download of REAL Binance USD-M perpetual 5m monthly ZIPs.
Research-only; strict ZIP integrity, row timestamps, 5m continuity and taker volumes.
Small bounded batches; SHA256 provenance; no trading signals or inferred missing candles.
"""
import csv,io,json,hashlib,urllib.request,urllib.error,zipfile,datetime as dt,collections,time
from pathlib import Path
O=Path("detector_futures_download_v46_results");O.mkdir(exist_ok=True)
# First 3 full months per symbol across three epochs; 9 downloads, bounded <250MB.
JOBS=[("BTC","2020-01"),("BTC","2023-08"),("BTC","2026-09"),
      ("ETH","2020-01"),("ETH","2023-08"),("ETH","2026-09"),
      ("SOL","2020-09"),("SOL","2023-08"),("SOL","2026-09")]
def fetch(url,limit=90_000_000):
 req=urllib.request.Request(url,headers={"User-Agent":"Detector-Research-v46"})
 with urllib.request.urlopen(req,timeout=100) as r:
  b=r.read(limit+1)
  if len(b)>limit:raise ValueError("ZIP_OVER_90MB")
  return b
results=[];errors=[]
for asset,month in JOBS:
 pair=asset+"USDT";url=f"https://data.binance.vision/data/futures/um/monthly/klines/{pair}/5m/{pair}-5m-{month}.zip"
 r={"asset":asset,"month":month,"venue":"Binance USD-M Futures","pair":pair,"source_url":url,"status":"FAILED","data_type":"PERPETUAL_5M_KLINES"}
 try:
  b=fetch(url);r["zip_bytes"]=len(b);r["zip_sha256"]=hashlib.sha256(b).hexdigest()
  with zipfile.ZipFile(io.BytesIO(b)) as z:
   bad=z.testzip()
   if bad:raise ValueError("BAD_ZIP_MEMBER:"+bad)
   csvs=[x for x in z.namelist() if x.lower().endswith(".csv")]
   if len(csvs)!=1:raise ValueError("EXPECTED_ONE_CSV")
   with z.open(csvs[0]) as f:
    reader=csv.reader(io.TextIOWrapper(f,encoding="utf-8-sig",newline=""))
    rows=0;first=None;last=None;gaps=0;duplicates=0;invalid=0;prev=None;ohlc_bad=0;vol_bad=0
    for line in reader:
     if not line:continue
     if not line[0].isdigit():continue
     rows+=1
     try:
      t=int(line[0]);o,h,l,c=map(float,line[1:5]);vol=float(line[5]);buy=float(line[9])
      if first is None:first=t
      last=t
      if prev is not None:
       d=t-prev
       if d==0:duplicates+=1
       elif d!=300000:gaps+=1
      prev=t
      if not (l<=min(o,c)<=max(o,c)<=h):ohlc_bad+=1
      if not (0<=buy<=vol):vol_bad+=1
     except Exception:invalid+=1
    y,m=map(int,month.split("-"))
    next_y,next_m=(y+1,1) if m==12 else (y,m+1)
    expected=int((dt.datetime(next_y,next_m,1,tzinfo=dt.timezone.utc)-dt.datetime(y,m,1,tzinfo=dt.timezone.utc)).total_seconds()/300)
    expected_first=int(dt.datetime(y,m,1,tzinfo=dt.timezone.utc).timestamp()*1000)
    expected_last=expected_first+(expected-1)*300000
    r.update(rows=rows,expected_rows=expected,first_utc=dt.datetime.fromtimestamp(first/1000,dt.timezone.utc).isoformat() if first else "",last_utc=dt.datetime.fromtimestamp(last/1000,dt.timezone.utc).isoformat() if last else "",gap_or_out_of_order_transitions=gaps,duplicate_timestamps=duplicates,invalid_rows=invalid,ohlc_invalid=ohlc_bad,taker_volume_invalid=vol_bad,zip_integrity="PASS",status="PASS" if rows==expected and first==expected_first and last==expected_last and not any([gaps,duplicates,invalid,ohlc_bad,vol_bad]) else "QUALITY_FAIL")
 except Exception as e:r.update(status="DOWNLOAD_OR_PARSE_ERROR",error=type(e).__name__+":"+str(e)[:240])
 results.append(r);print(asset,month,r["status"],flush=True)
fields=list(dict.fromkeys(k for r in results for k in r))
with (O/"monthly_quality.csv").open("w",newline="") as f:
 w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(results)
(O/"manifest.json").write_text(json.dumps({"version":"4.6","jobs":len(JOBS),"status_counts":dict(collections.Counter(r["status"] for r in results)),"scope":"9 selected full monthly perpetual 5m archives; no claims for other months","source":"data.binance.vision futures/um/monthly/klines","constraints":["SHA256 hashes identify downloaded ZIPs but do not prove historical authenticity alone","No archive bytes included in artifact; downloadable from recorded official URLs","No OI or funding in standard kline ZIP","Kline taker buy volume not proven identical to original takerlongshortRatio","No gap filling, trading signals, P&L or live system changes"],"next":"If passes, expand staged monthly batches; research historical OI/funding independently"},indent=2))
