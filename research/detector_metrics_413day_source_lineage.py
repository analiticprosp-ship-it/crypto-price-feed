#!/usr/bin/env python3
"""Reconstruct lineage of 413-day Binance 5m OI metric labels from archived R2 ZIPs.

Source ZIP -> masked dataset ZIP -> sorted-masked dataset ZIP, all SHA256 and
ZIP CRC verified. Compare full per-symbol OI labels and numeric values without
ever upgrading Binance 'create_time' into measured publication timestamp.
"""
import collections,csv,datetime as dt,hashlib,io,json,math,os,zipfile
from pathlib import Path
import boto3
from research.detector_h1_h10_r2_source import safe_members
from research.detector_h1h10_archived_candidate_content_audit import (
 CENSUS_KEY,CENSUS_SHA,get_verified,digest,audit_oi_csv,MAX_ZIP
)

OUT=Path("detector_metrics_413day_provenance")
OUT.mkdir(exist_ok=True)
ROOT="research/detector-metrics-413day-source-lineage/v1"
SORTED_RUN=39124177387
SYMBOLS=("BTCUSDT","ETHUSDT","SOLUSDT")
MAX_EXTRACTED=450_000_000
MAX_RAW_CSV_ROWS=450_000

def index_archive(census,run_id):
    matches=[r for r in census["all_archives"] if r["run_id"]==run_id]
    if len(matches)!=1:raise ValueError("EXACT_ARCHIVE_RUN_NOT_FOUND")
    return matches[0]

def open_zip(s3,bucket,meta):
    raw=get_verified(s3,bucket,meta["archive_object_key"],
        meta["archive_expected_sha256"],MAX_ZIP)
    z=zipfile.ZipFile(io.BytesIO(raw))
    members=safe_members(z)
    if sum(x.file_size for x in members)>MAX_EXTRACTED:
        raise ValueError("SOURCE_UNCOMPRESSED_LIMIT")
    if z.testzip() is not None:raise ValueError("SOURCE_ZIP_CRC_BAD")
    return z

def json_member(z,name):
    if name not in z.namelist():raise ValueError("REQUIRED_ZIP_MEMBER_NOT_PRESENT")
    entry=z.getinfo(name)
    if entry.file_size>1_000_000:raise ValueError("SOURCE_MANIFEST_TOO_LARGE")
    return json.loads(z.read(name))

def label(raw):
    """Naive Binance CSV create_time assumed UTC ONLY for source label equality."""
    if not raw:return None,False
    try:
        d=dt.datetime.fromisoformat(raw.strip().replace("Z","+00:00"))
        naive=d.tzinfo is None
        if naive:d=d.replace(tzinfo=dt.timezone.utc)
        if d.utcoffset()!=dt.timedelta(0):return None,naive
        return d.isoformat(),naive
    except ValueError:
        return None,False

def numeric(raw):
    try:
        v=float(raw)
        return repr(v) if math.isfinite(v) else None
    except (TypeError,ValueError):return None

def metrics_labels(z,sym):
    """Raw metrics history. Source_date is NOT first-publication time."""
    member=sym+"_metrics_5m.csv"
    if member not in z.namelist():raise ValueError("ORIGINAL_METRICS_CSV_MISSING")
    counts=collections.Counter();dates=collections.Counter()
    entries=0;bad=naive_count=bad_date=0
    with z.open(member) as f:
        reader=csv.DictReader(io.TextIOWrapper(f,encoding="utf-8-sig",newline=""))
        for row in reader:
            entries+=1
            if entries>MAX_RAW_CSV_ROWS:raise ValueError("RAW_METRICS_ROWS_LIMIT")
            stamp,naive=label(row.get("create_time"))
            naive_count+=int(naive)
            val=numeric(row.get("sum_open_interest"))
            if stamp is None or val is None:
                bad+=1;continue
            day=row.get("source_date")
            dates[day]+=1
            if stamp[:10]!=day:bad_date+=1
            counts[(stamp,val)]+=1
    return counts,{"original_rows":entries,"valid_oi_value_rows":sum(counts.values()),
         "missing_or_invalid_rows":bad,"naive_utc_labels":naive_count,
         "source_date_vs_label_day_disagreement":bad_date,
         "source_calendar_days":len(dates),
         "days_with_288_source_rows":sum(v==288 for v in dates.values())}

