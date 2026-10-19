#!/usr/bin/env python3
"""Read-only SHA/CRC forensic audit of 19 already-archived R2 candidate ZIPs.

Never turn ZIP file names, source event timestamps or historical OI labels into
causal exchange-publication proof. No downloads from exchanges, no paid data.
"""
import collections
import csv
import datetime as dt
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import zipfile

import boto3
from research.detector_h1_h10_r2_source import safe_members

CENSUS_KEY="research/detector-archive-candidate-census/v1/39218249173-1.json"
CENSUS_SHA="0139715d8cd3a6af7abb9d2933504cdc1cd8cf0502cdaeeed51a3d3cc92dc996"
ROOT="research/detector-archive-candidate-content-audit/v1"
OUT=Path("detector_archive_candidate_content_audit")
OUT.mkdir(exist_ok=True)
MAX_ZIP=80_000_000
MAX_ALL_COMPRESSED=500_000_000
MAX_MEMBER_COUNT=150
MAX_UNCOMPRESSED_PER_ZIP=450_000_000
MAX_CSV_ROWS=500_000
MAX_JSON_PREVIEW_BYTES=140_000
EXPECTED_CANDIDATES=19
PIT_WARNING="SOURCE_EVENT_OR_ZIP_TIME_IS_NOT_FIRST_PUBLICATION_TIME"

def digest(b):return hashlib.sha256(b).hexdigest()

def get_verified(s3,bucket,key,expected,limit):
    if not re.fullmatch("[0-9a-f]{64}",expected):
        raise ValueError("PINNED_SHA_INVALID")
    response=s3.get_object(Bucket=bucket,Key=key)
    size=int(response.get("ContentLength",-1))
    if not 0<size<=limit:raise ValueError("BOUNDED_SOURCE_SIZE_INVALID")
    b=response["Body"].read(limit+1)
    if len(b)!=size or digest(b)!=expected:
        raise ValueError("SOURCE_BYTE_SHA_MISMATCH")
    meta=response.get("Metadata",{}).get("sha256","").lower()
    if meta and meta!=expected:raise ValueError("SOURCE_METADATA_SHA_MISMATCH")
    return b

def timestamp(raw):
    if not raw:return None
    try:
        if raw.isdigit():
            n=int(raw)
            if n>=10**15:n/=1_000_000
            elif n>=10**12:n/=1000
            else:return None
            return dt.datetime.fromtimestamp(n,dt.timezone.utc)
        t=dt.datetime.fromisoformat(raw.replace("Z","+00:00"))
        if t.tzinfo is None or t.utcoffset()!=dt.timedelta(0):return None
        return t
    except (ValueError,OverflowError,OSError):
        return None

def oi_columns(header):
    names=set(header)
    if not ("timestamp_utc" in names or "timestamp" in names or "create_time" in names):
        return None
    cols=("sum_open_interest","open_interest","sumOpenInterest",
          "openInterest","oi")
    return next((x for x in cols if x in names),None)

def audit_oi_csv(z,member):
    """Fully scan bounded numeric 5m OI rows, day continuity is only EVENT LABEL."""
    with z.open(member) as raw:
        rd=csv.DictReader(io.TextIOWrapper(raw,encoding="utf-8-sig",newline=""))
        headers=rd.fieldnames or []
        oi=oi_columns(headers)
        if not oi:return {"kind":"CSV_NOT_OI_SERIES","headers":headers[:45]}
        timecol=next(x for x in ("timestamp_utc","timestamp","create_time") if x in headers)
        validity=oi+"_valid" if oi+"_valid" in headers else None
        counts=collections.Counter();aligned_counts=collections.Counter();seen=set()
        rows=valid=bad_ts=bad_value=duplicates=0
        first=last=None
        for row in rd:
            rows+=1
            if rows>MAX_CSV_ROWS:raise ValueError("CSV_ROWS_LIMIT")
            t=timestamp((row.get(timecol) or "").strip())
            if t is None:
                bad_ts+=1;continue
            s=row.get(oi,"")
            try:
                value=float(s)
                is_valid=math.isfinite(value) and value>=0
                if validity:is_valid=is_valid and row.get(validity) in ("1","true","True")
            except (ValueError,TypeError):
                is_valid=False
            if not is_valid:
                bad_value+=1;continue
            key=int(t.timestamp())
            if key in seen:duplicates+=1;continue
            seen.add(key);valid+=1
            counts[t.date().isoformat()]+=1
            if t.minute%5==0 and t.second==0 and t.microsecond==0:
                aligned_counts[t.date().isoformat()]+=1
            first=min(first,t) if first else t
            last=max(last,t) if last else t
        if not rows:return {"kind":"OI_VALUES_EMPTY","headers":headers[:45]}
        # A verified full 5m day must have all 288 distinct minute labels at 5m alignment.
        # Duplicate/irregular rows are not silently corrected.
        full_days=sorted(day for day,count in counts.items() if count==288 and aligned_counts[day]==288)
        streak=0;best=0;previous=None
        for day in full_days:
            d=dt.date.fromisoformat(day)
            streak=streak+1 if previous and d-previous==dt.timedelta(days=1) else 1
            best=max(best,streak);previous=d
        return {"kind":"OI_NUMERIC_EVENT_TIME_SERIES",
                "oi_col":oi,"time_col":timecol,"validity_col":validity,
                "rows":rows,"unique_numeric_observations":valid,
                "bad_timestamp":bad_ts,"invalid_or_masked_oi":bad_value,
                "duplicate_event_labels":duplicates,"first_event_utc":first.isoformat() if first else None,
                "last_event_utc":last.isoformat() if last else None,
                "observed_days":len(counts),"full_event_label_days":len(full_days),
                "max_consecutive_288_label_days":best,
                "candidate_7day_event_label_streak":best>=7,
                "original_source_publication":"UNVERIFIED",
                "real_asof_decision_ready":"NOT_PROVEN",
                "coverage_only":"EVENT_LABELS_NOT_FIRST_AVAILABLE"}

