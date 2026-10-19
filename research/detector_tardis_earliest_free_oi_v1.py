#!/usr/bin/env python3
"""First actual free Tardis derivative_ticker day after each instrument starts.

Dates sourced from a fresh official Tardis public exchange catalog (no guessed
inception). First-of-month sample follows the provider availableSince date.
Free sample existence, bytes, receipt-asof quality, publisher origin/release
and full continuity are separate. No paid data, no trading.
"""
import calendar,csv,datetime as dt,gzip,hashlib,io,json,math,os,urllib.error
from pathlib import Path
from research.detector_tardis_okx_free_archive_audit_v1 import load_bytes

UTC=dt.timezone.utc
OUT=Path("detector_tardis_earliest_free_day")
ROOT="research/detector-tardis-earliest-free-receipt/v1"
VENUES=("binance-futures","bybit","okex-swap")
COINS=("BTC","ETH","SOL")
COMPRESSED_CAP=16_000_000
PLAIN_CAP=140_000_000
ROW_CAP=700_000

def symbol(venue,coin):
    if venue not in VENUES or coin not in COINS:raise ValueError("BAD_VENUE_ASSET")
    return coin+"-USDT-SWAP" if venue=="okex-swap" else coin+"USDT"

def first_free_date(available_since):
    t=dt.datetime.fromisoformat(str(available_since).replace("Z","+00:00"))
    if t.tzinfo is None:raise ValueError("CATALOG_AVAILABLE_SINCE_HAS_NO_OFFSET")
    t=t.astimezone(UTC)
    year=t.year+(t.month==12)
    month=1 if t.month==12 else t.month+1
    return dt.date(year,month,1).isoformat()

def exact_catalog(entry,venue,coin):
    rows=entry.get("datasets",{}).get("symbols")
    if not isinstance(rows,list):raise ValueError("CATALOG_SCHEMA_INVALID")
    expected=symbol(venue,coin)
    matches=[r for r in rows if isinstance(r,dict) and r.get("id")==expected]
    if len(matches)!=1:raise ValueError("CATALOG_INSTRUMENT_NOT_EXACT")
    r=matches[0]
    if "derivative_ticker" not in r.get("dataTypes",[]):
        raise ValueError("CATALOG_DERIVATIVE_TICKER_NOT_AVAILABLE")
    if not r.get("availableSince"):raise ValueError("CATALOG_INCEPTION_MISSING")
    return r

def vendor_us(value):
    s=str(value).strip()
    if not (len(s)==16 and s.isdigit()):raise ValueError("VENDOR_TIMESTAMP_NOT_MICROSECONDS")
    n=int(s)
    if not 1_483_228_800_000_000<=n<=1_900_000_000_000_000:
        raise ValueError("VENDOR_TIMESTAMP_OUT_OF_SUPPORTED_BOUNDS")
    return n

