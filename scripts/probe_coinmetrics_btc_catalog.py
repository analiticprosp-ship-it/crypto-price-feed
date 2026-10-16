#!/usr/bin/env python3
"""Discover ACTUALLY AVAILABLE public Coin Metrics Community BTC metrics.

Read-only one-off catalog audit, no API key, no trading signals or candidate updates.
"""
import hashlib
import json
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
URL="https://community-api.coinmetrics.io/v4/catalog-v2/asset-metrics?assets=btc"
OUTPUT=ROOT/"research"/"btc-coinmetrics-supported-metrics.json"
DIAG=ROOT/"research"/"btc-coinmetrics-catalog-diagnostics.json"
SEARCH=("age","spent","cdd","supply","sply","flow","utxo","hodl","dorm","coin","act","val")

def fetch():
    req=urllib.request.Request(URL,headers={"User-Agent":"detector-coinmetrics-community-catalog/1.0",
                                            "Accept":"application/json"})
    with urllib.request.urlopen(req,timeout=15) as response:
        return response.read(3_000_000)

def extract(body):
    if not isinstance(body,dict) or not isinstance(body.get("data"),list):
        return None,"INVALID_CATALOG_RESPONSE"
    btc=next((x for x in body["data"] if isinstance(x,dict) and x.get("asset")=="btc"),None)
    if not btc or not isinstance(btc.get("metrics"),list):
        return None,"BTC_METRICS_NOT_IN_CATALOG"
    result=[]
    for entry in btc["metrics"]:
        if not isinstance(entry,dict):continue
        mid=entry.get("metric")
        if not isinstance(mid,str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{1,90}",mid):
            continue
        frequencies=entry.get("frequencies")
        result.append({"metric":mid,
                       "frequencies":[{"frequency":v.get("frequency"),
                                        "minTime":v.get("min_time"),
                                        "maxTime":v.get("max_time")}
                                       for v in frequencies if isinstance(v,dict)]
                       if isinstance(frequencies,list) else []})
    if not result:return None,"BTC_CATALOG_NO_VALID_METRIC_IDS"
    by_name={x["metric"]:x for x in result}
    return {"availableMetricCount":len(by_name),
            "relevant":[by_name[k] for k in sorted(by_name) if any(t in k.lower() for t in SEARCH)],
            "candidateCheck":{k:k in by_name for k in ("CDD","SplyAct1Yr","SplyAct3Yr","SplyActPct1yr","TxTfrValAdjNtv","TxCnt")},
            "allMetricIds":sorted(by_name)
           },"OK"

def main():
    at=datetime.now(timezone.utc).isoformat()
    try:
        raw=fetch()
        payload=json.loads(raw)
        parsed,status=extract(payload)
        err=None
    except urllib.error.HTTPError as exc:
        parsed=None;status="HTTP_"+str(exc.code)
        err=exc.read(650).decode("utf-8","replace")
        raw=None
    except Exception as exc:
        parsed=None;status="ERROR_"+type(exc).__name__
        err=None;raw=None
    OUTPUT.parent.mkdir(parents=True,exist_ok=True)
    diagnostic={"generatedAt":at,"sourceUrl":URL,"status":status,
                "errorSnippet":err[:350] if err else None,"researchOnly":True,
                "noTradeSignal":True}
    DIAG.write_text(json.dumps(diagnostic,indent=2)+"\n")
    if parsed is None:
        print("Community BTC catalog probe:",status)
        raise SystemExit(2)
    output={"schemaVersion":"btc-coinmetrics-public-catalog-1.0",
            "generatedAt":at,"sourceUrl":URL,
            "sourceSha256":hashlib.sha256(raw).hexdigest(),
            "license":"Coin Metrics Community data CC BY-NC 4.0",
            "researchOnly":True,"notTradeApproval":True,
            "notCryptoQuantAgeFlow":True,
            "notHistoricalOnchainData":True,
            "notes":"Metric catalog metadata only. Names are not downloaded numerical observations.",
            **parsed}
    OUTPUT.write_text(json.dumps(output,indent=2)+"\n")
    print("BTC public catalog metrics:",output["availableMetricCount"],
          "relevant:",len(output["relevant"]), "requested:",output["candidateCheck"])

if __name__=="__main__":
    main()
