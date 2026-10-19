#!/usr/bin/env python3
"""Prospective 48-hour OKX 5-minute OI availability research, never trading.

Observed receipt times bound availability at this runner, not publication time.
"""
import datetime as dt, hashlib, json, os, time, urllib.error, urllib.parse, urllib.request
import boto3
from botocore.exceptions import ClientError

PREFIX="research/oi-availability-okx/v1/pilot"
SCHEMA="detector-okx-oi-5m-forward-48h-v1"
SYMBOLS=("BTC-USDT-SWAP","ETH-USDT-SWAP","SOL-USDT-SWAP")
DURATION_MS=48*3600*1000
MAX_BYTES=500_000
MAX_POLL_ATTEMPTS=3
RETRY_BACKOFF_SECONDS=(1,2)

def now_ms():return int(time.time()*1000)
def utc(ms):return dt.datetime.fromtimestamp(ms/1000,dt.timezone.utc).isoformat()
def encoded(obj):return json.dumps(obj,sort_keys=True,ensure_ascii=False,separators=(",",":")).encode()

def store(s3,bucket,key,obj):
 data=encoded(obj)
 if len(data)>MAX_BYTES:raise ValueError("R2_RECORD_TOO_LARGE")
 digest=hashlib.sha256(data).hexdigest()
 s3.put_object(Bucket=bucket,Key=key,Body=data,ContentType="application/json",Metadata={"sha256":digest})
 body=s3.get_object(Bucket=bucket,Key=key)["Body"].read(MAX_BYTES+1)
 if hashlib.sha256(body).hexdigest()!=digest:raise ValueError("R2_READBACK_SHA256_FAILURE")
 return digest

def load(s3,bucket,key):
 try:
  obj=s3.get_object(Bucket=bucket,Key=key)
  if int(obj.get("ContentLength",-1))>MAX_BYTES:raise ValueError("R2_RECORD_SIZE_LIMIT")
  return json.loads(obj["Body"].read(MAX_BYTES+1))
 except ClientError as e:
  if e.response.get("Error",{}).get("Code") in ("404","NoSuchKey","NotFound"):return None
  raise

def validate_oi_data(payload,instrument,received_ms):
 if payload.get("code")!="0":raise ValueError("OKX_API_STATUS_NOT_SUCCESS")
 rows=payload.get("data")
 if not isinstance(rows,list) or not 1<=len(rows)<=100:raise ValueError("OKX_OI_ROWS_INVALID")
 parsed=[]
 for row in rows:
  if not isinstance(row,list) or len(row)<2:raise ValueError("OKX_OI_ROW_INVALID")
  label=int(row[0])
  if not 1600000000000<=label<=received_ms+60000:raise ValueError("OKX_OI_EVENT_LABEL_RANGE")
  parsed.append({"timestamp_ms":label,"raw":row,"sha256":hashlib.sha256(encoded(row)).hexdigest()})
 if len({x["timestamp_ms"] for x in parsed})!=len(parsed):raise ValueError("OKX_OI_DUPLICATE_TIMESTAMPS")
 return sorted(parsed,key=lambda r:r["timestamp_ms"])

def poll(instrument):
 url="https://www.okx.com/api/v5/rubik/stat/contracts/open-interest-history?"+urllib.parse.urlencode({"instId":instrument,"period":"5m","limit":100})
 start_ms=now_ms();start_mono=time.monotonic_ns()
 req=urllib.request.Request(url,headers={"Accept":"application/json","User-Agent":"Detector-H1H10-Forward-Research/1.0"})
 with urllib.request.urlopen(req,timeout=15) as resp:
  if resp.status!=200:raise ValueError("OKX_OI_HTTP_ERROR")
  server_date=resp.headers.get("Date");body=resp.read(150001)
 received=now_ms()
 if len(body)>150000:raise ValueError("OKX_OI_RESPONSE_LIMIT")
 return {"symbol":instrument,"request_start_ms":start_ms,"response_received_ms":received,
         "response_round_trip_ms":(time.monotonic_ns()-start_mono)//1000000,
         "server_date_header":server_date,"rows":validate_oi_data(json.loads(body),instrument,received),
         "provider":"OKX","api":"/api/v5/rubik/stat/contracts/open-interest-history",
         "period":"5m","scope":"observed-receipt-not-publication"}

