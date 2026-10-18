#!/usr/bin/env python3
"""Prospective OI availability observer (BTC/ETH/SOL), research only.

Measures when this runner actually received Binance USD-M 5m OI history.
A first-seen time is an observation-based upper bound, NOT exact publication.
Existing historical CSV create_time is NEVER treated as first availability.
"""
import datetime as dt
import email.utils
import hashlib
import json
import os
import time
import urllib.parse
import urllib.request

import boto3

SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
PREFIX = "research/oi-availability/v1"
SCHEMA = "detector-h1-h10-oi-availability-v1"
MAX_API_BYTES = 150_000


def utc_iso(ms):
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).isoformat()


def row_fingerprint(row):
    """Detect vendor changes to the content separately from timestamp semantics."""
    vals = {k: str(row.get(k, "")) for k in
            ("timestamp", "symbol", "sumOpenInterest", "sumOpenInterestValue")}
    return hashlib.sha256(json.dumps(vals, sort_keys=True).encode()).hexdigest()


def validate_rows(payload, symbol, response_ms):
    if not isinstance(payload, list) or not payload or len(payload) > 12:
        raise ValueError("INVALID_OI_HISTORY_RESPONSE")
    out = []
    seen = set()
    for row in payload:
        if not isinstance(row, dict) or row.get("symbol") != symbol:
            raise ValueError("OI_SYMBOL_MISMATCH")
        ts = int(row["timestamp"])
        if ts in seen or ts < 1600000000000 or ts > response_ms + 60000:
            raise ValueError("OI_TIMESTAMP_DUPLICATE_OR_OUT_OF_RANGE")
        seen.add(ts)
        if not row.get("sumOpenInterest") or not row.get("sumOpenInterestValue"):
            raise ValueError("OI_MISSING_VALUE")
        out.append({
            "timestamp_ms": ts,
            "sum_open_interest": str(row["sumOpenInterest"]),
            "sum_open_interest_value": str(row["sumOpenInterestValue"]),
            "row_sha256": row_fingerprint(row),
        })
    out.sort(key=lambda r: r["timestamp_ms"])
    return out


def poll(symbol):
    query = urllib.parse.urlencode({"symbol": symbol, "period": "5m", "limit": 12})
    url = "https://fapi.binance.com/futures/data/openInterestHist?" + query
    req = urllib.request.Request(url, headers={
        "User-Agent": "Detector-H1-H10-Research/1.0",
        "Accept": "application/json",
    })
    t0 = int(time.time() * 1000)
    begin = time.monotonic_ns()
    with urllib.request.urlopen(req, timeout=18) as r:
        if r.status != 200:
            raise ValueError("OI_HTTP_STATUS_NOT_200")
        body = r.read(MAX_API_BYTES + 1)
        server_date = r.headers.get("Date")
    t1 = int(time.time() * 1000)
    if len(body) > MAX_API_BYTES:
        raise ValueError("OI_RESPONSE_SIZE_LIMIT")
    payload = json.loads(body)
    rows = validate_rows(payload, symbol, t1)
    server_ms = None
    if server_date:
        server_ms = int(email.utils.parsedate_to_datetime(server_date).timestamp() * 1000)
    return {
        "symbol": symbol, "request_start_ms": t0, "response_received_ms": t1,
        "round_trip_ms": int((time.monotonic_ns() - begin) / 1_000_000),
        "http_server_date_ms": server_ms,
        "rows": rows, "source": "Binance USD-M GET /futures/data/openInterestHist?period=5m",
    }


def data_json(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2).encode()


def write_verified(s3, bucket, key, obj):
    data = data_json(obj)
    digest = hashlib.sha256(data).hexdigest()
    s3.put_object(Bucket=bucket, Key=key, Body=data,
                  ContentType="application/json", Metadata={"sha256": digest})
    retrieved = s3.get_object(Bucket=bucket, Key=key)["Body"].read(len(data) + 1)
    if hashlib.sha256(retrieved).hexdigest() != digest:
        raise ValueError("R2_WRITE_READBACK_SHA256_MISMATCH")


def load_json(s3, bucket, key):
    try:
        return json.loads(s3.get_object(Bucket=bucket, Key=key)["Body"].read(150_000))
    except s3.exceptions.NoSuchKey:
        return None
    except s3.exceptions.ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
            return None
        raise


