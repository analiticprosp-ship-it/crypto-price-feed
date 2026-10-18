#!/usr/bin/env python3
"""Research-only multi-regime Tardis Binance Futures OI, vendor-receipt as-of.

Read only free first-of-month samples. Never substitute for official Binance 5m
metrics. A snapshot is eligible only when vendor local_timestamp <= decision.
Future price outcomes, trading signals, P&L and orders are outside this script.
"""
import csv
import datetime as dt
import gzip
import hashlib
import io
import json
import math
import os
import statistics
import urllib.request
from pathlib import Path
import boto3

DAYS=("2024-01-01","2025-01-01","2026-09-01")
SYMBOLS=("BTCUSDT","ETHUSDT","SOLUSDT")
ROOT="research/tardis-binance-oi-multiday/v1"
MAX_GZ=10_000_000
MAX_CSV_BYTES=55_000_000
MAX_ROWS=200_000
BUCKET_US=300_000_000
DELAY_US=30_000_000
FIELD_NAMES=("bucket_start_utc","bucket_end_utc","decision_time_utc",
             "symbol","open_interest","vendor_receipt_utc","source_event_utc",
             "observation_age_seconds","asof_quality","source_provider")
OUT=Path("detector_tardis_multiday")
OUT.mkdir(exist_ok=True)


def epoch_us(day):
    return int(dt.datetime.fromisoformat(day).replace(tzinfo=dt.timezone.utc).timestamp()*1_000_000)


def iso(us):
    return dt.datetime.fromtimestamp(us/1_000_000,dt.timezone.utc).isoformat()


def sample_url(day,symbol):
    date=dt.date.fromisoformat(day)
    if date.day!=1 or not symbol in SYMBOLS or day not in DAYS:
        raise ValueError("UNAPPROVED_FREE_SAMPLE")
    return (f"https://datasets.tardis.dev/v1/binance-futures/derivative_ticker/"
            f"{date:%Y/%m/%d}/{symbol}.csv.gz")


def download(day,symbol):
    request=urllib.request.Request(sample_url(day,symbol),headers={
        "Accept":"application/gzip","User-Agent":"Detector-H1H10-Research/1.0"})
    data=io.BytesIO()
    with urllib.request.urlopen(request,timeout=75) as response:
        if response.status!=200:raise ValueError("SAMPLE_HTTP_ERROR")
        while True:
            block=response.read(512_000)
            if not block:break
            if data.tell()+len(block)>MAX_GZ:raise ValueError("SAMPLE_COMPRESSED_LIMIT")
            data.write(block)
    blob=data.getvalue()
    if blob[:2]!=bytes((31,139)):raise ValueError("SAMPLE_NOT_GZIP")
    return blob


def parse(blob,day,symbol):
    start=epoch_us(day);end=start+86_400_000_000
    counts={"rows":0,"valid_oi":0,"blank_or_invalid_oi":0,"outside_day":0,
            "nonmonotonic_receipt":0,"exchange_after_vendor":0,
            "invalid_time":0}
    records=[];prev=None;total=0
    with gzip.GzipFile(fileobj=io.BytesIO(blob)) as zipfile:
        text=io.TextIOWrapper(zipfile,encoding="utf-8-sig",newline="")
        reader=csv.DictReader(text)
        needed={"symbol","timestamp","local_timestamp","open_interest"}
        if not needed.issubset(reader.fieldnames or []):
            raise ValueError("SOURCE_REQUIRED_FIELDS_MISSING")
        for order,row in enumerate(reader):
            counts["rows"]+=1
            total+=sum(len(str(v or "")) for v in row.values())+len(row)*2
            if counts["rows"]>MAX_ROWS or total>MAX_CSV_BYTES:
                raise ValueError("SAMPLE_DECOMPRESSED_LIMIT")
            if row.get("symbol")!=symbol:raise ValueError("SOURCE_SYMBOL_MISMATCH")
            try:
                receipt=int(row["local_timestamp"])
                event=int(row["timestamp"])
                if receipt<1_600_000_000_000_000 or event<1_600_000_000_000_000:
                    raise ValueError("SOURCE_TIME_TOO_OLD")
            except (TypeError,ValueError):
                counts["invalid_time"]+=1;continue
            if prev is not None and receipt<prev:counts["nonmonotonic_receipt"]+=1
            prev=receipt
            if event>receipt:counts["exchange_after_vendor"]+=1
            if not start<=receipt<end:
                counts["outside_day"]+=1;continue
            raw=row.get("open_interest","")
            try:
                oi=float(raw)
                if not math.isfinite(oi) or oi<0:raise ValueError("INVALID_OI")
            except (TypeError,ValueError):
                counts["blank_or_invalid_oi"]+=1;continue
            counts["valid_oi"]+=1
            records.append((receipt,order,event,raw))
    if not records:raise ValueError("NO_VALID_VENDOR_RECEIPTS")
    records.sort(key=lambda r:(r[0],r[1]))
    return records,counts