class PollAttemptFailure(Exception):
 """Typed exhausted/terminal poll failure, with receipt-side attempt provenance."""
 def __init__(self,cause,attempts):
  super().__init__(str(cause))
  self.cause=cause
  self.attempts=attempts


def transient_poll_error(exc):
 """Retry only temporary empty API data, HTTP 429/5xx or network disruptions."""
 if isinstance(exc,urllib.error.HTTPError):
  return exc.code==429 or 500<=exc.code<600
 if isinstance(exc,(urllib.error.URLError,TimeoutError,ConnectionError)):
  return True
 if isinstance(exc,ValueError):
  return str(exc)=="OKX_OI_ROWS_INVALID"
 return False


def poll_with_retries(instrument,deadline_ms,fetch=None,sleeper=None,clock=None):
 """Finite retry; each unsuccessful attempt is marked, never backdated or interpolated."""
 if fetch is None:fetch=poll
 if sleeper is None:sleeper=time.sleep
 if clock is None:clock=now_ms
 history=[]
 for index in range(MAX_POLL_ATTEMPTS):
  if clock()>=deadline_ms:
   raise PollAttemptFailure(ValueError("PILOT_DEADLINE_REACHED"),history)
  started=clock()
  try:
   observed=fetch(instrument)
   history.append({"attempt":index+1,"status":"PASS",
                   "started_ms":started,"finished_ms":clock()})
   observed["attempt_trace"]=history
   return observed
  except Exception as exc:
   temporary=transient_poll_error(exc)
   history.append({"attempt":index+1,"status":"FAILED","started_ms":started,
                   "finished_ms":clock(),"error_type":type(exc).__name__,
                   "error_code":str(exc)[:100],"retryable":temporary})
   if not temporary or index+1==MAX_POLL_ATTEMPTS:
    raise PollAttemptFailure(exc,history) from exc
   sleeper(RETRY_BACKOFF_SECONDS[index])
 raise AssertionError("UNREACHABLE_POLL_LOOP")


def changes(previous,current):
 """Only an observed earlier success permits an absence lower-bound."""
 if previous is None:return [],[],True
 prior={x["timestamp_ms"]:x for x in previous["rows"]}
 prior_max=max(prior);prior_received=int(previous["response_received_ms"])
 if prior_received>current["response_received_ms"]:raise ValueError("NON_MONOTONIC_POLL_RECEIPT")
 seen=[];revisions=[]
 for row in current["rows"]:
  label=row["timestamp_ms"];old=prior.get(label)
  if old is not None:
   if old["sha256"]!=row["sha256"]:
    revisions.append({"source_timestamp_ms":label,"previous_sha256":old["sha256"],
                      "new_sha256":row["sha256"],"observed_ms":current["response_received_ms"]})
   continue
  absent=(label>prior_max and prior_received>=label)
  seen.append({"schema":SCHEMA,"provider":"OKX","symbol":current["symbol"],
               "source_timestamp_ms":label,"first_observed_ms":current["response_received_ms"],
               "first_observed_utc":utc(current["response_received_ms"]),
               "last_observed_absent_ms":prior_received if absent else None,
               "bound_type":"ABSENT_ON_PREVIOUS_POLL" if absent else "FIRST_OBSERVED_ONLY",
               "record_sha256":row["sha256"],
               "caveat":"Sampling bounds, not exact exchange publication time"})
 return seen,revisions,False

def disable_own_workflow():
 req=urllib.request.Request(
  "https://api.github.com/repos/"+os.environ["GITHUB_REPOSITORY"]+
  "/actions/workflows/detector-okx-oi-48h-pilot.yml/disable",
  data=b"",method="PUT",headers={"Authorization":"Bearer "+os.environ["GH_TOKEN"],
  "Accept":"application/vnd.github+json","User-Agent":"Detector-H1H10-Research/1.0"})
 with urllib.request.urlopen(req,timeout=15) as resp:
  if resp.status!=204:raise ValueError("WORKFLOW_SELF_DISABLE_NOT_CONFIRMED")

