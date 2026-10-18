#!/usr/bin/env python3
"""Publish approved completed research Actions artifacts to private Cloudflare R2.
Fail closed. No credentials printed. Requires scoped bucket credentials in GitHub Secrets.
"""
import datetime as dt,hashlib,io,json,os,sys,urllib.request,zipfile
import boto3
from detector_github_artifacts import fetch_artifact_zip
REPO=os.environ["GITHUB_REPOSITORY"]
TOKEN=os.environ["GH_READ_TOKEN"]
BUCKET=os.environ["R2_BUCKET"]
ACCOUNT=os.environ["R2_ACCOUNT_ID"]
ALLOWED={
 "Detector H1-H10 Source Timestamp Semantics",
 "Detector H1-H10 AsOf Timing Audit",
 "Detector H1-H10 Flow OI AsOf Join Audit",
 "Detector H1-H10 Three-Day Real AggTrades Expansion",
 "Detector H1-H10 Real AggTrades 5m Pilot",
}
MAX_ARTIFACT=80_000_000
def api(path):
 req=urllib.request.Request("https://api.github.com/repos/"+REPO+path,headers={"Authorization":"Bearer "+TOKEN,"Accept":"application/vnd.github+json","User-Agent":"detector-r2-archive"})
 with urllib.request.urlopen(req,timeout=30) as r:return json.load(r)
# Incremental bounded sync of all allowlisted completed runs, not just the newest.
# Run identity is immutable; latest points to the newest successfully archived run.
runs=[]
history_scan_exhausted=False
for page in range(1,101):
 # Unfiltered Actions listing avoids GitHub status-search 1000-result cutoff.
 batch=api(f"/actions/runs?per_page=100&page={page}")["workflow_runs"]
 runs.extend(batch)
 if len(batch)<100:
  history_scan_exhausted=True
  break
OPERATIONAL_WORKFLOWS = {
 "Detector H1-H10 Research R2 Archive",
 "Detector H1-H10 Independent R2 Integrity Audit",
 "Detector H1-H10 Live OI Availability Research",
}
candidates=sorted((r for r in runs if r.get("name","").startswith("Detector H1-H10 ") and r.get("name") not in OPERATIONAL_WORKFLOWS and r.get("head_branch")=="main" and r.get("conclusion")=="success"),key=lambda x:x["id"])
if not candidates:raise SystemExit("No approved successful research workflow found")
s3=boto3.client("s3",endpoint_url="https://"+ACCOUNT+".r2.cloudflarestorage.com",aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
def exists(key):
 try:s3.head_object(Bucket=BUCKET,Key=key);return True
 except s3.exceptions.ClientError as e:
  if e.response.get("Error",{}).get("Code") in ("404","NoSuchKey","NotFound"):return False
  raise
def get_json(key):
 return json.loads(s3.get_object(Bucket=BUCKET,Key=key)["Body"].read())
published=[];skipped=[];failed=[];verified_artifacts=0;verified_bytes=0
for run in candidates:
 rid=run["id"];key=f"research/{rid}/manifest.json"
 if exists(key):
  skipped.append(rid);continue
 try:
  artifacts=api(f"/actions/runs/{rid}/artifacts?per_page=100")["artifacts"]
  records=[]
  for art in artifacts:
   if art.get("expired") or art["size_in_bytes"]>MAX_ARTIFACT:continue
   blob=fetch_artifact_zip(art["archive_download_url"],TOKEN,MAX_ARTIFACT)
   with zipfile.ZipFile(io.BytesIO(blob)) as z:
    if z.testzip() is not None:raise ValueError("corrupt artifact zip")
   object_key=f"research/{rid}/{art['id']}-{art['name']}.zip"
   digest=hashlib.sha256(blob).hexdigest()
   s3.put_object(Bucket=BUCKET,Key=object_key,Body=blob,ContentType="application/zip",Metadata={"sha256":digest})
   # Strong readback verification, not just successful HTTP PUT.
   verify=s3.get_object(Bucket=BUCKET,Key=object_key)["Body"].read()
   if hashlib.sha256(verify).hexdigest()!=digest:raise ValueError("R2 readback checksum mismatch")
   verified_artifacts+=1;verified_bytes+=len(verify)
   records.append({"name":art["name"],"artifact_id":art["id"],"key":object_key,"bytes":len(blob),"sha256":digest})
  if not records:raise ValueError("no usable non-expired artifacts")
  manifest={"schema":"detector-research-r2-v1","run_id":rid,"workflow":run["name"],"head_sha":run["head_sha"],"completed_at":run["updated_at"],"published_at":dt.datetime.now(dt.timezone.utc).isoformat(),"artifacts":records,"access":"private","note":"Research only; no trading changes"}
  data=json.dumps(manifest,ensure_ascii=False,indent=2).encode()
  s3.put_object(Bucket=BUCKET,Key=key,Body=data,ContentType="application/json")
  if get_json(key)["run_id"]!=rid:raise ValueError("manifest readback mismatch")
  published.append(rid)
 except Exception as e:
  failed.append({"run_id":rid,"error":str(e)[:200]})
  print("RUN_FAILED",rid,type(e).__name__,flush=True)
# Never regress latest pointer when reprocessing historical runs.
all_complete=sorted(set(published+skipped))
if all_complete:
 newest=all_complete[-1]
 latest_key="research/latest.json"
 current_id=-1
 if exists(latest_key):
  current_id=int(get_json(latest_key).get("run_id",-1))
 if newest>current_id:
  newmanifest=get_json(f"research/{newest}/manifest.json")
  s3.put_object(Bucket=BUCKET,Key=latest_key,Body=json.dumps(newmanifest,ensure_ascii=False,indent=2).encode(),ContentType="application/json")
  if get_json(latest_key)["run_id"]!=newest:raise ValueError("latest readback mismatch")
summary={"status":"SYNC_COMPLETE" if not failed and history_scan_exhausted else "SYNC_PARTIAL","published":published,"already_archived":len(skipped),"failed":failed,"latest_run_id":max(all_complete) if all_complete else None,"scanned_runs":len(runs),"history_scan_exhausted":history_scan_exhausted,"verified_artifacts":verified_artifacts,"verified_bytes":verified_bytes}
print(json.dumps(summary,ensure_ascii=False),flush=True)
# Compact non-sensitive status, including failure; no credentials in report.
summary_path=os.environ.get("GITHUB_STEP_SUMMARY")
if summary_path:
 with open(summary_path,"a",encoding="utf-8") as fp:
  fp.write("## H1-H10 R2 archive sync\n\n")
  fp.write(f"- Status: {summary['status']}\n- Newly archived: {len(published)}\n- Already archived: {len(skipped)}\n- Failed: {len(failed)}\n- Latest run ID: {summary['latest_run_id']}\n- Full history scan: {history_scan_exhausted}\n- Verified new artifacts: {verified_artifacts}\n- SHA256-verified bytes: {verified_bytes}\n")
if failed or not history_scan_exhausted:sys.exit(2)
