#!/usr/bin/env python3
"""Causal (non-repainting) Gaussian Nadaraya-Watson ENVELOPE research candidate.

Pure OHLCV closed-candle consumer. The 50-bar kernel and 40-bar
historical deviation window are explicitly NOT TradingView LuxAlgo's
500-bar / 499-bar non-repainting defaults; no parity/alert claims.
No future lookahead, live bar, orders, or trade authority. Stdlib only.
"""
import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "market-structure.json"
OUTPUT = ROOT / "nadaraya-watson-research.json"
SYMBOLS = ("BTC", "ETH", "SOL", "SUI", "LINK", "XRP", "BNB", "ENA")
TF_MS = {"15m": 900000, "1H": 3600000, "4H": 14400000, "1D": 86400000}
BANDWIDTH = 8.0
KERNEL_BARS = 50
DEVIATION_BARS = 40
MULTIPLIER = 3.0
MIN_BARS = KERNEL_BARS + DEVIATION_BARS
SOURCE = "close"
MODEL_ID = "NWE_CAUSAL_GAUSSIAN_8_50_40_3_RESEARCH_PROXY_V1"
UNVERIFIED = "TRADINGVIEW_PARITY_UNVERIFIED"
NO_DATA = "NO_DATA"


def finite_num(value):
    try:
        x = float(value)
        return x if math.isfinite(x) else None
    except (ValueError, TypeError, OverflowError):
        return None


def prepare_closed(rows, timeframe, now_ms):
    """Do not join holes or treat an unfinished source candle as final."""
    if not isinstance(rows, list):
        return []
    stride = TF_MS[timeframe]
    by_time = {}
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        try:
            t = int(raw["t"])
        except (KeyError, ValueError, TypeError):
            continue
        o, h, l, c = [finite_num(raw.get(k)) for k in ("o", "h", "l", "c")]
        if (t < 0 or t + stride > now_ms or None in (o, h, l, c)
                or min(o, h, l, c) <= 0 or not (l <= min(o, c) <= max(o, c) <= h)):
            continue
        by_time[t] = {"t": t, "o": o, "h": h, "l": l, "c": c}
    return [by_time[t] for t in sorted(by_time)]


