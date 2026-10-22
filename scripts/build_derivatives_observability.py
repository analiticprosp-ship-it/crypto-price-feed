#!/usr/bin/env python3
"""Research-only bridge for genuine OI and taker flow observations.

Reads existing, on-disk GitHub data feeds. No trading API, no price generation,
no liquidation inference, no vendor indicator approximation. Standard library.
"""
import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
P5 = 300_000
HOUR = 3_600_000
MAX_AGE_MS = 20 * 60_000
OI_TOLERANCE_MS = 8 * 60_000
SYMBOLS = ("BTC", "ETH", "SOL", "XRP", "BNB", "LINK", "ENA", "SUI")
NO_DATA = "NO_DATA"
OBSERVED = "OBSERVED"


def finite(value):
    try:
        v = float(value)
        return v if math.isfinite(v) else None
    except (TypeError, ValueError, OverflowError):
        return None


def normalized_hour_taker(block, now_ms):
    """Require twelve contiguous, fully closed, correctly labeled 5m bars."""
    if not isinstance(block, dict) or block.get("status") != OBSERVED:
        return {"status": NO_DATA, "reason": "SOURCE_UNAVAILABLE"}
    if "taker" not in str(block.get("source", "")).lower():
        # OKX source is 'OKX USDT-SWAP contract taker history'; Binance source
        # is 'Binance USD-M perpetual' and has explicit taker dataMeaning.
        if block.get("dataMeaning") != "AGGREGATED_TAKER_BUY_SELL_BASE_VOLUME_NOT_TICK_CVD":
            return {"status": NO_DATA, "reason": "SOURCE_SEMANTICS_UNVERIFIED"}
    if block.get("notSpotFlow") is False:
        return {"status": NO_DATA, "reason": "SPOT_AND_PERP_MUST_NOT_BE_MIXED"}
    raw = block.get("recentClosed5m")
    if not isinstance(raw, list):
        return {"status": NO_DATA, "reason": "NO_5M_SERIES"}
    rows = {}
    for b in raw:
        if not isinstance(b, dict):
            continue
        try:
            start, end = int(b["startMs"]), int(b["endMs"])
        except (KeyError, TypeError, ValueError):
            continue
        buy, sell = finite(b.get("buyBase")), finite(b.get("sellBase"))
        if start >= 0 and end - start == P5 and start % P5 == 0 and end <= now_ms and buy is not None and sell is not None and buy >= 0 and sell >= 0:
            rows[start] = (end, buy, sell)
    if not rows:
        return {"status": NO_DATA, "reason": "NO_VALID_CLOSED_BARS"}
    last_start = max(rows)
    end_ms = rows[last_start][0]
    if not (0 <= now_ms - end_ms <= MAX_AGE_MS):
        return {"status": NO_DATA, "reason": "STALE_TAKER_SERIES"}
    starts = [end_ms - HOUR + P5 * i for i in range(12)]
    if any(s not in rows or rows[s][0] != s + P5 for s in starts):
        return {"status": NO_DATA, "reason": "INCOMPLETE_1H_5M_WINDOW"}
    buy = sum(rows[s][1] for s in starts)
    sell = sum(rows[s][2] for s in starts)
    if buy + sell <= 0:
        return {"status": NO_DATA, "reason": "ZERO_VOLUME_NO_DIRECTION"}
    return {
        "status": OBSERVED,
        "venue": "OKX" if "OKX" in str(block.get("source")) else "Binance",
        "market": "USDT_PERPETUAL",
        "windowStartMs": end_ms - HOUR,
        "windowEndMs": end_ms,
        "closedFiveMinuteBars": 12,
        "imbalancePct": round(100 * (buy - sell) / (buy + sell), 4),
        "interpretation": "AGGREGATED_PERPETUAL_TAKER_IMBALANCE_NOT_SPOT_CVD",
        "volumeUnitAudit": "NOT_ATTESTED_FOR_CROSS_VENUE_COMPARISON",
    }


def oi_hour_change(perpetual, now_ms):
    """Compare two observed OKX contract-OI samples roughly one hour apart."""
    rows = (perpetual or {}).get("openInterestHistory")
    if not isinstance(rows, list):
        return {"status": NO_DATA, "reason": "NO_OI_HISTORY"}
    samples = {}
    for s in rows:
        if not isinstance(s, dict):
            continue
        try:
            ts = int(s["t"])
        except (KeyError, ValueError, TypeError):
            continue
        oi = finite(s.get("oiContracts"))
        if 0 < ts <= now_ms and oi is not None and oi > 0:
            samples[ts] = oi
    if not samples:
        return {"status": NO_DATA, "reason": "NO_VALID_CONTRACT_OI_SAMPLES"}
    ts = max(samples)
    if not (0 <= now_ms - ts <= MAX_AGE_MS):
        return {"status": NO_DATA, "reason": "STALE_OI"}
    target = ts - HOUR
    choices = [(abs(t - target), t) for t in samples if t < ts and abs(t - target) <= OI_TOLERANCE_MS]
    if not choices:
        return {"status": NO_DATA, "reason": "NO_MATCHED_1H_OI_SAMPLE"}
    _, previous_ts = min(choices)
    cur, old = samples[ts], samples[previous_ts]
    return {
        "status": OBSERVED, "venue": "OKX", "market": "USDT_PERPETUAL",
        "startMs": previous_ts, "endMs": ts,
        "actualSpanMinutes": round((ts - previous_ts) / 60_000, 3),
        "currentContracts": cur, "previousContracts": old,
        "deltaContracts": round(cur - old, 8),
        "deltaContractsPct1h": round(100 * (cur / old - 1), 5),
        "contractDefinition": "OKX_OI_CONTRACTS_VENUE_SPECIFIC",
        "crossVenueAggregationAllowed": False,
        "tradeDirectionInferred": False,
    }


