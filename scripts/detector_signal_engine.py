#!/usr/bin/env python3
"""Independent Detector SHADOW fusion: exact closed 15m price + 3x5m taker bars.

Never generates trade approvals, current prices, futures sizing, P&L, NAV,
validated probabilities, or independent-evidence counts from correlated series.
stdlib only; every timestamp and source is explicit.
"""
import hashlib
import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
P5=300000
P15=900000
# Source publication timestamps are checked separately from market event time.
MAX_SOURCE_AGE_MS=45*60000
MAX_CLOSED_AGE_MS=35*60000
MAX_FLOW_BAR_AGE_MS=35*60000

def as_ms(v):
    try:
        t=datetime.fromisoformat(v.replace("Z","+00:00"))
        return int(t.timestamp()*1000) if t.tzinfo else None
    except (TypeError,ValueError,OverflowError,AttributeError):
        return None

def finite(v, min_value=None):
    try:
        x=float(v)
        return x if math.isfinite(x) and (min_value is None or x>=min_value) else None
    except (ValueError,TypeError):
        return None

def freshness_time(ms, now_ms, limit):
    return isinstance(ms,int) and not isinstance(ms,bool) and -5000<=now_ms-ms<=limit

def gate_global(summary, flow, now_ms):
    for label,obj in (("PRICE",summary),("TAKER",flow)):
        if not isinstance(obj,dict):
            return False,label+"_MISSING"
        if obj.get("researchOnly") is not True or obj.get("notTradeApproval") is not True:
            return False,label+"_RESEARCH_GUARD_MISSING"
        ts=as_ms(obj.get("generatedAt"))
        if not freshness_time(ts,now_ms,MAX_SOURCE_AGE_MS):
            return False,label+"_PUBLISH_STALE_OR_FUTURE"
    if summary.get("schemaVersion")!="1.0":
        return False,"PRICE_SCHEMA_MISMATCH"
    if flow.get("schemaVersion")!="detector-rest-flow-1.0" or flow.get("notSystemPrice") is not True:
        return False,"TAKER_SCHEMA_MISMATCH_OR_PRICE_GUARD"
    return True,"OK"

def market_pair(symbol, price_source, taker):
    """Never join price and taker flow from unlike venues or product types."""
    label=taker.get("source")
    inst=taker.get("instId")
    if not isinstance(label,str):
        return False
    if price_source in ("OKX-primary","OKX"):
        return label=="OKX USDT-SWAP contract taker history" and inst==symbol+"-USDT-SWAP"
    if price_source=="Binance Futures":
        return label=="Binance USD-M perpetual"
    return False

def aligned_flow(symbol, price_bar, price_source, taker, now_ms):
    if not isinstance(taker,dict) or taker.get("status")!="OBSERVED":
        return None,"TAKER_SOURCE_UNAVAILABLE"
    if not market_pair(symbol,price_source,taker):
        return None,"VENUE_OR_MARKET_MISMATCH"
    last_end=taker.get("lastClosed5mEndMs")
    if not freshness_time(last_end,now_ms,MAX_FLOW_BAR_AGE_MS):
        return None,"TAKER_LAST_CLOSED_BAR_STALE"
    series=taker.get("recentClosed5m")
    if not isinstance(series,list):
        return None,"TAKER_TIMESTAMP_HISTORY_MISSING"
    t0=price_bar["t"]
    records={}
    for row in series:
        if not isinstance(row,dict):
            continue
        start,end=row.get("startMs"),row.get("endMs")
        if not isinstance(start,int) or not isinstance(end,int) or isinstance(start,bool) or isinstance(end,bool):
            continue
        if start%P5 or end!=start+P5 or end>last_end:
            return None,"INVALID_5M_TIMESTAMP"
        buy=finite(row.get("buyBase"),0)
        sell=finite(row.get("sellBase"),0)
        if buy is None or sell is None:
            return None,"INVALID_5M_QUANTITY"
        if start in records:
            return None,"DUPLICATE_5M_BAR"
        records[start]=(buy,sell)
    def aggregate(start):
        req=[start+P5*k for k in range(3)]
        if any(x not in records for x in req):
            return None
        b=sum(records[x][0] for x in req)
        s=sum(records[x][1] for x in req)
        if b+s==0:
            return {"buyBase":b,"sellBase":s,"imbalance":None}
        return {"buyBase":round(b,8),"sellBase":round(s,8),
                "imbalance":round((b-s)/(b+s),6)}
    current=aggregate(t0)
    if current is None:
        return None,"NO_EXACT_3X5M_PRICE_WINDOW"
    previous=aggregate(t0-P15)
    return {
        "matchedStartMs":t0,"matchedEndMs":t0+P15,
        "source":taker.get("source"),
        "current":current,"previous":previous,
        "sameWindow":True,"family":"TAKER_AGGREGATED_5M",
        "notSpotFlow":True,"notTickCVD":True,
        "totalVolumeBase":round(current["buyBase"]+current["sellBase"],8)
    },"OK"

