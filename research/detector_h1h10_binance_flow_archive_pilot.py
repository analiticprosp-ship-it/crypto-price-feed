#!/usr/bin/env python3
"""H1/H6/H7 bounded no-cost Binance archive discovery and 5m PRICE sample.

Only official public static data.binance.vision. HEAD checks 7 named earlier
training-calendar days, BTC/ETH/SOL, Spot and USD-M futures, klines and aggTrades.
GET exactly six bounded first-day 5m kline ZIPs, plus official .CHECKSUM.
Verifies original publisher SHA256 + ZIP CRC + 288 timestamps before immutable R2.
AggTrades HEAD is AVAILABILITY/FILE-SIZE DISCOVERY ONLY: no trade-flow data claim.
Not historical as-of publication, not research backtest, not a production feed.
"""
import csv
import datetime as dt
import hashlib
import io
import json
import os
import re
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

import boto3

SCHEMA="detector-h1h10-binance-bounded-flow-archive-discovery-v1"
BASE="https://data.binance.vision/data"
OUT="research/detector-h1h10-binance-flow-archive-discovery/v1"
DAYS=tuple((dt.date(2026,5,4)+dt.timedelta(days=i)).isoformat() for i in range(7))
SYMBOLS=("BTCUSDT","ETHUSDT","SOLUSDT")
MARKETS=("spot","um")
DATASETS=("klines","aggTrades")
ZIP_MAX=850000
CHECKSUM_MAX=512
REQUEST_TIMEOUT=9
MAX_HEAD=84
EXPECTED_ROWS=288
UA="H1H10-Bounded-Research-Only/1.0"
HEXC=frozenset("0123456789abcdef")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def archive_url(market,kind,symbol,day):
    if (market not in MARKETS or kind not in DATASETS or symbol not in SYMBOLS
        or day not in DAYS):
        raise ValueError("UNAPPROVED_ARCHIVE_SCOPE")
    root=f"{BASE}/"+("spot" if market=="spot" else "futures/um")+f"/daily/{kind}/{symbol}"
    if kind=="klines":
        return f"{root}/5m/{symbol}-5m-{day}.zip"
    return f"{root}/{symbol}-aggTrades-{day}.zip"


def fetch_http(url,method="GET",cap=ZIP_MAX,open_url=None):
    if not url.startswith(BASE+"/") or not (url.endswith(".zip") or url.endswith(".zip.CHECKSUM")):
        raise ValueError("UNAPPROVED_EXTERNAL_URL")
    if method not in ("HEAD","GET"):
        raise ValueError("UNAPPROVED_HTTP_METHOD")
    if open_url is None:
        open_url=urllib.request.urlopen
    req=urllib.request.Request(url,method=method,headers={"User-Agent":UA})
    begun=time.time()
    try:
        with open_url(req,timeout=REQUEST_TIMEOUT) as resp:
            code=resp.status
            size=resp.headers.get("Content-Length")
            if code!=200:
                raise ValueError("SOURCE_HTTP_NOT_200")
            if method=="HEAD":
                return {"http":200,"bytes":int(size) if size and size.isdigit() else None,
                        "observed_at_utc":dt.datetime.now(dt.timezone.utc).isoformat(),
                        "elapsed_seconds":round(time.time()-begun,3)}
            if size and size.isdigit() and int(size)>cap:
                raise ValueError("SOURCE_SIZE_CAP")
            raw=resp.read(cap+1)
            if len(raw)>cap:
                raise ValueError("SOURCE_SIZE_CAP")
            return raw
    except urllib.error.HTTPError as exc:
        if exc.code in (403,404,405,451):
            if method=="HEAD":
                return {"http":exc.code,"bytes":None,"status":"UNVERIFIED_SOURCE_AVAILABILITY"}
        raise


def checksum_sha(body,name):
    if len(body)>CHECKSUM_MAX:raise ValueError("PUBLISHER_CHECKSUM_OVERSIZE")
    value=body.decode("ascii").strip().split()
    if len(value)!=2 or value[1].lstrip("*")!=name:
        raise ValueError("PUBLISHER_CHECKSUM_FILENAME_MISMATCH")
    digest=value[0].lower()
    if len(digest)!=64 or not set(digest)<=HEXC:
        raise ValueError("PUBLISHER_CHECKSUM_INVALID")
    return digest


