#!/usr/bin/env python3
"""Detector v5.3: read-only R2 integrity audit and known gap registry."""
import boto3,hashlib,json,os
from botocore.config import Config
required=("R2_ACCOUNT_ID","R2_ACCESS_KEY_ID","R2_SECRET_ACCESS_KEY","R2_BUCKET")
if not all(os.getenv(x) for x in required):raise SystemExit("R2 secrets missing")
s3=boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto",config=Config(signature_version="s3v4"))
bucket=os.environ["R2_BUCKET"]
known=[
 {"pair":"XRPUSDT","month":"2022-02","source_sha256":"0ad5e6d54e75e48481c7fe86f61e2e4e54406de060f7bc8e7113eef2ae90f859","missing_start_utc":"2022-02-26T00:00:00Z","missing_end_utc":"2022-02-28T23:55:00Z","missing_5m":864,"classification":"HISTORICAL_GAP"},
 {"pair":"NEARUSDT","month":"2022-02","source_sha256":"03f82e047addc08280295c65a45dc2962fff3a35a408a11292ebabe33efb4b40","missing_start_utc":"2022-02-26T00:00:00Z","missing_end_utc":"2022-02-28T23:55:00Z","missing_5m":864,"classification":"HISTORICAL_GAP"}
]
items=[];token=None
while True:
 kw={"Bucket":bucket,"Prefix":"binance/usdm/5m/","MaxKeys":1000}
 if token:kw["ContinuationToken"]=token
 page=s3.list_objects_v2(**kw)
 items.extend(page.get("Contents",[]))
 if not page.get("IsTruncated"):break
 token=page["NextContinuationToken"]
results=[]
for entry in items:
 key=entry["Key"]; h=s3.head_object(Bucket=bucket,Key=key); meta=h.get("Metadata",{})
 expected=meta.get("sha256","")
 row={"key":key,"bytes":entry["Size"],"metadata_sha256":expected,"quality_metadata":meta.get("quality",""),"integrity":"UNVERIFIED"}
 if not expected or len(expected)!=64:row["integrity"]="MISSING_SHA_METADATA"
 else:
  digest=hashlib.sha256()
  response=s3.get_object(Bucket=bucket,Key=key)
  for block in response["Body"].iter_chunks(chunk_size=1024*1024):
   if block:digest.update(block)
  row["integrity"]="PASS" if digest.hexdigest()==expected else "SHA256_MISMATCH"
 results.append(row)
os.makedirs("r2_audit_v53",exist_ok=True)
report={"version":"5.3","bucket":bucket,"objects":len(results),"integrity_pass":sum(x["integrity"]=="PASS" for x in results),"integrity_fail":sum(x["integrity"]!="PASS" for x in results),"known_source_gaps":known,"object_results":results,"notes":["Read-only R2 audit; no source modifications","Known source gaps are not repaired or approved for replay","Unlisted 404 months are not classified as listing dates","SHA256 validates stored bytes against original recorded metadata; it is not independent provenance validation"]}
with open("r2_audit_v53/audit.json","w") as f:json.dump(report,f,indent=2)
print(json.dumps({k:v for k,v in report.items() if k!="object_results"},indent=2))
if report["integrity_fail"]:raise SystemExit("R2 integrity failures; see report")