def calculate(rows, timeframe, now_ms):
    """One-sided gaussian kernel; causal MAE envelope, closed bars only."""
    bars = prepare_closed(rows, timeframe, now_ms)
    if len(bars) < MIN_BARS:
        return {"status": NO_DATA, "reason": "INSUFFICIENT_CLOSED_HISTORY",
                "availableBars": len(bars), "requiredBars": MIN_BARS}
    p = TF_MS[timeframe]
    last = bars[-MIN_BARS:]
    if any(last[i]["t"] - last[i-1]["t"] != p for i in range(1, len(last))):
        return {"status": NO_DATA, "reason": "GAPPED_CANDLE_HISTORY"}
    age = now_ms - (last[-1]["t"] + p)
    if age < 0 or age > p + 20 * 60_000:
        return {"status": NO_DATA, "reason": "STALE_LAST_CLOSED_BAR",
                "barClosedAtMs": last[-1]["t"] + p, "ageMs": age}
    # Only the last 90 bars are needed to compute the last TWO bands.
    closes = [x["c"] for x in last]
    weights = [math.exp(-0.5 * (i / BANDWIDTH) ** 2) for i in range(KERNEL_BARS)]
    weight_sum = sum(weights)
    estimates = {}
    deviations = {}
    for i in range(KERNEL_BARS - 1, len(closes)):
        avg = sum(closes[i - lag] * w for lag, w in enumerate(weights)) / weight_sum
        estimates[i] = avg
        deviations[i] = abs(closes[i] - avg)
    out = {}
    for i in (len(closes)-2, len(closes)-1):
        past = list(range(i - DEVIATION_BARS + 1, i + 1))
        if any(k not in deviations for k in past):
            return {"status": NO_DATA, "reason": "INSUFFICIENT_DEVIATION_WINDOW"}
        band = MULTIPLIER * sum(deviations[k] for k in past) / DEVIATION_BARS
        out[i] = {"center": estimates[i], "upper": estimates[i] + band,
                  "lower": estimates[i] - band, "close": closes[i]}
    prior, cur = out[len(closes)-2], out[len(closes)-1]
    upper_cross = prior["close"] <= prior["upper"] and cur["close"] > cur["upper"]
    lower_cross = prior["close"] >= prior["lower"] and cur["close"] < cur["lower"]
    return_lower = prior["close"] < prior["lower"] and cur["close"] >= cur["lower"]
    return_upper = prior["close"] > prior["upper"] and cur["close"] <= cur["upper"]
    slope = 100 * (cur["center"] / prior["center"] - 1)
    if cur["close"] > cur["upper"]:
        position = "ABOVE_UPPER"
    elif cur["close"] < cur["lower"]:
        position = "BELOW_LOWER"
    elif cur["close"] >= cur["center"]:
        position = "IN_CHANNEL_ABOVE_CENTER"
    else:
        position = "IN_CHANNEL_BELOW_CENTER"
    return {
        "status": "MODEL_OBSERVED_UNVERIFIED_PARITY",
        "source": "OKX_CLOSED_PERPETUAL_OHLCV",
        "closedCandleOnly": True, "repainting": False,
        "symbolTimeframe": timeframe, "barOpenMs": last[-1]["t"],
        "barClosedAtMs": last[-1]["t"] + p, "ageMs": age,
        "sourceClose": round(cur["close"], 8),
        "center": round(cur["center"], 8),
        "upper": round(cur["upper"], 8), "lower": round(cur["lower"], 8),
        "centerSlopePctPerBar": round(slope, 6),
        "centerDirection": "UP" if slope > 1e-10 else "DOWN" if slope < -1e-10 else "FLAT",
        "priceLocation": position,
        "crossAboveUpper": upper_cross, "crossBelowLower": lower_cross,
        "returnInsideFromBelow": return_lower, "returnInsideFromAbove": return_upper,
        "modelID": MODEL_ID,
        "inputCount": MIN_BARS,
        "parityStatus": UNVERIFIED,
        "notSignal": True, "notTradeApproval": True,
    }


def build(source, now_ms):
    universe = source.get("instruments", {})
    out = {}
    for symbol in SYMBOLS:
        perp = (universe.get(symbol) or {}).get("perpetual") or {}
        out[symbol] = {}
        for tf in ("15m", "1H", "4H", "1D"):
            block = perp.get(tf) or {}
            if not block.get("ok"):
                val = {"status": NO_DATA, "reason": "SOURCE_CANDLES_NOT_AVAILABLE"}
            else:
                val = calculate(block.get("candles"), tf, now_ms)
            out[symbol][tf] = val
    return {
        "schemaVersion": "nadaraya-watson-research-1.0.0",
        "generatedAt": datetime.fromtimestamp(now_ms / 1000, timezone.utc).isoformat(),
        "inputGeneratedAt": source.get("generatedAt"),
        "researchOnly": True, "notTradeApproval": True,
        "notBacktestParityClaim": True,
        "model": {
            "id": MODEL_ID, "type": "causal endpoint Gaussian Nadaraya-Watson envelope",
            "bandwidth": BANDWIDTH, "kernelBars": KERNEL_BARS,
            "deviationBars": DEVIATION_BARS, "multiplier": MULTIPLIER,
            "source": SOURCE, "repainting": False,
            "compareAgainst": "TradingView LuxAlgo Iko0E2kL with Repainting Smoothing OFF",
            "parityStatus": UNVERIFIED,
            "notIdenticalToOriginalWindow": True,
            "barConvention": "OKX 1D may use exchange-local UTC+8 day, not 1Dutc",
        },
        "instruments": out,
    }


def main():
    try:
        data = json.loads(INPUT.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        data = {}
    result = build(data, int(time.time() * 1000))
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    count = sum(v.get("status") == "MODEL_OBSERVED_UNVERIFIED_PARITY"
                for asset in result["instruments"].values() for v in asset.values())
    print(f"Nadaraya-Watson research-only proxy: {count} closed-bar models; no TradingView parity claimed.")


if __name__ == "__main__":
    main()
