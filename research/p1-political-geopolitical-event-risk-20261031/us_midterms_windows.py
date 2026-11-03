#!/usr/bin/env python3
"""Offline window planner and outcome calculator; no network or trading actions."""
import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

STEP = 300
PRODUCTS = ("BTC-USD", "ETH-USD")
HORIZONS = (("15m", 900), ("1h", 3600), ("4h", 14400), ("1d", 86400),
            ("7d", 604800), ("30d", 2592000), ("90d", 7776000))
ROOT = Path(__file__).resolve().parent
API = "api.exchange.coinbase.com"


def utc(value):
    if not value.endswith("Z"):
        raise ValueError("use a timestamp ending in Z")
    return datetime.fromisoformat(value[:-1] + "+00:00").timestamp()


def iso(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat().replace("+00:00", "Z")


def verified_bytes(root, relative, expected_sha):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("receipt path is outside the receipt directory")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha:
        raise ValueError(f"SHA-256 mismatch: {relative}")
    return raw


def event_clock(event, as_of, news_dir):
    """Return (pre-event boundary source, conservative post-event anchor)."""
    if event["role"] == "calendar_control":
        if event["timing_status"] != "SCHEDULE_CONFIRMED":
            raise ValueError("calendar control requires a confirmed schedule")
        clock = utc(event["scheduled_at_utc"])
        return clock, clock
    status = event["timing_status"]
    if status not in ("EXACT_SOURCE_AVAILABLE", "BOUNDED_SOURCE_AVAILABLE"):
        return None
    evidence = event["availability_evidence"]
    seen = utc(evidence["observed_at_utc"])
    if seen > as_of:
        return None
    if news_dir is None:
        raise ValueError("accepted result needs --news-dir with archived evidence")
    verified_bytes(news_dir, evidence["path"], evidence["sha256"])
    if status == "EXACT_SOURCE_AVAILABLE":
        exact = utc(event["first_market_available_timestamp_utc"])
        if exact > seen:
            raise ValueError("exact availability follows receipt")
        return exact, exact
    lo = utc(event["availability_lower_utc"])
    hi = utc(event["availability_upper_utc"])
    absent = evidence["last_absent"]
    verified_bytes(news_dir, absent["path"], absent["sha256"])
    if not (lo == utc(absent["observed_at_utc"]) < hi == seen and hi - lo <= 120):
        raise ValueError("invalid or over-wide availability interval")
    if lo // STEP != hi // STEP:
        return None  # ambiguous 5m bucket: sensitivity only
    return lo, hi


def load_market(manifest_path, as_of):
    """Read only hash-verified Coinbase Exchange 5m responses available at cutoff."""
    out = {product: {} for product in PRODUCTS}
    for receipt in json.loads(manifest_path.read_text())["receipts"]:
        product = receipt["product_id"]
        if product not in PRODUCTS:
            raise ValueError(f"unexpected product: {product}")
        received = utc(receipt["retrieved_at_utc"])
        if received > as_of:
            continue
        url = urlsplit(receipt["request_url"])
        query = parse_qs(url.query)
        if (url.scheme, url.netloc, url.path, query.get("granularity")) != (
            "https", API, f"/products/{product}/candles", ["300"]
        ):
            raise ValueError("unexpected venue, product, or granularity")
        start, end = (utc(query[key][0]) for key in ("start", "end"))
        if start % STEP or end % STEP or not 0 < end - start <= 299 * STEP:
            raise ValueError("request must be on the 5m UTC grid, <=299 buckets")
        raw = verified_bytes(manifest_path.parent, receipt["path"], receipt["sha256"])
        for bar in json.loads(raw):
            if len(bar) != 6:
                raise ValueError("unexpected Coinbase candle schema")
            t, low, high, op, close, volume = bar
            if not start <= t < end or t + STEP > min(as_of, received):
                continue
            if (type(t) is not int or t % STEP or
                any(type(x) not in (int, float) or not math.isfinite(x)
                    for x in (low, high, op, close, volume)) or
                not 0 < low <= min(op, close) <= max(op, close) <= high or volume < 0):
                raise ValueError(f"invalid candle: {product} {t}")
            previous = out[product].setdefault(t, bar)
            if previous != bar:
                raise ValueError(f"conflicting candles: {product} {t}")
    return out


def measures(bars):
    entry = bars[0][3]
    closes = [entry] + [bar[4] for bar in bars]
    return {
        "first_open": entry,
        "final_close": closes[-1],
        "return": closes[-1] / entry - 1,
        "mae_from_open": min(0.0, min(bar[1] for bar in bars) / entry - 1),
        "mfe_from_open": max(0.0, max(bar[2] for bar in bars) / entry - 1),
        "realized_vol_unannualized": math.sqrt(sum(
            math.log(right / left) ** 2 for left, right in zip(closes, closes[1:])
        )),
        "base_volume": sum(bar[5] for bar in bars),
    }


def windows(ledger, as_of, market=None, news_dir=None):
    if utc(ledger["audit_as_of_utc"]) > as_of:
        raise ValueError("cutoff predates ledger version")
    for event in ledger["events"]:
        role = event["role"]
        if role == "calendar_metadata":
            continue
        clocks = event_clock(event, as_of, news_dir)
        durations = HORIZONS[:4] if role == "diagnostic" else HORIZONS
        for label, seconds in (("pre_24h", -86400), *durations):
            for product in PRODUCTS:
                row = dict(event_id=event["event_id"], role=role, product=product,
                           window=label, start_utc=None, end_utc=None,
                           metrics=None, status="PENDING_ANCHOR")
                if clocks is not None:
                    before, after = clocks
                    if seconds < 0:
                        end = int(before // STEP) * STEP
                        start = end + seconds
                    else:
                        start = (int(after // STEP) + 1) * STEP
                        end = start + seconds
                    row.update(start_utc=iso(start), end_utc=iso(end))
                    if end > as_of:
                        row["status"] = "WINDOW_NOT_MATURED"
                    elif market is None or not market[product]:
                        row["status"] = "PENDING_MARKET_DATA"
                    else:
                        series = market[product]
                        stamps = range(start, end, STEP)
                        missing = [t for t in stamps if t not in series]
                        if missing:
                            row.update(status="DATA_GAP", missing_bars=len(missing),
                                       first_missing_utc=iso(missing[0]))
                        else:
                            row.update(status="OK", metrics=measures([series[t] for t in stamps]))
                yield row


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ledger", type=Path, default=ROOT / "us_midterms_2026_11_03_v1.json")
    p.add_argument("--as-of", required=True, help="ISO timestamp ending in Z")
    p.add_argument("--market-manifest", type=Path)
    p.add_argument("--news-dir", type=Path)
    args = p.parse_args()
    cutoff = utc(args.as_of)
    raw = args.ledger.read_bytes()
    market = load_market(args.market_manifest, cutoff) if args.market_manifest else None
    print(json.dumps({
        "as_of_utc": args.as_of,
        "ledger_sha256": hashlib.sha256(raw).hexdigest(),
        "market_manifest_sha256": (
            hashlib.sha256(args.market_manifest.read_bytes()).hexdigest()
            if args.market_manifest else None
        ),
        "windows": list(windows(json.loads(raw), cutoff, market, args.news_dir)),
    }, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
