#!/usr/bin/env python3
"""HYPE derivatives research: exact-source observations, no trading authority."""
import json
import math
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

OUT = Path("research/hype-derivatives/latest.json")
def now():
    return datetime.now(timezone.utc).isoformat()
def request(url, body=None):
    headers={"User-Agent":"crypto-price-feed/hype-shadow-1","Accept":"application/json"}
    if body is not None:
        headers["Content-Type"]="application/json"
        body=json.dumps(body).encode()
    with urllib.request.urlopen(urllib.request.Request(url,data=body,headers=headers),timeout=12) as r:
        return json.load(r)
def positive(v):
    x=float(v)
    if not math.isfinite(x) or x<0: raise ValueError("nonfinite/negative")
    return x
def record(source, market, fn):
    try:
        result=fn()
        if not result: raise ValueError("empty observation")
        return {"status":"OK","venue":source,"instrument":market,"observedAt":now(),"metrics":result}
    except Exception as exc:
        return {"status":"UNAVAILABLE","venue":source,"instrument":market,"observedAt":now(),"reason":str(exc)[:180],"metrics":{}}
def hyperliquid():
    data=request("https://api.hyperliquid.xyz/info",{"type":"metaAndAssetCtxs"})
    universe=data[0]["universe"]
    matches=[i for i,a in enumerate(universe) if a.get("name")=="HYPE"]
    if len(matches)!=1: raise ValueError("HYPE exact instrument not found")
    ctx=data[1][matches[0]]
    return {"openInterest":{"value":positive(ctx["openInterest"]),"unit":"HYPE"},
            "funding":{"value":float(ctx["funding"]),"unit":"fraction","period":"source-defined"},
            "volume24h":{"value":positive(ctx["dayNtlVlm"]),"unit":"USD_notional"},
            "liquidations":{"status":"UNAVAILABLE","reason":"No verified complete liquidation feed"}}
def okx():
    base="https://www.okx.com"
    inst="HYPE-USDT-SWAP"
    oi=request(base+"/api/v5/public/open-interest?instType=SWAP&instId="+inst)
    fr=request(base+"/api/v5/public/funding-rate?instId="+inst)
    tk=request(base+"/api/v5/market/ticker?instId="+inst)
    def exact(obj):
        if obj.get("code")!="0": raise ValueError("OKX API failure")
        xs=[x for x in obj.get("data",[]) if x.get("instId")==inst]
        if len(xs)!=1: raise ValueError("OKX exact instrument unavailable")
        return xs[0]
    o,f,t=exact(oi),exact(fr),exact(tk)
    return {"openInterest":{"value":positive(o["oiCcy"]),"unit":"HYPE","sourceTimestampMs":o.get("ts")},
            "funding":{"value":float(f["fundingRate"]),"unit":"fraction","nextFundingTimeMs":f.get("nextFundingTime")},
            "volume24h":{"value":positive(t["volCcy24h"]),"unit":"HYPE","sourceTimestampMs":t.get("ts")},
            "liquidations":{"status":"UNAVAILABLE","reason":"No verified complete liquidation feed"}}
def main():
    results=[record("Hyperliquid","HYPE perpetual",hyperliquid),record("OKX","HYPE-USDT-SWAP",okx)]
    out={"schemaVersion":"0.1.0","generatedAt":now(),"authority":"SHADOW_RESEARCH_ONLY_NO_TRADES",
         "notFor":["NAV","PnL","systemPrice","orders","signals","trading_limits"],
         "observations":results,
         "aggregation":"NONE_VENUE_SPECIFIC_UNITS_NOT_NORMALIZED",
         "liquidations":{"status":"UNAVAILABLE","reason":"No verified comprehensive event feed"}}
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n")
    print("HYPE shadow observations:",[(x["venue"],x["status"]) for x in results])
if __name__=="__main__": main()
