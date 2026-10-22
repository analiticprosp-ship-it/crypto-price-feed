#!/usr/bin/env python3
"""Bounded May 05–10 2026 ETH/SOL Spot+USD-M 5m event-flow expansion.

One independently bounded UTC day per GitHub matrix job, <=4 aggTrades ZIP
(25MiB/file, 60MiB total) + <=4 price ZIP (850KiB/file). Publisher .CHECKSUM
SHA256, ZIP CRC, strict Spot µs / UM ms, 288 price bars, 5m observed flow only.
Immutable private R2 raw and derived byte readbacks. Summaries descriptive.
NO historical source publication PIT, OOS holdout, trading or autonomous run.
"""
import csv
import io
import json
import os
from pathlib import Path
import zipfile

import boto3
from research.detector_h1h10_binance_flow_archive_pilot import (
    DAYS, archive_url, fetch_http, checksum_sha, validate_5m_zip,
    sha, put_immutable, ZIP_MAX,
)
from research.detector_h1h10_binance_aggtrades_first_verified import (
    parse_day_zip, flow_csv_bytes, MAX_ZIP_BYTES, MAX_TOTAL_ZIP_BYTES,
)
from research.detector_h1h10_binance_one_day_event_diagnostics import (
    diagnostics, read_flow_5m,
)

ROOT="research/detector-h1h10-binance-week-expansion/v1"
SCHEMA="detector-h1h10-2026may05-10-event-only-per-day-v1"
DAYS_ADDITIONAL=DAYS[1:]
MARKETS=("spot","um")
SYMBOLS=("ETHUSDT","SOLUSDT")
PRICE_MAX=ZIP_MAX
DAY_FLOW_CAP=MAX_TOTAL_ZIP_BYTES
DAY_PRICE_CAP=4*PRICE_MAX


def choose_day(raw):
    if raw not in DAYS_ADDITIONAL:
        raise ValueError("WEEK_EXPANSION_DAY_OUTSIDE_DISCOVERY")
    return raw


def exact_publisher_file(url,limit,loader=fetch_http):
    """Never treat HEAD/archive listing as verified downloaded original data."""
    payload=loader(url,"GET",cap=limit)
    check=loader(url+".CHECKSUM","GET",cap=512)
    digest=checksum_sha(check,url.rsplit("/",1)[1])
    if sha(payload)!=digest:
        raise ValueError("PUBLISHER_SHA_MISMATCH")
    return payload,digest


def read_prices(payload,market,symbol,day):
    v=validate_5m_zip(payload,market,symbol,day)
    with zipfile.ZipFile(io.BytesIO(payload)) as f:
        csv_data=f.read(f"{symbol}-5m-{day}.csv").decode("utf-8-sig")
    rows=list(csv.reader(io.StringIO(csv_data)))
    if v["publisher_csv_header_present"]:
        rows=rows[1:]
    if len(rows)!=288:
        raise ValueError("PRICE_PANEL_INCOMPLETE")
    values=[float(row[4]) for row in rows]
    return v,values


def join_day(day,by_key):
    """No cross-day future labels and no silent missing coin/venue substitution."""
    day=choose_day(day)
    if set(by_key)!={(m,s) for m in MARKETS for s in SYMBOLS}:
        raise ValueError("EXPECTED_FOUR_SPOT_UM_SOURCE_PAIRS_MISSING")
    by_source={};h6={}
    for key,(prices,flow) in sorted(by_key.items()):
        by_source["|".join(key)]=diagnostics(prices,flow)
    for sym in SYMBOLS:
        same_price=by_key["spot",sym][0]
        spot_flow=by_key["spot",sym][1]
        perp_flow=by_key["um",sym][1]
        h6[sym]={
            "status":"MATCHED_EVENT_BUCKET_ONLY",
            **diagnostics(same_price,perp_flow,spot_flow=spot_flow),
            "causal_rows_authorized":0,
        }
    return {"h1_h7_per_source":by_source, "h6_matched_coin":h6,
            "flow_source_count":4,"h6_matched_coin_count":2,
            "historical_first_available_at":"UNVERIFIED",
            "not_statistically_independent_5m_rows":True,
            "causal_authorized":0}


