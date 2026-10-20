#!/usr/bin/env python3
"""RESEARCH_ONLY: receipt-aware same-venue source-label candidates, NEVER PIT training.

Read SHA-pinned R2 manifests and all nine raw polls with independent R2 metadata
readback. Source-label equality is diagnostic only: OKX OI and taker bar-anchor
semantics, first-publication timestamps and historical contract units remain
UNVERIFIED. No synthetic 5m observations, historic availability or trade actions.
"""
import datetime as dt
import json
import os
import time

from research.detector_okx_3metric_forward_48h import (
    METRICS, P5, PREFIX, SCHEMA, SYMBOLS,
)
from research.detector_okx_3metric_receipt_audit import (
    MAX_RUN_REPORTS, check_one, verified_json,
)
from research.detector_okx_oi_48h_pilot import store

OUTPUT_PREFIX = "research/detector-okx-3metric-receipt-candidates/v1"
EXPECTED_ENDPOINTS = {
    "oi": "/api/v5/rubik/stat/contracts/open-interest-history",
    "price": "/api/v5/market/candles",
    "flow": "/api/v5/rubik/stat/taker-volume-contract",
}
HEX = frozenset("0123456789abcdef")


def _sha(value):
    return isinstance(value, str) and len(value) == 64 and set(value) <= HEX


def _identity(poll, symbol, metric, proof, check_ms):
    if (not isinstance(poll, dict)
        or poll.get("schema") != SCHEMA
        or poll.get("metric") != metric
        or poll.get("symbol") != symbol
        or poll.get("provider") != "OKX"
        or poll.get("research_only") is not True
        or poll.get("receipt_semantics") != "LOCAL_HTTP_RESPONSE_OBSERVED_NOT_EXCHANGE_PUBLICATION"
        or poll.get("source_endpoint") != EXPECTED_ENDPOINTS[metric]):
        raise ValueError("SAME_VENUE_SOURCE_IDENTITY_MISSING")
    received = poll.get("response_received_ms")
    started = poll.get("request_start_ms")
    if (not isinstance(received, int) or not isinstance(started, int)
        or started > received or received > check_ms or started < 1600000000000):
        raise ValueError("FUTURE_OR_INVALID_HTTP_RECEIPT")
    if (not isinstance(proof, dict)
        or proof.get("response_received_ms") != received
        or proof.get("row_count") != len(poll.get("rows", []))
        or not _sha(proof.get("raw_sha256"))
        or not isinstance(proof.get("raw_r2_key"), str)
        or not proof["raw_r2_key"].startswith(PREFIX + "/polls/")):
        raise ValueError("RAW_R2_MANIFEST_PROOF_MISSING")
    rows = poll["rows"]
    if not isinstance(rows, list) or not (1 <= len(rows) <= 100):
        raise ValueError("SOURCE_ROW_COUNT_UNVERIFIED")
    seen = set()
    for row in rows:
        label = row.get("label_ms")
        if (not isinstance(label, int) or label % P5
            or label in seen or label > received + 60000
            or not _sha(row.get("raw_sha256"))
            or not isinstance(row.get("data"), dict)):
            raise ValueError("LABEL_OR_ROW_SHA_INVALID")
        seen.add(label)
        d = row["data"]
        if metric == "price":
            if (d.get("source_bar_open_ms") != label
                or d.get("source_bar_nominal_end_ms") != label + P5
                or d.get("confirm") not in ("0", "1")):
                raise ValueError("CANDLE_ANCHOR_OR_CONFIRM_MISSING")
        elif metric == "flow":
            if (d.get("side_order") != "SELL_THEN_BUY"
                or d.get("requested_unit") != "1"
                or d.get("bucket_anchor_time_semantics") != "UNVERIFIED_BY_SOURCE_RELEASE"
                or "sell_native" not in d or "buy_native" not in d):
                raise ValueError("FLOW_UNIT_OR_ANCHOR_PROMOTED")
        else:
            if (d.get("units") != "NATIVE_OI_INSTRUMENT_SIZE_UNVERIFIED"
                or d.get("bucket_anchor_time_semantics") != "UNVERIFIED_BY_SOURCE_RELEASE"
                or "native_open_interest" not in d):
                raise ValueError("OI_UNIT_OR_ANCHOR_PROMOTED")
    return {x["label_ms"]: x for x in rows}


