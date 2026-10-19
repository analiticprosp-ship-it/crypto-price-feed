#!/usr/bin/env python3
"""RESEARCH_ONLY bounded source-specific historical depth inventory.

Bybit: explicit vintage OI 5m query, preserving errors.
OKX: bounded current 5m/1D response to inspect API schema; no history claim.
Tardis: official catalog per exchange, record each symbol and dataset time scope.
No trading, no paid data, no proxy, no extrapolation, no source equivalence claims.
"""
import datetime as dt
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import time
import urllib.error
import urllib.parse
import urllib.request

SYMBOLS=("BTC","ETH","SOL")
TARDIS_EXCHANGES=("binance","binance-futures","bybit","okex","okex-swap")
VINTAGE_YEARS=(2020,2021,2022,2023,2024,2025,2026)
MAX_BYTES=9_000_000
TIMEOUT_SECONDS=14
OUT=Path("detector_multivenue_depth_v1")
R2_ROOT="research/detector-multivenue-depth/v1"
UTC=dt.timezone.utc
DATE_UTC=dt.datetime.now(UTC).date().isoformat()
USER_AGENT="Detector-H1H10-MultiVenue-Depth-Research/1.0"

def utc_iso():
    return dt.datetime.now(UTC).isoformat()

def get_json(url,cap=MAX_BYTES):
    sent=utc_iso()
    req=urllib.request.Request(url, headers={"User-Agent":USER_AGENT,"Accept":"application/json"})
    try:
        with urllib.request.urlopen(req,timeout=TIMEOUT_SECONDS) as r:
            raw=r.read(cap+1)
            received=utc_iso()
            if len(raw)>cap:
                return {"http":r.status,"status":"RESPONSE_TOO_LARGE","received_at":received}
            parsed=json.loads(raw)
            return {"http":r.status,"status":"HTTP_JSON_RECEIVED",
                    "requested_at":sent,"received_at":received,
                    "sha256":hashlib.sha256(raw).hexdigest(),
                    "bytes":len(raw),"payload":parsed}
    except urllib.error.HTTPError as e:
        return {"http":e.code,"status":"HTTP_ERROR_NOT_HISTORY_PROOF","requested_at":sent,
                "received_at":utc_iso()}
    except Exception as e:
        return {"http":None,"status":"NETWORK_OR_SCHEMA_UNVERIFIED",
                "requested_at":sent,"received_at":utc_iso(),"error_type":type(e).__name__}

def maybe_numeric(value):
    try:
        x=Decimal(str(value))
        return x.is_finite()
    except (ValueError,InvalidOperation,TypeError):
        return False

def bybit_vintage(symbol,year):
    # One historical calendar-day window, never interpreted as complete availability.
    start=int(dt.datetime(year,1,1,tzinfo=UTC).timestamp()*1000)
    end=start+24*3600*1000-1
    params=urllib.parse.urlencode({"category":"linear","symbol":symbol+"USDT",
        "intervalTime":"5min","startTime":start,"endTime":end,"limit":4})
    url="https://api.bybit.com/v5/market/open-interest?"+params
    result={"venue":"Bybit","market":"USDT_linear_perpetual","dataset":"open_interest",
       "symbol":symbol+"USDT","requested_year":year,"window_start_ms":start,
       "window_end_ms":end,"source_url":url}
    fetched=get_json(url,100000)
    result.update({key:fetched.get(key) for key in
          ("http","status","requested_at","received_at","sha256","error_type")})
    raw=fetched.get("payload")
    if not isinstance(raw,dict):
        return result
    result["provider_code"]=raw.get("retCode")
    result["provider_message"]=str(raw.get("retMsg",""))[:80]
    if raw.get("retCode")!=0:
        result["status"]="PROVIDER_REJECTED_OR_UNAVAILABLE"; return result
    envelope=raw.get("result")
    if not isinstance(envelope,dict) or not isinstance(envelope.get("list"),list):
        result["status"]="SCHEMA_UNVERIFIED"; return result
    rows=envelope["list"]
    if len(rows)>4:
        result["status"]="ROW_LIMIT_VIOLATED";return result
    stamps=[];valid=True
    for row in rows:
        if not isinstance(row,dict):
            valid=False;break
        try:
            ts=int(row["timestamp"])
            if not (start<=ts<=end and maybe_numeric(row.get("openInterest"))):
                valid=False
            stamps.append(ts)
        except (KeyError,TypeError,ValueError):
            valid=False
    if not valid or len(stamps)!=len(set(stamps)):
        result["status"]="ROW_TIME_OR_VALUE_INVALID"
    elif stamps:
        result.update(status="BOUNDED_HISTORICAL_VALUES_OBSERVED",
            observations=len(stamps),min_source_label_ms=min(stamps),
            max_source_label_ms=max(stamps),
            oi_value_units="BYBIT_SYMBOL_SPECIFIC_NOT_NORMALIZED",
            original_publication_at="UNVERIFIED",
            first_available_at="NOT_PROVEN")
    else:
        result.update(status="NO_ROWS_IN_TEST_WINDOW_NOT_EARLIEST_PROOF",observations=0)
    return result

