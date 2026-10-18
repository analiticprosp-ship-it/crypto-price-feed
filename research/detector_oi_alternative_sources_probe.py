#!/usr/bin/env python3
"""Read-only single-run feasibility test for alternative 5m OI sources.

No exchange login, API secrets, trade endpoints, R2 writes, or bulk downloads.
Neither historical five-minute bars nor HTTP 200 prove historical publication time.
"""
import datetime as dt
import json
import os
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request

OUT = Path("detector_oi_sources_feasibility")
OUT.mkdir(parents=True, exist_ok=True)
SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
TIMEOUT = 12
MAX_BODY = 100_000

def fetch(url, method="GET"):
    req = urllib.request.Request(
        url,
        method=method,
        headers={"User-Agent": "Detector-H1H10-Research-Feasibility/1.0",
                 "Accept": "application/json" if method == "GET" else "*/*"},
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
            status = response.status
            size = response.headers.get("Content-Length")
            body = response.read(MAX_BODY + 1) if method == "GET" else b""
            if len(body) > MAX_BODY:
                return {"http": status, "outcome": "RESPONSE_TOO_LARGE"}
            return {"http": status, "body": body, "content_length": size}
    except urllib.error.HTTPError as exc:
        return {"http": exc.code, "outcome": "HTTP_ERROR"}
    except Exception as exc:
        return {"http": None, "outcome": type(exc).__name__}

def check_bybit(symbol):
    params = urllib.parse.urlencode({"category":"linear","symbol":symbol,
                                     "intervalTime":"5min","limit":5})
    response = fetch("https://api.bybit.com/v5/market/open-interest?" + params)
    result = {"source":"Bybit", "symbol":symbol, "interval":"5m",
              "http_status":response.get("http")}
    if "body" not in response:
        result["status"] = response.get("outcome", "NO_RESPONSE")
        return result
    try:
        decoded = json.loads(response["body"])
        rows = decoded.get("result", {}).get("list", [])
        timestamps = sorted(int(x["timestamp"]) for x in rows)
        if decoded.get("retCode") != 0 or not timestamps:
            raise ValueError("NO_VALID_5M_ROWS")
        result.update({"status":"AVAILABLE_5M","rows":len(rows),
                       "min_timestamp_ms":min(timestamps), "max_timestamp_ms":max(timestamps),
                       "five_min_step_seen":any(b-a==300_000 for a,b in zip(timestamps,timestamps[1:]))})
    except (ValueError,TypeError,KeyError,AttributeError) as exc:
        result["status"] = "SCHEMA_OR_API_REJECTION"
        result["reason"] = type(exc).__name__
    return result

def check_okx(symbol):
    base = symbol.replace("USDT","")
    response = fetch("https://www.okx.com/api/v5/rubik/stat/contracts/open-interest-history?"
                     + urllib.parse.urlencode({"ccy":base,"period":"5m"}))
    result = {"source":"OKX","symbol":base,"interval":"5m",
              "http_status":response.get("http")}
    if "body" not in response:
        result["status"] = response.get("outcome", "NO_RESPONSE")
        return result
    try:
        decoded=json.loads(response["body"])
        rows=decoded.get("data",[])
        timestamps=sorted(int(row[0]) for row in rows)
        if decoded.get("code") != "0" or not timestamps:
            raise ValueError("NO_VALID_5M_ROWS")
        result.update({"status":"AVAILABLE_5M","rows":len(rows),
                       "min_timestamp_ms":min(timestamps),"max_timestamp_ms":max(timestamps),
                       "five_min_step_seen":any(b-a==300_000 for a,b in zip(timestamps,timestamps[1:]))})
    except (ValueError,TypeError,KeyError,IndexError,AttributeError) as exc:
        result["status"]="SCHEMA_OR_API_REJECTION"
        result["reason"]=type(exc).__name__
    return result

def check_tardis(symbol):
    sample=f"https://datasets.tardis.dev/v1/binance-futures/derivative_ticker/2026/09/01/{symbol}.csv.gz"
    response=fetch(sample,method="HEAD")
    return {"source":"Tardis.dev","symbol":symbol,"interval":"event/sampled",
            "http_status":response.get("http"),
            "status":"SAMPLE_HTTP_200_METADATA_ONLY" if response.get("http")==200 else response.get("outcome","NOT_AVAILABLE"),
            "content_length":response.get("content_length"),
            "notice":"HEAD does NOT verify data rows or OI publication timestamps"}

def main():
    results=[]
    for sym in SYMBOLS:
        results.extend((check_bybit(sym),check_okx(sym),check_tardis(sym)))
    status="SOURCES_FOUND" if any(x["status"]=="AVAILABLE_5M" for x in results) else "NO_CONFIRMED_LIVE_5M_SOURCE"
    report={
        "schema":"detector-oi-alternative-sources-probe-v1",
        "checked_at_utc":dt.datetime.now(dt.timezone.utc).isoformat(),
        "status":status,"research_only":True, "samples":results,
        "interpretation":"API connectivity, five-minute history and data format only; not vendor publication-time validation",
        "not_done":"No historical bulk download, no subscriptions, no change to trading or H1-H10 validation",
    }
    (OUT/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print("OI_ALTERNATIVE_SOURCES",json.dumps(report,ensure_ascii=False),flush=True)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"],"a",encoding="utf-8") as f:
            f.write("## Детектор — проверка альтернативных источников OI\\n\\n")
            f.write(f"- Итог доступности: {status}\\n")
            for r in results:
                f.write(f"- {r['source']} {r['symbol']}: {r['status']} (HTTP {r['http_status']})\\n")
            f.write("- Время фактической публикации: НЕ ПОДТВЕРЖДЕНО\\n")

if __name__=="__main__":
    main()
