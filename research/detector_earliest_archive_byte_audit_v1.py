#!/usr/bin/env python3
"""Independently read exact earliest HTTP-200 archives from pinned depth probe.

One bounded archive per venue/symbol/family excluding oversized aggTrades.
ZIP CRC, publisher .CHECKSUM SHA256, source CSV rows, timestamps and units.
Never treat retrospective event labels as PIT availability or continuous history.
"""
import csv
import datetime as dt
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import urllib.error
import urllib.request
import zipfile

PARENT_KEY = "research/detector-source-depth-boundary/v1/39272568024-1.json"
PARENT_SHA = "4938b03031812f2f40bd3f1b24f03d97470c84ba09554ef5d842e926d08cd0fd"
ROOT = "research/detector-earliest-archive-byte-audit/v1"
OUT = Path("detector_earliest_archive_byte_audit")
ZIP_CAP = 8_000_000
CSV_CAP = 16_000_000
ALLOWED_FAMILIES = {
    "binance_spot_1h_klines", "binance_usdm_1h_klines",
    "binance_usdm_metrics_oi", "binance_usdm_funding",
}
UTC = dt.timezone.utc

def get_limited(url, cap):
    req = urllib.request.Request(url, headers={"User-Agent": "Detector-H1H10-Archive-Byte-Audit/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = r.read(cap + 1)
    if len(data) > cap:
        raise ValueError("ARCHIVE_BYTES_EXCEED_CAP")
    return data

def parse_time(s):
    s = str(s).strip()
    if s.isdigit():
        n = int(s)
        scale = 1_000_000 if n >= 10**14 else 1000
        return dt.datetime.fromtimestamp(n / scale, UTC), "us" if scale == 1_000_000 else "ms"
    val = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    naive = val.tzinfo is None
    if naive:
        val = val.replace(tzinfo=UTC)
    return val.astimezone(UTC), "naive_assumed_UTC_LABEL_ONLY" if naive else "offset_aware"

def valid_price_row(row):
    if len(row) < 7:
        raise ValueError("KLINE_FIELDS_SHORT")
    values = [float(x) for x in row[1:5]]
    o,h,l,c = values
    if not all(math.isfinite(x) and x > 0 for x in values) or h < max(o,c,l) or l > min(o,c,h):
        raise ValueError("KLINE_OHLC_INVALID")
    return row[0]

def audit_csv(family, stamp, data):
    reader = csv.reader(io.StringIO(data.decode("utf-8-sig")))
    rows = list(reader)
    if not rows:
        raise ValueError("CSV_EMPTY")
    header = rows[0]
    if "klines" in family:
        is_header = header[0].strip().lower() in ("open_time", "opentime")
        contents = rows[1:] if is_header else rows
        time_values = [valid_price_row(x) for x in contents]
        source_units = "OHLCV_PRICE_AND_VOLUME_NATIVE_ARCHIVE"
    else:
        normalized = [x.strip().lower() for x in header]
        if family == "binance_usdm_metrics_oi":
            required = ("create_time", "sum_open_interest")
            amount = "sum_open_interest"
        else:
            required = ("calc_time", "last_funding_rate")
            amount = "last_funding_rate"
        if not all(x in normalized for x in required):
            raise ValueError("REQUIRED_CSV_FIELDS_MISSING")
        times = normalized.index(required[0]); values = normalized.index(amount)
        contents = rows[1:]
        time_values = []
        for r in contents:
            if len(r) <= max(times, values):
                raise ValueError("CSV_FIELDS_SHORT")
            n = float(r[values])
            if not math.isfinite(n) or (amount == "sum_open_interest" and n <= 0):
                raise ValueError("SOURCE_NUMERIC_VALUE_INVALID")
            time_values.append(r[times])
        source_units = "OI_EXCHANGE_NATIVE_UNIT_UNVERIFIED" if amount == "sum_open_interest" else "FUNDING_RATE_FRACTION_UNIT_TO_CONFIRM"
    if not time_values:
        raise ValueError("NO_DATA_RECORDS")
    parsed = [parse_time(t) for t in time_values]
    timestamps = [t for t,u in parsed]
    units = sorted({u for t,u in parsed})
    if timestamps != sorted(timestamps) or len(timestamps) != len(set(timestamps)):
        raise ValueError("NONMONOTONIC_OR_DUPLICATE_SOURCE_TIMESTAMPS")
    prefix = stamp if len(stamp) == 7 else stamp[:10]
    if any(not x.isoformat().startswith(prefix) for x in timestamps):
        raise ValueError("SOURCE_DATE_OUTSIDE_ARCHIVE_DATE")
    return {"rows":len(contents),"first_label_utc":timestamps[0].isoformat(),
            "last_label_utc":timestamps[-1].isoformat(),
            "source_time_unit_forms":units, "source_fields":header if family not in ("binance_spot_1h_klines","binance_usdm_1h_klines") or is_header else "NO_HEADER",
            "source_quantity_unit":source_units, "true_gap_audit": "NOT_YET_COMPLETE"}

def extract_zip(raw):
    if not zipfile.is_zipfile(io.BytesIO(raw)):
        raise ValueError("SOURCE_NOT_ZIP")
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        if z.testzip() is not None:
            raise ValueError("SOURCE_ZIP_CRC_BAD")
        members = [x for x in z.infolist() if x.filename.endswith(".csv") and
                   "/" not in x.filename and not x.is_dir()]
        if len(members) != 1 or members[0].file_size > CSV_CAP:
            raise ValueError("SOURCE_ZIP_MEMBERS_OR_SIZE_INVALID")
        return z.read(members[0]), members[0].filename

def publisher_hash(url, rawsha):
    try:
        data = get_limited(url + ".CHECKSUM", 2048).decode("ascii",errors="strict")
    except urllib.error.HTTPError as e:
        return {"status":"PUBLISHER_CHECKSUM_HTTP_" + str(e.code)}
    except Exception as e:
        return {"status":"PUBLISHER_CHECKSUM_UNVERIFIED_" + type(e).__name__}
    found = re.search(r"\b([a-fA-F0-9]{64})\b",data)
    if not found:
        return {"status":"PUBLISHER_CHECKSUM_SCHEMA_INVALID"}
    declared = found.group(1).lower()
    return {"status":"PUBLISHER_SHA256_MATCH" if declared == rawsha else "PUBLISHER_SHA256_MISMATCH",
            "declared_sha256":declared}

def audit_archive(entry):
    result = {"family":entry["family"],"symbol":entry["symbol"],
              "source_archive_date":entry["earliest_observed_http_200"],
              "archive_venue":"Binance",
              "status":"UNVERIFIED","archive_publication_time":"UNVERIFIED",
              "causal_PIT":"UNVERIFIED"}
    if not result["source_archive_date"]:
        return dict(result,status="NO_EARLY_ARCHIVE_DISCOVERED")
    import_path = entry["earliest_observed_http_200"]
    from research.detector_source_depth_boundary_v1 import path_for
    url = path_for(entry["family"],entry["symbol"],import_path)
    result["source_url"] = url
    try:
        raw = get_limited(url,ZIP_CAP)
        data, member = extract_zip(raw)
        raw_sha = hashlib.sha256(raw).hexdigest()
        validation = audit_csv(entry["family"],import_path,data)
        check = publisher_hash(url,raw_sha)
        result.update(archive_sha256=raw_sha, csv_sha256=hashlib.sha256(data).hexdigest(),
                      archive_bytes=len(raw), csv_bytes=len(data), member=member,
                      publisher_checksum=check, validation=validation)
        result["status"] = ("PUBLISHER_CRC_SCHEMA_SAMPLE_PASS" if check["status"] == "PUBLISHER_SHA256_MATCH"
                 else "LOCAL_CRC_SCHEMA_SAMPLE_ONLY" if check["status"].startswith("PUBLISHER_CHECKSUM_")
                 else "PUBLISHER_CHECKSUM_DISCREPANCY")
    except Exception as e:
        result.update(status="SOURCE_SAMPLE_ERROR",error_type=type(e).__name__,error=str(e)[:160])
    return result

def r2():
    import boto3
    return boto3.client("s3",endpoint_url="https://" + os.environ["R2_ACCOUNT_ID"] + ".r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")

def verify_r2(cli,bucket,key,expected,cap):
    obj=cli.get_object(Bucket=bucket,Key=key)
    data=obj["Body"].read(cap + 1)
    if len(data)>cap or hashlib.sha256(data).hexdigest()!=expected:
        raise ValueError("PINNED_R2_SHA256_MISMATCH")
    return data

def main():
    OUT.mkdir(exist_ok=True)
    cli=r2();bucket=os.environ["R2_BUCKET"]
    parent=json.loads(verify_r2(cli,bucket,PARENT_KEY,PARENT_SHA,3_000_000))
    if parent.get("schema")!="detector-h1h10-free-source-depth-boundary-probe-v1":
        raise ValueError("PARENT_SCHEMA_MISMATCH")
    selected=[r for r in parent["families"] if r["family"] in ALLOWED_FAMILIES]
    if len(selected)!=12:
        raise ValueError("EXPECTED_12_SERIES")
    reports=[]
    for row in selected:
        item=audit_archive(row)
        reports.append(item)
        print("EARLIEST_ARCHIVE_SAMPLE",json.dumps({
            "family":item["family"],"symbol":item["symbol"],"date":item["source_archive_date"],
            "status":item["status"],"quality":item.get("publisher_checksum",{}).get("status"),
            "rows":item.get("validation",{}).get("rows"),
            "first":item.get("validation",{}).get("first_label_utc"),
            "error":item.get("error_type")},ensure_ascii=False),flush=True)
    report={"schema":"detector-h1h10-first-archive-publisher-sha-replay-v1",
            "status":"SAMPLE_EVIDENCE_ONLY_NOT_FULL_CONTINUITY",
            "input_report_key":PARENT_KEY,"input_report_sha256":PARENT_SHA,
            "series":reports,"count":len(reports),"research_only":True,
            "original_exchange_publication":"UNVERIFIED","causal_PIT":"UNVERIFIED",
            "limitations":[
              "Only earliest observed HTTP200 sample, not all months/days",
              "No complete temporal coverage or value revisions established",
              "Naive OI labels converted to UTC only for comparison, not availability",
              "Original historical funding rate and OI units not inferred from column names",
              "aggTrades excluded to avoid oversized downloads; price-flow not joined",
              "No trading or production signal permission"],
            "run_id":os.environ.get("GITHUB_RUN_ID")}
    blob=json.dumps(report,ensure_ascii=False,sort_keys=True,indent=2).encode()
    sha=hashlib.sha256(blob).hexdigest()
    key=ROOT+"/"+str(os.environ["GITHUB_RUN_ID"])+"-"+str(os.environ.get("GITHUB_RUN_ATTEMPT","1"))+".json"
    cli.put_object(Bucket=bucket,Key=key,Body=blob,ContentType="application/json",Metadata={"sha256":sha})
    if verify_r2(cli,bucket,key,sha,len(blob)+1)!=blob:
        raise ValueError("WRITEBACK_BYTE_MISMATCH")
    (OUT/"report.json").write_bytes(blob)
    print("EARLIEST_ARCHIVE_AUDIT_SUMMARY",json.dumps({
        "sample_count":len(reports),"publisher_verified":sum(x["status"]=="PUBLISHER_CRC_SCHEMA_SAMPLE_PASS" for x in reports),
        "local_only":sum(x["status"]=="LOCAL_CRC_SCHEMA_SAMPLE_ONLY" for x in reports),
        "errors":sum(x["status"] in ("SOURCE_SAMPLE_ERROR","PUBLISHER_CHECKSUM_DISCREPANCY") for x in reports),
        "r2_key":key,"sha256":sha,"edge_status":"EDGE_UNVALIDATED"},ensure_ascii=False))
    if any(x["status"] in ("SOURCE_SAMPLE_ERROR","PUBLISHER_CHECKSUM_DISCREPANCY") for x in reports):
        raise SystemExit(2)

if __name__=="__main__":
    main()
