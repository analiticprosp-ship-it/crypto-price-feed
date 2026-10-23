#!/usr/bin/env python3
"""Jan 21 2026 first predeclared negative-BTC-regime H1/H6/H7 source collection.

Selected date is authenticated from prior BTC 7-day PRICE ONLY scan with exact
R2 manifest SHA, never from ETH/SOL flow or same-day BTC prices. Four fixed
Binance ETH/SOL Spot/USD-M original aggTrades and price source ZIPs, original
Binance publisher checksum + ZIP CRC + source native UTC clocks, byte-for-byte
R2 SHA/metadata readbacks. Descriptive 15/60m within-day only; historical
first-publication unverified, no model/holdout/production/trade authority.
"""
import json
import os
from pathlib import Path

import boto3
from research.detector_h1h10_binance_flow_archive_pilot import (
    archive_url, fetch_http, ZIP_MAX, sha, put_immutable
)
from research.detector_h1h10_binance_week_event_expansion import (
    exact_publisher_file, read_prices
)
from research.detector_h1h10_binance_aggtrades_first_verified import (
    parse_day_zip, flow_csv_bytes, MAX_ZIP_BYTES, MAX_TOTAL_ZIP_BYTES
)
from research.detector_h1h10_binance_one_day_event_diagnostics import (
    read_flow_5m, diagnostics, verified_bytes
)

DAY="2026-01-21"
FROZEN=(DAY,)
ROOT="research/detector-h1h10-falling-jan21-exploratory/v1"
SCHEMA="detector-h1h10-first-falling-jan21-spot-um-event-only-v1"
PRIOR_SELECTION_PIN={
    "key":"research/detector-h1h10-regime-falling-candidate/v1/reports/39919875574-1.json",
    "sha256":"34dc9e58c6e083f817dd3502e20b5256012a3d777d53866d4af531f6570208b1",
    "schema":"detector-h1h10-btc-prefill-falling-selection-v1",
}
MARKETS=("spot","um")
SYMBOLS=("ETHUSDT","SOLUSDT")


def confirm_selection(document):
    if (document.get("schema")!=PRIOR_SELECTION_PIN["schema"]
        or document.get("scope")!="RESEARCH_ONLY"
        or document.get("selection",{}).get("selected_date")!=DAY
        or document["selection"].get("selection_status")!="FIRST_PREDECLARED_FALLING_PREWINDOW"
        or len(document.get("observed_candidates",()))!=1
        or document["observed_candidates"][0].get("day")!=DAY
        or document["observed_candidates"][0].get("status")!="VERIFIED"
        or document["observed_candidates"][0].get("classification",{}).get("is_falling") is not True
        or document.get("selected_day_aggtrades_downloaded")!=0
        or document.get("selection_uses_eth_sol_flow") is not False
        or document.get("locked_holdout_accessed") is not False
        or document.get("causal_joint_rows_authorized")!=0
        or document.get("trading_actions") is not False):
        raise ValueError("JAN21_BTC_SELECTION_SHA_PIN_OR_RESEARCH_SCOPE_INVALID")
    return document["observed_candidates"][0]["classification"]


