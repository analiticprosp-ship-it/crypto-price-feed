#!/usr/bin/env python3
"""H1/H6/H7 exploratory EVENT-ONLY evidence from exact immutable Binance archives.

No models, threshold tuning, statistical significance, trading authority or
historical first-publication claims. One pre-holdout day, 2026-05-04 ONLY.
Independent R2 SHA+metadata readback of original publisher-verified source
archive ZIPs and derived flow CSVs, exact same venue/symbol five-minute joins.
Day-boundary labels 15m and 60m are explicitly censored, not forward-filled.
"""
import csv
import datetime as dt
import hashlib
import io
import json
import math
import os
from pathlib import Path
import zipfile

import boto3

from research.detector_h1h10_binance_flow_archive_pilot import (
    OUT as PRICE_ROOT, validate_5m_zip, sha, put_immutable,
)
from research.detector_h1h10_binance_aggtrades_first_verified import (
    ROOT as FLOW_ROOT, DAY,
)

SCHEMA="detector-h1h10-binance-may04-exploratory-event-only-v1"
ROOT="research/detector-h1h10-binance-may04-event-only-diagnostics/v1"
PRICE_PIN={
    "key":PRICE_ROOT+"/run-reports/39750648258-1.json",
    "sha256":"272c46a729314513295ed9ec928a0e782d35e893f8b42ba387a84b733642cbc9",
    "schema":"detector-h1h10-binance-bounded-flow-archive-discovery-v1",
}
FLOW_PIN={
    "key":FLOW_ROOT+"/run-reports/39757195431-1.json",
    "sha256":"bd2b738d9bd42e35378bcaa10579ffab3776a791a6a8fb20ce553f3adc4fc796",
    "schema":"detector-h1h10-binance-aggtrades-bounded-raw-v1",
}
FIVE_MIN=300000
MAX_REPORT=280000
MAX_PRICE=850000
MAX_FLOW_ZIP=25*1024*1024
MAX_DERIVED=160000


def verified_bytes(s3,bucket,key,expected,size_cap):
    if (not isinstance(key,str) or not key.startswith("research/")
        or not isinstance(expected,str) or len(expected)!=64
        or not all(ch in "0123456789abcdef" for ch in expected)):
        raise ValueError("SOURCE_SHA_OR_KEY_INVALID")
    obj=s3.get_object(Bucket=bucket,Key=key)
    n=int(obj.get("ContentLength",-1))
    if not 0<n<=size_cap:
        raise ValueError("SOURCE_R2_SIZE_BOUND")
    data=obj["Body"].read(size_cap+1)
    if len(data)!=n or sha(data)!=expected:
        raise ValueError("SOURCE_R2_SHA256_FAILED")
    if obj.get("Metadata",{}).get("sha256")!=expected:
        raise ValueError("SOURCE_R2_METADATA_SHA256_MISSING_OR_WRONG")
    return data


def read_pinned_report(s3,bucket,pin):
    raw=verified_bytes(s3,bucket,pin["key"],pin["sha256"],MAX_REPORT)
    record=json.loads(raw)
    if (record.get("schema")!=pin["schema"]
        or record.get("scope")!="RESEARCH_ONLY"
        or record.get("edge_status")!="EDGE_UNVALIDATED"
        or record.get("trading_actions") is not False
        or record.get("training_authorized") is not False
        or record.get("causal_joint_rows_authorized")!=0):
        raise ValueError("ORIGINAL_RESEARCH_SOURCE_PROVENANCE_OR_AUTHORITY")
    return record


def kline_closes(body,market,symbol):
    evidence=validate_5m_zip(body,market,symbol,DAY)
    with zipfile.ZipFile(io.BytesIO(body),"r") as archive:
        raw=archive.read(f"{symbol}-5m-{DAY}.csv").decode("utf-8-sig")
    rows=list(csv.reader(io.StringIO(raw)))
    if evidence["publisher_csv_header_present"]:
        rows=rows[1:]
    if len(rows)!=288:
        raise ValueError("PRICE_ROWS_NOT_288")
    price=[float(r[4]) for r in rows]
    if any(not math.isfinite(x) or x<=0 for x in price):
        raise ValueError("PRICE_CLOSE_NONFINITE")
    return price