def build(structure, flow, now_ms, nw=None):
    """N-W is a separate closed-bar research proxy, never a vendor-equivalent signal."""
    nw = nw if isinstance(nw, dict) else {}
    nw_generated_at = nw.get("generatedAt")
    try:
        source_age_ms = now_ms - int(datetime.fromisoformat(nw_generated_at.replace("Z", "+00:00")).timestamp() * 1000)
    except (ValueError, TypeError, AttributeError):
        source_age_ms = None
    nw_fresh = source_age_ms is not None and 0 <= source_age_ms <= 30 * 60_000

    instruments = {}
    oi_map = (structure.get("instruments") or {})
    taker_map = (flow.get("instruments") or {})
    for symbol in SYMBOLS:
        pp = (oi_map.get(symbol) or {}).get("perpetual") or {}
        fb = (taker_map.get(symbol) or {}).get("taker") or {}
        nw_frames = (nw.get("instruments") or {}).get(symbol) or {}
        validated_frames = {}
        if nw_fresh and nw.get("model", {}).get("parityStatus") == "TRADINGVIEW_PARITY_UNVERIFIED":
            for timeframe in ("15m", "1H", "4H", "1D"):
                state = nw_frames.get(timeframe) or {}
                if (state.get("status") == "MODEL_OBSERVED_UNVERIFIED_PARITY"
                        and state.get("closedCandleOnly") is True
                        and state.get("parityStatus") == "TRADINGVIEW_PARITY_UNVERIFIED"):
                    validated_frames[timeframe] = state
        nw_bridge = ({
            "status": "RESEARCH_PROXY_UNVERIFIED",
            "parityStatus": "TRADINGVIEW_PARITY_UNVERIFIED",
            "timeframes": validated_frames,
            "notTradeApproval": True,
        } if validated_frames else {
            "status": NO_DATA,
            "reason": "NO_FRESH_CLOSED_BAR_NW_PROXY_OR_TV_PARITY_NOT_TESTED",
        })
        instruments[symbol] = {
            "oi1h": oi_hour_change(pp, now_ms),
            "taker1h": normalized_hour_taker(fb, now_ms),
            "liquidations": {"status": NO_DATA, "reason": "CONTINUOUS_VERIFIED_LIQUIDATION_STREAM_NOT_CONNECTED"},
            "nadarayaWatsonNR": nw_bridge,
            "pifagorMFI": {"status": NO_DATA, "reason": "AUTHORIZED_ORIGINAL_ALERT_NOT_CONNECTED"},
            "bigGuyBurjKhalifa": {"status": NO_DATA, "reason": "AUTHORIZED_ORIGINAL_ALERT_NOT_CONNECTED"},
        }
    return {
        "schemaVersion": "derivatives-observability-1.0.0",
        "generatedAt": datetime.fromtimestamp(now_ms / 1000, timezone.utc).isoformat(),
        "researchOnly": True, "notTradeApproval": True, "noSpotOrFuturesWriteback": True,
        "sourceFiles": ["market-structure.json", "detector-rest-flow.json", "nadaraya-watson-research.json"],
        "sourceTimestamps": {
            "marketStructure": structure.get("generatedAt"),
            "detectorRestFlow": flow.get("generatedAt")},
        "caveats": [
            "1H OI samples are observed, venue-specific and may be ~1H apart within 8m tolerance.",
            "Taker flow is ONE perpetual venue, not a spot CVD or tick-level liquidation tape.",
            "NO_DATA never means zero; proprietary indicators require genuine authorized signals.",
        ],
        "instruments": instruments,
    }


def main():
    def load(path):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError):
            return {}
    payload = build(load(ROOT / "market-structure.json"),
                    load(ROOT / "detector-rest-flow.json"),
                    int(time.time() * 1000),
                    load(ROOT / "nadaraya-watson-research.json"))
    output = ROOT / "derivatives-observability.json"
    output.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    ready = sum(field["status"] == OBSERVED for x in payload["instruments"].values()
                for name, field in x.items() if name in ("oi1h", "taker1h"))
    print(f"Derivatives research: {ready} observed fields across {len(SYMBOLS)} assets; no trade authority.")


if __name__ == "__main__":
    main()
