#!/usr/bin/env python3
"""Bounded independent Tardis free CSV receipt audit + OKX historical-window OI probe.

Proof levels deliberately separate vendor metadata, archive bytes/receipt timestamps,
and API source labels. Never claim historical point-in-time exchange publication.
No subscriptions, API keys, proxies, orders, position or portfolio changes.
"""
import csv, datetime as dt, gzip, hashlib, io, json, math, os, time
import urllib.error, urllib.parse, urllib.request
from pathlib import Path

UTC=dt.timezone.utc
ROOT="research/detector-free-tardis-okx-history-audit/v1"
OUT=Path("detector_free_tardis_okx_history")
PARENT_KEY="research/detector-multivenue-depth/v1/39283941176-1.json"
PARENT_SHA="c0bc98d6d146d08cb98bdcea96365b5cad810f222bc6b73b8c6af7ffba30b80d"
MARKETS=("binance-futures","bybit","okex-swap")
COINS=("BTC","ETH","SOL")
SAMPLE_DATES=("2024-01-01","2026-09-01")
OKX_YEARS=(2021,2022,2023,2024,2025,2026)
MAX_GZ=10_000_000
MAX_PLAIN=55_000_000
MAX_ROWS=300_000
UA="Detector-H1H10-Historical-Forensic/1.0"

def source_symbol(exchange,coin):
    if exchange not in MARKETS or coin not in COINS:raise ValueError("BAD_VENUE_SYMBOL")
    return coin+"-USDT-SWAP" if exchange=="okex-swap" else coin+"USDT"

def dt_utc(s):
    x=dt.datetime.fromisoformat(str(s).strip().replace("Z","+00:00"))
    if x.tzinfo is None:raise ValueError("RECEIPT_TIMESTAMP_NAIVE")
    if x.utcoffset()!=dt.timedelta(0):x=x.astimezone(UTC)
    return x

def load_bytes(url,limit,timeout=25):
    req=urllib.request.Request(url,headers={"User-Agent":UA,"Accept":"*/*"})
    with urllib.request.urlopen(req,timeout=timeout) as resp:
        raw=resp.read(limit+1)
        if len(raw)>limit:raise ValueError("DOWNLOAD_LIMIT_REACHED")
        return raw,resp.status

def verify_catalog(meta,exchange,coin,day):
    if meta.get("exchange")!=exchange or meta.get("status")!="CATALOG_SYMBOL_METADATA_OBSERVED":
        raise ValueError("CATALOG_NOT_VERIFIED")
    s=source_symbol(exchange,coin)
    choices=[x for x in meta.get("matched_symbols",[]) if x.get("symbol")==s]
    if len(choices)!=1:raise ValueError("CATALOG_SYMBOL_MISSING_OR_AMBIGUOUS")
    x=choices[0]
    if "derivative_ticker" not in x.get("dataTypes",[]):raise ValueError("CATALOG_DERIVATIVE_TICKER_UNAVAILABLE")
    start=x.get("availableSince")
    if not start or day < start[:10]:return None
    return x

