#!/usr/bin/env python3
"""H1-H10 research fastlane: immutable pinned evidence -> automatic readiness gates.

Daily, read-only decision process. No trading or workflow dispatch permissions.
Never promote source event labels / vendor receipts to original venue PIT or
a validated trading edge. Every source object must match pinned full SHA256.
"""
import datetime as dt,hashlib,json,os
from pathlib import Path
from research.detector_earliest_archive_byte_audit_v1 import r2,verify_r2
from research.detector_h1h10_join_readiness import summarize,verify_inventory_local_and_r2

OUT=Path("detector_h1h10_fastlane")
ROOT="research/detector-h1h10-fastlane/v1"
PINS={
 "joint_oi_source":{
  "key":"research/detector-h1h10-joint-oi-source-mask-2022-2026/v1/39377289885-1.json",
  "sha256":"1223ba344e7f0654f42ac7cb37a48b7a779b92a65689ca3183aaf446b2e29dd6",
  "schema":"detector-h1h10-2022-2026-joint-3coin-source-quality-register-v1"},
 "vendor_receipt_control":{
  "key":"research/detector-tardis-18-free-oi-asof-5m/v1/39298935123-1.json",
  "sha256":"REPLACE_FROM_VERIFIED_RECORD_ONLY",
  "schema":"detector-h1h10-tardis-18-free-oi-asof-5m-v1"}
}
# Vendor control is optional until its exact immutable SHA is registered.
# Never fetch or claim anything for it based on a guessed key/hash.
PINS.pop("vendor_receipt_control")

def evaluate(verified):
    source=verified["joint_oi_source"]
    if (source.get("schema")!=PINS["joint_oi_source"]["schema"] or
        source.get("joint_full_days")!=1734 or
        source.get("total_calendar_days")!=1750 or
        source.get("joint_excluded_days")!=16 or
        source.get("data_cutoff_last_day")!="2026-10-16" or
        source.get("edge_status")!="EDGE_UNVALIDATED" or
        not source.get("research_only") or
        source.get("pit_release_timestamp")!="UNVERIFIED"):
        raise ValueError("JOINT_SOURCE_VERIFIED_ASSERTIONS_FAILED")
    levels={"original_source_quality":"PASS",
      "source_5m_numeric_completeness":"PASS_WITH_16_EXCLUDED_DATES",
      "venue_original_first_publication":"UNVERIFIED",
      "collector_first_seen_continuity":"UNVERIFIED",
      "historical_price_flow_join":"INSUFFICIENT_CAUSAL_COVERAGE",
      "units_spot_perp_contract_parity":"NOT_ALL_VERIFIED",
      "locked_holdout_eligibility":"BLOCKED",
      "h1_h10_confirmatory":"BLOCKED",
      "production_trading":"PROHIBITED"}
    blockers=[
      {"id":"PIT_PUBLICATION","status":"BLOCKED","required":"Independent actual original exchange release or vendor-receipt/collector asof per required field with measured lag. A source event label alone is not enough."},
      {"id":"JOINT_PRICE_FLOW","status":"BLOCKED","required":"Same-venue BTC ETH SOL historical price/flow and source-first-available timestamps, exact gaps and units, before each 5m decision cutoff."},
      {"id":"PIT_HOLDOUT","status":"BLOCKED","required":"Freeze unaffected holdout days and matched price/flow/OI; no retrospective retuning; source-quality calendar cannot stand in for point-in-time."},
      {"id":"COSTS_AND_DETECTOR_A","status":"BLOCKED","required":"True historical detector A asof or A_MISSING, exchange fees, spread, slippage, funding and capacity."}]
    return {"pipeline_gates":levels,"blocking_dependencies":blockers,
      "next_priority":"PIT_AND_PRICE_FLOW_SOURCE_INVENTORY",
      "permitted_automatic_actions":["SOURCE_REPORT_AUDIT","READ_ONLY_INVENTORY","ARCHIVE_VALIDATION"],
      "forbidden_automatic_actions":["PAID_SUBSCRIPTION","PROXY_BYPASS","HOLDOUT_TUNING",
                                     "PRODUCTION_DETECTOR_ACTIVATION","TRADE_ORDER","PORTFOLIO_WRITEBACK"],
      "ready_for_confirmatory_h1_h10":False,"ready_for_trading":False}

def assemble(verified,inventory=None,inventory_proof=None):
    result=evaluate(verified)
    source=verified["joint_oi_source"]
    extra={}
    if inventory is not None:
        if inventory_proof is None:raise ValueError("INVENTORY_PROOF_REQUIRED")
        extra={"verified_source_inventory":inventory_proof,
            "price_oi_flow_overlap_audit":summarize(inventory)}
    return {"schema":"detector-h1h10-research-fastlane-readiness-v1",
      "source_evidence":PINS,
      "source_quality_days":source["total_calendar_days"],
      "source_joint_usable_days":source["joint_full_days"],
      "excluded_source_days":source["joint_excluded_days"],
      "source_cutoff_utc":source["data_cutoff_last_day"],
      "source_coverage_not_causal_pit":True,
      "status":"RESEARCH_PARTIAL_BLOCKED_NOT_EDGE",
      "edge_status":"EDGE_UNVALIDATED",
      "research_only":True,
      "spot_futures_nav_pnl_reserve_limits_unchanged":True,**result,**extra}

def stable_gate_state(core):
    """Content-address actual evidence status, not the daily inventory run ID.

    Every daily inventory has its own separate signed R2 run key and SHA;
    retaining that per-run provenance in the local artifact but removing it
    from the stable gate-state fingerprint prevents false NEW EVIDENCE alerts.
    """
    frozen=dict(core)
    frozen.pop("verified_source_inventory",None)
    frozen.pop("okx_forward_three_metric_receipts",None)
    return frozen

