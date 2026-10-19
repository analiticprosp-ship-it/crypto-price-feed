#!/usr/bin/env python3
"""Research-only Tardis 2019Dec..2021Jan BTC/ETH first-of-month OI receipts.

14 monthly free samples per asset, strictly vendor microsecond receipt-asof
at closed 5m end +30s. Source gzip CRC and SHA256 independently captured.
Free monthly days DO NOT imply all intervening days available or exchange PIT.
No paid access, regional bypass, trading, interpolation or account operations.
"""
import datetime as dt,gzip,hashlib,io,json,os,urllib.error
from pathlib import Path
from research.detector_tardis_earliest_free_oi_v1 import (
    measure, catalog_one, exact_catalog, first_free_date, symbol)
from research.detector_tardis_okx_free_archive_audit_v1 import load_bytes
from research.detector_earliest_archive_byte_audit_v1 import r2,verify_r2

VENUE="binance-futures"
COINS=("BTC","ETH")
SOURCE_START="2019-12-01"
SOURCE_END="2021-01-01"
PARENT_KEY="research/detector-tardis-earliest-free-receipt/v1/39309240387-1.json"
PARENT_SHA="12b936127078b4d0318a4f6c2b59c60ccfb28db562ccdef318b4e1fa1ed7bb95"
ROOT="research/detector-tardis-binance-btc-eth-2020-free-monthly-oi/v1"
OUT=Path("detector_tardis_binance_2020_monthly_oi")
GZ_CAP=16_000_000
CSV_CAP=140_000_000

def dates():
    result=[]
    for year,begin,end in ((2019,12,12),(2020,1,12),(2021,1,1)):
        for month in range(begin,end+1):
            result.append(f"{year:04d}-{month:02d}-01")
    if len(result)!=14 or result[0]!=SOURCE_START or result[-1]!=SOURCE_END:
        raise ValueError("MONTHLY_FREE_GRID_INVALID")
    return result

def sample_url(day,coin):
    if coin not in COINS or day not in dates():raise ValueError("NOT_APPROVED_FREE_SOURCE")
    yy,mm,dd=day.split("-")
    return f"https://datasets.tardis.dev/v1/{VENUE}/derivative_ticker/{yy}/{mm}/{dd}/{symbol(VENUE,coin)}.csv.gz"

def sample_one(day,coin,fetch=load_bytes):
    url=sample_url(day,coin)
    result={"day":day,"venue":VENUE,"symbol":symbol(VENUE,coin),
      "source_url":url,"status":"UNVERIFIED"}
    try:
        body,code=fetch(url,GZ_CAP,30)
        if code!=200:raise ValueError("HTTP_SAMPLE_NOT_200")
        with gzip.GzipFile(fileobj=io.BytesIO(body)) as g:
            plain=g.read(CSV_CAP+1)
        if len(plain)>CSV_CAP:raise ValueError("CSV_PLAIN_CAP_EXCEEDED")
        stats=measure(plain,day,VENUE,symbol(VENUE,coin))
        result.update(status="VENDOR_SAMPLE_SOURCE_CRC_SHA_PASS",
            gzip_sha256=hashlib.sha256(body).hexdigest(),
            csv_sha256=hashlib.sha256(plain).hexdigest(),
            gzip_bytes=len(body),csv_bytes=len(plain),
            gzip_crc_eof="PASS",oi_quality=stats)
    except urllib.error.HTTPError as e:
        result.update(status="HTTP_UNAVAILABLE_NOT_MISSING_HISTORY",http=e.code)
    except Exception as e:
        result.update(status="SOURCE_UNVERIFIED",error_type=type(e).__name__,error=str(e)[:160])
    return result

def earliest_sample_with_fresh(rows,coin):
    eligible=sorted((r for r in rows if r["symbol"]==symbol(VENUE,coin)
         and r["status"]=="VENDOR_SAMPLE_SOURCE_CRC_SHA_PASS"
         and r["oi_quality"]["fresh_5m_vendor_asof_buckets"]>0),key=lambda x:x["day"])
    return eligible[0]["day"] if eligible else None

def validate_pinned_prior(data):
    if data.get("schema")!="detector-tardis-earliest-free-oi-sample-v1":
        raise ValueError("PREVIOUS_REPORT_SCHEMA_MISMATCH")
    proof=[r for r in data.get("cases",[]) if r.get("venue")==VENUE
           and r.get("symbol") in ("BTCUSDT","ETHUSDT")]
    if len(proof)!=2:raise ValueError("PINNED_EARLY_BTC_ETH_SAMPLES_MISSING")
    if any(r.get("first_free_month_after_listing")!=SOURCE_START or
           r.get("quality",{}).get("fresh_5m_vendor_asof_buckets")!=0 or
           r.get("status")!="VERIFIED_VENDOR_RECEIPT_ASOF_EARLIEST_FREE_DAY"
           for r in proof):raise ValueError("PREVIOUS_SOURCE_EVIDENCE_NOT_EXPECTED")
    return {r["symbol"]:r["source_sha256"] for r in proof}

