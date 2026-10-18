#!/usr/bin/env python3
"""Build 5m receipt-asof Binance OI research features from Tardis R2 sample.

For each closed 5-minute bucket take the newest nonblank vendor OI observation
received by Tardis at/before bucket END + 30 seconds. The delay is a research
convention, NOT proof of actual user-visible release or trading edge.
"""
import csv,datetime as dt,gzip,hashlib,io,json,math,os,statistics
import boto3

ROOT="research/tardis-binance-oi-sample/v1/2026-10-01"
DAY_US=int(dt.datetime(2026,10,1,tzinfo=dt.timezone.utc).timestamp()*1_000_000)
DAY_END_US=DAY_US+86_400_000_000
FIVE_US=300_000_000
DELAY_US=30_000_000
MAX_GZ=8_000_000
MAX_LINES=150_000
SYMBOLS=("BTCUSDT","ETHUSDT","SOLUSDT")
FIELDS=("bucket_start_utc","bucket_end_utc","decision_time_utc","symbol",
        "open_interest","vendor_receipt_utc","source_event_utc",
        "observation_age_seconds","source_vendor","asof_quality")

def isotime(us):return dt.datetime.fromtimestamp(us/1_000_000,dt.timezone.utc).isoformat()
def latest_asof(records,decision_us):
 """Stable receipt-time sort; no records received after decision can enter."""
 eligible=(r for r in records if r["local_us"]<=decision_us)
 return max(eligible,key=lambda r:(r["local_us"],r["order"]),default=None)

def load_rows(blob,symbol):
 rows=[]
 with gzip.open(io.BytesIO(blob),"rt",encoding="utf-8-sig",newline="") as inp:
  reader=csv.DictReader(inp)
  needed={"symbol","timestamp","local_timestamp","open_interest"}
  if not needed.issubset(reader.fieldnames or []):raise ValueError("SOURCE_COLUMNS_MISSING")
  for i,row in enumerate(reader):
   if i>=MAX_LINES:raise ValueError("SOURCE_ROW_COUNT_LIMIT")
   if row["symbol"]!=symbol:raise ValueError("SOURCE_SYMBOL_MISMATCH")
   oi=row.get("open_interest","")
   if oi in ("",None):continue
   try:
    n=float(oi);local=int(row["local_timestamp"]);source=int(row["timestamp"])
    if not math.isfinite(n) or n<0:raise ValueError("BAD_OI")
   except (ValueError,TypeError):raise ValueError("SOURCE_OI_OR_TIMESTAMP_INVALID")
   if not 1600000000000000<=local<=1900000000000000:raise ValueError("SOURCE_TIME_INVALID")
   if not DAY_US<=local<DAY_END_US:continue
   rows.append({"order":i,"local_us":local,"source_us":source,"open_interest":oi})
 if not rows:raise ValueError("NO_VALID_OI_OBSERVATIONS")
 return rows

def produce(symbol,records):
 rows=[];ages=[];future=0
 records=sorted(records,key=lambda r:(r["local_us"],r["order"]))
 cursor=0;last=None
 for i in range(288):
  start=DAY_US+i*FIVE_US;end=start+FIVE_US;decision=end+DELAY_US
  while cursor<len(records) and records[cursor]["local_us"]<=decision:
   last=records[cursor];cursor+=1
  # 'last' is exactly what latest_asof(records,decision) would return.
  if last is None:
   rows.append({"bucket_start_utc":isotime(start),"bucket_end_utc":isotime(end),
                "decision_time_utc":isotime(decision),"symbol":symbol,
                "open_interest":"","vendor_receipt_utc":"","source_event_utc":"",
                "observation_age_seconds":"","source_vendor":"Tardis.dev",
                "asof_quality":"MISSING_ASOF_OI"})
   continue
  if last["local_us"]>decision:future+=1
  age=(decision-last["local_us"])/1_000_000;ages.append(age)
  rows.append({"bucket_start_utc":isotime(start),"bucket_end_utc":isotime(end),
               "decision_time_utc":isotime(decision),"symbol":symbol,
               "open_interest":last["open_interest"],
               "vendor_receipt_utc":isotime(last["local_us"]),
               "source_event_utc":isotime(last["source_us"]),
               "observation_age_seconds":f"{age:.6f}",
               "source_vendor":"Tardis.dev",
               "asof_quality":"OK_VENDOR_RECEIPT_PROVISIONAL" if age<=120
                              else "STALE_VENDOR_OI_OVER_120S"})
 if future:raise ValueError("LOOKAHEAD_DETECTED")
 return rows,{"buckets":len(rows),"with_asof_oi":len(ages),
              "stale_over_120s":sum(age>120 for age in ages),
              "max_age_s":max(ages) if ages else None,
              "median_age_s":statistics.median(ages) if ages else None,
              "future_receipt_used":future,"underlying_snapshots":len(records)}

