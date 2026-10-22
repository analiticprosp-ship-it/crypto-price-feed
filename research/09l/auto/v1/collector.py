#!/usr/bin/env python3
"""09L AUTO v1.0 — research-only, idempotent, UTC and append-only.
Uses only public Tardis monthly samples. Optional CoinGlass Model2 PIT capture
requires premium API key AND user-provided private S3-compatible storage.
No trade-related writes or inferences. No raw licensed datasets in public git.
"""
import argparse,csv,datetime as dt,gzip,hashlib,io,json,os,pathlib,sys,urllib.error,urllib.parse,urllib.request

ROOT=pathlib.Path(__file__).resolve().parent
OUT=ROOT/"derived"
UA="09L-AUTO-v1.0-research-only"
MAX_BYTES=8_000_000
CG_ENDPOINT="https://open-api-v4.coinglass.com/api/futures/liquidation/aggregated-heatmap/model2"
TARDIS_SOURCES=(("bybit","BTCUSDT"),("okex-swap","BTC-USDT-SWAP"))

def utcnow():
 return dt.datetime.now(dt.timezone.utc)
def iso(t):
 return t.isoformat(timespec="seconds").replace("+00:00","Z")
def put_json(path,payload):
 path.parent.mkdir(parents=True,exist_ok=True)
 if path.exists():raise RuntimeError("APPEND_ONLY_DESTINATION_ALREADY_EXISTS: "+path.name)
 path.write_text(json.dumps(payload,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf8")
def check_existing_history():
 f=ROOT.parents[1]/"v0.8.6-2026-10-20"/"derived"/"09L_v086_resets_summary.json"
 try:
  a=json.loads(f.read_text(encoding="utf8"))
  checks={"studies":len(a),"all_status_ok":all(x.get("status")=="OK" for x in a),
   "fixed_unaffected":sum(x.get("fixed_unaffected",0) for x in a),
   "correct_gt_both":sum(min(x["strict"]["correct_gt_flipped_windows"],
    x["strict"]["correct_gt_shift_windows"]) for x in a)}
  checks["status"]="PASS" if checks["studies"]==2 and checks["all_status_ok"] and checks["fixed_unaffected"]==15 and checks["correct_gt_both"]==15 else "REVIEW_REQUIRED"
  return checks
 except Exception as e:return {"status":"MISSING_OR_BAD_SOURCE","error":type(e).__name__}
class Tap:
 def __init__(self,stream):self.stream=stream;self.digest=hashlib.sha256();self.n=0
 def read(self,n=-1):
  data=self.stream.read(n);self.n+=len(data);self.digest.update(data)
  if self.n>MAX_BYTES:raise RuntimeError("SOURCE_EXCEEDS_CAP")
  return data
def get_tardis_liquidations(exchange,symbol,day):
 url=f"https://datasets.tardis.dev/v1/{exchange}/liquidations/{day:%Y/%m/%d}/PERPETUALS.csv.gz"
 audit={"exchange":exchange,"symbol":symbol,"source_date":day.isoformat(),"type":"observed_liquidation_messages","url":url,
        "status":"UNVERIFIED"}
 try:
  resp=urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":UA}),timeout=45)
  if resp.status!=200:raise RuntimeError("HTTP_"+str(resp.status))
  tap=Tap(resp)
  reader=csv.DictReader(io.TextIOWrapper(gzip.GzipFile(fileobj=tap),encoding="utf8",newline=""))
  needed={"symbol","local_timestamp","side","price","amount"}
  if not needed.issubset(reader.fieldnames or []):raise ValueError("REQUIRED_COLUMNS_MISSING")
  rows=0;btcn=0;invalid=0;backwards=0;previous=None;buy=0;sell=0
  low=int(dt.datetime(day.year,day.month,day.day,tzinfo=dt.timezone.utc).timestamp()*1e6)
  for record in reader:
   rows+=1
   if record["symbol"]!=symbol:continue
   btcn+=1
   try:
    ts=int(record["local_timestamp"]);qty=float(record["amount"]);price=float(record["price"])
    if not(low<=ts<low+86_400_000_000 and qty>=0 and price>0):raise ValueError()
    if record["side"]=="buy":buy+=1
    elif record["side"]=="sell":sell+=1
    else:raise ValueError()
    if previous is not None and ts<previous:backwards+=1
    previous=ts
   except (ValueError,TypeError):invalid+=1
  audit.update(status="OK" if rows>0 and btcn>0 and invalid==0 and backwards==0 else "DATA_INCOMPLETE",
      raw_rows_all_symbols=rows,btc_rows_observed=btcn,buy_rows=buy,sell_rows=sell,
      bad_rows=invalid,nonmonotonic_btc_capture_rows=backwards,
      compressed_bytes=tap.n,compressed_sha256=tap.digest.hexdigest())
 except Exception as exc:
  audit.update(status="SOURCE_UNAVAILABLE",error=type(exc).__name__+": "+str(exc)[:120])
 return audit
def monthly_asof(now):
 sample=dt.date(now.year,now.month,1)
 if now.date()==sample or (now.date().day==2 and now.hour<7):
  # The current month's day-1 archive is not presumed published before next day.
  year,month=(now.year-1,12) if now.month==1 else (now.year,now.month-1)
  sample=dt.date(year,month,1)
 return sample
def monthly_ingest(now,force=False):
 sample=monthly_asof(now);dest=OUT/"monthly"/(sample.isoformat()+".json")
 if dest.exists() and not force:
  old=json.loads(dest.read_text(encoding="utf8"))
  if old.get("status")=="SOURCE_AUDIT_OK":
   return {"status":"ALREADY_ARCHIVED","path":str(dest.relative_to(ROOT)),"source_date":sample.isoformat()}
  # Retry incomplete snapshots on a NEW append-only file; never silently overwrite.
  dest=OUT/"monthly"/(sample.isoformat()+"_retry_"+now.strftime("%Y%m%dT%H%M%SZ")+".json")
 items=[get_tardis_liquidations(venue,sym,sample) for venue,sym in TARDIS_SOURCES]
 result={"study":"09L-AUTO-v1 public monthly source ledger","captured_at_utc":iso(utcnow()),
         "source_date":sample.isoformat(),"scope":"RESEARCH_SHADOW","sources":items,
         "status":"SOURCE_AUDIT_OK" if all(i["status"]=="OK" for i in items) else "DATA_INCOMPLETE",
         "limitations":["Tardis public samples are available on first day of each month only",
                        "Liquidation messages are not a heatmap or evidence of model-2 cluster first touches",
                        "No daily continuity or calibrated cascade probabilities",
                        "Raw vendor source is not copied into GitHub"]}
 if dest.exists():return {"status":"ALREADY_ARCHIVED_FORCE_NOT_PERMITTED","path":str(dest.relative_to(ROOT))}
 put_json(dest,result)
 return {"status":result["status"],"path":str(dest.relative_to(ROOT)),
  "source_date":sample.isoformat(),"counts":{i["exchange"]:i.get("btc_rows_observed") for i in items}}
def coinglass_pit(now):
 """If credential or private archive missing, never call API. No licensed raw data to public GitHub."""
 key=os.getenv("CG_API_KEY","").strip()
 bucket=os.getenv("PIT_S3_BUCKET","").strip()
 access=os.getenv("AWS_ACCESS_KEY_ID","").strip()
 secret=os.getenv("AWS_SECRET_ACCESS_KEY","").strip()
 if not key:return {"status":"PIT_SNAPSHOT_MISSING","reason":"NO_COINGLASS_PRO_API_KEY"}
 if not(bucket and access and secret):return {"status":"PIT_SNAPSHOT_MISSING","reason":"NO_PRIVATE_S3_STORAGE_CREDENTIALS"}
 try:
  # boto3 is optional; installed by the corresponding GitHub workflow only with credentials.
  import boto3
  url=CG_ENDPOINT+"?"+urllib.parse.urlencode({"symbol":"BTC","range":"3d"})
  req=urllib.request.Request(url,headers={"CG-API-KEY":key,"accept":"application/json","User-Agent":UA})
  with urllib.request.urlopen(req,timeout=35) as h:raw=h.read(15_000_001)
  if len(raw)>15_000_000:raise RuntimeError("COINGLASS_RESPONSE_TOO_LARGE")
  parsed=json.loads(raw)
  data=parsed.get("data",{})
  if str(parsed.get("code"))!="0" or not isinstance(data,dict):raise ValueError("BAD_COINGLASS_RESULT")
  for field in ("y_axis","liquidation_leverage_data","price_candlesticks"):
   if not isinstance(data.get(field),list):raise ValueError("BAD_FIELD_"+field)
  sha=hashlib.sha256(raw).hexdigest()
  captured=utcnow();ts=captured.strftime("%Y%m%dT%H%M%SZ")
  private_key=f"09l/pit/coinglass_model2_BTC_3d/{captured:%Y/%m/%d}/{ts}_{sha[:12]}.json"
  options={"region_name":os.getenv("AWS_DEFAULT_REGION","us-east-1")}
  endpoint=os.getenv("PIT_S3_ENDPOINT","").strip()
  if endpoint:options["endpoint_url"]=endpoint
  client=boto3.client("s3",**options)
  client.put_object(Bucket=bucket,Key=private_key,Body=raw,ContentType="application/json",
     Metadata={"sha256":sha,"source":"coinglass-v4-model2","captured-utc":iso(captured)})
  # Only metadata, never raw vendor data, reaches public repository.
  return {"status":"PIT_SNAPSHOT_STORED_PRIVATELY","captured_at_utc":iso(captured),
     "sha256":sha,"private_object_key":private_key,
     "y_axis_count":len(data["y_axis"]),
     "heatmap_points_count":len(data["liquidation_leverage_data"]),
     "candles_count":len(data["price_candlesticks"]),
     "unit_scope":"aggregated_BTC_3d","first_hit_verified":False}
 except Exception as exc:
  # Never print secrets, response body or untrusted server messages.
  return {"status":"PIT_SNAPSHOT_FAILED","error_type":type(exc).__name__}
def run(mode):
 now=utcnow()
 ledger={"study":"09L-AUTO-v1","mode":mode,"run_at_utc":iso(now),
         "branch_scope":"research-only","trade_canon_mutation":False,
         "historical_gate":check_existing_history()}
 if mode=="selftest":
  assert monthly_asof(dt.datetime(2026,10,22,12,tzinfo=dt.timezone.utc))==dt.date(2026,10,1)
  assert monthly_asof(dt.datetime(2026,11,1,12,tzinfo=dt.timezone.utc))==dt.date(2026,10,1)
  assert monthly_asof(dt.datetime(2027,1,2,6,tzinfo=dt.timezone.utc))==dt.date(2026,12,1)
  assert ledger["historical_gate"]["status"]=="PASS",ledger["historical_gate"]
  ledger["status"]="SELFTEST_PASS"
 elif mode in ("daily","monthly"):
  ledger["monthly_public_feed"]=monthly_ingest(now)
  if mode=="daily":ledger["pit_aggregated_model2"]=coinglass_pit(now)
  ledger["status"]="AUDIT_COMPLETE" if ledger["historical_gate"]["status"]=="PASS" else "HISTORICAL_QA_GATE_FAILED"
 elif mode=="pit":
  ledger["pit_aggregated_model2"]=coinglass_pit(now)
  ledger["status"]="AUDIT_COMPLETE"
 else:raise ValueError("UNKNOWN_MODE")
 if mode!="selftest":
  suffix=now.strftime("%Y%m%dT%H%M%SZ")
  filename=OUT/"runs"/(suffix+"_"+mode+".json")
  put_json(filename,ledger)
 print(json.dumps(ledger,ensure_ascii=False,sort_keys=True))
 return 0 if ledger["status"] in ("SELFTEST_PASS","AUDIT_COMPLETE") else 2
if __name__=="__main__":
 p=argparse.ArgumentParser();p.add_argument("--mode",choices=("selftest","daily","monthly","pit"),default="daily")
 sys.exit(run(p.parse_args().mode))