def oi_context(derivatives,bar_end,now_ms):
    if not isinstance(derivatives,dict) or derivatives.get("venue")!="OKX":
        return {"status":"NO_DATA","confirm15m":False}
    oi=derivatives.get("openInterest")
    if not isinstance(oi,dict):
        return {"status":"NO_DATA","confirm15m":False}
    timestamp=oi.get("timestamp")
    if not freshness_time(timestamp,now_ms,MAX_SOURCE_AGE_MS):
        return {"status":"STALE","confirm15m":False}
    one_hour=finite(oi.get("deltaContractsPct1h"))
    delta15=finite(oi.get("deltaContractsPct15m"))
    # A later OI measurement was NOT available at the price-bar close;
    # 1h OI deltas never confirm the specific 15m candle.
    matched=(bar_end-5*60000)<=timestamp<=bar_end and delta15 is not None
    if timestamp>bar_end:
        category="POST_PRICE_BAR_CONTEXT_ONLY"
    elif not matched:
        category="ONE_HOUR_OR_UNALIGNED_CONTEXT_ONLY"
    else:
        category="ALIGNED_15M_OBSERVATION"
    return {
        "status":category,"venue":"OKX","asOfMs":timestamp,
        "hourlyDeltaContractsPct":one_hour,
        "fifteenMinuteDeltaContractsPct":delta15 if matched else None,
        "confirm15m":matched,
        "interpretation":"OI_IS_NOT_LONG_SHORT_DIRECTION; CORRELATED_WITH_PRICE_FLOW"
    }

def direction_models(bar, features, flow):
    """Qualitative hypothesis engine. Family-level grouping, NO probability score."""
    o,h,l,c=(finite(bar.get(k),0) for k in ("o","h","l","c"))
    if None in (o,h,l,c) or not (0<l<=min(o,c)<=max(o,c)<=h):
        return None,"INVALID_PRICE_BAR"
    width=h-l
    location=(c-l)/width if width else None
    data=flow["current"]
    imb=data["imbalance"]
    prev=flow["previous"]["imbalance"] if flow["previous"] else None
    local=features.get("localStructure") if isinstance(features,dict) else None
    if (not isinstance(local,dict) or
        features.get("status")!="OHLCV_PROXY_ONLY" or
        features.get("gapsInLast14")!=0):
        return None,"PRICE_STRUCTURE_UNVERIFIED"
    sweep_low=local.get("sweptLowReclaimed") is True
    sweep_high=local.get("sweptHighRejected") is True
    # These are early RESEARCH heuristics, not calibrated probabilities.
    price_long=sweep_low or (c>o and location is not None and location>=0.6)
    price_short=sweep_high or (c<o and location is not None and location<=0.4)
    flow_long=imb is not None and (
        (prev is not None and imb-prev>=0.15 and imb>=0.10) or
        (imb<=-0.10 and price_long))
    flow_short=imb is not None and (
        (prev is not None and imb-prev<=-0.15 and imb<=-0.10) or
        (imb>=0.10 and price_short))
    long_context=[]
    short_context=[]
    if sweep_low:long_context.append("PRICE_SWEEP_LOW_RECLAIM")
    if sweep_high:short_context.append("PRICE_SWEEP_HIGH_REJECT")
    if imb is not None:
        if imb<0 and price_long:
            long_context.append("SELL_PRESSURE_WITH_PRICE_RESILIENCE_UNVERIFIED_ABSORPTION")
        if imb>0 and price_short:
            short_context.append("BUY_PRESSURE_WITH_PRICE_WEAKNESS_UNVERIFIED_ABSORPTION")
    if prev is not None:
        if imb is not None and imb-prev>=0.15:long_context.append("TAKER_IMBALANCE_IMPROVING")
        if imb is not None and imb-prev<=-0.15:short_context.append("TAKER_IMBALANCE_WORSENING")
    def model(side, p_ok, f_ok, reasons):
        status="EARLY_CANDIDATE_SHADOW" if p_ok and f_ok else "WATCH" if p_ok or f_ok else "NO_EDGE"
        return {"direction":side,"status":status,
                "families":{
                    "PRICE_STRUCTURE":{"supportsHypothesis":bool(p_ok),"source":"CLOSED_15M_OHLCV_AND_RELATIVE_PRICE"},
                    "TAKER_VOLUME":{"supportsHypothesis":bool(f_ok),"source":"SAME_VENUE_3X5M_AGGREGATE"}},
                "context":reasons,"heuristicNotValidated":True,
                "notIndependentStatisticalProof":True}
    longs=model("LONG",price_long,flow_long,long_context)
    shorts=model("SHORT",price_short,flow_short,short_context)
    if longs["status"]=="EARLY_CANDIDATE_SHADOW" and shorts["status"]=="EARLY_CANDIDATE_SHADOW":
        longs["status"]=shorts["status"]="CONFLICT"
    return {"LONG":longs,"SHORT":shorts,
            "priceBar":{"open":o,"high":h,"low":l,"close":c,
                        "openMs":bar["t"],"closeMs":bar["endMs"],
                        "closeLocation":round(location,6) if location is not None else None},
            "flow":flow,
            "note":"Price bars are historical observations, NOT current system quotes."
            },"OK"

