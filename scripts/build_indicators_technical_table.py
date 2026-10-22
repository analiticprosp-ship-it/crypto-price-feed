#!/usr/bin/env python3
"""Research-only 4H technical table for the project's ИНДИКАТОРЫ command.

Source-of-truth = existing GitHub price, OKX OI, perpetual taker,
causal N-W proxy. Evidence families are NOT new macro/crypto votes.
Retain last observations with explicit freshness, NEVER promote stale
observations or proprietary Pifagor substitute to trade-ready signals.
"""
import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SYMBOLS = ("BTC", "ETH", "SOL", "XRP", "SUI", "LINK", "BNB", "ENA")
P5 = 300000
HOUR = 3600000
FRESH_MAX = {"prices": 15*60000, "oi": 20*60000, "taker": 20*60000}
BAR_MS = {"15m": 900000, "1H": HOUR, "4H": 4*HOUR, "1D": 24*HOUR}
PIFAGOR = {"status": "NOT_CONNECTED", "reason": "ORIGINAL_AUTHORIZED_CLOSED_BAR_ALERT_UNAVAILABLE"}
LIQUIDATIONS = {"status": "NOT_CONNECTED", "reason": "CONTINUOUS_VERIFIED_BYBIT_STREAM_NOT_DEPLOYED"}


def iso(ms):
    if ms is None:
        return None
    try:
        return datetime.fromtimestamp(ms/1000, timezone.utc).isoformat()
    except (OverflowError, TypeError, ValueError):
        return None


def epoch(text):
    if not isinstance(text, str):
        return None
    try:
        return int(datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()*1000)
    except (ValueError, OverflowError):
        return None


def numeric(x):
    try:
        z=float(x)
        return z if math.isfinite(z) else None
    except (TypeError, ValueError, OverflowError):
        return None


def quality(ts, now_ms, max_age):
    if ts is None or ts <= 0 or ts > now_ms + 1000:
        return "NO_TIMESTAMP"
    return "FRESH" if now_ms-ts <= max_age else "STALE"


def observed_oi(source, now_ms):
    data = ((source or {}).get("derivatives") or {}).get("openInterest") or {}
    ts = data.get("timestamp")
    ts = int(ts) if isinstance(ts, (str, int)) and str(ts).isdigit() else None
    x=numeric(data.get("deltaContractsPct1h"))
    if x is None or ts is None:
        return {"status": "NO_DATA", "reason": "NO_VERIFIED_OKX_CONTRACTS_1H"}
    return {"status": quality(ts, now_ms, FRESH_MAX["oi"]),
            "observedAtUTC": iso(ts), "deltaContractsPct1h": x,
            "venue": "OKX", "unit": "OI_CONTRACTS", "notLongShortBias": True}


def observed_taker(source, now_ms):
    s = (source or {}).get("taker") or {}
    if s.get("status") != "OBSERVED":
        return {"status": "NO_DATA", "reason": "TAKER_NOT_OBSERVED"}
    raw = s.get("recentClosed5m") or []
    bars={}
    for row in raw:
        try:
            t=int(row["startMs"]); end=int(row["endMs"])
        except (KeyError, TypeError, ValueError):
            continue
        b=numeric(row.get("buyBase")); v=numeric(row.get("sellBase"))
        if (t >= 0 and t%P5==0 and end-t==P5
                and b is not None and b>=0 and v is not None and v>=0 and end<=now_ms):
            bars[t] = (end,b,v)
    if not bars:
        return {"status": "NO_DATA", "reason": "NO_VALID_5M_BARS"}
    end=max(bars)+P5
    seq=list(range(end-HOUR,end,P5))
    if len(seq)!=12 or any(t not in bars or bars[t][0]!=t+P5 for t in seq):
        return {"status": "NO_DATA", "reason": "GAPPED_1H_5M_BARS"}
    b=sum(bars[t][1] for t in seq); v=sum(bars[t][2] for t in seq)
    if b+v<=0:
        return {"status": "NO_DATA", "reason": "ZERO_VOLUME_NOT_PROVEN_DIRECTION"}
    venue="OKX" if "OKX" in str(s.get("source","")) else "Binance" if "Binance" in str(s.get("source","")) else None
    if venue is None:
        return {"status": "NO_DATA", "reason": "VENUE_NOT_VERIFIED"}
    return {"status": quality(end,now_ms,FRESH_MAX["taker"]),
            "market": "PERPETUAL", "venue": venue,
            "windowStartUTC": iso(end-HOUR), "windowEndUTC": iso(end),
            "closedBars":12,
            "imbalancePct":round(100*(b-v)/(b+v),4),
            "meaning": "AGGREGATE_TAKER_NOT_SPOT_CVD_NOT_LIQUIDATIONS"}


