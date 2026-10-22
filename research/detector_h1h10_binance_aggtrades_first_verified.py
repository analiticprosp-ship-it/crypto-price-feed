#!/usr/bin/env python3
"""Bounded first RAW aggTrades receipt/quality pilot: H1/H6/H7, RESEARCH_ONLY.

May 4, 2026 (before 2026-07 locked holdout), BTC/ETH/SOL, Binance Spot/UM.
Six HEAD checks; at most FOUR price/size-selected ZIP GETs, <=25MiB each,
<=60MiB aggregate; original publisher .CHECKSUM and ZIP CRC; strict 7-column
trade clocks, independent 5m buy/sell quote-flow masks, no missing-slot fill.
R2 original ZIP + derived evidence + run manifest: PUT-GET-SHA verified.
Archive observations made NOW are NOT the original historical publication time.
No model, no holdout access, no trading, no new service or subscription.
"""
import collections
import csv
import datetime as dt
import io
import json
import math
import os
from pathlib import Path
import zipfile

from research.detector_h1h10_binance_flow_archive_pilot import (
    DAYS, SYMBOLS, MARKETS, OUT as PREVIOUS_PREFIX,
    archive_url, checksum_sha, fetch_http, put_immutable, sha,
)

DAY = DAYS[0]
SCOPE = "RESEARCH_ONLY"
ROOT = "research/detector-h1h10-binance-aggtrades-verified/v1"
SCHEMA = "detector-h1h10-binance-aggtrades-bounded-raw-v1"
MAX_FILES = 4
MAX_ZIP_BYTES = 25 * 1024 * 1024
MAX_TOTAL_ZIP_BYTES = 60 * 1024 * 1024
MAX_CSV_UNCOMPRESSED = 400 * 1024 * 1024
MAX_ROWS = 3_000_000
FIVE_MIN_MS = 300000
EXPECTED_HEADERS = (
    "agg_trade_id", "price", "quantity", "first_trade_id",
    "last_trade_id", "transact_time", "is_buyer_maker"
)


def parse_day_zip(payload, market, symbol, day):
    """Source event-time audit ONLY; never claim as-of publication or fill gaps."""
    if market not in MARKETS or symbol not in SYMBOLS or day != DAY:
        raise ValueError("AGGTRADE_UNAUTHORIZED_SOURCE_IDENTITY")
    if not 0 < len(payload) <= MAX_ZIP_BYTES:
        raise ValueError("AGGTRADE_ZIP_SIZE_LIMIT")
    start = int(dt.datetime.fromisoformat(day + "T00:00:00+00:00").timestamp() * 1000)
    time_divisor = 1000 if market == "spot" else 1
    slots = collections.defaultdict(lambda: [0, 0.0, 0.0, 0.0, 0.0])
    count = 0
    header_present = False
    prev_id = None
    prev_ts = None
    first_ts = last_ts = None
    with zipfile.ZipFile(io.BytesIO(payload), "r") as archive:
        names = archive.namelist()
        expected = f"{symbol}-aggTrades-{day}.csv"
        if names != [expected]:
            raise ValueError("AGGTRADE_ZIP_MEMBER_IDENTITY_MISMATCH")
        member = archive.getinfo(expected)
        if not 0 < member.file_size <= MAX_CSV_UNCOMPRESSED:
            raise ValueError("AGGTRADE_UNPACKED_SIZE_LIMIT")
        if archive.testzip() is not None:
            raise ValueError("AGGTRADE_ZIP_CRC_FAILURE")
        with archive.open(member) as original:
            rows = csv.reader(io.TextIOWrapper(original, encoding="utf-8-sig", newline=""))
            for row in rows:
                if count == 0 and not header_present and row and row[0].strip().lower() in ("agg_trade_id", "aggtradeid", "a"):
                    columns = tuple(x.strip().lower() for x in row[:7])
                    normalized = tuple(s.replace("_", "") for s in columns)
                    expected_normal = tuple(s.replace("_", "") for s in EXPECTED_HEADERS)
                    if normalized != expected_normal:
                        raise ValueError("AGGTRADE_CSV_HEADER_UNKNOWN")
                    header_present = True
                    continue
                if len(row) not in (7, 8):
                    raise ValueError("AGGTRADE_CSV_COLUMNS_INVALID")
                if count >= MAX_ROWS:
                    raise ValueError("AGGTRADE_ROW_COUNT_LIMIT")
                try:
                    aid = int(row[0])
                    price = float(row[1])
                    quantity = float(row[2])
                    first_id = int(row[3]); last_id = int(row[4])
                    raw_time = int(row[5])
                    maker = row[6].strip().lower()
                except (TypeError, ValueError, OverflowError) as exc:
                    raise ValueError("AGGTRADE_CSV_FIELDS_INVALID") from exc
                if (aid < 0 or first_id < 0 or last_id < first_id
                    or not math.isfinite(price) or not math.isfinite(quantity)
                    or price <= 0 or quantity <= 0 or maker not in ("true", "false")):
                    raise ValueError("AGGTRADE_TRADE_SEMANTICS_INVALID")
                if prev_id is not None and aid <= prev_id:
                    raise ValueError("AGGTRADE_DUPLICATE_OR_NONMONOTONIC_ID")
                if not start * time_divisor <= raw_time < (start + 86_400_000) * time_divisor:
                    raise ValueError("AGGTRADE_DAY_OR_TIME_UNIT_MISMATCH")
                if raw_time % time_divisor and market == "um":
                    raise ValueError("AGGTRADE_UM_TIMESTAMP_NOT_MS")
                event_ms = raw_time // time_divisor
                if prev_ts is not None and event_ms < prev_ts:
                    raise ValueError("AGGTRADE_NONMONOTONIC_EVENT_TIME")
                count += 1;prev_id = aid;prev_ts = event_ms
                if first_ts is None:
                    first_ts = raw_time
                last_ts = raw_time
                slot = event_ms // FIVE_MIN_MS * FIVE_MIN_MS
                sample = slots[slot]
                sample[0] += 1
                if maker == "false":
                    sample[1] += quantity
                    sample[3] += price * quantity
                else:
                    sample[2] += quantity
                    sample[4] += price * quantity
    if count == 0:
        raise ValueError("AGGTRADE_EMPTY_SOURCE")
    slot_ids = sorted(slots)
    observed = len(slot_ids)
    if observed > 288:
        raise ValueError("AGGTRADE_5M_BUCKET_OVERFLOW")
    rows = []
    for time_ms in slot_ids:
        n, buy_base, sell_base, buy_quote, sell_quote = slots[time_ms]
        rows.append({
            "bucket_start_utc": dt.datetime.fromtimestamp(time_ms / 1000, dt.timezone.utc).isoformat(),
            "aggtrade_count": n,
            "taker_buy_base": round(buy_base, 10),
            "taker_sell_base": round(sell_base, 10),
            "taker_buy_quote_usdt": round(buy_quote, 8),
            "taker_sell_quote_usdt": round(sell_quote, 8),
            "net_taker_quote_usdt": round(buy_quote-sell_quote, 8),
            "total_quote_usdt": round(buy_quote+sell_quote, 8),
            "availability": "EVENT_TIME_ONLY_FIRST_PUBLICATION_UNVERIFIED",
        })
    quality = {
        "symbol": symbol, "market": market, "utc_day": day,
        "trades": count, "five_minute_slots_with_trades": observed,
        "missing_five_minute_slots": 288-observed,
        "first_raw_trade_time": first_ts, "last_raw_trade_time": last_ts,
        "trade_clock_unit": "microseconds" if market == "spot" else "milliseconds",
        "csv_header_present": header_present,
        "publisher_zip_crc": "VERIFIED",
        "aggtrade_id_monotonicity": "VERIFIED",
        "source_event_time": "VERIFIED_SOURCE_LABEL_ONLY",
        "historical_original_publication_time": "UNVERIFIED",
        "conclusion": "EVENT_TIME_ONLY_NOT_ASOF",
        "causal_rows_authorized": 0,
    }
    return quality, rows