def audit_json(z,member):
    if member.file_size>MAX_JSON_PREVIEW_BYTES:
        return {"kind":"JSON_LARGE_NOT_FULLY_PARSED","bytes":member.file_size}
    try:
        v=json.loads(z.read(member))
    except (ValueError,UnicodeError):
        return {"kind":"JSON_PARSE_INVALID"}
    if isinstance(v,dict):
        keys=sorted(map(str,v.keys()))
        return {"kind":"JSON_STRUCTURED_REPORT_OR_DATA_UNCLASSIFIED",
                "top_keys":keys[:50],"schema":str(v.get("schema",""))[:120],
                "reported_status":str(v.get("status",""))[:120],
                "must_not_infer_oi_history":True}
    return {"kind":"JSON_OTHER","top_type":type(v).__name__}

def inspect_archive(blob,metadata):
    if len(blob)!=metadata["archive_bytes"] or digest(blob)!=metadata["archive_expected_sha256"]:
        raise ValueError("ARCHIVE_SHA_OR_LENGTH_MISMATCH")
    output={"run_id":metadata["run_id"],"workflow":metadata["workflow"],
            "artifact_name":metadata["artifact_name"],
            "archive_object_key":metadata["archive_object_key"],
            "archive_expected_sha256":metadata["archive_expected_sha256"],
            "archive_bytes":len(blob),
            "archive_integrity":"SHA256_AND_ZIP_CRC_VERIFIED",
            "archive_original_first_publication":"UNVERIFIED",
            "files":[]}
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        members=safe_members(z)
        if len(members)>MAX_MEMBER_COUNT:
            raise ValueError("ZIP_TOO_MANY_MEMBERS")
        if sum(x.file_size for x in members)>MAX_UNCOMPRESSED_PER_ZIP:
            raise ValueError("ZIP_UNCOMPRESSED_LIMIT")
        if z.testzip() is not None:raise ValueError("ZIP_CRC_INVALID")
        for member in members:
            if member.is_dir():continue
            name=member.filename
            rec={"name":name,"uncompressed_bytes":member.file_size}
            if name.lower().endswith(".csv"):
                rec.update(audit_oi_csv(z,member))
            elif name.lower().endswith(".json"):
                rec.update(audit_json(z,member))
            else:
                rec["kind"]="NON_CSV_JSON_FILE"
            output["files"].append(rec)
    series=[x for x in output["files"] if x["kind"]=="OI_NUMERIC_EVENT_TIME_SERIES"]
    output["observed_oi_series"]=len(series)
    output["max_consecutive_288_event_label_days"]=max(
        (x["max_consecutive_288_label_days"] for x in series),default=0)
    output["contains_7day_event_label_candidate"]=any(
        x["candidate_7day_event_label_streak"] for x in series)
    output["candidate_7day_first_publication_verified"]=False
    return output

def summarize(records):
    eligible=[x for x in records if x.get("archive_integrity")=="SHA256_AND_ZIP_CRC_VERIFIED"]
    files=[r for v in eligible for r in v["files"]]
    source=[r for r in files if r["kind"]=="OI_NUMERIC_EVENT_TIME_SERIES"]
    return {
      "archived_candidate_count":len(records),
      "archives_sha256_crc_pass":len(eligible),
      "archives_with_errors":len(records)-len(eligible),
      "files_examined":len(files),
      "actual_numeric_oi_csv_series":len(source),
      "oi_csv_event_label_streak_gte_7":sum(x["candidate_7day_event_label_streak"] for x in source),
      "max_oi_event_label_streak_in_one_file":max(
           (x["max_consecutive_288_label_days"] for x in source),default=0),
      "continuous_7day_publication_verified":False,
      "note":"ZIP contents may expose event-labelled series, never original first-available time"}