def measure(data,day,venue,sym):
    d=dt.date.fromisoformat(day)
    start=int(dt.datetime(d.year,d.month,d.day,tzinfo=UTC).timestamp()*1e6)
    stop=start+86_400_000_000
    cutoff=[start+(i+1)*300_000_000+30_000_000 for i in range(288)]
    reader=csv.DictReader(io.TextIOWrapper(io.BytesIO(data),encoding="utf-8-sig",newline=""))
    needed={"exchange","symbol","timestamp","local_timestamp","open_interest"}
    if not needed.issubset(reader.fieldnames or []):raise ValueError("SOURCE_FIELDS_UNVERIFIED")
    count=blank=invalid=excluded_future=out_of_day=0
    last_receipt=None;cursor=0;last_oi=None;fresh=stale=missing=0
    first_local=None;last_local=None
    def finalize(i,last):
        if last is None:return "missing"
        received,event,val=last
        if received>cutoff[i] or event>cutoff[i]:
            raise ValueError("FUTURE_VENDOR_DATA_CONSUMED")
        return "fresh" if cutoff[i]-received<=120_000_000 else "stale"
    def take_quality(i,last):
        nonlocal fresh,stale,missing
        kind=finalize(i,last)
        if kind=="fresh":fresh+=1
        elif kind=="stale":stale+=1
        else:missing+=1
    for r in reader:
        count+=1
        if count>ROW_CAP:raise ValueError("SOURCE_ROW_CAP_EXCEEDED")
        if r.get("symbol")!=sym or r.get("exchange")!=venue:
            raise ValueError("SOURCE_VENUE_SYMBOL_MISMATCH")
        received=vendor_us(r["local_timestamp"])
        event=vendor_us(r["timestamp"])
        if last_receipt is not None and received<last_receipt:
            raise ValueError("VENDOR_RECEIPT_NONMONOTONIC")
        last_receipt=received
        if first_local is None:first_local=received
        last_local=received
        if not start<=received<stop:
            out_of_day+=1
        while cursor<288 and cutoff[cursor]<received:
            take_quality(cursor,last_oi);cursor+=1
        raw=r.get("open_interest","")
        if raw in ("",None):
            blank+=1
            continue
        try:
            val=float(raw)
            if not math.isfinite(val) or val<0:raise ValueError()
        except (ValueError,TypeError):
            invalid+=1;continue
        if event>received:
            excluded_future+=1;continue
        if start<=received<stop and received<=cutoff[-1]:
            last_oi=(received,event,raw)
    while cursor<288:
        take_quality(cursor,last_oi);cursor+=1
    if count==0 or fresh+stale+missing!=288:
        raise ValueError("SOURCE_DAY_EMPTY_OR_BUCKET_ACCOUNTING_INVALID")
    return {"source_rows":count,"valid_open_interest_rows":count-blank-invalid-excluded_future,
        "blank_open_interest_rows":blank,"invalid_open_interest_rows":invalid,
        "future_exchange_event_excluded":excluded_future,"out_of_day_receipts":out_of_day,
        "vendor_receipt_first":dt.datetime.fromtimestamp(first_local/1e6,UTC).isoformat(),
        "vendor_receipt_last":dt.datetime.fromtimestamp(last_local/1e6,UTC).isoformat(),
        "fresh_5m_vendor_asof_buckets":fresh,"stale_5m_buckets":stale,
        "missing_5m_buckets":missing,"frozen_decision_rule":"closed 5m end +30 seconds; valid nonblank receipt and event <= cutoff; fresh age <=120s",
        "original_exchange_publication":"UNVERIFIED"}

def catalog_one(venue):
    url="https://api.tardis.dev/v1/exchanges/"+venue
    raw,http=load_bytes(url,8_000_000,25)
    if http!=200:raise ValueError("CATALOG_HTTP_NOT_200")
    return json.loads(raw),hashlib.sha256(raw).hexdigest(),url

def sample_one(doc,venue,coin):
    sym=symbol(venue,coin)
    result={"venue":venue,"symbol":sym,"catalog_evidence":"PROVIDER_METADATA_ONLY"}
    try:
        entry=exact_catalog(doc,venue,coin)
        date=first_free_date(entry["availableSince"])
        result["provider_available_since"]=entry["availableSince"]
        result["first_free_month_after_listing"]=date
        yyyy,mm,dd=date.split("-")
        url=f"https://datasets.tardis.dev/v1/{venue}/derivative_ticker/{yyyy}/{mm}/{dd}/{sym}.csv.gz"
        result["sample_url"]=url
        raw,http=load_bytes(url,COMPRESSED_CAP,30)
        if http!=200:raise ValueError("SAMPLE_HTTP_NOT_200")
        with gzip.GzipFile(fileobj=io.BytesIO(raw)) as z:
            plain=z.read(PLAIN_CAP+1)
            if len(plain)>PLAIN_CAP:raise ValueError("CSV_BYTES_CAP_EXCEEDED")
        sample=measure(plain,date,venue,sym)
        result.update(source_sha256=hashlib.sha256(raw).hexdigest(),
             csv_sha256=hashlib.sha256(plain).hexdigest(),
             source_compressed_bytes=len(raw),source_uncompressed_bytes=len(plain),
             crc_eof="PASS",quality=sample,
             status="VERIFIED_VENDOR_RECEIPT_ASOF_EARLIEST_FREE_DAY")
    except urllib.error.HTTPError as e:
        result.update(status="HTTP_UNAVAILABLE_NOT_SOURCE_ABSENCE",http=e.code)
    except Exception as e:
        result.update(status="UNVERIFIED_SAMPLE_OR_SCHEMA",error_type=type(e).__name__,
                      error=str(e)[:150])
    return result

