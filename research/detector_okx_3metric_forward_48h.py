#!/usr/bin/env python3
"""Prospective OKX same-venue OI+perp candle+taker-flow observer (48h research).

Three actual, independent REST response-received timestamps per instrument.
Persist raw polls, revisions, and sampled first-observed upper bounds to R2.
Source labels / stored history NEVER confer exchange-first-publication PIT.
Every document is SHA256 read back. Limited 48-hour best-effort GitHub cron;
no paid API, execution, predictive training or portfolio writeback.
"""
import datetime as dt
import hashlib
import json
import math
import os
import time
import urllib.parse
import urllib.request

import boto3
from research.detector_okx_oi_48h_pilot import poll as poll_oi
from research.detector_okx_oi_48h_pilot import store,load,disable_own_workflow

SYMBOLS=("BTC-USDT-SWAP","ETH-USDT-SWAP","SOL-USDT-SWAP")
METRICS=("oi","price","flow")
PREFIX="research/detector-okx-3metric-forward/v1"
SCHEMA="detector-okx-3metric-prospective-v1"
P5=300000
DURATION_MS=48*3600000
MAX_BYTES=180000
MAX_ROWS=100

def now_ms():return int(time.time()*1000)
def utc(ms):return dt.datetime.fromtimestamp(ms/1000,dt.timezone.utc).isoformat()
def sha(row):return hashlib.sha256(json.dumps(row,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()

def finite_nonnegative(value,positive=False):
    try:
        n=float(value)
        if not math.isfinite(n) or n<0 or (positive and n==0):
            raise ValueError("NONFINITE_OR_INVALID_AMOUNT")
    except (TypeError,ValueError,OverflowError) as exc:
        raise ValueError("NONFINITE_OR_INVALID_AMOUNT") from exc
    return str(value)

def parse_rows(metric,payload,inst,received):
    """Do not impute missing 5m labels or assume data availability from row ts."""
    if not isinstance(payload,dict) or str(payload.get("code"))!="0":
        raise ValueError("OKX_API_CODE_NOT_ZERO")
    data=payload.get("data")
    if not isinstance(data,list) or not 1<=len(data)<=MAX_ROWS:
        raise ValueError("SOURCE_ROWS_EMPTY_OR_OVERSIZE")
    result=[];seen=set()
    for row in data:
        if not isinstance(row,list):raise ValueError("SOURCE_ROW_NOT_ARRAY")
        if (metric=="price" and len(row)<9 or
            metric=="flow" and len(row)<3 or
            metric=="oi" and len(row)<2):
            raise ValueError("SOURCE_ROW_SCHEMA_INVALID")
        try:source_label=int(row[0])
        except (TypeError,ValueError) as exc:raise ValueError("SOURCE_LABEL_INVALID") from exc
        if (source_label < 1600000000000 or source_label>received+60000
           or source_label%P5!=0 or source_label in seen):
            raise ValueError("SOURCE_LABEL_DUPLICATE_OR_OFFGRID")
        seen.add(source_label)
        if metric=="price":
            if row[8] not in ("0","1"):raise ValueError("PRICE_CONFIRM_INVALID")
            for n in row[1:5]:finite_nonnegative(n,positive=True)
            value={"open":str(row[1]),"high":str(row[2]),"low":str(row[3]),
                   "close":str(row[4]),"confirm":str(row[8]),
                   "source_bar_open_ms":source_label,
                   "source_bar_nominal_end_ms":source_label+P5}
        elif metric=="flow":
            sell=finite_nonnegative(row[1]);buy=finite_nonnegative(row[2])
            value={"sell_native":sell,"buy_native":buy,
                   "side_order":"SELL_THEN_BUY",
                   "requested_unit":"1",
                   "bucket_anchor_time_semantics":"UNVERIFIED_BY_SOURCE_RELEASE"}
        else:
            qty=finite_nonnegative(row[1],positive=True)
            value={"native_open_interest":qty,"raw_row":row,
                   "units":"NATIVE_OI_INSTRUMENT_SIZE_UNVERIFIED",
                   "bucket_anchor_time_semantics":"UNVERIFIED_BY_SOURCE_RELEASE"}
        result.append({"label_ms":source_label,"raw_sha256":sha(row),"data":value})
    result.sort(key=lambda x:x["label_ms"])
    return result

ENDPOINTS={
    "price":("/api/v5/market/candles",{"bar":"5m","limit":"20"}),
    "flow":("/api/v5/rubik/stat/taker-volume-contract",{"period":"5m","unit":"1","limit":"20"}),
}
def poll_other(metric,inst):
    if metric not in ENDPOINTS:raise ValueError("UNSUPPORTED_METRIC")
    path,parameters=ENDPOINTS[metric]
    args={"instId":inst,**parameters}
    url="https://www.okx.com"+path+"?"+urllib.parse.urlencode(args)
    request=urllib.request.Request(url,headers={
        "Accept":"application/json","User-Agent":"H1H10-Prospective-Research/1.0"})
    started=now_ms();mono=time.monotonic_ns()
    with urllib.request.urlopen(request,timeout=15) as reply:
        if reply.status!=200:raise ValueError("OKX_HTTP_STATUS")
        response=reply.read(MAX_BYTES+1)
        server_date=reply.headers.get("Date")
    received=now_ms()
    if len(response)>MAX_BYTES:raise ValueError("HTTP_BODY_EXCEEDS_CAP")
    return {"schema":SCHEMA,"metric":metric,"symbol":inst,"provider":"OKX",
        "request_start_ms":started,"response_received_ms":received,
        "round_trip_ms":(time.monotonic_ns()-mono)//1000000,
        "server_http_date":server_date,"rows":parse_rows(metric,json.loads(response),inst,received),
        "source_endpoint":path,
        "receipt_semantics":"LOCAL_HTTP_RESPONSE_OBSERVED_NOT_EXCHANGE_PUBLICATION",
        "research_only":True}

def poll_source(metric,inst):
    if metric!="oi":return poll_other(metric,inst)
    original=poll_oi(inst)
    # Reuse already tested OKX REST call and normalize its envelope without
    # assuming raw OI amount is measured in USD or exchange first-published now.
    received=original["response_received_ms"]
    encoded={"code":"0","data":[r["raw"] for r in original["rows"]]}
    return {"schema":SCHEMA,"metric":"oi","symbol":inst,"provider":"OKX",
        "request_start_ms":original["request_start_ms"],"response_received_ms":received,
        "round_trip_ms":original["response_round_trip_ms"],
        "server_http_date":original.get("server_date_header"),
        "rows":parse_rows("oi",encoded,inst,received),
        "source_endpoint":original["api"],
        "receipt_semantics":"LOCAL_HTTP_RESPONSE_OBSERVED_NOT_EXCHANGE_PUBLICATION",
        "research_only":True}

def reconcile(previous,current):
    """First OBSERVATION: not an inferred original first-release timestamp."""
    now=current["response_received_ms"]
    if previous is None:
        return [],[],True
    if (previous.get("metric")!=current["metric"] or
        previous.get("symbol")!=current["symbol"] or
        not isinstance(previous.get("rows"),list) or
        now<=previous.get("response_received_ms",-1)):
        raise ValueError("PREVIOUS_POLL_IDENTITY_OR_CLOCK_INVALID")
    past={x["label_ms"]:x for x in previous["rows"]}
    last=max(past) if past else -1
    known_before=previous["response_received_ms"]
    first=[];revised=[]
    for x in current["rows"]:
        label=x["label_ms"]
        if label not in past:
            absent=(label>last and known_before>=label)
            first.append({"schema":SCHEMA,"symbol":current["symbol"],
                 "metric":current["metric"],"source_label_ms":label,
                 "first_observed_ms":now,"last_observed_absent_ms":known_before if absent else None,
                 "kind":"SAMPLED_ABSENT_THEN_PRESENT" if absent else "FIRST_OBSERVATION_ONLY",
                 "raw_sha256":x["raw_sha256"],
                 "never_original_exchange_publication":True})
        elif past[label]["raw_sha256"]!=x["raw_sha256"]:
            revised.append({"label_ms":label,"observed_at_ms":now,
                 "old_sha256":past[label]["raw_sha256"],
                 "new_sha256":x["raw_sha256"]})
    return first,revised,False

def coverage_gate(polls):
    """Never upgrade labels into PIT rows, even where 3 labels coincide."""
    by_symbol={}
    for instrument in SYMBOLS:
        streams={k:polls.get((instrument,k)) for k in METRICS}
        missing=[k for k,x in streams.items() if x is None]
        matched=[]
        if not missing:
            common=set.intersection(*(
                {x["label_ms"] for x in streams[k]["rows"]} for k in METRICS))
            for label in sorted(common):
                # No first-release claim. The source tick/bucket clock is not
                # uniformly documented as event open/end for each endpoint.
                matched.append(label)
        by_symbol[instrument]={
          "source_label_triples":len(matched),
          "last_common_source_label_ms":matched[-1] if matched else None,
          "missing_streams":missing,
          "join_grade":"SOURCE_LABEL_OVERLAP_ONLY_NO_CAUSAL_PIT",
          "causal_5m_rows_authorized":0,
          "training_authorized":False}
    return by_symbol

def main():
    run=os.environ["GITHUB_RUN_ID"];attempt=os.environ.get("GITHUB_RUN_ATTEMPT","1")
    bucket=os.environ["R2_BUCKET"]
    s3=boto3.client("s3",
        endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
    config_key=PREFIX+"/config.json";config=load(s3,bucket,config_key)
    if config is None:
        start=now_ms()
        config={"schema":SCHEMA,"start_ms":start,"end_ms":start+DURATION_MS,
          "duration_hours":48,"research_only":True}
        store(s3,bucket,config_key,config)
    if (config.get("schema")!=SCHEMA or
        config.get("end_ms",0)-config.get("start_ms",0)!=DURATION_MS or
        config.get("research_only") is not True):
        raise ValueError("UNTRUSTED_PILOT_CONFIGURATION")
    if now_ms()>=config["end_ms"]:
        # This research workflow self-disables; no long-lived paid infrastructure.
        workflow=os.environ["GITHUB_REPOSITORY"]
        req=urllib.request.Request(
           "https://api.github.com/repos/"+workflow+
           "/actions/workflows/detector-okx-3metric-forward-48h.yml/disable",
           data=b"",method="PUT",headers={
            "Authorization":"Bearer "+os.environ["GH_TOKEN"],
            "Accept":"application/vnd.github+json",
            "User-Agent":"H1H10-Prospective-Research/1.0"})
        with urllib.request.urlopen(req,timeout=20) as r:
            if r.status!=204:raise ValueError("SELF_DISABLE_UNVERIFIED")
        print("THREE_METRIC_PILOT_STOPPED",utc(config["end_ms"]))
        return
    all_polls={};problems=[];new_obs=0;revisions=0
    for instrument in SYMBOLS:
        for metric in METRICS:
            try:
                current=poll_source(metric,instrument)
                state_key=PREFIX+"/state/"+instrument+"/"+metric+".json"
                previous=load(s3,bucket,state_key)
                first,changed,bootstrap=reconcile(previous,current)
                poll_key=(PREFIX+"/polls/"+utc(current["response_received_ms"])[:10]+
                   "/"+run+"-"+attempt+"-"+instrument+"-"+metric+".json")
                store(s3,bucket,poll_key,current)  # Raw before changing last state.
                for item in first:
                    key=PREFIX+"/first-observed/"+instrument+"/"+metric+"/"+str(item["source_label_ms"])+".json"
                    existing=load(s3,bucket,key)
                    if existing is None:
                        store(s3,bucket,key,item)
                        new_obs+=1
                    elif (existing.get("first_observed_ms",-1)>item["first_observed_ms"]
                          or existing.get("raw_sha256")!=item["raw_sha256"]):
                        raise ValueError("IMMUTABLE_FIRST_OBSERVATION_CONFLICT")
                for item in changed:
                    key=(PREFIX+"/revisions/"+instrument+"/"+metric+"/"+
                         str(item["label_ms"])+"/"+run+"-"+attempt+".json")
                    store(s3,bucket,key,item)
                    revisions+=1
                store(s3,bucket,state_key,current)
                all_polls[(instrument,metric)]=current
                print("THREE_METRIC_SOURCE",instrument,metric,
                    "rows",len(current["rows"]),"new",len(first),
                    "bootstrap",bootstrap,flush=True)
            except Exception as err:
                problems.append({"symbol":instrument,"metric":metric,
                    "error_type":type(err).__name__,"error":str(err)[:100]})
    summary={"schema":SCHEMA,"run":run,"attempt":attempt,
       "status":"SOURCES_ALL_RECEIVED" if not problems else "PARTIAL_SOURCE_FAILURE",
       "observed_at_utc":utc(now_ms()),"pilot_end_utc":utc(config["end_ms"]),
       "source_reports":{i+"|"+m:{
          "response_received_ms":r["response_received_ms"],
          "row_count":len(r["rows"])} for (i,m),r in all_polls.items()},
       "coverage_gate":coverage_gate(all_polls),
       "first_observations_saved":new_obs,"revisions_saved":revisions,
       "errors":problems,"edge_status":"EDGE_UNVALIDATED",
       "original_exchange_first_publication":"UNVERIFIED",
       "causal_join_training":"BLOCKED",
       "scope":"RESEARCH_ONLY","trading_actions":False}
    k=PREFIX+"/run-reports/"+run+"-"+attempt+".json"
    stamp=store(s3,bucket,k,summary)
    print("H1H10_OKX_3METRIC_FORWARD",json.dumps({
      "status":summary["status"],"sources_ok":len(all_polls),
      "sources_failed":len(problems),"first_obs":new_obs,
      "common_labels_by_symbol":{k:v["source_label_triples"] for k,v in summary["coverage_gate"].items()},
      "causal_authorized":0,"r2_key":k,"sha256":stamp},ensure_ascii=False),flush=True)
    location=os.environ.get("GITHUB_STEP_SUMMARY")
    if location:
        with open(location,"a",encoding="utf-8") as output:
            output.write("## OKX forward 3-metric (RESEARCH_ONLY)\n\n")
            output.write(f"- Sources: {len(all_polls)}/9; errors: {len(problems)}\n")
            output.write(f"- New observed rows: {new_obs}\n")
            output.write("- Original exchange release: UNVERIFIED; causal H1–H10: BLOCKED\n")
            output.write(f"- Immutable run report: \`{k}\`\n")
    if problems:raise SystemExit(2)
if __name__=="__main__":main()
