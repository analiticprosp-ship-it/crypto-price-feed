#!/usr/bin/env python3
"""ONE-TIME pilot of free Coin Metrics BTC Community API daily research metrics.

Separate output from CryptoQuant/Glassnode Exchange Flow contract and from
Detector candidate execution. No paid credentials, no portfolio or prices.json.
Community use: CC BY-NC 4.0, attribution and source URLs preserved.
"""
import csv
import hashlib
import io
import json
import math
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/"research"/"btc-coinmetrics-community-proxy.json"
DIAG=ROOT/"research"/"btc-coinmetrics-community-diagnostics.json"
HOST="https://community-api.coinmetrics.io/v4/timeseries/asset-metrics"
METRICS={
    "CDD":{"meaning":"Coin Days Destroyed; BTC x days of spent UTXO lifetime, not number of 1-3y coins","family":"ONCHAIN_DORMANCY_PROXY","unit":"BTC-days"},
    "SplyAct1Yr":{"meaning":"BTC supply with onchain activity within rolling 1 year, a stock not daily flow","family":"ONCHAIN_ACTIVE_SUPPLY_PROXY","unit":"BTC"},
    "SplyAct3Yr":{"meaning":"BTC supply with onchain activity within rolling 3 years, a stock not daily flow","family":"ONCHAIN_ACTIVE_SUPPLY_PROXY","unit":"BTC"},
}
LICENSE_URL="https://creativecommons.org/licenses/by-nc/4.0/"
ATTRIBUTION="Coin Metrics Community Data; CC BY-NC 4.0; https://coinmetrics.io/"
MAX_ROWS=85

def iso(dt):
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00","Z")

def endpoint(metric,start,end):
    q=urllib.parse.urlencode({"assets":"btc","metrics":metric,"frequency":"1d",
                              "start_time":start,"end_time":end,
                              "page_size":150})
    return HOST+"?"+q

def fetch(url,timeout=15):
    req=urllib.request.Request(url,headers={
        "User-Agent":"detector-research-coinmetrics-community/1.0",
        "Accept":"application/json"})
    with urllib.request.urlopen(req,timeout=timeout) as r:
        body=r.read(2_000_000)
    return body

def read_metric(payload,metric,now):
    if not isinstance(payload,dict) or not isinstance(payload.get("data"),list):
        return [],"INVALID_SCHEMA"
    if payload.get("next_page_url") or payload.get("next_page_token"):
        return [],"PAGINATION_REQUIRED_NOT_SILENTLY_TRUNCATED"
    rows=[]
    for o in payload["data"]:
        if not isinstance(o,dict) or o.get("asset")!="btc" or metric not in o:
            continue
        timestamp=o.get("time")
        try:
            dt=datetime.fromisoformat(timestamp.replace("Z","+00:00"))
        except (TypeError,ValueError):
            continue
        if dt.tzinfo is None or dt>now+timedelta(seconds=5):
            continue
        x=o.get(metric)
        try:
            if isinstance(x,bool):continue
            value=float(x)
            if not math.isfinite(value) or value<0:continue
        except (TypeError,ValueError):
            continue
        # Daily values are observations, not quote timestamps or point-in-time trading triggers.
        rows.append({"dateUtc":dt.date().isoformat(),"value":value})
    dates=[r["dateUtc"] for r in rows]
    if len(dates)!=len(set(dates)):
        return [],"DUPLICATE_DAY_IN_SOURCE"
    rows.sort(key=lambda x:x["dateUtc"])
    if not rows:return [],"NO_VALID_ROWS"
    return rows[-MAX_ROWS:],"OK"

def error_class(ex):
    if isinstance(ex,urllib.error.HTTPError):
        return "HTTP_"+str(ex.code)
    if isinstance(ex,urllib.error.URLError):
        return "NETWORK_"+type(ex.reason).__name__
    return type(ex).__name__

def safe_http_explanation(err):
    """Include bounded public API validation hint. No auth headers are used."""
    if not isinstance(err,urllib.error.HTTPError):
        return None
    try:
        raw=err.read(1400).decode("utf-8","replace")
        body=json.loads(raw)
        if isinstance(body,dict):
            candidate=body.get("message") or body.get("error") or body.get("detail") or body.get("errors")
            if isinstance(candidate,(dict,list)):
                candidate=json.dumps(candidate)
            if isinstance(candidate,str):
                return candidate[:350]
        return raw[:350]
    except Exception:
        return "HTTP_BODY_UNAVAILABLE"

