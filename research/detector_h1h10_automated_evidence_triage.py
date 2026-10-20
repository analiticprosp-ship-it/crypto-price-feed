#!/usr/bin/env python3
"""RESEARCH_ONLY: automatic evidence-first research triage, not strategy automation.

Consumes one SHA-verified pinned inventory and independently validated
clock-compatibility audit. Emits a deterministic prioritized work queue with
missing proofs; DOES NOT fetch protected data, dispatch experiments, reclassify
historical rows, train models, execute trades, or alter prereg/holdout.
"""
import hashlib
import json
import os
from pathlib import Path

from research.detector_earliest_archive_byte_audit_v1 import r2, verify_r2
from research.detector_h1h10_join_readiness import summarize, verify_inventory_local_and_r2

PREFIX = "research/detector-h1h10-automated-evidence-triage/v1"
OUTPUT = Path("detector_h1h10_fastlane/automated_evidence_triage.json")
ORDER = ("H1", "H6", "H7", "H2")
PERMITTED = ("VERIFY_ARCHIVED_SOURCES", "RECONCILE_SOURCE_CLOCKS",
             "BUILD_DISCOVERY_ONLY_CANDIDATES", "PLAN_BOUNDED_FREE_SOURCE_PILOT")
FORBIDDEN = ("RUN_LOCKED_HOLDOUT", "PROMOTE_PIT_FROM_EVENT_LABEL",
             "EXECUTE_TRADE", "MODIFY_PORTFOLIO", "BUY_DATA",
             "CREATE_PAID_INFRASTRUCTURE", "RETROFIT_FIRST_PUBLICATION")


def make_plan(readiness):
    """Fail-closed priority queue; status labels are assertions, not trade signals."""
    if (not isinstance(readiness, dict)
        or readiness.get("edge_status") != "EDGE_UNVALIDATED"
        or readiness.get("scope") != "PINNED_SOURCE_INVENTORY_ONLY"
        or readiness.get("holdout_and_model_training_authorized") is not False
        or readiness.get("flow_publication_evidence") != "UNVERIFIED"
        or readiness.get("exchange_first_publication_evidence") != "UNVERIFIED"
        or readiness.get("causal_5m_features_eligible_for_locked_holdout") != 0
        or readiness.get("clock_compatible_full_joint_asset_market_days") != 0):
        raise ValueError("TRIAGE_CANNOT_UPGRADE_PIT_OR_EDGE")
    oi = readiness.get("tardis_oi_vendor_receipt_full_asset_days")
    trade = readiness.get("binance_trade_event_full_asset_market_days")
    coincidences = readiness.get("vendor_oi_and_event_flow_date_coincidences")
    if (type(oi) is not int or type(trade) is not int
        or type(coincidences) is not int
        or not 0 <= oi <= 21 or not 0 <= trade <= 18
        or not 0 <= coincidences <= min(oi * 2, trade)):
        raise ValueError("TRIAGE_SOURCE_COUNTS_INVALID")
    source = {
        "vendor_asof_oi_price_asset_days": oi,
        "event_only_spot_perp_trade_asset_market_days": trade,
        "date_only_overlaps": coincidences,
        "causal_5m_joint_rows": 0,
        "original_exchange_first_publication": "UNVERIFIED",
    }
    tasks = [
        {
            "id": "H1",
            "rank": 1,
            "objective": "Spot taker flow vs price-only for 15m direction",
            "ready": False,
            "gate": "SPOT_FLOW_FIRST_AVAILABLE_AND_SPOT_PRICE_ASOF_MISSING",
            "existing_evidence": "BINANCE_AGGTRADES_EVENT_TIME_ONLY",
            "next_action": "Acquire same-venue Spot price and taker receipts/PIT proof for a bounded 7-14-day pilot; source-label joins are discovery-only.",
            "allowed_mode_now": "SOURCE_AUDIT_AND_DISCOVERY_ONLY",
        },
        {
            "id": "H6",
            "rank": 2,
            "objective": "Spot vs perp trade-flow lead/lag with causal cutoffs",
            "ready": False,
            "gate": "SPOT_PERP_FLOW_FIRST_AVAILABLE_UNVERIFIED",
            "existing_evidence": "SAME_VENUE_BINANCE_SPOT_PERP_EVENT_ONLY",
            "next_action": "Audit Spot and perp per-trade first-availability clocks, common UTC intervals and unit parity; never infer lead from event labels.",
            "allowed_mode_now": "SOURCE_AUDIT_AND_DISCOVERY_ONLY",
        },
        {
            "id": "H7",
            "rank": 3,
            "objective": "Flow/price divergence before 15m spot reversal",
            "ready": False,
            "gate": "PRICE_FLOW_CAUSAL_SAME_VENUE_JOIN_MISSING",
            "existing_evidence": "DATE_ONLY_COINCIDENCES_NOT_CAUSAL",
            "next_action": "Reuse H1 source evidence; freeze divergence threshold on train-only, do not evaluate on locked holdout.",
            "allowed_mode_now": "SOURCE_AUDIT_AND_DISCOVERY_ONLY",
        },
        {
            "id": "H2",
            "rank": 4,
            "objective": "Incremental OI after price and active-buying flow",
            "ready": False,
            "gate": "OI_FLOW_PRICE_CLOCK_AND_HISTORICAL_UNIT_VERSIONS_MISSING",
            "existing_evidence": "TARDIS_VENDOR_ASOF_OI_AND_EVENT_ONLY_FLOW",
            "next_action": "Before ablation, require same-venue OI/price/taker first-available and effective historical native contract units.",
            "allowed_mode_now": "SOURCE_AUDIT_AND_DISCOVERY_ONLY",
        },
    ]
    if tuple(x["id"] for x in tasks) != ORDER:
        raise ValueError("TRIAGE_PREREG_HYPOTHESIS_ORDER_CHANGED")
    return {
        "schema": "detector-h1h10-automated-evidence-priority-v1",
        "scope": "RESEARCH_ONLY",
        "research_hypotheses_prioritized": list(ORDER),
        "priority_order_is_not_new_confirmatory_hypothesis_family": True,
        "source_inventory": source,
        "tasks": tasks,
        "research_jobs_automatically_unblocked": 0,
        "causal_5m_rows_authorized": 0,
        "holdout_training_authorized": False,
        "confirmatory_h1_h10": "BLOCKED",
        "edge_status": "EDGE_UNVALIDATED",
        "permitted_automatic_actions": list(PERMITTED),
        "forbidden_automatic_actions": list(FORBIDDEN),
        "trading_actions": False,
        "new_paid_sources": False,
    }


