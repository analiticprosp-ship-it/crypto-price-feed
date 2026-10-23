#!/usr/bin/env python3
"""Select first objectively FALLING pre-holdout discovery date from BTC *pre*-week.

Selection candidates and -3% threshold fixed before data inspection.
ONLY pre-D BTC Spot prices, original publisher ZIP SHA + R2 SHA readback.
No flow, no H1/H6/H7 fitted result, no historical original-publish proof,
no use of locked holdout, no trade or portfolio permission. If an earlier
candidate lacks quality data, earliest-eligible selection is BLOCKED rather
than silently skipping/peeking at later candidates.
"""
import datetime as dt
import json
import os
from decimal import Decimal
from pathlib import Path

import boto3
from research.detector_h1h10_binance_flow_archive_pilot import (
    archive_url, fetch_http, put_immutable, sha, ZIP_MAX,
)
from research.detector_h1h10_binance_week_event_expansion import (
    exact_publisher_file, read_prices,
)

ROOT="research/detector-h1h10-regime-falling-candidate/v1"
SCHEMA="detector-h1h10-btc-prefill-falling-selection-v1"
CANDIDATES=("2026-01-21","2026-02-04","2026-03-04","2026-03-25",
            "2026-04-29","2026-05-27","2026-06-24")
THRESHOLD=Decimal("-0.03")
SOURCE_DAYS=tuple(sorted({
    str(dt.date.fromisoformat(day)-dt.timedelta(days=n))
    for day in CANDIDATES for n in (1,7)
}))


def previous_days(day):
    if day not in CANDIDATES:
        raise ValueError("BEAR_CANDIDATE_DATE_OUTSIDE_PREDECLARATION")
    base=dt.date.fromisoformat(day)
    return (str(base-dt.timedelta(days=7)),str(base-dt.timedelta(days=1)))


def classify(day, first, last):
    begin,end=previous_days(day)
    if len(first)!=288 or len(last)!=288:
        raise ValueError("BEAR_FULL_PRIOR_WEEK_REQUIRED")
    open_at=Decimal(str(first[0]));close_at=Decimal(str(last[-1]))
    if open_at<=0 or close_at<=0:
        raise ValueError("BEAR_PRICE_INVALID")
    change=close_at/open_at-1
    return {"day":day,"seven_day_prior_return":round(float(change),10),
            "is_falling":change<THRESHOLD,
            "classification_label":"FALLING" if change<THRESHOLD else "NOT_FALLING",
            "pre_window_first_day":begin,"pre_window_last_day":end,
            "threshold_strict_lt":float(THRESHOLD),
            "only_prior_prices":True,
            "original_source_published_at":"UNVERIFIED"}


def find_first_falling(evaluated):
    """Never look past missing prior candidate (would bias earliest selection)."""
    for i,e in enumerate(evaluated):
        if e.get("day") != CANDIDATES[i]:
            raise ValueError("BEAR_CANDIDATE_ORDER_OR_SKIPPED_DAY")
        if e.get("status")!="VERIFIED":
            return {"selected_date":None,"selection_status":"BLOCKED_BY_EARLIER_MISSING_PRICE",
                    "stopped_at":e["day"]}
        if e["classification"]["is_falling"]:
            return {"selected_date":e["day"],"selection_status":"FIRST_PREDECLARED_FALLING_PREWINDOW",
                    "stopped_at":e["day"]}
    if len(evaluated)!=len(CANDIDATES):
        raise ValueError("BEAR_PREMATURE_STOP_WITHOUT_SELECTION")
    return {"selected_date":None,"selection_status":"NO_FALLING_DATE_IN_FIXED_CANDIDATES",
            "stopped_at":CANDIDATES[-1]}


