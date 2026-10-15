#!/usr/bin/env python3
"""Read-only health/quality gate for an OPTIONAL detector microflow file.

Never certifies prices, order execution or a profitable trading signal.
Default mode checks liveness; readiness checks observed non-gapped taker streams.
"""
import argparse
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = "detector-microflow-pilot-0.1"
WINDOWS = ("1m", "5m", "15m")

def parse_iso_ms(raw):
    if not isinstance(raw, str):
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return int(dt.timestamp() * 1000) if dt.tzinfo is not None else None
    except (ValueError, OverflowError, TypeError):
        return None

def validate(snapshot, *, now_ms, max_age_sec=75, mode="liveness",
             symbols=("SOLUSDT","SUIUSDT"), window="1m"):
    """Return a bounded JSON-compatible report, never success on missing observations."""
    errors = []
    warnings = []
    if not isinstance(snapshot, dict):
        return {"ok":False,"mode":mode,"errors":["INVALID_JSON_OBJECT"],"warnings":[]}
    if snapshot.get("schemaVersion") != SCHEMA:
        errors.append("SCHEMA_MISMATCH")
    for key in ("researchOnly","notTradeApproval","notSystemPrice","notForPricingOrNAV"):
        if snapshot.get(key) is not True:
            errors.append("MISSING_RESEARCH_ONLY_GUARD_"+key)
    generated_ms = parse_iso_ms(snapshot.get("generatedAt"))
    age_sec = None
    if generated_ms is None:
        errors.append("INVALID_GENERATED_AT")
    else:
        age_sec = round((now_ms - generated_ms)/1000, 1)
        if age_sec < -5 or age_sec > max_age_sec:
            errors.append("STALE_OR_FUTURE_SNAPSHOT")
    last_end = snapshot.get("lastCompleteMinuteEndMs")
    if isinstance(last_end, bool) or not isinstance(last_end, int):
        errors.append("INVALID_CLOSED_WINDOW")
    elif last_end > now_ms or now_ms - last_end > max_age_sec*1000+60000:
        errors.append("UNUSABLE_CLOSED_WINDOW")
    streams = snapshot.get("streams")
    if not isinstance(streams, dict):
        errors.append("STREAMS_MISSING")
        streams = {}
    availability = {}
    for market in ("spot","linear"):
        market_data = streams.get(market)
        if not isinstance(market_data, dict):
            errors.append("MARKET_MISSING_"+market)
            market_data = {}
        for symbol in symbols:
            obj = market_data.get(symbol)
            key = market+"."+symbol
            if not isinstance(obj, dict):
                errors.append("SYMBOL_MISSING_"+key)
                availability[key] = {"status":"NO_DATA"}
                continue
            trades = obj.get("taker_trade") or {}
            block = trades.get(window)
            if not isinstance(block, dict):
                errors.append("WINDOW_MISSING_"+key)
                availability[key] = {"status":"NO_DATA"}
                continue
            status = block.get("status")
            ratio = block.get("coverageRatio")
            data = block.get("data")
            availability[key] = {"status":status,"coverageRatio":ratio}
            if not isinstance(ratio, (int,float)) or isinstance(ratio,bool) or not math.isfinite(ratio) or not 0<=ratio<=1:
                errors.append("INVALID_COVERAGE_"+key)
                continue
            if status=="OBSERVED":
                if ratio<0.99 or not isinstance(data,dict) or not isinstance(data.get("count"),int) or data["count"]<=0:
                    errors.append("INVALID_OBSERVED_FLOW_"+key)
            elif status in ("NO_DATA_GAPPED_OR_WARMUP","NO_TRADE_EVENTS_UNVERIFIED"):
                if data is not None:
                    errors.append("MISSING_DATA_NOT_NULL_"+key)
                warnings.append(key+":"+status)
                if mode=="readiness":
                    errors.append("NO_TRADE_READINESS_"+key)
            else:
                errors.append("UNKNOWN_FLOW_STATUS_"+key)
    if mode not in ("liveness","readiness"):
        errors.append("INVALID_MODE")
    if window not in WINDOWS:
        errors.append("INVALID_WINDOW")
    return {"ok":not errors,"mode":mode,"window":window,"ageSeconds":age_sec,
            "symbols":list(symbols),"availability":availability,
            "errors":sorted(set(errors)),"warnings":sorted(set(warnings)),
            "note":"RESEARCH_ONLY; health != trading permission or data completeness guarantee"}

def main():
    p = argparse.ArgumentParser(description="Research-only Detector stream healthcheck")
    p.add_argument("--file",default="/data/detector-microflow.json")
    p.add_argument("--mode",choices=("liveness","readiness"),default="liveness")
    p.add_argument("--window",choices=WINDOWS,default="1m")
    p.add_argument("--symbols",default="SOLUSDT,SUIUSDT")
    p.add_argument("--max-age-sec",type=int,default=75)
    args=p.parse_args()
    if args.max_age_sec<20 or args.max_age_sec>600:
        p.error("max-age-sec must be 20..600")
    symbols=tuple(dict.fromkeys(x.strip().upper() for x in args.symbols.split(",") if x.strip()))
    if not symbols or len(symbols)>4:
        p.error("one to four symbols required")
    try:
        obj=json.loads(Path(args.file).read_text(encoding="utf-8"))
    except (OSError,ValueError) as e:
        print(json.dumps({"ok":False,"errors":["SNAPSHOT_UNAVAILABLE_OR_MALFORMED"],"detail":type(e).__name__}))
        return 2
    result=validate(obj,now_ms=int(time.time()*1000),max_age_sec=args.max_age_sec,
                    mode=args.mode,window=args.window,symbols=symbols)
    print(json.dumps(result,ensure_ascii=False,separators=(",",":")))
    return 0 if result["ok"] else 2

if __name__=="__main__":
    sys.exit(main())
