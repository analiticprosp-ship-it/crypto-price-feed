#!/usr/bin/env python3
"""Detector v4.8: parallel bounded monthly Binance USD-M futures ingestion.
Download source ZIPs, validate exact monthly 5m timestamps, OHLC and taker volumes.
Persist validated ZIPs as artifact (not permanent storage). No historical signals.
"""
import argparse,concurrent.futures,urllib.request,urllib.error,zipfile,io,csv,json,hashlib,datetime as dt,collections,time,os
from pathlib import Path
P=argparse.ArgumentParser();P.add_argument("--batch",type=int,default=0);P.add_argument("--batch-size",type=int,default=36);P.add_argument("--workers",type=int,default=6);a=P.parse_args()
ASSETS="BTC ETH BNB LINK XRP SOL AVAX AAVE INJ NEAR LDO APT SUI ENA HYPE ADA DOGE DOT LTC BCH TRX ATOM UNI ETC FIL ICP OP ARB PEPE SHIB WIF FET RENDER RNDR SEI TIA JUP WLD STX GRT SAND MANA CRV DYDX".split()
# Phase A: BTC/ETH/SOL complete coverage; phase B: remaining assets.
PRIORITY=["BTC","ETH","SOL"]+[x for x in ASSETS if x not in ("BTC","ETH","SOL")]
MONTHS=[f"{y}-{m:02d}" for y in range(2020,2027) for m in range(1,13) if (y,m)<=(2026,9)]
# Sort by asset to make deterministic resumable batches.
JOBS=[(s,m) for s in PRIORITY for m in MONTHS]
start=a.batch*a.batch_size;selected=JOBS[start:start+a.batch_size]
ROOT=Path("detector_futures_bulk_v48");DATA=ROOT/"data";REPORT=ROOT/"report";DATA.mkdir(parents=True,exist_ok=True);REPORT.mkdir(parents=True,exist_ok=True)
def run(job):
 symbol,month=job;pair=symbol+"USDT";url=f"https://data.binance.vision/data/futures/um/monthly/klines/{pair}/5m/{pair}-5m-{month}.zip"
 r={"asset":symbol,"month":month,"url":url,"status":"FAILED"}
 try:
  req=urllib.request.Request(url,headers={"User-Agent":"DetectorResearch-v48"})
  with urllib.request.urlopen(req,timeout=100) as response:
   raw=response.read(100_000_001)
  if len(raw)>100_000_000:raise ValueError("ZIP_SIZE_CAP")
  sha=hashlib.sha256(raw).hexdigest()
  with zipfile.ZipFile(io.BytesIO(raw)) as z:
   if z.testzip():raise ValueError("ZIP_CRC_FAILED")
   names=[x for x in z.namelist() if x.lower().endswith(".csv")]
   if len(names)!=1:raise ValueError("EXPECTED_SINGLE_CSV")
   n=0;first=None;last=None;prev=None;invalid=0;gaps=0;dupes=0
   with z.open(names[0]) as f:
    for line in csv.reader(io.TextIOWrapper(f,encoding="utf-8-sig",errors="replace")):
     if not line:continue
     if not line[0].isdigit():continue
     n+=1
     try:
      t=int(line[0]);o,h,l,c=map(float,line[1:5]);vol=float(line[5]);buy=float(line[9])
      if first is None:first=t
      if prev is not None:
       if t==prev:dupes+=1
       elif t-prev!=300000:gaps+=1
      prev=t;last=t
      if not (l<=min(o,c)<=max(o,c)<=h and 0<=buy<=vol):invalid+=1
     except Exception:invalid+=1
  y,m=map(int,month.split("-"));ny,nm=(y+1,1) if m==12 else (y,m+1)
  lo=int(dt.datetime(y,m,1,tzinfo=dt.timezone.utc).timestamp()*1000);hi=int(dt.datetime(ny,nm,1,tzinfo=dt.timezone.utc).timestamp()*1000)-300000
  expected=(hi-lo)//300000+1
  full=first==lo and last==hi and n==expected
  partial=first is not None and first>lo and last==hi and n==(hi-first)//300000+1
  clean=not (invalid or gaps or dupes)
  status="PASS_FULL_MONTH" if clean and full else "PARTIAL_FIRST_MONTH_CANDIDATE" if clean and partial else "QUALITY_FAIL"
  r.update(status=status,zip_sha256=sha,zip_bytes=len(raw),rows=n,expected_full_rows=expected,first_ms=first,last_ms=last,invalid=invalid,gaps=gaps,duplicates=dupes)
  if status.startswith("PASS") or status.startswith("PARTIAL"):
   target=DATA/f"{pair}-5m-{month}.zip";target.write_bytes(raw)
 except urllib.error.HTTPError as e:r.update(status="HTTP_"+str(e.code))
 except Exception as e:r.update(status="ERROR_"+type(e).__name__,error=str(e)[:160])
 return r
with concurrent.futures.ThreadPoolExecutor(max_workers=max(1,min(a.workers,8))) as ex:results=list(ex.map(run,selected))
fields=list(dict.fromkeys(k for r in results for k in r))
with (REPORT/"batch_inventory.csv").open("w",newline="") as f:
 w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(results)
(REPORT/"manifest.json").write_text(json.dumps({"version":"4.8","batch":a.batch,"batch_size":a.batch_size,"selected":len(selected),"global_jobs":len(JOBS),"range":[start,start+len(selected)],"statuses":dict(collections.Counter(r["status"] for r in results)),"stored_zip_count":len(list(DATA.glob("*.zip"))),"limitations":["Each batch is independent: no permanent resume database yet","GitHub Actions artifacts expire; download or mirror them","404 before contract listing is not an archive quality failure","PARTIAL_FIRST_MONTH_CANDIDATE requires independent listing verification","No original Detector signal parity, OI/funding or trading changes"]},indent=2))
print(json.dumps({"batch":a.batch,"selected":len(selected),"statuses":dict(collections.Counter(r["status"] for r in results))}),flush=True)
