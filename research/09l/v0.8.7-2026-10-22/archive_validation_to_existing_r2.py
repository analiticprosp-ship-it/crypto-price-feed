#!/usr/bin/env python3
"""Upload SMALL derived validation report into existing private R2. SHA256 readback required."""
import datetime as dt,hashlib,json,os,pathlib
import boto3
from botocore.exceptions import ClientError
ROOT=pathlib.Path(__file__).resolve().parent
SOURCE=ROOT/"derived"/"09L_v087_retrospective_chronological_baseline_vs_flow.json"
REQUIRED=("R2_ACCOUNT_ID","R2_ACCESS_KEY_ID","R2_SECRET_ACCESS_KEY","R2_BUCKET")
def run():
 miss=[k for k in REQUIRED if not os.getenv(k)]
 if miss:raise RuntimeError("R2_CREDS_NOT_CONFIGURED:"+",".join(miss))
 raw=SOURCE.read_bytes()
 if len(raw)>1_000_000:raise ValueError("DERIVED_REPORT_OVERSIZE")
 obj=json.loads(raw)
 if obj["status"]!="RETROSPECTIVE_BASELINE_DIAGNOSTIC_COMPLETE_NOT_PROSPECTIVE_OOS" or obj["trade_canon_mutation"] is not False:
  raise ValueError("EXPECTED_RESEARCH_SHADOW_REPORT_ONLY")
 digest=hashlib.sha256(raw).hexdigest()
 dest=f"research/09l/v087/validation/{digest}.json"
 cli=boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
                  aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
                  aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
                  region_name="auto")
 bucket=os.environ["R2_BUCKET"]
 try:
  cli.head_object(Bucket=bucket,Key=dest);mode="ALREADY_EXISTS"
 except ClientError as exc:
  if exc.response.get("ResponseMetadata",{}).get("HTTPStatusCode")!=404:raise
  cli.put_object(Bucket=bucket,Key=dest,Body=raw,ContentType="application/json",
                 Metadata={"sha256":digest,"study":"09l-shadow-v087-baseline-comparison"})
  mode="WRITTEN"
 readback=cli.get_object(Bucket=bucket,Key=dest)["Body"].read()
 if hashlib.sha256(readback).hexdigest()!=digest:raise RuntimeError("R2_READBACK_SHA_MISMATCH")
 receipt={"study":"09L v087 retrospective baseline shadow R2 receipt",
   "status":"R2_READBACK_SHA256_PASS","sha256":digest,"r2_key":dest,
   "byte_count":len(raw),"write_mode":mode,
   "recorded_at_utc":dt.datetime.now(dt.timezone.utc).isoformat(),
   "research_status":obj["status"],"scientific_gate":obj["primary_exploratory_gate"],
   "trading_canon_mutation":False}
 p=ROOT/"derived"/("r2_validation_receipt_"+digest[:16]+".json")
 with p.open("x") as f:json.dump(receipt,f,indent=2);f.write("\n")
 print(json.dumps({"status":receipt["status"],"r2_key":dest,"sha256":digest,
                   "scientific_gate":receipt["scientific_gate"]}))
if __name__=="__main__":run()
