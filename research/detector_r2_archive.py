#!/usr/bin/env python3
"""Bounded incremental GitHub Actions research artifact sync to private R2.

Skips successfully completed historical runs whose artifacts were NEVER
uploaded or already expired. These are NOT new transfer failures. Fails
closed on GitHub/R2/ZIP/credentials/hash/partial-page errors. Each permanent
artifact and manifest is read back by SHA256. No execution authority.
"""
import datetime as dt
import hashlib
import io
import json
import os
import sys
import urllib.request
import zipfile

import boto3
from detector_github_artifacts import fetch_artifact_zip
from detector_archive_policy import (
    MAX_ARTIFACT_BYTES,MAX_PAGES,artifact_plan,
    is_research_candidate,no_artifact_classification,select_since_cursor)

REPO=os.environ["GITHUB_REPOSITORY"]
TOKEN=os.environ["GH_READ_TOKEN"]
BUCKET=os.environ["R2_BUCKET"]
ACCOUNT=os.environ["R2_ACCOUNT_ID"]
UTC=dt.timezone.utc

def api(path):
    req=urllib.request.Request("https://api.github.com/repos/"+REPO+path,
        headers={"Authorization":"Bearer "+TOKEN,
                 "Accept":"application/vnd.github+json",
                 "User-Agent":"detector-r2-bounded-sync-v2"})
    with urllib.request.urlopen(req,timeout=35) as response:
        return json.load(response)

def digest(blob):return hashlib.sha256(blob).hexdigest()

# First successful v2 scan examined every available run through this run id;
# its archived source report is still tagged SYNC_PARTIAL because it did not
# exhaust the arbitrary 7-day lookback. Avoid pretending an older history sync.
BOOTSTRAP_RUN_ID=39205092827
CURSOR_KEY="research/detector-h1h10-archive-cursor/v3/latest.json"