def validate_5m_zip(body,market,symbol,day):
    if len(body)>ZIP_MAX:raise ValueError("KLINE_ZIP_OVERSIZE")
    with zipfile.ZipFile(io.BytesIO(body)) as z:
        if z.testzip() is not None:raise ValueError("KLINE_ZIP_CRC_FAIL")
        names=z.namelist()
        if len(names)!=1 or names[0]!=f"{symbol}-5m-{day}.csv":
            raise ValueError("KLINE_ZIP_MEMBER_INVALID")
        info=z.getinfo(names[0])
        if info.file_size>300000 or info.file_size<=0:
            raise ValueError("KLINE_CSV_UNPACKED_SIZE")
        raw=z.read(info)
    lines=list(csv.reader(io.StringIO(raw.decode("utf-8-sig"))))
    # Some Binance archives have a CSV header. Accept it ONLY if the exact
    # price/time column shape is recognized; never skip arbitrary first bars.
    has_header=False
    if len(lines)==EXPECTED_ROWS+1:
        first=[x.strip().lower().replace(" ","_") for x in lines[0]]
        if (len(first)>=7 and first[:7]==[
            "open_time","open","high","low","close","volume","close_time"]):
            has_header=True
            lines=lines[1:]
    if len(lines)!=EXPECTED_ROWS:
        raise ValueError("KLINE_NOT_FULL_DAY_COUNT_"+str(len(lines)))
    multiplier=1000000 if market=="spot" else 1000
    date_start=dt.datetime.fromisoformat(day+"T00:00:00+00:00")
    begin_ms=int(date_start.timestamp()*1000)
    for i,row in enumerate(lines):
        if len(row)<11:
            raise ValueError("KLINE_ROW_SHORT")
        try:
            start=int(row[0]);close_t=int(row[6])
            close=float(row[4]);vol=float(row[5])
        except (ValueError,TypeError) as exc:
            raise ValueError("KLINE_ROW_BAD_NUMBER") from exc
        expected=(begin_ms+i*300000)*(multiplier//1000)
        end=(begin_ms+(i+1)*300000)*(multiplier//1000)-1
        if start!=expected or close_t!=end or not 0<close<1e9 or not 0<=vol<1e18:
            raise ValueError("KLINE_CLOCK_OR_PRICE_INVALID")
    return {"rows":len(lines),"publisher_csv_header_present":has_header,
            "utc_day":day,"market":market,"symbol":symbol,
            "timestamp_unit":"microseconds" if market=="spot" else "milliseconds",
            "publisher_zip_crc_verified":True,"source_time_basis":"BAR_OPEN_NOT_ORIGINAL_PUBLICATION",
            "first_bar_open":lines[0][0],"last_bar_open":lines[-1][0]}


def put_immutable(s3,bucket,key,data):
    digest=sha(data)
    try:
        prior=s3.get_object(Bucket=bucket,Key=key)
    except s3.exceptions.NoSuchKey:
        prior=None
    if prior is not None:
        actual=prior["Body"].read(len(data)+1)
        if actual!=data or prior.get("Metadata",{}).get("sha256")!=digest:
            raise ValueError("IMMUTABLE_R2_KEY_COLLISION")
    else:
        s3.put_object(Bucket=bucket,Key=key,Body=data,
                      ContentType="application/octet-stream",
                      Metadata={"sha256":digest})
    result=s3.get_object(Bucket=bucket,Key=key)
    back=result["Body"].read(len(data)+1)
    if back!=data or result.get("Metadata",{}).get("sha256")!=digest:
        raise ValueError("R2_SHA_READBACK_FAILURE")
    return digest


def main():
    if os.environ.get("GITHUB_REPOSITORY")!="analiticprosp-ship-it/crypto-price-feed":
        raise ValueError("RESEARCH_REPOSITORY_SCOPE_INVALID")
    run=os.environ["GITHUB_RUN_ID"];attempt=os.environ.get("GITHUB_RUN_ATTEMPT","1")
    if not run.isdigit() or not attempt.isdigit():raise ValueError("RUN_ID_INVALID")
    s3=boto3.client("s3",
        endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
    bucket=os.environ["R2_BUCKET"]
    records=[];head_count=0
    for day in DAYS:
        for market in MARKETS:
            for symbol in SYMBOLS:
                for kind in DATASETS:
                    url=archive_url(market,kind,symbol,day)
                    record={"day":day,"market":market,"symbol":symbol,
                            "dataset":kind,"url":url,"mode":"HEAD_DISCOVERY_ONLY",
                            "original_publication_time":"UNVERIFIED",
                            "trading_authorized":False}
                    status=fetch_http(url,"HEAD")
                    record.update(status)
                    if kind=="aggTrades":
                        record["event_clock_semantics"]="SPOT_MICROSECONDS_2025_PLUS" if market=="spot" else "UM_MILLISECONDS"
                        record["historical_trade_availability_grade"]="UNVERIFIED_EVENT_ARCHIVE_NOT_DOWNLOADED"
                    records.append(record);head_count+=1
    if head_count!=MAX_HEAD:raise ValueError("UNEXPECTED_SOURCE_PROBE_COUNT")
    archived=[]
    # First-day price evidence only; aggTrades HEAD does not count as downloaded flow.
    day=DAYS[0]
    for market in MARKETS:
        for symbol in SYMBOLS:
            url=archive_url(market,"klines",symbol,day)
            payload=fetch_http(url,"GET")
            cks=fetch_http(url+".CHECKSUM","GET",cap=CHECKSUM_MAX)
            digest=checksum_sha(cks,url.rsplit("/",1)[1])
            if sha(payload)!=digest:
                raise ValueError("PUBLISHER_SHA256_MISMATCH")
            validation=validate_5m_zip(payload,market,symbol,day)
            raw_key=OUT+f"/raw-klines-2026-05-04/{market}-{symbol}-{digest}.zip"
            if put_immutable(s3,bucket,raw_key,payload)!=digest:
                raise ValueError("KLINE_RAW_R2_SHA_UNEXPECTED")
            archived.append({**validation,"publisher_sha256":digest,
                             "r2_object_key":raw_key,
                             "raw_http_response_received_during_run":True,
                             "trade_flow_collected":False})
    report={
        "schema":SCHEMA,"scope":"RESEARCH_ONLY",
        "window":list(DAYS),"sources":list(SYMBOLS),"markets":list(MARKETS),
        "head_probes":head_count,"head_source_reports":records,
        "downloaded_verified_5m_price_archives":len(archived),
        "verified_kline_samples":archived,
        "downloaded_aggtrades_archives":0,
        "source_type":"OFFICIAL_BINANCE_STATIC_ARCHIVES",
        "research_status":"PRICE_SAMPLE_SHA_CRC_VALIDATED_FLOW_ARCHIVE_DISCOVERY_ONLY",
        "historical_first_publication":"UNVERIFIED",
        "flow_publication_asof":"UNVERIFIED",
        "historical_causal_pit":"BLOCKED",
        "locked_holdout_used":False,
        "training_authorized":False,
        "causal_joint_rows_authorized":0,
        "edge_status":"EDGE_UNVALIDATED","trading_actions":False,
        "snapshot_as_of_run":run,"attempt":attempt}
    raw=json.dumps(report,sort_keys=True,ensure_ascii=False,indent=2).encode()
    key=OUT+f"/run-reports/{run}-{attempt}.json"
    digest=put_immutable(s3,bucket,key,raw)
    path=Path("detector_h1h10_binance_source_pilot/pilot.json")
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps({**report,"r2_key":key,"sha256":digest},
                               indent=2,ensure_ascii=False),encoding="utf-8")
    print("H1H10_BINANCE_FLOW_ARCHIVE_BOUNDED_PILOT",json.dumps({
        "head_probes":head_count,
        "head_200":sum(x.get("http")==200 for x in records),
        "head_non_200":sum(x.get("http")!=200 for x in records),
        "price_archives_publisher_sha_crc_verified":len(archived),
        "aggtrades_downloaded":0,"causal_authorized":0,
        "r2_key":key,"sha256":digest},sort_keys=True),flush=True)


if __name__=="__main__":
    main()
