#!/usr/bin/env python3
"""Serverless Detector research feed: closed Binance perpetual taker-volume bars
and Bybit linear open-interest observations, queried by REST on GitHub Actions.

Independent research. No trade permission, account, orders, CVD from tick streams,
live pricing, historical liquidation claims, or false backfill.
"""
import json
import math
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"detector-rest-flow.json"
P5=5*60_000
MAX_AGE=20*60_000
MAX_TICKERS=15

def finite_positive(value):
    try:
        x=float(value)
        return x if math.isfinite(x) and x>0 else None
    except (ValueError,TypeError):
        return None

def get_json(url,timeout=10):
    req=urllib.request.Request(url,headers={
        "User-Agent":"independent-detector-rest-research/1.0",
        "Accept":"application/json"})
    with urllib.request.urlopen(req,timeout=timeout) as r:
        return json.load(r)

def fetch_taker(symbol, getter=get_json):
    params=urllib.parse.urlencode({"symbol":symbol+"USDT","period":"5m","limit":16})
    return getter("https://fapi.binance.com/futures/data/takerlongshortRatio?"+params)

def fetch_oi(symbol, getter=get_json):
    params=urllib.parse.urlencode({"category":"linear","symbol":symbol+"USDT",
                                  "intervalTime":"5min","limit":16})
    return getter("https://api.bybit.com/v5/market/open-interest?"+params)

def taker_result(raw, now_ms):
    """Binance USDT-M aggregate taker buy/sell in BASE units, not trade-by-trade CVD."""
    if not isinstance(raw,list):
        return {"status":"NO_DATA","reason":"INVALID_SOURCE_RESPONSE"}
    rows={}
    for rec in raw:
        if not isinstance(rec,dict):
            continue
        try: t=int(rec["timestamp"])
        except (KeyError,ValueError,TypeError): continue
        buy=finite_positive(rec.get("buyVol"))
        sell=finite_positive(rec.get("sellVol"))
        # True zero may be legitimate, but API availability cannot be inferred from absent rows.
        if buy is None or sell is None or t<0 or t+P5>now_ms-30000:
            continue
        rows[t]={"t":t,"buyBase":buy,"sellBase":sell}
    bars=[rows[t] for t in sorted(rows)]
    if not bars or now_ms-(bars[-1]["t"]+P5)>MAX_AGE:
        return {"status":"NO_DATA","reason":"MISSING_OR_STALE_CLOSED_5M"}
    last=bars[-1]
    def summarize(subset):
        buy=sum(x["buyBase"] for x in subset)
        sell=sum(x["sellBase"] for x in subset)
        return {"buyBase":round(buy,8),"sellBase":round(sell,8),
                "deltaBase":round(buy-sell,8),
                "imbalance":round((buy-sell)/(buy+sell),6) if buy+sell else None}
    value={"status":"OBSERVED","source":"Binance USD-M perpetual","periodMs":P5,
           "lastClosed5mEndMs":last["t"]+P5,
           "ageMs":now_ms-(last["t"]+P5),"window5m":summarize([last]),
           "window15m":None,"priorWindow15m":None,
           "dataMeaning":"AGGREGATED_TAKER_BUY_SELL_BASE_VOLUME_NOT_TICK_CVD",
           "notSpotFlow":True}
    if len(bars)>=3 and all(bars[-k]["t"]-bars[-k-1]["t"]==P5 for k in (1,2)):
        value["window15m"]=summarize(bars[-3:])
    if len(bars)>=6 and all(bars[-k]["t"]-bars[-k-1]["t"]==P5 for k in range(1,6)):
        value["priorWindow15m"]=summarize(bars[-6:-3])
    return value