def sorted_labels(z,sym):
    member=sym+"_research_5m.csv"
    if member not in z.namelist():raise ValueError("SORTED_MASKED_CSV_MISSING")
    digest_in=hashlib.sha256()
    counts=collections.Counter()
    total=invalid=0
    with z.open(member) as f:
        reader=csv.DictReader(io.TextIOWrapper(f,encoding="utf-8-sig",newline=""))
        for row in reader:
            total+=1
            if total>MAX_RAW_CSV_ROWS:raise ValueError("SORTED_MASKED_ROWS_LIMIT")
            stamp,naive=label(row.get("timestamp_utc"))
            if naive:raise ValueError("SORTED_LABEL_NOT_UTC_OFFSET_AWARE")
            val=numeric(row.get("sum_open_interest"))
            is_valid=row.get("sum_open_interest_valid")=="1" and val is not None
            if stamp is None:raise ValueError("SORTED_TIMESTAMPS_INVALID")
            if not is_valid:
                invalid+=1;continue
            counts[(stamp,val)]+=1
    return counts,{"sorted_rows":total,
         "sorted_valid_oi_rows":sum(counts.values()),
         "sorted_masked_invalid_oi_rows":invalid}

def compare_counts(raw,sorted_count):
    """Exact full multiset of labels+numeric values after original validity masking."""
    missing=sum(max(0,count-sorted_count.get(key,0)) for key,count in raw.items())
    extra=sum(max(0,count-raw.get(key,0)) for key,count in sorted_count.items())
    return {"raw_valid_absent_from_sorted":missing,
        "sorted_valid_absent_from_raw":extra,
        "numeric_and_label_multiset_match":missing==0 and extra==0}