def symbol_result(sym,summary,flow,now_ms):
    price=(summary.get("instruments") or {}).get(sym)
    tf=price.get("15m") if isinstance(price,dict) else None
    taker_obj=(flow.get("instruments") or {}).get(sym)
    out={"symbol":sym,"status":"NO_DATA","reason":None,"LONG":None,"SHORT":None,
         "oi":{"status":"NO_DATA","confirm15m":False}}
    if not isinstance(tf,dict):
        out["reason"]="PRICE_15M_NOT_MONITORED"
        return out
    bar=tf.get("lastClosedBar")
    features=tf.get("detectorFeatures")
    if not isinstance(bar,dict):
        out["reason"]="NO_CLOSED_15M_BAR"
        return out
    start,end=bar.get("t"),bar.get("endMs")
    if (not isinstance(start,int) or isinstance(start,bool) or start%P15 or
        not isinstance(end,int) or isinstance(end,bool) or end!=start+P15 or
        tf.get("lastClosedOpen")!=start or
        not freshness_time(end,now_ms,MAX_CLOSED_AGE_MS)):
        out["reason"]="PRICE_15M_STALE_OR_TIME_MISMATCH"
        return out
    if not isinstance(features,dict) or features.get("sourceBarClosedAt")!=end:
        out["reason"]="STRUCTURE_BAR_MISMATCH"
        return out
    if not isinstance(taker_obj,dict):
        out["reason"]="TAKER_SYMBOL_NOT_MONITORED"
        return out
    matched,reason=aligned_flow(sym,bar,tf.get("source"),taker_obj.get("taker"),now_ms)
    if matched is None:
        out["reason"]=reason
        return out
    states,reason=direction_models(bar,features,matched)
    if states is None:
        out["reason"]=reason
        return out
    out.update(states)
    out["status"]="SHADOW_RESEARCH"
    out["reason"]=None
    out["oi"]=oi_context(price.get("derivatives"),end,now_ms)
    out["priceSource"]=tf.get("source")
    out["eventEndMs"]=end
    out["rsVsBTC"]=tf.get("rsVsBTC") # contextual price family only
    out["sourceFamilyLimits"]="PRICE_RS_BODY_SWEEP=ONE_FAMILY; BUY_SELL_IMBALANCE=ONE_FAMILY; OI_CONTEXT_NOT_DIRECTION"
    return out