def oi_result(raw, symbol, now_ms):
    """Observed Bybit linear OI snapshots; never sum with other venues."""
    if not isinstance(raw,dict) or raw.get("retCode")!=0:
        return {"status":"NO_DATA","reason":"INVALID_SOURCE_RESPONSE"}
    payload=raw.get("result") or {}
    if payload.get("symbol")!=symbol+"USDT" or payload.get("category")!="linear":
        return {"status":"NO_DATA","reason":"SYMBOL_OR_MARKET_MISMATCH"}
    rows={}
    for rec in payload.get("list",[]):
        try: t=int(rec["timestamp"])
        except (KeyError,ValueError,TypeError): continue
        qty=finite_positive(rec.get("openInterest"))
        if qty is None or t<0 or t>now_ms+2000:
            continue
        rows[t]=qty
    samples=sorted(rows.items())
    if not samples or now_ms-samples[-1][0]>MAX_AGE:
        return {"status":"NO_DATA","reason":"MISSING_OR_STALE_OI"}
    current_t,current=samples[-1]
    target=current_t-15*60000
    candidate=min(samples[:-1],key=lambda x:abs(x[0]-target),default=None)
    delta=None
    previous_time=None
    if candidate and abs(candidate[0]-target)<=P5//2 and candidate[1]>0:
        previous_time=candidate[0]
        delta=round(100*(current/candidate[1]-1),5)
    return {"status":"OBSERVED","source":"Bybit USDT linear","asOfMs":current_t,
            "ageMs":now_ms-current_t,"openInterest":current,
            "prior15mMs":previous_time,"deltaPct15m":delta,
            "unit":"BASE_ASSET_FOR_USDT_LINEAR; CONFIRM_INSTRUMENT_SPEC",
            "notTradeDirection":True,"notExchangeAggregated":True}

def one_symbol(symbol, now_ms, taker_fetch=fetch_taker, oi_fetch=fetch_oi):
    result={"symbol":symbol,
            "taker":{"status":"NO_DATA","reason":"NOT_FETCHED"},
            "openInterest":{"status":"NO_DATA","reason":"NOT_FETCHED"}}
    try:
        result["taker"]=taker_result(taker_fetch(symbol),now_ms)
    except Exception as ex:
        result["taker"]={"status":"NO_DATA","reason":"HTTP_OR_PARSE_ERROR","error":type(ex).__name__}
    try:
        result["openInterest"]=oi_result(oi_fetch(symbol),symbol,now_ms)
    except Exception as ex:
        result["openInterest"]={"status":"NO_DATA","reason":"HTTP_OR_PARSE_ERROR","error":type(ex).__name__}
    return result

def build(symbols,now_ms,taker_fetch=fetch_taker,oi_fetch=fetch_oi,max_workers=5):
    data={}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures={pool.submit(one_symbol,s,now_ms,taker_fetch,oi_fetch):s for s in symbols}
        for future in as_completed(futures):
            r=future.result()
            data[r["symbol"]]=r
    data={s:data[s] for s in symbols}
    observed=sum(1 for x in data.values()
                 for k in ("taker","openInterest") if x[k]["status"]=="OBSERVED")
    return {"schemaVersion":"detector-rest-flow-1.0",
            "generatedAt":datetime.fromtimestamp(now_ms/1000,timezone.utc).isoformat(),
            "source":"Binance futures REST + Bybit V5 public REST",
            "market":"PERPETUAL_RESEARCH","researchOnly":True,
            "notTradeApproval":True,"notSystemPrice":True,"notSpotFlow":True,
            "notCVD":True,"notLiquidationStream":True,
            "coverage":{"symbolsRequested":len(symbols),
                        "sourceObservationsValid":observed,
                        "expectedSourceObservations":2*len(symbols)},
            "timestampContract":"Each source's own timestamp; missing/stale never 0; generatedAt not price freshness",
            "evidenceFamily":"TAKER_FLOW_ONE_FAMILY; OI_SEPARATE_FAMILY",
            "instruments":data}

def symbols_from_universe(path):
    u=json.loads(Path(path).read_text())
    pool=list(dict.fromkeys(u["perpetual_core"]+u["groups"]["futures_extended"]))
    result=[s for s in pool if isinstance(s,str) and s.isalnum() and 2<=len(s)<=12]
    return result[:MAX_TICKERS]

def main():
    now_ms=int(time.time()*1000)
    symbols=symbols_from_universe(ROOT/"universe.json")
    payload=build(symbols,now_ms)
    # Never overwrite last successfully collected snapshot with an entirely unavailable run.
    if payload["coverage"]["sourceObservationsValid"]==0:
        raise RuntimeError("ALL_SOURCES_UNAVAILABLE: keep previous file and timestamp")
    OUT.write_text(json.dumps(payload,ensure_ascii=False,separators=(",",":"))+"\n")
    print("Detector serverless REST:",payload["coverage"],"as_of",payload["generatedAt"])

if __name__=="__main__":
    main()
