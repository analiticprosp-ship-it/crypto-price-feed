#!/usr/bin/env python3
"""Research-only timing audit of aggregated trades vs Tardis OI+prices, 2026-09-01.

This is an EVENT-BOUNDARY audit, NOT original aggTrade publication-time proof.
Source aggTrade ZIPs were archived as hashes in upstream manifest, but the
aggregated CSV itself is sourced from verified R2 GitHub artifact.
"""
import csv
import datetime as dt
import hashlib
import io
import json
import math
import os
import pathlib
import re
import boto3

DAY="2026-09-01"
SYMBOLS=("BTCUSDT","ETHUSDT","SOLUSDT")
VENUES=("spot","perp")
FLOW=pathlib.Path("flow")
ROOT="research/tardis-binance-oi-price-5m-join/v1"
OUT=pathlib.Path("detector_flow_boundary_audit")
OUT.mkdir(exist_ok=True)
EXPECTED=288

def us(value):
 t=dt.datetime.fromisoformat(str(value).replace("Z","+00:00"))
 if t.tzinfo is None:raise ValueError("UTC_OFFSET_REQUIRED")
 return int(t.timestamp()*1_000_000)

def assert_sha(data,digest):
 if hashlib.sha256(data).hexdigest()!=digest:
  raise ValueError("R2_SOURCE_SHA256_FAIL")

def read(s3,bucket,key,max_len):
 obj=s3.get_object(Bucket=bucket,Key=key)
 if not 0<int(obj["ContentLength"])<=max_len:raise ValueError("SOURCE_SIZE_LIMIT")
 b=obj["Body"].read(max_len+1)
 if len(b)>max_len:raise ValueError("SOURCE_READ_LIMIT")
 return b

def choose_price_manifest(s3,bucket):
 choices=[]
 for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket,Prefix=ROOT+"/manifest-"):
  for obj in page.get("Contents",[]):
   name=obj["Key"]
   if re.fullmatch(re.escape(ROOT)+r"/manifest-[0-9]+\.json",name):
    run_id=int(name.split("manifest-")[-1].removesuffix(".json"))
    choices.append((run_id,name))
 if not choices:raise ValueError("PRICE_SOURCE_MANIFEST_MISSING")
 run,key=max(choices)
 raw=read(s3,bucket,key,250000)
 doc=json.loads(raw)
 if doc.get("schema")!="detector-h1-h10-tardis-price-oi-forward-targets-v1" or str(doc.get("run_id"))!=str(run):
  raise ValueError("PRICE_SOURCE_MANIFEST_SCHEMA_INVALID")
 return doc,key,hashlib.sha256(raw).hexdigest()

def validate_flow(rows,day,market,symbol):
 """Full 5m bucket uses source event-times from aggTrades, not bar publication."""
 if not rows:raise ValueError("EMPTY_FLOW_SOURCE")
 day_start=us(day+"T00:00:00+00:00")
 daily={}
 before=0
 for row in rows:
  t=us(row["timestamp_utc"])
  if t<day_start or t>=day_start+86_400_000_000:
   before+=1
   continue
  if t in daily:raise ValueError("DUPLICATE_FLOW_BUCKET")
  if (t-day_start)%300_000_000:raise ValueError("FLOW_BUCKET_NOT_ALIGNED")
  fields=("taker_buy_quote","taker_sell_quote","delta_quote","total_quote")
  try:
   buy,sell,delta,total=map(lambda k:float(row[k]),fields)
   count=int(row["aggtrade_count"])
  except (ValueError,TypeError,KeyError) as exc:raise ValueError("FLOW_ROW_PARSE_ERROR") from exc
  if not all(math.isfinite(x) for x in (buy,sell,delta,total)) or min(buy,sell,total)<0 or count<1:
   raise ValueError("INVALID_FLOW_METRIC")
  tol=max(0.001,total*1e-10)
  if abs(buy+sell-total)>tol or abs(buy-sell-delta)>tol:
   raise ValueError("AGGTRADE_FLOW_ACCOUNTING_MISMATCH")
  daily[t]=row
 return daily,{"market":market,"symbol":symbol,"day":day,
               "source_rows_full_3day":len(rows),
               "other_day_rows":before,"selected_5m_buckets":len(daily),
               "missing_5m_buckets":288-len(daily)}

def audit(symbol,spot,perp,price_rows):
 start=us(DAY+"T00:00:00+00:00")
 if len(price_rows)!=288:raise ValueError("PRICE_SOURCE_ROW_COUNT")
 results={"symbol":symbol,"slots":0,"spot_flow_available":0,"perp_flow_available":0,
          "both_flow_and_price_oi_aligned":0,"closed_5m_boundary_violations":0,
          "source_publication_time":"AGGTRADES_PUBLICATION_UNVERIFIED"}
 for i,row in enumerate(price_rows):
  begin=start+i*300_000_000
  end=begin+300_000_000
  decision=end+30_000_000
  if (row["symbol"]!=symbol or us(row["bucket_end_utc"])!=end or
      us(row["decision_time_utc"])!=decision):
   raise ValueError("PRICE_OI_BOUNDARY_ALIGNMENT_FAIL")
  if row["last_price_vendor_receipt_utc"] and us(row["last_price_vendor_receipt_utc"])>decision:
   raise ValueError("FUTURE_PRICE_IN_FEATURE")
  if row["oi_vendor_receipt_utc"] and us(row["oi_vendor_receipt_utc"])>decision:
   raise ValueError("FUTURE_OI_IN_FEATURE")
  if decision<end:results["closed_5m_boundary_violations"]+=1
  has_spot=begin in spot;has_perp=begin in perp
  results["spot_flow_available"]+=int(has_spot)
  results["perp_flow_available"]+=int(has_perp)
  if has_spot and has_perp and row["price_oi_feature_quality"]=="OK_VENDOR_ASOF":
   results["both_flow_and_price_oi_aligned"]+=1
  results["slots"]+=1
 return results