def run(s3,bucket,rid,attempt,loader=fetch_http,write=put_immutable,selection=None):
    if selection is None:
        raw=verified_bytes(s3,bucket,PRIOR_SELECTION_PIN["key"],
                           PRIOR_SELECTION_PIN["sha256"],280000)
        selection=json.loads(raw)
    classification=confirm_selection(selection)
    successes=[];failures=[];panel={}
    total_flow_bytes=0
    total_price_bytes=0
    for market in MARKETS:
        for symbol in SYMBOLS:
            item={"day":DAY,"venue":"Binance","market":market,"symbol":symbol}
            try:
                f_url=archive_url(market,"aggTrades",symbol,DAY,allowed_days=FROZEN)
                metadata=loader(f_url,"HEAD",cap=0)
                n=metadata.get("bytes")
                if (metadata.get("http")!=200 or type(n) is not int or
                    not 0<n<=MAX_ZIP_BYTES or total_flow_bytes+n>MAX_TOTAL_ZIP_BYTES):
                    raise ValueError("JAN21_FLOW_SOURCE_SIZE_CAP")
                f_raw,f_sha=exact_publisher_file(f_url,MAX_ZIP_BYTES,loader)
                total_flow_bytes+=len(f_raw)
                quality,rows=parse_day_zip(f_raw,market,symbol,DAY,allowed_days=FROZEN)
                d_raw=flow_csv_bytes(rows)
                flows=read_flow_5m(d_raw,DAY,allowed_days=FROZEN)
                if len(flows)!=quality["five_minute_slots_with_trades"]:
                    raise ValueError("JAN21_FLOW_SOURCE_MASK_MISMATCH")
                p_url=archive_url(market,"klines",symbol,DAY,allowed_days=FROZEN)
                p_raw,p_sha=exact_publisher_file(p_url,ZIP_MAX,loader)
                total_price_bytes+=len(p_raw)
                if total_price_bytes>4*ZIP_MAX:
                    raise ValueError("JAN21_PRICE_SOURCE_SIZE_CAP")
                price_proof,prices=read_prices(p_raw,market,symbol,DAY)
                if price_proof["rows"]!=288:
                    raise ValueError("JAN21_PRICE_MISSING_5M")
                keys={
                    "original_flow":ROOT+f"/raw-flow/{market}-{symbol}-{f_sha}.zip",
                    "derived_flow":ROOT+f"/flow-5m/{market}-{symbol}-{sha(d_raw)}.csv",
                    "original_price":ROOT+f"/raw-price/{market}-{symbol}-{p_sha}.zip"
                }
                for name,body,digest in (
                    ("original_flow",f_raw,f_sha),
                    ("derived_flow",d_raw,sha(d_raw)),
                    ("original_price",p_raw,p_sha)):
                    if write(s3,bucket,keys[name],body)!=digest:
                        raise ValueError("JAN21_R2_SHA_READBACK_FAIL")
                panel[market,symbol]=(prices,flows)
                successes.append({**item,"status":"PUBLISHER_SHA_CRC_EVENT_CLOCK_PASS",
                    "source_aggtrades":quality["trades"],"flow_5m_slots":len(flows),
                    "flow_missing_5m_slots":288-len(flows),
                    "price_5m_slots":288,"original_first_available":"UNVERIFIED",
                    "flow_sha256":f_sha,"derived_sha256":sha(d_raw),
                    "price_sha256":p_sha,"r2_objects":keys})
            except Exception as exc:
                failures.append({**item,"status":"SOURCE_FAILED_NO_PROMOTION",
                                 "error_type":type(exc).__name__,
                                 "reason":str(exc)[:120]})
    complete=len(successes)==4 and not failures and len(panel)==4
    descriptive=None
    if complete:
        d={}
        for market,sym in sorted(panel):
            close,flow=panel[market,sym]
            d[f"{market}|{sym}"]=diagnostics(close,flow)
        h6={}
        for sym in SYMBOLS:
            close,spot_flow=panel["spot",sym]
            perp_flow=panel["um",sym][1]
            h6[sym]={"diagnostics":diagnostics(close,perp_flow,spot_flow=spot_flow),
                     "source_event_only":True,"causal_authorized":0}
        descriptive={"h1_h7":d,"h6":h6,"matched_spot_perp_coins":list(SYMBOLS),
                     "confirmed_causality":False,
                     "statistical_significance":"NOT_ASSESSED"}
    record={"schema":SCHEMA,"scope":"RESEARCH_ONLY","utc_day":DAY,
        "study_selection_exact_r2_pin":PRIOR_SELECTION_PIN,
        "prior_btc_regime":classification,
        "source_files":successes,"failed_source_files":failures,
        "status":"COMPLETE_FALLING_EVENT_ONLY" if complete else "INCOMPLETE_NO_JOIN",
        "verified_aggtrades":sum(x["source_aggtrades"] for x in successes),
        "verified_5m_event_slots":sum(x["flow_5m_slots"] for x in successes),
        "h1_h6_h7_exploratory":descriptive,
        "historical_first_available":"UNVERIFIED",
        "first_exchange_publication":"UNVERIFIED",
        "same_day_btc_used_in_regime":False,
        "locked_holdout_used":False,"independent_holdout_days_added":0,
        "causal_joint_rows_authorized":0,
        "confirmatory_h1_h6_h7":"BLOCKED",
        "edge_status":"EDGE_UNVALIDATED","trading_actions":False,
        "new_paid_services":False,"run_id":rid,"attempt":attempt}
    raw=json.dumps(record,ensure_ascii=False,sort_keys=True,indent=2).encode()
    key=ROOT+f"/run-reports/{rid}-{attempt}.json"
    digest=write(s3,bucket,key,raw)
    if digest!=sha(raw):
        raise ValueError("JAN21_REPORT_R2_SHA_FAIL")
    path=Path("detector_h1h10_falling_jan21_evidence/report.json")
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps({**record,"r2_key":key,"sha256":digest},
                               ensure_ascii=False,indent=2),encoding="utf-8")
    print("H1H10_VERIFIED_FALLING_REGIME_FLOW",
          json.dumps({"day":DAY,"prior_btc_change":classification["seven_day_prior_return"],
                      "source_files":len(successes),"source_errors":len(failures),
                      "flow_trade_rows":record["verified_aggtrades"],
                      "flow_5m_slots":record["verified_5m_event_slots"],
                      "causal_authorized":0,"r2_key":key,"sha256":digest},
                     ensure_ascii=False),flush=True)
    return record


def main():
    if os.environ.get("GITHUB_REPOSITORY")!="analiticprosp-ship-it/crypto-price-feed":
        raise ValueError("WRONG_REPO")
    rid=os.environ["GITHUB_RUN_ID"];attempt=os.environ.get("GITHUB_RUN_ATTEMPT","1")
    if not rid.isdigit() or not attempt.isdigit():
        raise ValueError("RUN_ID_INVALID")
    s3=boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
                    aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
                    aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
    item=run(s3,os.environ["R2_BUCKET"],rid,attempt)
    if item["status"]!="COMPLETE_FALLING_EVENT_ONLY":
        raise ValueError("FALLING_DAY_INCOMPLETE_NO_CONFIRMATORY_JOIN")


if __name__=="__main__":
    main()
