#!/usr/bin/env python3
"""Archive a single freely accessible Tardis 2026-10-01 Binance OI sample day.

This is vendor-received REST openInterest snapshots, NOT Binance 5m sum OI.
The local_timestamp makes vendor-receipt as-of research possible for this sample.
No account, API token, paid plan, trades or backtest claims.
"""
import csv,datetime as dt,gzip,hashlib,io,json,math,os,urllib.request
import boto3

DAY="2026-10-01"
SYMBOLS=("BTCUSDT","ETHUSDT","SOLUSDT")
PREFIX="research/tardis-binance-oi-sample/v1/"+DAY
LIMIT_ZIP=8_000_000
LIMIT_ROWS=150_000
LIMIT_UNCOMPRESSED=35_000_000
BUCKET_US=300_000_000
DAY_START=int(dt.datetime(2026,10,1,tzinfo=dt.timezone.utc).timestamp()*1_000_000)
DAY_END=DAY_START+86400*1_000_000

def get_sample(symbol):
 url=f"https://datasets.tardis.dev/v1/binance-futures/derivative_ticker/2026/10/01/{symbol}.csv.gz"
 req=urllib.request.Request(url,headers={"User-Agent":"Detector-H1H10-Research/1.0","Accept":"application/gzip"})
 with urllib.request.urlopen(req,timeout=65) as resp:
  if resp.status!=200:raise ValueError("TARDIS_SAMPLE_HTTP_INVALID")
  chunks=[];size=0
  while True:
   block=resp.read(512_000)
   if not block:break
   size+=len(block)
   if size>LIMIT_ZIP:raise ValueError("COMPRESSED_SAMPLE_TOO_LARGE")
   chunks.append(block)
 blob=b"".join(chunks)
 if blob[:2]!=bytes([0x1f,0x8b]):raise ValueError("TARDIS_SAMPLE_NOT_GZIP")
 return blob

