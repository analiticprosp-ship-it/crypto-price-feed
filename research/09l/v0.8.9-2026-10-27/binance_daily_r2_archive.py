#!/usr/bin/env python3
"""09L v089B only 8 verified Binance daily derived labels into existing PRIVATE R2."""
import argparse,datetime as dt,hashlib,json,os,pathlib
import boto3
from botocore.exceptions import ClientError
ROOT=pathlib.Path(__file__).resolve().parent
FOLDER=ROOT/"derived"/"daily_binance"
DATES=tuple(f"2026-10-{n:02d}" for n in range(19,27))
REQ=("R2_ACCOUNT_ID","R2_ACCESS_KEY_ID","R2_SECRET_ACCESS_KEY","R2_BUCKET")
def main(all_available=False):
 dates=DATES
 if all_available:
  dates=tuple(sorted(p.stem for p in FOLDER.glob("2026-??-??.json") if p.stem>="2026-10-19"))
 if any(not os.getenv(k) for k in REQ):raise RuntimeError("EXISTING_PRIVATE_R2_CREDENTIALS_REQUIRED")
 bucket=os.environ["R2_BUCKET"]
 cli=boto3.client("s3",region_name="auto",
   endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
   aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"])
 rec=[]
 for day in dates:
  p=FOLDER/(day+".json")
  if not p.exists():rec.append({"day":day,"status":"MISSING_DAILY_SOURCE"});continue
  raw=p.read_bytes();j=json.loads(raw)
  if j.get("status")!="DAILY_PRICE_ONLY_EXPLORATORY" or j.get("source",{}).get("status")!="OK" or j.get("date")!=day or not j.get("trading_canon_unchanged"):
   raise ValueError("DERIVED_NOT_ELIGIBLE")
  if len(j.get("eight_fixed_utc_windows",[]))!=8 or not j["source"].get("publisher_sha256"):raise ValueError("PRICE_DATA_QA_NOT_PASS")
  sha=hashlib.sha256(raw).hexdigest()
  key=f"research/09l/v089/daily-binance/{day}/{sha}.json"
  try:cli.head_object(Bucket=bucket,Key=key);mode="EXISTS"
  except ClientError as e:
   if e.response.get("ResponseMetadata",{}).get("HTTPStatusCode")!=404:raise
   cli.put_object(Bucket=bucket,Key=key,Body=raw,ContentType="application/json",Metadata={"sha256":sha})
   mode="WRITTEN"
  rr=cli.get_object(Bucket=bucket,Key=key)["Body"].read()
  if hashlib.sha256(rr).hexdigest()!=sha:raise RuntimeError("READBACK_SHA_MISMATCH")
  rec.append({"day":day,"status":"R2_SHA256_READBACK_PASS","r2_key":key,"sha256":sha,
      "native_source_sha256":j["source"]["publisher_sha256"],"mode":mode,
      "usable_cases":sum(x["status"]=="LABEL_READY" for x in j["eight_fixed_utc_windows"])})
 out={"study":"09L v089B Binance daily price-only compact private archive",
   "created_at_utc":dt.datetime.now(dt.timezone.utc).isoformat(),
   "status":"ARCHIVE_COMPLETE_FOR_PRESENT_SOURCES" if len(rec)>0 and len(rec)==len(dates) and all(x["status"]=="R2_SHA256_READBACK_PASS" for x in rec) else "ARCHIVE_PARTIAL",
   "dates":len(dates),"objects_readback":sum(x["status"]=="R2_SHA256_READBACK_PASS" for x in rec),
   "receipts":rec,"no_liquidation_feed":True,"coinglass_pit_missing":True,
   "trading_canon_unchanged":True}
 f=ROOT/"derived"/"r2"/("binance_daily_"+dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")+".json")
 f.parent.mkdir(parents=True,exist_ok=True)
 with f.open("x") as o:json.dump(out,o,indent=2)
 print(json.dumps({"status":out["status"],"objects":out["objects_readback"],"expected":len(dates),"usable":sum(x.get("usable_cases",0) for x in rec),"receipt":str(f.relative_to(ROOT))}))
if __name__=="__main__":
 p=argparse.ArgumentParser();p.add_argument("--all-available",action="store_true")
 main(p.parse_args().all_available)