def asof_5m(records,day,symbol):
    """No data with receipt after the decision may enter a feature."""
    day_start=epoch_us(day)
    rows=[];cursor=0;last=None;ages=[];missing=0;stale=0;future=0
    for i in range(288):
        start=day_start+i*BUCKET_US;end=start+BUCKET_US;decision=end+DELAY_US
        while cursor<len(records) and records[cursor][0]<=decision:
            last=records[cursor];cursor+=1
        row={"bucket_start_utc":iso(start),"bucket_end_utc":iso(end),
             "decision_time_utc":iso(decision),"symbol":symbol,
             "open_interest":"","vendor_receipt_utc":"","source_event_utc":"",
             "observation_age_seconds":"","asof_quality":"MISSING_VENDOR_ASOF",
             "source_provider":"Tardis Binance Futures derivative_ticker"}
        if last is None:
            missing+=1
        else:
            receipt,_,event,raw=last
            if receipt>decision:future+=1
            age=(decision-receipt)/1_000_000
            ages.append(age)
            if age>120:stale+=1
            row.update({"open_interest":raw,"vendor_receipt_utc":iso(receipt),
                "source_event_utc":iso(event),"observation_age_seconds":f"{age:.6f}",
                "asof_quality":"OK_VENDOR_RECEIPT" if age<=120 else "STALE_VENDOR_OVER_120S"})
        rows.append(row)
    if future:raise ValueError("FUTURE_VENDOR_RECEIPT_USED")
    stats={"buckets":288,"available":288-missing,"missing":missing,"stale_over_120s":stale,
           "future_vendor_receipts":future,
           "median_age_seconds":statistics.median(ages) if ages else None,
           "p99_age_seconds":sorted(ages)[int((len(ages)-1)*.99)] if ages else None,
           "max_age_seconds":max(ages) if ages else None,
           "earliest_vendor_receipt_us":records[0][0],
           "last_vendor_receipt_us":records[-1][0]}
    return rows,stats


def verified_put(s3,bucket,key,data,content_type):
    checksum=hashlib.sha256(data).hexdigest()
    s3.put_object(Bucket=bucket,Key=key,Body=data,ContentType=content_type,
                  Metadata={"sha256":checksum})
    read=s3.get_object(Bucket=bucket,Key=key)["Body"].read(len(data)+1)
    if hashlib.sha256(read).hexdigest()!=checksum:raise ValueError("R2_READBACK_SHA_MISMATCH")
    return checksum