def main():
 bucket=os.environ["R2_BUCKET"]
 s3=boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
                 aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
                 aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
 config_key=PREFIX+"/config.json";config=load(s3,bucket,config_key)
 if config is None:
  start=now_ms()
  config={"schema":SCHEMA,"start_ms":start,"end_ms":start+DURATION_MS,
          "created_by_run_id":os.environ["GITHUB_RUN_ID"],"duration_hours":48,"research_only":True}
  store(s3,bucket,config_key,config)
 if config.get("schema")!=SCHEMA or config["end_ms"]-config["start_ms"]!=DURATION_MS:
  raise ValueError("PILOT_CONFIG_INVALID")
 if now_ms()>=config["end_ms"]:
  disable_own_workflow()
  print("OKX_OI_48H_PILOT_CLOSED",json.dumps({"status":"CLOSED_AND_DISABLED",
         "started":utc(config["start_ms"]),"ended":utc(config["end_ms"])}),flush=True)
  return
 rid=os.environ["GITHUB_RUN_ID"];attempt=os.environ.get("GITHUB_RUN_ATTEMPT","1")
 errors=[];summary=[]
 for sym in SYMBOLS:
  try:
   observed=poll_with_retries(sym,config["end_ms"])
   prev=load(s3,bucket,PREFIX+"/state/"+sym+".json")
   first,revisions,bootstrap=changes(prev,observed)
   # Write immutable raw poll prior to advancing last-successful state.
   poll_key=(PREFIX+"/polls/"+utc(observed["response_received_ms"])[:10]+"/"+
             rid+"-"+attempt+"-"+sym+".json")
   store(s3,bucket,poll_key,observed)
   n=0
   for item in first:
    key=PREFIX+"/first-observed/"+sym+"/"+str(item["source_timestamp_ms"])+".json"
    if load(s3,bucket,key) is None:store(s3,bucket,key,item);n+=1
   for item in revisions:
    key=PREFIX+"/revisions/"+sym+"/"+str(item["source_timestamp_ms"])+"/"+rid+"-"+attempt+".json"
    store(s3,bucket,key,item)
   store(s3,bucket,PREFIX+"/state/"+sym+".json",observed)
   label=observed["rows"][-1]["timestamp_ms"]
   summary.append({"symbol":sym,"status":"PASS","bootstrap":bootstrap,
     "rows":len(observed["rows"]),"first_observed_new":n,"revisions":len(revisions),
     "attempts":observed["attempt_trace"],
     "newest_source_label":utc(label),"response_received_utc":utc(observed["response_received_ms"]),
     "lag_from_label_seconds":round((observed["response_received_ms"]-label)/1000,1)})
  except Exception as exc:
   underlying=exc.cause if isinstance(exc,PollAttemptFailure) else exc
   trace=exc.attempts if isinstance(exc,PollAttemptFailure) else []
   errors.append({"symbol":sym,"error_type":type(underlying).__name__,
                  "message":str(underlying)[:120],"attempts":trace})
   summary.append({"symbol":sym,"status":"ERROR","attempts":trace})
 result={"schema":SCHEMA,"run_id":rid,"attempt":attempt,
         "status":"POLL_PASS" if not errors else "POLL_PARTIAL",
         "pilot_start_utc":utc(config["start_ms"]),"pilot_end_utc":utc(config["end_ms"]),
         "observed_at_utc":utc(now_ms()),"symbols":summary,"errors":errors,
         "source_publication_time":"UNVERIFIED",
         "caveat":"GitHub cron is best-effort; never equate source labels with receipt times"}
 store(s3,bucket,PREFIX+"/run-reports/"+rid+"-"+attempt+".json",result)
 print("OKX_OI_48H_PILOT",json.dumps(result,ensure_ascii=False),flush=True)
 if os.environ.get("GITHUB_STEP_SUMMARY"):
  with open(os.environ["GITHUB_STEP_SUMMARY"],"a",encoding="utf-8") as fp:
   fp.write("## Детектор — 48 часов OI OKX (research)\n\n")
   fp.write(f"- Статус: {result['status']}\n- Начало: {result['pilot_start_utc']}\n")
   fp.write(f"- Конец (UTC): {result['pilot_end_utc']}\n- Ошибки: {len(errors)}\n")
   for row in summary:fp.write(f"- {row['symbol']}: {row['status']}, новых first-seen: {row.get('first_observed_new',0)}\n")
   fp.write("- Время публикации поставщиком: не подтверждено.\n")
 if errors:raise SystemExit(2)

if __name__=="__main__":
 main()