def read_flow_5m(raw,day=DAY):
    """Do not accept unobserved 5m rows or price/flow publisher time conflation."""
    if day!=DAY:
        raise ValueError("NON_FROZEN_DAY")
    start=int(dt.datetime.fromisoformat(day+"T00:00:00+00:00").timestamp()*1000)
    rows=list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
    if not 0<len(rows)<=288:
        raise ValueError("INVALID_DERIVED_FLOW_ROW_COUNT")
    seen={}
    for r in rows:
        try:
            t=dt.datetime.fromisoformat(r["bucket_start_utc"])
            if t.utcoffset()!=dt.timedelta(0):
                raise ValueError("FLOW_TIMESTAMP_NOT_UTC")
            ms=int(t.timestamp()*1000)
            n=int(r["aggtrade_count"])
            buy=float(r["taker_buy_quote_usdt"])
            sell=float(r["taker_sell_quote_usdt"])
            net=float(r["net_taker_quote_usdt"])
            total=float(r["total_quote_usdt"])
        except (KeyError,ValueError,TypeError,OverflowError) as exc:
            raise ValueError("INVALID_DERIVED_FLOW_VALUES") from exc
        if (ms<start or ms>=start+86400000 or (ms-start)%FIVE_MIN
            or ms in seen or n<=0 or not all(math.isfinite(x) for x in (buy,sell,net,total))
            or buy<0 or sell<0 or total<=0
            or abs(total-(buy+sell))>max(1e-5,total*1e-10)
            or abs(net-(buy-sell))>max(1e-5,total*1e-10)
            or r.get("availability")!="EVENT_TIME_ONLY_FIRST_PUBLICATION_UNVERIFIED"):
            raise ValueError("DERIVED_FLOW_CLOCK_MISSING_OR_ACCOUNTING_INVALID")
        index=(ms-start)//FIVE_MIN
        seen[index]={"imbalance":net/total,"buy":buy,"sell":sell,"count":n}
    if len(seen)!=len(rows):
        raise ValueError("DUPLICATE_FLOW_CLOCK")
    return seen


def pearson(pairs):
    """Descriptive association only; no fitted model or statistical inference."""
    if len(pairs)<3:
        return None
    xs=[a for a,_ in pairs];ys=[b for _,b in pairs]
    xbar=sum(xs)/len(xs);ybar=sum(ys)/len(ys)
    numerator=sum((x-xbar)*(y-ybar) for x,y in pairs)
    sx=sum((x-xbar)**2 for x in xs)
    sy=sum((y-ybar)**2 for y in ys)
    if sx<=0 or sy<=0:
        return None
    return round(numerator/math.sqrt(sx*sy),8)


def future_returns(close,flow,horizon):
    """Only event-bucket-aligned description, with actual day-boundary censor."""
    if len(close)!=288 or horizon not in (3,12):
        raise ValueError("RETURN_HORIZON_OR_BAR_COUNT")
    future={}
    for i in sorted(flow):
        if type(i)!=int or i<0 or i>=288:
            raise ValueError("FLOW_DAY_CLOCK_INDEX")
        if i<1 or i+horizon>=288:
            continue
        r5=math.log(close[i]/close[i-1])
        rfuture=math.log(close[i+horizon]/close[i])
        future[i]=(flow[i]["imbalance"],r5,rfuture)
    return future


def diagnostics(close,flow,spot_flow=None):
    """Compute descriptive, never OOS or directional strategy statistics."""
    coverage={"observed_flow_slots":len(flow),
              "missing_flow_slots":288-len(flow),
              "event_timestamp_only_not_first_available":True}
    outcome={}
    for h in (3,12):
        future=future_returns(close,flow,h)
        pairs=[(f,r) for f,_,r in future.values()]
        discrepancy=[
            (r5,rnext) for f,r5,rnext in future.values()
            if r5!=0 and f!=0 and (f>0)!=(r5>0)
        ]
        outcome[f"{h*5}m"]={
            "event_only_sample_count":len(pairs),
            "within_day_censored_count":len(flow)-len(pairs),
            "flow_future_price_logreturn_pearson_descriptive":pearson(pairs),
            "flow_price_sign_disagreements":len(discrepancy),
            "sign_disagreement_next_move_against_current_price_count":
                sum(1 for r5,rnext in discrepancy if (r5>0 and rnext<0) or (r5<0 and rnext>0)),
            "source_first_available_at":"UNVERIFIED",
            "statistical_significance":"NOT_TESTED_SINGLE_DAY",
            "predictive_claim":"PROHIBITED",
        }
        if spot_flow is not None:
            f=future_returns(close,spot_flow,h)
            common=sorted(set(future)&set(f))
            outcome[f"{h*5}m"]["spot_and_perp_same_coin_overlap_slots"]=len(common)
            outcome[f"{h*5}m"]["spot_flow_future_spot_price_correlation"]=pearson(
                [(f[i][0],f[i][2]) for i in common])
            outcome[f"{h*5}m"]["perp_flow_future_spot_price_correlation"]=pearson(
                [(future[i][0],f[i][2]) for i in common])
            outcome[f"{h*5}m"]["lead_lag_causal_status"]="UNVERIFIED_EVENT_TIMESTAMP_ONLY"
    return {"quality":coverage,"event_only_diagnostics":outcome,
            "not_h1_h6_h7_confirmatory":True,"trading_actions":False}