def observed_nw(asset, now_ms):
    tfs={}
    for tf in ("15m","1H","4H","1D"):
        d=(asset or {}).get(tf) or {}
        if d.get("status")!="MODEL_OBSERVED_UNVERIFIED_PARITY":
            tfs[tf]={"status":"NO_DATA","reason":d.get("reason") or "NO_CAUSAL_MODEL"}
            continue
        t=d.get("barClosedAtMs")
        fresh=quality(t,now_ms,BAR_MS[tf]+20*60000)
        tfs[tf]={"status":fresh if fresh!="FRESH" else "MODEL_OBSERVED_UNVERIFIED_PARITY",
                 "barClosedUTC":iso(t),"center":numeric(d.get("center")),
                 "upper":numeric(d.get("upper")),"lower":numeric(d.get("lower")),
                 "direction":d.get("centerDirection"),
                 "position":d.get("priceLocation"),
                 "parity":"TRADINGVIEW_PARITY_UNVERIFIED","notOriginalLuxAlgo":True}
    return tfs


def build(prices, summary, flow, nw, now_ms):
    quotes={q.get("symbol"):q for q in (prices.get("spot") or {}).get("quotes",[])
            if isinstance(q,dict)}
    out={}
    for sym in SYMBOLS:
        q=quotes.get(sym) or {}
        price_time=epoch(prices.get("generatedAt"))
        q_ok=q.get("ok") is True and (q.get("freshSourceCount") or 0)>=2
        price={"status":quality(price_time,now_ms,FRESH_MAX["prices"]) if q_ok else "NO_DATA",
               "observedAtUTC":prices.get("generatedAt"),
               "priceUSDT":numeric(q.get("systemPrice")) if q_ok else None,
               "sources":q.get("freshSourceCount") if q_ok else 0}
        out[sym]={
            "price":price,
            "oi1h":observed_oi((summary.get("instruments") or {}).get(sym),now_ms),
            "perpTaker1h":observed_taker((flow.get("instruments") or {}).get(sym),now_ms),
            "nadarayaWatson":observed_nw((nw.get("instruments") or {}).get(sym),now_ms),
            "liquidations":LIQUIDATIONS.copy(),
            "pifagorMFI":PIFAGOR.copy(),
            "bigGuyBurjKhalifa":PIFAGOR.copy(),
            "convergence":"UNVERIFIED_NO_ORIGINAL_PIFAGOR_AND_NO_SYNCHRONOUS_FULL_EVIDENCE",
            "tradeAuthority":False}
    return {"schemaVersion":"indicators-technical-table-v1.0",
            "command":"Индикаторы", "block":"TECHNICAL_CONVERGENCE_NOT_EIGHTH_FAMILY",
            "generatedAtUTC":iso(now_ms), "researchOnly":True,
            "noTradeApproval":True, "notCanonicalIndicatorHistory":True,
            "sources":{"prices":prices.get("generatedAt"),
                       "marketSummary":summary.get("generatedAt"),
                       "restFlow":flow.get("generatedAt"),
                       "nadarayaWatson":nw.get("generatedAt")},
            "limitations":["LAST_OBSERVED_STALE_IS_NOT_LIVE",
                           "NW_USES_CAUSAL_50_40_PROXY_NOT_TV_PARITY",
                           "MFI_BIG_GUY_NOT_AUTHENTICATED",
                           "LIQUIDATION_EVENTS_REQUIRE_ALWAYS_ON_WS",
                           "NO_5BD_OR_MACRO_CHECKPOINT_CREATED"],
            "table":out}


def main():
    def get(path):
        try:
            return json.loads((ROOT/path).read_text(encoding="utf-8"))
        except (OSError,ValueError):
            return {}
    result=build(get("prices.json"),get("market-summary.json"),
                 get("detector-rest-flow.json"),get("nadaraya-watson-research.json"),
                 int(time.time()*1000))
    (ROOT/"indicators-technical-table.json").write_text(
        json.dumps(result,ensure_ascii=False,separators=(",",":"))+"\n",encoding="utf-8")
    fresh=sum(x["status"]=="FRESH" for a in result["table"].values()
              for k,x in a.items() if k in ("price","oi1h","perpTaker1h"))
    print("Indicators technical table: observed fresh fields",fresh,
          "historical fields retained; no signal/writeback.")


if __name__ == "__main__":
    main()
