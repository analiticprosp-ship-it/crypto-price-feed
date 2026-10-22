#!/usr/bin/env python3
"""09L prospective CoinGlass Model2 aggregated BTC heatmap into existing PRIVATE R2.
Does nothing without separately licensed CG_API_KEY. No paid subscription/action.
Raw response NEVER committed to public GitHub or GH artifacts. Research only.
"""
import argparse,datetime as dt,hashlib,json,os,pathlib,urllib.parse,urllib.request
ROOT=pathlib.Path(__file__).resolve().parent
ENDPOINT="https://open-api-v4.coinglass.com/api/futures/liquidation/aggregated-heatmap/model2"
R2_ENV=("R2_ACCOUNT_ID","R2_ACCESS_KEY_ID","R2_SECRET_ACCESS_KEY","R2_BUCKET")
def utc():return dt.datetime.now(dt.timezone.utc)
def main(dry_run=False):
 now=utc()
 report={"study":"09L prospective CoinGlass aggregated Model2 BTC heatmap",
         "captured_attempt_at_utc":now.isoformat(),"data_rights":"PRIVATE_R2_ONLY_NO_GITHUB_RAW",
         "symbol":"BTC","heatmap_range":"3d","source":ENDPOINT,
         "historical_point_in_time":"ONLY_AFTER_SUCCESSFUL_AS_COLLECTED_PRIVATE_SAVE",
         "first_hit_verified":False,"trade_canon_changes":False,
         "status":"NOT_RUN"}
 if dry_run:
  assert ENDPOINT.endswith("aggregated-heatmap/model2")
  assert len(R2_ENV)==4
  print(json.dumps({"status":"SELFTEST_PASS"}));return
 key=os.getenv("CG_API_KEY","").strip()
 missing_r2=[x for x in R2_ENV if not os.getenv(x)]
 if not key:report.update(status="PIT_SNAPSHOT_MISSING",reason="COINGLASS_PRO_API_KEY_NOT_CONFIGURED")
 elif missing_r2:report.update(status="PIT_SNAPSHOT_MISSING",reason="EXISTING_R2_SECRETS_NOT_AVAILABLE")
 else:
  try:
   # Be sure the user's CoinGlass entitlement and license allow storage.
   import boto3
   qs=urllib.parse.urlencode({"symbol":"BTC","range":"3d"})
   req=urllib.request.Request(ENDPOINT+"?"+qs,headers={"CG-API-KEY":key,"accept":"application/json",
                                                      "User-Agent":"09L-PIT-v087-research"})
   with urllib.request.urlopen(req,timeout=32) as response:
    if response.status!=200:raise ValueError("NON_200_API_RESPONSE")
    raw=response.read(12_000_001)
   received=utc()
   if len(raw)>12_000_000:raise ValueError("MAX_RESPONSE_EXCEEDED")
   parsed=json.loads(raw)
   if str(parsed.get("code"))!="0" or not isinstance(parsed.get("data"),dict):
    raise ValueError("API_STATUS_OR_SCHEMA_NOT_VALID")
   data=parsed["data"]
   if not all(isinstance(data.get(k),list) for k in ("y_axis","liquidation_leverage_data","price_candlesticks")):
    raise ValueError("MODEL2_REQUIRED_ARRAYS_MISSING")
   sha=hashlib.sha256(raw).hexdigest()
   client=boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
                       aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
                       aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
   bucket=os.environ["R2_BUCKET"]
   object_key=f"research/09l/pit/coinglass_model2_aggregated_btc_3d/{received:%Y/%m/%d}/{received:%Y%m%dT%H%M%S%fZ}_{sha[:16]}.json"
   # Create immutable private record; read back to prove storage before calling it a valid PIT snapshot.
   client.put_object(Bucket=bucket,Key=object_key,Body=raw,ContentType="application/json",
                    Metadata={"sha256":sha,"captured-utc":received.strftime("%Y%m%dT%H%M%SZ")})
   ret=client.get_object(Bucket=bucket,Key=object_key)["Body"].read()
   if hashlib.sha256(ret).hexdigest()!=sha:raise RuntimeError("R2_SHA256_READBACK_MISMATCH")
   report.update(status="PIT_SNAPSHOT_STORED_PRIVATE_R2",r2_object_key=object_key,
                 sha256=sha,as_collected_at_utc=received.isoformat(),
                 request_started_at_utc=now.isoformat(),readback="SHA256_PASS",
                 shape={"price_levels":len(data["y_axis"]),
                        "heatmap_points":len(data["liquidation_leverage_data"]),
                        "candles":len(data["price_candlesticks"])})
  except Exception as e:
   # Never leak response bodies/keys/errors that might contain secrets.
   report.update(status="PIT_SNAPSHOT_FAILED",error_type=type(e).__name__)
 directory=ROOT/"derived"/"coinglass_pit_attempts"
 directory.mkdir(parents=True,exist_ok=True)
 fp=directory/(now.strftime("%Y%m%dT%H%M%S%fZ")+".json")
 with fp.open("x") as f:f.write(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
 print(json.dumps({"status":report["status"],"reason":report.get("reason"),
                  "private_readback":report.get("readback"),"report":str(fp.relative_to(ROOT))}))
if __name__=="__main__":
 p=argparse.ArgumentParser();p.add_argument("--selftest",action="store_true");main(p.parse_args().selftest)