def sync():
    now=dt.datetime.now(UTC)
    s3=boto3.client("s3",
       endpoint_url="https://"+ACCOUNT+".r2.cloudflarestorage.com",
       aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
       aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
       region_name="auto")
    def exists(key):
        try:
            s3.head_object(Bucket=BUCKET,Key=key)
            return True
        except s3.exceptions.ClientError as e:
            if e.response.get("Error",{}).get("Code") in ("404","NoSuchKey","NotFound"):
                return False
            raise
    def get_json(key,limit=2_000_000):
        return json.loads(s3.get_object(Bucket=BUCKET,Key=key)["Body"].read(limit))
    def write_verified(key,payload,media="application/json"):
        sha=digest(payload)
        s3.put_object(Bucket=BUCKET,Key=key,Body=payload,
                      ContentType=media,Metadata={"sha256":sha})
        obj=s3.get_object(Bucket=BUCKET,Key=key)
        stored=obj["Body"].read(len(payload)+1)
        if stored!=payload or digest(stored)!=sha:
            raise ValueError("R2_BYTE_READBACK_OR_SHA_MISMATCH")
        return sha
    def freeze_json(key,record):
        b=json.dumps(record,ensure_ascii=False,sort_keys=True,indent=2).encode()
        return write_verified(key,b)
    # Resume from a SHA-readback checked high-water mark. Scan only run IDs
    # strictly newer than the cursor; this also catches runs with a large
    # delay between GitHub creation and the next daily execution.
    previous_cursor=BOOTSTRAP_RUN_ID
    cursor_source="VERIFIED_V2_PAGE6_BOOTSTRAP_2026_10_20"
    if exists(CURSOR_KEY):
        response=s3.get_object(Bucket=BUCKET,Key=CURSOR_KEY)
        payload=response["Body"].read(100_000)
        expected=response.get("Metadata",{}).get("sha256","")
        if digest(payload)!=expected:
            raise ValueError("CURSOR_R2_SHA_MISMATCH")
        previous_doc=json.loads(payload)
        if (previous_doc.get("schema")!="detector-archive-verified-cursor-v3"
           or not isinstance(previous_doc.get("last_processed_run_id"),int)
           or previous_doc["last_processed_run_id"]<BOOTSTRAP_RUN_ID):
            raise ValueError("CURSOR_FORMAT_OR_ORDER_MISMATCH")
        previous_cursor=previous_doc["last_processed_run_id"]
        cursor_source="PREVIOUS_SHA_VERIFIED_CURSOR"
    runs=[];complete_scan=False;pages=0;newest_seen=previous_cursor
    for page in range(1,MAX_PAGES+1):
        response=api(f"/actions/runs?per_page=100&page={page}")
        batch=response.get("workflow_runs")
        if not isinstance(batch,list):raise ValueError("GITHUB_RUN_API_SCHEMA_INVALID")
        pages=page
        filtered,reached=select_since_cursor(batch,previous_cursor)
        runs.extend(filtered)
        if batch and page==1:
            newest_seen=max(newest_seen,batch[0]["id"])
        if reached or len(batch)<100:
            complete_scan=True
            break
    candidates=sorted((r for r in runs if is_research_candidate(r)),
                      key=lambda x:x["id"])
    published=[];already=[];benign=[];failed=[];verified_artifacts=0;verified_bytes=0
    for run in candidates:
        run_id=run["id"]
        manifest_key=f"research/{run_id}/manifest.json"
        skipped_key=f"research/archive-skipped-v2/{run_id}.json"
        if exists(manifest_key):
            already.append(run_id)
            continue
        if exists(skipped_key):
            benign.append({"run_id":run_id,"classification":get_json(skipped_key)["classification"],
                           "previously_classified":True})
            continue
        try:
            data=api(f"/actions/runs/{run_id}/artifacts?per_page=100")
            artifacts=data.get("artifacts")
            total=data.get("total_count",0)
            if not isinstance(total,int) or total>100:
                raise ValueError("GITHUB_ARTIFACT_PAGINATION_UNVERIFIED")
            if not isinstance(artifacts,list) or len(artifacts)!=total:
                raise ValueError("GITHUB_ARTIFACT_RESULT_MISMATCH")
            eligible,skipped=artifact_plan(artifacts)
            if not eligible:
                reason=no_artifact_classification(artifacts,skipped)
                freeze_json(skipped_key,{"schema":"detector-archive-skip-v2",
                    "run_id":run_id,"workflow":run["name"],
                    "classification":reason,"skipped_artifacts":skipped,
                    "checked_at_utc":now.isoformat(),
                    "scope":"RESEARCH_ONLY","not_a_successful_upload":True})
                benign.append({"run_id":run_id,"classification":reason})
                continue
            records=[]
            for art in eligible:
                blob=fetch_artifact_zip(art["archive_download_url"],
                       TOKEN,MAX_ARTIFACT_BYTES)
                with zipfile.ZipFile(io.BytesIO(blob)) as z:
                    if z.testzip() is not None:
                        raise ValueError("CORRUPT_SOURCE_ARTIFACT_ZIP")
                object_key=f"research/{run_id}/{art['id']}-{art['name']}.zip"
                sha=write_verified(object_key,blob,media="application/zip")
                verified_artifacts+=1;verified_bytes+=len(blob)
                records.append({"name":art["name"],"artifact_id":art["id"],
                    "key":object_key,"bytes":len(blob),"sha256":sha})
            manifest={"schema":"detector-research-r2-v2","run_id":run_id,
                "workflow":run["name"],"head_sha":run["head_sha"],
                "completed_at":run["updated_at"],"archived_at":now.isoformat(),
                "artifacts":records,"skipped_artifacts":skipped,
                "completeness":"PARTIAL_ELIGIBLE_ARTIFACTS_ONLY" if skipped else "ALL_ELIGIBLE_ARTIFACTS_VERIFIED",
                "source_scope":"RESEARCH_ONLY","trading_permission":False}
            freeze_json(manifest_key,manifest)
            published.append(run_id)
        except Exception as e:
            failed.append({"run_id":run_id,"type":type(e).__name__,
                           "error":str(e)[:180]})
            print("ARCHIVE_TRANSFER_FAILURE",run_id,type(e).__name__,flush=True)
    complete=sorted(set(published+already))
    if complete:
        newest=complete[-1]
        latest_key="research/latest.json"
        current=-1
        if exists(latest_key):
            current=int(get_json(latest_key).get("run_id",-1))
        if newest>current:
            newmanifest=get_json(f"research/{newest}/manifest.json")
            freeze_json(latest_key,newmanifest)
    status="SYNC_COMPLETE" if complete_scan and not failed else "SYNC_PARTIAL"
    if status=="SYNC_COMPLETE":
        # Persist only after all newly discovered runs are reconciled without
        # download failures; the next invocation may safely skip these run IDs.
        freeze_json(CURSOR_KEY,{
            "schema":"detector-archive-verified-cursor-v3",
            "last_processed_run_id":newest_seen,
            "previous_processed_run_id":previous_cursor,
            "established_at_utc":now.isoformat(),
            "bootstrap_basis":"verified scan through 39205092827 from 39382155529",
            "research_only":True})
    summary={"schema":"detector-h1h10-incremental-r2-sync-v3",
      "status":status,"created_at_utc":now.isoformat(),
      "policy":{"previous_cursor_run_id":previous_cursor,"cursor_source":cursor_source,"max_pages":MAX_PAGES},
      "pages_scanned":pages,"coverage_since_cursor_complete":complete_scan,
      "newest_run_id_scanned":newest_seen,"updated_cursor_if_success":newest_seen if status=="SYNC_COMPLETE" else None,
      "research_runs_examined":len(candidates),
      "newly_archived":published,"already_archived_count":len(already),
      "benign_skips":benign,"real_failures":failed,
      "verified_new_artifacts":verified_artifacts,
      "verified_new_bytes":verified_bytes,
      "latest_verified_run_id":complete[-1] if complete else None,
      "scope":"RESEARCH_ONLY","trading_actions":False}
    key=f"research/detector-h1h10-archive-sync-status/v3/{os.environ['GITHUB_RUN_ID']}-{os.environ.get('GITHUB_RUN_ATTEMPT','1')}.json"
    stamp=freeze_json(key,summary)
    print("DETECTOR_ARCHIVE_SYNC_V3",json.dumps({"status":status,
       "published":len(published),"existing":len(already),
       "benign_skips":len(benign),"real_failures":len(failed),
       "pages":pages,"coverage_complete":complete_scan,
       "r2_key":key,"sha256":stamp},ensure_ascii=False),flush=True)
    location=os.environ.get("GITHUB_STEP_SUMMARY")
    if location:
        with open(location,"a",encoding="utf-8") as f:
            f.write("## H1-H10 incremental R2 archive\n\n")
            f.write(f"- Status: {status}\n- New archive runs: {len(published)}\n")
            f.write(f"- Previously archived: {len(already)}\n")
            f.write(f"- Benign missing/expired source artifact runs: {len(benign)}\n")
            f.write(f"- Real transfer failures: {len(failed)}\n")
            f.write(f"- SHA-readback checked objects: {verified_artifacts}\n")
            f.write(f"- Audit report: \`{key}\`\n")
    if failed or not complete_scan:sys.exit(2)

if __name__=="__main__":
    sync()
