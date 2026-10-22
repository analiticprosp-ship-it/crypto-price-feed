#!/usr/bin/env python3
"""09L AUTO v1.1: unattended sparse hourly as-collected public orderbook snapshots.
NO TRADING. Hourly REST samples are NOT continuous L2, liquidation clusters or CoinGlass PIT.
"""
import argparse, datetime as dt, hashlib, json, math, pathlib, urllib.request, urllib.error
BASE=pathlib.Path(__file__).resolve().parent
DEST=BASE/"derived"/"live_snapshots"
SOURCES=[
 ("bybit","spot","BTCUSDT","https://api.bybit.com/v5/market/orderbook?category=spot&symbol=BTCUSDT&limit=25"),
 ("bybit","linear","BTCUSDT","https://api.bybit.com/v5/market/orderbook?category=linear&symbol=BTCUSDT&limit=25"),
 ("okx","spot","BTC-USDT","https://www.okx.com/api/v5/market/books?instId=BTC-USDT&sz=25"),
 ("okx","swap","BTC-USDT-SWAP","https://www.okx.com/api/v5/market/books?instId=BTC-USDT-SWAP&sz=25")]
MAX=250_000;STALE_MS=120_000
def now_ms():return int(dt.datetime.now(dt.timezone.utc).timestamp()*1000)
def iso_ms(x):return dt.datetime.fromtimestamp(x/1000,dt.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00","Z")
def levels(v):
 out=[]
 for row in v:
  if len(row)<2:raise ValueError("BOOK_COLUMNS")
  p,q=float(row[0]),float(row[1])
  if not(math.isfinite(p) and math.isfinite(q)) or p<=0 or q<0:raise ValueError("INVALID_LEVEL")
  out.append([p,q])
 if len(out)<5:raise ValueError("LESS_THAN_5_LEVELS")
 return out
def summarize(bids,asks):
 b,a=levels(bids),levels(asks)
 if not all(b[i][0]>=b[i+1][0] for i in range(len(b)-1)):raise ValueError("UNSORTED_BID")
 if not all(a[i][0]<=a[i+1][0] for i in range(len(a)-1)):raise ValueError("UNSORTED_ASK")
 if b[0][0]>=a[0][0]:raise ValueError("CROSSED_BOOK")
 mid=(b[0][0]+a[0][0])/2
 def depth(xs,n):return round(sum(x[1] for x in xs[:n]),8)
 return {"bid1_price":b[0][0],"ask1_price":a[0][0],"mid_price":mid,
         "spread_bps":round((a[0][0]-b[0][0])/mid*10000,5),
         "bid_depth_top5_native":depth(b,5),"ask_depth_top5_native":depth(a,5),
         "bid_depth_top25_native":depth(b,25),"ask_depth_top25_native":depth(a,25),
         "top5_native_imbalance":round((depth(b,5)-depth(a,5))/(depth(b,5)+depth(a,5)),6) if depth(b,5)+depth(a,5)>0 else None,
         "source_levels_bid":len(b),"source_levels_ask":len(a)}
def read_one(venue,kind,symbol,url):
 start=now_ms()
 record={"venue":venue,"instrument_kind":kind,"symbol":symbol,"request_started_ms":start,
         "request_url":url,"status":"UNTESTED"}
 try:
  req=urllib.request.Request(url,headers={"User-Agent":"09L-AUTO-v1.1-research-readonly","Accept":"application/json"})
  with urllib.request.urlopen(req,timeout=16) as f:
   raw=f.read(MAX+1)
   if len(raw)>MAX:raise ValueError("SOURCE_SIZE_CAP")
   if f.status!=200:raise ValueError("SOURCE_HTTP_STATUS")
  end=now_ms()
  obj=json.loads(raw.decode("utf8"))
  if venue=="bybit":
   if obj.get("retCode")!=0:raise ValueError("SOURCE_API_ERROR")
   body=obj["result"]
   if body.get("s")!=symbol:raise ValueError("MISMATCH_SYMBOL")
   bid=body["b"];ask=body["a"];source_ts=int(body["ts"])
   extra={"book_update_sequence":body.get("u"),"cross_sequence":body.get("seq"),"matching_engine_ms":body.get("cts")}
  else:
   if obj.get("code")!="0":raise ValueError("SOURCE_API_ERROR")
   arr=obj["data"]
   if len(arr)!=1:raise ValueError("UNEXPECTED_BOOK_ROWS")
   body=arr[0];bid=body["bids"];ask=body["asks"];source_ts=int(body["ts"])
   extra={"checksum":body.get("checksum"),"book_update_sequence":body.get("seqId")}
  vals=summarize(bid,ask)
  age=end-source_ts
  if age>STALE_MS or age< -5_000:raise ValueError("SOURCE_STALE_OR_FUTURE_TIMESTAMP")
  record.update(status="SOURCE_SNAPSHOT_VALID",request_completed_ms=end,
    source_timestamp_ms=source_ts,source_age_ms=age,captured_at_utc=iso_ms(end),
    raw_response_sha256=hashlib.sha256(raw).hexdigest(),raw_response_bytes=len(raw),
    units="NATIVE_VENUE_BOOK_AMOUNTS_DO_NOT_CROSS_COMPARE",**vals,**extra)
 except Exception as e:
  restricted=isinstance(e,urllib.error.HTTPError) and e.code==403
  record.update(status="SOURCE_ACCESS_RESTRICTED" if restricted else "SOURCE_UNAVAILABLE_OR_INVALID",
   request_completed_ms=now_ms(),
   error_type=type(e).__name__,
   http_status=e.code if isinstance(e,urllib.error.HTTPError) else None,
   error_tag=str(e)[:80] if isinstance(e,ValueError) else "HTTP_403_ACCESS_RESTRICTED" if restricted else type(e).__name__)
 return record
def main(test=False):
 if test:
  z=summarize([["100","1"],["99","2"],["98","3"],["97","4"],["96","5"]],[["101","6"],["102","7"],["103","8"],["104","9"],["105","10"]])
  assert z["bid_depth_top5_native"]==15
  assert z["ask_depth_top5_native"]==40
  assert z["mid_price"]==100.5
  print(json.dumps({"status":"SELFTEST_PASS"}));return
 start=now_ms()
 src=[read_one(*x) for x in SOURCES]
 completed=now_ms()
 valid=sum(x["status"]=="SOURCE_SNAPSHOT_VALID" for x in src)
 obj={"study":"09L-AUTO-v1.1 sparse public market snapshot","capture_begin_utc":iso_ms(start),
      "capture_end_utc":iso_ms(completed),
      "status":"COMPLETE_4_VENUES" if valid==4 else "PARTIAL_CAPTURE" if valid>0 else "ALL_SOURCES_MISSING",
      "valid_snapshots":valid,"required_snapshots":4,"snapshots":src,
      "point_in_time_rule":"ONLY_AS_RECEIVED_PAST_SNAPSHOTS_NO_BACKFILL",
      "scope":"SHADOW_DATA_ONLY","cadence":"GITHUB_SCHEDULE_BEST_EFFORT_1H_NOT_CONTINUOUS",
      "scientific_validity":"INSUFFICIENT_FOR_CASCADE_OR_CLUSTER_FIRST_HIT",
      "coinglass_model2_PIT":"NOT_COLLECTED_NO_CONFIGURED_PREMIUM_KEY_AND_PRIVATE_STORAGE",
      "trading_system_changes":False}
 timestamp=dt.datetime.fromtimestamp(start/1000,dt.timezone.utc)
 p=DEST/timestamp.strftime("%Y/%m/%d")/(timestamp.strftime("%Y%m%dT%H%M%S")+"_"+str(start%1000).zfill(3)+".json")
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open("x",encoding="utf8") as f:f.write(json.dumps(obj,ensure_ascii=False,indent=2,sort_keys=True)+"\n")
 print(json.dumps({"status":obj["status"],"path":str(p.relative_to(BASE)),
                   "valid":valid,"sources":[[x["venue"],x["instrument_kind"],x["status"],x.get("error_tag")] for x in src]}))
if __name__=="__main__":
 p=argparse.ArgumentParser();p.add_argument("--selftest",action="store_true");a=p.parse_args();main(a.selftest)
