#!/usr/bin/env python3
"""RESEARCH_ONLY: prospective OKX perpetual instrument unit-spec receipt archive.

This observes CURRENT publicly returned instrument definitions. It never invents
historical effective-at dates or uses today's ctVal/ctMult for 2022-2026 data.
No portfolio actions, trading endpoints, inferred PIT or production authority.
"""
import datetime as dt
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
import time
import urllib.parse
import urllib.request

import boto3
from research.detector_okx_oi_48h_pilot import store

SYMBOLS = ("BTC-USDT-SWAP", "ETH-USDT-SWAP", "SOL-USDT-SWAP")
PREFIX = "research/detector-okx-instrument-receipts/v1"
SCHEMA = "detector-h1h10-okx-public-instrument-unit-receipt-v1"
ENDPOINT = "/api/v5/public/instruments"
MAX_BYTES = 128000
SPEC_KEYS = ("instId", "instType", "ctType", "ctVal", "ctMult", "ctValCcy",
             "settleCcy", "lotSz", "tickSz", "listTime", "state", "instFamily")


def utc(ms):
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).isoformat()


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def positive_string(value):
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        x = Decimal(value)
        return x.is_finite() and x > 0
    except InvalidOperation:
        return False


def extract(payload, symbol, started_ms, received_ms):
    if symbol not in SYMBOLS:
        raise ValueError("FOREIGN_INSTRUMENT")
    if (not isinstance(started_ms, int) or not isinstance(received_ms, int)
        or started_ms < 1600000000000 or received_ms < started_ms):
        raise ValueError("BAD_HTTP_RECEIPT_CLOCK")
    if not isinstance(payload, dict) or str(payload.get("code")) != "0":
        raise ValueError("SOURCE_API_NOT_SUCCESS")
    data = payload.get("data")
    if not isinstance(data, list) or len(data) != 1 or not isinstance(data[0], dict):
        raise ValueError("INSTRUMENT_CARDINALITY_UNEXPECTED")
    row = data[0]
    if row.get("instType") != "SWAP" or row.get("instId") != symbol:
        raise ValueError("INSTRUMENT_ID_OR_VENUE_MISMATCH")
    if row.get("ctType") != "linear":
        raise ValueError("UNEXPECTED_NONLINEAR_CONTRACT")
    # Preserve every native spec string, including blank/missing values.
    spec = {name: row.get(name) for name in SPEC_KEYS}
    if any(v is not None and not isinstance(v, str) for v in spec.values()):
        raise ValueError("NATIVE_SPEC_FIELD_TYPE_CHANGED")
    required = ("ctVal", "ctMult", "ctValCcy", "settleCcy")
    complete = (positive_string(row.get("ctVal"))
                and positive_string(row.get("ctMult"))
                and all(isinstance(row.get(k), str) and row[k].strip()
                        for k in ("ctValCcy", "settleCcy")))
    list_time = row.get("listTime")
    if list_time not in (None, ""):
        if (not list_time.isdigit() or int(list_time) > received_ms
            or int(list_time) < 1500000000000):
            raise ValueError("INVALID_LISTING_TIME_NOT_HISTORICAL_SPEC")
    return {
        "symbol": symbol, "venue": "OKX", "market_type": "perpetual",
        "request_started_ms": started_ms, "response_received_ms": received_ms,
        "receipt_utc": utc(received_ms),
        "native_spec": spec,
        "native_spec_sha256": hashlib.sha256(canonical(spec)).hexdigest(),
        "current_spec_completeness": "COMPLETE_CURRENT_FIELDS" if complete else "PARTIAL_CURRENT_FIELDS",
        "ctVal_ctMult_ctValCcy_are_current_response_only": True,
        "historical_version_start_at": None,
        "historical_version_end_at": None,
        "history_effective_at_grade": "BLOCKED_NOT_PROVEN_BY_CURRENT_PUBLIC_INSTRUMENTS",
        "original_exchange_first_publication": "UNVERIFIED",
        "units_safe_for_historical_oi_or_flow_conversion": False,
        "causal_h1h10_rows_authorized": 0,
    }


