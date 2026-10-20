"""Fail-closed H1-H10 co-coverage audit of independently SHA-pinned R2 inventory.

No lookahead: a vendor's recorded receipt of OI on a day does NOT prove
that a separately archived aggTrades file was released at a decision cutoff.
This tool only inventories overlap; it does not join rows into causal features.
"""
import json
from pathlib import Path

COINS=frozenset(("BTCUSDT","ETHUSDT","SOLUSDT"))
TARDIS="open_interest_plus_last_price"
FLOW="taker_aggtrades_5m"
SCHEMA="detector-h1h10-real-evidence-inventory-v1"

def summarize(inventory):
    if (not isinstance(inventory,dict)
        or inventory.get("schema")!=SCHEMA
        or inventory.get("edge_status")!="EDGE_UNVALIDATED"
        or inventory.get("research_only") is not True
        or inventory.get("trading_actions") is not False):
        raise ValueError("UNTRUSTED_OR_LIVE_SOURCE_INVENTORY")
    rows=inventory.get("rows")
    if not isinstance(rows,list) or len(rows)!=39:
        raise ValueError("SOURCE_ROW_COUNT_UNEXPECTED")
    oi={};flows={};dates=set()
    for row in rows:
        if not isinstance(row,dict) or row.get("symbol") not in COINS:
            raise ValueError("ROW_SYMBOL_OR_TYPE_INVALID")
        day=row.get("date_start_utc")
        if not isinstance(day,str) or day!=row.get("date_end_utc"):
            raise ValueError("ROW_DATE_RANGE_INVALID")
        try:
            import datetime as dt
            dt.date.fromisoformat(day)
        except (TypeError,ValueError) as exc:
            raise ValueError("INVALID_SOURCE_UTC_DAY") from exc
        dates.add(day)
        metric=row.get("dataset")
        if (not isinstance(row.get("rows"),int) or not isinstance(row.get("expected_rows"),int)
            or row["rows"]<0 or row["expected_rows"]!=288
            or not isinstance(row.get("missing_intervals"),int)
            or row["missing_intervals"]<0
            or row["missing_intervals"]>288):
            raise ValueError("UNTRUSTED_FIVE_MINUTE_BUCKET_COUNTS")
        if not isinstance(row.get("source_sha256"),str) or len(row["source_sha256"])!=64:
            raise ValueError("SOURCE_HASH_MISSING")
        if metric==TARDIS:
            k=(day,row["symbol"])
            if k in oi:raise ValueError("DUPLICATE_OI_DAY_COIN")
            if row.get("market_type")!="perpetual" or "Tardis" not in row.get("venue",""):
                raise ValueError("OI_VENUE_PROVENANCE_MISMATCH")
            if row.get("time_basis")!="vendor_receipt_asof_not_exchange_publication":
                raise ValueError("OI_AVAILABILITY_CLOCK_SEMANTICS_CHANGED")
            if row.get("availability_status")!="VENDOR_RECEIPT_VERIFIED_EXCHANGE_PUBLICATION_UNVERIFIED":
                raise ValueError("OI_EXCHANGE_PUBLICATION_CLAIM_INVALID")
            oi[k]=row
        elif metric==FLOW:
            market=row.get("market_type")
            k=(day,row["symbol"],market)
            if market not in ("spot","perp") or k in flows:raise ValueError("DUPLICATE_FLOW_OR_MARKET")
            if row.get("venue")!="Binance" or row.get("time_basis")!="trade_event_time_only_not_first_publication":
                raise ValueError("FLOW_EVENT_VS_AVAILABILITY_CONFUSION")
            if row.get("availability_status")!="AGGTRADES_PUBLICATION_UNVERIFIED":
                raise ValueError("FLOW_AVAILABILITY_UNEXPECTED")
            flows[k]=row
        else:
            raise ValueError("UNKNOWN_SOURCE_IN_INVENTORY")
    if len(oi)!=21 or len(flows)!=18:raise ValueError("SOURCE_SHAPES_MISSING")
    vendor_asof_oi={(d,s) for (d,s),r in oi.items()
                    if r.get("status")=="VERIFIED_VENDOR_RECEIPT_ONLY"
                    and r["rows"]-r["missing_intervals"]==288}
    event_only_flow={(d,s,m) for (d,s,m),r in flows.items()
                     if r.get("status")=="VERIFIED_EVENT_TIME_ONLY"
                     and r["rows"]-r["missing_intervals"]==288}
    overlap=sorted({(d,s,m) for (d,s,m) in event_only_flow if (d,s) in vendor_asof_oi})
    # These sets overlap in calendar/event labels, not in proven release-time availability.
    # Prospective runner timestamp observations are real receipts, but GitHub
    # cron cadence is not guaranteed. Record observed gaps; never infer 5m
    # contiguity from a 5m *configured schedule*.
    import math
    aggregate=inventory.get("summary")
    if not isinstance(aggregate,dict):raise ValueError("PROSPECTIVE_SUMMARY_MISSING")
    okx=aggregate.get("okx")
    if not isinstance(okx,dict):raise ValueError("PROSPECTIVE_OKX_REPORT_MISSING")
    reports=okx.get("report_objects_read")
    failures=okx.get("gaps_observed_gt_10_minutes")
    median=okx.get("median_actual_gap_seconds")
    maximum=okx.get("max_actual_gap_seconds")
    if (not isinstance(reports,int) or reports<0 or
        not isinstance(failures,int) or failures<0 or failures>max(0,reports-1)):
        raise ValueError("PROSPECTIVE_GAP_COUNTS_INVALID")
    if reports>1:
        if (not isinstance(median,(int,float)) or not isinstance(maximum,(int,float))
            or not math.isfinite(median) or not math.isfinite(maximum)
            or median<0 or maximum<median):
            raise ValueError("PROSPECTIVE_RECEIPT_GAP_INVALID")
    cadence="NO_ACTUAL_PROSPECTIVE_OBSERVATION" if reports==0 else (
        "INSUFFICIENT_TO_EVALUATE_GAPS" if reports==1 else (
        "OBSERVED_GAPS_GT_10MIN" if failures>0 else
        "UNVERIFIED_5M_CONTINUITY_DESPITE_SAMPLES"))
    values={
        "inventory_source_row_count":len(rows),
        "okx_actual_poll_reports_read":reports,
        "okx_observed_gaps_over_10m":failures,
        "okx_median_observed_spacing_seconds":median,
        "okx_max_observed_spacing_seconds":maximum,
        "five_minute_continuous_first_seen_grade":cadence,
        "five_minute_first_seen_pit_proven":False,
        "tardis_oi_asset_days":len(oi),
        "tardis_oi_vendor_receipt_full_asset_days":len(vendor_asof_oi),
        "binance_trade_event_asset_market_days":len(flows),
        "binance_trade_event_full_asset_market_days":len(event_only_flow),
        "clock_compatible_full_joint_asset_market_days":0,
        "vendor_oi_and_event_flow_date_coincidences":len(overlap),
        "overlap_dates_utc":sorted({day for day,_,_ in overlap}),
        "overlap_symbols":sorted({symbol for _,symbol,_ in overlap}),
        "overlap_markets":sorted({market for _,_,market in overlap}),
        "example_overlap_quality":"DATE_COIN_MATCH_ONLY_NO_FLOW_RELEASE_PIT",
        "flow_publication_evidence":"UNVERIFIED",
        "exchange_first_publication_evidence":"UNVERIFIED",
        "vendor_oi_receipt_is_not_exchange_publication":True,
        "causal_5m_features_eligible_for_locked_holdout":0,
        "holdout_and_model_training_authorized":False,
        "edge_status":"EDGE_UNVALIDATED",
        "scope":"PINNED_SOURCE_INVENTORY_ONLY",
    }
    return values

def verify_inventory_local_and_r2(local_file,client,bucket,verify_r2):
    """Use the inventory's run-unique R2 key and exact digest, not a mutable latest."""
    local=json.loads(Path(local_file).read_text(encoding="utf-8"))
    key=local.get("r2_key")
    sha=local.get("r2_sha256")
    if (not isinstance(key,str) or
        not key.startswith("research/detector-h1h10-evidence-inventory/v1/") or
        not key.endswith(".json") or not isinstance(sha,str) or len(sha)!=64):
        raise ValueError("INVENTORY_R2_PIN_MISSING")
    raw=verify_r2(client,bucket,key,sha,800000)
    root=json.loads(raw)
    expected=dict(local)
    expected.pop("r2_key",None);expected.pop("r2_sha256",None)
    if root!=expected:raise ValueError("INVENTORY_LOCAL_R2_PAYLOAD_MISMATCH")
    return root,{"key":key,"sha256":sha}
