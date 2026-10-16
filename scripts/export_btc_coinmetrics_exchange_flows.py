#!/usr/bin/env python3
"""One-time BTC Coin Metrics Community EXCHANGE flows daily CSV+JSON export.

Actual Coin Metrics community-supported metrics: FlowInExNtv,
FlowOutExNtv, SplyExNtv. No age 1-3y classification, no sales inference.
CC BY-NC 4.0 attribution. Source first-available time/vintages unknown.
"""
import csv
import hashlib
import io
import json
import math
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"research"/"btc-exchange-flows-coinmetrics.json"
CSV=ROOT/"research"/"btc-exchange-flows-coinmetrics.csv"
DIAG=ROOT/"research"/"btc-exchange-flows-coinmetrics-diagnostics.json"
BASE="https://community-api.coinmetrics.io/v4/timeseries/asset-metrics"
METRICS={
    "FlowInExNtv":("exchangeInflowBtc","BTC/day"),
    "FlowOutExNtv":("exchangeOutflowBtc","BTC/day"),
    "SplyExNtv":("exchangeReserveBtc","BTC stock")
}
LICENSE="https://creativecommons.org/licenses/by-nc/4.0/"

def iso(dt):return dt.astimezone(timezone.utc).isoformat().replace("+00:00","Z")

def source_url(name, now):
    start=(now-timedelta(days=100)).date().isoformat()
    end=(now-timedelta(days=1)).date().isoformat() # no current incomplete day
    return BASE+"?"+urllib.parse.urlencode({"assets":"btc","metrics":name,"frequency":"1d",
                                          "start_time":start,"end_time":end,"page_size":130})

def retrieve(url):
    req=urllib.request.Request(url,headers={
        "User-Agent":"independent-detector-btc-exchange-research/1.0",
        "Accept":"application/json"})
    with urllib.request.urlopen(req,timeout=15) as stream:
        return stream.read(2_000_000)

def decode_rows(blob, metric, now):
    payload=json.loads(blob)
    if not isinstance(payload,dict) or not isinstance(payload.get("data"),list):
        return [],"INVALID_PROVIDER_SCHEMA"
    if payload.get("next_page_url") or payload.get("next_page_token"):
        return [],"PAGINATION_NOT_IMPLEMENTED"
    bydate={}
    for row in payload["data"]:
        if not isinstance(row,dict) or row.get("asset")!="btc" or metric not in row:
            continue
        try:
            date=datetime.fromisoformat(row["time"].replace("Z","+00:00"))
        except (TypeError,ValueError,KeyError):
            continue
        if not date.tzinfo or date>=now.replace(hour=0,minute=0,second=0,microsecond=0):
            continue
        try:
            if isinstance(row[metric],bool):continue
            n=float(row[metric])
            if not math.isfinite(n) or n<0:continue
        except (TypeError,ValueError):
            continue
        d=date.date().isoformat()
        if d in bydate:
            return [],"DUPLICATED_DAY"
        bydate[d]=n
    if not bydate:return [],"NO_VALID_DAILY_ROWS"
    return [{"dateUtc":d,"value":bydate[d]} for d in sorted(bydate)],"OK"

def safe_err(e):
    if isinstance(e,urllib.error.HTTPError):
        return "HTTP_"+str(e.code)
    if isinstance(e,urllib.error.URLError):
        return "NETWORK_"+type(e.reason).__name__
    return type(e).__name__

def get_export(*,now=None,fetch=retrieve):
    now=now or datetime.now(timezone.utc)
    allrows={}
    metas={}
    results={}
    for metric,(field,units) in METRICS.items():
        url=source_url(metric,now)
        try:
            raw=fetch(url)
            rows,status=decode_rows(raw,metric,now)
            sha=hashlib.sha256(raw).hexdigest()
        except Exception as e:
            rows=[];status=safe_err(e);sha=None
        results[metric]={"status":"OBSERVED" if rows else "NO_DATA",
                         "reason":status,"count":len(rows),
                         "mostRecentDay":rows[-1]["dateUtc"] if rows else None}
        if rows:
            allrows[field]={r["dateUtc"]:r["value"] for r in rows}
            metas[metric]={"sourceUrl":url,"sha256RawResponse":sha,
                           "field":field,"units":units,
                           "retrievedAt":iso(now)}
    dates=sorted(set(d for v in allrows.values() for d in v))
    daily=[]
    for d in dates:
        row={"dateUtc":d}
        for _,(field,unit) in METRICS.items():
            row[field]=allrows.get(field,{}).get(d)
        a,b=row["exchangeInflowBtc"],row["exchangeOutflowBtc"]
        row["netflowBtc"]=round(a-b,8) if a is not None and b is not None else None
        daily.append(row)
    diagnostic={"schemaVersion":"btc-community-flow-export-diagnostics-1.0",
                "generatedAt":iso(now),"status":"DATA_OBSERVED" if daily else "NO_DATA",
                "metricResults":results,
                "researchOnly":True,"notTradeApproval":True,
                "notSystemPrice":True}
    report={"schemaVersion":"btc-coinmetrics-exchange-flow-1.0",
            "generatedAt":iso(now),"provider":"Coin Metrics Community",
            "license":"CC BY-NC 4.0","licenseUrl":LICENSE,
            "attribution":"Coin Metrics; https://coinmetrics.io/; noncommercial use only",
            "asset":"BTC","frequency":"1d","metricSources":metas,
            "data":daily,
            "researchOnly":True,"notTradeApproval":True,"notSystemPrice":True,
            "notCurrentPrice":True,"notCohortAgeMetric":True,
            "notProofOfExecutedSales":True,"notPointInTimeBacktestReady":True,
            "notImportedToDetectorCandidates":True,
            "calculation":{"netflowBtc":"FlowInExNtv - FlowOutExNtv; same derived flow family",
                           "exchangeReserveBtc":"SplyExNtv, exchange labeled wallet balances; stock not daily turnover"},
            "limitations":[
                "Daily BTC exchange-labeled flows, NOT dormant 1-3y UTXO movements",
                "Inflow to exchange does not prove actual sale or directional derivatives positioning",
                "Exchange address tagging incomplete, provider can revise old data",
                "Historical first-availableAt and revisions not preserved, point-in-time backtest not established",
                "No live 15m alignment with price/taker flow; non-voting research only",
                "CC BY-NC 4.0 attribution applies to data exports"]
           }
    return report,diagnostic

def write():
    report,diag=get_export()
    DIAG.parent.mkdir(parents=True,exist_ok=True)
    DIAG.write_text(json.dumps(diag,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    if not report["data"]:
        print("No Coin Metrics exchange flow rows:",json.dumps(diag["metricResults"]))
        raise SystemExit(2)
    OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    with CSV.open("w",newline="",encoding="utf-8") as f:
        f.write("# Coin Metrics Community Data; CC BY-NC 4.0; https://coinmetrics.io/; research only\n")
        writer=csv.DictWriter(f,fieldnames=["dateUtc","exchangeInflowBtc","exchangeOutflowBtc",
                                          "netflowBtc","exchangeReserveBtc"])
        writer.writeheader()
        for d in report["data"]:
            writer.writerow({k:"" if v is None else v for k,v in d.items()})
    print("BTC Exchange Flow rows",len(report["data"]),"metric statuses:",json.dumps(diag["metricResults"]))

if __name__=="__main__":
    write()