def main():
 provenance=json.loads((FLOW/"_r2_provenance.json").read_text())
 if provenance.get("status")!="HASH_VERIFIED_NOT_PUBLICATION_TIME_VALIDATED" or (
     provenance.get("workflow")!="Detector H1-H10 Three-Day Real AggTrades Expansion"):
  raise ValueError("FLOW_R2_PROVENANCE_INVALID")
 manifest=json.loads((FLOW/"manifest.json").read_text())
 if tuple(manifest.get("dates",[]))!=("2026-09-01","2026-09-02","2026-09-03"):
  raise ValueError("FLOW_SOURCE_DATES_MISMATCH")
 bucket=os.environ["R2_BUCKET"]
 s3=boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
                 aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
                 aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
 price_manifest,key,sha=choose_price_manifest(s3,bucket)
 sources=[];aligned=[]
 for symbol in SYMBOLS:
  flows={}
  for market in VENUES:
   file=FLOW/f"{market}_{symbol}_2026-09-01_to_03_5m.csv"
   with file.open(newline="") as handle:
    rows=list(csv.DictReader(handle))
   flows[market],quality=validate_flow(rows,DAY,market,symbol)
   sources.append(quality)
  match=[x for x in price_manifest["outputs"] if x["day"]==DAY and x["symbol"]==symbol]
  if len(match)!=1:raise ValueError("PRICE_SOURCE_RECORD_AMBIGUOUS")
  data=read(s3,bucket,match[0]["features_key"],150000)
  assert_sha(data,match[0]["features_sha256"])
  price_rows=list(csv.DictReader(io.StringIO(data.decode("utf-8-sig"))))
  report=audit(symbol,flows["spot"],flows["perp"],price_rows)
  aligned.append(report)
  print("FLOW_BOUNDARY_ASOF",json.dumps(report,ensure_ascii=False),flush=True)
 summary={
  "schema":"detector-h1h10-flow-0901-event-boundary-v1",
  "status":"FLOW_EVENT_BOUNDARY_PASS" if all(x["both_flow_and_price_oi_aligned"]==288 for x in aligned) else "FLOW_EVENT_BOUNDARY_PARTIAL",
  "date":DAY,"market_pairs":"Binance Spot and Binance USDM perp BTC/ETH/SOL",
  "source_flow_artifact_sha256":provenance["archive_sha256"],
  "source_flow_run_id":provenance["run_id"],
  "price_r2_manifest_key":key,"price_r2_manifest_sha256":sha,
  "total_5m_asset_slots":sum(x["slots"] for x in aligned),
  "both_flow_and_price_oi_aligned":sum(x["both_flow_and_price_oi_aligned"] for x in aligned),
  "flow_sources":sources,"aligned":aligned,
  "strict_limitation":"AggTrades archived event timestamps confirm bucket membership, NOT vendor first publication or availability to execution at end+30s",
  "actionability":"NO_PREDICTIVE_H1H10_TEST_WITH_FULL_FLOW_UNTIL_FLOW_AVAILABLE_AT_VERIFIED",
  "research_only":True,"trades":False,"edge_status":"EDGE_UNVALIDATED",
  "run_id":os.environ["GITHUB_RUN_ID"]
 }
 blob=json.dumps(summary,sort_keys=True,ensure_ascii=False,indent=2).encode()
 result_key=("research/tardis-binance-flow-event-boundary/v1/"+
             os.environ["GITHUB_RUN_ID"]+"-"+os.environ.get("GITHUB_RUN_ATTEMPT","1")+".json")
 digest=hashlib.sha256(blob).hexdigest()
 s3.put_object(Bucket=bucket,Key=result_key,Body=blob,ContentType="application/json",Metadata={"sha256":digest})
 assert_sha(read(s3,bucket,result_key,len(blob)+1),digest)
 (OUT/"report.json").write_text(json.dumps({**summary,"r2_report_key":result_key,"r2_sha256":digest},ensure_ascii=False,indent=2))
 print("FLOW_BOUNDARY_AUDIT_SUMMARY",json.dumps({"status":summary["status"],
       "asset_slots":summary["total_5m_asset_slots"],
       "joint_coverage":summary["both_flow_and_price_oi_aligned"],
       "r2_report_key":result_key,"sha256":digest,"publication":"UNVERIFIED"},ensure_ascii=False),flush=True)
 if os.environ.get("GITHUB_STEP_SUMMARY"):
  with open(os.environ["GITHUB_STEP_SUMMARY"],"a",encoding="utf-8") as fp:
   fp.write("## H1-H10 flow event-boundary (NOT publication) audit\n\n")
   fp.write(f"- Joint data coverage: {summary['both_flow_and_price_oi_aligned']}/{summary['total_5m_asset_slots']}\n")
   fp.write("- Historical aggTrades first-availability: NOT VERIFIED; no predictive edge tests allowed.\n")

if __name__=="__main__":main()
