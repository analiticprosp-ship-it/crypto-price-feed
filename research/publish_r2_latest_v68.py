#!/usr/bin/env python3
"""Publish verified v6.8 research index to R2, including latest pointer.
Runs only after the replay and local index validation succeed.
"""
import hashlib,json,os
from datetime import datetime,timezone
from pathlib import Path
import boto3
p=Path("detector_v68_reports")
index=(p/"research_index.json").read_bytes()
summary=(p/"research_summary.md").read_bytes()
manifest=json.loads((p/"manifest.json").read_text())
report=(p/"fixed_windows.json").read_bytes()
parsed=json.loads(index)
digest=hashlib.sha256(report).hexdigest()
if manifest.get("status")!="RESEARCH_PASS" or manifest.get("reportSha256")!=digest or parsed.get("reportSha256")!=digest or parsed.get("sets")!=10:
 raise SystemExit("INDEX_PUBLISH_BLOCKED")
run=os.environ["GITHUB_RUN_ID"]
attempt=os.environ.get("GITHUB_RUN_ATTEMPT","1")
prefix=f"research/detector/v6.8/runs/{run}-{attempt}/"
if parsed.get("r2Prefix")!=prefix:raise SystemExit("PREFIX_MISMATCH")
s3=boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
bucket=os.environ["R2_BUCKET"]
def write_verified(key,data,ctype):
 checksum=hashlib.sha256(data).hexdigest()
 s3.put_object(Bucket=bucket,Key=key,Body=data,ContentType=ctype,Metadata={"sha256":checksum,"research-only":"true"})
 # Verify actual bytes, not only object metadata.
 response=s3.get_object(Bucket=bucket,Key=key)
 actual=hashlib.sha256(response["Body"].read()).hexdigest()
 if actual!=checksum:raise RuntimeError("R2_CONTENT_VERIFICATION_FAILED: "+key)
 return checksum
# First write run-scoped immutable-by-convention files. Publish pointer last.
index_hash=write_verified(prefix+"research_index.json",index,"application/json")
summary_hash=write_verified(prefix+"research_summary.md",summary,"text/markdown; charset=utf-8")
pointer={"schema":"detector-research-latest-v1","version":"6.8","researchOnly":True,"status":"RESEARCH_PASS","runId":run,"attempt":attempt,"updatedAtUTC":datetime.now(timezone.utc).isoformat(),"prefix":prefix,"reportSha256":digest,"indexSha256":index_hash,"summarySha256":summary_hash,"indexKey":prefix+"research_index.json","summaryKey":prefix+"research_summary.md","manifestKey":prefix+"manifest.json","reportKey":prefix+"fixed_windows.json","githubRunUrl":f"https://github.com/analiticprosp-ship-it/crypto-price-feed/actions/runs/{run}"}
pointer_bytes=json.dumps(pointer,ensure_ascii=False,indent=2).encode()
write_verified("research/detector/v6.8/latest.json",pointer_bytes,"application/json")
(p/"latest_pointer.json").write_bytes(pointer_bytes)
print("RESEARCH_LATEST_POINTER_VERIFIED "+json.dumps({"run":run,"prefix":prefix,"indexSha256":index_hash,"latestKey":"research/detector/v6.8/latest.json"}))