def main():
    bucket=os.environ["R2_BUCKET"]
    client=boto3.client("s3",
        endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
    records=[]
    for day in DAYS:
        for symbol in SYMBOLS:
            source=download(day,symbol)
            raw,quality=parse(source,day,symbol)
            bars,asof=asof_5m(raw,day,symbol)
            root=f"{ROOT}/{day}"
            original_key=root+"/"+symbol+".csv.gz"
            original_sha=verified_put(client,bucket,original_key,source,"application/gzip")
            content=io.StringIO(newline="")
            writer=csv.DictWriter(content,fieldnames=FIELD_NAMES)
            writer.writeheader();writer.writerows(bars)
            derived_data=content.getvalue().encode()
            derived_key=root+"/derived/"+symbol+"_vendor_asof_5m.csv"
            derived_sha=verified_put(client,bucket,derived_key,derived_data,"text/csv")
            item={"day":day,"symbol":symbol,"original_key":original_key,
                  "source_sha256":original_sha,"source_compressed_bytes":len(source),
                  "derived_key":derived_key,"derived_sha256":derived_sha,
                  "source_quality":quality,"asof_quality":asof}
            records.append(item)
            print("TARDIS_MULTIDAY_ROW",json.dumps({
                "day":day,"symbol":symbol,"source_rows":quality["rows"],
                "oi_valid":quality["valid_oi"],"asof_buckets":asof["available"],
                "future":asof["future_vendor_receipts"],
                "stale":asof["stale_over_120s"],"missing":asof["missing"],
                "source_sha256":original_sha,"derived_sha256":derived_sha}),flush=True)
    manifest={"schema":"detector-tardis-multiday-vendor-asof-v1",
        "dates":DAYS,"symbols":SYMBOLS,"records":records,
        "provider":"Tardis.dev","venue":"Binance USD-M Futures",
        "dataset":"derivative_ticker sampled OI (NOT Binance official 5m aggregates)",
        "research_only":True,"github_run_id":os.environ["GITHUB_RUN_ID"],
        "source_commit_sha":os.environ.get("GITHUB_SHA"),
        "decision_rule":"closed 5m bucket end +30s; vendor local_timestamp <= decision",
        "publication_status":"VENDOR_RECEIPT_ONLY_ORIGINAL_EXCHANGE_PUBLICATION_UNVERIFIED",
        "notes":["Free first-of-month sample days only; not random market sample",
                 "Vendor received records are not directly executable exchange availability",
                 "Last bucket of day may use a stale within-day record; no next-day data",
                 "No inferred predictive edge or trade decisions"]}
    data=json.dumps(manifest,ensure_ascii=False,sort_keys=True,indent=2).encode()
    key=ROOT+"/manifest.json"
    sha=verified_put(client,bucket,key,data,"application/json")
    summary={"status":"MULTIDAY_VENDOR_ASOF_COMPLETE","days":list(DAYS),
        "source_snapshots":sum(r["source_quality"]["rows"] for r in records),
        "total_5m_buckets":sum(r["asof_quality"]["buckets"] for r in records),
        "available_asof_buckets":sum(r["asof_quality"]["available"] for r in records),
        "missing_asof":sum(r["asof_quality"]["missing"] for r in records),
        "stale_over_120s":sum(r["asof_quality"]["stale_over_120s"] for r in records),
        "future_vendor_receipts":sum(r["asof_quality"]["future_vendor_receipts"] for r in records),
        "manifest_key":key,"manifest_sha256":sha,
        "publication_status":manifest["publication_status"]}
    (OUT/"report.json").write_text(json.dumps({"summary":summary,"records":records},ensure_ascii=False,indent=2))
    print("TARDIS_MULTIDAY_SUMMARY",json.dumps(summary,ensure_ascii=False),flush=True)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"],"a",encoding="utf-8") as f:
            f.write("## H1-H10 Tardis multi-day vendor-receipt OI\n\n")
            f.write(f"- Source snapshots: {summary['source_snapshots']}\n- 5m buckets available: {summary['available_asof_buckets']}/{summary['total_5m_buckets']}\n")
            f.write(f"- Future vendor receipts used: {summary['future_vendor_receipts']}\n- Missing: {summary['missing_asof']}\n- Stale >120s: {summary['stale_over_120s']}\n")
            f.write("- Statistical edge and actual exchange publication time remain UNVERIFIED.\n")

if __name__=="__main__":
    main()