def run(day,s3,bucket,run_id,attempt,loader=fetch_http):
    day=choose_day(day)
    flow_bytes_total=0
    price_bytes_total=0
    successes=[]
    failures=[]
    data={}
    # Exactly four predetermined venue/symbol pairs; no selection by outcome.
    for market in MARKETS:
        for symbol in SYMBOLS:
            item={"day":day,"venue":"Binance","market":market,"symbol":symbol}
            try:
                f_url=archive_url(market,"aggTrades",symbol,day)
                flow_head=loader(f_url,"HEAD")
                n=flow_head.get("bytes")
                if (flow_head.get("http")!=200 or type(n) is not int
                    or not 0<n<=MAX_ZIP_BYTES
                    or flow_bytes_total+n>DAY_FLOW_CAP):
                    raise ValueError("FLOW_HEAD_SIZE_OR_DAILY_CAP")
                f_raw,f_sha=exact_publisher_file(f_url,MAX_ZIP_BYTES,loader)
                flow_bytes_total+=len(f_raw)
                quality,rows=parse_day_zip(f_raw,market,symbol,day)
                derived=flow_csv_bytes(rows)
                p_url=archive_url(market,"klines",symbol,day)
                p_raw,p_sha=exact_publisher_file(p_url,PRICE_MAX,loader)
                price_bytes_total+=len(p_raw)
                if price_bytes_total>DAY_PRICE_CAP:
                    raise ValueError("PRICE_TOTAL_BYTE_CAP")
                validation,prices=read_prices(p_raw,market,symbol,day)
                flow=read_flow_5m(derived,day)
                if (len(flow)!=quality["five_minute_slots_with_trades"]
                    or validation["rows"]!=288):
                    raise ValueError("DERIVED_PRICE_FLOW_COVERAGE_MISMATCH")
                keys={
                    "raw_flow":ROOT+f"/raw-flow/{day}/{market}-{symbol}-{f_sha}.zip",
                    "derived_flow":ROOT+f"/derived-flow/{day}/{market}-{symbol}-{sha(derived)}.csv",
                    "raw_price":ROOT+f"/raw-price/{day}/{market}-{symbol}-{p_sha}.zip",
                }
                for kind,payload,digest in (
                    ("raw_flow",f_raw,f_sha),("derived_flow",derived,sha(derived)),
                    ("raw_price",p_raw,p_sha)):
                    if put_immutable(s3,bucket,keys[kind],payload)!=digest:
                        raise ValueError("R2_IMMUTABLE_READBACK_SHA_MISMATCH")
                data[market,symbol]=(prices,flow)
                successes.append({**item,"status":"ORIGINAL_SHA_CRC_AND_EVENT_LABEL_PASS",
                    "trade_count":quality["trades"],
                    "flow_observed_buckets":len(flow),
                    "missing_flow_buckets":288-len(flow),
                    "prices_verified_buckets":288,
                    "spot_price_trade_clock":"microseconds" if market=="spot" else "milliseconds",
                    "historical_source_publication":"UNVERIFIED",
                    "flow_publisher_sha256":f_sha,
                    "price_publisher_sha256":p_sha,
                    "derived_flow_sha256":sha(derived),
                    "r2_verified_objects":keys})
            except Exception as exc:
                failures.append({**item,"status":"SOURCE_FAILED_NO_DATA_PROMOTION",
                                 "error_type":type(exc).__name__,
                                 "error_code":str(exc)[:100]})
    ready=(len(successes)==4 and not failures)
    exploratory=join_day(day,data) if ready else None
    record={"schema":SCHEMA,"scope":"RESEARCH_ONLY","utc_day":day,
        "source_window_preselected":["2026-05-04","2026-05-05","2026-05-06",
                                     "2026-05-07","2026-05-08","2026-05-09",
                                     "2026-05-10"],
        "fixed_universe":["ETHUSDT","SOLUSDT"],
        "expected_price_and_flow_sources":4,
        "verified_sources":successes,"failed_sources":failures,
        "status":"COMPLETE_EVENT_ONLY_NOT_PIT" if ready else "INCOMPLETE_DO_NOT_JOIN",
        "actual_trades_verified":sum(x["trade_count"] for x in successes),
        "observed_event_flow_buckets":sum(x["flow_observed_buckets"] for x in successes),
        "complete_day_price_panel_sources":len(successes),
        "exploratory":exploratory,
        "only_event_time_no_historical_original_publication":True,
        "independent_day_count":1 if ready else 0,
        "minimum_confirmatory_60_holdout_days":"NOT_MET",
        "historical_pit":"BLOCKED",
        "holdout_consumed":False,
        "confirmatory_training_authorized":False,
        "causal_joint_rows_authorized":0,
        "statistical_significance":"NOT_ASSESSED",
        "edge_status":"EDGE_UNVALIDATED",
        "trading_actions":False,"new_paid_sources":False,
        "run_id":run_id,"run_attempt":attempt}
    raw=json.dumps(record,sort_keys=True,ensure_ascii=False,indent=2).encode()
    key=ROOT+f"/run-reports/{run_id}-{attempt}/{day}.json"
    digest=put_immutable(s3,bucket,key,raw)
    local=Path(f"detector_h1h10_week_expansion/{day}.json")
    local.parent.mkdir(exist_ok=True,parents=True)
    local.write_text(json.dumps({**record,"r2_key":key,"sha256":digest},
                                ensure_ascii=False,indent=2),encoding="utf-8")
    message={"day":day,"complete":ready,"source_files":len(successes),
             "failures":len(failures),"trades_verified":record["actual_trades_verified"],
             "flow_event_buckets":record["observed_event_flow_buckets"],
             "coin_pairs":exploratory["h6_matched_coin_count"] if ready else 0,
             "pvalue":"NOT_ASSESSED",
             "original_publication":"UNVERIFIED",
             "causal_authorized":0,"report_r2_key":key,"sha256":digest}
    print("H1H10_WEEK_DAY_RESULT",json.dumps(message,ensure_ascii=False),flush=True)
    return record


def main():
    day=choose_day(os.environ.get("H1H10_RESEARCH_DAY",""))
    if os.environ.get("GITHUB_REPOSITORY")!="analiticprosp-ship-it/crypto-price-feed":
        raise ValueError("WRONG_RESEARCH_REPOSITORY")
    run_id=os.environ["GITHUB_RUN_ID"];attempt=os.environ.get("GITHUB_RUN_ATTEMPT","1")
    if not run_id.isdigit() or not attempt.isdigit():
        raise ValueError("GITHUB_RUN_ID_INVALID")
    s3=boto3.client("s3",
        endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto")
    record=run(day,s3,os.environ["R2_BUCKET"],run_id,attempt)
    if record["status"]!="COMPLETE_EVENT_ONLY_NOT_PIT":
        raise ValueError("RESEARCH_DAY_INCOMPLETE_SOURCE_EVIDENCE")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"],"a",encoding="utf-8") as f:
            f.write(f"### {day} H1/H6/H7 pre-holdout event-only extension\n\n")
            f.write(f"- Trades: {record['actual_trades_verified']}, four complete source files.\n")
            f.write("- Causal first-publication: **UNVERIFIED**; holdout/model/production **BLOCKED**.\n")


if __name__=="__main__":
    main()