def build(price_report,flow_report,load):
    if (price_report.get("downloaded_verified_5m_price_archives")!=6
        or price_report.get("historical_causal_pit")!="BLOCKED"
        or price_report.get("locked_holdout_used") is not False
        or flow_report.get("verified_zip_count")!=4
        or flow_report.get("utc_day")!=DAY
        or flow_report.get("historical_exchange_release_pit")!="BLOCKED"
        or flow_report.get("locked_holdout_consumed") is not False):
        raise ValueError("SOURCE_REPORT_COVERAGE_OR_PIT_PROMOTED")
    prices={}
    for source in price_report["verified_kline_samples"]:
        market=source["market"];symbol=source["symbol"];key=(market,symbol)
        if key in prices or market not in ("spot","um"):
            raise ValueError("DUPLICATE_PRICE_SOURCE")
        if source.get("rows")!=288 or source.get("source_time_basis")!="BAR_OPEN_NOT_ORIGINAL_PUBLICATION":
            raise ValueError("UNVERIFIED_PRICE_SOURCE")
        prices[key]=kline_closes(load(source["r2_object_key"],source["publisher_sha256"],MAX_PRICE),market,symbol)
    if len(prices)!=6:raise ValueError("PRICE_PANEL_MISSING")
    flows={}
    source_receipts=[]
    for source in flow_report["files"]:
        if source.get("status")!="PUBLISHER_SHA_AND_SOURCE_EVENT_VERIFIED":
            raise ValueError("INVALID_FLOW_SOURCE_VERIFICATION")
        market=source["market"];symbol=source["symbol"];key=(market,symbol)
        if market not in ("spot","um") or key in flows or key not in prices:
            raise ValueError("FLOW_VENUE_OR_PRICE_PAIR_MISSING")
        if source.get("causal_rows_authorized")!=0 or source.get("historical_original_publication_time")!="UNVERIFIED":
            raise ValueError("FLOW_HISTORICAL_PIT_PROMOTED")
        # Full original raw ZIP SHA readback, plus independently checked derived CSV.
        raw=load(source["raw_r2_key"],source["publisher_sha256"],MAX_FLOW_ZIP)
        if not zipfile.is_zipfile(io.BytesIO(raw)):
            raise ValueError("FLOW_ORIGINAL_RAW_ZIP_INVALID")
        derived=load(source["derived_r2_key"],source["derived_sha256"],MAX_DERIVED)
        rows=read_flow_5m(derived)
        if len(rows)!=source["five_minute_slots_with_trades"]:
            raise ValueError("DERIVED_FLOW_ROWS_DO_NOT_MATCH_SOURCE")
        flows[key]=rows
        source_receipts.append({
            "market":market,"symbol":symbol,
            "original_sha256":source["publisher_sha256"],
            "derived_sha256":source["derived_sha256"],
            "five_minute_observed_slots":len(rows),
            "publisher_checksum_already_verified_in_origin_run":True,
            "source_event_only":True})
    if len(flows)!=4:raise ValueError("FLOW_COVERAGE_MISMATCH")
    by_source={}
    for (market,symbol),rows in sorted(flows.items()):
        by_source[f"{market}|{symbol}"]=diagnostics(prices[market,symbol],rows)
    # H6 specifically compares same-coin spot vs perp on identical UTC spots.
    h6={}
    for symbol in sorted({sym for _,sym in flows}):
        if ("spot",symbol) not in flows or ("um",symbol) not in flows:
            h6[symbol]={"status":"NO_MATCHED_SPOT_PERP_PAIR","causal_authorized":0}
            continue
        h6[symbol]={
            "status":"MATCHED_EVENT_LABELS_ONLY",
            **diagnostics(prices["spot",symbol],flows["um",symbol],
                          spot_flow=flows["spot",symbol]),
            "causal_authorized":0}
    return {"schema":SCHEMA,"scope":"RESEARCH_ONLY",
            "utc_day":DAY,"source_manifest_pins":{"price":PRICE_PIN,"flow":FLOW_PIN},
            "source_sha_verified_at_read":True,
            "source_file_receipts":source_receipts,
            "complete_price_asset_market_sources":len(prices),
            "flow_asset_market_sources":len(flows),
            "h1_h7_single_venue_flow_price":by_source,
            "h6_spot_perp_same_coin":h6,
            "observational_basis":"EVENT_TIME_AND_ARCHIVE_PROVENANCE_ONLY",
            "interpretation":"PRELIMINARY_DESCRIPTIVE_SINGLE_PRE_HOLDOUT_DAY",
            "independent_days":1,"confirmatory_holdout_used":False,
            "causal_h1_h6_h7_rows_authorized":0,"training_authorized":False,
            "historical_first_publication":"UNVERIFIED",
            "preregistered_h1_h6_h7_confirmatory":"BLOCKED",
            "edge_status":"EDGE_UNVALIDATED","trading_actions":False,
            "nav_capital_pnl_reserve_futures_unchanged":True}


