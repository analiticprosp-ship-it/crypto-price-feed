#!/usr/bin/env python3
"""Detector v4.7 — consecutive months, listing-aware quality, persisted audited CSV chunks.
Research only. No missing-bar synthesis, no historical signal claims.
"""
import csv,io,json,hashlib,urllib.request,zipfile,datetime as dt,collections,os
from pathlib import Path
O=Path("detector_futures_contiguous_v47_results");O.mkdir(exist_ok=True)
DATA=Path("detector_futures_contiguous_v47_data");DATA.mkdir(exist_ok=True)
SYMBOLS=["BTC","ETH","SOL"]
MONTHS=["2020-09","2020-10","2020-11","2020-12","2021-01","2021-02"]
MAX_ZIP=95_000_000
def get(url):
 with urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"DetectorResearch-v47"}),timeout=120) as r:
  b=r.read(MAX_ZIP+1)
  if len(b)>MAX_ZIP:raise ValueError("ZIP_SIZE_LIMIT")
  return b
results=[];boundary=[]
for asset in SYMBOLS:
 prev_end=None
 for month in MONTHS:
  pair=asset+"USDT";url=f"https://data.binance.vision/data/futures/um/monthly/klines/{pair}/5m/{pair}-5m-{month}.zip"
  row={"asset":asset,"month":month,"url":url,"status":"ERROR"}
  try:
   raw=get(url);row["zip_sha256"]=hashlib.sha256(raw).hexdigest();row["zip_bytes"]=len(raw)
   with zipfile.ZipFile(io.BytesIO(raw)) as z:
    if z.testzip():raise ValueError("ZIP_CRC_FAIL")
    names=[x for x in z.namelist() if x.endswith(".csv")]
    if len(names)!=1:raise ValueError("CSV_COUNT_NOT_ONE")
    with z.open(names[0]) as f:
     reader=csv.reader(io.TextIOWrapper(f,encoding="utf-8-sig"))
     prev=None;first=None;last=None;n=0;bad=0;gaps=0;dupes=0
     for r in reader:
      if not r or not r[0].isdigit():continue
      n+=1
      try:
       t=int(r[0]);o,h,l,c=map(float,r[1:5]);vol=float(r[5]);buy=float(r[9])
       if first is None:first=t
       last=t
       if prev is not None:
        if t==prev:dupes+=1
        elif t-prev!=300000:gaps+=1
       prev=t
       if not (l<=min(o,c)<=max(o,c)<=h and 0<=buy<=vol):bad+=1
      except Exception:bad+=1
   y,m=map(int,month.split("-"));ny,nm=(y+1,1) if m==12 else (y,m+1)
   start=int(dt.datetime(y,m,1,tzinfo=dt.timezone.utc).timestamp()*1000)
   end=int(dt.datetime(ny,nm,1,tzinfo=dt.timezone.utc).timestamp()*1000)-300000
   expected=(end-start)//300000+1
   full=(first==start and last==end and n==expected)
   partial=(first is not None and first>start and last==end and n==(end-first)//300000+1)
   clean=not (bad or gaps or dupes)
   status="PASS_FULL_MONTH" if clean and full else "PARTIAL_LISTING_MONTH_CANDIDATE" if clean and partial else "QUALITY_FAIL"
   row.update(status=status,rows=n,expected_full_rows=expected,first_timestamp_ms=first,last_timestamp_ms=last,first_utc=dt.datetime.fromtimestamp(first/1000,dt.timezone.utc).isoformat() if first else "",last_utc=dt.datetime.fromtimestamp(last/1000,dt.timezone.utc).isoformat() if last else "",invalid_rows=bad,gap_transitions=gaps,duplicate_timestamps=dupes)
   if prev_end is not None and first is not None:boundary.append({"asset":asset,"from_month":prev_month,"to_month":month,"delta_minutes":(first-prev_end)/60000,"contiguous":first-prev_end==300000})
   prev_end=last;prev_month=month
   # Store verified source ZIP bytes for reuse, never store failed files.
   if status in ("PASS_FULL_MONTH","PARTIAL_LISTING_MONTH_CANDIDATE"):
    target=DATA/f"{pair}-5m-{month}.zip";target.write_bytes(raw);row["stored_zip"]=str(target)
  except Exception as e:row["error"]=type(e).__name__+":"+str(e)[:200]
  results.append(row);print(asset,month,row["status"],flush=True)
def write(name,rows):
 keys=list(dict.fromkeys(k for r in rows for k in r))
 with (O/name).open("w",newline="") as f:
  w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(rows)
write("monthly_quality.csv",results);write("month_boundaries.csv",boundary)
(O/"manifest.json").write_text(json.dumps({"version":"4.7","symbols":SYMBOLS,"months":MONTHS,"statuses":dict(collections.Counter(r["status"] for r in results)),"source":"Binance USD-M perpetual monthly 5m ZIP","artifact_policy":"Separate ZIP artifact with original verified archives; may exceed GitHub artifact quota; workflow may fail to upload large batches","listing_warning":"PARTIAL_LISTING_MONTH_CANDIDATE is NOT proof of listing date","replay_warning":"No OI/funding, no original Detector signal parity, no live changes"},indent=2))