def flow_csv_bytes(rows):
    if not rows:
        raise ValueError("EMPTY_DERIVED_FLOW")
    buf = io.StringIO(newline="")
    fieldnames = list(rows[0])
    writer = csv.DictWriter(buf, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8")


def select_sources(head):
    """Select two smallest verified-size Spot and two smallest USD-M only."""
    if set(head) != {(market, sym) for market in MARKETS for sym in SYMBOLS}:
        raise ValueError("SOURCE_AVAILABILITY_INCOMPLETE")
    picked = []
    skipped = []
    total = 0
    for market in MARKETS:
        choices = sorted(((sym, head[market, sym]) for sym in SYMBOLS),
                         key=lambda x: (x[1].get("bytes") if x[1].get("bytes") is not None else 10**15, x[0]))
        added = 0
        for symbol, meta in choices:
            length = meta.get("bytes")
            if (meta.get("http") != 200 or type(length) is not int
                or length <= 0 or length > MAX_ZIP_BYTES):
                skipped.append({"market": market, "symbol": symbol, "reason": "HTTP_OR_SOURCE_SIZE_NOT_ELIGIBLE",
                                "observed_http": meta.get("http"), "observed_bytes": length})
                continue
            if added < 2 and len(picked) < MAX_FILES and total + length <= MAX_TOTAL_ZIP_BYTES:
                picked.append((market, symbol, length))
                total += length
                added += 1
            else:
                skipped.append({"market": market, "symbol": symbol, "reason": "BOUNDED_SELECTION_CAP",
                                "observed_bytes": length})
    return picked, skipped


def main():
    import boto3
    if os.environ.get("GITHUB_REPOSITORY") != "analiticprosp-ship-it/crypto-price-feed":
        raise ValueError("RESEARCH_REPOSITORY_SCOPE")
    run = os.environ["GITHUB_RUN_ID"]
    attempt = os.environ.get("GITHUB_RUN_ATTEMPT", "1")
    if not run.isdigit() or not attempt.isdigit():
        raise ValueError("INVALID_GITHUB_RUN")
    s3 = boto3.client(
        "s3", endpoint_url="https://" + os.environ["R2_ACCOUNT_ID"] + ".r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto")
    bucket = os.environ["R2_BUCKET"]
    head = {}
    for market in MARKETS:
        for symbol in SYMBOLS:
            url = archive_url(market, "aggTrades", symbol, DAY)
            status = fetch_http(url, "HEAD")
            head[market, symbol] = status
    chosen, skipped = select_sources(head)
    results = []
    for market, symbol, observed_size in chosen:
        url = archive_url(market, "aggTrades", symbol, DAY)
        try:
            body = fetch_http(url, "GET", cap=MAX_ZIP_BYTES)
            publisher_sha = checksum_sha(
                fetch_http(url + ".CHECKSUM", "GET", cap=512), url.split("/")[-1])
            if sha(body) != publisher_sha:
                raise ValueError("AGGTRADE_PUBLISHER_SHA256_FAILED")
            quality, rows = parse_day_zip(body, market, symbol, DAY)
            raw_key = ROOT + "/raw/" + market + "-" + symbol + "-" + publisher_sha + ".zip"
            derived = flow_csv_bytes(rows)
            derived_sha = sha(derived)
            derived_key = ROOT + "/derived/" + market + "-" + symbol + "-" + derived_sha + ".csv"
            if put_immutable(s3, bucket, raw_key, body) != publisher_sha:
                raise ValueError("AGGTRADE_ORIGINAL_R2_SHA_FAILED")
            if put_immutable(s3, bucket, derived_key, derived) != derived_sha:
                raise ValueError("AGGTRADE_DERIVED_R2_SHA_FAILED")
            results.append({**quality, "status": "PUBLISHER_SHA_AND_SOURCE_EVENT_VERIFIED",
                            "publisher_sha256": publisher_sha,
                            "raw_r2_key": raw_key, "derived_r2_key": derived_key,
                            "derived_sha256": derived_sha, "zip_bytes": len(body),
                            "head_observed_bytes": observed_size,
                            "downloaded_during_2026_10_research": True})
        except Exception as exc:
            # Never silently label missing/broken sources as successfully verified.
            results.append({"market": market, "symbol": symbol,
                            "status": "SOURCE_VERIFICATION_FAILED",
                            "error_type": type(exc).__name__,
                            "error_code": str(exc)[:100],
                            "causal_rows_authorized": 0})
    verified = [r for r in results if r["status"] == "PUBLISHER_SHA_AND_SOURCE_EVENT_VERIFIED"]
    report = {
        "schema": SCHEMA, "scope": SCOPE, "market": "BINANCE_SPOT_AND_USDM",
        "utc_day": DAY, "source_symbols": list(SYMBOLS),
        "selection_rule": "UP_TO_TWO_SMALLEST_VERIFIED_SIZE_ZIPS_PER_MARKET",
        "per_zip_max_bytes": MAX_ZIP_BYTES,
        "aggregate_max_zip_bytes": MAX_TOTAL_ZIP_BYTES,
        "head_checks": [
            {"market": m, "symbol": s, **head[m,s]}
            for m in MARKETS for s in SYMBOLS
        ],
        "chosen_zip_count": len(chosen),
        "verified_zip_count": len(verified),
        "skipped": skipped, "files": results,
        "actual_aggtrades_verified": sum(r["trades"] for r in verified),
        "event_only_five_minute_slots": sum(r["five_minute_slots_with_trades"] for r in verified),
        "source_publication_availability": "UNVERIFIED",
        "same_venue_causal_h1_h6_h7": "BLOCKED",
        "historical_exchange_release_pit": "BLOCKED",
        "training_authorized": False, "locked_holdout_consumed": False,
        "causal_joint_rows_authorized": 0,
        "edge_status": "EDGE_UNVALIDATED",
        "trading_actions": False,
        "new_paid_services": False,
        "github_run": run, "attempt": attempt,
    }
    data = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True).encode()
    key = ROOT + "/run-reports/" + run + "-" + attempt + ".json"
    digest = put_immutable(s3, bucket, key, data)
    path = Path("detector_h1h10_aggtrades_first_source/verified.json")
    path.parent.mkdir(exist_ok=True, parents=True)
    path.write_text(json.dumps({**report, "r2_key": key, "sha256": digest},
                               ensure_ascii=False, indent=2), encoding="utf-8")
    print("H1H10_VERIFIED_BINANCE_AGGTRADES", json.dumps({
        "head_http_200": sum(z.get("http") == 200 for z in head.values()),
        "selected": len(chosen), "actual_archives_verified": len(verified),
        "raw_trade_rows_verified": report["actual_aggtrades_verified"],
        "real_event_only_5m_slots": report["event_only_five_minute_slots"],
        "failed": len(results) - len(verified), "skipped": len(skipped),
        "historical_first_publication": "UNVERIFIED",
        "causal_authorized": 0, "r2_key": key, "sha256": digest,
    }, ensure_ascii=False), flush=True)
    if not verified or len({r["market"] for r in verified}) < 2:
        raise ValueError("SPOT_AND_UM_RAW_SOURCE_EVIDENCE_NOT_BOTH_VERIFIED")


if __name__ == "__main__":
    main()
