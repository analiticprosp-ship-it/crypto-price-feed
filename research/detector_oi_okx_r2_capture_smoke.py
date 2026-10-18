#!/usr/bin/env python3
"""One-time read-only OKX 5m OI sample capture to existing private R2.
A successful historical query proves only availability at *this request time*.
It does NOT prove historical event-time publication or causality.
"""
import datetime as dt
import hashlib
import json
import os
import time
import urllib.parse
import urllib.request
import boto3

SYMBOLS = ("BTC", "ETH", "SOL")
PREFIX = "research/oi-availability-okx/v1/probes/"
MAX_RESPONSE_BYTES = 120_000


def timestamp(ms):
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).isoformat()


def fetch(symbol):
    instrument = symbol + "-USDT-SWAP"
    path = "/api/v5/rubik/stat/contracts/open-interest-history?"
    url = "https://www.okx.com" + path + urllib.parse.urlencode({
        "instId": instrument, "period": "5m", "limit": 100,
    })
    before = int(time.time() * 1000)
    started = time.monotonic_ns()
    request = urllib.request.Request(url,headers={
        "Accept":"application/json","User-Agent":"Detector-H1H10-Research/1.0",
    })
    with urllib.request.urlopen(request,timeout=15) as response:
        status=response.status
        server_date=response.headers.get("Date")
        body=response.read(MAX_RESPONSE_BYTES+1)
    received=int(time.time()*1000)
    if status != 200 or len(body)>MAX_RESPONSE_BYTES:
        raise ValueError("OI_HTTP_OR_SIZE_INVALID")
    payload=json.loads(body)
    if payload.get("code")!="0":
        raise ValueError("OI_API_ERROR")
    rows=payload.get("data")
    if not isinstance(rows,list) or not rows or len(rows)>100:
        raise ValueError("OI_ROWS_MISSING")
    labels=[]
    for row in rows:
        if not isinstance(row,list) or len(row)<2:
            raise ValueError("OI_INVALID_ROW_SCHEMA")
        label=int(row[0])
        if label < 1600000000000 or label > received + 60000:
            raise ValueError("OI_TIMESTAMP_OUT_OF_RANGE")
        labels.append(label)
    if len(set(labels))!=len(labels):
        raise ValueError("OI_TIMESTAMP_DUPLICATED")
    labels.sort()
    return {
        "provider":"OKX","instrument":instrument,
        "source_endpoint":"/api/v5/rubik/stat/contracts/open-interest-history",
        "interval_requested":"5m",
        "request_started_ms":before,"response_received_ms":received,
        "request_duration_ms":int((time.monotonic_ns()-started)/1_000_000),
        "http_date_header":server_date,
        "source_label_min_ms":labels[0],"source_label_max_ms":labels[-1],
        "consecutive_five_minute_labels":all(y-x==300000 for x,y in zip(labels,labels[1:])),
        "row_count":len(rows),"raw_api_data":rows,
        "timing_scope":"API data had arrived by response_received_ms; historical availability is not established",
    }


def main():
    observations=[fetch(sym) for sym in SYMBOLS]
    run=os.environ["GITHUB_RUN_ID"]
    attempt=os.environ.get("GITHUB_RUN_ATTEMPT","1")
    dataset={
        "schema":"detector-okx-oi5m-one-shot-v1",
        "captured_at_utc":dt.datetime.now(dt.timezone.utc).isoformat(),
        "run_id":run,"attempt":attempt,"observations":observations,
        "research_only":True,
        "publication_status":"UNVERIFIED",
        "no_trading_or_portfolio_changes":True,
    }
    data=json.dumps(dataset,ensure_ascii=False,sort_keys=True).encode()
    digest=hashlib.sha256(data).hexdigest()
    client=boto3.client(
        "s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto",
    )
    key=PREFIX+run+"-"+attempt+".json"
    client.put_object(Bucket=os.environ["R2_BUCKET"],Key=key,Body=data,
                      ContentType="application/json",Metadata={"sha256":digest})
    readback=client.get_object(Bucket=os.environ["R2_BUCKET"],Key=key)["Body"].read(len(data)+1)
    if hashlib.sha256(readback).hexdigest()!=digest:
        raise ValueError("R2_READBACK_SHA256_MISMATCH")
    result={"status":"CAPTURE_PASS","run_id":run,"r2_key":key,"sha256":digest,
            "symbols":{x["instrument"]:{"rows":x["row_count"],
                      "label_min_utc":timestamp(x["source_label_min_ms"]),
                      "label_max_utc":timestamp(x["source_label_max_ms"]),
                      "response_received_utc":timestamp(x["response_received_ms"]),
                      "five_minute_continuity":x["consecutive_five_minute_labels"]}
                       for x in observations},
            "publication_time":"UNVERIFIED"}
    print("OKX_OI5M_R2_CAPTURE",json.dumps(result,ensure_ascii=False),flush=True)
    path=os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path,"a",encoding="utf-8") as f:
            f.write("## OKX OI 5m — single verified R2 capture\\n\\n")
            f.write(f"- Result: CAPTURE_PASS\\n- SHA-256: {digest}\\n")
            for name,info in result["symbols"].items():
                f.write(f"- {name}: {info['rows']} records, five-minute continuity {info['five_minute_continuity']}\\n")
            f.write("- OI historical publication time: UNVERIFIED\\n")


if __name__=="__main__":
    main()