def verify_no_escalation(plan):
    if (plan.get("trading_actions") is not False
        or plan.get("holdout_training_authorized") is not False
        or plan.get("causal_5m_rows_authorized") != 0
        or plan.get("edge_status") != "EDGE_UNVALIDATED"
        or plan.get("confirmatory_h1_h10") != "BLOCKED"
        or plan.get("new_paid_sources") is not False
        or plan.get("research_jobs_automatically_unblocked") != 0
        or tuple(t.get("id") for t in plan.get("tasks", ())) != ORDER
        or any(t.get("ready") is not False for t in plan["tasks"])):
        raise ValueError("TRIAGE_TRAINING_OR_TRADING_AUTHORITY_FORBIDDEN")
    return True


def main():
    client = r2()
    bucket = os.environ["R2_BUCKET"]
    inv, provenance = verify_inventory_local_and_r2(
        "detector_h1h10_evidence_inventory/inventory.json",
        client, bucket, verify_r2)
    validated = summarize(inv)
    plan = make_plan(validated)
    verify_no_escalation(plan)
    run = os.environ["GITHUB_RUN_ID"]
    attempt = os.environ.get("GITHUB_RUN_ATTEMPT", "1")
    if not run.isdigit() or not attempt.isdigit():
        raise ValueError("TRIAGE_RUN_ID_INVALID")
    result = {
        **plan,
        "inventory_provenance": provenance,
        "github_run_id": run,
        "github_attempt": attempt,
        "frozen_holdout_consumed": False,
        "private_source_rows_exported": False,
    }
    data = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
    digest = hashlib.sha256(data).hexdigest()
    key = PREFIX + "/" + run + "-" + attempt + ".json"
    client.put_object(Bucket=bucket, Key=key, Body=data,
                      ContentType="application/json", Metadata={"sha256": digest})
    reread = client.get_object(Bucket=bucket, Key=key)
    body = reread["Body"].read(len(data) + 1)
    if (body != data or hashlib.sha256(body).hexdigest() != digest
        or reread.get("Metadata", {}).get("sha256") != digest):
        raise ValueError("TRIAGE_IMMUTABLE_R2_SHA_READBACK_FAILED")
    OUTPUT.parent.mkdir(exist_ok=True, parents=True)
    OUTPUT.write_text(json.dumps({**result, "r2_key": key, "sha256": digest},
                                 ensure_ascii=False, indent=2), encoding="utf-8")
    print("H1H10_AUTOMATED_RESEARCH_TRIAGE", json.dumps({
        "priority": list(ORDER),
        "verified_oi_asset_days": plan["source_inventory"]["vendor_asof_oi_price_asset_days"],
        "event_only_flow_asset_market_days": plan["source_inventory"]["event_only_spot_perp_trade_asset_market_days"],
        "date_only_overlaps": plan["source_inventory"]["date_only_overlaps"],
        "causal_authorized": 0,
        "holdout": "BLOCKED",
        "r2_key": key,
        "sha256": digest,
    }, ensure_ascii=False), flush=True)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as fp:
            fp.write("## H1-H10 autonomous evidence triage (no experiment dispatch)\n\n")
            fp.write("Priority: H1 → H6 → H7 → H2. Evidence-only automatic work; no new causal rows.\n\n")
            fp.write(f"SHA-pinned R2: {key}, SHA256: {digest}.\n")


if __name__ == "__main__":
    main()