def inspect(blob,symbol):
 counts={"rows":0,"valid_open_interest":0,"empty_open_interest":0,
         "non_monotonic_local":0,"negative_exchange_to_local_ms":0,
         "outside_local_day":0,"invalid_timestamp":0}
 buck=set();earliest=None;latest=None;previous=None;headers=None;total=0
 with gzip.GzipFile(fileobj=io.BytesIO(blob)) as gz:
  stream=io.TextIOWrapper(gz,encoding="utf-8-sig",newline="")
  rd=csv.DictReader(stream);headers=rd.fieldnames or []
  if not {"symbol","timestamp","local_timestamp","open_interest"}.issubset(headers):
   raise ValueError("REQUIRED_TARDIS_HEADERS_MISSING")
  for row in rd:
   counts["rows"]+=1
   total+=sum(len(v or "") for v in row.values())+len(headers)
   if counts["rows"]>LIMIT_ROWS or total>LIMIT_UNCOMPRESSED:
    raise ValueError("TARDIS_SAMPLE_UNCOMPRESSED_LIMIT")
   if row["symbol"]!=symbol:raise ValueError("TARDIS_SYMBOL_MISMATCH")
   try:
    local=int(row["local_timestamp"]);source=int(row["timestamp"])
   except (ValueError,TypeError):
    counts["invalid_timestamp"]+=1;continue
   if not 1600000000000000<=local<=1900000000000000:
    counts["invalid_timestamp"]+=1;continue
   if previous is not None and local<previous:counts["non_monotonic_local"]+=1
   previous=local
   if local<source:counts["negative_exchange_to_local_ms"]+=1
   if not DAY_START<=local<DAY_END:counts["outside_local_day"]+=1
   earliest=local if earliest is None else min(earliest,local)
   latest=local if latest is None else max(latest,local)
   value=row.get("open_interest","")
   if not value:counts["empty_open_interest"]+=1;continue
   try:
    num=float(value)
    if not math.isfinite(num) or num<0:raise ValueError("OI_BAD_NUMBER")
   except (ValueError,TypeError):
    counts["empty_open_interest"]+=1;continue
   counts["valid_open_interest"]+=1
   if DAY_START<=local<DAY_END:buck.add((local-DAY_START)//BUCKET_US)
 if counts["rows"]==0 or counts["valid_open_interest"]==0:
  raise ValueError("TARDIS_OI_SAMPLE_EMPTY")
 return {"symbol":symbol,"date":DAY,"csv_headers":headers,"counts":counts,
         "five_minute_buckets_with_observed_oi":len(buck),
         "possible_5m_buckets_per_utc_day":288,
         "first_local_timestamp_us":earliest,
         "last_local_timestamp_us":latest,
         "quality_gate":"SAMPLE_FIELDS_VALIDATED_NOT_PREDICTIVE_BACKTEST"}

def store(s3,bucket,key,data,content_type):
 sha=hashlib.sha256(data).hexdigest()
 s3.put_object(Bucket=bucket,Key=key,Body=data,ContentType=content_type,Metadata={"sha256":sha})
 reread=s3.get_object(Bucket=bucket,Key=key)["Body"].read(len(data)+1)
 if hashlib.sha256(reread).hexdigest()!=sha:raise ValueError("R2_READBACK_SHA256_MISMATCH")
 return sha

def main():
 bucket=os.environ["R2_BUCKET"]
 s3=boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
                 aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
                 aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
 records=[]
 for symbol in SYMBOLS:
  blob=get_sample(symbol)
  report=inspect(blob,symbol)
  key=PREFIX+"/"+symbol+".csv.gz"
  report["r2_key"]=key
  report["compressed_bytes"]=len(blob)
  report["compressed_sha256"]=store(s3,bucket,key,blob,"application/gzip")
  records.append(report)
  print("TARDIS_OI_SAMPLE",json.dumps({"symbol":symbol,"rows":report["counts"]["rows"],
        "valid_oi":report["counts"]["valid_open_interest"],
        "buckets":report["five_minute_buckets_with_observed_oi"],
        "r2_sha256":report["compressed_sha256"]}),flush=True)
 manifest={"schema":"detector-tardis-binance-oi-receipt-asof-sample-v1",
    "sample_day":DAY,"provider":"Tardis.dev","underlying_exchange":"Binance USD-M Futures",
    "source_type":"derivative_ticker; vendor REST snapshots; not Binance 5m OI history",
    "research_only":True,"github_run_id":os.environ["GITHUB_RUN_ID"],
    "source_commit_sha":os.environ.get("GITHUB_SHA"),
    "archived_at_utc":dt.datetime.now(dt.timezone.utc).isoformat(),
    "records":records,"download_access":"first-of-month free samples",
    "causality_rule":"Only vendor local_timestamp<=research decision time; source timestamp alone unsafe",
    "limitations":["Tardis receiving time is not first publication time on Binance",
       "Vendor replay may have missing observations during outages",
       "A single free sample day is insufficient for out-of-sample strategy validation",
       "These are OI snapshots rather than Binance 5m archive metrics"]}
 manifest_bytes=json.dumps(manifest,ensure_ascii=False,sort_keys=True,indent=2).encode()
 manifest_key=PREFIX+"/manifest.json"
 digest=store(s3,bucket,manifest_key,manifest_bytes,"application/json")
 result={"status":"TARDIS_SAMPLE_R2_PASS","day":DAY,"run_id":os.environ["GITHUB_RUN_ID"],
         "manifest_key":manifest_key,"manifest_sha256":digest,
         "symbols":{r["symbol"]:{"rows":r["counts"]["rows"],
          "valid_oi":r["counts"]["valid_open_interest"],
          "bucket_coverage":r["five_minute_buckets_with_observed_oi"],
          "sha256":r["compressed_sha256"]} for r in records},
         "publication_time":"VENDOR_RECEIPT_ONLY"}
 print("TARDIS_OI_SAMPLE_R2",json.dumps(result,ensure_ascii=False),flush=True)
 if os.environ.get("GITHUB_STEP_SUMMARY"):
  with open(os.environ["GITHUB_STEP_SUMMARY"],"a",encoding="utf-8") as fp:
   fp.write("## Tardis Binance OI one-day receipt-time sample\n\n")
   fp.write(f"- Result: {result['status']}\n- UTC day: {DAY}\n")
   for sym,x in result["symbols"].items():
    fp.write(f"- {sym}: {x['rows']} rows, OI valid {x['valid_oi']}, covered 5m buckets {x['bucket_coverage']}/288\n")
   fp.write("- Decision as-of uses vendor local_timestamp, not unverified Binance metric create_time.\n")
if __name__=="__main__":main()