def main():
    if os.environ.get("GITHUB_REPOSITORY")!="analiticprosp-ship-it/crypto-price-feed":
        raise ValueError("WRONG_REPOSITORY_FOR_RESEARCH")
    rid=os.environ["GITHUB_RUN_ID"];attempt=os.environ.get("GITHUB_RUN_ATTEMPT","1")
    if not rid.isdigit() or not attempt.isdigit():
        raise ValueError("RUN_ID_INVALID")
    s3=boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
                    aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
                    aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
    bucket=os.environ["R2_BUCKET"]
    result=build(read_pinned_report(s3,bucket,PRICE_PIN),
                 read_pinned_report(s3,bucket,FLOW_PIN),
                 lambda key,digest,cap: verified_bytes(s3,bucket,key,digest,cap))
    result["run_id"]=rid;result["run_attempt"]=attempt
    data=json.dumps(result,sort_keys=True,ensure_ascii=False,indent=2).encode()
    key=ROOT+"/run-reports/"+rid+"-"+attempt+".json"
    digest=put_immutable(s3,bucket,key,data)
    path=Path("detector_h1h10_event_only_diagnostics/summary.json")
    path.parent.mkdir(exist_ok=True,parents=True)
    path.write_text(json.dumps({**result,"r2_key":key,"sha256":digest},
                               indent=2,ensure_ascii=False),encoding="utf-8")
    brief={"day":DAY,"flow_sources":result["flow_asset_market_sources"],
           "matched_spot_perp_assets":[s for s,v in result["h6_spot_perp_same_coin"].items()
                                      if v["status"]=="MATCHED_EVENT_LABELS_ONLY"],
           "h6_pair_count":sum(v["status"]=="MATCHED_EVENT_LABELS_ONLY"
                               for v in result["h6_spot_perp_same_coin"].values()),
           "historical_publication":"UNVERIFIED","causal_authorized":0,
           "edge":"EDGE_UNVALIDATED","r2_key":key,"sha256":digest}
    print("H1H10_BINANCE_ONE_DAY_EVENT_ONLY_DIAGNOSTICS",json.dumps(brief,ensure_ascii=False),flush=True)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"],"a",encoding="utf-8") as f:
            f.write("## H1/H6/H7 single-day descriptive source audit; NOT a backtest\n\n")
            f.write(f"- Exact immutable pinned source manifests: {PRICE_PIN['sha256']}, {FLOW_PIN['sha256']}\n")
            f.write(f"- Matched Spot/Perp symbol count: {brief['h6_pair_count']}\n")
            f.write("- Only event timestamps, historical first available **UNVERIFIED**, confirmatory tests **BLOCKED**.\n")
            f.write(f"- R2 key: {key}; SHA256: {digest}\n")


if __name__=="__main__":
    main()