def store(s3,bucket,key,blob,typ):
 digest=hashlib.sha256(blob).hexdigest()
 s3.put_object(Bucket=bucket,Key=key,Body=blob,ContentType=typ,Metadata={"sha256":digest})
 readback=s3.get_object(Bucket=bucket,Key=key)["Body"].read(len(blob)+1)
 if hashlib.sha256(readback).hexdigest()!=digest:raise ValueError("R2_SHA256_READBACK_MISMATCH")
 return digest

def main():
 bucket=os.environ["R2_BUCKET"]
 s3=boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
  aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
  region_name="auto")
 manifest=json.loads(s3.get_object(Bucket=bucket,Key=ROOT+"/manifest.json")["Body"].read())
 if manifest.get("schema")!="detector-tardis-binance-oi-receipt-asof-sample-v1":
  raise ValueError("SOURCE_MANIFEST_SCHEMA_MISMATCH")
 outputs=[]
 for sym in SYMBOLS:
  matching=[r for r in manifest["records"] if r["symbol"]==sym]
  if len(matching)!=1:raise ValueError("SOURCE_MANIFEST_AMBIGUOUS")
  meta=matching[0];object_key=meta["r2_key"]
  obj=s3.get_object(Bucket=bucket,Key=object_key)
  if int(obj["ContentLength"])>MAX_GZ:raise ValueError("SOURCE_COMPRESSED_SIZE_LIMIT")
  blob=obj["Body"].read(MAX_GZ+1)
  if hashlib.sha256(blob).hexdigest()!=meta["compressed_sha256"]:
   raise ValueError("SOURCE_SHA256_MISMATCH")
  original=load_rows(blob,sym)
  rows,stats=produce(sym,original)
  if stats["buckets"]!=288 or stats["future_receipt_used"]:
   raise ValueError("ASOF_QUALITY_GATE_FAILED")
  out=io.StringIO(newline="");w=csv.DictWriter(out,fieldnames=FIELDS);w.writeheader();w.writerows(rows)
  key=ROOT+"/derived/"+sym+"_tardis_vendor_asof_5m.csv"
  digest=store(s3,bucket,key,out.getvalue().encode(),"text/csv")
  outputs.append({"symbol":sym,"source_sha256":meta["compressed_sha256"],"object_key":key,
                  "sha256":digest,**stats})
 result={"schema":"detector-tardis-oi-vendor-receipt-5m-asof-v1","date":"2026-10-01",
  "run_id":os.environ["GITHUB_RUN_ID"],"decision_lag_after_bucket_end_seconds":30,
  "venue":"Binance USDM OI observed at Tardis",
  "source":"Tardis derivative_ticker, not Binance 5m metric CSV",
  "cutoff":"vendor local_timestamp<=5m_end+30s",
  "lookahead_status":"NO_VENDOR_TIMESTAMP_LEAKAGE",
  "important_limits":["Vendor receipt is not guaranteed release time to our execution venue",
     "Only one free day; statistical edge and causal price label alignment untested",
     "Never treat Binance create_time as equivalent to Tardis local_timestamp"],
  "outputs":outputs,"research_only":True}
 key=ROOT+"/derived/manifest.json"
 digest=store(s3,bucket,key,json.dumps(result,indent=2,ensure_ascii=False).encode(),"application/json")
 result["manifest_sha256"]=digest
 print("TARDIS_VENDOR_ASOF_5M",json.dumps(result,ensure_ascii=False),flush=True)
 if os.environ.get("GITHUB_STEP_SUMMARY"):
  with open(os.environ["GITHUB_STEP_SUMMARY"],"a",encoding="utf-8") as fp:
   fp.write("## Detector: Tardis vendor-receipt 5m as-of sample\n\n")
   for x in outputs:fp.write(f"- {x['symbol']}: {x['with_asof_oi']}/288 OI buckets, future used: {x['future_receipt_used']}, stale: {x['stale_over_120s']}\n")
   fp.write("- Not Binance 5m metrics; publication and trading edge unverified.\n")
if __name__=="__main__":main()