def main():
    bucket=os.environ["R2_BUCKET"]
    s3=boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
       aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
       aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
    census=json.loads(get_verified(s3,bucket,CENSUS_KEY,CENSUS_SHA,1_000_000))
    sorted_meta=index_archive(census,SORTED_RUN)
    # The sorted manifest is the authority for its input run. Multiple
    # masked dataset revisions exist; do not guess from newest run number.
    with open_zip(s3,bucket,sorted_meta) as discovery_z:
        actual_masked_run=json_member(discovery_z,"manifest.json").get("source_run_id")
    if not isinstance(actual_masked_run,int):
        raise ValueError("SORTED_MASKED_SOURCE_RUN_MISSING")
    masked_meta=index_archive(census,actual_masked_run)
    with open_zip(s3,bucket,sorted_meta) as sorted_z:
        with open_zip(s3,bucket,masked_meta) as masked_z:
            sort_manifest=json_member(sorted_z,"manifest.json")
            masked_manifest=json_member(masked_z,"manifest.json")
            if sort_manifest.get("source_run_id")!=actual_masked_run:
                raise ValueError("SORTED_LINEAGE_RUN_ID_MISMATCH")
            source_run=masked_manifest.get("source_metrics_run")
            source_prices_run=masked_manifest.get("source_prices_run")
            if not isinstance(source_run,int):
                raise ValueError("MASKED_METRICS_LINEAGE_MISSING")
            original_meta=index_archive(census,source_run)
            rows=[]
            with open_zip(s3,bucket,original_meta) as source_z:
                source_manifest=json_member(source_z,"manifest.json")
                original_meta_records=source_manifest.get("records",[])
                for sym in SYMBOLS:
                    one,src=metrics_labels(source_z,sym)
                    two,derived=sorted_labels(sorted_z,sym)
                    comparison=compare_counts(one,two)
                    # Independent completeness from sorted numeric time series (same audit function as #87).
                    continuity=audit_oi_csv(sorted_z,sorted_z.getinfo(sym+"_research_5m.csv"))
                    if continuity.get("kind")!="OI_NUMERIC_EVENT_TIME_SERIES":
                        raise ValueError("CANNOT_REPRODUCE_SORTED_OI_TIMESERIES")
                    bysource=[r for r in original_meta_records if r.get("symbol")==sym]
                    downloads=sum(str(r.get("status","")).startswith("DOWNLOADED") for r in bysource)
                    item={"symbol":sym,"archive_runs":{
                        "original_metrics":source_run,"masked":actual_masked_run,"sorted":SORTED_RUN,
                        "price_candles":source_prices_run},
                        "source_downloads_reported":downloads,
                        "source_metrics_row_analysis":src,
                        "sorted_analysis":derived,
                        "numeric_values_and_labels_comparison":comparison,
                        "day_continuity":continuity,
                        "provenance":"Binance USD-M daily metrics CSV create_time event labels",
                        "publication_status":"ORIGINAL_METRICS_PUBLICATION_UNVERIFIED",
                        "naive_utc_label_assumption":src["naive_utc_labels"]>0}
                    rows.append(item)
                    print("OI413_PROVENANCE_SYMBOL",json.dumps({
                        "symbol":sym,"source_run":source_run,"count_raw":src["valid_oi_value_rows"],
                        "count_sorted":derived["sorted_valid_oi_rows"],
                        "equal":comparison["numeric_and_label_multiset_match"],
                        "full_5m_days":continuity["full_event_label_days"],
                        "longest_streak":continuity["max_consecutive_288_label_days"],
                        "first":continuity["first_event_utc"],"last":continuity["last_event_utc"],
                        "naive_labels":src["naive_utc_labels"]},ensure_ascii=False),flush=True)
                verified_lineage=all(x["numeric_values_and_labels_comparison"]["numeric_and_label_multiset_match"] for x in rows)
                report={
                    "schema":"detector-h1h10-413day-metrics-source-lineage-v1",
                    "status":"METRICS_SOURCE_LINEAGE_EXACT_PASS" if verified_lineage else
                             "METRICS_SOURCE_LINEAGE_DISCREPANCY",
                    "pinned_census_sha256":CENSUS_SHA,
                    "source_metrics_archive_sha256":original_meta["archive_expected_sha256"],
                    "masked_archive_sha256":masked_meta["archive_expected_sha256"],
                    "sorted_archive_sha256":sorted_meta["archive_expected_sha256"],
                    "symbol_evidence":rows,
                    "research_only":True,"trading_actions":False,
                    "original_venue_publication_time":"UNVERIFIED",
                    "safe_usage":"RETROSPECTIVE_DESCRIPTIVE_AND_HYPOTHESIS_DISCOVERY_ONLY",
                    "prohibited_usage":"NO_EXECUTABLE_POINT_IN_TIME_H1_H10_CONFIRMATION_FROM_EVENT_LABELS",
                    "notes":[
                        "Source CSV create_time and source_date are not exchange first-publication time",
                        "Source daily zip files were downloaded historically, not recorded prospectively at each 5m interval",
                        "Naive source timestamps treated as UTC labels for exact value matching only",
                        "No validation of 1h spot/perp price ingestion or original fee/spread/slippage",
                        "Even verified 413 day source lineage must not imply OI was usable causally on every source date"],
                    "run_id":os.environ["GITHUB_RUN_ID"],"source_commit":os.environ.get("GITHUB_SHA")}
                payload=json.dumps(report,ensure_ascii=False,sort_keys=True,indent=2).encode()
                key=ROOT+"/"+report["run_id"]+"-"+os.environ.get("GITHUB_RUN_ATTEMPT","1")+".json"
                checksum=digest(payload)
                s3.put_object(Bucket=bucket,Key=key,Body=payload,ContentType="application/json",
                    Metadata={"sha256":checksum})
                if digest(s3.get_object(Bucket=bucket,Key=key)["Body"].read(len(payload)+1))!=checksum:
                    raise ValueError("SOURCE_LINEAGE_R2_READBACK_SHA_MISMATCH")
                (OUT/"report.json").write_text(json.dumps({**report,"r2_key":key,
                     "r2_sha256":checksum},ensure_ascii=False,indent=2))
                print("OI413_PROVENANCE_SUMMARY",json.dumps({
                    "status":report["status"],"source_run":source_run,
                    "metrics_sha":original_meta["archive_expected_sha256"],
                    "r2_key":key,"sha256":checksum,
                    "edge_status":"EDGE_UNVALIDATED"},ensure_ascii=False),flush=True)
                if not verified_lineage:raise SystemExit(2)

if __name__=="__main__":main()