def okx_latest(symbol,period):
    params=urllib.parse.urlencode({"instId":symbol+"-USDT-SWAP","period":period,"limit":12})
    url="https://www.okx.com/api/v5/rubik/stat/contracts/open-interest-history?"+params
    result={"venue":"OKX","market":"USDT_SWAP","dataset":"open_interest",
        "symbol":symbol+"-USDT-SWAP","period":period,"source_url":url}
    fetched=get_json(url,180000)
    result.update({key:fetched.get(key) for key in
        ("http","status","requested_at","received_at","sha256","error_type")})
    raw=fetched.get("payload")
    if not isinstance(raw,dict):return result
    result["provider_code"]=raw.get("code")
    result["provider_message"]=str(raw.get("msg",""))[:80]
    if raw.get("code")!="0":
        result["status"]="PROVIDER_REJECTED_OR_UNAVAILABLE";return result
    rows=raw.get("data")
    if not isinstance(rows,list) or len(rows)>12:
        result["status"]="SCHEMA_UNVERIFIED";return result
    times=[];bad=0;sample_cols=0
    for row in rows:
        try:
            ts=int(row[0])
            if not isinstance(row,list) or len(row)<2 or not maybe_numeric(row[1]):
                bad+=1; continue
            times.append(ts);sample_cols=max(sample_cols,len(row))
        except (ValueError,TypeError,IndexError,KeyError):
            bad+=1
    if bad or len(times)!=len(set(times)):
        result["status"]="ROW_TIME_OR_VALUE_INVALID";return result
    result.update(status="LATEST_WINDOW_VALUES_OBSERVED" if times else "NO_ROWS_IN_LATEST_WINDOW",
       observations=len(times),min_source_label_ms=min(times) if times else None,
       max_source_label_ms=max(times) if times else None,sample_column_count=sample_cols,
       original_publication_at="UNVERIFIED",historical_start="NOT_ESTABLISHED",
       contract_unit="UNVERIFIED_USE_EXCHANGE_INSTRUMENT_METADATA")
    return result

def trim_catalog(exchange,parsed):
    if not isinstance(parsed,dict):
        raise ValueError("CATALOG_ROOT_NOT_OBJECT")
    datasets=parsed.get("datasets")
    if not isinstance(datasets,dict):
        return {"exchange":exchange,"status":"DATASET_METADATA_MISSING_OR_SCHEMA_DIFFERENT",
                "top_keys":list(parsed)[:25]}
    listing=datasets.get("symbols",[])
    # Do not silently normalize unknown structures.
    if not isinstance(listing,list):
        return {"exchange":exchange,"status":"SYMBOLS_METADATA_NOT_ARRAY",
                "dataset_keys":list(datasets)[:25]}
    rows=[]
    for record in listing:
        if not isinstance(record,dict):
            continue
        sym=str(record.get("id",""))
        if not sym or sym.upper() in ("SPOT","PERPETUALS","FUTURES","OPTIONS","COMBOS"):
            continue
        matches=[coin for coin in SYMBOLS if sym.upper().startswith(coin) and
            ("USDT" in sym.upper() or "USD" in sym.upper())]
        if not matches:
            continue
        types=record.get("dataTypes",[])
        rows.append({"symbol":sym,"coins":matches,
          "availableSince":record.get("availableSince"),
          "availableTo":record.get("availableTo"),
          "dataTypes":types if isinstance(types,list) else "SCHEMA_UNVERIFIED",
          "catalog_metadata_only":True})
    return {"exchange":exchange,"status":"CATALOG_SYMBOL_METADATA_OBSERVED",
        "catalog_symbol_count":len(listing),"matched_symbol_count":len(rows),
        "exportedUntil":datasets.get("exportedUntil"),
        "matched_symbols":sorted(rows,key=lambda x:x["symbol"])[:120],
        "matched_symbols_truncated":len(rows)>120,
        "original_exchange_publication":"UNVERIFIED",
        "max_purchasable_history":"NOT_MEASURED_NO_SUBSCRIPTION"}