def new_appearances(previous, measurement):
    """First observed by *our* polls. Only infer absence with strict bounds."""
    if previous is None:
        return [], True
    prior_rows = previous.get("rows", [])
    old_ts = {r["timestamp_ms"] for r in prior_rows}
    old_max = max(old_ts) if old_ts else -1
    prev_time = int(previous["response_received_ms"])
    fresh = []
    for row in measurement["rows"]:
        if row["timestamp_ms"] in old_ts:
            continue
        absent = row["timestamp_ms"] > old_max and prev_time >= row["timestamp_ms"]
        fresh.append({
            "schema": SCHEMA, "symbol": measurement["symbol"],
            "source_timestamp_ms": row["timestamp_ms"],
            "source_timestamp_utc": utc_iso(row["timestamp_ms"]),
            "first_observed_at_utc": utc_iso(measurement["response_received_ms"]),
            "first_observed_ms": measurement["response_received_ms"],
            "last_observed_absent_ms": prev_time if absent else None,
            "last_observed_absent_utc": utc_iso(prev_time) if absent else None,
            "bound_type": "QUERY_ABSENCE_TO_FIRST_OBSERVATION" if absent else "FIRST_OBSERVATION_ONLY",
            "first_row_sha256": row["row_sha256"],
            "interpretation": "First seen by this sampled API collector; not exact exchange publication time.",
        })
    return fresh, False


def main():
    bucket = os.environ["R2_BUCKET"]
    s3 = boto3.client(
        "s3",
        endpoint_url="https://" + os.environ["R2_ACCOUNT_ID"] + ".r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )
    polls = []
    errors = []
    new_points = 0
    for sym in SYMBOLS:
        try:
            measurement = poll(sym)
            state_key = f"{PREFIX}/state/{sym}.json"
            previous = load_json(s3, bucket, state_key)
            fresh, bootstrap = new_appearances(previous, measurement)
            created = 0
            for item in fresh:
                k = f"{PREFIX}/first-observed/{sym}/{item['source_timestamp_ms']}.json"
                prior = load_json(s3, bucket, k)
                if prior is None:
                    write_verified(s3, bucket, k, item)
                    created += 1
            # Update state only after the immutable first-observed records were checked.
            write_verified(s3, bucket, state_key, measurement)
            new_points += created
            polls.append({
                "symbol": sym, "status": "OBSERVED",
                "bootstrap": bootstrap,
                "received_at_utc": utc_iso(measurement["response_received_ms"]),
                "most_recent_source_timestamp_utc": utc_iso(measurement["rows"][-1]["timestamp_ms"]),
                "new_first_observed_records": created,
                "lag_to_newest_source_label_ms":
                    measurement["response_received_ms"] - measurement["rows"][-1]["timestamp_ms"],
                "request_round_trip_ms": measurement["round_trip_ms"],
                "server_date_delta_ms": (measurement["response_received_ms"] -
                                         measurement["http_server_date_ms"]) if measurement["http_server_date_ms"] else None,
            })
        except Exception as exc:
            errors.append({"symbol": sym, "error_type": type(exc).__name__,
                           "reason": str(exc)[:120]})
            polls.append({"symbol": sym, "status": "SOURCE_UNAVAILABLE_OR_WRITEBACK_FAILURE"})
    run = os.environ.get("GITHUB_RUN_ID", "unknown")
    attempt = os.environ.get("GITHUB_RUN_ATTEMPT", "1")
    now = dt.datetime.now(dt.timezone.utc)
    result = {
        "schema": SCHEMA, "status": "POLL_OK" if not errors else "POLL_PARTIAL",
        "observed_at_utc": now.isoformat(),
        "github_run_id": run, "github_run_attempt": attempt,
        "results": polls, "errors": errors,
        "new_first_observed_records": new_points,
        "source_semantics": "Binance REST timestamp labels 5m; actual publication time unverified",
        "statement": "Only upper bounds from sampled observation; no retrospective availability proof",
        "scope": "isolated H1-H10 research; no orders or portfolio changes",
    }
    key = f"{PREFIX}/polls/{now:%Y-%m-%d}/{run}-{attempt}.json"
    write_verified(s3, bucket, key, result)
    print("OI_AVAILABILITY_POLL", json.dumps(result, ensure_ascii=False), flush=True)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write("## H1-H10 live OI availability observation\n\n")
            f.write(f"- Status: {result['status']}\n- New first-observed records: {new_points}\n")
            for item in polls:
                f.write(f"- {item['symbol']}: {item['status']}, {item.get('most_recent_source_timestamp_utc', 'n/a')}\n")
            f.write("- Publication time: UNVERIFIED (sampling bounds only)\n")
    if errors:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
