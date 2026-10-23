#!/usr/bin/env python3
"""Three precommitted dates with PRIOR-week BTC regimes; exploratory ONLY.

Dates fixed ex ante to 2026-02-18, 04-15, 06-17, all before locked holdout
2026-07-01. BTC regime fixed from source-verified Spot 5m open at D-7
and close at D-1 (all strictly before D). >3% up, <-3% down, otherwise
consolidation. NO adaptive or post-outcome date replacement/selection.
On D: ETH/SOL Spot and USD-M original aggTrades and 5m prices, exact
publisher SHA256, ZIP CRC, raw native event clocks, 5m gap masks, original
raw + derived SHA PUT/GET into private R2. No PIT original-publication,
no confirmatory H1-H10, no statistical independence of 5m observations,
no model training, no trades, no portfolio or risk-limit mutations.
"""
import datetime as dt
import json
import os
from pathlib import Path

import boto3

from research.detector_h1h10_binance_flow_archive_pilot import (
    archive_url, fetch_http, put_immutable, sha, ZIP_MAX
)
from research.detector_h1h10_binance_week_event_expansion import (
    exact_publisher_file, read_prices, join_day as _may_join,
)
from research.detector_h1h10_binance_aggtrades_first_verified import (
    parse_day_zip, flow_csv_bytes, MAX_ZIP_BYTES, MAX_TOTAL_ZIP_BYTES
)
from research.detector_h1h10_binance_one_day_event_diagnostics import (
    read_flow_5m, diagnostics
)

SCHEMA="detector-h1h10-prior-btc-regime-3day-exploratory-v1"
ROOT="research/detector-h1h10-regime-3day-2026/v1"
PRECOMMITTED_DATES=("2026-02-18","2026-04-15","2026-06-17")
MARKETS=("spot","um")
FLOW_SYMBOLS=("ETHUSDT","SOLUSDT")
SOURCE_ALLOWLIST=tuple(sorted({
    *PRECOMMITTED_DATES,
    *(str(dt.date.fromisoformat(d)-dt.timedelta(days=n))
      for d in PRECOMMITTED_DATES for n in (1,7))
}))
UP_THRESHOLD=0.03
DOWN_THRESHOLD=-0.03
MAX_FLOW_DAY=MAX_TOTAL_ZIP_BYTES
MAX_PRICE_DAY=6*ZIP_MAX


def choose_day(day):
    if day not in PRECOMMITTED_DATES:
        raise ValueError("REGIME_UNFROZEN_OR_HOLDOUT_DAY")
    return day


def lead_dates(day):
    choose_day(day)
    day=dt.date.fromisoformat(day)
    return ((day-dt.timedelta(days=7)).isoformat(),
            (day-dt.timedelta(days=1)).isoformat())


def source_url(market,kind,symbol,day):
    if market not in MARKETS or symbol not in (*FLOW_SYMBOLS,"BTCUSDT"):
        raise ValueError("REGIME_SOURCE_IDENTITY_NOT_ALLOWED")
    if symbol=="BTCUSDT" and (market!="spot" or kind!="klines"):
        raise ValueError("REGIME_BTC_ONLY_SPOT_PRICE")
    return archive_url(market,kind,symbol,day,allowed_days=SOURCE_ALLOWLIST)


def regime_prior_week(day,first_prices,last_prices):
    begin,end=lead_dates(day)
    if len(first_prices)!=288 or len(last_prices)!=288:
        raise ValueError("REGIME_FULL_PREWINDOW_BARS_REQUIRED")
    start=first_prices[0];finish=last_prices[-1]
    if not 0<start<1e9 or not 0<finish<1e9:
        raise ValueError("REGIME_BTC_PRICE_INVALID")
    change=finish/start-1.0
    label=("RISING" if change>UP_THRESHOLD else
           "FALLING" if change<DOWN_THRESHOLD else "CONSOLIDATING")
    return {"label":label,"seven_day_return":round(change,10),
            "first_price_day":begin,"last_price_day":end,
            "classification_cutoff_utc":day+"T00:00:00+00:00",
            "defined_ex_ante":True,
            "thresholds":{"rising_gt":UP_THRESHOLD,"falling_lt":DOWN_THRESHOLD},
            "day_to_be_analyzed_not_used_for_regime":True}