def run(s3,bucket,run_id,attempt,loader=fetch_http,write=put_immutable):
    observations=[]
    for day in CANDIDATES:
        source_receipts=[]
        prices={}
        failures=[]
        for previous in previous_days(day):
            try:
                url=archive_url("spot","klines","BTCUSDT",previous,allowed_days=SOURCE_DAYS)
                raw,digest=exact_publisher_file(url,ZIP_MAX,loader)
                proof,close=read_prices(raw,"spot","BTCUSDT",previous)
                key=ROOT+f"/btc-prior-price/{previous}/{digest}.zip"
                if write(s3,bucket,key,raw)!=digest:
                    raise ValueError("BEAR_BTC_R2_IMMUTABLE_SHA_FAILED")
                prices[previous]=close
                source_receipts.append({"day":previous,"source_sha256":digest,
                                        "r2_object_key":key,"verified_rows":proof["rows"],
                                        "source_first_publication":"UNVERIFIED"})
            except Exception as exc:
                failures.append({"day":previous,"error_type":type(exc).__name__,
                                 "reason":str(exc)[:120]})
        classification=classify(day,prices[previous_days(day)[0]],
                                prices[previous_days(day)[1]]) if not failures else None
        observations.append({"day":day,"status":"VERIFIED" if not failures else "DATA_MISSING",
                             "sources":source_receipts,"failures":failures,
                             "classification":classification})
        if failures or classification["is_falling"]:
            break
    selection=find_first_falling(observations)
    record={"schema":SCHEMA,"scope":"RESEARCH_ONLY",
        "purpose":"H1_H6_H7_DISCOVERY_REGIME_COVERAGE_ONLY",
        "precommitted_ordered_candidates":list(CANDIDATES),
        "observed_candidates":observations,"selection":selection,
        "selection_uses_eth_sol_flow":False,
        "selection_uses_candidate_day_prices":False,
        "selected_day_aggtrades_downloaded":0,
        "original_first_available":"UNVERIFIED",
        "locked_holdout_accessed":False,
        "confirmatory_holdout_eligible_days_added":0,
        "causal_joint_rows_authorized":0,
        "h1_h6_h7_confirmatory":"BLOCKED",
        "edge_status":"EDGE_UNVALIDATED",
        "new_paid_services":False,
        "trading_actions":False,
        "run_id":run_id,"attempt":attempt}
    raw=json.dumps(record,sort_keys=True,ensure_ascii=False,indent=2).encode()
    key=ROOT+f"/reports/{run_id}-{attempt}.json"
    digest=write(s3,bucket,key,raw)
    if digest!=sha(raw):
        raise ValueError("BEAR_SELECTION_R2_REPORT_SHA_FAILED")
    path=Path("detector_h1h10_falling_regime_selection/report.json")
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps({**record,"r2_key":key,"sha256":digest},
                               ensure_ascii=False,indent=2),encoding="utf-8")
    print("H1H10_FIRST_FALLING_REGIME_SOURCE_DISCOVERY",
          json.dumps({"checked":len(observations),
                      **selection,"r2_key":key,"sha256":digest,
                      "historical_pit":"BLOCKED","edge":"EDGE_UNVALIDATED"},
                     ensure_ascii=False),flush=True)
    return record


def main():
    if os.environ.get("GITHUB_REPOSITORY")!="analiticprosp-ship-it/crypto-price-feed":
        raise ValueError("WRONG_RESEARCH_REPOSITORY")
    run_id=os.environ["GITHUB_RUN_ID"];attempt=os.environ.get("GITHUB_RUN_ATTEMPT","1")
    if not run_id.isdigit() or not attempt.isdigit():
        raise ValueError("RUN_ID_INVALID")
    s3=boto3.client("s3",
                    endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
                    aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
                    aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
                    region_name="auto")
    r=run(s3,os.environ["R2_BUCKET"],run_id,attempt)
    if r["selection"]["selection_status"]=="BLOCKED_BY_EARLIER_MISSING_PRICE":
        raise ValueError("BEAR_PRIOR_SOURCE_MISSING_NO_SILENT_DATE_SKIP")


if __name__=="__main__":
    main()
