#!/usr/bin/env python3
"""R2-backed historical ZIP ingestion; research-only, never trades."""
import argparse, calendar, csv, datetime as dt, hashlib, io, json, os, urllib.error, urllib.request, zipfile
from concurrent.futures import ThreadPoolExecutor
import boto3
from botocore.config import Config

p=argparse.ArgumentParser()
p.add_argument("--batch",type=int,default=11)
p.add_argument("--batch-size",type=int,default=36)
p.add_argument("--workers",type=int,default=4)
a=p.parse_args()
ASSETS="BTC ETH BNB LINK XRP SOL AVAX AAVE INJ NEAR LDO APT SUI ENA HYPE ADA DOGE DOT LTC BCH TRX ATOM UNI ETC FIL ICP OP ARB PEPE SHIB WIF FET RENDER RNDR SEI TIA JUP WLD STX GRT SAND MANA CRV DYDX".split()
PRIORITY=["BTC","ETH","SOL"]+[x for x in ASSETS if x not in ("BTC","ETH","SOL")]
MONTHS=[f"{y}-{m:02d}" for y in range(2020,2027) for m in range(1,13) if (y,m)<=(2026,9)]
JOBS=[(s,m) for s in PRIORITY for m in MONTHS]
required=("R2_ACCOUNT_ID","R2_ACCESS_KEY_ID","R2_SECRET_ACCESS_KEY","R2_BUCKET")
assert all(os.getenv(x) for x in required),"Missing R2 secrets"
bucket=os.environ["R2_BUCKET"]
s3=boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto",config=Config(signature_version="s3v4",retries={"max_attempts":3,"mode":"standard"}))

def job(item):
 symbol,month=item; pair=symbol+"USDT"; key=f"binance/usdm/5m/{pair}/{month}.zip"
 url=f"https://data.binance.vision/data/futures/um/monthly/klines/{pair}/5m/{pair}-5m-{month}.zip"
 result={"asset":symbol,"month":month,"key":key}
 try:
  try:
   head=s3.head_object(Bucket=bucket,Key=key)
   meta=head.get("Metadata",{})
   if meta.get("sha256") and meta.get("quality") in ("full","partial") and int(head.get("ContentLength",0))>0:
    result.update(status="ALREADY_STORED_METADATA_VERIFIED",sha256=meta["sha256"])
    return result
   result["existing_unverified"]=True
  except s3.exceptions.ClientError as e:
   if e.response.get("Error",{}).get("Code") not in ("404","NoSuchKey","NotFound"):raise
  req=urllib.request.Request(url,headers={"User-Agent":"DetectorResearch-R2-v51"})
  with urllib.request.urlopen(req,timeout=120) as f:raw=f.read(100_000_001)
  if len(raw)>100_000_000:raise ValueError("ZIP_TOO_LARGE")
  sha=hashlib.sha256(raw).hexdigest()
  with zipfile.ZipFile(io.BytesIO(raw)) as z:
   if z.testzip():raise ValueError("ZIP_CRC")
   names=[n for n in z.namelist() if n.lower().endswith(".csv")]
   if len(names)!=1:raise ValueError("CSV_COUNT")
   n=0;first=None;last=None;prev=None
   with z.open(names[0]) as f:
    for row in csv.reader(io.TextIOWrapper(f,encoding="utf-8-sig")):
     if not row or not row[0].isdigit():continue
     if len(row)<10:raise ValueError("CSV_COLUMNS")
     ts=int(row[0]);o,h,l,c=map(float,row[1:5]);v=float(row[5]);buy=float(row[9])
     if not(l<=min(o,c)<=max(o,c)<=h and 0<=buy<=v):raise ValueError("BAD_OHLC_VOLUME")
     if prev is not None and ts-prev!=300000:raise ValueError("GAP_OR_DUPLICATE")
     if first is None:first=ts
     prev=last=ts;n+=1
  y,m=map(int,month.split("-"));ny,nm=(y+1,1) if m==12 else(y,m+1)
  lo=int(dt.datetime(y,m,1,tzinfo=dt.timezone.utc).timestamp()*1000)
  hi=int(dt.datetime(ny,nm,1,tzinfo=dt.timezone.utc).timestamp()*1000)-300000
  full=first==lo and last==hi and n==(hi-lo)//300000+1
  partial=first is not None and first>lo and last==hi and n==(hi-first)//300000+1
  if not(full or partial):raise ValueError("MONTH_BOUNDARY_OR_COUNT")
  quality="full" if full else "partial"
  s3.put_object(Bucket=bucket,Key=key,Body=raw,ContentType="application/zip",Metadata={"sha256":sha,"quality":quality,"rows":str(n),"source":"binance-futures-um-5m"})
  check=s3.head_object(Bucket=bucket,Key=key)
  if check["ContentLength"]!=len(raw) or check["Metadata"].get("sha256")!=sha:raise ValueError("UPLOAD_HEAD_MISMATCH")
  result.update(status="UPLOADED_"+quality.upper(),sha256=sha,rows=n,bytes=len(raw))
 except urllib.error.HTTPError as e:result.update(status="HTTP_"+str(e.code))
 except Exception as e:result.update(status="ERROR",error=str(e)[:180])
 return result

selected=JOBS[a.batch*a.batch_size:(a.batch+1)*a.batch_size]
with ThreadPoolExecutor(max_workers=max(1,min(a.workers,6))) as pool:results=list(pool.map(job,selected))
os.makedirs("r2_ingest_report",exist_ok=True)
with open("r2_ingest_report/batch.json","w") as f:json.dump({"version":"5.1","batch":a.batch,"selected":len(selected),"results":results,"limitations":["Partial months are unverified listing candidates; may represent historical gaps","HEAD metadata checks provenance, not full byte re-download","Existing old GitHub artifacts are not imported by this job","No Detector parity, OI/funding, trading or portfolio changes"]},f,indent=2)
print(json.dumps({"batch":a.batch,"counts":{k:sum(r["status"]==k for r in results) for k in sorted(set(r["status"] for r in results))}},indent=2))
if any(r["status"]=="ERROR" for r in results):raise SystemExit("Some jobs failed; inspect report")