def diagnose(report, raw_polls, candidate_check_at_ms):
    """Return fail-closed RECEIPT-AWARE CANDIDATES; training authorization is zero."""
    if (not isinstance(candidate_check_at_ms, int)
        or candidate_check_at_ms < 1600000000000
        or report.get("schema") != SCHEMA
        or report.get("scope") != "RESEARCH_ONLY"
        or report.get("trading_actions") is not False
        or report.get("status") != "SOURCES_ALL_RECEIVED"
        or report.get("original_exchange_first_publication") != "UNVERIFIED"
        or report.get("causal_join_training") != "BLOCKED"
        or report.get("edge_status") != "EDGE_UNVALIDATED"):
        raise ValueError("PIT_AUTHORITY_OR_SCOPE_MISMATCH")
    proofs = report.get("source_reports")
    if not isinstance(proofs, dict) or len(proofs) != 9 or len(raw_polls) != 9:
        raise ValueError("ALL_NINE_SOURCES_REQUIRED")
    diagnostic = {}
    for symbol in SYMBOLS:
        maps = {}
        for metric in METRICS:
            name = symbol + "|" + metric
            if name not in proofs or name not in raw_polls:
                raise ValueError("MISSING_SOURCE_FOR_SAME_VENUE_JOIN")
            maps[metric] = _identity(raw_polls[name], symbol, metric, proofs[name],
                                     candidate_check_at_ms)
        overlap = sorted(set.intersection(*(set(maps[m]) for m in METRICS)))
        original = report.get("coverage_gate", {}).get(symbol)
        if (not isinstance(original, dict)
            or original.get("source_label_triples") != len(overlap)
            or original.get("causal_5m_rows_authorized") != 0
            or original.get("training_authorized") is not False
            or original.get("join_grade") != "SOURCE_LABEL_OVERLAP_ONLY_NO_CAUSAL_PIT"):
            raise ValueError("COLLECTOR_SOURCE_LABEL_COUNT_OR_PIT_PROMOTED")
        rows = []
        rejected = {"receipt_after_cutoff": 0, "nominal_end_after_cutoff": 0,
                    "price_bar_unconfirmed": 0}
        for label in overlap:
            values = {m: maps[m][label] for m in METRICS}
            if any(raw_polls[symbol + "|" + m]["response_received_ms"] > candidate_check_at_ms
                   for m in METRICS):
                rejected["receipt_after_cutoff"] += 1
                continue
            # Over-conservative diagnostic cutoff even when OI/flow anchor is
            # unknown; NEVER infer an actual exchange release from this rule.
            if label + P5 > candidate_check_at_ms:
                rejected["nominal_end_after_cutoff"] += 1
                continue
            if values["price"]["data"]["confirm"] != "1":
                rejected["price_bar_unconfirmed"] += 1
                continue
            rows.append({
                "source_label_ms": label,
                "price_nominal_end_ms": label + P5,
                "row_sha256_by_metric": {m: values[m]["raw_sha256"] for m in METRICS},
                "raw_poll_sha256_by_metric": {m: proofs[symbol + "|" + m]["raw_sha256"]
                                             for m in METRICS},
                "http_response_received_ms_by_metric": {
                    m: raw_polls[symbol + "|" + m]["response_received_ms"]
                    for m in METRICS},
                "status": "JOIN_CANDIDATE_ONLY",
            })
        diagnostic[symbol] = {
            "raw_source_label_triples": len(overlap),
            "cutoff_passed_candidates": len(rows),
            "rejected": rejected,
            "rows": rows,
            "quality_status": "JOIN_CANDIDATE_ONLY",
            "causal_rows_authorized": 0,
        }
    return {
        "schema": "detector-h1h10-okx-receipt-candidate-only-v1",
        "scope": "RESEARCH_ONLY",
        "edge_status": "EDGE_UNVALIDATED",
        "trading_actions": False,
        "collector_run": report["run"],
        "collector_attempt": report["attempt"],
        "candidate_check_at_ms": candidate_check_at_ms,
        "venue": "OKX",
        "market_type": "USDT_PERPETUAL_ONLY",
        "bar_size_ms": P5,
        "observed_clock_basis": "ACTUAL_COLLECTOR_HTTP_RESPONSE_RECEIPT",
        "unknown_oi_flow_source_label_anchor": True,
        "unknown_exchange_first_publication": True,
        "historical_instrument_units_verified": False,
        "no_synthetic_or_interpolated_buckets": True,
        "training_authorized": False,
        "causal_rows_authorized": 0,
        "historical_confirmatory_status": "BLOCKED",
        "candidates": diagnostic,
    }