def main():
    OUT.mkdir(exist_ok=True)
    s3=r2();bucket=os.environ["R2_BUCKET"]
    parent_blob=verify_r2(s3,bucket,PARENT_KEY,PARENT_SHA,900_000)
    baseline=validate_pinned_prior(json.loads(parent_blob))
    catalog,catalog_sha,catalog_url=catalog_one(VENUE)
    catalog_entries={}
    for coin in COINS:
        entry=exact_catalog(catalog,VENUE,coin)
        catalog_entries[coin]={"instrument":entry["id"],"availableSince":entry["availableSince"],
           "first_free_after_listing":first_free_date(entry["availableSince"])}
        if catalog_entries[coin]["first_free_after_listing"]!=SOURCE_START:
            raise ValueError("INSTRUMENT_CATALOG_EARLY_PERIOD_CHANGED")
    samples=[]
    for coin in COINS:
        for day in dates():
            r=sample_one(day,coin)
            if day==SOURCE_START and r.get("gzip_sha256")!=baseline.get(symbol(VENUE,coin)):
                # Source historic revisions MUST NOT be silently treated as identical.
                r["status"]="PINNED_2019DEC_ARCHIVE_BYTES_REVISED_OR_UNAVAILABLE"
            samples.append(r)
            print("BINANCE_TARDIS_2020_FREE_OI_SAMPLE",json.dumps({
                "coin":coin,"day":day,"status":r["status"],
                "source_rows":r.get("oi_quality",{}).get("source_rows"),
                "valid_oi":r.get("oi_quality",{}).get("valid_open_interest_rows"),
                "fresh_5m":r.get("oi_quality",{}).get("fresh_5m_vendor_asof_buckets"),
                "stale_5m":r.get("oi_quality",{}).get("stale_5m_buckets"),
                "missing_5m":r.get("oi_quality",{}).get("missing_5m_buckets"),
                "error":r.get("error_type")},ensure_ascii=False),flush=True)
    origins={coin:earliest_sample_with_fresh(samples,coin) for coin in COINS}
    statuses={}
    for x in samples:statuses[x["status"]]=statuses.get(x["status"],0)+1
    report={"schema":"detector-binance-btc-eth-tardis-2020-free-monthly-oi-v1",
        "source":"Tardis Binance Futures derivative_ticker first-day free monthly samples",
        "parent_key":PARENT_KEY,"parent_sha256":PARENT_SHA,
        "catalog_url":catalog_url,"catalog_sha256":catalog_sha,
        "catalog_entries":catalog_entries,
        "dates":dates(),"symbols":list(COINS),
        "samples":samples,"sample_statuses":statuses,
        "earliest_observed_free_month_with_fresh_oi":origins,
        "causal_cutoff":"Tardis vendor local receipt and source event <= 5m end+30 seconds; fresh <=120 seconds",
        "source_history_inception":"NOT_PROVEN_MONTHLY_SAMPLING_ONLY",
        "original_exchange_publication":"UNVERIFIED",
        "source_revision_check":"Prior Dec-2019 compressed SHA256 pinned to earlier verified evidence",
        "retrospective_vendor_receipt":"NOT_EXECUTION_SYSTEM_FIRST_SEEN",
        "research_only":True,"edge_status":"EDGE_UNVALIDATED","trading_portfolio_mutations":False,
        "limits":["14 isolated first-of-month days, not 14 continuous months",
          "First fresh sampled day is not exchange dataset inception",
          "Native OI units cannot be compared cross-venue absent instrument metadata",
          "No original source rows modified or values imputed"],
        "run_id":os.environ["GITHUB_RUN_ID"]}
    content=json.dumps(report,ensure_ascii=False,sort_keys=True,indent=2).encode()
    digest=hashlib.sha256(content).hexdigest()
    key=ROOT+"/"+str(os.environ["GITHUB_RUN_ID"])+"-"+str(os.environ.get("GITHUB_RUN_ATTEMPT","1"))+".json"
    s3.put_object(Bucket=bucket,Key=key,Body=content,ContentType="application/json",Metadata={"sha256":digest})
    if verify_r2(s3,bucket,key,digest,len(content)+1)!=content:
        raise ValueError("R2_WRITE_READBACK_BYTES_MISMATCH")
    (OUT/"report.json").write_bytes(content)
    print("BINANCE_TARDIS_2020_FREE_OI_SUMMARY",json.dumps({
        "sample_count":len(samples),"statuses":statuses,
        "earliest_fresh_sample":origins,"r2_key":key,
        "sha256":digest,"edge":"EDGE_UNVALIDATED"},ensure_ascii=False),flush=True)
    if any(r["status"]!="VENDOR_SAMPLE_SOURCE_CRC_SHA_PASS" for r in samples):
        raise SystemExit("SOME_FREE_VENDOR_SOURCE_CASES_UNVERIFIED_SEE_SAVED_REPORT")

if __name__=="__main__":
    main()
