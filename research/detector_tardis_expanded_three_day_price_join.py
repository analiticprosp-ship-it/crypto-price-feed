#!/usr/bin/env python3
"""Independently verify expanded 3-day Tardis source and join price-asof + future labels.

Research-only new prefix; leave original 4-day datasets and model results intact.
"""
import json,os
from pathlib import Path
import boto3

from research.detector_tardis_fourday_independent_audit import (
 get_bytes,assert_digest,raw_snapshots,verify_derived
)
from research.detector_tardis_price_oi_forward_labels import (
 price_snapshots,price_asof_by_bucket,build_join,to_csv,store,
 FEATURE_FIELDS,LABEL_FIELDS
)
from research.detector_tardis_expansion_free_three_days import NEW_DAYS

SOURCE_ROOT="research/tardis-binance-oi-expansion/v1"
SOURCE_MANIFEST_SHA256="75db27426a90d1e877a1475c3470bbcbd0b666d3762327c7294d2b5098a17370"
ROOT="research/tardis-binance-expanded-price-5m-join/v1"
SYMBOLS=("BTCUSDT","ETHUSDT","SOLUSDT")
OUT=Path("detector_tardis_expanded_price_join")
OUT.mkdir(exist_ok=True)


def verify_source_item(entry,day,symbol):
 if (entry["day"]!=day or entry["symbol"]!=symbol
   or entry["original_key"]!=f"{SOURCE_ROOT}/{day}/{symbol}.csv.gz"
   or entry["derived_key"]!=f"{SOURCE_ROOT}/{day}/derived/{symbol}_vendor_asof_5m.csv"):
  raise ValueError("SOURCE_EXPANSION_KEY_MISMATCH")
 for name in ("source_sha256","derived_sha256"):
  if len(entry[name])!=64:raise ValueError("SOURCE_HASH_INVALID")


def main():
 bucket=os.environ["R2_BUCKET"]
 client=boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
    aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
    aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
 manifest_blob=get_bytes(client,bucket,SOURCE_ROOT+"/manifest.json",500000)
 assert_digest(manifest_blob,SOURCE_MANIFEST_SHA256)
 manifest=json.loads(manifest_blob)
 if (manifest.get("schema")!="detector-tardis-multiday-vendor-asof-v1"
     or tuple(manifest.get("dates",()))!=NEW_DAYS
     or tuple(manifest.get("symbols",()))!=SYMBOLS
     or len(manifest.get("records",()))!=9):
  raise ValueError("EXPANDED_SOURCE_SCHEMA_MISMATCH")
 entries=[]
 for day in NEW_DAYS:
  for symbol in SYMBOLS:
   items=[x for x in manifest["records"] if x["day"]==day and x["symbol"]==symbol]
   if len(items)!=1:raise ValueError("EXPANDED_SOURCE_AMBIGUOUS")
   meta=items[0];verify_source_item(meta,day,symbol)
   raw=get_bytes(client,bucket,meta["original_key"],10_000_000)
   oi_csv=get_bytes(client,bucket,meta["derived_key"],200_000)
   assert_digest(raw,meta["source_sha256"])
   assert_digest(oi_csv,meta["derived_sha256"])
   causal=verify_derived(raw_snapshots(raw,day,symbol),oi_csv,day,symbol)
   observed,quality=price_snapshots(raw,day,symbol)
   prices=price_asof_by_bucket(observed,day)
   features,labels=build_join(day,symbol,oi_csv,prices)
   base=f"{ROOT}/{day}"
   feature_key=base+"/"+symbol+"_vendor_asof_features.csv"
   label_key=base+"/"+symbol+"_future_price_labels.csv"
   feature_hash=store(client,bucket,feature_key,to_csv(features,FEATURE_FIELDS),"text/csv")
   label_hash=store(client,bucket,label_key,to_csv(labels,LABEL_FIELDS),"text/csv")
   item={"day":day,"symbol":symbol,
         "raw_source_key":meta["original_key"],"raw_source_sha256":meta["source_sha256"],
         "derived_oi_sha256":meta["derived_sha256"],"independent_causal_audit":causal,
         "features_key":feature_key,"features_sha256":feature_hash,
         "labels_key":label_key,"labels_sha256":label_hash,
         "rows":len(features),
         "valid_price_oi":sum(x["price_oi_feature_quality"]=="OK_VENDOR_ASOF" for x in features),
         "future_15m_labels":sum(bool(x["future_last_price_return_15m"]) for x in labels),
         "future_60m_labels":sum(bool(x["future_last_price_return_60m"]) for x in labels),
         "price_source_quality":quality}
   entries.append(item)
   print("EXPANDED_PRICE_JOIN_ROW",json.dumps({k:v for k,v in item.items() if k!="price_source_quality"},ensure_ascii=False),flush=True)
 report={"schema":"detector-tardis-expanded-three-day-price-oi-join-v1",
   "status":"EXPANDED_THREE_DAY_PRICE_JOIN_VERIFIED",
   "research_only":True,"trade_actions":False,"edge_status":"EDGE_UNVALIDATED",
   "source_manifest_key":SOURCE_ROOT+"/manifest.json",
   "source_manifest_sha256":SOURCE_MANIFEST_SHA256,
   "days":list(NEW_DAYS),"symbols":list(SYMBOLS),"outputs":entries,
   "totals":{"feature_rows":sum(x["rows"] for x in entries),
             "valid_price_oi":sum(x["valid_price_oi"] for x in entries),
             "label_15m":sum(x["future_15m_labels"] for x in entries),
             "label_60m":sum(x["future_60m_labels"] for x in entries),
             "lookahead_records":0},
   "limits":["Tardis vendor receipts, NOT Binance publication time",
             "Free first-day sample, not random market selection",
             "All future labels stored in separate hashed files",
             "Not H1-H10 confirmatory test; no trading signals"],
   "run_id":os.environ["GITHUB_RUN_ID"]}
 blob=json.dumps(report,ensure_ascii=False,indent=2,sort_keys=True).encode()
 key=ROOT+"/manifest-"+os.environ["GITHUB_RUN_ID"]+".json"
 digest=store(client,bucket,key,blob,"application/json")
 (OUT/"report.json").write_text(json.dumps({**report,"r2_manifest_key":key,
  "r2_manifest_sha256":digest},ensure_ascii=False,indent=2))
 print("EXPANDED_PRICE_JOIN_SUMMARY",json.dumps({"status":report["status"],
   "totals":report["totals"],"r2_manifest_key":key,"sha256":digest,
   "edge_status":"EDGE_UNVALIDATED"},ensure_ascii=False),flush=True)

if __name__=="__main__":main()