def tardis_catalog(exchange):
    url="https://api.tardis.dev/v1/exchanges/"+exchange
    received=get_json(url,MAX_BYTES)
    out={"venue":"Tardis.dev","exchange":exchange,"source_url":url,
      "http":received.get("http"),"query_status":received.get("status"),
      "metadata_sha256":received.get("sha256"),
      "bytes":received.get("bytes"),
      "checked_at_utc":received.get("received_at"),
      "source_publication_at":"UNVERIFIED"}
    if received.get("status")!="HTTP_JSON_RECEIVED":
        out["status"]="CATALOG_UNAVAILABLE_NOT_DATA_ABSENCE"
        out["error_type"]=received.get("error_type")
        return out
    details=trim_catalog(exchange,received["payload"])
    out.update(details)
    return out

def run():
    OUT.mkdir(exist_ok=True)
    bybit=[]
    for symbol in SYMBOLS:
        for year in VINTAGE_YEARS:
            bybit.append(bybit_vintage(symbol,year))
            time.sleep(0.15)
    okx=[]
    for symbol in SYMBOLS:
        for period in ("5m","1D"):
            okx.append(okx_latest(symbol,period))
            time.sleep(0.15)
    tardis=[tardis_catalog(exchange) for exchange in TARDIS_EXCHANGES]
    result={"schema":"detector-h1h10-multivenue-source-depth-v1",
       "checked_at_utc":utc_iso(),"research_only":True,
       "edge_status":"EDGE_UNVALIDATED","trade_actions":False,
       "bybit_vintage":bybit,"okx_windows":okx,"tardis_catalogs":tardis,
       "quality_interpretation":{
        "bybit":"One 4-row sample at Jan 1 UTC for each queried year; failures/empty windows do not prove absence",
        "okx":"Latest bounded rows at two requested periods; no historic first date or contract unit",
        "tardis":"Metadata provider catalog availability, NOT verified CSV content or paid access",
        "causal_pit":"NONE_OF_THE_ABOVE_PROVE_ORIGINAL_EXCHANGE_FIRST_PUBLICATION",
        "no_lookahead":"No confirmatory backtest or trading use permitted"},
       "limits":["No historical bulk download or subscription",
          "Tardis month-first-day free samples are a separate follow-up",
          "Provider 403/451/429 preserved, no proxy or automated region bypass",
          "All timestamps are venue source-label timestamps, not proven availability",
          "No spot/perp/funding/liquidation comparability inferred from one venue",
          "No Spot/Futures/NAV/P&L/limit changes"]}
    content=json.dumps(result,ensure_ascii=False,sort_keys=True,indent=2).encode()
    digest=hashlib.sha256(content).hexdigest()
    key=R2_ROOT+"/"+str(os.environ.get("GITHUB_RUN_ID","manual"))+"-"+str(os.environ.get("GITHUB_RUN_ATTEMPT","1"))+".json"
    r2={"status":"NOT_CONFIGURED"}
    env=("R2_BUCKET","R2_ACCOUNT_ID","R2_ACCESS_KEY_ID","R2_SECRET_ACCESS_KEY")
    if all(os.environ.get(s) for s in env):
        import boto3
        client=boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
            aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
            aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
        bucket=os.environ["R2_BUCKET"]
        client.put_object(Bucket=bucket,Key=key,Body=content,ContentType="application/json",Metadata={"sha256":digest})
        again=client.get_object(Bucket=bucket,Key=key)["Body"].read(len(content)+1)
        if again!=content or hashlib.sha256(again).hexdigest()!=digest:
            raise ValueError("R2_REPORT_WRITEBACK_INVALID")
        r2={"status":"SHA256_READBACK_PASS","key":key}
    (OUT/"report.json").write_bytes(content)
    print("MULTIVENUE_DEPTH_SUMMARY",json.dumps({
        "status":"EVIDENCE_RECORDED_NOT_PIT_CERTIFIED",
        "bybit_value_windows":sum(x["status"]=="BOUNDED_HISTORICAL_VALUES_OBSERVED" for x in bybit),
        "bybit_api_rejections":sum(x["status"]=="PROVIDER_REJECTED_OR_UNAVAILABLE" for x in bybit),
        "bybit_network_or_http_failures":sum(x["status"] in ("NETWORK_OR_SCHEMA_UNVERIFIED","HTTP_ERROR_NOT_HISTORY_PROOF") for x in bybit),
        "bybit_earliest_tested_observation":{
            symbol:min((x["requested_year"] for x in bybit if x["symbol"]==symbol+"USDT"
            and x["status"]=="BOUNDED_HISTORICAL_VALUES_OBSERVED"),default=None)
            for symbol in SYMBOLS},
        "okx_results":[{"symbol":x["symbol"],"period":x["period"],"status":x["status"],
                         "rows":x.get("observations")} for x in okx],
        "tardis_results":[{"exchange":x["exchange"],"status":x["status"],
                           "matched_symbols":x.get("matched_symbol_count")} for x in tardis],
        "sha256":digest,"r2":r2},ensure_ascii=False),flush=True)

if __name__=="__main__":
    run()