def collect(*,now=None,getter=fetch):
    now=now or datetime.now(timezone.utc)
    start=(now-timedelta(days=80)).date().isoformat()
    end=now.date().isoformat()
    out={"schemaVersion":"btc-coinmetrics-community-proxy-1.0",
         "generatedAt":iso(now),"provider":"Coin Metrics",
         "providerClass":"COMMUNITY_PUBLIC_NO_API_KEY",
         "license":"CC BY-NC 4.0","licenseUrl":LICENSE_URL,
         "attribution":ATTRIBUTION,
         "researchOnly":True,"notTradeApproval":True,
         "notSystemPrice":True,"notExchangeInflow":True,
         "notCryptoQuantSpentAge1to3":True,
         "notVerifiedPointInTime":True,"noTradingScore":True,
         "scopes":["ONCHAIN_DORMANCY_PROXY","ONCHAIN_ACTIVE_SUPPLY_PROXY"],
         "timeNotes":"Historical metric time is a DAILY period label; original first publication/revisions unknown; use no lookahead in backtests",
         "limitations":[
             "Coin Days Destroyed and Active Supply do not isolate moved BTC aged 1-3y",
             "Active Supply 1Y/3Y is a rolling stock, NOT daily output volume or exchange deposit",
             "These metrics are not exchange-labeled BTC inflow/outflow and cannot prove selling",
             "Provider community datasets may be revised; no historical first-known time guaranteed",
             "Noncommercial attribution/reuse is subject to Coin Metrics CC BY-NC 4.0 terms",
             "Separate research only; no automatic Detector candidates or portfolio impact"
         ],"metrics":{}}
    diagnostic={"schemaVersion":"btc-coinmetrics-probe-diagnostics-1.0",
                "generatedAt":iso(now),"provider":"Coin Metrics Community API",
                "access":"PUBLIC_NO_KEY","requested":list(METRICS),
                "statusByMetric":{},"researchOnly":True,"noTradeSignal":True}
    for metric,spec in METRICS.items():
        url=endpoint(metric,start,end)
        explanation=None
        try:
            raw=getter(url)
            obj=json.loads(raw)
            rows,status=read_metric(obj,metric,now)
            reason=status
            digest=hashlib.sha256(raw).hexdigest()
        except (ValueError,UnicodeDecodeError) as exc:
            rows=[];reason="INVALID_JSON";digest=None
        except Exception as exc:
            rows=[];reason=error_class(exc);digest=None
            explanation=safe_http_explanation(exc)
        latest=rows[-1]["dateUtc"] if rows else None
        diagnostic["statusByMetric"][metric]={
            "status":"OBSERVED" if rows else "NO_DATA",
            "reason":reason,"rowCount":len(rows),"lastDataDate":latest,
            "validationHint":explanation}
        if rows:
            out["metrics"][metric]=dict(spec,sourceUrl=url,rawSha256=digest,
                                         sourceDataRetrievalAt=iso(now),
                                         dataAvailabilityTimeKnown=False,
                                         observations=rows)
    diagnostic["validMetrics"]=len(out["metrics"])
    diagnostic["status"]="DATA_OBSERVED" if out["metrics"] else "ALL_SOURCES_UNAVAILABLE"
    out["coverage"]={"validMetrics":len(out["metrics"]),"requestedMetrics":len(METRICS),
                     "latestDates":{k:v["observations"][-1]["dateUtc"] for k,v in out["metrics"].items()}}
    return out,diagnostic

def main():
    payload,diagnostic=collect()
    DIAG.parent.mkdir(parents=True,exist_ok=True)
    DIAG.write_text(json.dumps(diagnostic,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    if not payload["metrics"]:
        print("Coin Metrics: ALL SOURCES UNAVAILABLE",json.dumps(diagnostic["statusByMetric"]))
        raise SystemExit(2)
    DATA.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("Coin Metrics:",json.dumps(diagnostic["statusByMetric"]),flush=True)

if __name__=="__main__":
    main()