def main():
    import boto3
    OUT.mkdir(exist_ok=True)
    cases=[];catalogs=[]
    for venue in VENUES:
        try:
            source,digest,url=catalog_one(venue)
            catalogs.append({"venue":venue,"catalog_url":url,"catalog_sha256":digest,"status":"CATALOG_SHA256_RECORDED"})
            for coin in COINS:
                case=sample_one(source,venue,coin);cases.append(case)
                print("TARDIS_EARLIEST_FREE",json.dumps({
                   "venue":venue,"symbol":case["symbol"],
                   "catalog_since":case.get("provider_available_since"),
                   "sample_day":case.get("first_free_month_after_listing"),
                   "status":case["status"],
                   "fresh":case.get("quality",{}).get("fresh_5m_vendor_asof_buckets"),
                   "missing":case.get("quality",{}).get("missing_5m_buckets"),
                   "error":case.get("error_type")},ensure_ascii=False),flush=True)
        except Exception as e:
            catalogs.append({"venue":venue,"status":"CATALOG_UNAVAILABLE", "error":type(e).__name__})
            for coin in COINS:
                cases.append({"venue":venue,"symbol":symbol(venue,coin),
                    "status":"CATALOG_UNAVAILABLE_NOT_ABSENCE"})
    if len(cases)!=9:raise ValueError("NINE_INSTRUMENT_TARGETS_REQUIRED")
    report={"schema":"detector-tardis-earliest-free-oi-sample-v1",
       "source":"Tardis official public catalog + first-day-of-following-month derivative_ticker",
       "catalogs":catalogs,"cases":cases,"case_count":len(cases),
       "sample_pass":sum(x["status"]=="VERIFIED_VENDOR_RECEIPT_ASOF_EARLIEST_FREE_DAY" for x in cases),
       "scope":"one free first-of-month day per instrument, not a historical continuous dataset",
       "vendor_receipt":"Tardis local_timestamp; original exchange release NOT established",
       "research_only":True,"edge_status":"EDGE_UNVALIDATED",
       "trading_changes":False,"run_id":os.environ.get("GITHUB_RUN_ID")}
    content=json.dumps(report,ensure_ascii=False,sort_keys=True,indent=2).encode()
    digest=hashlib.sha256(content).hexdigest()
    key=ROOT+"/"+str(os.environ["GITHUB_RUN_ID"])+"-"+str(os.environ.get("GITHUB_RUN_ATTEMPT","1"))+".json"
    client=boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
       aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
    bucket=os.environ["R2_BUCKET"]
    client.put_object(Bucket=bucket,Key=key,Body=content,ContentType="application/json",Metadata={"sha256":digest})
    back=client.get_object(Bucket=bucket,Key=key)["Body"].read(len(content)+1)
    if back!=content or hashlib.sha256(back).hexdigest()!=digest:
        raise ValueError("R2_VERIFIED_BYTE_WRITEBACK_FAILED")
    (OUT/"report.json").write_bytes(content)
    print("TARDIS_EARLIEST_FREE_SUMMARY",json.dumps({
      "cases":len(cases),"sample_pass":report["sample_pass"],
      "source_fail_or_unknown":len(cases)-report["sample_pass"],
      "sha256":digest,"r2_key":key,"edge":"EDGE_UNVALIDATED"},ensure_ascii=False))
if __name__=="__main__":
    main()