def parse_tardis_csv(raw,sample_day):
    compressed_sha=hashlib.sha256(raw).hexdigest()
    # Bounded expansion while streaming gzip: CRC is checked only on reaching EOF.
    with gzip.GzipFile(fileobj=io.BytesIO(raw)) as gz:
        data=gz.read(MAX_PLAIN+1)
        if len(data)>MAX_PLAIN:raise ValueError("DECOMPRESSED_LIMIT_REACHED")
    content_sha=hashlib.sha256(data).hexdigest()
    decoded=io.TextIOWrapper(io.BytesIO(data),encoding="utf-8-sig",newline="")
    reader=csv.DictReader(decoded)
    fields=reader.fieldnames or []
    if not {"local_timestamp","timestamp"}.issubset(fields):
        raise ValueError("VENDOR_RECEIPT_COLUMNS_MISSING")
    obs=missing_oi=invalid_oi=out_of_day=receipt_backwards=0
    prior=None;lo=hi=None;seen_5m=set()
    day=dt.date.fromisoformat(sample_day)
    oi_cols=[x for x in ("open_interest","open_interest_value") if x in fields]
    for row in reader:
        obs+=1
        if obs>MAX_ROWS:raise ValueError("MAX_ROWS_EXCEEDED")
        t=dt_utc(row["local_timestamp"])
        if t.date()!=day:out_of_day+=1
        if prior is not None and t<prior:receipt_backwards+=1
        prior=t
        lo=t if lo is None or t<lo else lo
        hi=t if hi is None or t>hi else hi
        if t.date()==day:seen_5m.add(t.hour*12+t.minute//5)
        if "open_interest" not in row or row["open_interest"] in ("",None):
            missing_oi+=1
        else:
            try:
                v=float(row["open_interest"])
                if not math.isfinite(v) or v<0:invalid_oi+=1
            except (ValueError,TypeError):invalid_oi+=1
    if not obs:raise ValueError("EMPTY_VENDOR_CSV")
    return {"compressed_sha256":compressed_sha,"csv_sha256":content_sha,
       "compressed_bytes":len(raw),"csv_bytes":len(data),
       "rows":obs,"fields":fields[:60],
       "first_receipt_utc":lo.isoformat() if lo else None,
       "last_receipt_utc":hi.isoformat() if hi else None,
       "unique_5m_receipt_buckets":len(seen_5m),
       "missing_open_interest_rows":missing_oi,
       "invalid_open_interest_rows":invalid_oi,
       "out_of_day_receipt_rows":out_of_day,
       "receipt_order_reversals":receipt_backwards,
       "gzip_crc_eof_read":"PASS",
       "receipt_proof":"VENDOR_CAPTURE_RECEIPT_TIME_ONLY",
       "original_exchange_publication_time":"UNVERIFIED"}

def tardis_one(meta,exchange,coin,day):
    symbol=source_symbol(exchange,coin)
    evidence={"source":"Tardis.dev","exchange":exchange,"coin":coin,"symbol":symbol,
              "sample_day_utc":day,"status":"NOT_CHECKED"}
    try:
        entry=verify_catalog(meta,exchange,coin,day)
        if entry is None:
            evidence["status"]="BEFORE_PROVIDER_CATALOG_AVAILABLE_SINCE"
            return evidence
        yyyy,mm,dd=day.split("-")
        url=f"https://datasets.tardis.dev/v1/{exchange}/derivative_ticker/{yyyy}/{mm}/{dd}/{symbol}.csv.gz"
        evidence["source_url"]=url
        raw,http=load_bytes(url,MAX_GZ,30)
        if http!=200:raise ValueError("HTTP_NON_200")
        evidence["quality"]=parse_tardis_csv(raw,day)
        q=evidence["quality"]
        evidence["status"]=("VENDOR_GZIP_RECEIPT_PASS" if
            q["out_of_day_receipt_rows"]==0 and q["receipt_order_reversals"]==0 and
            q["invalid_open_interest_rows"]==0 and q["missing_open_interest_rows"]<q["rows"]
            else "VENDOR_CONTENT_PARTIAL")
        evidence["provider_available_since"]=entry.get("availableSince")
    except urllib.error.HTTPError as e:
        evidence.update(status="HTTP_UNAVAILABLE_NOT_ABSENCE",http_code=e.code)
    except Exception as e:
        evidence.update(status="CONTENT_OR_NETWORK_UNVERIFIED",error_type=type(e).__name__,error=str(e)[:120])
    return evidence

def okx_one(coin,year):
    symbol=coin+"-USDT-SWAP"
    start=int(dt.datetime(year,1,1,tzinfo=UTC).timestamp()*1000)
    end=int(dt.datetime(year,2,1,tzinfo=UTC).timestamp()*1000)-1
    q=urllib.parse.urlencode({"instId":symbol,"period":"5m","begin":start,"end":end,"limit":20})
    url="https://www.okx.com/api/v5/rubik/stat/contracts/open-interest-history?"+q
    out={"venue":"OKX","instId":symbol,"target_year":year,"period":"5m",
       "target_start_ms":start,"target_end_ms":end,"source_url":url,
       "original_publication_time":"UNVERIFIED"}
    try:
        raw,http=load_bytes(url,200_000,15)
        out["http"]=http;out["response_sha256"]=hashlib.sha256(raw).hexdigest()
        payload=json.loads(raw)
        out["provider_code"]=payload.get("code")
        if http!=200 or payload.get("code")!="0":
            out["status"]="API_NOT_SUCCESS_NOT_HISTORY_ABSENCE";return out
        rows=payload.get("data")
        if not isinstance(rows,list) or len(rows)>20:
            out["status"]="API_SCHEMA_UNVERIFIED";return out
        stamps=[]
        for row in rows:
            if not isinstance(row,list) or len(row)<2:
                raise ValueError("BAD_OI_ROW_SCHEMA")
            stamp=int(row[0])
            val=float(row[1])
            if not math.isfinite(val) or val<0:raise ValueError("BAD_OI_NUMERIC")
            stamps.append(stamp)
        if len(stamps)!=len(set(stamps)):raise ValueError("DUPLICATE_API_LABELS")
        inside=[x for x in stamps if start<=x<=end]
        out.update(returned_rows=len(stamps),in_target_rows=len(inside),
             first_returned_label_ms=min(stamps) if stamps else None,
             last_returned_label_ms=max(stamps) if stamps else None,
             response_outside_target_rows=len(stamps)-len(inside),
             status=("HISTORICAL_WINDOW_SOURCE_LABELS_OBSERVED" if inside
               else "OUT_OF_TARGET_OR_EMPTY_NO_DEPTH_PROOF"))
    except urllib.error.HTTPError as e:
        out.update(status="HTTP_BLOCKED_NOT_HISTORY_ABSENCE",http=e.code)
    except Exception as e:
        out.update(status="SOURCE_UNVERIFIED",error_type=type(e).__name__,error=str(e)[:120])
    return out

def read_pinned(s3,bucket):
    response=s3.get_object(Bucket=bucket,Key=PARENT_KEY)
    raw=response["Body"].read(300_000)
    if hashlib.sha256(raw).hexdigest()!=PARENT_SHA:raise ValueError("PINNED_CATALOG_SHA_MISMATCH")
    parent=json.loads(raw)
    if parent.get("schema")!="detector-h1h10-multivenue-source-depth-v1":raise ValueError("CATALOG_SCHEMA_MISMATCH")
    metas={r["exchange"]:r for r in parent["tardis_catalogs"]}
    if set(metas)!={"binance","binance-futures","bybit","okex","okex-swap"}:
        raise ValueError("PINNED_CATALOG_COMPLETENESS_MISMATCH")
    return metas

def main():
    import boto3
    OUT.mkdir(exist_ok=True)
    client=boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
      aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
      aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
    bucket=os.environ["R2_BUCKET"]
    metas=read_pinned(client,bucket)
    tardis=[]
    for ex in MARKETS:
      for coin in COINS:
        # Fixed early and recent free sample per instrument, never other dates.
        for day in SAMPLE_DATES:
          item=tardis_one(metas[ex],ex,coin,day)
          tardis.append(item)
          print("TARDIS_SAMPLE",json.dumps({"exchange":ex,"symbol":item["symbol"],
             "day":day,"status":item["status"],"rows":item.get("quality",{}).get("rows"),
             "buckets":item.get("quality",{}).get("unique_5m_receipt_buckets"),
             "error":item.get("error_type"),"http":item.get("http_code")}),flush=True)
    okx=[]
    for coin in COINS:
      for year in OKX_YEARS:
        item=okx_one(coin,year);okx.append(item)
        print("OKX_HISTORY",json.dumps({"symbol":item["instId"],"year":year,
           "status":item["status"],"in_window":item.get("in_target_rows"),
           "rows":item.get("returned_rows"),"error":item.get("error_type")}),flush=True)
        time.sleep(0.18)
    report={"schema":"detector-h1h10-tardis-free-csv-okx-vintage-audit-v1",
      "run_id":os.environ.get("GITHUB_RUN_ID"),"parent_key":PARENT_KEY,"parent_sha256":PARENT_SHA,
      "Tardis_free_samples":tardis,"OKX_historical_time_windows":okx,
      "research_only":True,"edge_status":"EDGE_UNVALIDATED",
      "source_publication_time":"UNVERIFIED","portfolio_and_trading_mutations":False,
      "limitations":["Tardis first-of-month free receipt times DO NOT prove exchange release times",
         "Tardis free sample days not continuity for untested dates",
         "OKX vintage probe observes max 20 rows, not annual archive depth",
         "Empty/blocked/out-of-window historical responses never prove missing source",
         "OI values are exchange-specific native units, NOT cross-venue normalized",
         "No data eligible for confirmatory H1-H10 by this probe alone"]}
    body=json.dumps(report,sort_keys=True,ensure_ascii=False,indent=2).encode()
    digest=hashlib.sha256(body).hexdigest()
    key=ROOT+"/"+str(os.environ["GITHUB_RUN_ID"])+"-"+str(os.environ.get("GITHUB_RUN_ATTEMPT","1"))+".json"
    client.put_object(Bucket=bucket,Key=key,Body=body,ContentType="application/json",Metadata={"sha256":digest})
    copied=client.get_object(Bucket=bucket,Key=key)["Body"].read(len(body)+1)
    if copied!=body or hashlib.sha256(copied).hexdigest()!=digest:
        raise ValueError("R2_WRITE_READBACK_SHA_MISMATCH")
    (OUT/"report.json").write_bytes(body)
    print("FREE_TARDIS_OKX_AUDIT_SUMMARY",json.dumps({
      "tardis_pass":sum(x["status"]=="VENDOR_GZIP_RECEIPT_PASS" for x in tardis),
      "tardis_partial":sum(x["status"]=="VENDOR_CONTENT_PARTIAL" for x in tardis),
      "tardis_unavailable":sum(x["status"] not in ("VENDOR_GZIP_RECEIPT_PASS","VENDOR_CONTENT_PARTIAL") for x in tardis),
      "okx_vintage_observed":sum(x["status"]=="HISTORICAL_WINDOW_SOURCE_LABELS_OBSERVED" for x in okx),
      "okx_outside_or_empty":sum(x["status"]=="OUT_OF_TARGET_OR_EMPTY_NO_DEPTH_PROOF" for x in okx),
      "sha256":digest,"r2_key":key,"status":"SOURCE_SPECIFIC_EVIDENCE_ONLY_EDGE_UNVALIDATED"},ensure_ascii=False))
if __name__=="__main__":
    main()