def join(day,panel):
    choose_day(day)
    expected={(m,s) for m in MARKETS for s in FLOW_SYMBOLS}
    if set(panel)!=expected:
        raise ValueError("REGIME_FOUR_COIN_VENUE_PAIRS_REQUIRED")
    h17={"|".join(key):diagnostics(*panel[key]) for key in sorted(panel)}
    h6={}
    for symbol in FLOW_SYMBOLS:
        spot_price,spot_flow=panel["spot",symbol]
        _,perp_flow=panel["um",symbol]
        h6[symbol]={"status":"EVENT_TIME_MATCHED_NOT_CAUSAL",
                    "diagnostics":diagnostics(spot_price,perp_flow,spot_flow=spot_flow),
                    "causal_authorized":0}
    return {"h1_h7":h17,"h6":h6,"h6_pairs":2,
            "independent_utc_days":1,"event_only":True,
            "causal_authorized":0,"edge":"EDGE_UNVALIDATED"}


def run(day,s3,bucket,rid,attempt,loader=fetch_http,write=put_immutable):
    day=choose_day(day)
    failures=[];receipts=[];panel={}
    byte_budget={"aggTrades":0,"price":0}
    btc_closes={}
    # BTC reference days are a priori as-of information for regime LABEL ONLY.
    first,last=lead_dates(day)
    for d in (first,last):
        try:
            url=source_url("spot","klines","BTCUSDT",d)
            payload,digest=exact_publisher_file(url,ZIP_MAX,loader)
            byte_budget["price"]+=len(payload)
            if byte_budget["price"]>MAX_PRICE_DAY:
                raise ValueError("REGIME_PRICE_BYTE_CAP")
            proof,price=read_prices(payload,"spot","BTCUSDT",d)
            key=ROOT+f"/raw-prior-btc/{d}/{digest}.zip"
            if write(s3,bucket,key,payload)!=digest:
                raise ValueError("REGIME_BTC_R2_SHA_READBACK")
            btc_closes[d]=price
            receipts.append({"role":"PRIOR_BTC_REGIME_PRICE","market":"spot",
                             "symbol":"BTCUSDT","day":d,"archive_sha256":digest,
                             "r2_key":key,"5m_rows":proof["rows"],
                             "original_publication":"UNVERIFIED"})
        except Exception as e:
            failures.append({"role":"PRIOR_BTC_REGIME_PRICE","day":d,
                             "code":type(e).__name__,"reason":str(e)[:120]})
    regime=regime_prior_week(day,btc_closes[first],btc_closes[last]) if len(btc_closes)==2 else None
    for market in MARKETS:
        for symbol in FLOW_SYMBOLS:
            entry={"role":"STUDY","market":market,"symbol":symbol,"day":day}
            try:
                f_url=source_url(market,"aggTrades",symbol,day)
                head=loader(f_url,"HEAD",cap=0)
                size=head.get("bytes")
                if (head.get("http")!=200 or type(size) is not int
                    or not 0<size<=MAX_ZIP_BYTES
                    or byte_budget["aggTrades"]+size>MAX_FLOW_DAY):
                    raise ValueError("REGIME_FLOW_SOURCE_SIZE_OR_BUDGET")
                flow_raw,flow_hash=exact_publisher_file(f_url,MAX_ZIP_BYTES,loader)
                byte_budget["aggTrades"]+=len(flow_raw)
                quality,flow_rows=parse_day_zip(flow_raw,market,symbol,day,allowed_days=SOURCE_ALLOWLIST)
                derivative=flow_csv_bytes(flow_rows)
                fdata=read_flow_5m(derivative,day,allowed_days=SOURCE_ALLOWLIST)
                if len(fdata)!=quality["five_minute_slots_with_trades"]:
                    raise ValueError("REGIME_FLOW_OBSERVED_MASK_MISMATCH")
                p_url=source_url(market,"klines",symbol,day)
                price_raw,price_hash=exact_publisher_file(p_url,ZIP_MAX,loader)
                byte_budget["price"]+=len(price_raw)
                if byte_budget["price"]>MAX_PRICE_DAY:
                    raise ValueError("REGIME_PRICE_BYTE_CAP")
                price_proof,prices=read_prices(price_raw,market,symbol,day)
                keys={
                    "original_flow":ROOT+f"/raw-flow/{day}/{market}-{symbol}-{flow_hash}.zip",
                    "derived_flow":ROOT+f"/flow-5m/{day}/{market}-{symbol}-{sha(derivative)}.csv",
                    "original_price":ROOT+f"/raw-price/{day}/{market}-{symbol}-{price_hash}.zip"}
                for role,blob,digest in (
                    ("original_flow",flow_raw,flow_hash),
                    ("derived_flow",derivative,sha(derivative)),
                    ("original_price",price_raw,price_hash)):
                    if write(s3,bucket,keys[role],blob)!=digest:
                        raise ValueError("REGIME_SOURCE_R2_SHA_READBACK")
                panel[market,symbol]=(prices,fdata)
                receipts.append({**entry,"status":"PUBLISHER_SHA_CRC_5M_EVENT_ONLY",
                                 "trades_verified":quality["trades"],
                                 "observed_flow_5m":len(fdata),
                                 "missing_flow_5m":288-len(fdata),
                                 "price_5m":price_proof["rows"],
                                 "raw_flow_sha256":flow_hash,
                                 "derived_sha256":sha(derivative),
                                 "price_sha256":price_hash,
                                 "r2_objects":keys,"source_first_available":"UNVERIFIED"})
            except Exception as e:
                failures.append({**entry,"code":type(e).__name__,
                                 "reason":str(e)[:120]})
    complete=regime is not None and len(panel)==4 and not failures
    results=join(day,panel) if complete else None
    report={"schema":SCHEMA,"scope":"RESEARCH_ONLY","utc_day":day,
            "precommitted_sampling_dates":list(PRECOMMITTED_DATES),
            "predeclared_btc_regime":regime,
            "fixed_symbols":list(FLOW_SYMBOLS),"fixed_markets":list(MARKETS),
            "receipts":receipts,"failures":failures,
            "status":"COMPLETE_DESCRIPTIVE_NOT_PIT" if complete else "INCOMPLETE_NOT_ANALYZABLE",
            "source_counts":{"btc_prior_reference_days":len(btc_closes),
                             "study_venue_symbol_pairs":len(panel),
                             "study_aggtrades":sum(x.get("trades_verified",0) for x in receipts),
                             "flow_5m_slots":sum(x.get("observed_flow_5m",0) for x in receipts)},
            "exploratory":results,
            "one_sample_day_only":True,
            "independent_holdout_days_added":0,
            "historical_first_published_at":"UNVERIFIED",
            "confirmatory_training_allowed":False,
            "locked_holdout_used":False,
            "causal_joint_rows_authorized":0,
            "edge_status":"EDGE_UNVALIDATED","trading_actions":False,
            "new_paid_resources":False,"run_id":rid,"attempt":attempt}
    raw=json.dumps(report,ensure_ascii=False,sort_keys=True,indent=2).encode()
    dest=ROOT+f"/reports/{rid}-{attempt}/{day}.json"
    digest=write(s3,bucket,dest,raw)
    if digest!=sha(raw):
        raise ValueError("REGIME_REPORT_SHA_READBACK")
    local=Path("detector_h1h10_regime_three_dates")/f"{day}.json"
    local.parent.mkdir(parents=True,exist_ok=True)
    local.write_text(json.dumps({**report,"r2_key":dest,"sha256":digest},
                                ensure_ascii=False,indent=2),encoding="utf-8")
    print("H1H10_REGIME_DAY",json.dumps({"day":day,
        "complete":complete,
        "prior_regime":regime["label"] if regime else "UNVERIFIED",
        "prior_return":regime["seven_day_return"] if regime else None,
        "original_aggtrades":report["source_counts"]["study_aggtrades"],
        "verified_flow_slots":report["source_counts"]["flow_5m_slots"],
        "study_pairs":len(panel),"failed":len(failures),
        "causal_authorized":0,
        "r2_key":dest,"sha256":digest},ensure_ascii=False),flush=True)
    return report


def main():
    day=choose_day(os.environ.get("H1H10_RESEARCH_DAY",""))
    if os.environ.get("GITHUB_REPOSITORY")!="analiticprosp-ship-it/crypto-price-feed":
        raise ValueError("WRONG_REPOSITORY")
    rid=os.environ["GITHUB_RUN_ID"];attempt=os.environ.get("GITHUB_RUN_ATTEMPT","1")
    if not rid.isdigit() or not attempt.isdigit():
        raise ValueError("GITHUB_RUN_ID_INVALID")
    s3=boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
                    aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
                    aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
    result=run(day,s3,os.environ["R2_BUCKET"],rid,attempt)
    if result["status"]!="COMPLETE_DESCRIPTIVE_NOT_PIT":
        raise ValueError("REGIME_SOURCE_DAY_INCOMPLETE")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"],"a",encoding="utf-8") as f:
            f.write(f"## H1/H6/H7 exploratory {day} — prior BTC regime {result['predeclared_btc_regime']['label']}\n\n")
            f.write("- Historical first-available / OOS / edge: **UNVERIFIED / BLOCKED / EDGE_UNVALIDATED**.\n")


if __name__=="__main__":
    main()
