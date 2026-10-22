#!/usr/bin/env python3
"""09L v087 compact derived-label R2 archive — reuse EXISTING private Cloudflare R2.
No new secrets, bucket or user account. Never rehost raw Tardis/paid CoinGlass.
Verifies SHA-256 by GET readback; content-addressed writes, no overwrite.
"""
import argparse,datetime as dt,hashlib,json,os,pathlib,sys
import boto3
from botocore.exceptions import ClientError
ROOT=pathlib.Path(__file__).resolve().parent
OUT=ROOT/"derived"/"r2_receipts"
PREFIX="research/09l/v087"
NEEDED=("R2_ACCOUNT_ID","R2_ACCESS_KEY_ID","R2_SECRET_ACCESS_KEY","R2_BUCKET")
CANDIDATES=(("bybit","2026-06-01"),("bybit","2026-07-01"),("bybit","2026-08-01"),
            ("okex-swap","2026-06-01"),("okex-swap","2026-07-01"),("okex-swap","2026-08-01"))
def client():
 missing=[k for k in NEEDED if not os.getenv(k)]
 if missing:raise RuntimeError("R2_CONFIG_MISSING:"+",".join(missing))
 return boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
  aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
  region_name="auto")
def put_verified(c,bucket,key,raw):
 expected=hashlib.sha256(raw).hexdigest()
 try:
  c.head_object(Bucket=bucket,Key=key)
  was="ALREADY_EXISTS"
 except ClientError as e:
  if e.response.get("ResponseMetadata",{}).get("HTTPStatusCode")!=404:raise
  # Non-overwriting write, verified by readback.
  c.put_object(Bucket=bucket,Key=key,Body=raw,ContentType="application/json",
               Metadata={"sha256":expected,"study":"09l-v087-shadow"})
  was="WRITTEN"
 check=c.get_object(Bucket=bucket,Key=key)["Body"].read()
 if hashlib.sha256(check).hexdigest()!=expected:raise RuntimeError("READBACK_SHA256_MISMATCH:"+key)
 return {"status":"R2_SHA256_READBACK_PASS","write_mode":was,"key":key,"sha256":expected,"size_bytes":len(raw)}
def main(selftest=False,all_available=False):
 assert PREFIX=="research/09l/v087"
 assert len(CANDIDATES)==6
 if selftest:
  assert all(day.endswith("-01") and venue in ("bybit","okex-swap") for venue,day in CANDIDATES)
  print(json.dumps({"status":"SELFTEST_PASS","allowed_studies":len(CANDIDATES)}));return
 c=client();bucket=os.environ["R2_BUCKET"]
 targets=CANDIDATES
 if all_available:
  discovered=[]
  for p in sorted((ROOT/"derived"/"v087_labels").glob("*/*_no_lookahead_trade_labels.json")):
   venue=p.parent.name
   day=p.name.split("_no_lookahead_trade_labels.json")[0]
   if venue not in ("bybit","okex-swap") or len(day)!=10 or not day.endswith("-01"):
    raise ValueError("OUTSIDE_VENUE_DAY_SCOPE")
   discovered.append((venue,day))
  targets=tuple(discovered)
 records=[]
 for venue,day in targets:
  p=ROOT/"derived"/"v087_labels"/venue/(day+"_no_lookahead_trade_labels.json")
  if not p.is_file():
   records.append({"venue":venue,"day":day,"status":"SOURCE_OUTPUT_MISSING"});continue
  raw=p.read_bytes()
  if len(raw)>4_000_000:raise ValueError("DERIVED_SIZE_CAP")
  obj=json.loads(raw)
  if obj.get("venue")!=venue or obj.get("source_date_utc")!=day or obj.get("trading_canon_unchanged") is not True:
   raise ValueError("BAD_RESEARCH_OBJECT:"+p.name)
  if obj.get("source",{}).get("status")!="OK":
   raise ValueError("ARCHIVE_REFUSED_SOURCE_NOT_OK:"+p.name)
  if obj.get("status") not in ("LABELS_REGISTERED_EXPLORATORY","PARTIAL_LABELS_MISSING_ASOF_PRICE"):
   raise ValueError("BAD_STATUS:"+p.name)
  sha=hashlib.sha256(raw).hexdigest()
  key=f"{PREFIX}/labels/{venue}/{day}/{sha}.json"
  rec=put_verified(c,bucket,key,raw)
  rec.update({"venue":venue,"day":day,"science_status":obj["status"],
              "ready_case_count":sum(x["status"]=="LABEL_READY" for x in obj["eight_clock_fixed_cases"]),
              "case_count":len(obj["eight_clock_fixed_cases"]),
              "source_sha256":obj["source"].get("compressed_sha256")})
  records.append(rec)
 now=dt.datetime.now(dt.timezone.utc)
 manifest={"study":"09L v0.8.7 first-day-of-month incremental research archiving",
   "run_at_utc":now.isoformat(),"bucket_alias":"EXISTING_PRIVATE_R2_NO_BUCKET_CHANGE",
   "prefix":PREFIX,"r2_receipts":records,
   "status":"ARCHIVE_COMPLETE" if targets and len(records)==len(targets) and all(x["status"]=="R2_SHA256_READBACK_PASS" for x in records)
    else "ARCHIVE_PARTIAL",
   "coinglass_model2_pit":"MISSING",
   "independent_future_OOS":"NOT_ESTABLISHED",
   "trading_canon_unchanged":True}
 mraw=json.dumps(manifest,ensure_ascii=False,sort_keys=True,indent=2).encode()+b"\n"
 msha=hashlib.sha256(mraw).hexdigest()
 manifest_receipt=put_verified(c,bucket,f"{PREFIX}/manifests/{now:%Y/%m/%d}/{msha}.json",mraw)
 manifest["manifest_r2_readback"]=manifest_receipt
 OUT.mkdir(parents=True,exist_ok=True)
 file=OUT/(now.strftime("%Y%m%dT%H%M%S%fZ")+".json")
 with file.open("x") as f:json.dump(manifest,f,ensure_ascii=False,indent=2)
 print(json.dumps({"status":manifest["status"],"manifest_sha256":msha,
     "uploaded":sum(x["status"]=="R2_SHA256_READBACK_PASS" for x in records),
     "expected":len(targets),"cases":sum(x.get("ready_case_count",0) for x in records),
     "missing":[(x["venue"],x["day"]) for x in records if x["status"]!="R2_SHA256_READBACK_PASS"],
     "readback":manifest_receipt["status"],"report":str(file.relative_to(ROOT))}))
if __name__=="__main__":
 p=argparse.ArgumentParser();p.add_argument("--selftest",action="store_true");p.add_argument("--all-available",action="store_true")
 args=p.parse_args()
 main(args.selftest,args.all_available)