def fetch_one(symbol):
    url = "https://www.okx.com" + ENDPOINT + "?" + urllib.parse.urlencode({
        "instType": "SWAP", "instId": symbol})
    request = urllib.request.Request(url, headers={
        "Accept": "application/json", "User-Agent": "H1H10-ResearchOnly-UnitReceipt/1.0"})
    started_ms = int(time.time() * 1000)
    with urllib.request.urlopen(request, timeout=15) as response:
        if response.status != 200:
            raise ValueError("HTTP_SOURCE_STATUS_NOT_200")
        raw = response.read(MAX_BYTES + 1)
        server_date = response.headers.get("Date")
    received_ms = int(time.time() * 1000)
    if len(raw) > MAX_BYTES:
        raise ValueError("HTTP_RESPONSE_SIZE_LIMIT")
    payload = json.loads(raw)
    parsed = extract(payload, symbol, started_ms, received_ms)
    parsed["source_endpoint"] = ENDPOINT
    parsed["server_http_date"] = server_date
    parsed["source_receipt_semantics"] = "ACTUAL_LOCAL_HTTP_RESPONSE_NOT_EXCHANGE_FIRST_RELEASE"
    return parsed, raw


def store_raw(s3, bucket, key, raw):
    if not (key.startswith(PREFIX + "/raw/") and key.endswith(".json")
            and isinstance(raw, bytes) and 0 < len(raw) <= MAX_BYTES):
        raise ValueError("RAW_SOURCE_WRITE_NOT_ALLOWED")
    sha = hashlib.sha256(raw).hexdigest()
    s3.put_object(Bucket=bucket, Key=key, Body=raw,
                  ContentType="application/json", Metadata={"sha256": sha})
    fetched = s3.get_object(Bucket=bucket, Key=key)
    if (fetched.get("Metadata", {}).get("sha256") != sha
        or hashlib.sha256(fetched["Body"].read(MAX_BYTES + 1)).hexdigest() != sha):
        raise ValueError("RAW_R2_READBACK_SHA_MISMATCH")
    return sha


def main():
    run = os.environ["GITHUB_RUN_ID"]
    attempt = os.environ.get("GITHUB_RUN_ATTEMPT", "1")
    if not (run.isdigit() and attempt.isdigit()):
        raise ValueError("UNTRUSTED_WORKFLOW_RUN_ID")
    bucket = os.environ["R2_BUCKET"]
    s3 = boto3.client(
        "s3", endpoint_url="https://" + os.environ["R2_ACCOUNT_ID"] + ".r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"], region_name="auto")
    reports = []
    for symbol in SYMBOLS:
        parsed, raw = fetch_one(symbol)
        source_key = PREFIX + "/raw/" + run + "-" + attempt + "-" + symbol + ".json"
        sha = store_raw(s3, bucket, source_key, raw)
        parsed["raw_r2_key"] = source_key
        parsed["raw_response_sha256"] = sha
        reports.append(parsed)
    manifest = {
        "schema": SCHEMA, "research_only": True, "trading_actions": False,
        "edge_status": "EDGE_UNVALIDATED", "github_run": run, "attempt": attempt,
        "scope": "THREE_OKX_USDT_PERPETUAL_INSTRUMENTS",
        "observed_source_responses": len(reports),
        "source_reports": reports,
        "new_historical_contract_spec_versions_verified": 0,
        "historical_contract_unit_handoff": "BLOCKED",
        "historical_first_release_pit": "UNVERIFIED",
        "causal_join_authorized": False, "training_authorized": False,
        "historical_confirmation": "BLOCKED",
        "current_response_is_not_historical_effective_from": True,
        "official_docs": "https://www.okx.com/docs-v5/en/",
    }
    path = PREFIX + "/manifests/" + run + "-" + attempt + ".json"
    digest = store(s3, bucket, path, manifest)
    print("H1H10_OKX_CURRENT_UNITS_RECEIPTS", json.dumps({
        "status": "SOURCE_RECEIPT_VERIFIED",
        "symbols": [x["symbol"] for x in reports],
        "source_shas": {x["symbol"]: x["raw_response_sha256"] for x in reports},
        "current_field_grades": {x["symbol"]: x["current_spec_completeness"] for x in reports},
        "r2_key": path, "sha256": digest,
        "historical_unit_versions_verified": 0, "causal_authorized": 0,
    }, ensure_ascii=False), flush=True)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as out:
            out.write("## OKX instrument receipt evidence — RESEARCH_ONLY\n\n")
            out.write("3 raw public responses SHA/readback verified. Historical units/PIT **BLOCKED**.\n\n")
            out.write(f"R2 key: \`{path}\`, SHA256: \`{digest}\`.\n")


if __name__ == "__main__":
    main()
