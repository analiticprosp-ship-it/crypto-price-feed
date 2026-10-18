#!/usr/bin/env python3
"""Publish approved completed research Actions artifacts to private Cloudflare R2.
Fail closed. No credentials printed. Requires scoped bucket credentials in GitHub Secrets.
"""
import datetime as dt,hashlib,io,json,os,sys,urllib.request,zipfile
import boto3
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
runs=api("/actions/runs?status=success&per_page=100")["workflow_runs"]
candidates=[r for r in runs if r.get("name") in ALLOWED and r.get("head_branch")=="main" and r.get("conclusion")=="success"]
if not candidates:raise SystemExit("No approved successful research workflow found")
run=max(candidates,key=lambda x:x["id"])
artifacts=api("/actions/runs/"+str(run["id"])+"/artifacts?per_page=100")["artifacts"]
s3=boto3.client("s3",endpoint_url="https://"+ACCOUNT+".r2.cloudflarestorage.com",aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
records=[]
for art in artifacts:
 if art.get("expired") or art["size_in_bytes"]>MAX_ARTIFACT:continue
 url=art["archive_download_url"]
 req=urllib.request.Request(url,headers={"Authorization":"Bearer "+TOKEN,"Accept":"application/vnd.github+json","User-Agent":"detector-r2-archive"})
 with urllib.request.urlopen(req,timeout=120) as response:
  buf=io.BytesIO()
  while True:
   chunk=response.read(1048576)
   if not chunk:break
   if buf.tell()+len(chunk)>MAX_ARTIFACT:raise ValueError("artifact_exceeded_size_limit")
   buf.write(chunk)
 blob=buf.getvalue()
 with zipfile.ZipFile(io.BytesIO(blob)) as z:
  if z.testzip() is not None:raise ValueError("corrupt artifact zip")
 key=f"research/{run['id']}/{art['id']}-{art['name']}.zip"
 digest=hashlib.sha256(blob).hexdigest()
 s3.put_object(Bucket=BUCKET,Key=key,Body=blob,ContentType="application/zip",Metadata={"sha256":digest})
 records.append({"name":art["name"],"artifact_id":art["id"],"key":key,"bytes":len(blob),"sha256":digest})
if not records:raise SystemExit("No acceptable research artifacts")
manifest={"schema":"detector-research-r2-v1","run_id":run["id"],"workflow":run["name"],"head_sha":run["head_sha"],"completed_at":run["updated_at"],"published_at":dt.datetime.now(dt.timezone.utc).isoformat(),"artifacts":records,"access":"private","note":"Research results only; trading unchanged"}
data=json.dumps(manifest,ensure_ascii=False,indent=2).encode()
s3.put_object(Bucket=BUCKET,Key=f"research/{run['id']}/manifest.json",Body=data,ContentType="application/json")
s3.put_object(Bucket=BUCKET,Key="research/latest.json",Body=data,ContentType="application/json")
print(json.dumps({"status":"PUBLISHED","run_id":run["id"],"workflow":run["name"],"artifact_count":len(records),"latest_key":"research/latest.json"}))