def main():
    bucket=os.environ["R2_BUCKET"]
    s3=boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
       aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
       aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
    census=json.loads(get_verified(s3,bucket,CENSUS_KEY,CENSUS_SHA,1_000_000))
    if census.get("schema")!="detector-existing-research-r2-archive-census-v1":
        raise ValueError("PINNED_CENSUS_SCHEMA_INVALID")
    candidates=census["candidate_artifacts"]
    if len(candidates)!=EXPECTED_CANDIDATES or len({x["archive_object_key"] for x in candidates})!=len(candidates):
        raise ValueError("PINNED_CANDIDATE_SET_CHANGED")
    total=sum(x["archive_bytes"] for x in candidates)
    if total>MAX_ALL_COMPRESSED:
        raise ValueError("BOUNDED_CANDIDATE_TOTAL_TOO_LARGE")
    records=[]
    for meta in candidates:
        try:
            blob=get_verified(s3,bucket,meta["archive_object_key"],
                meta["archive_expected_sha256"],MAX_ZIP)
            item=inspect_archive(blob,meta)
            records.append(item)
            print("ARCHIVE_CONTENT_AUDIT_ROW",json.dumps({
                "run_id":item["run_id"],"artifact":item["artifact_name"],
                "integrity":item["archive_integrity"],"oi_series":item["observed_oi_series"],
                "max_oi_288_day_streak":item["max_consecutive_288_event_label_days"],
                "member_types":[x["kind"] for x in item["files"]][:12]},ensure_ascii=False),flush=True)
        except Exception as exc:
            records.append({"run_id":meta["run_id"],"workflow":meta["workflow"],
               "artifact_name":meta["artifact_name"],"archive_object_key":meta["archive_object_key"],
               "archive_integrity":"UNVERIFIED_ERROR","error_type":type(exc).__name__,
               "error":str(exc)[:160]})
    totals=summarize(records)
    report={
      "schema":"detector-h1h10-existing-archive-content-forensics-v1",
      "status":"ARCHIVE_CONTENT_AUDIT_PASS" if totals["archives_with_errors"]==0
               else "ARCHIVE_CONTENT_AUDIT_PARTIAL",
      "pinned_census":CENSUS_KEY,"pinned_census_sha256":CENSUS_SHA,
      "coverage_not_claimed":"19 name-selected R2 archives only; no assumption about unrelated artifacts",
      "items":records,"summary":totals,
      "hard_limitations":[
        PIT_WARNING,
        "Even a 7-day 5m source-event-label streak is not a vendor receipt or venue publication proof",
        "A metadata/report-only artifact is not an independent OI history measurement",
        "Other non-candidate R2 ZIPs were not inspected here",
        "No free current-year continuous original venue publish-time OI guaranteed"],
      "research_only":True,"trade_actions":False,"edge_status":"EDGE_UNVALIDATED",
      "run_id":os.environ["GITHUB_RUN_ID"],"source_commit":os.environ.get("GITHUB_SHA")}
    result=json.dumps(report,ensure_ascii=False,sort_keys=True,indent=2).encode()
    sha256=digest(result)
    key=ROOT+"/"+report["run_id"]+"-"+os.environ.get("GITHUB_RUN_ATTEMPT","1")+".json"
    s3.put_object(Bucket=bucket,Key=key,Body=result,ContentType="application/json",
                  Metadata={"sha256":sha256})
    obj=s3.get_object(Bucket=bucket,Key=key)
    if digest(obj["Body"].read(len(result)+1))!=sha256:
        raise ValueError("R2_AUDIT_WRITE_READBACK_MISMATCH")
    (OUT/"report.json").write_text(json.dumps({**report,"r2_key":key,
        "r2_sha256":sha256},ensure_ascii=False,indent=2),encoding="utf-8")
    print("ARCHIVE_CONTENT_AUDIT_SUMMARY",json.dumps({
        "status":report["status"],"summary":totals,"r2_key":key,
        "sha256":sha256,"edge_status":"EDGE_UNVALIDATED"},ensure_ascii=False),flush=True)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"],"a",encoding="utf-8") as f:
            f.write("## Detector H1-H10 archived candidate ZIP contents audit\n\n")
            f.write(f"- Archived ZIP SHA+CRC: {totals['archives_sha256_crc_pass']}/{totals['archived_candidate_count']}\n")
            f.write(f"- Actual 5m OI-labelled CSV series: {totals['actual_numeric_oi_csv_series']}\n")
            f.write(f"- Max 5m event-labelled continuous full-day streak: {totals['max_oi_event_label_streak_in_one_file']} days\n")
            f.write("- Source original publish-time proof: UNVERIFIED\n")
    if totals["archives_with_errors"]:
        raise SystemExit(2)

if __name__=="__main__":main()
