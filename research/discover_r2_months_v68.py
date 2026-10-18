#!/usr/bin/env python3
"""Discover and validate new BTC/ETH full monthly R2 archives; no automatic replay inclusion."""
import hashlib,json,os,re
from pathlib import Path
import boto3
from datetime import datetime,timezone
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
# The original v6.5 module has import-time R2 side effects: load only read_month AST.
import ast
source=ast.parse((ROOT/"research/detector_matched_controls_v65.py").read_text())
func=next(n for n in source.body if isinstance(n,ast.FunctionDef) and n.name=="read_month")
ns={"hashlib":hashlib}
import csv,io,zipfile
ns.update(csv=csv,io=io,zipfile=zipfile,P5=300000)
exec(compile(ast.Module(body=[func],type_ignores=[]),"<read_month>","exec"),ns)
read_month=ns["read_month"]
s3=boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
bucket=os.environ["R2_BUCKET"]
baseline={"2024-09","2025-03","2025-09","2026-03","2026-09"}
today=datetime.now(timezone.utc).strftime("%Y-%m")
inventory={}
for sym in ("BTC","ETH"):
 prefix=f"binance/usdm/5m/{sym}USDT/"
 keys=[]
 for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket,Prefix=prefix):
  for obj in page.get("Contents",[]):
   key=obj["Key"]
   match=re.fullmatch(re.escape(prefix)+r"(20\d\d-(?:0[1-9]|1[0-2]))\.zip",key)
   if match and match.group(1)<today:keys.append(match.group(1))
 inventory[sym]=sorted(set(keys))
common=sorted((set(inventory["BTC"])&set(inventory["ETH"]))-baseline)
# Cap validation cost. Latest months first, to avoid loading all history in a single run.
selected=common[-6:]
results=[]
for month in selected:
 for sym in ("BTC","ETH"):
  rec={"symbol":sym,"month":month,"status":"BLOCKED"}
  try:
   bars,sha=read_month(s3,bucket,sym,month)
   start=datetime.fromtimestamp(bars[0]["t"]/1000,timezone.utc)
   end=datetime.fromtimestamp(bars[-1]["endMs"]/1000,timezone.utc)
   # Require complete UTC calendar month, not merely a gap-free partial archive.
   year,mon=map(int,month.split("-"))
   next_month=f"{year+1}-01" if mon==12 else f"{year}-{mon+1:02d}"
   expected_end=datetime.fromisoformat(next_month+"-01").replace(tzinfo=timezone.utc)
   if start!=datetime.fromisoformat(month+"-01").replace(tzinfo=timezone.utc) or end!=expected_end:
    raise ValueError("PARTIAL_MONTH")
   rec.update(status="VALIDATED_FULL_MONTH",sourceSha256=sha,bars15m=len(bars))
  except Exception as exc:rec["reason"]=type(exc).__name__+":"+str(exc)[:180]
  results.append(rec)
folder=Path("detector_v68_reports");folder.mkdir(exist_ok=True)
report={"version":"6.8","researchOnly":True,"mode":"DISCOVERY_ONLY","generatedAtUTC":datetime.now(timezone.utc).isoformat(),"baselineMonths":sorted(baseline),"inventoryCounts":{s:len(v) for s,v in inventory.items()},"commonAdditionalMonths":len(common),"validationBatch":selected,"results":results,"policy":"New months require research protocol review before replay inclusion; no live changes."}
(folder/"archive_discovery.json").write_text(json.dumps(report,indent=2,ensure_ascii=False))
valid=sorted({r["month"] for r in results if r["status"]=="VALIDATED_FULL_MONTH" and all(x["status"]=="VALIDATED_FULL_MONTH" for x in results if x["month"]==r["month"])})
print("ARCHIVE_DISCOVERY_COMPLETE "+json.dumps({"inventoryCounts":report["inventoryCounts"],"commonAdditionalMonths":len(common),"checked":len(selected),"validatedPairedMonths":valid,"blocked":len([r for r in results if r["status"]=="BLOCKED"])}))