def build(summary,flow,*,now_ms,input_hashes=None):
    eligible,reason=gate_global(summary,flow,now_ms)
    left=summary.get("instruments",{}) if isinstance(summary,dict) else {}
    right=flow.get("instruments",{}) if isinstance(flow,dict) else {}
    symbols=sorted(set(left)|set(right))
    results={}
    if eligible:
        for sym in symbols:
            results[sym]=symbol_result(sym,summary,flow,now_ms)
    else:
        for sym in symbols:
            results[sym]={"symbol":sym,"status":"NO_DATA","reason":reason,
                          "LONG":None,"SHORT":None,"oi":{"status":"NO_DATA","confirm15m":False}}
    candidates=[]
    for sym,r in results.items():
        for direction in ("LONG","SHORT"):
            block=r.get(direction)
            if block and block["status"]=="EARLY_CANDIDATE_SHADOW":
                candidates.append({"symbol":sym,"direction":direction,
                                   "status":"EARLY_CANDIDATE_SHADOW",
                                   "eventEndMs":r["eventEndMs"],
                                   "families":["PRICE_STRUCTURE","TAKER_VOLUME"],
                                   "oiRole":r["oi"]["status"]})
    candidates.sort(key=lambda c:(c["symbol"],c["direction"]))
    coverage={"symbols":len(symbols),
              "fullyAligned":sum(x["status"]=="SHADOW_RESEARCH" for x in results.values()),
              "shadowCandidates":len(candidates),
              "unavailable":sum(x["status"]=="NO_DATA" for x in results.values()),
              "withAlignedOI15m":sum(x["oi"].get("confirm15m") is True for x in results.values())}
    return {
        "schemaVersion":"detector-shadow-fusion-1.0",
        "generatedAt":datetime.fromtimestamp(now_ms/1000,timezone.utc).isoformat(),
        "producerStatus":"RESEARCH_ONLY",
        "operationalStatus":"SHADOW_ONLY_NO_TRADE_AUTHORITY",
        "researchOnly":True,"notTradeApproval":True,"notSystemPrice":True,
        "noValidatedProbability":True,"noExecutionLevels":True,
        "dataGate":{"ok":eligible,"reason":reason},
        "sourceProvenance":{
            "marketSummaryGeneratedAt":summary.get("generatedAt") if isinstance(summary,dict) else None,
            "takerRestGeneratedAt":flow.get("generatedAt") if isinstance(flow,dict) else None,
            "inputSha256":input_hashes or {}},
        "features":{"price":"OHLCV + RS ONE FAMILY",
                    "flow":"AGGREGATED_TAKER_VOLUME ONE FAMILY",
                    "oi":"SEPARATE OBSERVATION, DIRECTION UNKNOWN, MAY BE CONTEXT ONLY"},
        "coverage":coverage,"candidates":candidates,"instruments":results,
        "limitations":[
            "Research heuristics not walk-forward validated; no measured hit-rate",
            "Price and taker flow are causally/statistically related, NOT independent proofs",
            "OI hour context is not synchronous 15m confirmation; later OI never backdated",
            "Only same-venue perpetual data; no Spot order flow, book, complete liquidations",
            "No live system prices, entry levels, authorization, leverage or orders",
            "No retroactive interpolation of missing data or unknown venues"
        ]
    }

def main():
    paths={"market-summary.json":ROOT/"market-summary.json",
           "detector-rest-flow.json":ROOT/"detector-rest-flow.json"}
    source={}
    digests={}
    for name,path in paths.items():
        try:
            content=path.read_bytes()
            source[name]=json.loads(content)
            digests[name]=hashlib.sha256(content).hexdigest()
        except (OSError,ValueError) as ex:
            source[name]={"sourceMissing":type(ex).__name__}
    out=build(source["market-summary.json"],source["detector-rest-flow.json"],
              now_ms=int(time.time()*1000),input_hashes=digests)
    target=ROOT/"detector-candidates.json"
    target.write_text(json.dumps(out,ensure_ascii=False,separators=(",",":"))+"\n")
    print("Detector SHADOW:",json.dumps(out["coverage"],sort_keys=True),
          "gate="+out["dataGate"]["reason"])
    # Return success for an honest NO_DATA research report. Never claim it as valid candidates.

if __name__=="__main__":
    main()
