#!/usr/bin/env python3
"""Read-only R2 monthly coverage matrix for the detector research universe."""
import csv,datetime as dt,json,os
import boto3
from botocore.config import Config
ASSETS="BTC ETH BNB LINK XRP SOL AVAX AAVE INJ NEAR LDO APT SUI ENA HYPE ADA DOGE DOT LTC BCH TRX ATOM UNI ETC FIL ICP OP ARB PEPE SHIB WIF FET RENDER RNDR SEI TIA JUP WLD STX GRT SAND MANA CRV DYDX".split()
MONTHS=[f"{y}-{m:02d}" for y in range(2020,2027) for m in range(1,13) if (y,m)<=(2026,9)]
s3=boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto",config=Config(signature_version="s3v4"))
bucket=os.environ["R2_BUCKET"]
objects={};token=None
while True:
 kw={"Bucket":bucket,"Prefix":"binance/usdm/5m/","MaxKeys":1000}
 if token:kw["ContinuationToken"]=token
 page=s3.list_objects_v2(**kw)
 for o in page.get("Contents",[]):objects[o["Key"]]=o
 if not page.get("IsTruncated"):break
 token=page["NextContinuationToken"]
rows=[]
for symbol in ASSETS:
 for month in MONTHS:
  key=f"binance/usdm/5m/{symbol}USDT/{month}.zip"
  if key in objects:
   h=s3.head_object(Bucket=bucket,Key=key);meta=h.get("Metadata",{})
   q=meta.get("quality","")
   status="STORED_FULL_METADATA" if q=="full" else "STORED_PARTIAL_UNVERIFIED" if q=="partial" else "STORED_UNKNOWN"
   rows.append({"asset":symbol,"month":month,"status":status,"bytes":objects[key]["Size"],"sha256_metadata":meta.get("sha256",""),"rows_metadata":meta.get("rows","")})
  else:rows.append({"asset":symbol,"month":month,"status":"MISSING_UNCLASSIFIED","bytes":0,"sha256_metadata":"","rows_metadata":""})
os.makedirs("detector_v57_reports",exist_ok=True)
with open("detector_v57_reports/coverage.csv","w",newline="") as f:
 w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
counts={s:sum(r["status"]==s for r in rows) for s in sorted(set(r["status"] for r in rows))}
with open("detector_v57_reports/coverage_summary.json","w") as f:json.dump({"version":"5.7","expected_grid":len(rows),"r2_objects_total_under_prefix":len(objects),"counts":counts,"limitations":["Missing does not imply delisting or no trading; cross-reference original batch HTTP 404 reports","Stored full/partial derived from uploader metadata, not independent source audit","Partial archives are not approved for replay without interval validation","No R2 writes or trading changes"]},f,indent=2)
print(json.dumps(counts,indent=2))