def main():
    import boto3
    bucket = os.environ["R2_BUCKET"]
    s3 = boto3.client(
        "s3",
        endpoint_url="https://" + os.environ["R2_ACCOUNT_ID"] + ".r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )
    root = PREFIX + "/run-reports/"
    keys = []
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=root):
        keys.extend(x["Key"] for x in page.get("Contents", []) if x["Key"].endswith(".json"))
        if len(keys) > MAX_RUN_REPORTS:
            raise ValueError("PILOT_REPORT_SAFETY_CAP_EXCEEDED")
    if not keys:
        raise ValueError("PILOT_REPORTS_MISSING")
    # Run IDs are monotonically allocated by GitHub, while attempts may repeat.
    key = max(keys, key=lambda k: tuple(int(x) for x in
              k.rsplit("/", 1)[1].removesuffix(".json").split("-")))
    report = verified_json(s3, bucket, key)
    verified, legacy = check_one(s3, bucket, report, verify_raw=True)
    if verified != 9 or legacy:
        raise ValueError("NINE_RAW_SHA_READBACKS_REQUIRED")
    raw_polls = {
        name: verified_json(s3, bucket, proof["raw_r2_key"], proof["raw_sha256"])
        for name, proof in report["source_reports"].items()
    }
    candidate_check_at_ms = int(time.time() * 1000)
    result = diagnose(report, raw_polls, candidate_check_at_ms)
    result["source_report_r2_key"] = key
    result["source_report_raw_sha_readback_count"] = verified
    result["source_report_sha_provenance"] = "R2_METADATA_AND_RAW_LINKED_OBJECTS_VERIFIED"
    result["not_exchange_first_release"] = True
    run_id = os.environ["GITHUB_RUN_ID"]
    attempt = os.environ.get("GITHUB_RUN_ATTEMPT", "1")
    out_key = OUTPUT_PREFIX + "/" + run_id + "-" + attempt + ".json"
    digest = store(s3, bucket, out_key, result)  # Write, R2 read back and compare.
    counts = {s: r["cutoff_passed_candidates"] for s, r in result["candidates"].items()}
    output = {"r2_key": out_key, "sha256": digest, "verified_raw_sha": verified,
              "source_run": report["run"], "candidate_counts": counts,
              "causal_authorized": 0, "confirmatory": "BLOCKED"}
    print("H1H10_RECEIPT_JOIN_CANDIDATE_ONLY", json.dumps(output), flush=True)
    local = "detector_h1h10_fastlane"
    os.makedirs(local, exist_ok=True)
    with open(local + "/okx_receipt_candidate.json", "w", encoding="utf-8") as fp:
        json.dump({**result, "r2_key": out_key, "sha256": digest},
                  fp, indent=2, ensure_ascii=False)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fp:
            fp.write("## H1H10 receipt-aware same-venue candidate-only audit\n\n")
            fp.write(f"9/9 source SHA readback: PASS. Candidate counts: {counts}.\n\n")
            fp.write("**Causal rows authorized: 0. Locked holdout: BLOCKED.**\n\n")
            fp.write(f"R2 key: \`{out_key}\`, SHA256: \`{digest}\`.\n")


if __name__ == "__main__":
    main()