def main():
    OUT.mkdir(exist_ok=True)
    client=r2();bucket=os.environ["R2_BUCKET"]
    seen={}
    for name,pin in PINS.items():
        if len(pin["sha256"])!=64:
            raise ValueError("UNPINNED_REQUIRED_SOURCE_SHA")
        source=verify_r2(client,bucket,pin["key"],pin["sha256"],2_000_000)
        seen[name]=json.loads(source)
        print("FASTLANE_SHA_SOURCE_CHECK",json.dumps({"name":name,"sha256":pin["sha256"]}),flush=True)
    inventory,inventory_proof=verify_inventory_local_and_r2(
        "detector_h1h10_evidence_inventory/inventory.json",client,bucket,verify_r2)
    core=assemble(seen,inventory=inventory,inventory_proof=inventory_proof)
    receipt_path=OUT/"okx_three_metric_receipt_audit.json"
    if not receipt_path.is_file():
        raise ValueError("MISSING_AUTOMATED_THREE_METRIC_RECEIPT_AUDIT")
    receipt=json.loads(receipt_path.read_text(encoding="utf-8"))
    if (receipt.get("scope")!="RESEARCH_ONLY"
        or receipt.get("edge_status")!="EDGE_UNVALIDATED"
        or receipt.get("continuous_5m_pit_grade")!="UNVERIFIED"
        or receipt.get("historical_h1h10_confirmation")!="BLOCKED"
        or receipt.get("trading_actions") is not False
        or not isinstance(receipt.get("sha256"),str)
        or len(receipt["sha256"])!=64):
        raise ValueError("THREE_METRIC_AUDIT_MISREPRESENTS_PIT")
    # This dynamic prospective receipt counter is attached to this run's
    # artifact, but excluded from content-addressed historical gate state.
    core["okx_forward_three_metric_receipts"]={
        "r2_key":receipt["r2_key"],"sha256":receipt["sha256"],
        "reports":receipt["reports"],
        "raw_sha_verified":receipt["raw_sha_verified"],
        "legacy_raw_pin_missing":receipt["legacy_streams_missing_raw_pin"],
        "observed_gaps_over_20m":receipt["gaps_over_20_minutes"],
        "causal_5m_eligibility":"UNVERIFIED",
        "trading_actions":False}
    print("FASTLANE_VERIFIED_PRICE_FLOW_OI_INVENTORY",json.dumps({
        "key":inventory_proof["key"],"sha256":inventory_proof["sha256"],
        "date_only_overlap":core["price_oi_flow_overlap_audit"]["vendor_oi_and_event_flow_date_coincidences"],
        "causal_joint_rows":core["price_oi_flow_overlap_audit"]["causal_5m_features_eligible_for_locked_holdout"]
    },ensure_ascii=False),flush=True)
    # Deterministic key for state comparison: don't invent change or alerts each day.
    state_blob=json.dumps(stable_gate_state(core),ensure_ascii=False,sort_keys=True).encode()
    fingerprint=hashlib.sha256(state_blob).hexdigest()
    key=f"{ROOT}/evidence-{fingerprint}.json"
    # Fixed content object is idempotent: reruns do not overwrite with a new timestamp.
    try:
        obj=client.get_object(Bucket=bucket,Key=key)
        stored=obj["Body"].read(3_000_000)
        if stored!=state_blob or hashlib.sha256(stored).hexdigest()!=fingerprint:
            raise ValueError("EXISTING_FASTLANE_STATE_HASH_CHANGED")
        changed=False
    except client.exceptions.NoSuchKey:
        client.put_object(Bucket=bucket,Key=key,Body=state_blob,
            ContentType="application/json",Metadata={"sha256":fingerprint})
        obj=client.get_object(Bucket=bucket,Key=key)
        if obj["Body"].read(len(state_blob)+1)!=state_blob:
            raise ValueError("FASTLANE_R2_SOURCE_READBACK_MISMATCH")
        changed=True
    if changed:
        print("FASTLANE_GATE_STATE_CHANGED",json.dumps({"state_key":key,"fingerprint":fingerprint}),flush=True)
    else:
        print("FASTLANE_GATE_STATE_UNCHANGED",json.dumps({"state_key":key,"fingerprint":fingerprint}),flush=True)
    (OUT/"status.json").write_text(json.dumps({**core,"r2_state_key":key,
         "sha256":fingerprint,"new_state":changed},indent=2,ensure_ascii=False),encoding="utf-8")
    print("H1H10_FASTLANE_READINESS",json.dumps({
        "source":"PASS","joint_source_days":1734,"pit":"UNVERIFIED",
        "joint_flow":"BLOCKED","holdout":"BLOCKED","edge":"EDGE_UNVALIDATED",
        "new_evidence_state":changed,"r2_key":key,"sha256":fingerprint,
        "inventory_r2_key":inventory_proof["key"],"inventory_sha256":inventory_proof["sha256"],
        "date_only_overlaps":core["price_oi_flow_overlap_audit"]["vendor_oi_and_event_flow_date_coincidences"],
        "causal_joint_rows":0},ensure_ascii=False),flush=True)
    summary=os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary,"a",encoding="utf-8") as f:
            f.write("## H1-H10 Fastlane readiness (read only)\n\n")
            f.write("- Source-quality history: **PASS 1734/1750**\n")
            f.write("- Original first publication/PIT: **UNVERIFIED**\n")
            f.write("- Joint historical price/flow asof: **BLOCKED**\n")
            f.write("- Confirmatory H1-H10, trades: **BLOCKED**\n")
            f.write(f"- Same evidence as previous run: **{not changed}**\n")
            f.write(f"- R2 immutable state: \`{key}\`\n")
if __name__=="__main__":
    main()
