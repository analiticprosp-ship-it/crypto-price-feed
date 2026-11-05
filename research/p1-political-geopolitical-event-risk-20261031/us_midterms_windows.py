#!/usr/bin/env python3
"""Offline window planner and outcome calculator; no network or trading actions."""
import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
import re
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

STEP = 300
PRODUCTS = ("BTC-USD", "ETH-USD")
HORIZONS = (("15m", 900), ("1h", 3600), ("4h", 14400), ("1d", 86400),
            ("7d", 604800), ("30d", 2592000), ("90d", 7776000))
ROOT = Path(__file__).resolve().parent
API = "api.exchange.coinbase.com"


def utc(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z", value):
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
    if event["role"] == "observation_control":
        # This clock measures our receipt, never the first public result.
        evidence = event["observation_evidence"]
        seen = utc(evidence["observed_at_utc"])
        if seen > as_of:
            return None
        if news_dir is None:
            raise ValueError("observation requires archived receipt")
        verified_bytes(news_dir, evidence["path"], evidence["sha256"])
        if event["timing_status"] != "OBSERVATION_CONFIRMED":
            return None
        return seen, seen
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
    if evidence.get("capture_kind") != "ORIGINAL_SOURCE_RESPONSE":
        raise ValueError("result anchor requires original source response, not an extract")
    if not all(evidence.get(key) for key in ("source_url", "source_item_id", "source_version",
                                           "semantic_review", "publication_proof_method")):
        raise ValueError("result anchor lacks source identity or reviewed publication proof")
    if status == "EXACT_SOURCE_AVAILABLE":
        if event.get("availability_lower_utc") or event.get("availability_upper_utc"):
            raise ValueError("exact clock cannot also have interval bounds")
        exact = utc(event["first_market_available_timestamp_utc"])
        if exact > seen:
            raise ValueError("exact availability follows receipt")
        return exact, exact
    if event.get("first_market_available_timestamp_utc"):
        raise ValueError("bounded clock cannot claim an exact timestamp")
    lo = utc(event["availability_lower_utc"])
    hi = utc(event["availability_upper_utc"])
    absent = evidence["last_absent"]
    verified_bytes(news_dir, absent["path"], absent["sha256"])
    if not (lo == utc(absent["observed_at_utc"]) < hi == seen):
        raise ValueError("invalid availability interval")
    if hi - lo > 120 or lo // STEP != hi // STEP:
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
            if (type(t) is not int or t % STEP or
                any(type(x) not in (int, float) or not math.isfinite(x)
                    for x in (low, high, op, close, volume)) or
                not 0 < low <= min(op, close) <= max(op, close) <= high or volume < 0):
                raise ValueError(f"invalid candle: {product} {t}")
            if not start <= t < end or t + STEP > min(as_of, received):
                continue
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
    events = ledger["events"] + ledger.get("observation_events", [])
    if len({event["event_id"] for event in events}) != len(events):
        raise ValueError("duplicate event IDs")
    for event in events:
        role = event["role"]
        if role not in ("calendar_metadata", "calendar_control", "diagnostic", "primary", "observation_control"):
            raise ValueError("unknown event role")
        if role == "calendar_metadata":
            continue
        clocks = event_clock(event, as_of, news_dir)
        durations = HORIZONS[:4] if role == "diagnostic" else HORIZONS
        intervals = durations if role == "observation_control" else (("pre_24h", -86400), *durations)
        for label, seconds in intervals:
            for product in PRODUCTS:
                row = dict(event_id=event["event_id"], role=role, product=product,
                           window=label, start_utc=None, end_utc=None,
                           metrics=None, baseline=None, status="PENDING_ANCHOR",
                           timing_status=event["timing_status"],
                           anchor_receipt_sha256=(event.get("availability_evidence") or
                                                  event.get("observation_evidence") or {}).get("sha256"),
                           estimand=("AFTER_OBSERVATION_MONITORING" if role == "observation_control"
                                     else "CALENDAR_COMPARISON" if role == "calendar_control"
                                     else "AFTER_SOURCE_AVAILABILITY"),
                           study_class="DESCRIPTIVE")
                if clocks is not None:
                    before, after = clocks
                    if seconds < 0:
                        end = int(before // STEP) * STEP
                        start = end + seconds
                    else:
                        start = (int(after // STEP) + 1) * STEP
                        end = start + seconds
                    row.update(start_utc=iso(start), end_utc=iso(end),
                               anchor_lower_utc=iso(before), anchor_upper_utc=iso(after))
                    first = (market or {}).get(product, {}).get(start)
                    if first is not None:
                        row["baseline"] = dict(price=first[3], field="open", timestamp_utc=iso(start),
                                               candle_sha256=candle_hash(first))
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


def candle_hash(bar):
    return hashlib.sha256(json.dumps(bar, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def baseline_entries(rows):
    """Only eligible closed first candles. No choosing a later candle after a gap."""
    entries = {}
    for row in rows:
        if row["window"] == "pre_24h" or row["baseline"] is None:
            continue
        key = row["event_id"] + "|" + row["product"]
        value = {k: row[k] for k in ("event_id", "product", "start_utc", "anchor_lower_utc",
                                     "anchor_upper_utc", "anchor_receipt_sha256", "estimand", "baseline")}
        if key in entries and entries[key] != value:
            raise ValueError("inconsistent baseline across horizons")
        entries[key] = value
    return entries


def check_baseline_lock(rows, lock, as_of):
    if utc(lock["frozen_as_of_utc"]) > as_of:
        raise ValueError("baseline lock is newer than cutoff")
    current = baseline_entries(rows)
    for key, saved in lock["entries"].items():
        if key not in current or current[key] != saved:
            raise ValueError("baseline changed or unavailable: " + key)


def event_audit(ledger, as_of, news_dir):
    output = []
    for event in ledger["events"] + ledger.get("observation_events", []):
        clocks = None if event["role"] == "calendar_metadata" else event_clock(event, as_of, news_dir)
        output.append(dict(event_id=event["event_id"], role=event["role"],
                           timing_status=event["timing_status"],
                           result_anchor_required=event["role"] in ("primary", "diagnostic"),
                           usable_scoring_clock=clocks is not None,
                           anchor_lower_utc=iso(clocks[0]) if clocks else None,
                           anchor_upper_utc=iso(clocks[1]) if clocks else None))
    return output


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ledger", type=Path, default=ROOT / "us_midterms_2026_11_03_v1.json")
    p.add_argument("--as-of", required=True, help="ISO timestamp ending in Z")
    p.add_argument("--market-manifest", type=Path)
    p.add_argument("--news-dir", type=Path)
    p.add_argument("--baseline-lock", type=Path, help="verify pinned first candles from an earlier run")
    p.add_argument("--write-baseline-lock", type=Path, help="create a new immutable lock; never overwrite")
    args = p.parse_args()
    cutoff = utc(args.as_of)
    raw = args.ledger.read_bytes()
    market = load_market(args.market_manifest, cutoff) if args.market_manifest else None
    ledger = json.loads(raw)
    rows = list(windows(ledger, cutoff, market, args.news_dir))
    if args.baseline_lock:
        check_baseline_lock(rows, json.loads(args.baseline_lock.read_bytes()), cutoff)
    if args.write_baseline_lock:
        entries = baseline_entries(rows)
        if not entries:
            raise ValueError("no verified first candles to freeze; no empty/zero baseline lock")
        lock = dict(frozen_as_of_utc=args.as_of, ledger_sha256=hashlib.sha256(raw).hexdigest(),
                    market_manifest_sha256=hashlib.sha256(args.market_manifest.read_bytes()).hexdigest(),
                    parent_lock_sha256=(hashlib.sha256(args.baseline_lock.read_bytes()).hexdigest()
                                        if args.baseline_lock else None), entries=entries)
        with args.write_baseline_lock.open("x") as handle:
            json.dump(lock, handle, indent=2, allow_nan=False)
            handle.write("\n")
    print(json.dumps({
        "as_of_utc": args.as_of,
        "calculator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "baseline_lock_sha256": (hashlib.sha256(args.baseline_lock.read_bytes()).hexdigest()
                                 if args.baseline_lock else None),
        "ledger_sha256": hashlib.sha256(raw).hexdigest(),
        "market_manifest_sha256": (
            hashlib.sha256(args.market_manifest.read_bytes()).hexdigest()
            if args.market_manifest else None
        ),
        "event_audit": event_audit(ledger, cutoff, args.news_dir),
        "windows": rows,
    }, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()

