#!/usr/bin/env python3
"""Research-only forward outcome snapshots for detected SHADOW events."""
import datetime as dt
import hashlib
import json
import os
import sys
from pathlib import Path

import boto3
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from detector_event_followthrough import candles, ms

UTC = dt.timezone.utc
HORIZONS = {"15m": 900000, "1h": 3600000, "4h": 14400000}
NOW = int(dt.datetime.now(UTC).timestamp() * 1000)
PREFIX = "shadow/v1/outcomes"

def evaluate(event, bars):
    detection = ms(event["firstDetectedAtUtc"])
    result = {"event_id": event["id"], "symbol": event["symbol"],
              "direction": event["direction"], "firstDetectedAtUtc": event["firstDetectedAtUtc"],
              "barClosedAtUtc": event.get("barClosedAtUtc"),
              "reference_policy": "LAST_15M_CLOSE_KNOWN_AT_DETECTION",
              "horizons": {}}
    prior = [b for b in bars if b["t"] + 900000 <= detection]
    if not prior:
        result["status"] = "NO_PRE_DETECTION_REFERENCE"
        return result
    base = prior[-1]["c"]
    result["reference_price"] = base
    result["reference_bar_end_ms"] = prior[-1]["t"] + 900000
    sign = 1 if event["direction"] == "LONG" else -1
    for name, delta in HORIZONS.items():
        target = detection + delta
        eligible = [b for b in bars if b["t"] + 900000 >= target and b["t"] + 900000 <= NOW]
        if not eligible:
            result["horizons"][name] = {"status": "PENDING_OR_MISSING"}
            continue
        bar = eligible[0]
        # No extrapolation: use the first fully completed candle at or after target.
        result["horizons"][name] = {
            "status": "OK", "target_ms": target, "observed_bar_end_ms": bar["t"] + 900000,
            "observed_close": bar["c"],
            "signed_change_pct": round(100 * sign * (bar["c"] / base - 1), 6)}
    result["status"] = "COMPLETE" if all(x["status"] == "OK" for x in result["horizons"].values()) else "PARTIAL"
    return result

def main():
    events = json.loads(Path("detector-signal-events.json").read_text())["events"]
    start = NOW - 48 * 3600000
    selected = [e for e in events if e.get("status") == "EARLY_CANDIDATE_SHADOW"
                and e.get("direction") in ("LONG", "SHORT")
                and e.get("firstDetectedAtUtc")
                and start <= ms(e["firstDetectedAtUtc"]) <= NOW]
    session = requests.Session()
    session.headers.update({"User-Agent": "shadow-forward-outcomes-research/1.0"})
    rows, errors = [], {}
    for symbol in sorted({e["symbol"] for e in selected}):
        subset = [e for e in selected if e["symbol"] == symbol]
        try:
            first = min(ms(e["firstDetectedAtUtc"]) for e in subset)
            bars = candles(session, symbol, first - 3600000, NOW)
            rows.extend(evaluate(e, bars) for e in subset)
        except Exception as exc:
            errors[symbol] = str(exc)
            rows.extend({"event_id": e["id"], "symbol": symbol, "status": "FETCH_FAILED",
                         "error": str(exc)} for e in subset)
    payload = {"schema": "SHADOW_FORWARD_OUTCOMES_V1", "researchOnly": True,
               "generated_at_utc": dt.datetime.now(UTC).isoformat(),
               "source": "OKX USDT perpetual 15m closed candles",
               "selection": "last 48 hours by firstDetectedAtUtc",
               "horizon_method": "first fully completed 15m close at or after detection plus horizon",
               "limitations": ["not executable entry price", "no fills/fees/spread/slippage",
                               "missing and pending observations not counted as successes",
                               "15m close sampling, not intrabar path"],
               "selected_events": len(selected), "errors": errors, "results": rows}
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    digest = hashlib.sha256(raw).hexdigest()
    day = dt.datetime.now(UTC).strftime("%Y-%m-%d")
    key = f"{PREFIX}/{day}/{digest}.json"
    s3 = boto3.client("s3",
        endpoint_url=f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"], region_name="auto")
    bucket = os.environ["R2_BUCKET"]
    s3.put_object(Bucket=bucket, Key=key, Body=raw, ContentType="application/json",
                  Metadata={"sha256": digest})
    readback = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
    if hashlib.sha256(readback).hexdigest() != digest:
        raise RuntimeError("R2_OUTCOMES_READBACK_MISMATCH")
    print("R2_SHADOW_OUTCOMES_READBACK_OK", key, "events", len(selected),
          "complete", sum(r.get("status") == "COMPLETE" for r in rows),
          "partial", sum(r.get("status") == "PARTIAL" for r in rows),
          "errors", len(errors))
    if errors:
        raise RuntimeError("MARKET_DATA_INCOMPLETE: " + ",".join(errors))

if __name__ == "__main__":
    main()
